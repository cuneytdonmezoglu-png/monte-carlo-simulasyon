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
            if res.status_code == 200:
                with open(csv_yolu, "w", encoding="utf-8") as f:
                    f.write(res.text)
        except Exception:
            pass

    if os.path.exists(csv_yolu):
        try:
            return pd.read_csv(csv_yolu)
        except Exception:
            pass
    return pd.DataFrame()

def h2h_bul_football_data(ev, dep, spor_adi):
    hedef_lig = None
    if "Turkey" in spor_adi or "Super Lig" in spor_adi:
        hedef_lig = "Süper Lig"
    elif "EPL" in spor_adi or "Soccer_epl" in spor_adi:
        hedef_lig = "Premier League"
    elif "Spain" in spor_adi:
        hedef_lig = "La Liga"
    elif "Italy" in spor_adi:
        hedef_lig = "Serie A"
    elif "Germany" in spor_adi:
        hedef_lig = "Bundesliga"
    elif "France" in spor_adi:
        hedef_lig = "Ligue 1"
        
    if not hedef_lig:
        return []

    df = football_data_arsif_cek(hedef_lig)
    if df.empty:
        return []

    required_cols = {"HomeTeam", "AwayTeam", "FTHG", "FTAG"}
    if not required_cols.issubset(df.columns):
        return []

    ev_temiz = ev.lower().replace("sk", "").replace("fk", "").strip()
    dep_temiz = dep.lower().replace("sk", "").replace("fk", "").strip()

    maclar = []
    for _, row in df.iterrows():
        h_team = str(row["HomeTeam"]).lower()
        a_team = str(row["AwayTeam"]).lower()
        
        matches_home = (ev_temiz in h_team or h_team in ev_temiz) and (dep_temiz in a_team or a_team in dep_temiz)
        matches_away = (dep_temiz in h_team or h_team in dep_temiz) and (ev_temiz in a_team or a_team in ev_temiz)
        
        if matches_home or matches_away:
            maclar.append({
                "Tarih": str(row.get("Date", "Bilinmiyor")),
                "Lig": hedef_lig,
                "Ev Sahibi": row["HomeTeam"],
                "Skor": f"{int(row['FTHG'])} - {int(row['FTAG'])}",
                "Deplasman": row["AwayTeam"]
            })
    return maclar[:10]

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

mac_secim_dict = {}
for idx, m in enumerate(maclar):
    if isinstance(m, dict) and "home_team" in m and "away_team" in m:
        home = str(m.get("home_team", "Ev"))
        away = str(m.get("away_team", "Dep"))
        sport = str(m.get("sport_title", "Futbol"))
        match_id = str(m.get("id", str(idx)))
        label = sport + ": " + home + " vs " + away + " [" + match_id[:6] + "]"
        mac_secim_dict[label] = m

secilen_str = st.selectbox("Simule Etmek Istedigin Maci Sec:", list(mac_secim_dict.keys()))
secilen_mac = mac_secim_dict[secilen_str]

ev = str(secilen_mac.get("home_team", "Ev"))
dep = str(secilen_mac.get("away_team", "Deplasman"))
sport_title = str(secilen_mac.get("sport_title", ""))

# Piyasa Oranlarını Çek (Sadece Değer Kıyaslaması İçin)
bookmakers = secilen_mac.get("bookmakers", [])
ev_o, ber_o, dep_o, buro_detaylari = [], [], [], []
if isinstance(bookmakers, list):
    for bm in bookmakers:
        if isinstance(bm, dict):
            b_name = str(bm.get("title", "Buro"))
            for mkt in bm.get("markets", []):
                if isinstance(mkt, dict) and str(mkt.get("key")) == "h2h":
                    e_p, b_p, d_p = None, None, None
                    for out in mkt.get("outcomes", []):
                        nm = str(out.get("name", ""))
                        pr = out.get("price")
                        if nm == ev: e_p = pr
                        elif nm == "Draw": b_p = pr
                        elif nm == dep: d_p = pr
                    if e_p and b_p and d_p:
                        try:
                            ev_o.append(float(e_p))
                            ber_o.append(float(b_p))
                            dep_o.append(float(d_p))
                            buro_detaylari.append({"Buro": b_name, "MS 1": float(e_p), "MS X": float(b_p), "MS 2": float(d_p)})
                        except Exception:
                            pass

max_ev = float(max(ev_o)) if len(ev_o) > 0 else 2.10
max_ber = float(max(ber_o)) if len(ber_o) > 0 else 3.20
max_dep = float(max(dep_o)) if len(dep_o) > 0 else 3.10

# --- BAĞIMSIZ GOL BEKLENTİSİ (xG) MODELLEME ---
st.sidebar.markdown("---")
st.sidebar.header("Bağımsız xG & Güç Parametreleri")
ev_guc = st.sidebar.slider(ev + " Hücum Gücü Katsayısı", 0.5, 2.0, 1.20, step=0.05)
dep_guc = st.sidebar.slider(dep + " Hücum Gücü Katsayısı", 0.5, 2.0, 1.00, step=0.05)
ev_eksik = st.sidebar.slider(ev + " Sakat/Eksik Etkisi (%)", 0, 40, 0, step=5)
dep_eksik = st.sidebar.slider(dep + " Sakat/Eksik Etkisi (%)", 0, 40, 0, step=5)
sim_sayisi = st.slider("Monte Carlo Simülasyon Tekrarı:", 10000, 100000, 50000, step=10000)

