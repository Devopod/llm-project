---
name: testing-astradev
description: End-to-end testing guide for AstraDev platform. Use when verifying signup, project creation, multi-agent pipeline, file generation, APK build, and ZIP download.
---

# Testing AstraDev End-to-End

## Architecture Overview
- **Frontend:** Next.js 14 at localhost:3000
- **Backend:** Django 5 + Daphne (ASGI) at localhost:8000
- **Worker:** Celery with Redis broker (redis://localhost:6379/1)
- **Database:** PostgreSQL at localhost:5432 (astradev/astradev_secret)
- **AI:** Groq API with dual-key rotation

## Running the Stack

```bash
# Start infrastructure (if not running)
cd /home/ubuntu/repos/astradev && docker compose up -d

# Start backend (Daphne ASGI for WebSocket support)
cd backend && daphne -b 0.0.0.0 -p 8000 astradev.asgi:application &

# Start Celery worker
cd backend && celery -A astradev.celery_app worker --loglevel=info --concurrency=2 &

# Start frontend
cd frontend && npx next start -p 3000 &
```

## Key Test Flows

### 1. Signup Flow
- Navigate to /signup
- Fill: Display Name, Email, Password (min 8 chars, uppercase, lowercase, number, special)
- Submit → should redirect to /dashboard

### 2. Project Creation + Agent Pipeline
- Click "+ New Project" on dashboard
- Fill name and prompt (keep prompt SHORT - under 50 words for Groq free tier)
- Click "Start Building"
- Wait 30-60 seconds for pipeline (Groq rate limits cause retries)
- Verify status changes: planning → in_progress → completed
- Verify tasks appear in sidebar
- Verify files appear in sidebar

### 3. Files Tab
- Click file name in sidebar to view content
- Verify code is displayed in a pre/code block

### 4. Build APK
- Click "Build APK" button (top-right, red)
- Verify chat message is sent to agent requesting Android project generation
- APK build creates Android project structure files (not actual compiled APK without Android SDK)

### 5. Download ZIP
- Click "Download ZIP" button
- Verify ZIP file downloads with project files

## Known Issues / Gotchas

- **Groq free tier TPM limit (8000 tokens/min):** Keep prompts short. The system automatically retries with backoff but pipelines take longer.
- **max_tokens parameter:** Groq SDK uses `max_tokens`, NOT `max_completion_tokens`. If you see "unexpected keyword argument" errors, check groq_client.py.
- **Next.js params:** Use `useParams()` hook, NOT `use(params)` with Promise params - the latter crashes in production builds.
- **WebSocket messages:** Messages may appear on refresh rather than live-streaming depending on timing. The WebSocket connection is functional but the initial messages during pipeline creation come before the connection is established.
- **Celery hot reload:** Celery does NOT hot-reload. After changing agent code, you must restart the Celery worker: `pkill -f "celery -A astradev"; cd backend && celery -A astradev.celery_app worker --loglevel=info --concurrency=2 &`

## Devin Secrets Needed

- `GROQ_API_KEY_1` — Groq API key (primary)
- `GROQ_API_KEY_2` — Groq API key (secondary/rotation)

## Checking Logs

```bash
# Celery worker logs (agent pipeline execution)
tail -f /tmp/celery.log

# Django backend logs
# Check the terminal running daphne

# Check if Groq API calls succeed
grep "HTTP/1.1 200 OK" /tmp/celery.log
grep "Groq API error" /tmp/celery.log
```
