# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

CSV_RESERVATIONS = "reservations_normalise.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# ============================== STYLE ==============================
def apply_style():
    st.markdown(
        """
        <style>
          .chip {
            display:inline-block; background:#333; color:#eee;
            padding:4px 8px; border-radius:12px; margin:4px; font-size:0.9rem;
          }
        </style>
        """, unsafe_allow_html=True
    )

# ============================== DATA ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
    "base","charges","%","res_id","ical_uid","AAAA","MM"
]

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff","")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3: return df
        except Exception: continue
    return pd.DataFrame()

def _to_num(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype="float64")
    sc = (
        s.astype(str)
         .str.replace("€","",regex=False)
         .str.replace(" ","",regex=False)
         .str.replace(",",".",regex=False)
         .str.strip()
    )
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype="object")
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return d.dt.date

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty: return pd.DataFrame(columns=BASE_COLS)
    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    for c in BASE_COLS:
        if c not in df.columns: df[c] = None

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Recalcul AAAA / MM
    da_all = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = pd.to_numeric(da_all.dt.year, errors="coerce")
    df["MM"]   = pd.to_numeric(da_all.dt.month, errors="coerce")

    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    try:
        with open(CSV_RESERVATIONS,"rb") as f: raw = f.read()
        df = _detect_delimiter_and_read(raw)
    except Exception:
        df = pd.DataFrame()
    return ensure_schema(df), DEFAULT_PALETTE

# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"Aujourd'hui : {today.strftime('%d/%m/%Y')}")

    arr = df[df["date_arrivee"]==today][["nom_client","telephone","plateforme"]]
    dep = df[df["date_depart"]==today][["nom_client","telephone","plateforme"]]