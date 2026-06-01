$ErrorActionPreference = "Stop"

if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
  throw "python is not available on PATH. Install Python 3.11+ first."
}

if (-not (Test-Path ".venv")) {
  Write-Host "Creating .venv..."
  python -m venv .venv
}

if (-not (Test-Path ".env")) {
  Write-Host "Creating .env from .env.example..."
  Copy-Item ".env.example" ".env"
}

Write-Host "Installing dependencies..."
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

Write-Host "Starting Hyperdress.AI at http://127.0.0.1:8000"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
