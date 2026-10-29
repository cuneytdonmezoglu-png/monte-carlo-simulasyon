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
        url = f"https://api.the-odds-api.com/v4/sports/{lig}/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h"
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
                return res_h2h.json().get("response", [])[:10]
    except Exception:
        pass
    return []

# --- KONTROL PANELİ ---
st.sidebar.header("Kontrol Paneli")
if st.sidebar.button("Bülteni Yenile"):
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    st.rerun()

maclar, is_cached = tum_liglerin_verisini_getir()

if is_cached:
    st.sidebar.success(f"Yuklu Mac Sayisi: {len(maclar)} (Kredi Harcanmiyor)")
else:
    st.sidebar.info("Taze Bulten Cekildi")

if not maclar or len(maclar) == 0:
    st.error("Bulten verisi cekilemedi veya aktif mac bulunamadi.")
    st.stop()

# --- GÜVENLİ MAÇ SEÇİMİ ---
gecerli_maclar = []
mac_listesi = []

for idx, m in enumerate(maclar):
    if isinstance(m, dict) and "home_team" in m and "away_team" in m:
        home = m.get("home_team", "Ev")
        away = m.get("away_team", "Dep")
        sport = m.get("sport_title", "Futbol")
        mac_listesi.append(f"{sport}: {home} vs {away}")
        gecerli_maclar.append(m)

if not gecerli_maclar:
    st.error("Önbellekteki maç verisinin biçimi uyumsuz.")
    st.stop()

secilen_str = st.selectbox("Simule Etmek Istedigin Maci Sec:", mac_listesi)
secilen_mac = gecerli_maclar[mac_listesi.index(secilen_str)]

ev = secilen_mac.get("home_team", "Ev")
dep = secilen_mac.get("away_team", "Deplasman")

# Oranları Çek
bookmakers = secilen_mac.get("bookmakers", [])
ev_o, ber_o, dep_o, buro_detaylari = [], [], [], []

if isinstance(bookmakers, list):
    for bm in bookmakers:
        if isinstance(bm, dict):
            b_name = bm.get("title", "Buro")
            for mkt in bm.get("markets", []):
                if isinstance(mkt, dict) and mkt.get("key") == "h2h":
                    outcomes = mkt.get("outcomes", [])
                    e = next((i["price"] for i in outcomes if isinstance(i, dict) and i.get("name") == ev), None)
                    b = next((i["price"] for i in outcomes if isinstance(i, dict) and i.get("name") == "Draw"), None)
                    d = next((i["price"] for i in outcomes if isinstance(i, dict) and i.get("name") == dep), None)
                    if e and b and d:
                        ev_o.append(e)
                        ber_o.append(b)
                        dep_o.append(d)
                        buro_detaylari.append({"Buro": b_name, "MS 1": e, "MS X": b, "MS 2": d})

avg_ev = np.mean(ev_o) if ev_o else 2.00
avg_ber = np.mean(ber_o) if ber_o else 3.20
avg_dep = np.mean(dep_o) if dep_o else 3.50

max_ev = max(ev_o) if ev_o else avg_ev
max_ber = max(ber_o) if ber_o else avg_ber
max_dep = max(dep_o) if dep_o else avg_dep

# METRİKLER
st.markdown("---")
col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric(f"MS 1: {ev}", f"En Yuksek: {max_ev:.2f}", f"Ort: {avg_ev:.2f}")
col_m2.metric("MS X: Beraberlik", f"En Yuksek: {max_ber:.2f}", f"Ort: {avg_ber:.2f}")
col_m3.metric(f"MS 2: {dep}", f"En Yuksek: {max_dep:.2f}", f"Ort: {avg_dep:.2f}")
st.markdown("---")

# PARAMETRELER
st.sidebar.markdown("---")
st.sidebar.header("Kadro & H2H Ince Ayarlari")
h2h_weight = st.sidebar.slider("H2H / Gecmis Mac Agirlik Carpani", -30, 30, 0)
ev_eksik = st.sidebar.slider(f"{ev} Sakat/Eksik Oyuncu Etkisi (%)", 0, 40, 0, step=5)
dep_eksik = st.sidebar.slider(f"{dep} Sakat/Eksik Oyuncu Etkisi (%)", 0, 40, 0, step=5)

