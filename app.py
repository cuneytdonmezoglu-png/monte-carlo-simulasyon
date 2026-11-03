import streamlit as st
import requests
import numpy as np
import pandas as pd
import io
import math
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
        for c in ("HTHG", "HTAG"):
            if c not in df.columns:
                df[c] = np.nan
        return df[["_tarih", "HomeTeam", "AwayTeam", "FTHG", "FTAG", "HTHG", "HTAG"]].copy()
    except Exception:
        return None

def _lig_bul(ev_takim, dep_takim):
    """Iki takimin da yer aldigi CSV ligini bulur (T1, E0, ...). Yoksa None."""
    guncel = _guncel_sezon_baslangici()
    for kod in CSV_LIGLERI:
        for sezon in (guncel, guncel - 1):
            df = _csv_sezon_getir(kod, sezon)
            if df is None:
                continue
            adlar = set(df["HomeTeam"]).union(set(df["AwayTeam"]))
            if any(_ad_eslesiyor_mu(ev_takim, x) for x in adlar) and any(_ad_eslesiyor_mu(dep_takim, x) for x in adlar):
                return kod
    return None

def _csv_h2h(ev_takim, dep_takim):
    """Kaynak 2: football-data.co.uk. Donus: (mac_listesi_apifootball_formatinda, hata)."""
    guncel = _guncel_sezon_baslangici()
    bulunan_lig = _lig_bul(ev_takim, dep_takim)
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


# =====================================================================
# GERCEK MONTE CARLO MOTORU: hucum/savunma gucu endeksleri
# =====================================================================
def _csv_takim_adi(aranan, adlar):
    adlar = list(adlar)
    for a in adlar:
        if _norm(a) == _norm(aranan):
            return a
    for a in adlar:
        if _ad_eslesiyor_mu(aranan, a):
            return a
    return None

def guc_modeli_fit(H, A, X, Y, W, n_takim, on_oyun=6.0, iterasyon=300):
    """
    Carpimsal Poisson modeli (Maher / Dixon-Coles tarzi), rakip kalitesine gore duzeltilmis:
        Ev golu  ~ Poisson(mu * ev_avantaji * hucum[ev]  * savunma[dep])
        Dep golu ~ Poisson(mu *                hucum[dep] * savunma[ev])
    savunma > 1 = rakibe ortalamadan FAZLA gol yedirir (kotu savunma).
    W: zaman agirliklari (yeni maclar daha agir). on_oyun: kucuk orneklemi 1.00'a cekmek icin
    her takima eklenen 'ortalama performansli sanal mac' sayisi (shrinkage).
    """
    H = np.asarray(H); A = np.asarray(A)
    X = np.asarray(X, dtype=float); Y = np.asarray(Y, dtype=float); W = np.asarray(W, dtype=float)
    e0 = float(np.sum(W * (X + Y)) / (2.0 * np.sum(W)))   # takim basina ortalama gol
    att = np.ones(n_takim); sav = np.ones(n_takim)
    mu = e0; ha = 1.25
    k = float(on_oyun) * e0
    for _ in range(iterasyon):
        num = np.bincount(H, W * X, n_takim) + np.bincount(A, W * Y, n_takim)
        den = np.bincount(H, W * mu * ha * sav[A], n_takim) + np.bincount(A, W * mu * sav[H], n_takim)
        att = (num + k) / (den + k)

        num = np.bincount(H, W * Y, n_takim) + np.bincount(A, W * X, n_takim)
        den = np.bincount(H, W * mu * att[A], n_takim) + np.bincount(A, W * mu * ha * att[H], n_takim)
        sav = (num + k) / (den + k)

        ha = float(np.sum(W * X) / np.sum(W * mu * att[H] * sav[A]))

        # kimlik sabitleme: ortalama hucum = ortalama savunma = 1
        att_o, sav_o = att.mean(), sav.mean()
        att = att / att_o; sav = sav / sav_o
        mu = float(np.sum(W * (X + Y)) / np.sum(W * (ha * att[H] * sav[A] + att[A] * sav[H])))
    return att, sav, mu, ha

