"""
CSF Extractor v2
- PDF → CSF抽出 (Anthropic Claude)
- 同一企業の年度間比較 (compare_yearly)
- 異業種・異企業間の比較 (compare_companies)
"""
from __future__ import annotations

import argparse
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import anthropic
from dotenv import load_dotenv

load_dotenv()

STORE_DIR = Path(os.path.dirname(__file__)) / ".csf_store"

_anthropic_client: anthropic.Anthropic | None = None


def _client() -> anthropic.Anthropic:
    global _anthropic_client
    if _anthropic_client is None:
        _anthropic_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    return _anthropic_client


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class CompanyDiffResult:
    company_a: str
    company_b: str
    company_a_label: str
    company_b_label: str
    year: int
    common_themes: list[dict]
    company_a_unique: list[dict]
    company_b_unique: list[dict]
    strategic_insights: list[dict]


# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

def _store_path(company: str, year: int) -> Path:
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    return STORE_DIR / f"csf_{company}_{year}.json"


def save_yearly(data: dict, company: str, year: int) -> None:
    """企業・年度をキーにCSFデータをJSONで保存する。"""
    path = _store_path(company, year)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_yearly(company: str, year: int) -> dict | None:
    """企業・年度を指定してCSFデータを読み込む。存在しなければ None を返す。"""
    path = _store_path(company, year)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def load_all_companies(year: int) -> dict[str, dict]:
    """指定年度の全企業CSFをまとめて返す。 {company_key: data} の辞書。"""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    results: dict[str, dict] = {}
    for path in STORE_DIR.glob(f"csf_*_{year}.json"):
        # ファイル名: csf_{company}_{year}.json → stem: csf_{company}_{year}
        stem = path.stem
        prefix = "csf_"
        suffix = f"_{year}"
        if stem.startswith(prefix) and stem.endswith(suffix):
            company_key = stem[len(prefix) : -len(suffix)]
            results[company_key] = json.loads(path.read_text(encoding="utf-8"))
    return results


# ---------------------------------------------------------------------------
# CSF extraction
# ---------------------------------------------------------------------------

def extract_csf_with_llm(pdf_bytes: bytes, *, year: int, company: str) -> dict:
    """PDFバイト列からCSF項目をClaudeで抽出し、ファイル保存後に結果を返す。"""
    import base64

    system_prompt = (
        "あなたは企業のアニュアルレポートや有価証券報告書から"
        "CSF（重要成功要因）を抽出する専門家です。"
        "必ずJSON配列のみを出力してください。"
    )

    user_prompt = f"""以下の企業レポートから、CSF（Critical Success Factors）を抽出してください。

企業名: {company}
対象年度: {year}年

各CSFを以下のJSONスキーマで出力してください（配列形式）:
[
  {{
    "csf_label": "CSFの短い名称（20文字以内）",
    "category": "財務 / 顧客 / 業務プロセス / 学習・成長 のいずれか",
    "summary": "このCSFの内容説明（2〜3文）",
    "evidence": "レポート中の根拠となる記述（引用または要約）",
    "importance": "high / medium / low"
  }}
]

JSONのみ出力してください。説明文は不要です。"""

    pdf_b64 = base64.standard_b64encode(pdf_bytes).decode()

    response = _client().messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        temperature=0,
        system=system_prompt,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "document",
                        "source": {
                            "type": "base64",
                            "media_type": "application/pdf",
                            "data": pdf_b64,
                        },
                    },
                    {"type": "text", "text": user_prompt},
                ],
            }
        ],
    )

    items = _parse_json(response.content[0].text.strip())
    result = {"year": year, "company": company, "items": items}
    save_yearly(result, company=company.lower().replace(" ", "_"), year=year)
    return result


# ---------------------------------------------------------------------------
# Same-company yearly diff
# ---------------------------------------------------------------------------

def compare_yearly(result_from: dict, result_to: dict) -> dict:
    """同一企業の2年度間CSF差分を返す。"""
    items_from = {i["csf_label"]: i for i in result_from.get("items", [])}
    items_to = {i["csf_label"]: i for i in result_to.get("items", [])}

    return {
        "from_year": result_from.get("year"),
        "to_year": result_to.get("year"),
        "company": result_to.get("company"),
        "added": [i for k, i in items_to.items() if k not in items_from],
        "removed": [i for k, i in items_from.items() if k not in items_to],
        "kept": [i for k, i in items_to.items() if k in items_from],
    }