sim_sayisi = st.slider("Simulasyon Tekrar Sayisi:", 10000, 100000, 50000, step=10000)

if st.button("Detayli Gelismis Simulasyonu Calistir", type="primary"):
    with st.spinner("H2H Arsiv Verileri ve Monte Carlo Hesaplamasi Yapiliyor..."):
        h2h_gecmis = h2h_ve_form_getir(ev, dep)
        
        h_ev, h_ber, h_dep = 1/avg_ev, 1/avg_ber, 1/avg_dep
        toplam_oran = h_ev + h_ber + h_dep
        p_ev, p_dep = h_ev/toplam_oran, h_dep/toplam_oran

        base_ev_xg = -np.log(1 - p_ev) * 1.35
        base_dep_xg = -np.log(1 - p_dep) * 1.10

        ev_xg = max(0.2, np.round(base_ev_xg * (1 + (h2h_weight / 100)) * (1 - (ev_eksik / 100)), 2))
        dep_xg = max(0.2, np.round(base_dep_xg * (1 - (h2h_weight / 100)) * (1 - (dep_eksik / 100)), 2))

        e_gol = np.random.poisson(ev_xg, sim_sayisi)
        d_gol = np.random.poisson(dep_xg, sim_sayisi)

        e_iy = np.random.poisson(ev_xg * 0.43, sim_sayisi)
        d_iy = np.random.poisson(dep_xg * 0.43, sim_sayisi)

        dilim_xg = (ev_xg + dep_xg) / 6
        d_0_15 = np.random.poisson(dilim_xg, sim_sayisi)
        d_15_30 = np.random.poisson(dilim_xg, sim_sayisi)
        d_30_45 = np.random.poisson(dilim_xg * 1.1, sim_sayisi)
        d_45_60 = np.random.poisson(dilim_xg, sim_sayisi)
        d_60_75 = np.random.poisson(dilim_xg * 1.2, sim_sayisi)
        d_75_90 = np.random.poisson(dilim_xg * 1.3, sim_sayisi)

        ms1 = np.sum(e_gol > d_gol) / sim_sayisi * 100
        msX = np.sum(e_gol == d_gol) / sim_sayisi * 100
        ms2 = np.sum(e_gol < d_gol) / sim_sayisi * 100

        fair_ms1 = 100 / ms1 if ms1 > 0 else 99
        fair_msX = 100 / msX if msX > 0 else 99
        fair_ms2 = 100 / ms2 if ms2 > 0 else 99

        iy1 = np.sum(e_iy > d_iy) / sim_sayisi * 100
        iyX = np.sum(e_iy == d_iy) / sim_sayisi * 100
        iy2 = np.sum(e_iy < d_iy) / sim_sayisi * 100

        iy_gol_var = np.sum((e_iy + d_iy) > 0.5) / sim_sayisi * 100
        toplam_gol = e_gol + d_gol
        ust25 = np.sum(toplam_gol > 2.5) / sim_sayisi * 100

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "Mac Sonu & IY",
            "Gol Dakikalari & IY Gol",
            "Gecmis H2H Maclari",
            "Value Bet & Kadro",
            "Yabanci Burolar"
        ])

        with tab1:
            st.subheader("Mac Sonu ve Ilk Yari Dagilimlari")
            st.info(f"Modifiye Gol Beklentileri (xG) -> {ev}: {ev_xg:.2f} | {dep}: {dep_xg:.2f}")
            c1, c2 = st.columns(2)
            with c1:
                st.write("### Mac Sonucu (MS)")
                df_ms = pd.DataFrame({
                    "Secenek": ["MS 1", "MS X", "MS 2"],
                    "Olasilik (%)": [ms1, msX, ms2],
                    "Adil Oran": [fair_ms1, fair_msX, fair_ms2]
                })
                st.dataframe(df_ms.style.format({"Olasilik (%)": "{:.1f}%", "Adil Oran": "{:.2f}"}))

            with c2:
                st.write("### Ilk Yari Sonucu (IY)")
                df_iy = pd.DataFrame({
                    "Secenek": ["IY 1", "IY X", "IY 2"],
                    "Olasilik (%)": [iy1, iyX, iy2],
                    "Adil Oran": [100/iy1, 100/iyX, 100/iy2]
                })
                st.dataframe(df_iy.style.format({"Olasilik (%)": "{:.1f}%", "Adil Oran": "{:.2f}"}))

        with tab2:
            st.subheader("Zaman Dilimlerine Gore Gol Olasiliklari")
            col_z1, col_z2 = st.columns(2)
            with col_z1:
                st.metric("Ilk Yari 0.5 Gol Ust", f"%{iy_gol_var:.1f}", f"Adil Oran: {100/iy_gol_var:.2f}")
                st.metric("Mac Geneli 2.5 Gol Ust", f"%{ust25:.1f}", f"Adil Oran: {100/ust25:.2f}")

            with col_z2:
                df_dilim = pd.DataFrame({
                    "Zaman Araligi": ["0-15 dk", "15-30 dk", "30-45+ dk", "45-60 dk", "60-75 dk", "75-90+ dk"],
                    "Gol Olasiligi (%)": [
                        np.sum(d_0_15 > 0)/sim_sayisi*100,
                        np.sum(d_15_30 > 0)/sim_sayisi*100,
                        np.sum(d_30_45 > 0)/sim_sayisi*100,
                        np.sum(d_45_60 > 0)/sim_sayisi*100,
                        np.sum(d_60_75 > 0)/sim_sayisi*100,
                        np.sum(d_75_90 > 0)/sim_sayisi*100
                    ]
                })
                st.dataframe(df_dilim.style.format({"Gol Olasiligi (%)": "{:.1f}%"}))

        with tab3:
            st.subheader("Iki Takim Arasindaki Son H2H Maclar (API-Football)")
            if h2h_gecmis:
                h2h_list = []
                for m in h2h_gecmis:
                    if isinstance(m, dict):
                        tarih = m.get("fixture", {}).get("date", "")[:10]
                        teams = m.get("teams", {})
                        ev_t = teams.get("home", {}).get("name", "Ev")
                        dep_t = teams.get("away", {}).get("name", "Dep")
                        goals = m.get("goals", {})
                        ev_g = goals.get("home", 0)
                        dep_g = goals.get("away", 0)
                        skor = f"{ev_g} - {dep_g}"
                        h2h_list.append({"Tarih": tarih, "Ev Sahibi": ev_t, "Skor": skor, "Deplasman": dep_t})
                st.table(pd.DataFrame(h2h_list))
            else:
                st.warning("API uzerinde dogrudan eslesen otomatik H2H kaydi bulunamadi. Sol paneldeki H2H slider'ini kullanabilirsiniz.")

        with tab4:
            st.subheader("Degerli Bahis (Value Bet) Firsatlari")
            val_1 = max_ev > fair_ms1
            val_X = max_ber > fair_msX
            val_2 = max_dep > fair_ms2

            df_val = pd.DataFrame({
                "Secenek": ["MS 1", "MS X", "MS 2"],
                "Simulasyon Adil Orani": [f"{fair_ms1:.2f}", f"{fair_msX:.2f}", f"{fair_ms2:.2f}"],
                "Piyasa En Yuksek Oran": [f"{max_ev:.2f}", f"{max_ber:.2f}", f"{max_dep:.2f}"],
                "Value Durumu": [
                    "DEGERLI" if val_1 else "Notr",
                    "DEGERLI" if val_X else "Notr",
                    "DEGERLI" if val_2 else "Notr"
                ]
            })
            st.table(df_val)

        with tab5:
            st.subheader("Yabanci Burolarin Canlı Oran Listesi")
            if buro_detaylari:
                st.dataframe(pd.DataFrame(buro_detaylari))
            else:
                st.info("Buro detayi bulunamadi.")
