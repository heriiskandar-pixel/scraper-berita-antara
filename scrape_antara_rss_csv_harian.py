#!/usr/bin/env python3
"""
scrape_antara_rss.py  (versi Excel - 1 file per TANGGAL TERBIT berita)
=========================================================================

APA YANG DILAKUKAN SCRIPT INI
------------------------------
1. Mengambil data berita dari RSS feed ANTARA News (judul, link, tanggal
   terbit, ringkasan, kategori, dsb).
2. Mengelompokkan berita berdasarkan TANGGAL TERBIT ASLINYA (bukan tanggal
   script dijalankan) -- jadi kalau ada berita tanggal 1 Agustus dan 3
   Agustus dalam satu kali ambil data, otomatis dipisah ke 2 file berbeda:
       berita_antara_2026-08-01.xlsx
       berita_antara_2026-08-03.xlsx
   Dijamin isi tiap file cuma berita dengan tanggal terbit yang sesuai nama
   filenya -- tidak akan ada berita "nyasar" beda tanggal.
3. Kalau file untuk tanggal itu sudah pernah ada sebelumnya (dari run
   kemarin/tadi), data baru digabung ke situ (bukan ditimpa), lalu berita
   yang sama (link sama) tidak digandakan.
4. Berita yang tanggal terbitnya gagal dibaca/rusak akan DIBUANG (dicatat
   di layar), bukan disimpan sembarangan -- supaya tidak ada file dengan
   isi tanggal yang salah.
5. Berita yang lebih tua dari MAKS_UMUR_HARI hari (lihat pengaturan di
   bawah) tidak diambil sama sekali.
6. Setiap file Excel yang dihasilkan sudah otomatis aktif filter/sort-nya
   (AutoFilter) begitu dibuka -- tidak perlu Ctrl+Shift+L manual lagi.

CATATAN PENTING
----------------
Script ini HANYA mengambil data dari RSS feed (judul, ringkasan singkat,
tanggal, dsb). Script ini TIDAK membuka halaman artikel penuh di
antaranews.com, karena setiap halaman artikel ANTARA mencantumkan larangan
eksplisit terhadap crawling/pengindeksan otomatis untuk AI tanpa izin
tertulis dari ANTARA.

CARA PAKAI (paling gampang)
-----------------------------
    python3 scrape_antara_rss.py

Tidak perlu argumen apa pun.
"""

import os
import re
import time
from datetime import datetime
from html import unescape
from xml.etree import ElementTree as ET

import pandas as pd
import requests

import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime
import time
from dateutil import parser  # <-- tambahkan ini
from datetime import datetime, timedelta  # <-- pastikan timedelta ada
import re
# ----------------------------------------------------------------------
# FUNGSI SCRAPING LANGSUNG UNTUK DETIK.COM
# ----------------------------------------------------------------------
def ambil_detik(max_artikel=30):
    url = "https://www.detik.com/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Gagal ambil Detik: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'lxml')
    hasil = []
    debug_count = 0

    links = soup.find_all('a', href=re.compile(r'/(berita|news|detik)/\d+'))
    
    for a in links[:max_artikel * 2]:
        try:
            link = a.get('href')
            if not link:
                continue
            if link.startswith('/'):
                link = 'https://www.detik.com' + link
            elif not link.startswith('http'):
                continue

            judul = a.get_text(strip=True)
            if len(judul) < 20:
                continue

            kategori = 'umum'
            path = link.replace('https://', '').replace('http://', '')
            if path.startswith('news.'):
                path = path.replace('news.', '')
            parts = path.split('/')
            if len(parts) > 1:
                possible = parts[1].lower()
                if possible in ['ekonomi', 'politik', 'olahraga', 'sepakbola', 'tekno', 'health', 'lifestyle', 'dunia', 'metro', 'humaniora', 'hiburan', 'otomotif', 'bisnis', 'finansial', 'bursa']:
                    kategori = possible

            tanggal = ''
            parent = a.parent
            time_tag = parent.find('time') if parent else None
            if time_tag:
                tanggal = time_tag.get_text(strip=True)
            if not tanggal:
                for sibling in parent.find_all(['span', 'div'], class_=re.compile(r'time|date')):
                    tanggal = sibling.get_text(strip=True)
                    if tanggal:
                        break

            if debug_count < 3:
                print(f"  [DEBUG Detik] Contoh tanggal: '{tanggal}'")
                debug_count += 1

            hasil.append({
                "Kategori": kategori,
                "Judul": judul,
                "Tanggal Terbit": tanggal,
                "Penulis": "",
                "Ringkasan": "",
                "Link": link,
                "URL Gambar": "",
                "Media": "detikcom"
            })
            if len(hasil) >= max_artikel:
                break
        except Exception:
            continue

    return hasil
