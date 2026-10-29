import streamlit as st
import requests
import numpy as np
import pandas as pd
import json
import os
from datetime import datetime

st.set_page_config(page_title="Pro Monte Carlo Analytics Panel", page_icon="⚽", layout="wide")

API_KEY = "f6649c5150399729774787d9fac15cbb"
CACHE_FILE = "maclar_cache.json"

st.title("⚽ Profesyonel Futbol Monte Carlo & Value Bet Paneli")

LIGLER = [
    "soccer_turkey_super_league", "soccer_epl", "soccer_spain_la_liga",
    "soccer_italy_serie_a", "soccer_germany_bundesliga", "soccer_france_ligue_one",
    "soccer_uefa_champs_league", "soccer_uefa_europa_league"
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
        url = f'https://api.the-odds-api.com/v4/sports/{lig}/odds/?apiKey={API_KEY}&regions=eu&markets=h2h'
        try:
            res = requests.get(url)
            if res.status_code == 200:
                tum_maclar.extend(res.json())
        except:
            pass
        pbar.progress((idx + 1) / len(LIGLER))
    pbar.empty()

    if tum_maclar:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(tum_maclar, f, ensure_ascii=False, indent=4)
        return tum_maclar, False

    fallback_url = f'https://api.the-odds-api.com/v4/sports/soccer/odds/?apiKey={API_KEY}&regions=eu&markets=h2h'
    res = requests.get(fallback_url)
    return (res.json() if res.status_code == 200 else []), False

# --- SIDEBAR CONTROL ---
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
                ev_o.append(e); ber_o.append(b); dep_o.append(d)
                buro_detaylari.append({"Büro": b_name, "MS 1": e, "MS X": b, "MS 2": d})

avg_ev = np.mean(ev_o) if ev_o else 2.00
avg_ber = np.mean(ber_o) if ber_o else 3.20
avg_dep = np.mean(dep_o) if dep_o else 3.50

max_ev = max(ev_o) if ev_o else avg_ev
max_ber = max(ber_o) if ber_o else avg_ber
max_dep = max(dep_o) if dep_o else avg_dep

# MAÇ BAŞLIĞI VE ORAN METRİKLERİ
col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric(f"MS 1: {ev}", f"En Yüksek: {max_ev:.2f}", f"Ort: {avg_ev:.2f}")
col_m2.metric("MS X: Beraberlik", f"En Yüksek: {max_ber:.2f}", f"Ort: {avg_ber:.2f}")
col_m3.metric(f"MS 2: {dep}", f"En Yüksek: {max_dep:.2f}", f"Ort: {avg_dep:.2f}")

sim_sayisi = st.slider("Simülasyon Tekrar Sayısı:", 10000, 100000, 50000, step=10000)

if st.button("🚀 50.000 Maçlık Detaylı Simülasyonu Başlat", type="primary"):
    with st.spinner("Monte Carlo simülasyonu çalıştırılıyor..."):
        h_ev, h_ber, h_dep = 1/avg_ev, 1/avg_ber, 1/avg_dep
        toplam = h_ev + h_ber + h_dep
        p_ev, p_dep = h_ev/toplam, h_dep/toplam

        ev_xg = np.round(-np.log(1 - p_ev) * 1.35, 2)
        dep_xg = np.round(-np.log(1 - p_dep) * 1.10, 2)

        # Oynatımlar
        e_gol = np.random.poisson(ev_xg, sim_sayisi)
        d_gol = np.random.poisson(dep_xg, sim_sayisi)

        e_iy = np.random.poisson(ev_xg * 0.45, sim_sayisi)
        d_iy = np.random.poisson(dep_xg * 0.45, sim_sayisi)

        # Metrikler
        ms1 = np.sum(e_gol > d_gol) / sim_sayisi * 100
        msX = np.sum(e_gol == d_gol) / sim_sayisi * 100
        ms2 = np.sum(e_gol < d_gol) / sim_sayisi * 100

        fair_ms1 = 100 / ms1 if ms1 > 0 else 99
        fair_msX = 100 / msX if msX > 0 else 99
        fair_ms2 = 100 / ms2 if ms2 > 0 else 99

        iy1 = np.sum(e_iy > d_iy) / sim_sayisi * 100
        iyX = np.sum(e_iy == d_iy) / sim_sayisi * 100
        iy2 = np.sum(e_iy < d_iy) / sim_sayisi * 100

        toplam_gol = e_gol + d_gol
        ust15 = np.sum(toplam_gol > 1.5) / sim_sayisi * 100
        ust25 = np.sum(toplam_gol > 2.5) / sim_sayisi * 100
        ust35 = np.sum(toplam_gol > 3.5) / sim_sayisi * 100
        kg_var = np.sum((e_gol > 0) & (d_gol > 0)) / sim_sayisi * 100

        korner_lam = (ev_xg + dep_xg) * 3.1 + 2.5
        kart_lam = (ev_xg + dep_xg) * 1.2 + 2.0
        kornerler = np.random.poisson(korner_lam, sim_sayisi)
        kartlar = np.random.poisson(kart_lam, sim_sayisi)

        # --- SEKMELİ KAPSAMLI TASARIM ---
        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "📊 Maç Sonu & İY", 
            "⚽ Gol & KG & Skor", 
            "⛳ Korner & Kart", 
            "💎 Değerli Bahis (Value Bet)",
            "🌐 Yabancı Bürolar"
        ])

        with tab1:
            st.subheader("Maç Sonu ve İlk Yarı Dağılımları")
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
                st.bar_chart(df_iy.set_index("Seçenek")["Olasılık (%)"])
                st.dataframe(df_iy.style.format({"Olasılık (%)": "{:.1f}%", "Adil Oran": "{:.2f}"}))

        with tab2:
            st.subheader("Gol İstatistikleri & Skor Dağılımı")
            cg1, cg2 = st.columns(2)
            with cg1:
                st.write("### Alt / Üst Olasılıkları")
                st.metric("1.5 Gol Üst", f"%{ust15:.1f}", f"Adil Oran: {100/ust15:.2f}")
                st.metric("2.5 Gol Üst", f"%{ust25:.1f}", f"Adil Oran: {100/ust25:.2f}")
                st.metric("3.5 Gol Üst", f"%{ust35:.1f}", f"Adil Oran: {100/ust35:.2f}")
                st.metric("Karşılıklı Gol Var (KG)", f"%{kg_var:.1f}", f"Adil Oran: {100/kg_var:.2f}")

            with cg2:
                st.write("### 🎯 En Olası 5 Skor Tahmini")
                skorlar = [f"{e}-{d}" for e, d in zip(e_gol, d_gol)]
                s_series = pd.Series(skorlar).value_counts(normalize=True) * 100
                for skor, pct in s_series.head(5).items():
                    st.write(f"**Skor {skor}:** %{pct:.1f} (Adil Oran: `{100/pct:.2f}`)")

        with tab3:
            st.subheader("Korner ve Kart Tahminleri")
            ck1, ck2 = st.columns(2)
            with ck1:
                st.write("### Korner Beklentileri")
                st.metric("8.5 Korner Üst", f"%{np.sum(kornerler > 8.5)/sim_sayisi*100:.1f}")
                st.metric("9.5 Korner Üst", f"%{np.sum(kornerler > 9.5)/sim_sayisi*100:.1f}")
                st.metric("10.5 Korner Üst", f"%{np.sum(kornerler > 10.5)/sim_sayisi*100:.1f}")
            with ck2:
                st.write("### Kart Beklentileri")
                st.metric("3.5 Kart Üst", f"%{np.sum(kartlar > 3.5)/sim_sayisi*100:.1f}")
                st.metric("4.5 Kart Üst", f"%{np.sum(kartlar > 4.5)/sim_sayisi*100:.1f}")

        with tab4:
            st.subheader("💎 Değerli Bahis (Value Bet) Fırsatları")
            
            val_1 = max_ev > fair_ms1
            val_X = max_ber > fair_msX
            val_2 = max_dep > fair_ms2

            df_val = pd.DataFrame({
                "Seçenek": ["MS 1", "MS X", "MS 2"],
                "Simülasyon Adil Oranı": [f"{fair_ms1:.2f}", f"{fair_msX:.2f}", f"{fair_ms2:.2f}"],
                "Piyasa En Yüksek Oran": [f"{max_ev:.2f}", f"{max_ber:.2f}", f"{max_dep:.2f}"],
                "Value Durumu": [
                    "🔥 DEĞERLİ (Kasa Avantajı Var)" if val_1 else "Nötr",
                    "🔥 DEĞERLİ (Kasa Avantajı Var)" if val_X else "Nötr",
                    "🔥 DEĞERLİ (Kasa Avantajı Var)" if val_2 else "Nötr"
                ]
            })
            st.table(df_val)

        with tab5:
            st.subheader("🌐 Yabancı Büroların Canlı Oran Listesi")
            st.dataframe(pd.DataFrame(buro_detaylari))