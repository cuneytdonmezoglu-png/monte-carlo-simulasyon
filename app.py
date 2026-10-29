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
        url = f'https://api.the-odds-api.com/v4/sports/{lig}/odds/?apiKey={ODDS_API_KEY}&regions=eu&markets=h2h'
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

# --- API-FOOTBALL OTOMATİK H2H BİLGİSİ ---
@st.cache_data(ttl=86400)
def h2h_ve_form_getir(ev_takim, dep_takim):
    headers = {
        "x-rapidapi-key": RAPID_API_KEY,
        "x-rapidapi-host": "api-football-v1.p.rapidapi.com"
    }
    try:
        res_ev = requests.get(f"https://api-football-v1.p.rapidapi.com/v3/teams?search={ev_takim}", headers=headers, timeout=5)
        res_dep = requests.get(f"https://api-football-v1.p.rapidapi.com/v3/teams?search={dep_takim}", headers=headers, timeout=5)
        
        if res_ev.status_code == 200 and res_dep.status_code == 200:
            d_ev = res_ev.json().get('response', [])
            d_dep = res_dep.json().get('response', [])
            
            if d_ev and d_dep:
                ev_id = d_ev[0]['team']['id']
                dep_id = d_dep[0]['team']['id']
                
                h2h_url = f"https://api-football-v1.p.rapidapi.com/v3/fixtures/headtohead?h2h={ev_id}-{dep_id}"
                res_h2h = requests.get(h2h_url, headers=headers, timeout=5)
                
                if res_h2h.status_code == 200:
                    h2h_data = res_h2h.json().get('response', [])
                    return h2h_data[:10]
    except Exception:
        pass
    return []

# --- CONTROL PANEL ---
st.sidebar.header("🕹️ Kontrol Paneli")
if st.sidebar.button("🔄 Bülteni Yenile (1 Kredi)"):
    if os.path.exists(CACHE_FILE):
        os.remove(CACHE_FILE)
    st.rerun()

maclar, is_cached = tum_liglerin_verisini_getir()

if is_cached:
    st.sidebar.success(f"🛡️ Yüklü Maç Sayısı: {len(maclar)} (Kredi Harcanmıyor)")
else:
    st.sidebar.info("🌐 Taze Bülten Çekildi")

if not maclar:
    st.warning("Aktif maç verisi bulunamadı.")
    st.stop()

# --- MAÇ SEÇİMİ ---
mac_listesi = [f"{m.get('sport_title', 'Futbol')}: {m['home_team']} vs {m['away_team']}" for m in maclar]
secilen_str = st.selectbox("📌 Simüle Etmek İstediğin Maçı Seç:", mac_listesi)
secilen_mac = maclar[mac_listesi.index(secilen_str)]

ev, dep = secilen_mac['home_team'], secilen_mac['away_team']

# Oran Verilerini Derleme
bookmakers = secilen_mac.get('bookmakers', [])
ev_o, ber_o, dep_o, buro_detaylari = [], [], [], []

for bm in bookmakers:
    b_name = bm['title']
    for mkt in bm['markets']:
        if mkt['key'] == 'h2h':
            e = next((i['price'] for i in mkt['outcomes'] if i['name'] == ev), None)
            b = next((i['price'] for i in mkt['outcomes'] if i['name'] == 'Draw'), None)
            d = next((i['price'] for i in mkt['outcomes'] if i['name'] == dep), None)
            if e and b and d:
                ev_o.append(e); ber_o.append(b); dep_o.append(d)
                buro_detaylari.append({"Büro": b_name, "MS 1": e, "MS X": b, "MS 2": d})

avg_ev = np.mean(ev_o) if ev_o else 2.00
avg_ber = np.mean(ber_o) if ber_o else 3.20
avg_dep = np.mean(dep_o) if dep_o else 3.50

max_ev = max(ev_o) if ev_o else avg_ev
max_ber = max(ber_o) if ber_o else avg_ber
max_dep = max(dep_o) if dep_o else avg_dep

# --- SAKATLIK & H2H DİNAMİK PARAMETRELERİ ---
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Kadro & H2H İnce Ayarları")
h2h_weight = st.sidebar.slider("H2H / Geçmiş Maç Ağırlık Çarpanı", -30, 30, 0, help="Geçmiş H2H üstünlüğünü simülasyona manuel ekler/çıkarır.")
ev_eksik = st.sidebar.slider(f"{ev} Sakat/Eksik Oyuncu Etkisi (%)", 0, 40, 0, step=5)
dep_eksik = st.sidebar.slider(f"{dep} Sakat/Eksik Oyuncu Etkisi (%)", 0, 40, 0, step=5)

sim_sayisi = st.slider("Simülasyon Tekrar Sayısı:", 10000, 100000, 50000, step=10000)

if st.button("🚀 Detaylı Gelişmiş Simülasyonu Çalıştır", type="primary"):
    with st.spinner("H2H Arşiv Verileri ve Dakika Bazlı Monte Carlo Hesaplaması Yapılıyor..."):
        h2h_gecmis = h2h_ve_form_getir(ev, dep)
        
        h_ev, h_ber, h_dep = 1/avg_ev, 1/avg_ber, 1/avg_dep
        toplam = h_ev + h_ber + h_dep
        p_ev, p_dep = h_ev/toplam, h_dep/toplam

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
            "📊 Maç Sonu & İY",
            "⏱️ Gol Dakikaları & İY Gol",
            "📜 Geçmiş H2H Maçları",
            "💎 Value Bet & Kadro",
            "🌐 Yabancı Bürolar"
        ])

        with tab1:
            st.subheader("Maç Sonu ve İlk Yarı Dağılımları")
            st.info(f"💡 Modifiye Gol Beklentileri (xG) -> **{ev}:** `{ev_xg:.2f}` | **{dep}:** `{dep_xg:.2f}`")
            c1, c2 = st.columns(2)
            with c1:
                st.write("### Maç Sonucu (MS)")
                df_ms = pd.DataFrame({
                    "Seçenek": ["MS 1", "MS X", "MS 2"],
                    "Olasılık (%)": [ms1, msX, ms2],
                    "Adil Oran": [fair_ms1, fair_msX, fair_ms2]
                })
                st.bar_chart(df_ms.set_index("Seçenek")["Olasılık (%)"])
                st.dataframe(df_ms.style.format({"Olasılık (%)": "{:.1f}%", "Adil Oran": "{:.2f}"}))

            with c2:
                st.write("### İlk Yarı Sonucu (İY)")
                df_iy = pd.DataFrame({
                    "Seçenek": ["İY 1", "İY X", "İY 2"],
                    "Olasılık (%)": [iy1, iyX, iy2],
                    "Adil Oran": [100/iy1, 100/iyX, 100/iy2]
                })
                st.bar_chart(df_iy.set_index
