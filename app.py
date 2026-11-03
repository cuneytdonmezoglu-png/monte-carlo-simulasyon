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

def takim_adi_duzenle(ad):
    degisiklikler = {
        "Gazişehir Gaziantep": "Gaziantep",
        "Kasimpasa SK": "Kasimpasa",
        "Galatasaray": "Galatasaray",
        "Fenerbahce": "Fenerbahce",
        "Besiktas": "Besiktas"
    }
    for k, v in degisiklikler.items():
        if k.lower() in ad.lower():
            return v
    for g in ["SK", "FK", "Club", "FC", "BB", "AS", "SS"]:
        ad = ad.replace(g, "")
    return ad.strip()

@st.cache_data(ttl=3600)
def sofascore_h2h_getir(ev_takim, dep_takim):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        ev_sorgu = takim_adi_duzenle(ev_takim)
        dep_sorgu = takim_adi_duzenle(dep_takim)

        ev_arama = requests.get(f"https://api.sofascore.com/api/v1/search/teams?q={ev_sorgu}", headers=headers, timeout=4)
        ev_id = None
        if ev_arama.status_code == 200:
            teams = ev_arama.json().get("teams", [])
            if teams:
                ev_id = teams[0].get("id")

        dep_arama = requests.get(f"https://api.sofascore.com/api/v1/search/teams?q={dep_sorgu}", headers=headers, timeout=4)
        dep_id = None
        if dep_arama.status_code == 200:
            teams = dep_arama.json().get("teams", [])
            if teams:
                dep_id = teams[0].get("id")

        if not (ev_id and dep_id):
            return [], f"Eşleştirme yapılamadı ({ev_sorgu} vs {dep_sorgu})."

        h2h_url = f"https://api.sofascore.com/api/v1/team/{ev_id}/vs/{dep_id}/events"
        res = requests.get(h2h_url, headers=headers, timeout=5)
        if res.status_code == 200:
            events = res.json().get("events", [])
            islenmis_maclar = []
            for evn in events[:10]:
                tarih_ts = evn.get("startTimestamp", 0)
                tarih = datetime.fromtimestamp(tarih_ts).strftime('%Y-%m-%d') if tarih_ts else "Bilinmiyor"
                turnuva = evn.get("tournament", {}).get("name", "Lig/Kupa")
                home_t = evn.get("homeTeam", {}).get("name", "Ev")
                away_t = evn.get("awayTeam", {}).get("name", "Dep")
                home_score = evn.get("homeScore", {}).get("current", 0)
                away_score = evn.get("awayScore", {}).get("current", 0)
                
                islenmis_maclar.append({
                    "Tarih": tarih,
                    "Lig": turnuva,
                    "Ev Sahibi": home_t,
                    "Skor": f"{home_score} - {away_score}",
                    "Deplasman": away_t
                })
            return islenmis_maclar, None
    except Exception as e:
        return [], f"Bağlantı hatası: {str(e)}"
    
    return [], "Arşivde karşılıklı maç bulunamadı."

# --- KONTROL PANELİ ---
st.sidebar.header("Kontrol Paneli")
if st.sidebar.button("Bulteni Yenile (Kredi Harcar)"):
