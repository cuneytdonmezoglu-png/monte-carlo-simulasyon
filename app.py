import streamlit as st
import requests
import numpy as np
import pandas as pd
import json
import os
from datetime import datetime

st.set_page_config(page_title="Pro Monte Carlo & Skor Analiz Paneli", page_icon="⚽", layout="wide")

ODDS_API_KEY = "f6649c5150399729774787d9fac15cbb"
CACHE_FILE = "maclar_cache.json"

st.title("⚽ Profesyonel Futbol Monte Carlo, Skor Tahmin & Canlı H2H Paneli")

LIGLER = [
    "soccer_turkey_super_league",
    "soccer_epl",
    "soccer_spain_la_liga",
    "soccer_italy_serie_a",
    "soccer_germany_bundesliga",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league",
    "soccer_uefa_europa_league"
]

def tum_liglerin_verisini_getir():
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list) and len(data) > 0:
                    return data, True
        except Exception:
            pass

    tum_maclar = []
    pbar = st.progress(0)
    for idx, lig in enumerate(LIGLER):
        url = "https://api.the-odds-api.com/v4/sports/" + lig + "/odds/?apiKey=" + ODDS_API_KEY + "&regions=eu&markets=h2h"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                json_data = res.json()
                if isinstance(json_data, list):
                    tum_maclar.extend(json_data)
        except Exception:
            pass
        pbar.progress((idx + 1) / len(LIGLER))
    pbar.empty()

    if tum_maclar:
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(tum_maclar, f, ensure_ascii=False, indent=4)
        except Exception:
            pass
        return tum_maclar, False

    return [], False

# --- AKILLI TAKIM ID EŞLEŞTİRME SÖZLÜĞÜ (Sofascore Resmi ID'leri) ---
SOFASCORE_TAKIM_IDLERI = {
    # Süper Lig Örnekleri
    "Galatasaray": 2993,
    "Fenerbahce": 2999,
    "Besiktas": 2987,
    "Trabzonspor": 2989,
    "Basaksehir": 10534,
    "Adana Demirspor": 11598,
    "Gazişehir Gaziantep": 11222,
    "Gaziantep FK": 11222,
    "Kasimpasa SK": 3004,
    "Kasımpaşa": 3004,
    "Antalyaspor": 3001,
    "Alanyaspor": 44871,
    "Kayserispor": 3000,
    "Sivasspor": 2992,
    "Konyaspor": 2998,
    "Hatayspor": 20412,
    "Samsunspor": 3013,
    "Rizespor": 3002,
    "Eyüpspor": 7926,
    "Bodrum FK": 208573,
    
    # Avrupa Devleri Örnekleri
    "Real Madrid": 2829,
    "Barcelona": 2817,
    "Atletico Madrid": 2836,
    "Manchester City": 17,
    "Manchester United": 35,
    "Arsenal": 42,
    "Liverpool": 44,
    "Chelsea": 38,
    "Tottenham Hotspur": 33,
    "Real Madrid": 2829,
    "Bayern Munich": 2681,
    "Borussia Dortmund": 2672,
    "Inter": 2697,
    "AC Milan": 2692,
    "Juventus": 2687,
    "PSG": 1644
}

def takim_id_bul(takim_adi):
    # 1. Doğrudan sözlükte var mı kontrol et
    if takim_adi in SOFASCORE_TAKIM_IDLERI:
        return SOFASCORE_TAKIM_IDLERI[takim_adi]
    
    # 2. Küçük/büyük harf duyarsız veya kısmi eşleşme dene
    for key, val in SOFASCORE_TAKIM_IDLERI.items():
        if key.lower() in takim_adi.lower() or takim_adi.lower() in key.lower():
            return val
            
    return None

@st.cache_data(ttl=3600)
def sofascore_h2h_getir(ev_takim, dep_takim):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        ev_id = takim_id_bul(ev_takim)
        dep_id = takim_id_bul(dep_takim)

        # Eğer sözlükte bulunamadıysa Sofascore arama API'sine fallback yap
        if not ev_id:
            arama = requests.get(f"https://api.sofascore.com/api/v1/search/teams?q={ev_takim}", headers=headers, timeout=3)
            if arama.status_code == 200:
                teams = arama.json().get("teams", [])
                if teams: ev_id = teams[0].get("id")

        if not dep_id:
            arama = requests.get(f"https://api.sofascore.com/api/v1/search/teams?q={dep_takim}", headers=headers, timeout=3)
            if arama.status_code == 200:
                teams = arama.json().get("teams", [])
                if teams: dep_id = teams[0].get("id")

        if not (ev_id and dep_id):
            return [], f"Eşleştirme yapılamadı ({ev_takim} vs {dep_takim})."

        h2h_url = f"https://api.sofascore.com/api/v1/team/{ev_id}/vs/{dep_id}/events"
        res = requests.get(h2h_url, headers=headers, timeout=5)
        if res.status_code == 200:
            events = res.json().get("events", [])
            islenmis_maclar = []
            for evn in events[:10]:
                tarih_ts = evn.get("startTimestamp", 0)
                tarih = datetime.fromtimestamp(tarih_ts).strftime('%Y-%m-%d') if tarih_ts else "B
