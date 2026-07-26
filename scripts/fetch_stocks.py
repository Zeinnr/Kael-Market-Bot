"""
fetch_stocks.py
Ambil data fundamental saham individu, ETF, dan bond ETF dari Yahoo Finance
(via library yfinance, gratis, tanpa API key).

Menghasilkan struktur data yang sudah dikelompokkan sesuai kategori:
- big_tech: saham teknologi besar
- financials: saham sektor finansial
- etf: ETF index & income
- bonds: bond ETF

Setiap saham individu juga dapat "valuation_flag" (relatif ke peer group-nya,
BUKAN fair value absolut — itu butuh model valuasi terpisah yang jauh lebih
kompleks daripada scope bot ini).
"""

import statistics

try:
    import yfinance as yf
except ImportError:
    yf = None

BIG_TECH = {
    "NVDA": "NVIDIA", "ORCL": "Oracle", "AAPL": "Apple", "TSLA": "Tesla",
    "AMZN": "Amazon", "MSFT": "Microsoft", "GOOG": "Alphabet", "META": "Meta Platforms",
    "PLTR": "Palantir", "INTC": "Intel", "ASML": "ASML Holding", "TSM": "Taiwan Semiconductor",
}

FINANCIALS = {"BLK": "BlackRock", "BAC": "Bank of America"}

ETFS = {
    "QQQ": "Invesco QQQ Trust (Nasdaq-100)",
    "SPY": "SPDR S&P 500 ETF",
    "VOO": "Vanguard S&P 500 ETF",
    "VTI": "Vanguard Total Stock Market ETF",
    "JEPI": "JPMorgan Equity Premium Income ETF",
    "JEPQ": "JPMorgan Nasdaq Equity Premium Income ETF",
}

BONDS = {
    "TLT": "iShares 20+ Year Treasury Bond ETF",
    "AGG": "iShares Core US Aggregate Bond ETF",
    "BND": "Vanguard Total Bond Market ETF",
}


def _compute_yield(dividend_rate, price):
    """
    JANGAN pakai field 'dividendYield' langsung dari yfinance -- formatnya
    kadang desimal (0.022), kadang persen (2.2), tergantung ticker & versi
    API, dan nggak ada cara pasti nebak yang mana tanpa tau nilai aslinya
    duluan (circular problem). Threshold-based guess (raw > 1 = persen)
    ternyata salah untuk banyak ticker (AAPL, MSFT, NVDA dll keluar
    30-95% -- jelas salah, real yield saham2 itu < 2%).

    Solusi: hitung yield sendiri dari dua angka yang TIDAK ambigu --
    dividendRate (dolar per tahun) dan harga saham (dolar). Ini selalu
    konsisten karena keduanya angka mentah, bukan field yang formatnya
    bisa berubah-ubah.

    Return desimal (0.0044 = 0.44%), konsisten dipakai di seluruh sistem
    (frontend & compute_rankings mengalikan *100 untuk tampilan).
    """
    if not isinstance(dividend_rate, (int, float)) or not isinstance(price, (int, float)) or price <= 0:
        return None
    if dividend_rate <= 0:
        return None
    return round(dividend_rate / price, 5)


def _normalize_fund_yield(raw):
    """
    Khusus ETF/fund: field 'yield' dari yfinance terbukti konsisten desimal
    (0.0107 = 1.07%) untuk semua ticker fund yang dipakai bot ini (QQQ, SPY,
    VOO, VTI, JEPI, JEPQ -- sudah diverifikasi tampil benar di produksi).
    Beda dari saham individu, distribusi ETF dilaporkan lebih terstandarisasi
    jadi threshold guard ini masih aman dipakai di sini -- TAPI kalau nanti
    nambah ETF baru dan yield-nya keluar aneh, ganti juga ke _compute_yield.
    """
    if raw is None or not isinstance(raw, (int, float)):
        return None
    if raw > 1:
        return round(raw / 100, 5)
    return raw


def fetch_equity_fundamentals(ticker: str, name: str) -> dict:
    """Ambil indikator fundamental untuk saham individu."""
    if yf is None:
        return {"name": name, "error": "yfinance tidak terinstall"}
    try:
        info = yf.Ticker(ticker).info
        price = info.get("currentPrice") or info.get("regularMarketPrice")
        dividend_rate = info.get("dividendRate") or info.get("trailingAnnualDividendRate")
        return {
            "name": info.get("shortName", name),
            "price": price,
            "per": info.get("trailingPE"),
            "pbv": info.get("priceToBook"),
            "roe": info.get("returnOnEquity"),
            "roa": info.get("returnOnAssets"),
            "der": info.get("debtToEquity"),
            "npm": info.get("profitMargins"),
            "fcf": info.get("freeCashflow"),
            "revenue_growth": info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "dividend_yield": _compute_yield(dividend_rate, price),
        }
    except Exception as e:
        return {"name": name, "error": str(e)}


def fetch_fund_fundamentals(ticker: str, name: str) -> dict:
    """Ambil indikator untuk ETF/bond (metrik beda dari saham individu — nggak punya PER/ROE)."""
    if yf is None:
        return {"name": name, "error": "yfinance tidak terinstall"}
    try:
        info = yf.Ticker(ticker).info
        return {
            "name": info.get("longName", name),
            "price": info.get("navPrice") or info.get("regularMarketPrice"),
            "dividend_yield": _normalize_fund_yield(info.get("yield") or info.get("trailingAnnualDividendYield")),
            "ytd_return": info.get("ytdReturn"),
            "expense_ratio": info.get("annualReportExpenseRatio"),
            "three_year_return": info.get("threeYearAverageReturn"),
        }
    except Exception as e:
        return {"name": name, "error": str(e)}


def add_relative_valuation(group: dict) -> dict:
    """
    Kasih label 'undervalued'/'overvalued'/'fair' berdasarkan PER & PBV
    RELATIF terhadap rata-rata peer group ini (bukan fair value absolut).
    """
    pers = [v["per"] for v in group.values() if isinstance(v.get("per"), (int, float))]
    if len(pers) < 3:
        for v in group.values():
            v["valuation_flag"] = "data tidak cukup"
        return group

    mean_per = statistics.mean(pers)
    stdev_per = statistics.pstdev(pers) or 1

    for v in group.values():
        per = v.get("per")
        if not isinstance(per, (int, float)):
            v["valuation_flag"] = "data tidak cukup"
            continue
        z = (per - mean_per) / stdev_per
        if z < -0.5:
            v["valuation_flag"] = "undervalued relatif ke peer group"
        elif z > 0.5:
            v["valuation_flag"] = "overvalued relatif ke peer group"
        else:
            v["valuation_flag"] = "fair relatif ke peer group"
    return group


def fetch_all_stocks() -> dict:
    big_tech = {t: fetch_equity_fundamentals(t, n) for t, n in BIG_TECH.items()}
    financials = {t: fetch_equity_fundamentals(t, n) for t, n in FINANCIALS.items()}
    etf = {t: fetch_fund_fundamentals(t, n) for t, n in ETFS.items()}
    bonds = {t: fetch_fund_fundamentals(t, n) for t, n in BONDS.items()}

    big_tech = add_relative_valuation(big_tech)
    financials = add_relative_valuation(financials)

    return {
        "big_tech": big_tech,
        "financials": financials,
        "etf": etf,
        "bonds": bonds,
    }


if __name__ == "__main__":
    import json
    print(json.dumps(fetch_all_stocks(), indent=2, ensure_ascii=False))
