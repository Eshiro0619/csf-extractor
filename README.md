# csf-extractor

A monorepo for the CSF Extractor application.

## Structure

```
csf-extractor/
├── backend/       # FastAPI application
└── frontend/      # Next.js application (coming soon)
```

## Backend

FastAPI-based backend for CSF extraction.

### Setup

```bash
cd backend
cp .env.example .env
pip install -r requirements.txt
uvicorn main:app --reload
```
