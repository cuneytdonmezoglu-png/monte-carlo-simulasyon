import streamlit as st
import requests
import numpy as np
import pandas as pd
import io
import json
import unicodedata
import difflib
import os
from datetime import datetime

st.set_page_config(page_title="Pro Monte Carlo & Skor Analiz Paneli", page_icon="⚽", layout="wide")

def _anahtar_oku(isim):
    try:
        if isim in st.secrets:
            return str(st.secrets[isim])
    except Exception:
        pass
    return os.environ.get(isim, "")

ODDS_API_KEY = _anahtar_oku("ODDS_API_KEY")
API_FOOTBALL_KEY = _anahtar_oku("API_FOOTBALL_KEY")
API_FOOTBALL_BASE = "https://v3.football.api-sports.io"
H2H_MAC_SAYISI = 20
CACHE_FILE = "maclar_cache.json"

st.title("⚽ Profesyonel Futbol Monte Carlo, Skor Tahmin & H2H Paneli")

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
    """Önbellekteki maçları kullanır; yoksa liglerden oran verisini çeker."""
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and data:
                return data, True
        except (OSError, json.JSONDecodeError):
            st.sidebar.warning("Önbellek okunamadı; yeni veri deneniyor.")

    if not ODDS_API_KEY:
        st.error(
            "The Odds API anahtarı bulunamadı. "
            "ODDS_API_KEY ortam değişkenini veya Streamlit secrets ayarını tanımlayın."
        )
        return [], False

    tum_maclar = []
    progress = st.progress(0)
    hatalar = []

    for idx, lig in enumerate(LIGLER):
        url = f"https://api.the-odds-api.com/v4/sports/{lig}/odds/"
        try:
            response = requests.get(
                url,
                params={
                    "apiKey": ODDS_API_KEY,
                    "regions": "eu",
                    "markets": "h2h",
                    "oddsFormat": "decimal",
                },
                timeout=15,
            )
            if response.status_code == 200:
                payload = response.json()
                if isinstance(payload, list):
                    tum_maclar.extend(payload)
            else:
                hatalar.append(f"{lig}: HTTP {response.status_code}")
        except (requests.RequestException, ValueError) as exc:
            hatalar.append(f"{lig}: {exc}")
        progress.progress((idx + 1) / len(LIGLER))

    progress.empty()

    if tum_maclar:
        try:
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(tum_maclar, f, ensure_ascii=False, indent=2)
        except OSError as exc:
            st.sidebar.warning(f"Önbellek kaydedilemedi: {exc}")
        return tum_maclar, False

    if hatalar:
        st.sidebar.warning("Bazı liglerden veri alınamadı: " + " | ".join(hatalar[:3]))
    return [], False


def takim_id_bul(takim_adi, headers):
    if not isinstance(takim_adi, str):
        return None
    temiz = takim_adi.replace(".", " ").strip()
    parcalar = [p.strip() for p in temiz.split() if len(p.strip()) > 2]
    adaylar = []
    if parcalar:
        adaylar.append(parcalar[-1])
        if parcalar[0] != parcalar[-1]:
            adaylar.append(parcalar[0])
    adaylar.append(temiz)
    for arama_terimi in adaylar:
        try:
            res = requests.get(
                API_FOOTBALL_BASE + "/teams",
                headers=headers,
                params={"search": arama_terimi},
                timeout=6
            )
            if res.status_code == 200:
                data = res.json().get("response", [])
                if data and isinstance(data, list):
                    # Tam isim eslesmesi varsa onu tercih et
                    for d in data:
                        if str(d.get("team", {}).get("name", "")).lower() == takim_adi.lower():
                            return d["team"]["id"]
                    return data[0]["team"]["id"]
        except Exception:
            pass
    return None

