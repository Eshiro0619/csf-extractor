import json
import os
from contextlib import contextmanager

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from csf_extractor_v2 import compare_yearly, extract_csf_with_llm

load_dotenv()

UPLOAD_DIR = "/app/uploads"
DATABASE_URL = os.getenv("DATABASE_URL")

app = FastAPI(title="CSF Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    _init_db()


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _init_db():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS csf_results (
                    id SERIAL PRIMARY KEY,
                    year INT NOT NULL,
                    company TEXT,
                    pdf_filename TEXT,
                    items JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS csf_cache (
                    cache_key TEXT PRIMARY KEY,
                    data JSONB NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            """)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    year: int = Form(...),
    company: str = Form(...),
):
    pdf_bytes = await file.read()

    # PDFをローカルボリュームに保存
    save_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(save_path, "wb") as f:
        f.write(pdf_bytes)

    result = extract_csf_with_llm(pdf_bytes, year=year, company=company)

    # 結果をDBに保存
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO csf_results (year, company, pdf_filename, items)
                VALUES (%s, %s, %s, %s)
                """,
                (year, company, file.filename, json.dumps(result)),
            )

    return result


@app.get("/results/{year}")
def get_results(year: int):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT * FROM csf_results WHERE year = %s ORDER BY created_at DESC LIMIT 1",
                (year,),
            )
            row = cur.fetchone()

    if row is None:
        raise HTTPException(status_code=404, detail=f"No results found for year {year}")

    return dict(row)


@app.get("/diff/{year_from}/{year_to}")
def get_diff(year_from: int, year_to: int):
    result_from = _fetch_items(year_from)
    result_to = _fetch_items(year_to)

    if result_from is None:
        raise HTTPException(status_code=404, detail=f"No results found for year {year_from}")
    if result_to is None:
        raise HTTPException(status_code=404, detail=f"No results found for year {year_to}")

    diff = compare_yearly(result_from, result_to)
    return diff


@app.get("/health")
def health_check():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _fetch_items(year: int):
    """Return the items JSONB for the most recent result of the given year, or None."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT items FROM csf_results WHERE year = %s ORDER BY created_at DESC LIMIT 1",
                (year,),
            )
            row = cur.fetchone()
    return row[0] if row else None


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
