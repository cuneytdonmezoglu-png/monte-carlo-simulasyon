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
CSV_CACHE_DIR = "football_data_cache"

if not os.path.exists(CSV_CACHE_DIR):
    os.makedirs(CSV_CACHE_DIR)

st.title("⚽ Gerçek Monte Carlo & Bağımsız Skor Değer Motoru")

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

FOOTBALL_DATA_URLS = {
    "Süper Lig": "https://www.football-data.co.uk/mmz4281/2425/T1.csv",
    "Premier League": "https://www.football-data.co.uk/mmz4281/2425/E0.csv",
    "La Liga": "https://www.football-data.co.uk/mmz4281/2425/SP1.csv",
    "Serie A": "https://www.football-data.co.uk/mmz4281/2425/I1.csv",
    "Bundesliga": "https://www.football-data.co.uk/mmz4281/2425/D1.csv",
    "Ligue 1": "https://www.football-data.co.uk/mmz4281/2425/F1.csv"
}

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

@st.cache_data(ttl=86400)
def football_data_arsif_cek(lig_adi):
    if lig_adi not in FOOTBALL_DATA_URLS:
        return pd.DataFrame()
    csv_yolu = os.path.join(CSV_CACHE_DIR, f"{lig_adi}.csv")
    if not os.path.exists(csv_yolu) or (datetime.now().timestamp() - os.path.getmtime(csv_yolu) > 86400):
        try:
            url = FOOTBALL_DATA_URLS[lig_adi]
            res = requests.get(url, timeout=10)
            if res.status_code == 20