# ---------------------------------------------------------------------------
# Cross-company comparison
# ---------------------------------------------------------------------------

def compare_companies(
    company_a: str,
    company_b: str,
    year: int,
    company_a_label: str,
    company_b_label: str,
) -> CompanyDiffResult:
    """異業種・異企業間のCSFを比較分析し、CompanyDiffResult を返す。"""
    data_a = load_yearly(company_a, year)
    data_b = load_yearly(company_b, year)

    if data_a is None:
        raise FileNotFoundError(f"{company_a} の {year}年度データが見つかりません")
    if data_b is None:
        raise FileNotFoundError(f"{company_b} の {year}年度データが見つかりません")

    def fmt_items(data: dict) -> str:
        lines = []
        for i, item in enumerate(data.get("items", []), 1):
            label = item.get("csf_label", "")
            summary = item.get("summary", "")
            lines.append(f"{i}. {label}: {summary}")
        return "\n".join(lines) if lines else "（データなし）"

    system_prompt = (
        "あなたは企業戦略の比較アナリストです。\n"
        "2社のCSF（重要成功要因）リストを分析し、\n"
        "業界を超えた戦略的共通点・相違点を抽出します。\n"
        "必ずJSONオブジェクトのみを出力してください。"
    )

    user_prompt = f"""以下の2社のCSFを比較分析してください。

【{company_a_label}のCSF】
{fmt_items(data_a)}

【{company_b_label}のCSF】
{fmt_items(data_b)}

以下のJSONスキーマで出力してください:
{{
  "common_themes": [
    {{
      "theme_label": "共通テーマ名（20文字以内）",
      "theme_summary": "両社に共通する戦略的意味（1〜2文）",
      "company_a_csf": "対応するA社のcsf_label",
      "company_b_csf": "対応するB社のcsf_label",
      "similarity_reason": "なぜ同一テーマと判断したか（1文）"
    }}
  ],
  "company_a_unique": [
    {{
      "csf_label": "A社固有のCSFラベル",
      "uniqueness_reason": "B社にない理由・背景（1文）"
    }}
  ],
  "company_b_unique": [
    {{
      "csf_label": "B社固有のCSFラベル",
      "uniqueness_reason": "A社にない理由・背景（1文）"
    }}
  ],
  "strategic_insights": [
    {{
      "insight": "業界横断で見えてくる示唆（1〜2文）"
    }}
  ]
}}

JSONのみ出力してください。説明文は不要です。"""

    response = _client().messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        temperature=0,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    parsed = _parse_json(response.content[0].text.strip())

    result = CompanyDiffResult(
        company_a=company_a,
        company_b=company_b,
        company_a_label=company_a_label,
        company_b_label=company_b_label,
        year=year,
        common_themes=parsed.get("common_themes", []),
        company_a_unique=parsed.get("company_a_unique", []),
        company_b_unique=parsed.get("company_b_unique", []),
        strategic_insights=parsed.get("strategic_insights", []),
    )

    save_company_diff(result)
    return result


# ---------------------------------------------------------------------------
# Report / save
# ---------------------------------------------------------------------------

def company_diff_to_report(result: CompanyDiffResult) -> str:
    """CompanyDiffResult を読みやすいテキストレポートに変換する。"""
    lines = [
        "═══ CSF 企業間比較レポート ═══",
        f"対象年度: {result.year}年",
        f"A社: {result.company_a_label} ({result.company_a})",
        f"B社: {result.company_b_label} ({result.company_b})",
        "",
        "─── 共通テーマ ───",
    ]
    for i, t in enumerate(result.common_themes, 1):
        lines += [
            f"{i}. {t.get('theme_label', '')}",
            f"   概要        : {t.get('theme_summary', '')}",
            f"   A社CSF      : {t.get('company_a_csf', '')}",
            f"   B社CSF      : {t.get('company_b_csf', '')}",
            f"   共通と判断した理由: {t.get('similarity_reason', '')}",
            "",
        ]

    lines += [f"─── {result.company_a_label} 固有CSF ───"]
    for item in result.company_a_unique:
        lines.append(f"  ・{item.get('csf_label', '')}: {item.get('uniqueness_reason', '')}")
    lines.append("")

    lines += [f"─── {result.company_b_label} 固有CSF ───"]
    for item in result.company_b_unique:
        lines.append(f"  ・{item.get('csf_label', '')}: {item.get('uniqueness_reason', '')}")
    lines.append("")

    lines += ["─── 業界横断の戦略的示唆 ───"]
    for i, insight in enumerate(result.strategic_insights, 1):
        lines.append(f"{i}. {insight.get('insight', '')}")

    return "\n".join(lines)


