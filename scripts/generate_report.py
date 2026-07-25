"""
generate_report.py
Mengirim raw_data.json ke Claude API, minta dianalisis dengan framing korelasi
lintas aset (equities, crypto, real estate, commodities) sesuai gaya "Kael".

Output: report.json (dibaca oleh docs/index.html)
"""

import os
import re
import json
import datetime
import statistics
import urllib.request
import urllib.error

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """Kamu adalah "Kael" — analis makro yang tajam, kritis, dan tidak basa-basi.
Tugasmu: menganalisis data ekonomi US, berita global/AI, dan data saham/ETF/bond,
lalu menjelaskan KORELASINYA lintas aset (saham individu, ETF, bond, crypto, commodities).

Aturan ketat:
- Jangan generic ("ini bisa berdampak ke market" itu noise, TIDAK BOLEH ditulis).
- Setiap klaim korelasi harus punya mekanisme kausal yang jelas.
- PENTING soal data saham: angka indikator (PER, ROE, valuation_flag, dividend_yield,
  dll) SUDAH dihitung oleh sistem Python dan dikirim ke kamu sebagai fakta. JANGAN
  menghitung ulang atau menebak angka baru — kamu HANYA boleh menjelaskan ARTI dan
  IMPLIKASI dari angka yang sudah ada, bukan menghasilkan angka baru.
- valuation_flag yang dikirim itu RELATIF terhadap peer group, bukan fair value
  absolut — jangan klaim "undervalued" sebagai rekomendasi beli.
- Untuk stock_commentary: fokus HANYA ke 4-6 ticker yang paling relevan dengan
  cerita makro/news hari ini (jangan bahas semua saham, pilih yang paling terhubung
  ke correlation_analysis kamu).
- Kalau data tidak cukup jelas / ambigu, katakan itu secara eksplisit.
- Tulis ringkas dan padat. Setiap field summary maksimal 3-4 kalimat.
  correlation_analysis maksimal 4 item paling penting saja.
- Output HARUS format JSON valid, tanpa markdown fence, dengan struktur:
{
  "headline": "satu kalimat ringkasan paling penting hari ini",
  "economic_summary": "ringkasan data ekonomi yang baru rilis, angka konkret",
  "correlation_analysis": [
    {"trigger": "...", "mechanism": "...", "affected_assets": ["..."], "confidence": "high/medium/low"}
  ],
  "stock_commentary": [
    {"ticker": "NVDA", "note": "kenapa ticker ini relevan hari ini, dikaitkan ke correlation_analysis di atas"}
  ],
  "ai_tech_summary": "ringkasan berita AI/tech penting",
  "global_summary": "ringkasan berita ekonomi/geopolitik global",
  "risk_flags": ["hal yang perlu diwaspadai minggu ini"]
}
"""


def call_claude(raw_data: dict) -> dict:
    if not ANTHROPIC_API_KEY:
        return {"error": "ANTHROPIC_API_KEY belum diset"}

    user_content = (
        "Analisis data berikut dan hasilkan report sesuai format JSON yang ditentukan:\n\n"
        + json.dumps(raw_data, ensure_ascii=False)
    )

    body = json.dumps({
        "model": "claude-sonnet-5",
        "max_tokens": 6000,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_content}],
    }).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw_body = resp.read().decode()
    except urllib.error.HTTPError as e:
        error_body = e.read().decode(errors="replace")
        return {"error": f"HTTP {e.code}: {error_body[:500]}"}
    except Exception as e:
        return {"error": f"Request gagal: {e}"}

    try:
        data = json.loads(raw_body)
    except Exception:
        return {"error": f"Response bukan JSON valid. Raw response: {raw_body[:500]}"}

    if data.get("type") == "error":
        return {"error": f"API error: {data.get('error', {}).get('message', 'unknown')}"}

    text = "".join(
        block.get("text", "") for block in data.get("content", [])
        if block.get("type") == "text"
    )

    if not text.strip():
        return {"error": f"Claude tidak mengembalikan teks. Full response: {json.dumps(data)[:500]}"}

    # Cari blok JSON pertama ({ ... }) di dalam teks, jaga-jaga kalau ada
    # penjelasan tambahan di luar instruksi meskipun sudah diminta JSON murni.
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {"error": f"Tidak ditemukan JSON dalam respons. Raw text: {text[:500]}"}

    try:
        return json.loads(match.group(0))
    except Exception as e:
        return {"error": f"Gagal parse JSON: {e}. Raw text: {text[:500]}"}


def _zscore_map(values: dict) -> dict:
    """values: {ticker: number}. Return {ticker: zscore}. Butuh minimal 3 data poin valid."""
    nums = [v for v in values.values() if isinstance(v, (int, float))]
    if len(nums) < 3:
        return {t: None for t in values}
    mean = statistics.mean(nums)
    stdev = statistics.pstdev(nums) or 1
    return {
        t: (round((v - mean) / stdev, 3) if isinstance(v, (int, float)) else None)
        for t, v in values.items()
    }


