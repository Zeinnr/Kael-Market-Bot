# Kael Market & AI Signal Bot

Sistem otomatis yang tiap hari (2x sehari) fetch data ekonomi US + news AI/global,
generate analisis korelasi via Claude, dan tampilkan di dashboard web. Semua gratis
(GitHub Actions + GitHub Pages), kecuali biaya Claude API (kecil, ~$0.01-0.05 per run).

## Setup (sekali doang, ±15 menit)

### 1. Bikin repo GitHub
```
git init
git add .
git commit -m "Initial setup"
git remote add origin https://github.com/USERNAME/kael-market-bot.git
git push -u origin main
```

### 2. Ambil API keys (semua gratis untuk signup)

**FRED API key** (data ekonomi resmi):
- Daftar di https://fred.stlouisfed.org/docs/api/api_key.html
- Gratis, instan, tanpa kartu kredit.

**Anthropic API key** (buat generate analisis):
- https://console.anthropic.com → API Keys → Create Key
- Ini yang kena charge per token (lihat pricing di console).

### 3. Masukin API keys ke GitHub Secrets
Di repo GitHub kamu: **Settings → Secrets and variables → Actions → New repository secret**
- `FRED_API_KEY` = key dari FRED
- `ANTHROPIC_API_KEY` = key dari Anthropic

Jangan pernah taruh API key langsung di kode / commit ke repo. Selalu lewat Secrets.

### 4. Aktifkan GitHub Pages
**Settings → Pages → Source: Deploy from branch → branch: main, folder: /dashboard**

Dashboard kamu akan live di:
`https://USERNAME.github.io/kael-market-bot/`

### 5. Test manual dulu sebelum nunggu jadwal otomatis
**Actions tab → Daily Market & AI Report → Run workflow**

Cek log-nya. Kalau sukses, `dashboard/report.json` akan ke-update otomatis dan
dashboard bakal nampilin data baru dalam 1-2 menit.

## Cara kerja jadwal otomatis

Workflow jalan otomatis jam **06:00 dan 18:00 UTC** (13:00 & 01:00 WIB) — bisa
diubah di `.github/workflows/daily-report.yml`, baris `cron:`. Format cron:
`menit jam tanggal bulan hari`.

## File yang perlu kamu pahami

| File | Fungsi |
|---|---|
| `scripts/fetch_data.py` | Ambil data mentah dari FRED + RSS feed |
| `scripts/generate_report.py` | Kirim data mentah ke Claude, minta analisis korelasi |
| `.github/workflows/daily-report.yml` | Jadwal otomatis (cron) |
| `dashboard/index.html` | Dashboard yang kamu lihat di browser |
| `dashboard/report.json` | Hasil analisis terbaru (auto-generated, jangan edit manual) |

## Next steps kalau mau upgrade (jangan langsung ke sini — beresin dasar dulu)

1. **Tambah indikator ekonomi lain** — edit dict `ECONOMIC_SERIES` di `fetch_data.py`.
   Cari series ID di https://fred.stlouisfed.org (contoh: `MORTGAGE30US` buat suku
   bunga KPR, `WTISPLC` buat harga minyak).
2. **Notifikasi Telegram** — kalau nanti mau push notif tiap report baru, tinggal
   tambah step di workflow yang hit Telegram Bot API. Gampang nambahnya begitu
   struktur ini jalan stabil.
3. **Historical tracking** — simpan tiap report.json ke folder `history/` dengan
   nama tanggal, biar bisa lihat tren korelasi dari waktu ke waktu (ini yang bikin
   analisis kamu makin tajam dibanding kompetitor yang cuma kasih snapshot harian).
4. **Filter noise** — kalau RSS feed kebanyakan artikel nggak relevan, tambah
   keyword filter di `fetch_rss()` sebelum masuk ke Claude (hemat token juga).

## Kenapa arsitektur ini (bukan VPS/server biasa)

- **Zero cost bulanan** — GitHub Actions 2000 menit gratis/bulan udah lebih dari
  cukup buat 2x run/hari.
- **Zero maintenance server** — nggak ada server yang bisa down, nggak ada yang
  perlu di-restart.
- **Auditable** — tiap run ke-log di tab Actions, tiap perubahan data ke-track di
  git history. Kamu bisa lihat evolusi analisis dari waktu ke waktu.
- **Scalable tanpa kamu terlibat** — sesuai non-negotiable kamu: sistem jalan
  meski kamu nggak buka laptop.

Trade-off: latency update cuma 2x sehari (bukan real-time). Kalau nanti butuh
lebih sering, tinggal tambah baris cron — tapi jangan over-engineer di awal.
