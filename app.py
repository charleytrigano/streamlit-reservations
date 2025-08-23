# app.py — Villa Tobias (COMPLET)
# - Palette plateformes éditable (sidebar) + pastilles
# - Calendrier lisible sur thème sombre (cases colorées par plateforme + noms clients)
# - Restauration XLSX robuste (BytesIO) + engine="openpyxl"
# - Normalisation automatique des EN-TÊTES XLSX (aliases -> noms canoniques)
# - KPI, Recherche, Filtre Payé, Ajout/Modif/Supp, Liste clients, Rapport, Export ICS, SMS
# - Bouton vidage de cache
# - Aucune imbrication d’expander
# - Pas d'API expérimentale (st.rerun uniquement)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
from urllib.parse import quote
import colorsys
import unicodedata

FICHIER = "reservations.xlsx"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",  # bleu
    "Airbnb":  "#e74c3c",  # rouge
    "Autre":   "#f59e0b",  # orange
}

def get_palette() -> dict:
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    pal = {}
    for k, v in st.session_state.palette.items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4, 7):
            pal[k] = v
    st.session_state.palette = pal
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = {str(k): str(v) for k, v in palette.items() if k and v}

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

def render_palette_editor_sidebar():
    palette = get_palette()
    st.sidebar.markdown("## 🎨 Plateformes")
    with st.sidebar.expander("➕ Ajouter / modifier des plateformes", expanded=False):
        c1, c2 = st.columns([2,1])
        with c1:
            new_name = st.text_input("Nom de la plateforme", key="pal_new_name", placeholder="Ex: Expedia")
        with c2:
            new_color = st.color_picker("Couleur", key="pal_new_color", value="#9b59b6")
        colA, colB = st.columns(2)
        if colA.button("Ajouter / Mettre à jour"):
            name = (new_name or "").strip()
            if not name:
                st.warning("Entrez un nom de plateforme.")
            else:
                palette[name] = new_color
                save_palette(palette)
                st.success(f"✅ Plateforme « {name} » enregistrée.")
        if colB.button("Réinitialiser la palette"):
            save_palette(DEFAULT_PALETTE.copy())
            st.success("✅ Palette réinitialisée.")
    if palette:
        st.sidebar.markdown("**Plateformes existantes :**")
        for pf in sorted(palette.keys()):
            cols = st.sidebar.columns([1, 3, 1])
            with cols[0]:
                st.markdown(
                    f'<span style="display:inline-block;width:1.1em;height:1.1em;background:{palette[pf]};border-radius:3px;"></span>',
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown(f"{pf}")
            with cols[2]:
                if st.button("🗑", key=f"del_{pf}"):
                    pal = get_palette()
                    if pf in pal:
                        del pal[pf]
                        save_palette(pal)
                        st.rerun()

# ==============================  MAINTENANCE / CACHE  ==============================

def render_cache_section_sidebar():
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache et relancer"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.sidebar.success("Cache vidé. Redémarrage…")
        st.rerun()

# ==============================  OUTILS  ==============================

def to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

# ==============================  NORMALISATION EN-TÊTES XLSX  ==============================

def _slug(s: str) -> str:
    s = s.strip().lower()
    s = ''.join(c for c in unicodedata.normalize('NFKD', s) if not unicodedata.combining(c))
    for ch in ["\u00A0", "\t", "\n"]:
        s = s.replace(ch, " ")
    s = s.replace("/", " ").replace("-", " ").replace(".", " ").replace(",", " ")
    s = " ".join(s.split())
    return s

HEADER_ALIASES = {
    # prix
    "prix brut": "prix_brut", "brut": "prix_brut", "total brut": "prix_brut",
    "prix net": "prix_net", "net": "prix_net", "total net": "prix_net",
    # frais / commissions
    "commission": "commissions", "commissions": "commissions", "commission booking": "commissions",
    "frais cb": "frais_cb", "frais carte": "frais_cb", "frais carte bancaire": "frais_cb", "frais de carte": "frais_cb",
    # taxes / ménage
    "taxe sejour": "taxes_sejour", "taxes sejour": "taxes_sejour", "taxes de sejour": "taxes_sejour",
    "menage": "menage", "menage ": "menage",
    # dates / divers
    "date arrivee": "date_arrivee", "arrivee": "date_arrivee",
    "date depart": "date_depart", "depart": "date_depart",
    "plateforme": "plateforme", "plate forme": "plateforme", "plateforme ota": "plateforme",
    "client": "nom_client", "nom": "nom_client", "nom client": "nom_client",
    "telephone": "telephone", "tel": "telephone",
    "paye": "paye", "paye ": "paye", "payee": "paye", "payé": "paye",
    "sms envoye": "sms_envoye", "sms envoyé": "sms_envoye", "sms": "sms_envoye",
    "nuitees": "nuitees", "nb nuits": "nuitees", "nuit": "nuitees",
    "aaaa": "AAAA", "annee": "AAAA", "année": "AAAA",
    "mm": "MM", "mois": "MM",
    "base": "base", "charges": "charges", "%": "%", "pourcentage": "%",
    "ical uid": "ical_uid", "uid": "ical_uid",
}

def _standardize_headers(df: pd.DataFrame) -> pd.DataFrame:
    mapping = {}
    for c in df.columns:
        key = _slug(str(c))
        canon = HEADER_ALIASES.get(key)
        if canon:
            mapping[c] = canon
    if mapping:
        df = df.rename(columns=mapping)
    return df

# ==============================  SCHEMA & CALCULS  ==============================

BASE_COLS = [
    "paye", "nom_client", "sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%", "AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    if "paye" in df.columns:
        df["paye"] = df["paye"].fillna(False).astype(bool)
    if "sms_envoye" in df.columns:
        df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"]   = df["ical_uid"].fillna("")

    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df