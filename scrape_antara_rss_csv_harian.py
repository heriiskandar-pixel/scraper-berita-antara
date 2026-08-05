#!/usr/bin/env python3
"""
scrape_berita_rss.py
====================
Mengambil berita dari ANTARA News (RSS), Detik.com (RSS), dan Kompas.com (scraping).
Menyimpan hasil ke file Excel per tanggal terbit dengan Ringkasan & URL Gambar terisi.
"""

import os
import re
import time
import json
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone
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
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

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
        dt = parser.parse(str(raw), fuzzy=True)
        if dt.tzinfo is None:
            wib = timezone(timedelta(hours=7))
            dt = dt.replace(tzinfo=wib)
        return dt
    except Exception:
        return None

def format_tanggal_rfc2822(dt):
    if not dt:
        return ""
    return dt.strftime("%a, %d %b %Y %H:%M:%S %z")

# ----------------------------------------------------------------------
# AMBIL RSS ANTARA & DETIK
# ----------------------------------------------------------------------
FEEDS = {
    "antara-terkini": {"url": "https://www.antaranews.com/rss/terkini.xml", "media": "Antara", "kategori": "Terkini"},
    "antara-politik": {"url": "https://www.antaranews.com/rss/politik.xml", "media": "Antara", "kategori": "Politik"},
    "detik-news":     {"url": "https://news.detik.com/rss", "media": "Detik", "kategori": "News"},
    "detik-finance":  {"url": "https://finance.detik.com/rss", "media": "Detik", "kategori": "Finance"},
    "detik-sport":    {"url": "https://sport.detik.com/rss", "media": "Detik", "kategori": "Sport"},
}

