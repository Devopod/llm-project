#!/bin/bash
# AstraDev Startup Script
set -e

echo "=== Starting AstraDev ==="

# Ensure Docker services are running
cd /home/ubuntu/repos/astradev
docker compose up -d

# Wait for PostgreSQL
echo "Waiting for PostgreSQL..."
until docker compose exec -T postgres pg_isready -U astradev 2>/dev/null; do
    sleep 1
done
echo "PostgreSQL ready!"

# Wait for Redis
echo "Waiting for Redis..."
until docker compose exec -T redis redis-cli ping 2>/dev/null | grep -q PONG; do
    sleep 1
done
echo "Redis ready!"

# Start Celery worker in background
cd /home/ubuntu/repos/astradev/backend
celery -A astradev.celery_app worker --loglevel=info --concurrency=2 &
CELERY_PID=$!
echo "Celery worker started (PID: $CELERY_PID)"

# Start Django backend with Daphne (ASGI for WebSocket support)
daphne -b 0.0.0.0 -p 8000 astradev.asgi:application &
BACKEND_PID=$!
echo "Django backend started on port 8000 (PID: $BACKEND_PID)"

# Start Next.js frontend
cd /home/ubuntu/repos/astradev/frontend
npx next start -p 3000 &
FRONTEND_PID=$!
echo "Next.js frontend started on port 3000 (PID: $FRONTEND_PID)"

echo ""
echo "=== AstraDev is running ==="
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo ""

# Wait for all
wait
