import streamlit as st
import requests
import numpy as np
import pandas as pd
import json
import os
from datetime import datetime

st.set_page_config(page_title="Pro Monte Carlo Analytics", page_icon="⚽", layout="wide")

ODDS_API_KEY = "f6649c5150399729774787d9fac15cbb"
RAPID_API_KEY = "0a912cbbe6msh15ad4f09e04d7a8p1c1967jsn3d1970aec964"
CACHE_FILE = "maclar_cache.json"

st.title("⚽ Profesyonel Futbol Monte Carlo, H2H & Kadro Analiz Paneli")

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

def metni_temizle(metin):
    if not isinstance(metin, str):
        return "", []
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ", "cgiosuCGIOSU")
    temiz = metin.translate(tr_map)
    gereksiz = ["Torku", "Atiker", "Yukatel", "Bitexen", "Mondihome", "Oznur", "Kablo", "Rams", "Corendon", "SK", "FK", "Club", "FC", "BB"]
    kelimeler = [k for k in temiz.split() if k not in gereksiz]
    sade = " ".join(kelimeler)
    return sade, kelimeler

def takim_id_bul(takim_adi, headers):
    temiz_metin, kelimeler = metni_temizle(takim_adi)
    arama_listesi = []
    if temiz_metin:
        arama_listesi.append(temiz_metin)
    if kelimeler:
        arama_listesi.append(kelimeler[-1])
        arama_listesi.append(kelimeler[0])
    arama_listesi.append(str(takim_adi))
    
    benzersiz_sorgular = list(dict.fromkeys([s.strip() for s in arama_listesi if len(s.strip()) > 2]))

    for sorgu in benzersiz_sorgular:
        try:
            url = "https://api-football-v1.p.rapidapi.com/v3/teams?search=" + sorgu
            res = requests.get(url, headers=headers, timeout=4)
            if res.status_code == 200:
                data = res.json().get("response", [])
                if data and isinstance(data, list) and len(data) > 0:
                    return data[0]["team"]["id"]
        except Exception:
            pass
    return None

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
            h2h_url = "https://api-football-v1.p.rapidapi.com/v3/fixtures/headtohead?h2h=" + str(ev_id) + "-" + str(dep_id)
            res_h2h = requests.get(h2h_url, headers=headers, timeout=5)
            if res_h2h.status_code == 200:
                return res_h2h.json().get("response", [])[:10]
    except Exception:
        pass
    return []

# --- KONTROL PANELİ ---
st.sidebar.header("Kontrol Paneli")
if st.sidebar.button("Bulteni Yenile"):
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
        except Exception:
            pass
    st.rerun()

maclar, is_cached = tum_liglerin_verisini_getir()

if is_cached:
    st.sidebar.success("Yuklu Mac Sayisi: " + str(len(maclar)) + " (Kredi Harcanmiyor)")
else:
    st.sidebar.info("Taze Bulten Cekildi")

if not maclar or len(maclar) == 0:
    st.error("Bulten verisi cekilemedi veya aktif mac bulunamadi.")
    st.stop()

# --- MAÇ SEÇİMİ ---
gecerli_maclar = []
mac_listesi = []

for m in maclar:
    if isinstance(m, dict) and "home_team" in m and "away_team" in m:
        home = m.get("home_team", "Ev")
        away = m.get("away_team", "Dep")
        sport = m.get("sport_title", "Futbol")
        mac_listesi.append(str(sport) + ": " + str(home) + " vs " + str(away))
        gecerli_maclar.append(m)

if not gecerli_maclar:
    st.error("Onbellekteki mac verisinin bicimi uyumsuz.")
    st.stop()

secilen_str = st.selectbox("Simule Etmek Istedigin Maci Sec:", mac_listesi)
secilen_mac = gecerli_maclar[mac_listesi.index(secilen_str)]

ev = str(secilen_mac.get("home_team", "Ev"))
dep = str(secilen_mac.get("away_team", "Deplasman"))

# Oranları Çek
bookmakers = secilen_mac.get("bookmakers", [])
ev_o, ber_o, dep_o, buro_detaylari = [], [], [], []

if isinstance(bookmakers, list):
    for bm in bookmakers:
        if isinstance(bm, dict):
            b_name = bm.get("title", "Buro")
            for mkt in bm.get("markets", []):
                if isinstance(mkt
