# app.py — Villa Tobias (COMPLET, stable)
# - Fix "DataFrame is ambiguous" : jamais de `if df:` ; on utilise .empty / not None
# - Restauration XLSX via BytesIO + engine="openpyxl"
# - Feuille "Plateformes" optionnelle dans reservations.xlsx (nom | couleur)
# - Tous les onglets : Réservations, Ajouter, Modifier/Supprimer, Calendrier, Rapport, Clients, Export ICS, SMS, Plateformes
# - Palette chargée/sauvegardée depuis/vers Excel (si possible), sinon session_state

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

FICHIER = "reservations.xlsx"
SHEET_RESAS = "Sheet1"         # feuille des réservations (par défaut)
SHEET_PLATF = "Plateformes"    # feuille optionnelle palette plateformes

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")


# ==============================  HELPERS GÉNÉRIQUES  ==============================
def not_empty(x) -> bool:
    """True si x est un DataFrame non vide ; False sinon."""
    return isinstance(x, pd.DataFrame) and not x.empty


# ==============================  PALETTE (PLATEFORMES) ==============================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",  # bleu
    "Airbnb":  "#e74c3c",  # rouge
    "Autre":   "#f59e0b",  # orange
}

def _clean_palette_dict(d: dict) -> dict:
    out = {}
    for k, v in (d or {}).items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4, 7) and k.strip():
            out[k.strip()] = v
    return out if out else DEFAULT_PALETTE.copy()

def _read_palette_from_excel(path: str) -> dict:
    try:
        if not os.path.exists(path):
            return DEFAULT_PALETTE.copy()
        xls = pd.ExcelFile(path, engine="openpyxl")
        if SHEET_PLATF not in xls.sheet_names:
            return DEFAULT_PALETTE.copy()
        dfp = pd.read_excel(xls, sheet_name=SHEET_PLATF, engine="openpyxl")
        if not not_empty(dfp):
            return DEFAULT_PALETTE.copy()
        # colonnes attendues : 'plateforme', 'couleur'
        # on accepte aussi 'Plateforme', 'Couleur'
        cols = {c.lower(): c for c in dfp.columns}
        if "plateforme" not in cols or "couleur" not in cols:
            return DEFAULT_PALETTE.copy()
        pal = dict(zip(dfp[cols["plateforme"]].astype(str), dfp[cols["couleur"]].astype(str)))
        return _clean_palette_dict(pal)
    except Exception:
        return DEFAULT_PALETTE.copy()

def _write_palette_to_excel(writer, palette: dict):
    pal = _clean_palette_dict(palette)
    dfp = pd.DataFrame(sorted(pal.items()), columns=["plateforme", "couleur"])
    dfp.to_excel(writer, index=False, sheet_name=SHEET_PLATF)

def get_palette() -> dict:
    # session_state d'abord
    if "palette" in st.session_state:
        return _clean_palette_dict(st.session_state.palette)
    # sinon tenter depuis Excel
    pal = _read_palette_from_excel(FICHIER)
    st.session_state.palette = pal.copy()
    return pal

def save_palette(palette: dict):
    st.session_state.palette = _clean_palette_dict(palette)

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

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
    """Force la lecture du téléphone en TEXTE, retire .0 éventuel, espaces, et garde le +."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

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

    # Booléens
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    # Dates
    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(to_date_only)

    # Téléphone
    df["telephone"] = df["telephone"].apply(normalize_tel)

    # Numériques
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Nuitées
    df["nuitees"] = [
        (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
        for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
    ]

    # AAAA/MM
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    # Défauts texte
    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"]   = df["ical_uid"].fillna("")

    # Calculs
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    # Arrondis
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)

    # Ordre
    ordered_cols = [c for c in BASE_COLS if c in df.columns]
    rest_cols = [c for c in df.columns if c not in ordered_cols]
    return df[ordered_cols + rest_cols]

def is_total_row(row: pd.Series) -> bool:
    name_is_total = str(row.get("nom_client","")).strip().lower() == "total"
    pf_is_total   = str(row.get("plateforme","")).strip().lower() == "total"
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    no_dates = not isinstance(d1, date) and not isinstance(d2, date)
    has_money = any(pd.notna(row.get(c)) and float(row.get(c) or 0) != 0
                    for c in ["prix_brut","prix_net","base","charges"])
    return name_is_total or pf_is_total or (no_dates and has_money)

def split_totals(df: pd.DataFrame):
    if df is None or df.empty:
        return df, df
    mask = df.apply(is_total_row, axis=1)
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    by = [c for c in ["date_arrivee","nom_client"] if c in df.columns]
    return df.sort_values(by=by, na_position="last").reset_index(drop=True)


# ==============================  EXCEL I/O  ==============================
@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float) -> pd.DataFrame:
    # On lit UNIQUEMENT la feuille de réservations
    return pd.read_excel(path, engine="openpyxl", sheet_name=SHEET_RESAS,
                         converters={"telephone": normalize_tel})

def _read_full_excel(path: str):
    """Retourne (df_resa, palette_dict) à partir du fichier Excel."""
    df_resa = ensure_schema(pd.DataFrame())
    pal = DEFAULT_PALETTE.copy()
    if not os.path.exists(path):
        return df_resa, pal
    try:
        xls = pd.ExcelFile(path, engine="openpyxl")
        # réservations
        if SHEET_RESAS in xls.sheet_names:
            df_resa = pd.read_excel(xls, sheet_name=SHEET_RESAS, engine="openpyxl",
                                    converters={"telephone": normalize_tel})
            df_resa = ensure_schema(df_resa)
        # plateformes
        pal = _read_palette_from_excel(path)
        return df_resa, pal
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return df_resa, pal

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER