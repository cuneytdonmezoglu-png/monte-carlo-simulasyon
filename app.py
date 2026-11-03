import streamlit as st
import requests
import numpy as np
import pandas as pd
import json
import os

st.set_page_config(page_title="Pro Monte Carlo & Skor Analiz Paneli", page_icon="⚽", layout="wide")

def _anahtar_oku(isim):
    try:
        if isim in st.secrets:
            return str(st.secrets[isim])
    except Exception:
        pass
    return os.environ.get(isim, "")

ODDS_API_KEY = _anahtar_oku("ODDS_API_KEY")
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

# Sofascore arama ve H2H kazıma motoru (Ücretsiz, sınırsız ve API kredisiz)
def sofascore_h2h_getir(ev_takim, dep_takim):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json"
    }
    try:
        # 1. Ev sahibi ID bul
        ev_arama = requests.get(f"https://api.sofascore.com/api/v1/search/teams?q={ev_id_temizle(ev_takim)}", headers=headers, timeout=5)
        ev_id = None
        if ev_arama.status_code == 200:
            teams = ev_arama.json().get("teams", [])
            if teams:
                ev_id = teams[0].get("id")

        # 2. Deplasman ID bul
        dep_arama = requests.get(f"https://api.sofascore.com/api/v1/search/teams?q={ev_id_temizle(dep_takim)}", headers=headers, timeout=5)
        dep_id = None
        if dep_arama.status_code == 200:
            teams = dep_arama.json().get("teams", [])
            if teams:
                dep_id = teams[0].get("id")

        if not (ev_id and dep_id):
            return [], "Takımlar Sofascore veritabanında eşleştirilemedi."

        # 3. Aralarındaki maçları (H2H) çek
        h2h_url = f"https://api.sofascore.com/api/v1/team/{ev_id}/vs/{dep_id}/events"
        res = requests.get(h2h_url, headers=headers, timeout=6)
        if res.status_code == 200:
            events = res.json().get("events", [])
            islenmis_maclar = []
            for evn in events[:10]: # Son 10 maç
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
        return [], f"Scraper bağlantı hatası: {str(e)}"
    
    return [], "Arşivde karşılıklı maç bulunamadı."

def ev_id_temizle(ad):
    for g in ["Torku", "Atiker", "Yukatel", "Bitexen", "Mondihome", "Oznur", "Kablo", "Rams", "Corendon", "SK", "FK", "Club", "FC", "BB"]:
        ad = ad.replace(g, "")
    return ad.strip()

# --- KONTROL PANELİ ---
st.sidebar.header("Kontrol Paneli")
if st.sidebar.button("Bulteni Yenile (Kredi Harcar)"):
    if os.path.exists(CACHE_FILE):
        try:
            os.remove(CACHE_FILE)
        except Exception:
            pass
    st.rerun()

if not ODDS_API_KEY:
    st.error("ODDS_API_KEY bulunamadı. st.secrets veya ortam değişkeni olarak ekleyin.")
    st.stop()

maclar, is_cached = tum_liglerin_verisini_getir()

if is_cached:
    st.sidebar.success("Yuklu Mac Sayisi: " + str(len(maclar)) + " (Kredi Harcanmiyor)")
else:
    st.sidebar.info("Taze Bulten Cekildi")

if not maclar or len(maclar) == 0:
    st.warning("Bulten verisi cekilemedi veya aktif mac bulunamadi.")
    st.stop()

# --- GÜVENLİ MAÇ SEÇİMİ ---
mac_secim_dict = {}

for idx, m in enumerate(maclar):
    if isinstance(m, dict) and "home_team" in m and "away_team" in m:
        home = str(m.get("home_team", "Ev"))
        away = str(m.get("away_team", "Dep"))
        sport = str(m.get("sport_title", "Futbol"))
        match_id = str(m.get("id", str(idx)))
        
        label = sport + ": " + home + " vs " + away + " [" + match_id[:6] + "]"
        mac_secim_dict[label] = m

if not mac_secim_dict:
    st.error("Onbellekteki mac verisinin bicimi uyumsuz.")
    st.stop()

secilen_str = st.selectbox("Simule Etmek Istedigin Maci Sec:", list(mac_secim_dict.keys()))
secilen_mac = mac_secim_dict[secilen_str]

ev = str(secilen_mac.get("home_team", "Ev"))
dep = str(secilen_mac.get("away_team", "Deplasman"))

# Oranları Çek
bookmakers = secilen_mac.get("bookmakers", [])
ev_o, ber_o, dep_o, buro_detaylari = [], [], [], []

if isinstance(bookmakers, list):
    for bm in bookmakers:
        if isinstance(bm, dict):
            b_name = str(bm.get("title", "Buro"))
            markets = bm.get("markets", [])
            if isinstance(markets, list):
                for mkt in markets:
                    if isinstance(mkt, dict) and str(mkt.get("key")) == "h2h":
                        outcomes = mkt.get("outcomes", [])
                        if isinstance(outcomes, list):
                            e_price, b_price, d_price = None, None, None
                            for out in outcomes:
                                if isinstance(out, dict):
                                    nm = str(out.get("name", ""))
                                    pr = out.get("price")
                                    if nm == ev: e_price = pr
                                    elif nm == "Draw": b_price = pr
                                    elif nm == dep: d_price = pr
                            
                            if e_price is not None and b_price is not None and d_price is not None:
                                try:
                                    ev_o.append(float(e_price))
                                    ber_o.append(float(b_price))
                                    dep_o.append(float(d_price))
                                    buro_detaylari.append({
                                        "Buro": b_
