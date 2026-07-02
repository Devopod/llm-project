---
name: testing-astradev
description: End-to-end testing guide for AstraDev platform. Use when verifying signup, project creation, multi-agent pipeline, file generation, APK build, ZIP download, settings, billing, docs, admin panel, and deploy flow.
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
- **Important:** Clear localStorage before signup if you see "Token expired" errors from stale sessions

### 2. NavBar Navigation
- After signup, verify NavBar shows: Projects, Docs, Billing, Settings, Account, Logout
- All links navigate to correct pages

### 3. Settings Page (/settings)
- Email field is disabled (not editable)
- Display Name is editable
- Bio textarea available
- Click "Save Changes" → "Profile updated successfully" message
- Subscription section shows current plan with "Manage Billing" button
- Change Password section with current/new password fields
- Danger Zone with "Delete Account" button

### 4. Billing Page (/billing)
- **Usage stats:** Messages Today (x/20 for free), APK Builds Today (x/3), Total Projects
- **Plan cards:** Free ($0, "Current Plan" disabled), Pro ($8/month, 976 BDT/month), Plus ($20/month, 2440 BDT/month)
- **bKash modal:** Click "Upgrade to Pro" or "Upgrade to Plus"
  - Shows "Pay via bKash" heading
  - bKash number: 01849691859
  - Amount with BDT conversion (1 USD = 122 BDT)
  - Transaction ID and bKash Number input fields
  - Submit Payment and Cancel buttons

### 5. Docs Page (/docs)
- Sidebar with 7 sections: Getting Started, AI Agents, Supported Languages, APK Build, Plans & Pricing, Workspaces, API Reference
- Click sections to navigate content
- Plans & Pricing section shows correct pricing info ($8/976BDT, $20/2440BDT)

### 6. Admin Panel (/admin)
- **Credentials:** Admin123 / Admin123
- Login form with Username and Password fields
- **Note:** Wrong credentials correctly reject login but may not show visible error text (known minor UX issue)
- Dashboard tab: 4 stat cards (Total Users, Active Users, Total Projects, Pending Payments) + Plan Distribution
- Users tab: table with Email, Name, Plan, Messages, Projects, Joined, Actions (Delete)
- Payments tab: table with Date, User, Plan, Amount, TxID, Sender, Status, Actions (Verify/Reject)

### 7. Project Creation + Agent Pipeline
- Click "+ New Project" on dashboard
- Fill name and prompt (keep prompt SHORT - under 50 words for Groq free tier)
- Click "Start Building"
- Wait 30-60 seconds for pipeline (Groq rate limits cause retries)
- Verify status changes: planning → in_progress → completed
- Verify tasks appear in sidebar
- Verify files appear in sidebar

### 8. Deploy Button
- On project page, verify purple "Deploy" button alongside "Build APK" and "Download ZIP"
- Click Deploy → triggers `window.confirm()` dialog (Approve/Deny)
- **Note:** Browser automation auto-accepts confirm() dialogs, so you can't visually verify the dialog in automated testing. Verify via code inspection instead.
- After approval, project status changes to "deploying" → "completed"

### 9. Build APK
- Click "Build APK" button (top-right, green)
- Verify chat message is sent to agent requesting Android project generation

### 10. Download ZIP
- Click "Download ZIP" button
- Verify ZIP file downloads with project files

## Known Issues / Gotchas

- **Groq free tier TPM limit (8000 tokens/min):** Keep prompts short. The system automatically retries with backoff but pipelines take longer.
- **max_tokens parameter:** Groq SDK uses `max_tokens`, NOT `max_completion_tokens`. If you see "unexpected keyword argument" errors, check groq_client.py.
- **Next.js params:** Use `useParams()` hook, NOT `use(params)` with Promise params - the latter crashes in production builds.
- **WebSocket messages:** Messages may appear on refresh rather than live-streaming depending on timing. The WebSocket connection is functional but the initial messages during pipeline creation come before the connection is established.
- **Celery hot reload:** Celery does NOT hot-reload. After changing agent code, you must restart the Celery worker: `pkill -f "celery -A astradev"; cd backend && celery -A astradev.celery_app worker --loglevel=info --concurrency=2 &`
- **localStorage stale tokens:** If you see "Token expired" errors on signup/login pages, clear localStorage first: `localStorage.clear()` in browser console.
- **Admin error message:** The admin login form may not display visible error text for wrong credentials. It correctly rejects (stays on login page) but lacks user feedback.
- **Browser automation + confirm():** `window.confirm()` dialogs are auto-accepted by browser automation tools. To verify deploy confirmation exists, inspect the code at `frontend/app/projects/[id]/page.tsx` line 136.
- **Input field replacement:** When using browser automation to clear input fields, `Ctrl+A` followed by typing may append instead of replace. Use native value setter via console for reliable replacement.

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