def _apifootball_h2h(ev_takim, dep_takim):
    """Kaynak 1: API-Football. Donus: (mac_listesi, hata_mesaji)."""
    if not API_FOOTBALL_KEY:
        return [], "API_FOOTBALL_KEY bulunamadi (st.secrets veya ortam degiskeni olarak ekleyin)."
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    try:
        ev_id = takim_id_bul(ev_takim, headers)
        dep_id = takim_id_bul(dep_takim, headers)
        if not (ev_id and dep_id):
            return [], "Takimlardan biri API-Football'da bulunamadi."
        res = requests.get(
            API_FOOTBALL_BASE + "/fixtures/headtohead",
            headers=headers,
            params={"h2h": str(ev_id) + "-" + str(dep_id), "last": H2H_MAC_SAYISI},
            timeout=8
        )
        if res.status_code != 200:
            return [], "API hatasi: HTTP " + str(res.status_code)
        js = res.json()
        errors = js.get("errors")
        if errors:
            # Ornek: ucretsiz planda sezon kisiti ya da gunluk limit asimi
            return [], "API uyarisi: " + (json.dumps(errors, ensure_ascii=False) if not isinstance(errors, str) else errors)
        mac_listesi = js.get("response", [])
        # Sadece oynanmis maclari al, en yeniden eskiye sirala
        oynanan = [
            m for m in mac_listesi
            if isinstance(m, dict) and m.get("fixture", {}).get("status", {}).get("short") in ("FT", "AET", "PEN")
        ]
        oynanan.sort(key=lambda m: str(m.get("fixture", {}).get("date", "")), reverse=True)
        return oynanan[:H2H_MAC_SAYISI], None
    except Exception as e:
        return [], "Baglanti hatasi: " + str(e)


# --- KAYNAK 2: football-data.co.uk (anahtarsiz, ucretsiz CSV arsivi) ---
CSV_LIGLERI = {
    "T1": "Süper Lig",
    "E0": "Premier League",
    "SP1": "La Liga",
    "I1": "Serie A",
    "D1": "Bundesliga",
    "F1": "Ligue 1",
}
CSV_SEZON_SAYISI = 10

# Odds API / API-Football adi -> CSV'deki kisa ad
TAKIM_ESLESTIRME = {
    "manchester united": "man united", "manchester city": "man city",
    "newcastle united": "newcastle", "nottingham forest": "nott'm forest",
    "tottenham hotspur": "tottenham", "wolverhampton wanderers": "wolves",
    "brighton and hove albion": "brighton", "west ham united": "west ham",
    "leicester city": "leicester", "leeds united": "leeds",
    "atletico madrid": "ath madrid", "athletic bilbao": "ath bilbao",
    "athletic club": "ath bilbao", "real betis": "betis",
    "real sociedad": "sociedad", "celta vigo": "celta",
    "rayo vallecano": "vallecano", "espanyol": "espanol",
    "bayern munich": "bayern munich", "borussia dortmund": "dortmund",
    "borussia monchengladbach": "m'gladbach", "bayer leverkusen": "leverkusen",
    "eintracht frankfurt": "ein frankfurt", "rb leipzig": "rb leipzig",
    "1 fc koln": "fc koln", "fsv mainz 05": "mainz", "vfb stuttgart": "stuttgart",
    "paris saint germain": "paris sg", "paris saint-germain": "paris sg",
    "olympique marseille": "marseille", "olympique lyonnais": "lyon",
    "as monaco": "monaco", "ac milan": "milan", "inter milan": "inter",
    "internazionale": "inter", "hellas verona": "verona", "as roma": "roma",
    "istanbul basaksehir": "buyuksehyr", "basaksehir": "buyuksehyr",
    "medipol basaksehir": "buyuksehyr", "fenerbahce": "fenerbahce",
    "besiktas": "besiktas", "galatasaray": "galatasaray",
    "kasimpasa": "kasimpasa", "alanyaspor": "alanyaspor",
    "caykur rizespor": "rizespor", "rizespor": "rizespor",
    "eyupspor": "eyupspor", "genclerbirligi": "genclerbirligi",
}
_GURULTU = {"fc", "cf", "afc", "sk", "ac", "as", "sc", "ssc", "rc", "us", "1", "fsv", "vfb", "spor", "kulubu"}

