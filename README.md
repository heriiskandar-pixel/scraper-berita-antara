# Scraper Berita ANTARA (RSS) — Otomatis Harian via GitHub Actions

Repo ini otomatis mengambil berita dari RSS feed ANTARA News setiap hari jam
07:00 WIB, dan menyimpan hasilnya sebagai file CSV di folder `data/`.

## Struktur file
- `scrape_antara_rss_csv_harian.py` — script scraping-nya
- `requirements.txt` — daftar library Python yang dibutuhkan
- `.github/workflows/scrape-daily.yml` — jadwal otomatis (GitHub Actions)
- `data/` — tempat hasil CSV harian tersimpan (otomatis bertambah tiap hari)

## Menjalankan manual (tanpa nunggu jadwal)
Buka tab **Actions** di repo ini → pilih workflow "Scrape Berita ANTARA
Harian" → klik tombol **Run workflow**.

## Mengubah jam jadwal
Edit baris `cron: "0 0 * * *"` di file
`.github/workflows/scrape-daily.yml`. Format: `menit jam tanggal bulan hari`,
dan waktunya dalam UTC (WIB = UTC+7, jadi kurangi 7 jam dari jam WIB yang
Anda mau).

## Catatan
Script ini hanya mengambil data dari RSS feed (bukan isi artikel penuh),
karena ANTARA melarang crawling otomatis untuk AI di halaman artikelnya.