def save_company_diff(result: CompanyDiffResult) -> None:
    """比較結果を .csf_store に JSON + TXT の2形式で保存する。"""
    STORE_DIR.mkdir(parents=True, exist_ok=True)
    base = STORE_DIR / f"company_diff_{result.company_a}_{result.company_b}_{result.year}"
    base.with_suffix(".json").write_text(
        json.dumps(asdict(result), ensure_ascii=False, indent=2), encoding="utf-8"
    )
    base.with_suffix(".txt").write_text(
        company_diff_to_report(result), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _parse_json(text: str):
    """LLM応答からJSONを抽出する（markdownコードフェンス対応）。"""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())


def _save_dummy(company: str, label: str, year: int, items: list[dict]) -> None:
    data = {"year": year, "company": label, "items": items}
    save_yearly(data, company=company, year=year)
    print(f"✓ {label} ({company}) {year}年度 ダミーデータを保存しました")
    print(f"  → {_store_path(company, year)}")


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def _cmd_extract(args: argparse.Namespace) -> None:
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"エラー: {pdf_path} が見つかりません")
        return
    print(f"抽出中: {pdf_path} ({args.company}, {args.year}年度)")
    result = extract_csf_with_llm(pdf_path.read_bytes(), year=args.year, company=args.company)
    print(f"✓ {len(result['items'])} 件のCSFを抽出しました")
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _cmd_diff(args: argparse.Namespace) -> None:
    data_from = load_yearly(args.company, args.year_from)
    data_to = load_yearly(args.company, args.year_to)
    if data_from is None:
        print(f"エラー: {args.company} の {args.year_from}年度データが見つかりません")
        return
    if data_to is None:
        print(f"エラー: {args.company} の {args.year_to}年度データが見つかりません")
        return
    print(json.dumps(compare_yearly(data_from, data_to), ensure_ascii=False, indent=2))


def _cmd_compare(args: argparse.Namespace) -> None:
    print(f"比較中: {args.label_a} vs {args.label_b} ({args.year}年度)")
    try:
        result = compare_companies(
            company_a=args.company_a,
            company_b=args.company_b,
            year=args.year,
            company_a_label=args.label_a,
            company_b_label=args.label_b,
        )
    except FileNotFoundError as e:
        print(f"エラー: {e}")
        return
    print(company_diff_to_report(result))
    base = f"company_diff_{args.company_a}_{args.company_b}_{args.year}"
    print(f"\n✓ レポート保存先: .csf_store/{base}.(json|txt)")


