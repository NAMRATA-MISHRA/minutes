import asyncio
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from app.models import MeetingMinutes

FILLER_WORDS_REGEX = re.compile(
    r"\b(um+|uh+|like|you know|i mean|sort of|kind of|basically|actually)\b",
    re.IGNORECASE,
)


def clean_transcript(text: str) -> str:
    cleaned = FILLER_WORDS_REGEX.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def chunk_text(text: str, max_chars: int = 7000) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + max_chars, len(text))
        if end < len(text):
            breakpoint = text.rfind(" ", start, end)
            end = breakpoint if breakpoint > start else end
        chunks.append(text[start:end].strip())
        start = end
    return [c for c in chunks if c]


async def _wait_until_file_active(client: genai.Client, file_name: str, timeout_s: float = 120.0) -> types.File:
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout_s
    current = await client.aio.files.get(name=file_name)
    while current.state != types.FileState.ACTIVE:
        if current.state == types.FileState.FAILED:
            err = getattr(current, "error", None)
            raise RuntimeError(f"Gemini file processing failed: {err or 'unknown error'}")
        if loop.time() > deadline:
            raise TimeoutError("Timed out waiting for uploaded audio to become ACTIVE in Gemini.")
        await asyncio.sleep(1.0)
        current = await client.aio.files.get(name=file_name)
    return current


def _text_from_response(response: types.GenerateContentResponse) -> str:
    text = (response.text or "").strip()
    if text:
        return text
    if response.candidates:
        for c in response.candidates:
            if c.content and c.content.parts:
                parts = [p.text for p in c.content.parts if getattr(p, "text", None)]
                if parts:
                    return "\n".join(parts).strip()
    raise RuntimeError("Gemini returned an empty response (check safety filters or model availability).")


async def transcribe_audio(client: genai.Client, model: str, file_path: str) -> str:
    path = Path(file_path)
    mime = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    upload_cfg = types.UploadFileConfig(mime_type=mime, display_name=path.name)
    uploaded = await client.aio.files.upload(file=str(path), config=upload_cfg)
    try:
        ready = await _wait_until_file_active(client, uploaded.name)
        response = await client.aio.models.generate_content(
            model=model,
            contents=[
                (
                    "Transcribe this audio verbatim. Output plain transcript text only. "
                    "Do not add labels, markdown, or commentary."
                ),
                ready,
            ],
            config=types.GenerateContentConfig(temperature=0.0),
        )
        return _text_from_response(response)
    finally:
        try:
            await client.aio.files.delete(name=uploaded.name)
        except Exception:
            pass


async def summarize_chunks(client: genai.Client, model: str, chunks: list[str]) -> str:
    if len(chunks) == 1:
        return chunks[0]

    partials: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        response = await client.aio.models.generate_content(
            model=model,
            contents=(
                f"Summarize transcript chunk {idx}/{len(chunks)} using factual bullet points only. "
                "Do not invent details.\n\n"
                f"{chunk}"
            ),
            config=types.GenerateContentConfig(temperature=0.2),
        )
        partials.append(_text_from_response(response))
    return "\n".join(partials)


def _minutes_json_schema() -> dict[str, Any]:
    """JSON Schema for Gemini structured output (matches MeetingMinutes)."""
    return {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "summary": {"type": "string"},
            "key_points": {"type": "array", "items": {"type": "string"}},
            "decisions": {"type": "array", "items": {"type": "string"}},
            "action_items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "task": {"type": "string"},
                        "owner": {"type": "string"},
                        "deadline": {"type": "string"},
                    },
                    "required": ["task", "owner", "deadline"],
                },
            },
        },
        "required": ["title", "summary", "key_points", "decisions", "action_items"],
    }


async def generate_minutes(client: genai.Client, model: str, transcript_text: str) -> MeetingMinutes:
    schema = _minutes_json_schema()
    response = await client.aio.models.generate_content(
        model=model,
        contents=(
            "Convert this transcript into structured meeting minutes. "
            "Extract action items; use empty string for owner or deadline if not stated. "
            "Keep the output concise and professional.\n\n"
            f"Transcript:\n{transcript_text}"
        ),
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are an expert meeting assistant. You output only valid JSON that matches "
                "the requested schema."
            ),
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=0.3,
        ),
    )
    payload = _text_from_response(response)
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        parsed = json.loads(payload.strip().removeprefix("```json").removesuffix("```").strip())
    return MeetingMinutes.model_validate(parsed)


def ensure_upload_dir(upload_dir: str) -> None:
    Path(upload_dir).mkdir(parents=True, exist_ok=True)
