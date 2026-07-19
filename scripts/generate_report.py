"""
generate_report.py
Mengirim raw_data.json ke Claude API, minta dianalisis dengan framing korelasi
lintas aset (equities, crypto, real estate, commodities) sesuai gaya "Kael".

Output: report.json (dibaca oleh dashboard/index.html)
"""

import os
import json
import datetime
import urllib.request

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
API_URL = "https://api.anthropic.com/v1/messages"

SYSTEM_PROMPT = """Kamu adalah "Kael" — analis makro yang tajam, kritis, dan tidak basa-basi.
Tugasmu: menganalisis data ekonomi US dan berita global/AI terbaru, lalu menjelaskan
KORELASINYA ke kelas aset lain (equities, crypto, real estate, commodities).

Aturan ketat:
- Jangan generic ("ini bisa berdampak ke market" itu noise, TIDAK BOLEH ditulis).
- Setiap klaim korelasi harus punya mekanisme kausal yang jelas (contoh: "CPI naik →
  ekspektasi Fed hawkish naik → yield obligasi naik → tekanan ke growth stock &
  crypto karena discount rate naik").
- Kalau data tidak cukup jelas / ambigu, katakan itu secara eksplisit, jangan
  dipaksakan jadi kesimpulan pasti.
- Highlight risiko institutional/manipulation angle kalau relevan (terutama untuk
  data yang berkaitan dengan crypto/ETF flows).
- Output HARUS format JSON valid, tanpa markdown fence, dengan struktur:
{
  "headline": "satu kalimat ringkasan paling penting hari ini",
  "economic_summary": "ringkasan data ekonomi yang baru rilis, angka konkret",
  "correlation_analysis": [
    {"trigger": "...", "mechanism": "...", "affected_assets": ["..."], "confidence": "high/medium/low"}
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
        "max_tokens": 2000,
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
            data = json.loads(resp.read().decode())
        text = "".join(
            block.get("text", "") for block in data.get("content", [])
            if block.get("type") == "text"
        )
        cleaned = text.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(cleaned)
    except Exception as e:
        return {"error": str(e)}


def main():
    base_dir = os.path.join(os.path.dirname(__file__), "..")
    raw_path = os.path.join(base_dir, "raw_data.json")

    with open(raw_path, "r", encoding="utf-8") as f:
        raw_data = json.load(f)

    analysis = call_claude(raw_data)

    report = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "raw_economic_data": raw_data.get("economic_data", {}),
        "raw_news": raw_data.get("news", {}),
        "analysis": analysis,
    }

    out_path = os.path.join(base_dir, "dashboard", "report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("Report generated:", "OK" if "error" not in analysis else analysis["error"])


if __name__ == "__main__":
    main()
