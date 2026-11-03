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
    # Özel isim temizleme ve eşleştirme kısayolları
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
                                        "Buro": b_name, 
                                        "MS 1": float(e_price), 
                                        "MS X": float(b_price), 
                                        "MS 2": float(d_price)
                                    })
                                except Exception:
                                    pass

avg_ev = float(np.mean(ev_o)) if len(ev_o) > 0 else 2.10
avg_ber = float(np.mean(ber_o)) if len(ber_o) > 0 else 3.20
avg_dep = float(np.mean(dep_o)) if len(dep_o) > 0 else 3.10

max_ev = float(max(ev_o)) if len(ev_o) > 0 else avg_ev
max_ber = float(max(ber_o)) if len(ber_o) > 0 else avg_ber
max_dep = float(max(dep_o)) if len(dep_o) > 0 else avg_dep

# METRİKLER
st.markdown("---")
col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric("MS 1: " + ev, "En Yuksek: " + f"{max_ev:.2f}", "Ort: " + f"{avg_ev:.2f}")
col_m2.metric("MS X: Beraberlik", "En Yuksek: " + f"{max_ber:.2f}", "Ort: " + f"{avg_ber:.2f}")
col_m3.metric("MS 2: " + dep, "En Yuksek: " + f"{max_dep:.2f}", "Ort: " + f"{avg_dep:.2f}")
st.markdown("---")

# PARAMETRELER
st.sidebar.markdown("---")
st.sidebar.header("Kadro & H2H Ince Ayarlari")
h2h_weight = st.sidebar.slider("H2H / Gecmis Mac Agirlik Carpani", -30, 30, 0)
ev_eksik = st.sidebar.slider(ev + " Sakat/Eksik Oyuncu Etkisi (%)", 0, 40, 0, step=5)
dep_eksik = st.sidebar.slider(dep + " Sakat/Eksik Oyuncu Etkisi (%)", 0, 40, 0, step=5)

sim_sayisi = st.slider("Simulasyon Tekrar Sayisi:", 10000, 100000, 50000, step=10000)

# OTOMATİK HESAPLAMA
h2h_gecmis, h2h_hata = sofascore_h2h_getir(ev, dep)

safe_avg_ev = avg_ev if avg_ev > 0 else 2.10
safe_avg_ber = avg_ber if avg_ber > 0 else 3.20
safe_avg_dep = avg_dep if avg_dep > 0 else 3.10

h_ev = 1.0 / safe_avg_ev
h_ber = 1.0 / safe_avg_ber
h_dep = 1.0 / safe_avg_dep
toplam_oran = h_ev + h_ber + h_dep

p_ev = h_ev / toplam_oran
p_dep = h_dep / toplam_oran

p_ev = min(0.99, max(0.01, p_ev))
p_dep = min(0.99, max(0.01, p_dep))

base_ev_xg = -np.log(1.0 - p_ev) * 1.35
base_dep_xg = -np.log(1.0 - p_dep) * 1.10

ev_xg = max(0.2, np.round(base_ev_xg * (1.0 + (h2h_weight / 100.0)) * (1.0 - (ev_eksik / 100.0)), 2))
dep_xg = max(0.2, np.round(base_dep_xg * (1.0 - (h2h_weight / 100.0)) * (1.0 - (dep_eksik / 100.0)), 2))

e_gol = np.random.poisson(ev_xg, sim_sayisi)
d_gol = np.random.poisson(dep_xg, sim_sayisi)

e_iy = np.random.poisson(ev_xg * 0.43, sim_sayisi)
d_iy = np.random.poisson(dep_xg * 0.43, sim_sayisi)

skor_sayaclari = {}
for eg, dg in zip(e_gol, d_gol):
    skor_str = f"{eg} - {dg}"
    skor_sayaclari[skor_str] = skor_sayaclari.get(skor_str, 0) + 1

sirali_skorlar = sorted(skor_sayaclari.
