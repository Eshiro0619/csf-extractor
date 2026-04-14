import os
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from csf_extractor_v2 import extract_csf_with_llm, compare_yearly

load_dotenv()

app = FastAPI(title="CSF Extractor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/extract")
async def extract(
    file: UploadFile = File(...),
    year: int = Form(...),
    company: str = Form(...),
):
    pdf_bytes = await file.read()
    result = extract_csf_with_llm(pdf_bytes, year=year, company=company)
    return result


@app.get("/results/{year}")
def get_results(year: int):
    result = _load_result(year)
    if result is None:
        raise HTTPException(status_code=404, detail=f"No results found for year {year}")
    return result


@app.get("/diff/{year_from}/{year_to}")
def get_diff(year_from: int, year_to: int):
    result_from = _load_result(year_from)
    result_to = _load_result(year_to)
    if result_from is None:
        raise HTTPException(status_code=404, detail=f"No results found for year {year_from}")
    if result_to is None:
        raise HTTPException(status_code=404, detail=f"No results found for year {year_to}")
    diff = compare_yearly(result_from, result_to)
    return diff


@app.get("/health")
def health_check():
    return {"status": "ok"}


def _load_result(year: int):
    """Load saved CSF result for the given year from .csf_store/."""
    import json
    store_dir = os.path.join(os.path.dirname(__file__), ".csf_store")
    path = os.path.join(store_dir, f"{year}.json")
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