# BAĞIMSIZ MATRİS HESABI (Oranlardan Bağımsız Saf Poisson xG)
ev_xg = max(0.2, np.round(1.45 * ev_guc * (1.0 - (ev_eksik / 100.0)), 2))
dep_xg = max(0.2, np.round(1.15 * dep_guc * (1.0 - (dep_eksik / 100.0)), 2))

# 50.000 Kez Monte Carlo Zar Atma (Poisson Dağılımı)
e_gol = np.random.poisson(ev_xg, sim_sayisi)
d_gol = np.random.poisson(dep_xg, sim_sayisi)

e_iy = np.random.poisson(ev_xg * 0.43, sim_sayisi)
d_iy = np.random.poisson(dep_xg * 0.43, sim_sayisi)

skor_sayaclari = {}
for eg, dg in zip(e_gol, d_gol):
    skor_str = f"{eg} - {dg}"
    skor_sayaclari[skor_str] = skor_sayaclari.get(skor_str, 0) + 1

sirali_skorlar = sorted(skor_sayaclari.items(), key=lambda x: x[1], reverse=True)[:5]
en_olasi_skor_listesi = []
for skor_str, adet in sirali_skorlar:
    yuzde = (adet / sim_sayisi) * 100
    en_olasi_skor_listesi.append({"Maç Skoru": skor_str, "Monte Carlo Olasılığı (%)": f"%{yuzde:.2f}"})

ms1 = float(np.sum(e_gol > d_gol)) / sim_sayisi * 100.0
msX = float(np.sum(e_gol == d_gol)) / sim_sayisi * 100.0
ms2 = float(np.sum(e_gol < d_gol)) / sim_sayisi * 100.0

model_fair_ms1 = 100.0 / ms1 if ms1 > 0 else 999.0
model_fair_msX = 100.0 / msX if msX > 0 else 999.0
model_fair_ms2 = 100.0 / ms2 if ms2 > 0 else 999.0

h2h_gecmis = h2h_bul_football_data(ev, dep, sport_title)

# EKRAN MİMARİSİ
st.markdown("---")
col_m1, col_m2, col_m3 = st.columns(3)
col_m1.metric("Model xG: " + ev, f"{ev_xg:.2f}")
col_m2.metric("Model xG: Beraberlik", "-")
col_m3.metric("Model xG: " + dep, f"{dep_xg:.2f}")
st.markdown("---")

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "🎯 Bağımsız Skor & Model Matrisi",
    "⏱️ Gol Dakikalari & IY",
    "📊 CSV H2H Arşivi",
    "💎 Gerçek Değer (Value Bet)",
    "🌐 Piyasa Oranları"
])

with tab1:
    st.subheader("🎯 Bağımsız Monte Carlo Olasılık Matrisi")
    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.write("### 🏆 En Muhtemel 5 Skor")
        st.dataframe(pd.DataFrame(en_olasi_skor_listesi), use_container_width=True)
    with col_s2:
        st.write("### 📈 Bağımsız Maç Sonucu Olasılıkları")
        df_ms = pd.DataFrame({
            "Secenek": ["MS 1 (" + ev + ")", "MS X (Beraberlik)", "MS 2 (" + dep + ")"],
            "Model Olasilik (%)": [ms1, msX, ms2],
            "Model Adil Orani": [model_fair_ms1, model_fair_msX, model_fair_ms2]
        })
        st.dataframe(df_ms.style.format({"Model Olasilik (%)": "{:.1f}%", "Model Adil Orani": "{:.2f}"}), use_container_width=True)

with tab2:
    st.subheader("Zaman Dilimlerine Göre Gol Olasılıkları")
    iy_gol_var = float(np.sum((e_iy + d_iy) > 0.5)) / sim_sayisi * 100.0
    ust25 = float(np.sum((e_gol + d_gol) > 2.5)) / sim_sayisi * 100.0
    st.metric("İlk Yarı 0.5 Gol Üst", f"%{iy_gol_var:.1f}")
    st.metric("Maç Geneli 2.5 Gol Üst", f"%{ust25:.1f}")

with tab3:
    st.subheader("İki Takım Arasındaki Geçmiş Maçlar (CSV Arşivi)")
    if h2h_gecmis:
        st.table(pd.DataFrame(h2h_gecmis))
    else:
        st.info("Bu lig için arşivde karşılıklı maç kaydı bulunamadı.")

with tab4:
    st.subheader("💎 Piyasa vs Model Değer Karşılaştırması (Value Bet)")
    val_1 = max_ev > model_fair_ms1
    val_X = max_ber > model_fair_msX
    val_2 = max_dep > model_fair_ms2

    df_val = pd.DataFrame({
        "Secenek": ["MS 1", "MS X", "MS 2"],
        "Model Adil Orani": [f"{model_fair_ms1:.2f}", f"{model_fair_msX:.2f}", f"{model_fair_ms2:.2f}"],
        "Piyasa En Yuksek Oran": [f"{max_ev:.2f}", f"{max_ber:.2f}", f"{max_dep:.2f}"],
        "Value Durumu": [
            "DEĞERLİ (Piyasa Yüksek Ödüyor)" if val_1 else "Değersiz",
            "DEĞERLİ (Piyasa Yüksek Ödüyor)" if val_X else "Değersiz",
            "DEĞERLİ (Piyasa Yüksek Ödüyor)" if val_2 else "Değersiz"
        ]
    })
    st.table(df_val)

with tab5:
    st.subheader("Yabancı Büroların Canlı Oran Listesi")
    if buro_detaylari:
        st.dataframe(pd.DataFrame(buro_detaylari))
    else:
        st.info("Bu maç için büro oranı bulunamadı.")
