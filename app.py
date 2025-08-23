import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, datetime, timezone
from io import BytesIO
import hashlib
import os
import colorsys

FICHIER = "reservations.xlsx"

# ============================== CONFIG ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

# ============================== PALETTE ==============================
def get_palette():
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    return st.session_state.palette

def save_palette(p):
    st.session_state.palette = p

def platform_badge(name, palette):
    color = palette.get(name, "#999999")
    return f'<span style="background:{color};padding:2px 6px;border-radius:3px;">{name}</span>'

# ============================== OUTILS ==============================
def to_date_only(x):
    try: return pd.to_datetime(x).date()
    except: return None

def normalize_tel(x):
    if pd.isna(x): return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"): s = s[:-2]
    return s

BASE_COLS = [
    "paye","nom_client","sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%","AAAA","MM","ical_uid"
]

def ensure_schema(df):
    if df is None: df = pd.DataFrame()
    for c in BASE_COLS:
        if c not in df.columns: df[c] = np.nan
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee","date_depart"]: df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    df["nuitees"] = [(d2-d1).days if (isinstance(d1,date) and isinstance(d2,date)) else 0
                     for d1,d2 in zip(df["date_arrivee"],df["date_depart"])]
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d,date) else np.nan).astype("Int64")
    df["MM"] = df["date_arrivee"].apply(lambda d: d.month if isinstance(d,date) else np.nan).astype("Int64")
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(0)
    df["base"] = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(0)
    df["charges"] = (df["prix_brut"] - df["prix_net"]).clip(0)
    df["%"] = (df["charges"]/df["prix_brut"]*100).replace([np.inf,-np.inf],0).fillna(0).round(2)
    return df

# ============================== EXCEL I/O ==============================
@st.cache_data
def _read_excel(path, mtime):
    return pd.read_excel(path, engine="openpyxl", converters={"telephone": normalize_tel})

def charger_donnees():
    if not os.path.exists(FICHIER): return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel(FICHIER, mtime)
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur Excel: {e}")
        return ensure_schema(pd.DataFrame())

def sauvegarder_donnees(df):
    df = ensure_schema(df)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            df.to_excel(w, index=False)
        st.cache_data.clear()
        st.success("💾 Sauvegarde effectuée.")
    except Exception as e:
        st.error(f"Sauvegarde impossible: {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer xlsx", type=["xlsx"])
    if up is not None:
        try:
            bio = BytesIO(up.read())
            df_new = pd.read_excel(bio, engine="openpyxl", converters={"telephone": normalize_tel})
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df):
    buf = BytesIO()
    ensure_schema(df).to_excel(buf, index=False, engine="openpyxl")
    st.sidebar.download_button("💾 Télécharger xlsx", buf.getvalue(),
        file_name="reservations.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ============================== VUES ==============================
def vue_reservations(df):
    palette = get_palette()
    st.title("📋 Réservations")
    st.markdown("### Plateformes")
    st.markdown(" ".join([platform_badge(p,palette) for p in palette]), unsafe_allow_html=True)

    edited = st.data_editor(df, use_container_width=True, num_rows="dynamic")
    if st.button("💾 Sauvegarder"):
        sauvegarder_donnees(edited)
        st.rerun()

    for i,row in edited.iterrows():
        col1,col2 = st.columns(2)
        if col1.button(f"✏️ Modifier {row['nom_client']}", key=f"edit_{i}"):
            st.info(f"(Simulation) Modification de {row['nom_client']}")
        if col2.button(f"🗑 Supprimer {row['nom_client']}", key=f"del_{i}"):
            edited = edited.drop(i)
            sauvegarder_donnees(edited)
            st.rerun()

def vue_calendrier(df):
    palette = get_palette()
    st.title("📅 Calendrier")
    if df.empty: return st.info("Aucune donnée.")
    mois = st.selectbox("Mois", list(calendar.month_name)[1:], index=date.today().month-1)
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()), index=0)
    mois_index = list(calendar.month_name).index(mois)
    monthcal = calendar.monthcalendar(int(annee), mois_index)
    core = df.copy()

    planning = {}
    for _,r in core.iterrows():
        if isinstance(r["date_arrive