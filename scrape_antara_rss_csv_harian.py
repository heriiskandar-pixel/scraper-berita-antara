#!/usr/bin/env python3
"""
scrape_berita_rss.py
====================
Skrip otomatisasi penarik berita:
- Analisis Sentimen berbasis AI (IndoBERT via Hugging Face Transformers).
- Menarik RSS Feed ANTARA News, Detikcom, CNN Indonesia, Tribunnews, CNBC Indonesia, Kontan, Tempo, Republika, Liputan6, JPNN, RRI, ANTARA Daerah, serta ANTARA Sumut & Aceh.
- Scraping halaman Indeks Kanal Detikcom (termasuk regional Sumut) & Kompas.com.
- Pemetaan kategori, ekstraksi gambar, penulis, dan sentimen secara akurat.
- Menyimpan data kumulatif tanpa duplikat ke dalam satu file semua_berita.json.
"""

import os
import re
import time
import json
import requests
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html import unescape
from xml.etree import ElementTree as ET
from bs4 import BeautifulSoup
from dateutil import parser
from transformers import pipeline

# ----------------------------------------------------------------------
# PENGATURAN GLOBAL
# ----------------------------------------------------------------------
OUTPUT_FOLDER = "data"
FILENAME_JSON = "semua_berita.json"
MAKS_UMUR_HARI = 7
MAX_PAGE_INDEKS = 3
MAX_WORKERS = 12

SENTIMEN_MODEL_ID = os.environ.get(
    "SENTIMEN_MODEL_ID",
    "mdhugol/indonesia-bert-sentiment-classification"
)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "id-ID,id;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.google.com/",
}

try:
    import cloudscraper
    _CF_SCRAPER = cloudscraper.create_scraper(
        browser={"browser": "chrome", "platform": "windows", "mobile": False}
    )
except ImportError:
    _CF_SCRAPER = requests

def _http_get(url, timeout=15, gunakan_cloudscraper=False):
    if not gunakan_cloudscraper:
        return requests.get(url, headers=HEADERS, timeout=timeout)

    resp = None
    try:
        resp = _CF_SCRAPER.get(url, headers=HEADERS, timeout=timeout)
        if resp.status_code != 403:
            return resp
    except Exception:
        pass

    try:
        proxy_url = "https://api.allorigins.win/raw?url=" + requests.utils.quote(url, safe="")
        resp_proxy = requests.get(proxy_url, headers=HEADERS, timeout=timeout + 15)
        return resp_proxy
    except Exception:
        if resp is not None:
            return resp
        raise

# ----------------------------------------------------------------------
# INISIALISASI MODEL AI SENTIMEN (INDOBERT)
# ----------------------------------------------------------------------
_STAT_SENTIMEN = {
    "sukses": 0,
    "gagal_load_model": 0,
    "label_tidak_dikenali": 0,
    "error_inferensi": 0,
}
_LABEL_TIDAK_DIKENALI_CONTOH = set()

print(f"Memuat model sentimen IndoBERT dari Hugging Face ('{SENTIMEN_MODEL_ID}')...")
try:
    sentimen_pipeline = pipeline(
        "text-classification",
        model=SENTIMEN_MODEL_ID,
        tokenizer=SENTIMEN_MODEL_ID,
        truncation=True,
        max_length=512,
    )
    id2label = dict(getattr(sentimen_pipeline.model.config, "id2label", {}))
    print(f"Model IndoBERT berhasil dimuat. Label mapping model: {id2label}\n")
except Exception as e:
    print(f"PERINGATAN KRITIS: Gagal memuat model IndoBERT ({type(e).__name__}: {e}).")
    print(f"                    -> SEMUA sentimen pada run ini akan menjadi 'Netral'.\n")
    sentimen_pipeline = None

def _normalisasi_label(label_mentah, skor):
    l = str(label_mentah).strip().upper()
    if l in ("0",) or "POS" in l:
        return "Positif"
    if l in ("2",) or "NEG" in l:
        return "Negatif"
    if l in ("1",) or "NEU" in l or "NET" in l:
        return "Netral"
    return "Netral"

def analisa_sentimen(judul, ringkasan):
    if not sentimen_pipeline:
        _STAT_SENTIMEN["gagal_load_model"] += 1
        return "Netral"
    teks = f"{judul}. {ringkasan}".strip()
    if not teks:
        return "Netral"
    try:
        hasil = sentimen_pipeline(teks)[0]
        _STAT_SENTIMEN["sukses"] += 1
        return _normalisasi_label(hasil["label"], hasil.get("score", 0.0))
    except Exception:
        _STAT_SENTIMEN["error_inferensi"] += 1
        return "Netral"