def _norm(ad):
    ad = unicodedata.normalize("NFKD", str(ad)).encode("ascii", "ignore").decode("ascii")
    ad = ad.lower().replace("-", " ").replace(".", " ")
    return " ".join(ad.split())

def _anahtar_kelimeler(ad):
    return " ".join(k for k in _norm(ad).split() if k not in _GURULTU)

def _ad_eslesiyor_mu(aranan, csv_adi):
    a = _norm(aranan)
    c = _norm(csv_adi)
    hedef = TAKIM_ESLESTIRME.get(a) or TAKIM_ESLESTIRME.get(_anahtar_kelimeler(aranan))
    if hedef:
        # Bilinen takimlarda sadece belirlenen ada izin ver ("Inter Milan" != "Milan")
        return _norm(hedef) == c
    ak, ck = _anahtar_kelimeler(aranan), _anahtar_kelimeler(csv_adi)
    if not ak or not ck:
        return False
    if ak == ck:
        return True
    if len(ck) >= 4 and (ck in ak or ak in ck):
        return True
    return difflib.SequenceMatcher(None, ak, ck).ratio() >= 0.82

def _guncel_sezon_baslangici():
    bugun = datetime.now()
    return bugun.year if bugun.month >= 7 else bugun.year - 1

@st.cache_data(ttl=86400, show_spinner=False)
def _csv_sezon_getir(lig_kodu, sezon_baslangic):
    kod = str(sezon_baslangic)[-2:] + str(sezon_baslangic + 1)[-2:]
    url = "https://www.football-data.co.uk/mmz4281/" + kod + "/" + lig_kodu + ".csv"
    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200 or not r.content:
            return None
        metin = r.content.decode("latin-1")
        df = pd.read_csv(io.StringIO(metin), on_bad_lines="skip")
        gerekli = {"Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"}
        if not gerekli.issubset(df.columns):
            return None
        df = df.dropna(subset=["Date", "HomeTeam", "AwayTeam", "FTHG", "FTAG"])
        df["_tarih"] = pd.to_datetime(df["Date"], dayfirst=True, errors="coerce")
        df = df.dropna(subset=["_tarih"])
        return df[["_tarih", "HomeTeam", "AwayTeam", "FTHG", "FTAG"]].copy()
    except Exception:
        return None

def _csv_h2h(ev_takim, dep_takim):
    """Kaynak 2: football-data.co.uk. Donus: (mac_listesi_apifootball_formatinda, hata)."""
    guncel = _guncel_sezon_baslangici()
    bulunan_lig = None
    for kod in CSV_LIGLERI:
        # Son 2 sezondan birinde iki takim da gorunuyorsa lig odur
        for sezon in (guncel, guncel - 1):
            df = _csv_sezon_getir(kod, sezon)
            if df is None:
                continue
            adlar = set(df["HomeTeam"]).union(set(df["AwayTeam"]))
            ev_var = any(_ad_eslesiyor_mu(ev_takim, a) for a in adlar)
            dep_var = any(_ad_eslesiyor_mu(dep_takim, a) for a in adlar)
            if ev_var and dep_var:
                bulunan_lig = kod
                break
        if bulunan_lig:
            break
    if not bulunan_lig:
        return [], "Iki takim ayni ligin CSV arsivinde bulunamadi (Avrupa kupasi maci olabilir)."

    sonuc = []
    for sezon in range(guncel, guncel - CSV_SEZON_SAYISI, -1):
        df = _csv_sezon_getir(bulunan_lig, sezon)
        if df is None:
            continue
        for _, satir in df.iterrows():
            h, a = satir["HomeTeam"], satir["AwayTeam"]
            if (_ad_eslesiyor_mu(ev_takim, h) and _ad_eslesiyor_mu(dep_takim, a)) or \
               (_ad_eslesiyor_mu(dep_takim, h) and _ad_eslesiyor_mu(ev_takim, a)):
                sonuc.append({
                    "fixture": {"date": satir["_tarih"].strftime("%Y-%m-%d"), "status": {"short": "FT"}},
                    "league": {"name": CSV_LIGLERI[bulunan_lig]},
                    "teams": {"home": {"name": h}, "away": {"name": a}},
                    "goals": {"home": int(satir["FTHG"]), "away": int(satir["FTAG"])},
                })
    return sonuc, None