def compute_equity_ranking(equities: dict) -> list:
    """
    Ranking saham berdasarkan skor komposit dari 9 indikator (equal-weighted z-score).
    METODOLOGI (penting buat transparansi, bukan black box):
    - Indikator "semakin tinggi semakin baik": ROE, ROA, NPM, revenue_growth,
      earnings_growth, dividend_yield  -> pakai z-score apa adanya
    - Indikator "semakin rendah semakin baik" (murah/sehat secara relatif):
      PER, PBV, DER -> z-score DIBALIK (dikali -1)
    - FCF TIDAK dimasukkan ke skor komposit karena nilai dolarnya nggak
      sebanding antar perusahaan beda ukuran (FCF Amazon vs Palantir beda
      skala drastis) -- FCF tetap ditampilkan sebagai angka mentah di card,
      hanya tidak ikut dihitung ke ranking.
    - Skor akhir = rata-rata dari semua z-score yang tersedia (skip yang None).
    Ini BUKAN rekomendasi beli/jual. Bobot equal-weight ini pilihan desain,
    bukan kebenaran objektif -- analis lain bisa kasih bobot beda dan hasil
    ranking bisa berubah.
    """
    valid = {t: v for t, v in equities.items() if "error" not in v}
    if not valid:
        return []

    higher_better = ["roe", "roa", "npm", "revenue_growth", "earnings_growth", "dividend_yield"]
    lower_better = ["per", "pbv", "der"]

    z_scores = {}
    for field in higher_better + lower_better:
        raw = {t: v.get(field) for t, v in valid.items()}
        z = _zscore_map(raw)
        if field in lower_better:
            z = {t: (-zv if zv is not None else None) for t, zv in z.items()}
        z_scores[field] = z

    ranking = []
    for t in valid:
        component_scores = [z_scores[f][t] for f in higher_better + lower_better if z_scores[f][t] is not None]
        composite = round(statistics.mean(component_scores), 3) if component_scores else None
        ranking.append({
            "ticker": t,
            "name": valid[t].get("name", t),
            "composite_score": composite,
            "components_used": len(component_scores),
        })

    ranking = [r for r in ranking if r["composite_score"] is not None]
    ranking.sort(key=lambda r: r["composite_score"], reverse=True)
    return ranking


def compute_fund_ranking(funds: dict) -> list:
    """
    Ranking ETF/fund berdasarkan dividend_yield (tinggi=baik) dan expense_ratio
    (rendah=baik). ytd_return dimasukkan kalau datanya tersedia (yfinance sering
    tidak punya field ini untuk ETF, jadi kalau kosong otomatis di-skip, bukan error).
    """
    valid = {t: v for t, v in funds.items() if "error" not in v}
    if not valid:
        return []

    div_z = _zscore_map({t: v.get("dividend_yield") for t, v in valid.items()})
    expense_raw = {t: v.get("expense_ratio") for t, v in valid.items()}
    expense_z = _zscore_map(expense_raw)
    expense_z = {t: (-zv if zv is not None else None) for t, zv in expense_z.items()}
    return_z = _zscore_map({t: v.get("ytd_return") for t, v in valid.items()})

    ranking = []
    for t in valid:
        parts = [z[t] for z in (div_z, expense_z, return_z) if z[t] is not None]
        composite = round(statistics.mean(parts), 3) if parts else None
        ranking.append({
            "ticker": t,
            "name": valid[t].get("name", t),
            "composite_score": composite,
            "components_used": len(parts),
        })

    ranking = [r for r in ranking if r["composite_score"] is not None]
    ranking.sort(key=lambda r: r["composite_score"], reverse=True)
    return ranking


def compute_rankings(stocks: dict) -> dict:
    """
    Hitung ranking dividend yield dan valuation extremes secara DETERMINISTIK
    di Python — bukan diminta ke Claude, supaya angkanya akurat, bukan tebakan LLM.
    """
    all_items = []
    for group_name, group in stocks.items():
        for ticker, data in group.items():
            if "error" in data:
                continue
            all_items.append({"ticker": ticker, "group": group_name, **data})

    dividend_ranked = sorted(
        [i for i in all_items if isinstance(i.get("dividend_yield"), (int, float))],
        key=lambda x: x["dividend_yield"], reverse=True,
    )
    dividend_leaders = [
        {"ticker": i["ticker"], "name": i.get("name", i["ticker"]),
         "dividend_yield": i["dividend_yield"], "group": i["group"]}
        for i in dividend_ranked[:5]
    ]

    equities = [i for i in all_items if i["group"] in ("big_tech", "financials")]
    undervalued = [i for i in equities if i.get("valuation_flag") == "undervalued relatif ke peer group"]
    overvalued = [i for i in equities if i.get("valuation_flag") == "overvalued relatif ke peer group"]

    return {
        "dividend_leaders": dividend_leaders,
        "most_undervalued": [{"ticker": i["ticker"], "name": i.get("name"), "per": i.get("per")} for i in undervalued],
        "most_overvalued": [{"ticker": i["ticker"], "name": i.get("name"), "per": i.get("per")} for i in overvalued],
        "equity_ranking": compute_equity_ranking({**stocks.get("big_tech", {}), **stocks.get("financials", {})}),
        "fund_ranking": compute_fund_ranking(stocks.get("etf", {})),
    }


def main():
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    raw_path = os.path.join(base_dir, "raw_data.json")

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    analysis = call_claude(raw_data)
    rankings = compute_rankings(raw_data.get("stocks", {}))

    report = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "raw_economic_data": raw_data.get("economic_data", {}),
        "raw_news": raw_data.get("news", {}),
        "raw_stocks": raw_data.get("stocks", {}),
        "rankings": rankings,
        "analysis": analysis,
    }

    out_path = os.path.join(base_dir, "docs", "report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("Report generated:", "OK" if "error" not in analysis else analysis["error"])


if __name__ == "__main__":
    main()