@st.cache_data(ttl=86400, show_spinner=False)
def guc_endeksleri_getir(ev_takim, dep_takim, yari_omur_gun=270.0, on_oyun=6.0, sezon_sayisi=3):
    """Iki takimin ligindeki son sezonlardan hucum/savunma endekslerini hesaplar."""
    kod = _lig_bul(ev_takim, dep_takim)
    if not kod:
        return {"ok": False, "hata": "Iki takim ayni ligin arsivinde bulunamadi (Avrupa kupasi / farkli lig)."}
    guncel = _guncel_sezon_baslangici()
    parcalar = []
    for sezon in range(guncel, guncel - int(sezon_sayisi), -1):
        df = _csv_sezon_getir(kod, sezon)
        if df is not None and len(df) > 0:
            parcalar.append(df)
    if not parcalar:
        return {"ok": False, "hata": "Lig verisi indirilemedi."}
    df = pd.concat(parcalar, ignore_index=True)
    if len(df) < 60:
        return {"ok": False, "hata": "Guc modeli icin yeterli mac yok (" + str(len(df)) + ")."}

    yas = (pd.Timestamp(datetime.now()) - df["_tarih"]).dt.days.clip(lower=0).to_numpy(dtype=float)
    W = 0.5 ** (yas / float(yari_omur_gun))

    takimlar = sorted(set(df["HomeTeam"]).union(set(df["AwayTeam"])))
    idx = {t: i for i, t in enumerate(takimlar)}
    H = df["HomeTeam"].map(idx).to_numpy(dtype=int)
    A = df["AwayTeam"].map(idx).to_numpy(dtype=int)
    X = df["FTHG"].to_numpy(dtype=float)
    Y = df["FTAG"].to_numpy(dtype=float)

    att, sav, mu, ha = guc_modeli_fit(H, A, X, Y, W, len(takimlar), on_oyun)

    ev_ad = _csv_takim_adi(ev_takim, takimlar)
    dep_ad = _csv_takim_adi(dep_takim, takimlar)
    if ev_ad is None or dep_ad is None:
        return {"ok": False, "hata": "Takim adi lig verisiyle eslesmedi."}
    i_e, i_d = idx[ev_ad], idx[dep_ad]

    # Ilk yari gol payi (veri varsa ligden, yoksa 0.44)
    ht_pay = 0.44
    ht = df.dropna(subset=["HTHG", "HTAG"])
    if len(ht) > 200:
        w_ht = 0.5 ** ((pd.Timestamp(datetime.now()) - ht["_tarih"]).dt.days.clip(lower=0).to_numpy(dtype=float) / float(yari_omur_gun))
        toplam_ft = float(np.sum(w_ht * (ht["FTHG"].to_numpy(dtype=float) + ht["FTAG"].to_numpy(dtype=float))))
        toplam_ht = float(np.sum(w_ht * (ht["HTHG"].to_numpy(dtype=float) + ht["HTAG"].to_numpy(dtype=float))))
        if toplam_ft > 0:
            ht_pay = float(min(0.50, max(0.38, toplam_ht / toplam_ft)))

    n_oynanan = np.bincount(H, minlength=len(takimlar)) + np.bincount(A, minlength=len(takimlar))
    genel = att / sav
    tablo = pd.DataFrame({
        "Takım": takimlar,
        "Hücum Gücü": att,
        "Savunma Gücü": 1.0 / sav,
        "Genel Güç": genel,
        "Maç": n_oynanan,
    }).sort_values("Genel Güç", ascending=False).reset_index(drop=True)
    tablo.index = tablo.index + 1

    return {
        "ok": True, "lig": kod, "lig_adi": CSV_LIGLERI[kod],
        "mu": mu, "ev_avantaji": ha, "ht_pay": ht_pay,
        "ev_ad": ev_ad, "dep_ad": dep_ad,
        "att_ev": float(att[i_e]), "sav_ev": float(sav[i_e]),
        "att_dep": float(att[i_d]), "sav_dep": float(sav[i_d]),
        "n_ev": int(n_oynanan[i_e]), "n_dep": int(n_oynanan[i_d]),
        "lam_ev": float(mu * ha * att[i_e] * sav[i_d]),
        "lam_dep": float(mu * att[i_d] * sav[i_e]),
        "tablo": tablo, "toplam_mac": int(len(df)),
    }

