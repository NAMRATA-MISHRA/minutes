from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from google import genai
from google.genai import errors as genai_errors

from app.config import settings
from app.models import GenerateNotesResponse
from app.services import (
    chunk_text,
    clean_transcript,
    ensure_upload_dir,
    generate_minutes,
    summarize_chunks,
    transcribe_audio,
)
from app.storage import get_meeting, initialize_db, list_meetings, save_meeting

app = FastAPI(title="Meeting Minutes AI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Before StaticFiles mount: directory must exist; paths are absolute under backend/ (see config).
ensure_upload_dir(settings.upload_dir)
initialize_db(settings.database_path)

app.mount("/uploads", StaticFiles(directory=settings.upload_dir), name="uploads")


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "gemini_configured": bool(settings.gemini_api_key),
        "gemini_model": settings.gemini_model if settings.gemini_api_key else None,
    }


@app.post("/upload-audio")
async def upload_audio(file: Annotated[UploadFile, File(...)]) -> dict:
    ensure_upload_dir(settings.upload_dir)
    filename = f"{Path(file.filename or 'audio').stem}_{Path(file.filename or 'audio').suffix or '.webm'}"
    safe_name = filename.replace(" ", "_")
    dest = Path(settings.upload_dir) / safe_name

    content = await file.read()
    dest.write_bytes(content)

    return {
        "message": "Audio uploaded successfully",
        "file_url": f"/uploads/{safe_name}",
        "file_path": str(dest),
    }


@app.post("/generate-notes", response_model=GenerateNotesResponse)
async def generate_notes(
    file: Annotated[UploadFile | None, File()] = None,
    file_url: Annotated[str | None, Form()] = None,
) -> GenerateNotesResponse:
    api_key = settings.gemini_api_key
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail=(
                "Missing GEMINI_API_KEY (or GOOGLE_API_KEY). Add it to backend/.env (or repo-root .env) "
                "and restart the server. See backend/.env.example."
            ),
        )

    ensure_upload_dir(settings.upload_dir)
    audio_path: str | None = None

    if file is not None:
        raw_name = file.filename or "meeting_audio.webm"
        safe_name = raw_name.replace(" ", "_")
        dest = Path(settings.upload_dir) / safe_name
        dest.write_bytes(await file.read())
        audio_path = str(dest)
    elif file_url:
        if file_url.startswith("/uploads/"):
            audio_path = str(Path(settings.upload_dir) / file_url.replace("/uploads/", "", 1))
        else:
            audio_path = file_url

    if not audio_path or not Path(audio_path).exists():
        raise HTTPException(
            status_code=400,
            detail="Provide a valid file upload or local file_url from /upload-audio",
        )

    client = genai.Client(api_key=api_key)
    model = settings.gemini_model

    try:
        raw_transcript = await transcribe_audio(client, model, audio_path)
        cleaned_transcript = clean_transcript(raw_transcript)
        chunks = chunk_text(cleaned_transcript)
        normalized_transcript = await summarize_chunks(client, model, chunks)
        notes = await generate_minutes(client, model, normalized_transcript)
    except genai_errors.ClientError as exc:
        msg = str(exc)
        code = 401 if any(s in msg for s in ("401", "UNAUTHENTICATED", "API key", "API_KEY")) else 400
        raise HTTPException(status_code=code, detail=f"Gemini client error: {exc}") from exc
    except genai_errors.ServerError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini server error: {exc}") from exc
    except genai_errors.APIError as exc:
        raise HTTPException(status_code=502, detail=f"Gemini API error: {exc}") from exc
    except TimeoutError as exc:
        raise HTTPException(status_code=504, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    saved = save_meeting(
        settings.database_path,
        transcript=normalized_transcript,
        notes=notes.model_dump(),
    )
    return GenerateNotesResponse(**saved)


@app.get("/meetings", response_model=list[GenerateNotesResponse])
async def meetings(limit: int = 50) -> list[GenerateNotesResponse]:
    rows = list_meetings(settings.database_path, limit=limit)
    return [GenerateNotesResponse(**row) for row in rows]


@app.get("/meetings/{meeting_id}", response_model=GenerateNotesResponse)
async def meeting_by_id(meeting_id: int) -> GenerateNotesResponse:
    meeting = get_meeting(settings.database_path, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="Meeting not found")
    return GenerateNotesResponse(**meeting)
