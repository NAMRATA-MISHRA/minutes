import json
import re
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

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


async def transcribe_audio(client: AsyncOpenAI, file_path: str) -> str:
    with open(file_path, "rb") as audio_file:
        transcript = await client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
        )
    return transcript.text


async def summarize_chunks(client: AsyncOpenAI, model: str, chunks: list[str]) -> str:
    if len(chunks) == 1:
        return chunks[0]

    partials: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        response = await client.responses.create(
            model=model,
            input=[
                {
                    "role": "system",
                    "content": "Summarize this transcript chunk with factual bullet points only.",
                },
                {
                    "role": "user",
                    "content": f"Chunk {idx}/{len(chunks)}:\n\n{chunk}",
                },
            ],
        )
        partials.append(response.output_text)
    return "\n".join(partials)


def _minutes_json_schema() -> dict[str, Any]:
    return {
        "name": "meeting_minutes",
        "schema": {
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
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["title", "summary", "key_points", "decisions", "action_items"],
            "additionalProperties": False,
        },
        "strict": True,
    }


async def generate_minutes(
    client: AsyncOpenAI, model: str, transcript_text: str
) -> MeetingMinutes:
    response = await client.responses.create(
        model=model,
        input=[
            {
                "role": "system",
                "content": (
                    "You are an expert meeting assistant. Convert transcript content "
                    "into concise, professional meeting minutes."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Convert this transcript into structured meeting minutes. "
                    "Extract action items and include owner/deadline only if present; "
                    "otherwise use empty string for unknown values.\n\n"
                    f"Transcript:\n{transcript_text}"
                ),
            },
        ],
        text={"format": {"type": "json_schema", "name": "meeting_minutes", "schema": _minutes_json_schema()["schema"], "strict": True}},
    )

    text_payload = response.output_text
    parsed = json.loads(text_payload)
    return MeetingMinutes.model_validate(parsed)


def ensure_upload_dir(upload_dir: str) -> None:
    Path(upload_dir).mkdir(parents=True, exist_ok=True)
