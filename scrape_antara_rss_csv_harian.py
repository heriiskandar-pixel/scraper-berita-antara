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


def parse_tanggal(raw: str):
    """Ubah format tanggal RSS (mis. 'Thu, 28 May 2026 13:27:46 +0700') jadi objek datetime.
    Kalau gagal dibaca, kembalikan None."""
    if not raw:
        return None
    for fmt in ("%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z"):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
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

    if not semua_berita:
        print("\nTidak ada berita yang berhasil diambil. Cek koneksi internet Anda.")
        return

    df = pd.DataFrame(semua_berita)

    # Parse tanggal terbit -> objek datetime. Kalau gagal dibaca, DIBUANG
    # (bukan disimpan sembarangan) supaya tidak ada file dengan tanggal salah.
    df["_tanggal_parsed"] = df["Tanggal Terbit"].apply(parse_tanggal)
    jumlah_sebelum = len(df)
    df = df[df["_tanggal_parsed"].notna()].reset_index(drop=True)
    jumlah_tanggal_gagal = jumlah_sebelum - len(df)
    if jumlah_tanggal_gagal:
        print(f"\n{jumlah_tanggal_gagal} berita dibuang karena tanggal terbitnya gagal dibaca")

    # Buang berita yang lebih tua dari MAKS_UMUR_HARI hari
    now = datetime.now().astimezone()
    batas_lama = now.timestamp() - (MAKS_UMUR_HARI * 24 * 60 * 60)
    jumlah_sebelum = len(df)
    df = df[df["_tanggal_parsed"].apply(lambda d: d.timestamp()) >= batas_lama].reset_index(drop=True)
    jumlah_dibuang = jumlah_sebelum - len(df)
    if jumlah_dibuang:
        print(f"{jumlah_dibuang} berita dibuang karena lebih tua dari {MAKS_UMUR_HARI} hari")

    if df.empty:
        print("\nTidak ada berita yang lolos filter tanggal. Tidak ada file yang disimpan.")
        return

    # Satu berita bisa muncul di beberapa kategori (mis. 'terkini' dan 'ekonomi').
    # Gabungkan nama kategorinya jadi satu, lalu buang baris duplikat.
    kategori_gabungan = (
        df.groupby("Link")["Kategori"]
        .apply(lambda s: ", ".join(sorted(set(s))))
        .to_dict()
    )
    df["Kategori"] = df["Link"].map(kategori_gabungan)
    df = df.drop_duplicates(subset=["Link"]).reset_index(drop=True)

    # Tanggal (tanpa jam) untuk pengelompokan nama file -- pakai tanggal LOKAL
    # sesuai zona waktu yang tertulis di RSS (WIB, +0700), bukan tanggal UTC.
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

        # Jaga-jaga: pastikan SEMUA baris di file ini benar tanggalnya sesuai nama file
        # (mis. kalau ada baris lama yang entah kenapa tanggalnya beda, dibuang di sini)
        gabungan = gabungan[
            gabungan["Tanggal Terbit"].apply(lambda t: str(parse_tanggal(t).date()) == tanggal_file if parse_tanggal(t) else False)
        ].reset_index(drop=True)

        simpan_excel(gabungan, path_output)
        print(f"- {tanggal_file}: {len(gabungan)} berita -> {path_output}")

    print("\nSelesai!")


if __name__ == "__main__":
    main()