def cetak_ringkasan_sentimen():
    print("\n--- Ringkasan Proses Analisis Sentimen ---")
    print(f"  Berhasil dianalisis      : {_STAT_SENTIMEN['sukses']}")
    print(f"  Gagal (model tidak load) : {_STAT_SENTIMEN['gagal_load_model']}")
    print(f"  Gagal (error inferensi)  : {_STAT_SENTIMEN['error_inferensi']}")
    print("-------------------------------------------\n")

# ----------------------------------------------------------------------
# DAFTAR RSS FEEDS & KANAL INDEKS
# ----------------------------------------------------------------------
FEEDS_RSS = {
    "antara-terkini":    {"url": "https://www.antaranews.com/rss/terkini.xml", "media": "Antara", "kategori": "Terkini"},
    "antara-top-news":   {"url": "https://www.antaranews.com/rss/top-news.xml", "media": "Antara", "kategori": "Top News"},
    "antara-ekonomi":    {"url": "https://www.antaranews.com/rss/ekonomi.xml", "media": "Antara", "kategori": "Ekonomi"},
    "antara-politik":    {"url": "https://www.antaranews.com/rss/politik.xml", "media": "Antara", "kategori": "Politik"},
    "detik-news":        {"url": "https://news.detik.com/berita/rss", "media": "Detik", "kategori": "News"},
    "detik-finance":     {"url": "https://finance.detik.com/rss", "media": "Detik", "kategori": "Finance"},
    "detik-hot":         {"url": "https://hot.detik.com/rss", "media": "Detik", "kategori": "Hot"},
    "cnn-nasional":      {"url": "https://www.cnnindonesia.com/nasional/rss", "media": "CNN Indonesia", "kategori": "Nasional"},
    "cnn-ekonomi":       {"url": "https://www.cnnindonesia.com/ekonomi/rss", "media": "CNN Indonesia", "kategori": "Ekonomi"},
    "tribun-news":       {"url": "https://www.tribunnews.com/rss", "media": "Tribunnews", "kategori": "News"},
    "cnbc-news":         {"url": "https://www.cnbcindonesia.com/news/rss", "media": "CNBC Indonesia", "kategori": "News"},
    "kontan-nasional":   {"url": "https://rss.kontan.co.id/news/nasional", "media": "Kontan", "kategori": "Nasional"},
    "tempo-nasional":    {"url": "https://rss.tempo.co/nasional", "media": "Tempo", "kategori": "Nasional"},
    "republika-news":    {"url": "https://www.republika.co.id/rss/nasional/", "media": "Republika", "kategori": "News"},
    "liputan6-news":     {"url": "https://feed.liputan6.com/rss/news", "media": "Liputan6", "kategori": "News"},
    "jpnn-utama":        {"url": "https://www.jpnn.com/rss", "media": "JPNN", "kategori": "Nasional"},
    "rri-utama":         {"url": "https://rri.co.id/rss", "media": "RRI", "kategori": "Nasional"},
    "antara-jabar":      {"url": "https://jabar.antaranews.com/rss/terkini.xml", "media": "ANTARA Jabar", "kategori": "Regional"},
    "antara-sumut":      {"url": "https://sumut.antaranews.com/rss/terkini.xml", "media": "ANTARA Sumut", "kategori": "Regional"},
    "antara-aceh":       {"url": "https://aceh.antaranews.com/rss/terkini.xml", "media": "ANTARA Aceh", "kategori": "Regional"},
}