def piyasa_lambdalari(p1, pX, p2):
    """Marjdan arindirilmis 1-X-2 olasiliklarina uyan (lambda_ev, lambda_dep) cifti (Poisson, grid arama).
    Sadece iki takim ayni lig verisinde yoksa yedek olarak kullanilir."""
    k = np.arange(0, 11)
    lg = np.array([math.lgamma(x + 1.0) for x in k])

    def ara(lh_grid, la_grid):
        def pmf(l):
            l = np.asarray(l, dtype=float)[:, None]
            return np.exp(-l + k[None, :] * np.log(l) - lg[None, :])
        ph, pa = pmf(lh_grid)[:, None, :], pmf(la_grid)[None, :, :]
        cdf_h = np.cumsum(ph, axis=-1)
        berabere = (ph * pa).sum(-1)
        ev_kazanir = (pa * (1.0 - cdf_h)).sum(-1)
        hata = (ev_kazanir - p1) ** 2 + (berabere - pX) ** 2
        i, j = np.unravel_index(np.argmin(hata), hata.shape)
        return float(lh_grid[i]), float(la_grid[j])

    lh, la = ara(np.linspace(0.2, 4.5, 87), np.linspace(0.2, 4.5, 87))
    lh, la = ara(np.linspace(max(0.05, lh - 0.1), lh + 0.1, 41), np.linspace(max(0.05, la - 0.1), la + 0.1, 41))
    return lh, la

def _gol_dilimleri(rng, gol_sayilari, ilk_yari_pay):
    """Her golu 6 dakika dilimine (0-15, 15-30, 30-45+, 45-60, 60-75, 75-90+) dagitir. Ilk yari = ilk 3 dilim."""
    p = np.concatenate([np.array([0.30, 0.33, 0.37]) * ilk_yari_pay,
                        np.array([0.28, 0.33, 0.39]) * (1.0 - ilk_yari_pay)])
    kalan_n = gol_sayilari.copy(); kalan_p = 1.0; dilimler = []
    for pi in p[:-1]:
        kk = rng.binomial(kalan_n, min(1.0, pi / kalan_p))
        dilimler.append(kk); kalan_n = kalan_n - kk; kalan_p -= pi
    dilimler.append(kalan_n)
    return dilimler

def monte_carlo_simule(ev_lam, dep_lam, n, belirsizlik=0.08, rho=-0.10, ilk_yari_pay=0.44):
    """
    Monte Carlo: her simulasyonda
      1) guc tahmin belirsizligi: lambda'lar log-normal gurultuyle oynar (ortalama korunur),
      2) goller Poisson'dan cekilir,
      3) Dixon-Coles dusuk skor duzeltmesi (0-0, 1-0, 0-1, 1-1) onem agirligi (w) ile uygulanir,
      4) goller dakika dilimlerine dagitilir (ilk yari / ikinci yari tutarli).
    Tum olasiliklar agirlikli oran: sum(w[olay]) / sum(w).
    """
    rng = np.random.default_rng()
    if belirsizlik > 0:
        lam_e = ev_lam * rng.lognormal(-0.5 * belirsizlik ** 2, belirsizlik, n)
        lam_d = dep_lam * rng.lognormal(-0.5 * belirsizlik ** 2, belirsizlik, n)
    else:
        lam_e = np.full(n, float(ev_lam)); lam_d = np.full(n, float(dep_lam))
    e = rng.poisson(lam_e); d = rng.poisson(lam_d)

    w = np.ones(n)
    m = (e == 0) & (d == 0); w[m] = 1.0 - lam_e[m] * lam_d[m] * rho
    m = (e == 0) & (d == 1); w[m] = 1.0 + lam_e[m] * rho
    m = (e == 1) & (d == 0); w[m] = 1.0 + lam_d[m] * rho
    m = (e == 1) & (d == 1); w[m] = 1.0 - rho
    w = np.clip(w, 1e-6, None)

    e_dil = _gol_dilimleri(rng, e, ilk_yari_pay)
    d_dil = _gol_dilimleri(rng, d, ilk_yari_pay)
    return {
        "e": e, "d": d, "w": w,
        "e_iy": e_dil[0] + e_dil[1] + e_dil[2],
        "d_iy": d_dil[0] + d_dil[1] + d_dil[2],
        "dilim_toplam": [e_dil[i] + d_dil[i] for i in range(6)],
    }

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

