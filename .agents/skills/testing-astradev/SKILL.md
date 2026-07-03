---
name: testing-astradev
description: End-to-end testing guide for AstraDev platform. Use when verifying signup, project creation, multi-agent pipeline, file generation, APK build, ZIP download, deploy flow, validation pipeline, and self-healing code generation.
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

### 8. Deploy Flow (Auto-Deploy Prompt + Manual Deploy)

**Auto-Deploy Prompt (Primary Flow):**
- After project pipeline completes, the orchestrator emits a `deploy_prompt` message
- The activity feed renders inline "Approve & Deploy" (green) and "Skip Deployment" (gray) buttons
- Click "Approve & Deploy" → deployment starts automatically (no confirm dialog)
- Buttons are replaced with "Deployment initiated..." text
- After deployment, a green "Live: /projects/.../deployed/" pill appears in the header
- Navigate to the deployed URL to verify the web app loads and functions
- **State persistence:** On page refresh, the `deployTriggered` state is restored from message history by checking if any `deployment`-type messages exist *after* the `deploy_prompt` message. This prevents the Approve/Deny buttons from reappearing and avoids double-deployment.
- **Gotcha:** The deployer agent also emits `deployment`-type messages during the build phase (before the `deploy_prompt`). If the frontend checks for ANY deployment message, it will incorrectly show "Deployment initiated..." even before the user clicks Approve. The fix is to only check for deployment messages that come *after* the `deploy_prompt` in the message array.

**Manual Deploy Button (Fallback):**
- On project page, the purple "Deploy" button in the top bar still works as a fallback
- Click Deploy → triggers deployment via `projectsApi.deploy(id, 'approve')`

**Deployed App Verification:**
- Deployed apps are served via Django reverse proxy at `/projects/<id>/deployed/`
- Flask apps get `app.run()` patched to use a dynamic port assigned during deployment
- **URL Rewriting:** The deploy proxy rewrites absolute URLs in HTML responses (`action="/path"`, `href="/path"`, `src="/path"`, `fetch("/path")`) to use the proxy prefix. Without this, form submissions go to the Next.js frontend and 404.
- For Flask Calculator: enter numbers, select operation, click Calculate, verify correct result

**Frontend Build Caching:**
- After editing `frontend/app/projects/[id]/page.tsx`, you MUST rebuild (`npx next build`) and restart the Next.js server for changes to take effect.
- The browser may cache old JS chunks. After rebuilding, verify the server is serving the new chunk hash by checking `curl -s http://localhost:3000/projects/<id> | grep -o 'page-[a-f0-9]*\.js'`
- If the browser still uses old chunks, clear caches via console: `caches.keys().then(names => names.forEach(name => caches.delete(name))); window.location.reload(true);`

### 8b. Validation Pipeline Testing
The validation pipeline runs after all tasks complete. To verify it works:

**Shell-based validator tests:**
```python
# Test validators catch known-bad files
from astradev.agents.validators import validate_file, validate_workspace

# Should FAIL: Python syntax error
validate_file("def foo(\n", "bad.py")

# Should FAIL: JSON-wrapped README
validate_file('{"files": [{"path": "README.md"}]}', "README.md")

# Should FAIL: TODO placeholder
validate_file("def foo():\n    # TODO: implement\n    pass\n", "todo.py")

# Should FAIL: Missing HTML closing tags
validate_file("<html><body><h1>Hi</h1>", "bad.html")

# Should PASS: Valid Python
validate_file("from flask import Flask\napp = Flask(__name__)\n", "app.py")

# Workspace validation
report = validate_workspace("/tmp/astradev_workspaces/<project-id>/")
# Check report.passed (bool), report.failed_files (list), report.summary (str)
```

**Browser-based pipeline test:**
1. Create a new project via the UI
2. Watch the activity log for validation messages:
   - "Running validation pipeline..." 
   - "Validation: X/Y files passed"
   - If files fail: "Repairing <filename>: <error details>"
   - After repair: "Repaired <filename>"
   - "Post-repair validation: X/X files passed"
   - "Running code review..."
   - "Running security check..."
   - "Project completed — all validations passed!"
