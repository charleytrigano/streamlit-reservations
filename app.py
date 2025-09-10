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

# --- Purge du cache à chaque lancement ---
try:
    st.cache_data.clear()
    st.cache_resource.clear()
except Exception:
    pass

CSV_RESERVATIONS = "reservations_normalise.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# ============================== HELPERS ==============================
def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: 
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ","]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3:
                return df
        except Exception:
            continue
    return pd.read_csv(StringIO(txt), dtype=str)

def _to_bool_series(s: pd.Series) -> pd.Series:
    return s.astype(str).str.strip().str.lower().isin(["true","1","oui","yes","y","vrai"]).fillna(False)

def _to_num(s: pd.Series) -> pd.Series:
    sc = (
        s.astype(str)
        .str.replace("€","",regex=False)
        .str.replace(" ","",regex=False)
        .str.replace(",",".",regex=False)
        .str.strip()
    )
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return d.dt.date

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

# ============================== DATA ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
    "base","charges","%","res_id","ical_uid","AAAA","MM"
]

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b])

    # Numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Nuitées recalculées
    mask = df["date_arrivee"].notna() & df["date_depart"].notna()
    if mask.any():
        da = pd.to_datetime(df.loc[mask,"date_arrivee"])
        dd = pd.to_datetime(df.loc[mask,"date_depart"])
        df.loc[mask,"nuitees"] = (dd-da).dt.days.clip(lower=0)

    # Prix net / charges / base / %
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).fillna(0.0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).fillna(0.0)

    pct = np.where(df["prix_brut"]>0, (df["charges"]/df["prix_brut"]*100), 0)
    df["%"] = pd.Series(pct, index=df.index).fillna(0.0)

    # AAAA / MM
    da_all = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = pd.to_numeric(da_all.dt.year, errors="coerce")
    df["MM"]   = pd.to_numeric(da_all.dt.month, errors="coerce")

    # res_id & ical_uid
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    df.loc[miss_res,"res_id"] = [str(uuid.uuid4()) for _ in range(miss_res.sum())]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    try:
        raw = open(CSV_RESERVATIONS,"rb").read()
        base_df = _detect_delimiter_and_read(raw)
    except Exception:
        base_df = pd.DataFrame()
    return ensure_schema(base_df), DEFAULT_PALETTE

# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    arr = df[df["date_arrivee"]==today][["nom_client","telephone","plateforme"]]
    dep = df[df["date_depart"]==today][["nom_client","telephone","plateforme"]]

    st.subheader("🟢 Arrivées du jour")
    st.dataframe(arr if not arr.empty else pd.DataFrame([{"nom_client":"Aucune"}]))

    st.subheader("🔴 Départs du jour")
    st.dataframe(dep if not dep.empty else pd.DataFrame([{"nom_client":"Aucun"}]))

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty: 
        st.info("Aucune réservation"); return

    years = ["Toutes"] + sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True).tolist()
    year = st.selectbox("Année", years)

    if year!="Toutes":
        df = df[df["AAAA"]==int(year)]

    st.dataframe(df,use_container_width=True)

# ============================== MAIN ==============================
def main():
    df, palette = charger_donnees()
    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)

if __name__ == "__main__":
    main()