st.sidebar.markdown("---")
st.sidebar.header("Güç Modeli Ayarları")
yari_omur = st.sidebar.slider("Maç ağırlığı yarı ömrü (gün)", 90, 720, 270, step=30,
                              help="Kısa = son maçlar çok daha önemli. 270 gün: 9 ay önceki maç yarı ağırlıkta.")
on_oyun = st.sidebar.slider("Küçük örneklem koruması (sanal maç)", 0, 20, 6,
                            help="Az maç oynamış takımların endeksini lig ortalamasına (1.00) çeker.")
guc_belirsizligi = st.sidebar.slider("Güç tahmin belirsizliği (%)", 0, 25, 8,
                                     help="Her simülasyonda gol beklentisi bu oranda oynar; kuyruk olaylarını gerçekçi yapar.")
rho_dc = st.sidebar.slider("Düşük skor düzeltmesi (Dixon-Coles ρ)", -0.20, 0.0, -0.10, step=0.01,
                           help="0-0 ve 1-1 gibi düşük skorların bağımsız Poisson'dan farkını ayarlar.")

sim_sayisi = st.slider("Simulasyon Tekrar Sayisi:", 10000, 100000, 50000, step=10000)

if st.button("Detayli Gelismis Simulasyonu Calistir", type="primary"):
    with st.spinner("Monte Carlo Skor Matrisi ve H2H Analizi Hesaplaniyor..."):
        h2h_gecmis, h2h_hata, h2h_kaynaklar = h2h_ve_form_getir(ev, dep)

        # 1) Piyasa (sadece karsilastirma ve yedek icin): marjdan arindirilmis olasiliklar
        inv = np.array([1.0 / max(avg_ev, 1.01), 1.0 / max(avg_ber, 1.01), 1.0 / max(avg_dep, 1.01)])
        piyasa_p = inv / inv.sum()

        # 2) Gol beklentileri: takim guc endekslerinden; ayni ligde degillerse piyasadan turetilen lambda
        guc = guc_endeksleri_getir(ev, dep, float(yari_omur), float(on_oyun))
        if guc.get("ok"):
            model_kaynagi = "Güç Modeli (" + guc["lig_adi"] + ")"
            ev_xg_ham, dep_xg_ham = guc["lam_ev"], guc["lam_dep"]
            ilk_yari_pay = guc["ht_pay"]
        else:
            model_kaynagi = "Piyasa-türevi yedek"
            ev_xg_ham, dep_xg_ham = piyasa_lambdalari(*piyasa_p)
            ilk_yari_pay = 0.44

        ev_xg = float(min(5.0, max(0.15, ev_xg_ham * (1.0 + h2h_weight / 100.0) * (1.0 - ev_eksik / 100.0))))
        dep_xg = float(min(5.0, max(0.15, dep_xg_ham * (1.0 - h2h_weight / 100.0) * (1.0 - dep_eksik / 100.0))))

        # 3) Monte Carlo
        sim = monte_carlo_simule(ev_xg, dep_xg, sim_sayisi, guc_belirsizligi / 100.0, rho_dc, ilk_yari_pay)
        e_gol, d_gol, wts = sim["e"], sim["d"], sim["w"]
        e_iy, d_iy = sim["e_iy"], sim["d_iy"]
        W_toplam = float(np.sum(wts))

        def oran(maske):
            return float(np.sum(wts[maske])) / W_toplam * 100.0

        # En olasi skorlar (agirlikli sayim)
        anahtar = np.minimum(e_gol, 9) * 10 + np.minimum(d_gol, 9)
        sayac = np.bincount(anahtar, weights=wts, minlength=100)
        en_olasi_skor_listesi = []
        for ix in np.argsort(-sayac)[:5]:
            en_olasi_skor_listesi.append({
                "Maç Skoru": str(ix // 10) + " - " + str(ix % 10),
                "Simülasyon Olasılığı (%)": f"%{sayac[ix] / W_toplam * 100.0:.2f}"
            })

        ms1 = oran(e_gol > d_gol)
        msX = oran(e_gol == d_gol)
        ms2 = oran(e_gol < d_gol)

        fair_ms1 = 100.0 / ms1 if ms1 > 0.0 else 999.0
        fair_msX = 100.0 / msX if msX > 0.0 else 999.0
        fair_ms2 = 100.0 / ms2 if ms2 > 0.0 else 999.0

        iy1 = oran(e_iy > d_iy)
        iyX = oran(e_iy == d_iy)
        iy2 = oran(e_iy < d_iy)

        fair_iy1 = 100.0 / iy1 if iy1 > 0.0 else 999.0
        fair_iyX = 100.0 / iyX if iyX > 0.0 else 999.0
        fair_iy2 = 100.0 / iy2 if iy2 > 0.0 else 999.0

        iy_gol_var = oran((e_iy + d_iy) > 0)
        ust25 = oran((e_gol + d_gol) > 2)
        kg_var = oran((e_gol > 0) & (d_gol > 0))

        fair_iy_gol = 100.0 / iy_gol_var if iy_gol_var > 0.0 else 999.0
        fair_ust25 = 100.0 / ust25 if ust25 > 0.0 else 999.0

        dilim_adlari = ["0-15 dk", "15-30 dk", "30-45+ dk", "45-60 dk", "60-75 dk", "75-90+ dk"]
        df_dilim = pd.DataFrame({
            "Zaman Araligi": dilim_adlari,
            "Gol Olasiligi (%)": [oran(x > 0) for x in sim["dilim_toplam"]]
        })

        tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
            "🎯 Skor Tahminleri & MS",
            "⏱️ Gol Dakikalari & IY",
            "📊 Gecmis H2H Maclari",
            "💎 Value Bet & Kadro",
            "🌐 Yabanci Burolar",
            "🧠 Güç Endeksleri"
        ])

        with tab1:
            st.subheader("🎯 En Olası Skor Tahminleri (Monte Carlo Matrisi)")
            st.info(f"Gol Beklentileri (λ) -> {ev}: {ev_xg:.2f} | {dep}: {dep_xg:.2f}  •  Kaynak: {model_kaynagi}")
            if not guc.get("ok"):
                st.warning("Güç endeksleri hesaplanamadı: " + str(guc.get("hata")) + " Gol beklentileri piyasa oranlarından türetildi; 'Value Bet' sekmesi bu durumda anlamlı değildir.")
            
            col_skor1, col_skor2 = st.columns(2)
            with col_skor1:
                st.write("### 🏆 En Muhtemel 5 Maç Skoru")
                st.dataframe(pd.DataFrame(en_olasi_skor_listesi), use_container_width=True)
            with col_skor2:
                st.write("### 📈 Maç Sonucu (MS) Olasılıkları")
                df_ms = pd.DataFrame({
                    "Secenek": ["MS 1 (" + ev + ")", "MS X (Beraberlik)", "MS 2 (" + dep + ")"],
                    "Olasilik (%)": [ms1, msX, ms2],
                    "Adil Oran": [fair_ms1, fair_msX, fair_ms2],
                    "Piyasa Olasılığı (%)": list(piyasa_p * 100.0)
                })
                st.dataframe(df_ms.style.format({"Olasilik (%)": "{:.1f}%", "Adil Oran": "{:.2f}", "Piyasa Olasılığı (%)": "{:.1f}%"}), use_container_width=True)
                st.caption(f"Karşılıklı gol (KG Var): %{kg_var:.1f} • 2.5 Üst: %{ust25:.1f}")

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
                "Beklenen Değer (EV %)": [
                    f"{(ms1 / 100.0 * max_ev - 1.0) * 100.0:+.1f}",
                    f"{(msX / 100.0 * max_ber - 1.0) * 100.0:+.1f}",
                    f"{(ms2 / 100.0 * max_dep - 1.0) * 100.0:+.1f}"
                ],
                "Value Durumu": [
                    ("DEGERLI" if v else "Notr") if guc.get("ok") else "-"
                    for v in (val_1, val_X, val_2)
                ]
            })
            if not guc.get("ok"):
                st.info("Gol beklentileri piyasadan türetildiği için model piyasayla aynı bilgiyi kullanıyor; bu maçta value hesabı yapılmaz.")
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

        with tab6:
            st.subheader("🧠 Takım Güç Endeksleri")
            if guc.get("ok"):
                st.caption(
                    guc["lig_adi"] + " • " + str(guc["toplam_mac"]) + " maç • yarı ömür " + str(yari_omur) + " gün • "
                    "lig ortalaması takım başı " + f"{guc['mu']:.2f}" + " gol • ev sahibi avantajı ×" + f"{guc['ev_avantaji']:.2f}"
                )
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**" + ev + "** (eşleşen ad: " + guc["ev_ad"] + ")")
                    m1, m2 = st.columns(2)
                    m1.metric("Hücum Gücü", f"{guc['att_ev']:.2f}")
                    m2.metric("Savunma Gücü", f"{1.0 / guc['sav_ev']:.2f}")
                    st.caption("Kullanılan maç: " + str(guc["n_ev"]))
                with c2:
                    st.markdown("**" + dep + "** (eşleşen ad: " + guc["dep_ad"] + ")")
                    m3, m4 = st.columns(2)
                    m3.metric("Hücum Gücü", f"{guc['att_dep']:.2f}")
                    m4.metric("Savunma Gücü", f"{1.0 / guc['sav_dep']:.2f}")
                    st.caption("Kullanılan maç: " + str(guc["n_dep"]))
                st.markdown(
                    "**Nasıl okunur?** 1.00 = lig ortalaması. Hücum Gücü 1.30 → rakip kalitesi düzeltildikten sonra "
                    "ligdeki ortalama takımdan %30 fazla gol atıyor. Savunma Gücü 1.30 → ortalama takıma göre %23 az gol yiyor.  \n"
                    "**Gol beklentisi (λ):** λ_ev = lig ort. × ev avantajı × " + ev + " hücumu × " + dep + " savunma zayıflığı; "
                    "λ_dep = lig ort. × " + dep + " hücumu × " + ev + " savunma zayıflığı."
                )
                tablo = guc["tablo"]
                hedef = {guc["ev_ad"], guc["dep_ad"]}
                def vurgula(satir):
                    return ["background-color: rgba(255, 193, 7, 0.25)" if satir["Takım"] in hedef else "" for _ in satir]
                with st.expander("Ligdeki tüm takımların güç sıralaması"):
                    st.dataframe(
                        tablo.style.apply(vurgula, axis=1).format({"Hücum Gücü": "{:.2f}", "Savunma Gücü": "{:.2f}", "Genel Güç": "{:.2f}", "Maç": "{:.0f}"}),
                        use_container_width=True
                    )
            else:
                st.info("Bu maç için güç endeksleri hesaplanamadı: " + str(guc.get("hata")))
                st.write("Yedek yöntem: piyasa oranları marjdan arındırılıp Poisson modeline uydurularak gol beklentileri bulundu → "
                         + ev + ": " + f"{ev_xg_ham:.2f}" + " | " + dep + ": " + f"{dep_xg_ham:.2f}")
