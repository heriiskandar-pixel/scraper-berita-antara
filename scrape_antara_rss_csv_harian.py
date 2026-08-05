#!/usr/bin/env python3
"""
scrape_berita_rss.py
====================
Mengambil berita dari ANTARA News (RSS), Detik.com (RSS), dan Kompas.com (scraping ringan).
Menyimpan hasil ke file Excel per tanggal terbit.
"""

import os
import re
import time
import json
import requests
import pandas as pd
from datetime import datetime, timedelta
from html import unescape
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
from dateutil import parser

# ----------------------------------------------------------------------
# PENGATURAN
# ----------------------------------------------------------------------
OUTPUT_FOLDER = "data"
FILENAME_PREFIX = "berita"
MAKS_UMUR_HARI = 7
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RSSReader/1.0)"}

# ----------------------------------------------------------------------
# FUNGSI UTILITAS
# ----------------------------------------------------------------------
def clean_html(raw_html):
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", "", raw_html)
    return unescape(text).strip()

def parse_tanggal(raw):
    if not raw:
        return None
    try:
        return parser.parse(str(raw), fuzzy=True)
    except Exception:
        return None

# ----------------------------------------------------------------------
# AMBIL RSS ANTARA & DETIK
# ----------------------------------------------------------------------
FEEDS = {
    "antara-terkini": "https://www.antaranews.com/rss/terkini.xml",
    "antara-politik": "https://www.antaranews.com/rss/politik.xml",
    "detik-news": "https://news.detik.com/rss",
    "detik-finance": "https://finance.detik.com/rss",
    "detik-sport": "https://sport.detik.com/rss",
}

def ambil_rss(nama_feed, url_feed):
    hasil = []
    try:
        resp = requests.get(url_feed, headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item"):
            judul = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            tanggal = (item.findtext("pubDate") or "").strip()
            deskripsi = clean_html(item.findtext("description") or "")
            hasil.append({
                "Kategori": nama_feed,
                "Judul": judul,
                "Tanggal Terbit": tanggal,
                "Penulis": "",
                "Ringkasan": deskripsi,
                "Link": link,
                "URL Gambar": "",
                "Media": "rss"
            })
    except Exception as e:
        print(f"Gagal ambil RSS {nama_feed}: {e}")
    return hasil

# ----------------------------------------------------------------------
# SCRAPING KOMPAS.COM
# ----------------------------------------------------------------------
def ambil_kompas(max_artikel=30):
    headers = {"User-Agent": "Mozilla/5.0"}
    hasil = []
    urls = ["https://www.kompas.com/", "https://www.kompas.com/terpopuler"]

    for url in urls:
        if len(hasil) >= max_artikel:
            break
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"Gagal ambil Kompas dari {url}: {e}")
            continue

        soup = BeautifulSoup(resp.text, 'lxml')
        link_candidates = soup.find_all('a', href=re.compile(r'/read/\d+'))

        for a in link_candidates[:max_artikel * 3]:
            link = a.get('href')
            if not link or not link.startswith("http"):
                continue
            judul = a.get_text(strip=True)
            if len(judul) < 20:
                continue

            tanggal = ""
            try:
                artikel_resp = requests.get(link, headers=headers, timeout=10)
                artikel_soup = BeautifulSoup(artikel_resp.text, 'lxml')
                meta_time = artikel_soup.find('meta', attrs={'name':'publishdate'})
                if meta_time and meta_time.get('content'):
                    tanggal = meta_time['content']
                else:
                    # fallback: cari elemen read__time
                    date_div = artikel_soup.find(['div','span'], class_=re.compile(r'read__time|date'))
                    if date_div:
                        tanggal = date_div.get_text(strip=True)
            except Exception as e:
                print(f"Gagal ambil tanggal dari {link}: {e}")

            hasil.append({
                "Kategori": "kompas",
                "Judul": judul,
                "Tanggal Terbit": tanggal,
                "Penulis": "",
                "Ringkasan": "",
                "Link": link,
                "URL Gambar": "",
                "Media": "kompascom"
            })
            if len(hasil) >= max_artikel:
                break
    return hasil

# ----------------------------------------------------------------------
# SIMPAN EXCEL
# ----------------------------------------------------------------------
def simpan_excel(df, path_output):
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    with pd.ExcelWriter(path_output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Berita")
        ws = writer.sheets["Berita"]
        for cell in ws[1]:
            cell.font = Font(bold=True)
        for idx, col in enumerate(df.columns, start=1):
            panjang = max([len(str(col))] + [len(str(v)) for v in df[col].astype(str).tolist()[:200]])
            ws.column_dimensions[get_column_letter(idx)].width = min(max(panjang + 2, 10), 60)
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"

# ----------------------------------------------------------------------
# MAIN
# ----------------------------------------------------------------------
def main():
    print("Mulai mengambil berita...\n")
    semua_berita = []

    for nama_feed, url_feed in FEEDS.items():
        print(f"- Mengambil RSS '{nama_feed}' ...", end=" ")
        berita = ambil_rss(nama_feed, url_feed)
        print(f"{len(berita)} berita")
        semua_berita.extend(berita)
        time.sleep(0.5)

    print("\n- Mengambil Kompas.com via scraping ...", end=" ")
    kompas_berita = ambil_kompas(max_artikel=30)
    print(f"{len(kompas_berita)} berita")
    semua_berita.extend(kompas_berita)

    if not semua_berita:
        print("Tidak ada berita yang berhasil diambil.")
        return

    df = pd.DataFrame(semua_berita)
    df["_tanggal_parsed"] = df["Tanggal Terbit"].apply(parse_tanggal)

    # Perbaikan timezone
    now = datetime.now().astimezone()
    batas_lama = now - timedelta(days=MAKS_UMUR_HARI)
    df["_tanggal_parsed"] = df["_tanggal_parsed"].apply(lambda d: d.replace(tzinfo=None) if d and d.tzinfo else d)
    df = df[df["_tanggal_parsed"].notna()]
    df = df[df["_tanggal_parsed"] >= batas_lama.replace(tzinfo=None)]

    df["_tanggal_file"] = df["_tanggal_parsed"].apply(lambda d: d.date().isoformat())
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    for tanggal_file, grup in df.groupby("_tanggal_file"):
        grup = grup.drop(columns=["_tanggal_parsed", "_tanggal_file"])
        path_output = os.path.join(OUTPUT_FOLDER, f"{FILENAME_PREFIX}_{tanggal_file}.xlsx")
        simpan_excel(grup, path_output)
        print(f"- {tanggal_file}: {len(grup)} berita -> {path_output}")

    daftar = [{"file": f, "tanggal": f.replace(f"{FILENAME_PREFIX}_", "").replace(".xlsx", "")}
              for f in os.listdir(OUTPUT_FOLDER) if f.endswith(".xlsx")]
    with open(os.path.join(OUTPUT_FOLDER, "index.json"), "w", encoding="utf-8") as f:
        json.dump(daftar, f, ensure_ascii=False, indent=2)

    print("\nSelesai!")

if __name__ == "__main__":
    main()
