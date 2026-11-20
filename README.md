# Startup Research Studio

A monorepo with a CrewAI/FastAPI backend and a Next.js frontend.

## Run the full stack with Docker Compose

Make sure Docker Desktop is running, then from the repository root run:

```powershell
docker compose up --build
```

Compose starts PostgreSQL, waits for it to become healthy, then starts the
FastAPI backend and Next.js frontend. Open `http://localhost:3000` for the UI
and `http://localhost:8000/docs` for the API docs. Stop the stack with
`Ctrl+C`; run `docker compose down` to stop and remove the containers while
keeping the database volume.

The backend reads `GEMINI_API_KEY`, `SERPER_API_KEY`, and other existing
application settings from `backend/.env`. Compose overrides `DATABASE_URL`
inside the backend container so it connects to the `db` service. Local
PostgreSQL data is persisted in the `postgres_data` Docker volume. By default,
the database is exposed to the host on port `5433` to avoid conflicting with a
local PostgreSQL already using port `5432`.

The default PostgreSQL username and password in Compose are for local
development only. Set `POSTGRES_USER`, `POSTGRES_PASSWORD`, and optionally
`POSTGRES_DB` in a root `.env` file before using this setup beyond a local
development machine. Set `POSTGRES_HOST_PORT` to change the host port, or
`NEXT_PUBLIC_API_URL` if the browser must reach the backend at a different
address.

## Backend

Configure `DATABASE_URL`, `GEMINI_API_KEY`, and `SERPER_API_KEY` in
`backend/.env`. Start FastAPI from the backend directory:

```powershell
Set-Location backend
uv sync
uv run python -m uvicorn main:app --reload
```

The API is available at `http://127.0.0.1:8000`; its interactive docs are at
`http://127.0.0.1:8000/docs`. Submit a startup idea with `POST /reports` using
`{"idea":"..."}`, then poll `GET /reports/{job_id}` for its status and result.

Run the CrewAI Flow directly from `backend/` with:

```powershell
uv run python flow.py
```

## Frontend

After Node.js and npm are installed, start the Next.js app from the frontend
directory:

```powershell
Set-Location frontend
npm run dev
```

The frontend should call the backend at `http://127.0.0.1:8000`. Keep the API
and frontend running in separate terminals during local development. To use a
different API address, set `NEXT_PUBLIC_API_URL` in `frontend/.env.local`.

## Project structure

- `backend/` - CrewAI Flow, FastAPI API, agent/task configuration, and Python dependencies
- `frontend/` - Next.js application