def _cmd_dummy(args: argparse.Namespace) -> None:
    toyota_items = [
        {"csf_label": "グローバル生産効率",     "category": "業務プロセス", "summary": "世界各地の生産拠点における品質・コスト・納期の最適化。トヨタ生産方式を核とした継続的改善活動。",               "evidence": "グローバル生産台数1,000万台超を達成し、工場稼働率95%維持",            "importance": "high"},
        {"csf_label": "カーボンニュートラル対応", "category": "顧客",       "summary": "2050年カーボンニュートラル達成に向けたEV・FCV・HEVのマルチパスウェイ戦略。",                              "evidence": "BEV・FCEV・HEVのラインナップ拡充、2030年までにBEV350万台目標",    "importance": "high"},
        {"csf_label": "ソフトウェア開発力",      "category": "学習・成長", "summary": "車両OSやADASなどソフトウェア定義型車両（SDV）への転換を加速。",                                           "evidence": "アリーンOSの開発投資を大幅拡充、ソフト人材を5年で1万人採用",      "importance": "high"},
        {"csf_label": "サプライチェーン強靭化",  "category": "業務プロセス", "summary": "半導体不足などサプライチェーンリスクへの対応力強化と調達先の多様化。",                                     "evidence": "重要部品の内製化・複数調達先確保を推進、在庫水準を戦略的に積み上げ", "importance": "medium"},
        {"csf_label": "新興国市場開拓",          "category": "財務",       "summary": "インド・東南アジア等の成長市場でのシェア拡大と現地生産体制の強化。",                                        "evidence": "インド市場での販売台数前年比25%増、現地調達率70%を達成",          "importance": "medium"},
    ]
    toshiba_items = [
        {"csf_label": "エネルギーシステム革新",   "category": "業務プロセス", "summary": "再生可能エネルギーと蓄電池を組み合わせた次世代エネルギーソリューションの提供。",                          "evidence": "洋上風力・水素関連の受注残高が過去最高水準に到達",                  "importance": "high"},
        {"csf_label": "デジタルインフラ強化",     "category": "学習・成長", "summary": "社会インフラのデジタル化・DX推進による新規ビジネス創出とコスト削減。",                                    "evidence": "IoTプラットフォーム『Meister』の顧客数30%増、DX案件売上2倍",    "importance": "high"},
        {"csf_label": "カーボンニュートラル貢献", "category": "顧客",       "summary": "顧客企業の脱炭素化を支援するソリューション事業の拡大。",                                                  "evidence": "CO2排出量可視化サービスの導入企業200社突破、削減実績1億トン超",   "importance": "high"},
        {"csf_label": "サイバーセキュリティ",     "category": "業務プロセス", "summary": "インフラ・重要設備向けのセキュリティ対策技術の強化と事業拡大。",                                         "evidence": "セキュリティ関連売上高が前年比40%増、国内シェアトップ3入り",       "importance": "high"},
        {"csf_label": "コーポレートガバナンス改革", "category": "財務",     "summary": "株主価値向上と経営透明性確保のための組織改革の推進。",                                                      "evidence": "社外取締役比率を過半数に引き上げ完了、ROE目標10%を設定",           "importance": "medium"},
    ]

    company = args.company.lower()
    if company == "toyota":
        _save_dummy("toyota", "トヨタ自動車", args.year, toyota_items)
    elif company == "toshiba":
        _save_dummy("toshiba", "東芝", args.year, toshiba_items)
    else:
        print("エラー: ダミーデータは toyota / toshiba のみ対応しています")


def main() -> None:
    parser = argparse.ArgumentParser(description="CSF Extractor v2")
    sub = parser.add_subparsers(dest="command", required=True)

    # extract
    p = sub.add_parser("extract", help="PDFからCSFを抽出")
    p.add_argument("pdf", help="PDFファイルのパス")
    p.add_argument("--company", required=True, help="企業キー（例: toyota）")
    p.add_argument("--year", type=int, required=True, help="対象年度")
    p.set_defaults(func=_cmd_extract)

    # diff
    p = sub.add_parser("diff", help="同一企業の年度間CSF比較")
    p.add_argument("company", help="企業キー")
    p.add_argument("year_from", type=int)
    p.add_argument("year_to", type=int)
    p.set_defaults(func=_cmd_diff)

    # compare
    p = sub.add_parser("compare", help="異業種・異企業間のCSF比較")
    p.add_argument("company_a", help="企業Aキー（例: toyota）")
    p.add_argument("company_b", help="企業Bキー（例: toshiba）")
    p.add_argument("--year", type=int, required=True, help="対象年度")
    p.add_argument("--label-a", required=True, dest="label_a", help="企業Aの表示名")
    p.add_argument("--label-b", required=True, dest="label_b", help="企業Bの表示名")
    p.set_defaults(func=_cmd_compare)

    # dummy
    p = sub.add_parser("dummy", help="テスト用ダミーデータを作成")
    p.add_argument("company", choices=["toyota", "toshiba"])
    p.add_argument("--year", type=int, default=2024)
    p.set_defaults(func=_cmd_dummy)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
