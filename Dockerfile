# ── Stage 1: Build React frontend ──────────────────────────────────────────
FROM node:20-slim AS frontend-build

WORKDIR /app/frontend
COPY frontend/package.json ./
RUN npm install
COPY frontend/ ./
RUN npm run build

# ── Stage 2: Python backend + static frontend ───────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Install git (needed to pip-install pandas-ta from GitHub) then Python deps
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend source
COPY backend/ ./backend/

# Copy built React app to the path main.py expects
COPY --from=frontend-build /app/frontend/dist ./frontend/dist/

ENV APP_ENV=prod \
    PYTHONUNBUFFERED=1

WORKDIR /app/backend
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
