import streamlit as st
import requests
import numpy as np
import pandas as pd
import json
import os
from datetime import datetime

st.set_page_config(page_title="Pro Monte Carlo & Skor Analiz Paneli", page_icon="⚽", layout="wide")

try:
    ODDS_API_KEY = st.secrets["ODDS_API_KEY"]
except Exception:
    ODDS_API_KEY = os.getenv("ODDS_API_KEY", "")
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


# --- GENİŞLETİLMİŞ AKILLI TAKIM ID EŞLEŞTİRME SÖZLÜĞÜ ---
SOFASCORE_TAKIM_IDLERI = {
    "Galatasaray": 2993,
    "Fenerbahce": 2999,
    "Besiktas": 2987,
    "Trabzonspor": 2989,
    "Basaksehir": 10534,