@st.cache_data(ttl=86400)
def h2h_ve_form_getir(ev_takim, dep_takim):
    """Birden fazla kaynaktan H2H toplar. Donus: (mac_listesi, hata, kaynaklar)."""
    kaynaklar, hatalar, tum = [], [], {}

    # Kaynak 2 (anahtarsiz, cok sezon) once; Kaynak 1 (API-Football) eksikleri tamamlar
    for ad, fonk in (("football-data.co.uk", _csv_h2h), ("API-Football", _apifootball_h2h)):
        try:
            liste, hata = fonk(ev_takim, dep_takim)
        except Exception as e:
            liste, hata = [], str(e)
        if hata and not liste:
            hatalar.append(ad + ": " + hata)
        if liste:
            kaynaklar.append(ad)
            for m in liste:
                anahtar = str(m.get("fixture", {}).get("date", ""))[:10]
                tum.setdefault(anahtar, m)  # ayni gun ayni takimlar = ayni mac

    maclar = sorted(tum.values(), key=lambda m: str(m["fixture"]["date"]), reverse=True)[:H2H_MAC_SAYISI]
    if not maclar:
        return [], " | ".join(hatalar) or "Hicbir kaynaktan veri alinamadi.", []
    return maclar, None, kaynaklar

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
    st.error("ODDS_API_KEY bulunamadi. st.secrets veya ortam degiskeni olarak ekleyin.")
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
                                    if nm == ev: 
                                        e_price = pr
                                    elif nm == "Draw": 
                                        b_price = pr
                                    elif nm == dep: 
                                        d_price = pr
                            
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

