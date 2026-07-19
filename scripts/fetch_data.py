"""
fetch_data.py
Mengambil:
1. Data rilis ekonomi US terbaru dari FRED (Federal Reserve Economic Data)
2. News global & AI terbaru dari RSS feed publik (gratis, tanpa API key)

Output: raw_data.json (dibaca oleh generate_report.py)
"""

import os
import json
import datetime
import urllib.request
import xml.etree.ElementTree as ET

FRED_API_KEY = os.environ.get("FRED_API_KEY", "")
FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"

# Series ID FRED yang paling market-moving.
# Ini bukan random pick — ini indikator yang benar-benar dipantau trader & Fed.
ECONOMIC_SERIES = {
    "CPIAUCSL": "CPI (Inflasi Konsumen)",
    "PAYEMS": "Nonfarm Payrolls (Jobs Report)",
    "UNRATE": "Tingkat Pengangguran",
    "FEDFUNDS": "Fed Funds Rate",
    "PCEPI": "PCE Price Index (Indikator favorit Fed)",
    "RSAFS": "Retail Sales",
    "DGS10": "US 10-Year Treasury Yield",
    "GDP": "GDP (Kuartalan)",
}


def fetch_fred_series(series_id: str) -> dict:
    """Ambil 2 observasi terakhir dari satu series FRED untuk hitung perubahan."""
    if not FRED_API_KEY:
        return {"error": "FRED_API_KEY belum diset"}

    url = (
        f"{FRED_BASE}?series_id={series_id}&api_key={FRED_API_KEY}"
        f"&file_type=json&sort_order=desc&limit=2"
    )
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
        obs = data.get("observations", [])
        if len(obs) < 2:
            return {"error": "data tidak cukup"}
        latest, previous = obs[0], obs[1]
        latest_val = float(latest["value"]) if latest["value"] != "." else None
        prev_val = float(previous["value"]) if previous["value"] != "." else None
        change = None
        if latest_val is not None and prev_val is not None and prev_val != 0:
            change = round(((latest_val - prev_val) / abs(prev_val)) * 100, 2)
        return {
            "date": latest["date"],
            "value": latest_val,
            "previous_value": prev_val,
            "change_pct": change,
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_economic_data() -> dict:
    result = {}
    for series_id, label in ECONOMIC_SERIES.items():
        result[series_id] = {"label": label, **fetch_fred_series(series_id)}
    return result


# RSS feed gratis, tidak butuh API key. Ini sumber legit (bukan blog SEO).
NEWS_FEEDS = {
    "global_economy": "https://feeds.reuters.com/reuters/businessNews",
    "ai_tech": "https://www.technologyreview.com/feed/",
    "markets": "https://feeds.marketwatch.com/marketwatch/topstories/",
    "crypto": "https://www.coindesk.com/arc/outboundfeeds/rss/",
}


def fetch_rss(url: str, limit: int = 8) -> list:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as resp:
            raw = resp.read()
        root = ET.fromstring(raw)
        items = []
        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title", default="").strip()
            link = item.findtext("link", default="").strip()
            pub = item.findtext("pubDate", default="").strip()
            if title:
                items.append({"title": title, "link": link, "published": pub})
        return items
    except Exception as e:
        return [{"error": str(e)}]


def fetch_all_news() -> dict:
    return {category: fetch_rss(url) for category, url in NEWS_FEEDS.items()}


def main():
    payload = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "economic_data": fetch_economic_data(),
        "news": fetch_all_news(),
    }
    out_path = os.path.join(os.path.dirname(__file__), "..", "raw_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved raw_data.json with {len(payload['economic_data'])} economic series "
          f"and {sum(len(v) for v in payload['news'].values())} news items")


if __name__ == "__main__":
    main()
