"use client";

import { useState } from "react";

const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

type ExtractResult = Record<string, unknown>;

export default function Home() {
  const [file, setFile] = useState<File | null>(null);
  const [year, setYear] = useState<string>(String(new Date().getFullYear()));
  const [company, setCompany] = useState<string>("");
  const [result, setResult] = useState<ExtractResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;

    setLoading(true);
    setError(null);
    setResult(null);

    const form = new FormData();
    form.append("file", file);
    form.append("year", year);
    form.append("company", company);

    try {
      const res = await fetch(`${BACKEND_URL}/extract`, {
        method: "POST",
        body: form,
      });
      if (!res.ok) {
        const text = await res.text();
        throw new Error(`${res.status} ${res.statusText}: ${text}`);
      }
      const data: ExtractResult = await res.json();
      setResult(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50 py-12 px-4">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-3xl font-bold text-gray-900 mb-2">CSF Extractor</h1>
        <p className="text-gray-500 mb-8">PDFをアップロードして CSF 項目を抽出します</p>

        <form
          onSubmit={handleSubmit}
          className="bg-white rounded-2xl shadow p-6 space-y-5"
        >
          {/* PDF ファイル */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              PDF ファイル <span className="text-red-500">*</span>
            </label>
            <input
              type="file"
              accept="application/pdf"
              required
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              className="block w-full text-sm text-gray-600 file:mr-4 file:py-2 file:px-4
                         file:rounded-lg file:border-0 file:text-sm file:font-medium
                         file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100"
            />
          </div>

          {/* 年度 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              年度 <span className="text-red-500">*</span>
            </label>
            <input
              type="number"
              required
              value={year}
              onChange={(e) => setYear(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          {/* 会社名 */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              会社名 <span className="text-red-500">*</span>
            </label>
            <input
              type="text"
              required
              value={company}
              onChange={(e) => setCompany(e.target.value)}
              placeholder="例: 株式会社サンプル"
              className="w-full rounded-lg border border-gray-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-lg bg-blue-600 py-2.5 text-sm font-semibold text-white
                       hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition"
          >
            {loading ? "抽出中..." : "CSF を抽出する"}
          </button>
        </form>

        {/* エラー表示 */}
        {error && (
          <div className="mt-6 rounded-xl bg-red-50 border border-red-200 p-4 text-sm text-red-700">
            <p className="font-semibold mb-1">エラー</p>
            <pre className="whitespace-pre-wrap break-all">{error}</pre>
          </div>
        )}

        {/* 結果表示 */}
        {result && (
          <div className="mt-6 bg-white rounded-2xl shadow p-6">
            <h2 className="text-lg font-semibold text-gray-800 mb-4">抽出結果</h2>

            <div className="grid grid-cols-2 gap-2 text-sm mb-4">
              <span className="text-gray-500">会社名</span>
              <span className="font-medium">{String(result.company ?? "—")}</span>
              <span className="text-gray-500">年度</span>
              <span className="font-medium">{String(result.year ?? "—")}</span>
            </div>

            {Array.isArray(result.items) && result.items.length > 0 ? (
              <ul className="divide-y divide-gray-100">
                {(result.items as Record<string, unknown>[]).map((item, i) => (
                  <li key={i} className="py-2 text-sm text-gray-700">
                    <pre className="whitespace-pre-wrap break-all">
                      {JSON.stringify(item, null, 2)}
                    </pre>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="rounded-lg bg-gray-50 p-4">
                <p className="text-xs text-gray-400 mb-2">RAW JSON</p>
                <pre className="text-xs text-gray-700 whitespace-pre-wrap break-all overflow-auto max-h-96">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