# Perbaikan struktur URL indeks Detik menggunakan format direktori path yang valid
KANAL_INDEKS_DETIK = [
    {"url_path": "inet", "kategori": "Teknologi"},
    {"url_path": "hot", "kategori": "Hiburan"},
    {"url_path": "health", "kategori": "Kesehatan"},
    {"url_path": "food", "kategori": "Kuliner"},
    {"url_path": "travel", "kategori": "Wisata"},
    {"url_path": "oto", "kategori": "Otomotif"},
    {"url_path": "sumut", "kategori": "Regional Sumut"},
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
    ringkasan = ""
    url_gambar = ""
    penulis = ""
    domain_cf = any(d in url for d in ["cnnindonesia.com", "cnbcindonesia.com", "tempo.co"])
    try:
        resp = _http_get(url, timeout=6, gunakan_cloudscraper=domain_cf)
        if resp.status_code == 200:
            soup = BeautifulSoup(resp.text, 'lxml')
            
            meta_desc = soup.find('meta', attrs={'name': 'description'}) or \
                        soup.find('meta', attrs={'property': 'og:description'}) or \
                        soup.find('meta', attrs={'name': 'twitter:description'})
            if meta_desc and meta_desc.get('content'):
                ringkasan = meta_desc['content'].strip()

            meta_img = soup.find('meta', attrs={'property': 'og:image'}) or \
                       soup.find('meta', attrs={'name': 'twitter:image'})
            if meta_img and meta_img.get('content'):
                url_gambar = meta_img['content'].strip()

            meta_auth = soup.find('meta', attrs={'name': 'author'}) or \
                        soup.find('meta', attrs={'name': 'baca-author'}) or \
                        soup.find('meta', attrs={'property': 'article:author'})
            if meta_auth and meta_auth.get('content'):
                penulis = meta_auth['content'].strip()
            
            if not penulis:
                elem_author = soup.select_one('.detail__author, .read__author, .credit-title-name, .author, .byline')
                if elem_author:
                    penulis = elem_author.get_text(strip=True)

            if penulis:
                penulis = re.sub(r'^(Oleh|By|Penulis|Reporter|Editor)\s*:\s*', '', penulis, flags=re.I)
                penulis = re.sub(r'\s*-\s*(detik|Kompas|ANTARA|CNN|CNBC|Tribun|Tempo|Kontan|Liputan6|JPNN|RRI).*$', '', penulis, flags=re.I)
                penulis = penulis.strip()
    except Exception:
        pass

    if not penulis and media_default:
        penulis = f"Redaksi {media_default}"

    return ringkasan, url_gambar, penulis

def ekstraksi_detail_banyak_halaman(daftar_link, media_default="", max_workers=MAX_WORKERS):
    hasil = {}
    if not daftar_link:
        return hasil
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_ke_link = {
            executor.submit(ekstraksi_detail_halaman, link, media_default): link
            for link in daftar_link
        }
        for future in as_completed(future_ke_link):
            link = future_ke_link[future]
            try:
                hasil[link] = future.result()
            except Exception:
                hasil[link] = ("", "", "")
    return hasil

# ----------------------------------------------------------------------
# MODUL SCRAPING
# ----------------------------------------------------------------------
def ambil_rss(feed_info):
    hasil = []
    domain_cf = any(d in feed_info["url"] for d in ["cnnindonesia.com", "cnbcindonesia.com", "tempo.co"])
    try:
        resp = _http_get(feed_info["url"], timeout=20, gunakan_cloudscraper=domain_cf)
        resp.raise_for_status()
        
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            root = ET.fromstring(resp.text.encode('utf-8'))

        namespaces = {
            'media': 'http://search.yahoo.com/mrss/',
            'dc': 'http://purl.org/dc/elements/1.1/',
            'content': 'http://purl.org/rss/1.0/modules/content/'
        }

        item_mentah = []
        link_perlu_detail = set()
        for item in root.findall(".//item"):
            judul = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            tanggal = (item.findtext("pubDate") or "").strip()
            raw_desc = item.findtext("description") or ""
            
            cat_xml = item.findtext("category")
            kategori_berita = cat_xml.strip().capitalize() if cat_xml and cat_xml.strip() else feed_info["kategori"]

            penulis = ""
            for tag_auth in ["dc:creator", "author", "creator"]:
                found_p = item.findtext(tag_auth, namespaces=namespaces) or item.findtext(tag_auth)
                if found_p and found_p.strip():
                    penulis = found_p.strip()
                    break

            deskripsi = clean_html(raw_desc)
            url_gambar = ""
            enclosure = item.find("enclosure")
            if enclosure is not None and enclosure.get("url"):
                url_gambar = enclosure.get("url")
            if not url_gambar:
                media_content = item.find("media:content", namespaces) or item.find("media:thumbnail", namespaces)
                if media_content is not None and media_content.get("url"):
                    url_gambar = media_content.get("url")

            butuh_detail = (not penulis) or (len(deskripsi) < 30) or (not url_gambar)
            if butuh_detail and link:
                link_perlu_detail.add(link)

            item_mentah.append({
                "kategori": kategori_berita,
                "judul": judul,
                "link": link,
                "tanggal": tanggal,
                "penulis": penulis,
                "deskripsi": deskripsi,
                "url_gambar": url_gambar,
            })

        detail_map = ekstraksi_detail_banyak_halaman(
            list(link_perlu_detail), media_default=feed_info["media"]
        )

        for it in item_mentah:
            penulis = it["penulis"]
            deskripsi = it["deskripsi"]
            url_gambar = it["url_gambar"]

            if it["link"] in detail_map:
                detail_desc, detail_img, detail_penulis = detail_map[it["link"]]
                if not penulis and detail_penulis:
                    penulis = detail_penulis
                if len(deskripsi) < 30 and detail_desc:
                    deskripsi = detail_desc
                if not url_gambar and detail_img:
                    url_gambar = detail_img

            if not penulis:
                penulis = f"Redaksi {feed_info['media']}"

            sentimen = analisa_sentimen(it["judul"], deskripsi)

            hasil.append({
                "Kategori": it["kategori"],
                "Judul": it["judul"],
                "Tanggal Terbit": it["tanggal"],
                "Penulis": penulis,
                "Ringkasan": deskripsi,
                "Sentimen": sentimen,
                "Link": it["link"],
                "URL Gambar": url_gambar,
                "Media": feed_info["media"]
            })
    except Exception as e:
        print(f"Gagal ambil RSS {feed_info['media']} ({feed_info['kategori']}): {e}")
    return hasil

def ambil_indeks_detik(url_path, kategori_nama, max_page=3):
    hasil = []
    tgl_now = datetime.now().strftime("%m/%d/%Y")
    kandidat = []

    for page in range(1, max_page + 1):
        # Menggunakan struktur URL path standar Detik.com (misal: detik.com/sumut/indeks/1)
        url = f"https://www.detik.com/{url_path}/indeks/{page}?date={tgl_now}"
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
                    kandidat.append((link, judul, url_gambar))
        except Exception as e:
            print(f"Gagal scraping indeks Detik [{url_path}] hal {page}: {e}")

    detail_map = ekstraksi_detail_banyak_halaman(
        [link for link, _, _ in kandidat], media_default="Detikcom"
    )

    wib = timezone(timedelta(hours=7))
    tgl_sekarang_wib = format_tanggal_rfc2822(datetime.now(wib))

    for link, judul, url_gambar in kandidat:
        ringkasan, img_detail, penulis = detail_map.get(link, ("", "", ""))
        if not url_gambar:
            url_gambar = img_detail
        if not penulis:
            penulis = "Redaksi Detikcom"

        sentimen = analisa_sentimen(judul, ringkasan)
        hasil.append({
            "Kategori": kategori_nama,
            "Judul": judul,
            "Tanggal Terbit": tgl_sekarang_wib,
            "Penulis": penulis,
            "Ringkasan": ringkasan,
            "Sentimen": sentimen,
            "Link": link,
            "URL Gambar": url_gambar,
            "Media": "Detik"
        })

    return hasil

def ambil_indeks_kompas(max_page=3):
    hasil = []
    seen_links = set()
    tgl_now = datetime.now().strftime("%Y-%m-%d")
    kandidat = []

    for page in range(1, max_page + 1):
        url = f"https://indeks.kompas.com/?site=all&date={tgl_now}&page={page}"
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                break
                
            soup = BeautifulSoup(resp.text, 'lxml')
            articles = (
                soup.find_all('div', class_=re.compile(r'article__list|articleList|article__item')) or
                soup.find_all('div', class_='neath-item')
            )
            
            if not articles:
                link_candidates = soup.find_all('a', href=re.compile(r'https?://[a-zA-Z0-9.-]*kompas\.com/read/\d{4}/\d{2}/\d{2}/\d+'))
                for a in link_candidates:
                    link = a.get('href')
                    if not link or link in seen_links: 
                        continue
                    judul = a.get_text(strip=True)
                    if len(judul) < 10: 
                        continue
                    seen_links.add(link)
                    kandidat.append((link, judul, "Berita Utama"))
            else:
                for art in articles:
                    tag_a = art.find('a', href=True)
                    if not tag_a: 
                        continue
                    link = tag_a['href']
                    if not link.startswith("http"):
                        if link.startswith("//"): 
                            link = "https:" + link
                        elif link.startswith("/"): 
                            link = "https://www.kompas.com" + link
                    if link in seen_links: 
                        continue
                    seen_links.add(link)

                    tag_title = art.find('h3') or art.find('h2') or art.find('a')
                    judul = tag_title.get_text(strip=True) if tag_title else ""
                    if len(judul) < 10: 
                        continue

                    tag_cat = art.find('div', class_=re.compile(r'article__subtitle|subtitle|kanal')) or art.find('h4')
                    kategori = tag_cat.get_text(strip=True) if tag_cat else "General"
                    kandidat.append((link, judul, kategori))
        except Exception as e:
            print(f"Gagal scraping indeks Kompas hal {page}: {e}")

    detail_map = ekstraksi_detail_banyak_halaman(
        [link for link, _, _ in kandidat], media_default="Kompas.com"
    )

    wib = timezone(timedelta(hours=7))
    tgl_sekarang_wib = format_tanggal_rfc2822(datetime.now(wib))

    for link, judul, kategori in kandidat:
        ringkasan, url_gambar, penulis = detail_map.get(link, ("", "", ""))
        if not penulis:
            penulis = "Redaksi Kompas.com"

        sentimen = analisa_sentimen(judul, ringkasan)
        hasil.append({
            "Kategori": kategori,
            "Judul": judul,
            "Tanggal Terbit": tgl_sekarang_wib,
            "Penulis": penulis,
            "Ringkasan": ringkasan,
            "Sentimen": sentimen,
            "Link": link,
            "URL Gambar": url_gambar,
            "Media": "Kompas"
        })

    return hasil

# ----------------------------------------------------------------------
# MAIN FUNCTION
# ----------------------------------------------------------------------
def main():
    print("=== MULAI SCRAPING BERITA OTOMATIS + AI SENTIMEN (INDOBERT) ===\n")
    semua_berita = []

    print("1. Mengambil Feed RSS...")
    for key, feed_info in FEEDS_RSS.items():
        print(f"   - [{feed_info['media']}] Kanal '{feed_info['kategori']}'...", end=" ")
        berita = ambil_rss(feed_info)
        print(f"{len(berita)} berita")
        semua_berita.extend(berita)
        time.sleep(0.1)

    print(f"\n2. Mengambil Indeks Kanal Detikcom (termasuk Sumut) (Halaman 1-{MAX_PAGE_INDEKS})...")
    for k_detik in KANAL_INDEKS_DETIK:
        print(f"   - [Detik] Indeks {k_detik['kategori']} (detik.com/{k_detik['url_path']})...", end=" ")
        berita_detik = ambil_indeks_detik(k_detik['url_path'], k_detik['kategori'], max_page=MAX_PAGE_INDEKS)
        print(f"{len(berita_detik)} berita")
        semua_berita.extend(berita_detik)
        time.sleep(0.2)

    print(f"\n3. Mengambil Indeks Kompas.com (Halaman 1-{MAX_PAGE_INDEKS})...", end=" ")
    kompas_berita = ambil_indeks_kompas(max_page=MAX_PAGE_INDEKS)
    print(f"{len(kompas_berita)} berita")
    semua_berita.extend(kompas_berita)

    cetak_ringkasan_sentimen()

    if not semua_berita:
        print("\nTidak ada berita yang berhasil diambil.")
        return

    df = pd.DataFrame(semua_berita)
    df.drop_duplicates(subset=["Link"], keep="first", inplace=True)

    df["_tanggal_parsed"] = df["Tanggal Terbit"].apply(parse_tanggal)
    now = datetime.now(timezone.utc)
    batas_lama = now - timedelta(days=MAKS_UMUR_HARI)
    
    df = df[df["_tanggal_parsed"].notna()]
    df = df[df["_tanggal_parsed"] >= batas_lama]

    if df.empty:
        print("\nTidak ada berita baru dalam rentang waktu yang ditentukan.")
        return

    df["Tanggal Terbit"] = df["_tanggal_parsed"].apply(format_tanggal_rfc2822)
    df = df.drop(columns=["_tanggal_parsed"])
    
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    path_output = os.path.join(OUTPUT_FOLDER, FILENAME_JSON)

    print("\n4. Menyimpan Hasil ke File JSON...")
    data_final = df.to_dict(orient="records")
    if os.path.exists(path_output):
        try:
            with open(path_output, "r", encoding="utf-8") as f:
                data_lama = json.load(f)
            existing_links = {item["Link"]: item for item in data_lama}
            for item in data_final:
                existing_links[item["Link"]] = item
            data_final = list(existing_links.values())
        except Exception as e:
            print(f"Peringatan: Gagal membaca file JSON lama ({e}), menimpa dengan data baru.")

    with open(path_output, "w", encoding="utf-8") as f:
        json.dump(data_final, f, ensure_ascii=False, indent=2)

    print(f"   - Berhasil menyimpan total {len(data_final)} berita ke: {path_output}")
    print("\n=== PROSES SELESAI! ===")

if __name__ == "__main__":
    main()