if st.button("Detayli Gelismis Simulasyonu Calistir", type="primary"):
    with st.spinner("Monte Carlo Skor Matrisi ve H2H Analizi Hesaplaniyor..."):
        h2h_gecmis, h2h_hata, h2h_kaynaklar = h2h_ve_form_getir(ev, dep)
        
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
        
        sirali_skorlar = sorted(skor_sayaclari.items(), key=lambda x: x[1], reverse=True)[:5]
        en_olasi_skor_listesi = []
        for skor_Str, adet in sirali_skorlar:
            yuzde = (adet / sim_sayisi) * 100
            en_olasi_skor_listesi.append({"Maç Skoru": skor_Str, "Simülasyon Olasılığı (%)": f"%{yuzde:.2f}"})

        ms1 = float(np.sum(e_gol > d_gol)) / sim_sayisi * 100.0
        msX = float(np.sum(e_gol == d_gol)) / sim_sayisi * 100.0
        ms2 = float(np.sum(e_gol < d_gol)) / sim_sayisi * 100.0

        fair_ms1 = 100.0 / ms1 if ms1 > 0.0 else 999.0
        fair_msX = 100.0 / msX if msX > 0.0 else 999.0
        fair_ms2 = 100.0 / ms2 if ms2 > 0.0 else 999.0

        iy1 = float(np.sum(e_iy > d_iy)) / sim_sayisi * 100.0
        iyX = float(np.sum(e_iy == d_iy)) / sim_sayisi * 100.0
        iy2 = float(np.sum(e_iy < d_iy)) / sim_sayisi * 100.0

        fair_iy1 = 100.0 / iy1 if iy1 > 0.0 else 999.0
        fair_iyX = 100.0 / iyX if iyX > 0.0 else 999.0
        fair_iy2 = 100.0 / iy2 if iy2 > 0.0 else 999.0

        iy_gol_var = float(np.sum((e_iy + d_iy) > 0.5)) / sim_sayisi * 100.0
        toplam_gol = e_gol + d_gol
        ust25 = float(np.sum(toplam_gol > 2.5)) / sim_sayisi * 100.0

        fair_iy_gol = 100.0 / iy_gol_var if iy_gol_var > 0.0 else 999.0
        fair_ust25 = 100.0 / ust25 if ust25 > 0.0 else 999.0

        tab1, tab2, tab3, tab4, tab5 = st.tabs([
            "🎯 Skor Tahminleri & MS",
            "⏱️ Gol Dakikalari & IY",
            "📊 Gecmis H2H Maclari",
            "💎 Value Bet & Kadro",
            "🌐 Yabanci Burolar"
        ])

        with tab1:
            st.subheader("🎯 En Olası Skor Tahminleri (Monte Carlo Matrisi)")
            st.info(f"Modifiye Gol Beklentileri (xG) -> {ev}: {ev_xg:.2f} | {dep}: {dep_xg:.2f}")
            
            col_skor1, col_skor2 = st.columns(2)
            with col_skor1:
                st.write("### 🏆 En Muhtemel 5 Maç Skoru")
                st.dataframe(pd.DataFrame(en_olasi_skor_listesi), use_container_width=True)
            with col_skor2:
                st.write("### 📈 Maç Sonucu (MS) Olasılıkları")
                df_ms = pd.DataFrame({
                    "Secenek": ["MS 1 (" + ev + ")", "MS X (Beraberlik)", "MS 2 (" + dep + ")"],
                    "Olasilik (%)": [ms1, msX, ms2],
                    "Adil Oran": [fair_ms1, fair_msX, fair_ms2]
                })
                st.dataframe(df_ms.style.format({"Olasilik (%)": "{:.1f}%", "Adil Oran": "{:.2f}"}), use_container_width=True)

        with tab2:
            st.subheader("Zaman Dilimlerine Gore Gol Olasiliklari")
            col_z1, col_z2 = st.columns(2)
            with col_z1:
                st.metric("Ilk Yari 0.5 Gol Ust", f"%{iy_gol_var:.1f}", "Adil Oran: " + f"{fair_iy_gol:.2f}")
                st.metric("Mac Geneli 2.5 Gol Ust", f"%{ust25:.1f}", "Adil Oran: " + f"{fair_ust25:.2f}")
                
                df_iy = pd.DataFrame({
                    "Secenek": ["IY 1", "IY X", "IY 2"],
                    "Olasilik (%)": [iy1, iyX, iy2],
                    "Adil Oran": [fair_iy1, fair_iyX, fair_iy2]
                })
                st.dataframe(df_iy.style.format({"Olasilik (%)": "{:.1f}%", "Adil Oran": "{:.2f}"}))

            with col_z2:
                dilim_xg = (ev_xg + dep_xg) / 6.0
                d_0_15 = np.random.poisson(dilim_xg, sim_sayisi)
                d_15_30 = np.random.poisson(dilim_xg, sim_sayisi)
                d_30_45 = np.random.poisson(dilim_xg * 1.1, sim_sayisi)
                d_45_60 = np.random.poisson(dilim_xg, sim_sayisi)
                d_60_75 = np.random.poisson(dilim_xg * 1.2, sim_sayisi)
                d_75_90 = np.random.poisson(dilim_xg * 1.3, sim_sayisi)

                df_dilim = pd.DataFrame({
                    "Zaman Araligi": ["0-15 dk", "15-30 dk", "30-45+ dk", "45-60 dk", "60-75 dk", "75-90+ dk"],
                    "Gol Olasiligi (%)": [
                        float(np.sum(d_0_15 > 0)) / sim_sayisi * 100.0,
                        float(np.sum(d_15_30 > 0)) / sim_sayisi * 100.0,
                        float(np.sum(d_30_45 > 0)) / sim_sayisi * 100.0,
                        float(np.sum(d_45_60 > 0)) / sim_sayisi * 100.0,
                        float(np.sum(d_60_75 > 0)) / sim_sayisi * 100.0,
                        float(np.sum(d_75_90 > 0)) / sim_sayisi * 100.0
                    ]
                })
                st.dataframe(df_dilim.style.format({"Gol Olasiligi (%)": "{:.1f}%"}))

        with tab3:
            st.subheader("İki Takım Arasındaki Geçmiş Maçlar (H2H)")
            if h2h_gecmis and isinstance(h2h_gecmis, list) and len(h2h_gecmis) > 0:
                h2h_list = []
                ev_galibiyet, beraberlik, dep_galibiyet = 0, 0, 0
                toplam_gol_h2h = 0
                for m in h2h_gecmis:
                    if isinstance(m, dict):
                        tarih = str(m.get("fixture", {}).get("date", ""))[:10]
                        lig_adi = str(m.get("league", {}).get("name", ""))
                        teams = m.get("teams", {})
                        ev_t = str(teams.get("home", {}).get("name", "Ev"))
                        dep_t = str(teams.get("away", {}).get("name", "Dep"))
                        goals = m.get("goals", {})
                        eg = goals.get("home")
                        dg = goals.get("away")
                        eg = int(eg) if eg is not None else 0
                        dg = int(dg) if dg is not None else 0
                        toplam_gol_h2h += eg + dg
                        # Secili maçtaki takimlar acisindan sonuc say
                        if eg == dg:
                            beraberlik += 1
                        else:
                            kazanan = ev_t if eg > dg else dep_t
                            if kazanan == ev or ev.lower() in kazanan.lower() or kazanan.lower() in ev.lower():
                                ev_galibiyet += 1
                            else:
                                dep_galibiyet += 1
                        h2h_list.append({
                            "Tarih": tarih,
                            "Lig": lig_adi,
                            "Ev Sahibi": ev_t,
                            "Skor": str(eg) + " - " + str(dg),
                            "Deplasman": dep_t
                        })
                n = len(h2h_list)
                if n < H2H_MAC_SAYISI:
                    st.warning("Bu iki takım arasında API'de " + str(n) + " oynanmış maç bulundu (hedef: " + str(H2H_MAC_SAYISI) + "). Ücretsiz planda erişilebilen sezonlar sınırlı olabilir.")
                c1, c2, c3, c4 = st.columns(4)
                c1.metric(ev + " Galibiyet", ev_galibiyet)
                c2.metric("Beraberlik", beraberlik)
                c3.metric(dep + " Galibiyet", dep_galibiyet)
                c4.metric("Maç Başı Gol", f"{toplam_gol_h2h / n:.2f}" if n else "-")
                st.table(pd.DataFrame(h2h_list))
                st.caption("Kaynak: " + ", ".join(h2h_kaynaklar))
            else:
                if h2h_hata:
                    st.warning("H2H verisi alınamadı: " + h2h_hata)
                else:
                    st.info("Bu iki takım için API arşivinde doğrudan H2H kaydı bulunamadı. Sol paneldeki 'H2H Ağırlık Çarpanı' ile simülasyonu manuel yönlendirebilirsiniz.")

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
            st.subheader("Yabanci Burolarin Canli Oran Listesi")
            if buro_detaylari:
                df_buro = pd.DataFrame(buro_detaylari)
                st.dataframe(
                    df_buro.style.format({"MS 1": "{:.2f}", "MS X": "{:.2f}", "MS 2": "{:.2f}"}),
                    use_container_width=True
                )
                st.caption(
                    "Toplam " + str(len(df_buro)) + " buro | "
                    "En yuksek -> MS 1: " + f"{max_ev:.2f}" + " | MS X: " + f"{max_ber:.2f}" + " | MS 2: " + f"{max_dep:.2f}"
                )
            else:
                st.info("Bu mac icin yabanci buro orani bulunamadi.")
