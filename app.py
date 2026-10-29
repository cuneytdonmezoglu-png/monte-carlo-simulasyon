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

def takim_id_bul(takim_adi, headers):
    # 1. Aşama: Temizlik
    gereksiz = ["Torku", "Atiker", "Yukatel", "Bitexen", "Mondihome", "Öznur Kablo", "Rams", "Corendon", "SK", "FK"]
    kelimeler = takim_adi.split()
    temiz_kelimeler = [k for k in kelimeler if k not in gereksiz]
    
    arama_listesi = [
        takim_adi,                             # Tam isim
        " ".join(temiz_kelimeler),             # Temizlenmiş isim
        temiz_kelimeler[-1] if temiz_kelimeler else takim_adi  # En ana kelime (Örn: Konyaspor)
    ]
    
    for sorgu in arama_listesi:
        if not sorgu:
            continue
        try:
            res = requests.get(f"https://api-football-v1.p.rapidapi.com/v3/teams?search={sorgu}", headers=headers, timeout=4)
            if res.status_code == 200:
                data = res.json().get('response', [])
                if data:
                    return data[0]['team']['id']
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
                return res_h2h.json().get('response', [])[:10]
    except Exception:
        pass
    return []

# --- KONTROL PANELİ ---
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

# Oranları Çek
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
                ev_o.append(e)
                ber_o.append(b)
                dep_o.append(d)
                buro_detaylari.append({"Büro": b_name, "MS 1": e, "MS X": b, "MS 2": d})

avg_ev = np.mean(ev_o) if ev_o else 2.00
avg_ber = np.mean(ber_o) if ber_o else 3.20
avg_dep = np.mean(dep_o) if dep_o else 3.50

max_ev = max(ev_o) if ev_o else avg_ev
max_ber = max(ber_o) if ber_o else avg_ber
max_dep = max(dep_o) if dep_o else avg_dep

# METRİKLER
st.markdown("---")
col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric(f"MS 1: {ev}", f"En Yüksek: {max_ev:.2f}", f"Ort: {avg_ev:.2f}")
col_m2.metric("MS X: Beraberlik", f"En Yüksek: {max_ber:.2f}", f"Ort: {avg_ber:.2f}")
col_m3.metric(f"MS 2: {dep}", f"En Yüksek: {max_dep:.2f}", f"Ort: {avg_dep:.2f}")
st.markdown("---")

# PARAMETRELER
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Kadro & H2H İnce Ayarları")
h2h_weight = st.sidebar.slider("H2H / Geçmiş Maç Ağırlık Çarpanı", -30, 30, 0)
ev_eksik = st.sidebar.slider(f"{ev} Sakat/Eksik Oyuncu Etkisi (%)", 0, 40, 0, step=5)
dep_eksik = st.sidebar.slider(f"{dep} Sakat/Eksik Oyuncu Etkisi (%)", 0, 40, 0, step=5)

sim_sayisi = st.slider("Simülasyon Tekrar Sayısı:", 10000, 100000, 50000, step=10000)

if st.button("🚀 Detaylı Gelişmiş Simülasyonu Çalıştır", type="primary"):
    with st.spinner("H2H Arşiv Verileri ve Dakika Bazlı Monte Carlo Hesaplaması Yapılıyor..."):
        h2h_gecmis = h2h_ve_form_getir(ev, dep)
        
        h_ev, h_ber, h_dep = 1/avg_ev, 1/avg_ber, 1/avg_dep
        toplam = h_ev + h_ber + h_dep
        p_ev, p_dep = h_ev/top
