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


def _parse_meeting_minutes_json(payload: str) -> MeetingMinutes:
    """Parse model output into MeetingMinutes (handles fences / minor formatting)."""
    text = payload.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```\s*$", "", text)
    text = text.strip()
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            data = json.loads(text[start : end + 1])
        else:
            raise
    return MeetingMinutes.model_validate(data)


async def generate_minutes(client: genai.Client, model: str, transcript_text: str) -> MeetingMinutes:
    # Do not use response_json_schema here: Gemini often returns 500 INTERNAL
    # "Failed to convert server response to JSON" when server-side schema coercion fails.
    # application/json + prompt + Pydantic validation is more reliable across models.
    response = await client.aio.models.generate_content(
        model=model,
        contents=(
            "Convert this transcript into structured meeting minutes.\n"
            "Return one JSON object only (no markdown, no code fences) with exactly these keys:\n"
            '- "title": string\n'
            '- "summary": string\n'
            '- "key_points": array of strings\n'
            '- "decisions": array of strings\n'
            '- "action_items": array of objects, each with "task", "owner", "deadline" (all strings; '
            'use "" if unknown)\n\n'
            "Be concise and professional. Do not invent facts.\n\n"
            f"Transcript:\n{transcript_text}"
        ),
        config=types.GenerateContentConfig(
            system_instruction=(
                "You are an expert meeting assistant. You only output valid JSON for the user request."
            ),
            response_mime_type="application/json",
            temperature=0.3,
        ),
    )
    return _parse_meeting_minutes_json(_text_from_response(response))


def ensure_upload_dir(upload_dir: str) -> None:
    Path(upload_dir).mkdir(parents=True, exist_ok=True)
