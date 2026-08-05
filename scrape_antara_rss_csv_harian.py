#!/usr/bin/env python3
"""
scrape_berita_rss.py
====================
Skrip otomatisasi penarik berita:
- Menarik seluruh RSS Feed ANTARA News (17 Kanal) & RSS Detikcom.
- Melakukan scraping halaman Indeks Kanal Detikcom hingga Halaman 3 (max_page=3).
- Melakukan scraping halaman Indeks Kompas.com hingga Halaman 3 (max_page=3).
- Ekstraksi nama Penulis/Author secara presisi (termasuk fallback Redaksi).
- Analisis Sentimen Otomatis (Positif, Netral, Negatif).
- Menyimpan data kumulatif tanpa duplikat ke Excel per tanggal terbit & index.json.
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
# PENGATURAN GLOBAL
# ----------------------------------------------------------------------
OUTPUT_FOLDER = "data"
FILENAME_PREFIX = "berita"
MAKS_UMUR_HARI = 7
MAX_PAGE_INDEKS = 3  # Pengambilan hingga Halaman 3 untuk Indeks Detik & Kompas

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

# ----------------------------------------------------------------------
# KAMUS SENTIMEN BAHASA INDONESIA
# ----------------------------------------------------------------------
KATA_POSITIF = {
    "tumbuh", "naik", "untung", "sukses", "menang", "mencapai", "rekor", "apresiasi", 
    "positif", "membaik", "stabil", "bantuan", "resmi", "dukung", "lonjakan", "prestasi", 
    "puncak", "terbaik", "optimal", "laba", "surplus", "penghargaan", "berhasil", 
    "kerjasama", "inovasi", "pemulihan", "mendorong", "maju", "bangkit", "sejahtera",
    "pembangunan", "investasi", "optimis", "meningkat", "sambut", "karya", "juara"
}

KATA_NEGATIF = {
    "anjlok", "turun", "rugi", "krisis", "korupsi", "rusak", "tewas", "korban", 
    "kebakaran", "bencana", "gempa", "kecelakaan", "kasus", "sanksi", "ancam", 
    "ancaman", "bahaya", "tersangka", "pidana", "tangkap", "sidang", "sulit", 
    "menderita", "inflasi", "defisit", "blokir", "gagalkan", "vandalism", "ditahan", 
    "polisi", "kejahatan", "meninggal", "sakit", "wabah", "teror", "banjir", 
    "longsor", "sengketa", "parah", "pemecatan", "denda", "kecewa", "batal"
}

def analisa_sentimen(judul, ringkasan):
    """Menghitung skor sentimen berdasarkan frekuensi kata positif vs negatif"""
    teks = f"{judul} {ringkasan}".lower()
    kata_kata = re.findall(r'\b[a-z-]+\b', teks)
    
    skor_pos = sum(1 for w in kata_kata if w in KATA_POSITIF)
    skor_neg = sum(1 for w in kata_kata if w in KATA_NEGATIF)
    
    if skor_pos > skor_neg:
        return "Positif"
    elif skor_neg > skor_pos:
        return "Negatif"
    else:
        return "Netral"

# ----------------------------------------------------------------------
# 1. DAFTAR RSS FEEDS (ANTARA NEWS & DETIK)
# ----------------------------------------------------------------------
FEEDS_RSS = {
    # ANTARA NEWS (17 KANAL)
    "antara-terkini":    {"url": "https://www.antaranews.com/rss/terkini.xml", "media": "Antara", "kategori": "Terkini"},
    "antara-top-news":   {"url": "https://www.antaranews.com/rss/top-news.xml", "media": "Antara", "kategori": "Top News"},
    "antara-politik":    {"url": "https://www.antaranews.com/rss/politik.xml", "media": "Antara", "kategori": "Politik"},
    "antara-hukum":      {"url": "https://www.antaranews.com/rss/hukum.xml", "media": "Antara", "kategori": "Hukum"},
    "antara-ekonomi":    {"url": "https://www.antaranews.com/rss/ekonomi.xml", "media": "Antara", "kategori": "Ekonomi"},
    "antara-metro":      {"url": "https://www.antaranews.com/rss/metro.xml", "media": "Antara", "kategori": "Metro"},
    "antara-sepakbola":  {"url": "https://www.antaranews.com/rss/sepakbola.xml", "media": "Antara", "kategori": "Sepakbola"},
    "antara-olahraga":   {"url": "https://www.antaranews.com/rss/olahraga.xml", "media": "Antara", "kategori": "Olahraga"},
    "antara-humaniora":  {"url": "https://www.antaranews.com/rss/humaniora.xml", "media": "Antara", "kategori": "Humaniora"},
    "antara-lifestyle":  {"url": "https://www.antaranews.com/rss/lifestyle.xml", "media": "Antara", "kategori": "Lifestyle"},
    "antara-hiburan":    {"url": "https://www.antaranews.com/rss/hiburan.xml", "media": "Antara", "kategori": "Hiburan"},
    "antara-dunia":      {"url": "https://www.antaranews.com/rss/dunia.xml", "media": "Antara", "kategori": "Dunia"},
    "antara-infografis": {"url": "https://www.antaranews.com/rss/infografis.xml", "media": "Antara", "kategori": "Infografis"},
    "antara-tekno":      {"url": "https://www.antaranews.com/rss/tekno.xml", "media": "Antara", "kategori": "Tekno"},
    "antara-otomotif":   {"url": "https://www.antaranews.com/rss/otomotif.xml", "media": "Antara", "kategori": "Otomotif"},
    "antara-warta-bumi": {"url": "https://www.antaranews.com/rss/warta-bumi.xml", "media": "Antara", "kategori": "Warta Bumi"},
    "antara-foto":       {"url": "https://www.antaranews.com/rss/foto.xml", "media": "Antara", "kategori": "Foto"},

    # DETIK.COM (RSS)
    "detik-news":        {"url": "https://news.detik.com/rss", "media": "Detik", "kategori": "News"},
    "detik-finance":     {"url": "https://finance.detik.com/rss", "media": "Detik", "kategori": "Finance"},
    "detik-sport":       {"url": "https://sport.detik.com/rss", "media": "Detik", "kategori": "Sport"},
}

# ----------------------------------------------------------------------
# 2. DAFTAR KANAL INDEKS DETIKCOM (NON-RSS)
# ----------------------------------------------------------------------
KANAL_INDEKS_DETIK = [
    {"subdomain": "inet", "kategori": "Teknologi"},
    {"subdomain": "hot", "kategori": "Hiburan"},
    {"subdomain": "health", "kategori": "Kesehatan"},
    {"subdomain": "food", "kategori": "Kuliner"},
    {"subdomain": "travel", "kategori": "Wisata"},
    {"subdomain": "oto", "kategori": "Otomotif"},
    {"subdomain": "edu", "kategori": "Edukasi"},
    {"subdomain": "hikmah", "kategori": "Hikmah"},
    {"subdomain": "properti", "kategori": "Properti"},
    {"subdomain": "wolipop", "kategori": "Gaya Hidup"},
]

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

def ekstraksi_detail_halaman(url, media_default=""):
    """Mengambil meta description, og:image, dan Penulis dari halaman detail artikel"""
    ringkasan = ""
    url_gambar = ""
    penulis = ""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=6)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'lxml')
            
            # Ringkasan / Deskripsi
            meta_desc = soup.find('meta', attrs={'name': 'description'}) or \
                        soup.find('meta', attrs={'property': 'og:description'}) or \
                        soup.find('meta', attrs={'name': 'twitter:description'})
            if meta_desc and meta_desc.get('content'):
                ringkasan = meta_desc['content'].strip()
            else:
                p_first = soup.find('p')
                if p_first:
                    ringkasan = p_first.get_text(strip=True)

            # URL Gambar
            meta_img = soup.find('meta', attrs={'property': 'og:image'}) or \
                       soup.find('meta', attrs={'name': 'twitter:image'})
            if meta_img and meta_img.get('content'):
                url_gambar = meta_img['content'].strip()

            # Ekstraksi Penulis / Author
            meta_auth = soup.find('meta', attrs={'name': 'author'}) or \
                        soup.find('meta', attrs={'name': 'baca-author'}) or \
                        soup.find('meta', attrs={'property': 'article:author'}) or \
                        soup.find('meta', attrs={'property': 'dd:author'})
            
            if meta_auth and meta_auth.get('content'):
                penulis = meta_auth['content'].strip()
            
            # Jika meta tag kosong, cari di struktur HTML
            if not penulis:
                elem_author = soup.select_one('.detail__author, .read__author, .credit-title-name, .author, .byline, .penulis')
                if elem_author:
                    penulis = elem_author.get_text(strip=True)

            # Bersihkan format teks penulis
            if penulis:
                penulis = re.sub(r'^(Oleh|By|Penulis|Reporter)\s*:\s*', '', penulis, flags=re.I)
                penulis = re.sub(r'\s*-\s*detik.*$', '', penulis, flags=re.I)
                penulis = re.sub(r'\s*-\s*Kompas.*$', '', penulis, flags=re.I)
                penulis = re.sub(r'\s*-\s*ANTARA.*$', '', penulis, flags=re.I)
                penulis = penulis.strip()

    except Exception:
        pass

    # Fallback jika penulis tidak ditemukan
    if not penulis and media_default:
        penulis = f"Tim Redaksi {media_default}"

    return ringkasan, url_gambar, penulis

# ----------------------------------------------------------------------
# MODUL SCRAPING
# ----------------------------------------------------------------------
def ambil_rss(feed_info):
    """Ekstraksi berita dari Feed RSS"""
    hasil = []
    try:
        resp = requests.get(feed_info["url"], headers=HEADERS, timeout=20)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)
        
        namespaces = {
            'media': 'http://search.yahoo.com/mrss/',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'content': 'http://purl.org/rss/1.0/modules/content/'
        }

        for item in root.findall(".//item"):
            judul = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            tanggal = (item.findtext("pubDate") or "").strip()
            raw_desc = item.findtext("description") or ""
            
            cat_xml = item.findtext("category")
            kategori_berita = cat_xml.strip().capitalize() if cat_xml and cat_xml.strip() else feed_info["kategori"]

            # Ekstraksi Penulis dari RSS Tag
            penulis = ""
            for tag_auth in ["dc:creator", "author", "creator"]:
                found_p = item.findtext(tag_auth, namespaces=namespaces) or item.findtext(tag_auth)
                if found_p and found_p.strip():
                    penulis = found_p.strip()
                    break
            
            if not penulis:
                penulis = f"Redaksi {feed_info['media']}"

            # Ekstraksi Gambar RSS
            url_gambar = ""
            enclosure = item.find("enclosure")
            if enclosure is not None and enclosure.get("url"):
                url_gambar = enclosure.get("url")
            
            if not url_gambar:
                media_content = item.find("media:content", namespaces) or item.find("media:thumbnail", namespaces)
                if media_content is not None and media_content.get("url"):
                    url_gambar = media_content.get("url")

            if not url_gambar and raw_desc:
                match_img = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', raw_desc, re.IGNORECASE)
                if match_img:
                    url_gambar = match_img.group(1)

            deskripsi = clean_html(raw_desc)
            sentimen = analisa_sentimen(judul, deskripsi)

            hasil.append({
                "Kategori": kategori_berita,
                "Judul": judul,
                "Tanggal Terbit": tanggal,
                "Penulis": penulis,
                "Ringkasan": deskripsi,
                "Sentimen": sentimen,
                "Link": link,
                "URL Gambar": url_gambar,
                "Media": feed_info["media"]
            })
    except Exception as e:
        print(f"Gagal ambil RSS {feed_info['media']} ({feed_info['kategori']}): {e}")
    return hasil

def ambil_indeks_detik(subdomain, kategori_nama, max_page=3):
    """Scraping Indeks Detikcom hingga Halaman max_page"""
    hasil = []
    tgl_now = datetime.now().strftime("%m/%d/%Y")
    
    for page in range(1, max_page + 1):
        url = f"https://{subdomain}.detik.com/indeks/{page}?date={tgl_now}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                break
                
            soup = BeautifulSoup(resp.text, 'html.parser')
            articles = soup.find_all('article')
            
            for art in articles:
                tag_a = art.find('a', href=True)
                if not tag_a:
                    continue
                    
                link = tag_a['href']
                tag_title = art.find('h3') or art.find('h2') or tag_a
                judul = tag_title.get_text(strip=True) if tag_title else ""
                
                tag_img = art.find('img')
                url_gambar = ""
                if tag_img:
                    url_gambar = tag_img.get('src') or tag_img.get('data-src') or ""

                if len(judul) > 15:
                    ringkasan, img_detail, penulis = ekstraksi_detail_halaman(link, media_default="Detikcom")
                    if not url_gambar:
                        url_gambar = img_detail

                    sentimen = analisa_sentimen(judul, ringkasan)

                    hasil.append({
                        "Kategori": kategori_nama,
                        "Judul": judul,
                        "Tanggal Terbit": format_tanggal_rfc2822(datetime.now(timezone(timedelta(hours=7)))),
                        "Penulis": penulis,
                        "Ringkasan": ringkasan,
                        "Sentimen": sentimen,
                        "Link": link,
                        "URL Gambar": url_gambar,
                        "Media": "Detik"
                    })
        except Exception as e:
            print(f"Gagal scraping indeks Detik [{subdomain}] hal {page}: {e}")
            
    return hasil

def ambil_indeks_kompas(max_page=3):
    """Scraping Indeks Kompas.com hingga Halaman max_page"""
    hasil = []
    seen_links = set()
    tgl_now = datetime.now().strftime("%Y-%m-%d")

    for page in range(1, max_page + 1):
        url = f"https://indeks.kompas.com/?site=all&date={tgl_now}&page={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                break
                
            soup = BeautifulSoup(resp.text, 'lxml')
            articles = soup.find_all('div', class_='article__list') or soup.find_all('div', class_='articleList')
            
            if not articles:
                link_candidates = soup.find_all('a', href=re.compile(r'/read/\d{4}/\d{2}/\d{2}/'))
                for a in link_candidates:
                    link = a.get('href')
                    if not link or link in seen_links: continue
                    if link.startswith("//"): link = "https:" + link
                    elif link.startswith("/"): link = "https://www.kompas.com" + link
                    
                    judul = a.get_text(strip=True)
                    if len(judul) < 20: continue
                    
                    seen_links.add(link)
                    ringkasan, url_gambar, penulis = ekstraksi_detail_halaman(link, media_default="Kompas.com")
                    sentimen = analisa_sentimen(judul, ringkasan)
                    
                    hasil.append({
                        "Kategori": "Berita Utama",
                        "Judul": judul,
                        "Tanggal Terbit": format_tanggal_rfc2822(datetime.now(timezone(timedelta(hours=7)))),
                        "Penulis": penulis,
                        "Ringkasan": ringkasan,
                        "Sentimen": sentimen,
                        "Link": link,
                        "URL Gambar": url_gambar,
                        "Media": "Kompas"
                    })
            else:
                for art in articles:
                    tag_a = art.find('a', href=True)
                    if not tag_a: continue
                    
                    link = tag_a['href']
                    if link in seen_links: continue
                    seen_links.add(link)

                    tag_title = art.find('h3') or art.find('h2') or tag_a
                    judul = tag_title.get_text(strip=True) if tag_title else ""
                    if len(judul) < 15: continue

                    tag_cat = art.find('div', class_='article__subtitle') or art.find('h4')
                    kategori = tag_cat.get_text(strip=True) if tag_cat else "General"

                    ringkasan, url_gambar, penulis = ekstraksi_detail_halaman(link, media_default="Kompas.com")
                    sentimen = analisa_sentimen(judul, ringkasan)

                    hasil.append({
                        "Kategori": kategori,
                        "Judul": judul,
                        "Tanggal Terbit": format_tanggal_rfc2822(datetime.now(timezone(timedelta(hours=7)))),
                        "Penulis": penulis,
                        "Ringkasan": ringkasan,
                        "Sentimen": sentimen,
                        "Link": link,
                        "URL Gambar": url_gambar,
                        "Media": "Kompas"
                    })
        except Exception as e:
            print(f"Gagal scraping indeks Kompas hal {page}: {e}")

    return hasil

# ----------------------------------------------------------------------
# PENYIMPANAN DATA KE EXCEL
# ----------------------------------------------------------------------
def simpan_excel(df, path_output):
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter
    
    if os.path.exists(path_output):
        try:
            df_lama = pd.read_excel(path_output)
            df = pd.concat([df_lama, df], ignore_index=True)
            df.drop_duplicates(subset=["Link"], keep="first", inplace=True)
        except Exception as e:
            print(f"Gagal membaca Excel lama ({path_output}): {e}")

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
# MAIN FUNCTION
# ----------------------------------------------------------------------
def main():
    print("=== MULAI PENGAMBILAN BERITA AUTOMATIS (SENTIMEN + PENULIS) ===\n")
    semua_berita = []

    # 1. Ambil RSS Feeds
    print("1. Mengambil Feed RSS (ANTARA & Detik RSS)...")
    for key, feed_info in FEEDS_RSS.items():
        print(f"   - [{feed_info['media']}] Kanal '{feed_info['kategori']}'...", end=" ")
        berita = ambil_rss(feed_info)
        print(f"{len(berita)} berita")
        semua_berita.extend(berita)
        time.sleep(0.1)

    # 2. Scraping Indeks Detikcom (Halaman 1 s/d 3)
    print(f"\n2. Mengambil Indeks Kanal Detikcom (Halaman 1-{MAX_PAGE_INDEKS})...")
    for k_detik in KANAL_INDEKS_DETIK:
        print(f"   - [Detik] Indeks {k_detik['kategori']} ({k_detik['subdomain']}.detik.com)...", end=" ")
        berita_detik = ambil_indeks_detik(k_detik['subdomain'], k_detik['kategori'], max_page=MAX_PAGE_INDEKS)
        print(f"{len(berita_detik)} berita")
        semua_berita.extend(berita_detik)
        time.sleep(0.2)

    # 3. Scraping Indeks Kompas.com (Halaman 1 s/d 3)
    print(f"\n3. Mengambil Indeks Kompas.com (Halaman 1-{MAX_PAGE_INDEKS})...", end=" ")
    kompas_berita = ambil_indeks_kompas(max_page=MAX_PAGE_INDEKS)
    print(f"{len(kompas_berita)} berita")
    semua_berita.extend(kompas_berita)

    if not semua_berita:
        print("\nTidak ada berita yang berhasil diambil.")
        return

    df = pd.DataFrame(semua_berita)
    df.drop_duplicates(subset=["Link"], keep="first", inplace=True)

    # Parsing & Filter Umur Berita
    df["_tanggal_parsed"] = df["Tanggal Terbit"].apply(parse_tanggal)
    now = datetime.now(timezone.utc)
    batas_lama = now - timedelta(days=MAKS_UMUR_HARI)
    
    df = df[df["_tanggal_parsed"].notna()]
    df = df[df["_tanggal_parsed"] >= batas_lama]

    if df.empty:
        print("\nTidak ada berita baru dalam rentang waktu yang ditentukan.")
        return

    df["Tanggal Terbit"] = df["_tanggal_parsed"].apply(format_tanggal_rfc2822)
    df["_tanggal_file"] = df["_tanggal_parsed"].apply(lambda d: d.date().isoformat())
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    print("\n4. Menyimpan & Menggabungkan Hasil ke File Excel...")
    for tanggal_file, grup in df.groupby("_tanggal_file"):
        grup_clean = grup.drop(columns=["_tanggal_parsed", "_tanggal_file"])
        path_output = os.path.join(OUTPUT_FOLDER, f"{FILENAME_PREFIX}_{tanggal_file}.xlsx")
        simpan_excel(grup_clean, path_output)
        print(f"   - Update File: {path_output}")

    # Update index.json untuk Dashboard
    daftar = [{"file": f, "tanggal": f.replace(f"{FILENAME_PREFIX}_", "").replace(".xlsx", "")}
              for f in os.listdir(OUTPUT_FOLDER) if f.endswith(".xlsx")]
    with open(os.path.join(OUTPUT_FOLDER, "index.json"), "w", encoding="utf-8") as f:
        json.dump(daftar, f, ensure_ascii=False, indent=2)

    print("\n=== PROSES SELESAI! SEMUA BERITA & SENTIMEN BERHASIL DI-UPDATE ===")

if __name__ == "__main__":
    main()
