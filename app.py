import streamlit as st
import requests
import numpy as np
import pandas as pd
import json
import os
from datetime import datetime

st.set_page_config(page_title="Pro Monte Carlo & H2H Analytics Panel", page_icon="⚽", layout="wide")

ODDS_API_KEY = "f6649c5150399729774787d9fac15cbb"
RAPID_API_KEY = "0a912cbbe6msh15ad4f09e04d7a8p1c1967jsn3d1970aec964"
CACHE_FILE = "maclar_cache.json"

st.title("⚽ Profesyonel Futbol Monte Carlo, H2H & Kadro Analiz Paneli")

LIGLER = [
    "soccer_turkey_super_league", "soccer_turkey_cup",
    "soccer_epl", "soccer_fa_cup", "soccer_england_efl_cup",
    "soccer_spain_la_liga", "soccer_spain_copa_del_rey",
    "soccer_italy_serie_a", "soccer_italy_coppa_italia",
    "soccer_germany_bundesliga", "soccer_germany_dfb_pokal",
    "soccer_france_ligue_one",
    "soccer_uefa_champs_league", "soccer_uefa_europa_league", "soccer_uefa_europa_conference_league"
]

def tum_liglerin_verisini_getir():
    if os.path.exists(CACHE_FILE):
        dosya_tarihi = datetime.fromtimestamp(os.path.getmtime(CACHE_FILE)).date()
        if dosya_tarihi == datetime.now().date():
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f), True

    tum_maclar = []
    pbar = st.progress(0)
    for idx, lig in enumerate(LIGLER):
        url = f"https://api.the-odds-api.com/v4/sports/{lig}/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h"
        try:
            res = requests.get(url, timeout=5)
            if res.status_code == 200:
                tum_maclar.extend(res.json())
        except Exception:
            pass
        pbar.progress((idx + 1) / len(LIGLER))
    pbar.empty()

    if tum_maclar:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(tum_maclar, f, ensure_ascii=False, indent=4)
        return tum_maclar, False

    return [], False

def takim_id_bul(takim_adi, headers):
    gereksiz = ["Torku", "Atiker", "Yukatel", "Bitexen", "Mondihome", "Öznur Kablo", "Rams", "Corendon", "SK", "FK"]
    kelimeler = takim_adi.split()
    temiz_kelimeler = [k for k in kelimeler if k not in gereksiz]
    
    arama_listesi = [
        takim_adi,
        " ".join(temiz_kelimeler),
        temiz_kelimeler[-1] if temiz_kelimeler else takim_adi
    ]
    
    for sorgu in arama_listesi:
        if not sorgu:
            continue
        try:
            res = requests.get(f"https://api-football-v1.p.rapidapi.com/v3/teams?search={sorgu}", headers=headers, timeout=4)
            if res.status_code == 200:
                data = res.json().get("response", [])
                if data:
                    return data[0]["team"]["id"]
        except Exception:
            pass
    return None

# --- API-FOOTBALL OTOMATİK H2H BİLGİSİ ---
@st.cache_data(ttl=86400)
def h2h_ve_form_getir(ev_takim, dep_takim):
    headers = {
        "x-rapidapi-key": RAPID_API_KEY,
        "x-rapidapi-host": "api-football-v1.p.rapidapi.com"
    }
    try:
        ev_id = takim_id_bul(ev_takim, headers)
        dep_id = takim_id_bul(dep_takim, headers)
        
        if ev_id and dep_id:
            h2h_url = f"https://api-football-v1.p.rapidapi.com/v3/fixtures/headtohead?h2h={ev_id}-{dep_id}"
            res_h2h = requests.get(h2h_url, headers=headers, timeout=5)
            if res_h2h.status_code == 200:
                d = res_h2h.json().get("response", [])
                return d[:10]
    except Exception:
        pass
    return []

# --- KONTROL PANELİ ---
