# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib, json
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO

# ============================== VERSION / CONFIG ==============================
APP_VERSION = "2025-09-09-01"  # <<--- incrémente ce numéro pour forcer le vidage cache
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# --- HARD CLEAR (lié à APP_VERSION) ---
try:
    st.session_state["_app_version"]
except Exception:
    st.session_state["_app_version"] = None

if st.session_state["_app_version"] != APP_VERSION:
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    st.session_state["_app_version"] = APP_VERSION
    st.toast("♻️ Cache vidé automatiquement (version changée)", icon="✅")

CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# ============================== STYLE ==============================
def apply_style(light: bool):
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    st.markdown(
        f"""
        <style>
          html, body, [data-testid="stAppViewContainer"] {{
            background: {bg}; color: {fg};
          }}
          [data-testid="stSidebar"] {{
            background: {side}; border-right: 1px solid {border};
          }}
          .glass {{ background: rgba(255,255,255,0.06); border-radius:12px; padding:10px; }}
          .chip {{ display:inline-block; background:#444; color:#fff;
                  padding:4px 8px; border-radius:8px; margin:2px; font-size:0.85rem }}
        </style>
        """,
        unsafe_allow_html=True
    )

# ============================== DATA HELPERS ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
    "base","charges","%","res_id","ical_uid","AAAA","MM"
]

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3: return df
        except Exception: continue
    return pd.DataFrame()

def _to_num(s): return pd.to_numeric(pd.Series(s).astype(str).str.replace("€","").str.replace(",","."), errors="coerce")

def _to_date(s): return pd.to_datetime(s, errors="coerce", dayfirst=True).dt.date

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame(columns=BASE_COLS)
    df = df.copy()
    for c in BASE_COLS:
        if c not in df.columns: df[c] = None
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])
    df["AAAA"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year
    df["MM"]   = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.month
    miss = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss.any(): df.loc[miss,"res_id"] = [str(uuid.uuid4()) for _ in range(miss.sum())]
    return df[BASE_COLS]

@st.cache_data
def _load_file_bytes(path: str):
    try:
        with open(path,"rb") as f: return f.read()
    except: return None

@st.cache_data
def charger_donnees():
    raw = _load_file_bytes(CSV_RESERVATIONS)
    df = ensure_schema(_detect_delimiter_and_read(raw)) if raw else pd.DataFrame(columns=BASE_COLS)
    rawp = _load_file_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        pal = _detect_delimiter_and_read(rawp)
        if "plateforme" in pal and "couleur" in pal: palette = dict(zip(pal["plateforme"], pal["couleur"]))
    return df, palette

def sauvegarder_donnees(df):
    out = ensure_schema(df).copy()
    for c in ["date_arrivee","date_depart"]:
        out[c] = pd.to_datetime(out[c], errors="coerce").dt.strftime("%d/%m/%Y")
    out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
    st.cache_data.clear(); return True

# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    arr = df[df["date_arrivee"]==today][["nom_client","telephone","plateforme"]]
    dep = df[df["date_depart"]==today][["nom_client","telephone","plateforme"]]
    st.subheader("🟢 Arrivées du jour")
    st.dataframe(arr if not arr.empty else pd.DataFrame([{"nom_client":"Aucune"}]))
    st.subheader("🔴 Départs du jour")
    st.dataframe(dep if not dep.empty else pd.DataFrame([{"nom_client":"Aucun"}]))

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    st.dataframe(df, use_container_width=True)

# ============================== ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button("Télécharger CSV", df.to_csv(sep=";", index=False).encode("utf-8"), file_name=CSV_RESERVATIONS, mime="text/csv")
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        df_new = ensure_schema(_detect_delimiter_and_read(up.read()))
        sauvegarder_donnees(df_new)
        st.success("Fichier restauré"); st.rerun()
    if st.sidebar.button("🧹 Vider le cache"):
        st.cache_data.clear(); st.cache_resource.clear(); st.rerun()

# ============================== MAIN ==============================
def main():
    apply_style(True)
    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette = charger_donnees()
    pages = {"🏠 Accueil": vue_accueil, "📋 Réservations": vue_reservations}
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()