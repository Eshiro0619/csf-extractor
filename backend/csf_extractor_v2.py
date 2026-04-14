# CSF Extractor v2
# TODO: 本実装に差し替えてください

def extract_csf_with_llm(pdf_bytes: bytes, *, year: int, company: str) -> dict:
    """PDFバイト列からCSF項目を抽出してdictで返す（スタブ）。"""
    return {
        "year": year,
        "company": company,
        "items": [],
        "note": "stub — not yet implemented",
    }


def compare_yearly(result_from: dict, result_to: dict) -> dict:
    """2年度のCSF結果を比較して差分を返す（スタブ）。"""
    return {
        "from": result_from.get("year"),
        "to": result_to.get("year"),
        "diff": [],
        "note": "stub — not yet implemented",
    }
