#!/usr/bin/env python3
"""
scrape_antara_rss.py  (versi sederhana - simpan ke CSV per hari)
==================================================================

APA YANG DILAKUKAN SCRIPT INI
------------------------------
1. Mengambil data berita dari RSS feed ANTARA News (judul, link, tanggal,
   ringkasan, kategori, dsb -- yang memang disediakan ANTARA untuk RSS).
2. Menyimpannya ke file CSV yang namanya otomatis mengandung tanggal HARI INI,
   contoh: berita_antara_2026-08-03.csv
3. Kalau dijalankan lagi di hari yang SAMA, file hari itu akan ditimpa dengan
   data terbaru (jadi aman dijalankan berkali-kali dalam sehari).
4. Kalau dijalankan di hari BERBEDA, otomatis membuat file CSV baru (nama
   tanggalnya beda) -- jadi lama-lama Anda akan punya satu file CSV per hari,
   seperti arsip harian.

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

Itu saja. Tidak perlu argumen apa pun. Secara default script akan mengambil
SEMUA kategori berita dan menyimpannya ke folder yang sama dengan file
CSV bernama sesuai tanggal hari ini.

Kalau mau folder output beda, kalau mau
"""

import os
import re
import time
from datetime import datetime, date
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
OUTPUT_FOLDER = "data"            # folder tempat CSV disimpan (folder 'data' di dalam repo)
FILENAME_PREFIX = "berita_antara"  # nama file jadi: data/berita_antara_2026-08-03.csv

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

    # Satu berita bisa muncul di beberapa kategori (mis. 'terkini' dan 'ekonomi').
    # Gabungkan nama kategorinya jadi satu, lalu buang baris duplikat.
    kategori_gabungan = (
        df.groupby("Link")["Kategori"]
        .apply(lambda s: ", ".join(sorted(set(s))))
        .to_dict()
    )
    df["Kategori"] = df["Link"].map(kategori_gabungan)
    df = df.drop_duplicates(subset=["Link"]).reset_index(drop=True)

    # Nama file otomatis pakai tanggal HARI INI
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    nama_file = f"{FILENAME_PREFIX}_{date.today().isoformat()}.csv"
    path_output = os.path.join(OUTPUT_FOLDER, nama_file)

    # encoding utf-8-sig supaya kalau dibuka di Excel, huruf non-ASCII (é, ñ, dsb) tidak berantakan
    df.to_csv(path_output, index=False, encoding="utf-8-sig")

    print(f"\nSelesai! {len(df)} berita disimpan ke file: {path_output}")


if __name__ == "__main__":
    main()
