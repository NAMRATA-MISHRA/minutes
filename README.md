# Meeting Minutes AI

Meeting Minutes AI is a full-stack application that records or uploads meeting audio, transcribes it with OpenAI Whisper, and generates structured meeting minutes using GPT.

## Features

- Browser recording (Start/Stop) using `MediaRecorder`
- Audio upload to FastAPI backend (`POST /upload-audio`)
- Meeting notes generation (`POST /generate-notes`)
- Transcript cleanup + long transcript chunk handling
- Structured JSON minutes format:
  - `title`
  - `summary`
  - `key_points`
  - `decisions`
  - `action_items` (`task`, `owner`, `deadline`)
- Notes editing UI (transcript + generated notes)
- Local persistence in SQLite (`id`, `transcript`, `notes`, `created_at`)
- JSON export from frontend

## Tech Stack

- Backend: FastAPI (Python)
- Frontend: React + Vite
- AI:
  - Whisper (`whisper-1`) for transcription
  - GPT model (`OPENAI_MODEL`, default `gpt-4o-mini`) for minute generation
- Storage: SQLite

## Project Structure

```text
minutes/
  backend/
    app/
      main.py
      services.py
      storage.py
      models.py
      config.py
    requirements.txt
    .env.example
  frontend/
    src/
      App.jsx
      api.js
    .env.example
```

## Backend Setup

1. Create and activate a virtual environment:

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Configure environment:

```bash
cp .env.example .env
```

Set values in `.env`:

- `OPENAI_API_KEY`: your OpenAI API key
- `OPENAI_MODEL`: model for summary/notes generation
- `UPLOAD_DIR`: upload directory (default `uploads`)
- `DATABASE_PATH`: SQLite file path (default `meetings.db`)

4. Run backend:

```bash
uvicorn app.main:app --reload --port 8000
```

## Frontend Setup

1. Install dependencies:

```bash
cd frontend
npm install
```

2. Configure frontend environment:

```bash
cp .env.example .env
```

Set:

- `VITE_API_BASE_URL=http://localhost:8000`

3. Run frontend:

```bash
npm run dev
```

## API Endpoints

- `POST /upload-audio`
  - form-data: `file`
  - stores audio locally and returns `file_url`

- `POST /generate-notes`
  - form-data: `file` or `file_url`
  - flow:
    1. Whisper transcription
    2. transcript cleanup + optional chunk normalization
    3. GPT structured minutes generation
    4. save transcript/notes to SQLite

- `GET /meetings?limit=50`
  - returns latest saved meetings from SQLite

- `GET /meetings/{meeting_id}`
  - returns one saved meeting by id

## User Flow

1. Start and stop recording in the frontend (or upload an audio file).
2. Click **Generate Notes**.
3. App uploads audio, transcribes it, and generates minutes.
4. Transcript and notes are displayed and editable.
5. Meeting is saved automatically and appears in History.
6. Export minutes as JSON.