# ----------------------------------------------------------------------
# FUNGSI SCRAPING LANGSUNG UNTUK KOMPAS.COM
# ----------------------------------------------------------------------
def ambil_kompas(max_artikel=30):
    url = "https://www.kompas.com/"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
    except Exception as e:
        print(f"  Gagal ambil Kompas: {e}")
        return []

    soup = BeautifulSoup(resp.text, 'lxml')
    hasil = []
    debug_count = 0

    links = soup.find_all('a', href=re.compile(r'/read/\d+'))
    
    for a in links[:max_artikel * 2]:
        try:
            link = a.get('href')
            if not link:
                continue
            if link.startswith('/'):
                link = 'https://www.kompas.com' + link
            elif not link.startswith('http'):
                continue

            judul = a.get_text(strip=True)
            if len(judul) < 20:
                continue

            kategori = 'umum'
            path = link.replace('https://', '').replace('http://', '')
            if path.startswith('www.'):
                path = path.replace('www.', '')
            parts = path.split('/')
            if len(parts) > 1:
                possible = parts[1].lower()
                if possible in ['ekonomi', 'politik', 'olahraga', 'sepakbola', 'tekno', 'health', 'lifestyle', 'dunia', 'metro', 'humaniora', 'hiburan', 'otomotif', 'bisnis', 'finansial', 'bursa', 'internasional', 'nasional']:
                    kategori = possible

            tanggal = ''
            parent = a.parent
            time_tag = parent.find('time') if parent else None
            if time_tag:
                tanggal = time_tag.get_text(strip=True)
            if not tanggal:
                for sibling in parent.find_all(['span', 'div'], class_=re.compile(r'date|time')):
                    tanggal = sibling.get_text(strip=True)
                    if tanggal:
                        break

            if debug_count < 3:
                print(f"  [DEBUG Kompas] Contoh tanggal: '{tanggal}'")
                debug_count += 1

            hasil.append({
                "Kategori": kategori,
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
        except Exception:
            continue

    return hasil
# ----------------------------------------------------------------------
# 1) DAFTAR KANAL RSS ANTARA NEWS
#    (kalau mau ambil sebagian saja, edit/hapus baris di bawah)
# ----------------------------------------------------------------------
FEEDS = {
    "terkini": "https://www.antaranews.com/rss/terkini.xml",
    "top-news": "https://www.antaranews.com/rss/top-news.xml",
    "politik": "https://www.antaranews.com/rss/politik.xml",
    "hukum": "https://www.antaranews.com/rss/hukum.xml",
    "ekonomi": "https://www.antaranews.com/rss/ekonomi.xml",
    "ekonomi-finansial": "https://www.antaranews.com/rss/ekonomi-finansial.xml",
    "ekonomi-bisnis": "https://www.antaranews.com/rss/ekonomi-bisnis.xml",
    "ekonomi-bursa": "https://www.antaranews.com/rss/ekonomi-bursa.xml",
    "metro": "https://www.antaranews.com/rss/metro.xml",
    "sepakbola": "https://www.antaranews.com/rss/sepakbola.xml",
    "olahraga": "https://www.antaranews.com/rss/olahraga.xml",
    "humaniora": "https://www.antaranews.com/rss/humaniora.xml",
    "lifestyle": "https://www.antaranews.com/rss/lifestyle.xml",
    "hiburan": "https://www.antaranews.com/rss/hiburan.xml",
    "dunia": "https://www.antaranews.com/rss/dunia.xml",
    "infografik": "https://www.antaranews.com/rss/infografik.xml",
    "tekno": "https://www.antaranews.com/rss/tekno.xml",
    "otomotif": "https://www.antaranews.com/rss/otomotif.xml",
    "warta-bumi": "https://www.antaranews.com/rss/warta-bumi.xml",
    "rilis-pers": "https://www.antaranews.com/rss/rilis-pers.xml",
    "photo": "https://www.antaranews.com/rss/photo.xml",
    "video": "https://www.antaranews.com/rss/video.xml",
}

# ----------------------------------------------------------------------
# 2) PENGATURAN -- ubah di sini kalau perlu
# ----------------------------------------------------------------------
OUTPUT_FOLDER = "data"            # folder tempat file Excel disimpan
FILENAME_PREFIX = "berita_antara"  # nama file jadi: data/berita_antara_2026-08-03.xlsx
MAKS_UMUR_HARI = 7                # buang berita yang tanggal terbitnya lebih tua dari X hari

# ----------------------------------------------------------------------

NS = {
    "content": "http://purl.org/rss/1.0/modules/content/",
    "dc": "http://purl.org/dc/elements/1.1/",
    "media": "http://search.yahoo.com/mrss/",
}
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; RSSReader/1.0)"}


def clean_html(raw_html: str) -> str:
    """Buang tag HTML (mis. <img>) dari teks, sisakan teksnya saja."""
    if not raw_html:
        return ""
    text = re.sub(r"<[^>]+>", "", raw_html)
    return unescape(text).strip()


def parse_tanggal_umum(raw):
    """
    Parse berbagai format tanggal:
    - Format RSS standar (GMT, WIB)
    - Format Indonesia (Senin, 28 Mei 2026)
    - Format RELATIF (misal: '2 jam lalu', '5 hari yang lalu')
    """
    if not raw:
        return None
    
    raw = str(raw).strip()
    raw_lower = raw.lower()

    # =============================================
    # 1. DETEKSI TANGGAL RELATIF BAHASA INDONESIA
    # =============================================
    # Pola: angka + satuan waktu + (yang lalu / lalu)
    # Contoh: "2 jam yang lalu", "5 hari lalu", "1 minggu lalu"
    pola = re.compile(r'(\d+)\s*(menit|jam|hari|minggu|bulan|tahun)\s*(yang lalu|lalu)?')
    cocok = pola.search(raw_lower)
    
    if cocok:
        jumlah = int(cocok.group(1))
        satuan = cocok.group(2)
        
        # Waktu sekarang (dengan timezone, sesuai dengan logika di main)
        now = datetime.now().astimezone()
        
        # Konversi satuan ke timedelta
        if satuan == 'menit':
            delta = timedelta(minutes=jumlah)
        elif satuan == 'jam':
            delta = timedelta(hours=jumlah)
        elif satuan == 'hari':
            delta = timedelta(days=jumlah)
        elif satuan == 'minggu':
            delta = timedelta(weeks=jumlah)
        elif satuan == 'bulan':
            # Pendekatan: 1 bulan = 30 hari (cukup akurat untuk kebutuhan ini)
            delta = timedelta(days=jumlah * 30)
        elif satuan == 'tahun':
            # Pendekatan: 1 tahun = 365 hari
            delta = timedelta(days=jumlah * 365)
        else:
            delta = None
        
        if delta:
            # Kurangi waktu sekarang dengan delta
            hasil = now - delta
            return hasil

    # =============================================
    # 2. FORMAT LAINNYA (RSS, INDONESIA, DLL)
    # =============================================
    
    # Coba dengan dateutil (paling fleksibel)
    try:
        from dateutil import parser
        return parser.parse(raw, fuzzy=True)
    except:
        pass

    # Ganti nama bulan Indonesia ke Inggris (untuk format "Senin, 28 Mei 2026")
    bulan_ind = {
        'Jan': 'Jan', 'Feb': 'Feb', 'Mar': 'Mar', 'Apr': 'Apr',
        'Mei': 'May', 'Jun': 'Jun', 'Jul': 'Jul', 'Agu': 'Aug',
        'Sep': 'Sep', 'Okt': 'Oct', 'Nov': 'Nov', 'Des': 'Dec'
    }
    raw_english = raw
    for id, en in bulan_ind.items():
        raw_english = raw_english.replace(id, en)

    # Coba format RSS standar: "Thu, 28 May 2026 13:27:46 +0700"
    try:
        return datetime.strptime(raw_english, "%a, %d %b %Y %H:%M:%S %z")
    except:
        pass

    # Coba format lain
    for fmt in ("%d %b %Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw_english, fmt)
        except:
            continue

    # Kalau semua gagal, kembalikan None (berita akan dibuang)
    return None

def ambil_satu_feed(nama_feed: str, url_feed: str) -> list[dict]:
    """Ambil dan parse satu RSS feed. Kembalikan list berita (list of dict)."""
    resp = requests.get(url_feed, headers=HEADERS, timeout=20)
    resp.raise_for_status()

    root = ET.fromstring(resp.content)
    channel = root.find("channel")
    if channel is None:
        return []

    hasil = []
    for item in channel.findall("item"):
        judul = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        tanggal = (item.findtext("pubDate") or "").strip()
        penulis = (item.findtext("dc:creator", namespaces=NS) or "").strip()

        deskripsi = clean_html(item.findtext("description") or "")
        isi_encoded = clean_html(item.findtext("content:encoded", namespaces=NS) or "")

        gambar_url = ""
        media = item.find("media:content", namespaces=NS)
        if media is not None:
            gambar_url = media.get("url", "")

        hasil.append({
            "Kategori": nama_feed,
            "Judul": judul,
            "Tanggal Terbit": tanggal,
            "Penulis": penulis,
            "Ringkasan": deskripsi or isi_encoded,
            "Link": link,
            "URL Gambar": gambar_url,
           "Media": "antara"
        })
    return hasil


def simpan_excel(df: pd.DataFrame, path_output: str):
    """Simpan satu DataFrame ke file Excel dengan header tebal + AutoFilter otomatis aktif."""
    from openpyxl.styles import Font
    from openpyxl.utils import get_column_letter

    df = df.copy()
    # Excel tidak bisa simpan datetime dengan timezone -> buang info timezone-nya
    if "Tanggal Terbit" in df.columns:
        df["Tanggal Terbit"] = df["Tanggal Terbit"].apply(
            lambda v: v.replace(tzinfo=None) if isinstance(v, datetime) else v
        )

    with pd.ExcelWriter(path_output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Berita")
        ws = writer.sheets["Berita"]

        for cell in ws[1]:
            cell.font = Font(bold=True)

        for idx, col in enumerate(df.columns, start=1):
            panjang = max([len(str(col))] + [len(str(v)) for v in df[col].astype(str).tolist()[:200]])
            ws.column_dimensions[get_column_letter(idx)].width = min(max(panjang + 2, 10), 60)

        # Aktifkan AutoFilter untuk seluruh rentang data
        ws.auto_filter.ref = ws.dimensions
        ws.freeze_panes = "A2"


def muat_excel_lama(path_output: str) -> pd.DataFrame:
    """Baca file Excel yang sudah ada sebelumnya (kalau ada), untuk digabung dengan data baru."""
    if not os.path.exists(path_output):
        return pd.DataFrame()
    try:
        return pd.read_excel(path_output, sheet_name="Berita")
    except Exception as e:
        print(f"  [!] Tidak bisa baca file lama '{path_output}' ({e}), akan ditimpa baru.")
        return pd.DataFrame()


def main():
    print("Mulai mengambil berita dari RSS ANTARA News...\n")

    semua_berita = []
    for nama_feed, url_feed in FEEDS.items():
        print(f"- Mengambil kategori '{nama_feed}' ...", end=" ")
        try:
            berita = ambil_satu_feed(nama_feed, url_feed)
            print(f"{len(berita)} berita")
            semua_berita.extend(berita)
        except Exception as e:
            print(f"GAGAL ({e})")
        time.sleep(0.5)  # jeda sopan antar-request, jangan dihapus

# ========== TAMBAHAN SCRAPING DETIK & KOMPAS ==========
    print("\n- Mengambil Detik.com via scraping ...", end=" ")
    detik_berita = ambil_detik(max_artikel=30)
    print(f"{len(detik_berita)} berita")
    semua_berita.extend(detik_berita)
    time.sleep(1)

    print("- Mengambil Kompas.com via scraping ...", end=" ")
    kompas_berita = ambil_kompas(max_artikel=30)
    print(f"{len(kompas_berita)} berita")
    semua_berita.extend(kompas_berita)
    time.sleep(1)
    # ========== AKHIR TAMBAHAN ==========

   
    if    df = pd.DataFrame(semua_berita)

    # === PARSING TANGGAL DENGAN FALLBACK ===
    now = datetime.now().astimezone()

    def safe_parse_tanggal(tanggal_str):
        hasil = parse_tanggal_umum(tanggal_str)
        if hasil is None:
            return now  # fallback ke hari ini
        return hasil

    df["_tanggal_parsed"] = df["Tanggal Terbit"].apply(safe_parse_tanggal)

    # === DEBUG: CEK BERAPA YANG BERHASIL ===
    print(f"Berhasil parse tanggal: {df['_tanggal_parsed'].notna().sum()} dari {len(df)}")
    gagal = df[df['_tanggal_parsed'].isna()]
    if not gagal.empty:
        print("Contoh tanggal yang gagal di-parse:")
        print(gagal['Tanggal Terbit'].head(5).tolist())

    # === BUANG YANG TANGGALNYA NULL (HANYA YANG SANGAT GAGAL) ===
    jumlah_sebelum = len(df)
    df = df[df["_tanggal_parsed"].notna()].reset_index(drop=True)
    jumlah_tanggal_gagal = jumlah_sebelum - len(df)
    if jumlah_tanggal_gagal:
        print(f"{jumlah_tanggal_gagal} berita dibuang karena tanggalnya NULL")

    # === BUANG BERITA YANG LEBIH TUA DARI 7 HARI ===
    batas_lama = now.timestamp() - (MAKS_UMUR_HARI * 24 * 60 * 60)
    jumlah_sebelum = len(df)
    df = df[df["_tanggal_parsed"].apply(lambda d: d.timestamp()) >= batas_lama].reset_index(drop=True)
    jumlah_dibuang = jumlah_sebelum - len(df)
    if jumlah_dibuang:
        print(f"{jumlah_dibuang} berita dibuang karena lebih tua dari {MAKS_UMUR_HARI} hari")

    if df.empty:
        print("\nTidak ada berita yang lolos filter tanggal. Tidak ada file yang disimpan.")
        return

    # === GABUNGKAN KATEGORI PER LINK ===
    kategori_gabungan = (
        df.groupby("Link")["Kategori"]
        .apply(lambda s: ", ".join(sorted(set(s))))
        .to_dict()
    )
    df["Kategori"] = df["Link"].map(kategori_gabungan)
    df = df.drop_duplicates(subset=["Link"]).reset_index(drop=True)

    # === TANGGAL (TANPA JAM) UNTUK NAMA FILE ===
    df["_tanggal_file"] = df["_tanggal_parsed"].apply(lambda d: d.date().isoformat())

    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    print()
    for tanggal_file, grup in df.groupby("_tanggal_file"):
        grup = grup.drop(columns=["_tanggal_parsed", "_tanggal_file"])
        path_output = os.path.join(OUTPUT_FOLDER, f"{FILENAME_PREFIX}_{tanggal_file}.xlsx")

        lama = muat_excel_lama(path_output)
        if not lama.empty:
            gabungan = pd.concat([lama, grup], ignore_index=True)
            gabungan = gabungan.drop_duplicates(subset=["Link"], keep="last").reset_index(drop=True)
        else:
            gabungan = grup

        # === VALIDASI TANGGAL (DINONAKTIFKAN SEMENTARA AGAR DATA TIDAK HILANG) ===
        # gabungan = gabungan[
        #     gabungan["Tanggal Terbit"].apply(lambda t: str(parse_tanggal_umum(t).date()) == tanggal_file if parse_tanggal_umum(t) else False)
        # ]

        simpan_excel(gabungan, path_output)
        print(f"- {tanggal_file}: {len(gabungan)} berita -> {path_output}")

    # Buat daftar semua file Excel yang ada di folder output (index.json),
    # lengkap dengan tanggal dan jumlah berita di tiap file -- dipakai oleh
    # halaman web viewer (index.html) untuk menampilkan tabel & grafik tanpa
    # harus download semua file Excel satu-satu.
    import json
    from openpyxl import load_workbook

    daftar = []
    for f in os.listdir(OUTPUT_FOLDER):
        if not f.endswith(".xlsx"):
            continue
        tanggal = f.replace(f"{FILENAME_PREFIX}_", "").replace(".xlsx", "")
        try:
            wb = load_workbook(os.path.join(OUTPUT_FOLDER, f), read_only=True)
            ws = wb["Berita"]
            jumlah = max(ws.max_row - 1, 0)  # dikurangi 1 baris header
            wb.close()
        except Exception:
            jumlah = None
        daftar.append({"file": f, "tanggal": tanggal, "jumlah": jumlah})

    daftar.sort(key=lambda x: x["tanggal"], reverse=True)
    with open(os.path.join(OUTPUT_FOLDER, "index.json"), "w", encoding="utf-8") as f:
        json.dump(daftar, f, ensure_ascii=False, indent=2)

    print("\nSelesai!")


if __name__ == "__main__":
    main()