3. Click on files to verify they contain complete code (no TODO, no pass stubs, no truncation)
4. Verify README.md starts with `#`, not `{` or `[`

### 9. File Save (Edit → Save → Persist)
- Click any file in the sidebar → file content loads with line numbers
- Click "Edit" button → textarea appears with Save/Cancel buttons
- Modify content → click Save
- **Pass:** Green "Saved!" text appears next to filename
- **Fail:** Red "Save failed" or no response
- Switch to another file, then switch back → verify edit persisted
- **Known issue:** Next.js trailing slash can break file save if `file_path.strip('/')` is missing in views.py
- Works for both sample project files and agent-generated files

### 10. Build APK
- Click "Build APK" button (top-right, green)
- Verify chat message is sent to agent requesting Android project generation

### 11. Download ZIP
- Click "Download ZIP" button
- Verify ZIP file downloads with project files

## Known Issues / Gotchas

- **Groq free tier TPM limit (8000 tokens/min):** Keep prompts short. The system automatically retries with backoff but pipelines take longer. The daily token limit (200K TPD) can be hit; the system auto-disables exhausted keys and rotates to the next.
- **max_tokens parameter:** Groq SDK uses `max_tokens`, NOT `max_completion_tokens`. If you see "unexpected keyword argument" errors, check groq_client.py. Current max_tokens is 8192.
- **Next.js params:** Use `useParams()` hook, NOT `use(params)` with Promise params - the latter crashes in production builds.
- **Deploy proxy URL rewriting:** The `_rewrite_urls()` function in `deploy_proxy.py` rewrites absolute URLs in HTML responses. If a deployed app's forms/links still 404, check whether the HTML uses absolute paths that aren't caught by the regex (e.g., `window.location = "/path"` or dynamically constructed URLs).
- **WebSocket messages:** Messages may appear on refresh rather than live-streaming depending on timing. The WebSocket connection is functional but the initial messages during pipeline creation come before the connection is established.
- **Celery hot reload:** Celery does NOT hot-reload. After changing agent code, you must restart the Celery worker: `pkill -f "celery -A astradev"; cd backend && celery -A astradev.celery_app worker --loglevel=info --concurrency=2 &`
- **localStorage stale tokens:** If you see "Token expired" errors on signup/login pages, clear localStorage first: `localStorage.clear()` in browser console.
- **Admin error message:** The admin login form may not display visible error text for wrong credentials. It correctly rejects (stays on login page) but lacks user feedback.
- **Browser automation + confirm():** `window.confirm()` dialogs are auto-accepted by browser automation tools. To verify deploy confirmation exists, inspect the code at `frontend/app/projects/[id]/page.tsx` line 136.
- **Input field replacement:** When using browser automation to clear input fields, `Ctrl+A` followed by typing may append instead of replace. Use native value setter via console for reliable replacement.
- **ngrok free-tier login issue:** Browser-based login/signup may fail with "User not found" on first visit through ngrok. The ngrok interstitial page might interfere with fetch API calls. Workaround: clear localStorage and use console-based fetch to set tokens, or dismiss the ngrok warning first.
- **File save trailing slash:** Next.js appends a trailing slash to route params. The backend must strip it with `file_path.strip('/')` in `project_file_content()` and `project_file_edit()` views. Without this, file save returns 500.
- **Deployment port patching:** Flask apps have hardcoded `app.run(port=5000)`. The deploy task patches this with regex to use the dynamically assigned port. If the regex doesn't match, the app starts on port 5000 but the proxy expects the dynamic port — resulting in 503.
- **Agent file editing (related_name):** The Project model uses `related_name='messages'` on the Message FK. Code must use `project.messages` not `project.message_set`. The auto-fix loop in orchestrator.py depends on this.

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