def ambil_rss(feed_info):
    hasil = []
    try:
        resp = requests.get(feed_info["url"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        
        # Namespace XML untuk menangani tag media:content / media:thumbnail
        namespaces = {
            'media': 'http://search.yahoo.com/mrss/',
            'content': 'http://purl.org/rss/1.0/modules/content/'
        }

        for item in root.findall(".//item"):
            judul = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            tanggal = (item.findtext("pubDate") or "").strip()
            raw_desc = item.findtext("description") or ""
            
            cat_xml = item.findtext("category")
            kategori_berita = cat_xml.strip().capitalize() if cat_xml else feed_info["kategori"]

            # --- EKSTRAKSI URL GAMBAR ---
            url_gambar = ""
            
            # 1. Cek tag <enclosure url="...">
            enclosure = item.find("enclosure")
            if enclosure is not None and enclosure.get("url"):
                url_gambar = enclosure.get("url")
            
            # 2. Cek tag <media:content> atau <media:thumbnail>
            if not url_gambar:
                media_content = item.find("media:content", namespaces) or item.find("media:thumbnail", namespaces)
                if media_content is not None and media_content.get("url"):
                    url_gambar = media_content.get("url")

            # 3. Ekstrak dari HTML <img> di dalam description
            if not url_gambar and raw_desc:
                match_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_desc, re.IGNORECASE)
                if match_img:
                    url_gambar = match_img.group(1)

            # Clean description untuk ringkasan teks
            deskripsi = clean_html(raw_desc)

            hasil.append({
                "Kategori": kategori_berita,
                "Judul": judul,
                "Tanggal Terbit": tanggal,
                "Penulis": "",
                "Ringkasan": deskripsi,
                "Link": link,
                "URL Gambar": url_gambar,
                "Media": feed_info["media"]
            })
    except Exception as e:
        print(f"Gagal ambil RSS {feed_info['media']} ({feed_info['kategori']}): {e}")
    return hasil

# ----------------------------------------------------------------------
# SCRAPING KOMPAS.COM
# ----------------------------------------------------------------------
def ambil_kompas(max_artikel=30):
    hasil = []
    seen_links = set()
    urls = ["https://www.kompas.com/", "https://www.kompas.com/terpopuler"]

    for url in urls:
        if len(hasil) >= max_artikel:
            break
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
        except Exception as e:
            print(f"Gagal ambil Kompas dari {url}: {e}")
            continue

        soup = BeautifulSoup(resp.text, 'lxml')
        link_candidates = soup.find_all('a', href=re.compile(r'/read/\d{4}/\d{2}/\d{2}/'))

        for a in link_candidates:
            link = a.get('href')
            if not link or link in seen_links:
                continue
            
            if link.startswith("//"):
                link = "https:" + link
            elif link.startswith("/"):
                link = "https://www.kompas.com" + link

            judul = a.get_text(strip=True)
            if len(judul) < 20:
                continue

            # Tanggal dari URL Kompas
            match_date = re.search(r'/read/(\d{4})/(\d{2})/(\d{2})/', link)
            if match_date:
                thn, bln, tgl = match_date.groups()
                tanggal = f"{thn}-{bln}-{tgl} 00:00:00 +0700"
            else:
                tanggal = ""

            # Kategori dari domain
            subdomain_match = re.search(r'https://([a-zA-Z0-9-]+)\.kompas\.com', link)
            if subdomain_match:
                kat = subdomain_match.group(1).capitalize()
                kategori = "Berita Utama" if kat in ["Www", "News"] else kat
            else:
                kategori = "General"

            # EKSTRAKSI DETAIL ARTIKEL (RINGKASAN, GAMBAR, PENULIS)
            ringkasan = ""
            url_gambar = ""
            penulis = ""
            try:
                art_resp = requests.get(link, headers=HEADERS, timeout=5)
                if art_resp.status_code == 200:
                    art_soup = BeautifulSoup(art_resp.text, 'lxml')
                    
                    # 1. Ringkasan
                    meta_desc = art_soup.find('meta', attrs={'name': 'description'}) or \
                                art_soup.find('meta', attrs={'property': 'og:description'})
                    if meta_desc and meta_desc.get('content'):
                        ringkasan = meta_desc['content'].strip()
                    else:
                        p_first = art_soup.find('p')
                        if p_first:
                            ringkasan = p_first.get_text(strip=True)

                    # 2. URL Gambar
                    meta_img = art_soup.find('meta', attrs={'property': 'og:image'}) or \
                               art_soup.find('meta', attrs={'name': 'twitter:image'})
                    if meta_img and meta_img.get('content'):
                        url_gambar = meta_img['content'].strip()

                    # 3. Penulis
                    meta_author = art_soup.find('meta', attrs={'name': 'author'})
                    if meta_author and meta_author.get('content'):
                        penulis = meta_author['content'].strip()

            except Exception:
                pass

            seen_links.add(link)
            hasil.append({
                "Kategori": kategori,
                "Judul": judul,
                "Tanggal Terbit": tanggal,
                "Penulis": penulis,
                "Ringkasan": ringkasan,
                "Link": link,
                "URL Gambar": url_gambar,
                "Media": "Kompas"
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

    for key, feed_info in FEEDS.items():
        print(f"- Mengambil RSS [{feed_info['media']}] Kategori '{feed_info['kategori']}' ...", end=" ")
        berita = ambil_rss(feed_info)
        print(f"{len(berita)} berita")
        semua_berita.extend(berita)
        time.sleep(0.5)

    print("\n- Mengambil Kompas via scraping ...", end=" ")
    kompas_berita = ambil_kompas(max_artikel=30)
    print(f"{len(kompas_berita)} berita")
    semua_berita.extend(kompas_berita)

    if not semua_berita:
        print("Tidak ada berita yang berhasil diambil.")
        return

    df = pd.DataFrame(semua_berita)
    df["_tanggal_parsed"] = df["Tanggal Terbit"].apply(parse_tanggal)

    now = datetime.now(timezone.utc)
    batas_lama = now - timedelta(days=MAKS_UMUR_HARI)
    
    df = df[df["_tanggal_parsed"].notna()]
    df = df[df["_tanggal_parsed"] >= batas_lama]

    if df.empty:
        print("Tidak ada berita dalam rentang tanggal yang ditentukan.")
        return

    df["Tanggal Terbit"] = df["_tanggal_parsed"].apply(format_tanggal_rfc2822)
    df["_tanggal_file"] = df["_tanggal_parsed"].apply(lambda d: d.date().isoformat())
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    for tanggal_file, grup in df.groupby("_tanggal_file"):
        grup_clean = grup.drop(columns=["_tanggal_parsed", "_tanggal_file"])
        path_output = os.path.join(OUTPUT_FOLDER, f"{FILENAME_PREFIX}_{tanggal_file}.xlsx")
        simpan_excel(grup_clean, path_output)
        print(f"- {tanggal_file}: {len(grup_clean)} berita -> {path_output}")

    daftar = [{"file": f, "tanggal": f.replace(f"{FILENAME_PREFIX}_", "").replace(".xlsx", "")}
              for f in os.listdir(OUTPUT_FOLDER) if f.endswith(".xlsx")]
    with open(os.path.join(OUTPUT_FOLDER, "index.json"), "w", encoding="utf-8") as f:
        json.dump(daftar, f, ensure_ascii=False, indent=2)

    print("\nSelesai!")

if __name__ == "__main__":
    main()
