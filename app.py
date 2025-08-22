# app.py — Villa Tobias (COMPLET, léger, restauration xlsx simple, calendrier lisible)

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

# ========= CONFIG =========
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
FICHIER = "reservations.xlsx"

# ========= PALETTE PLATEFORMES =========

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",  # bleu
    "Airbnb":  "#e74c3c",  # rouge
    "Autre":   "#f59e0b",  # orange
}

def get_palette() -> dict:
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    # nettoyage minimal
    pal = {}
    for k, v in st.session_state.palette.items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#"):
            pal[k] = v
    st.session_state.palette = pal
    return pal

def save_palette(pal: dict):
    st.session_state.palette = {str(k): str(v) for k, v in pal.items() if k and v}

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

def render_palette_editor_sidebar():
    pal = get_palette()
    st.sidebar.markdown("## 🎨 Plateformes")
    with st.sidebar.expander("➕ Ajouter / modifier des plateformes", expanded=False):
        c1, c2 = st.columns([2,1])
        with c1:
            new_name = st.text_input("Nom", key="pal_new_name", placeholder="Ex: Expedia")
        with c2:
            new_color = st.color_picker("Couleur", key="pal_new_color", value="#9b59b6")
        colA, colB = st.columns(2)
        if colA.button("Ajouter / Mettre à jour"):
            name = (new_name or "").strip()
            if not name:
                st.warning("Entrez un nom.")
            else:
                pal[name] = new_color
                save_palette(pal)
                st.success(f"✅ Plateforme « {name} » enregistrée.")
        if colB.button("Réinitialiser"):
            save_palette(DEFAULT_PALETTE.copy())
            st.success("✅ Palette réinitialisée.")
    if pal:
        st.sidebar.markdown("**Plateformes existantes :**")
        for pf in sorted(pal.keys()):
            c = st.sidebar.columns([1, 4, 1])
            c[0].markdown(
                f'<span style="display:inline-block;width:1.1em;height:1.1em;background:{pal[pf]};border-radius:3px;"></span>',
                unsafe_allow_html=True,
            )
            c[1].markdown(pf)
            if c[2].button("🗑", key=f"del_{pf}"):
                pal2 = get_palette()
                if pf in pal2:
                    del pal2[pf]
                    save_palette(pal2)
                    st.rerun()

# ========= OUTILS / SCHÉMA =========

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

BASE_COLS = [
    "paye","nom_client","sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%","AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan
    # types
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage",
              "taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # calculs
    if "date_arrivee" in df and "date_depart" in df:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
    df["MM"] = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"] = df["ical_uid"].fillna("")

    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"] = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"] = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage",
              "taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)

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

# ========= EXCEL I/O (sauvegarde & restauration très simples) =========

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    # on force l'engine openpyxl pour éviter "file format cannot be determined"
    return pd.read_excel(path, engine="openpyxl", converters={"telephone": normalize_tel})

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime)
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def _force_telephone_text_format_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
    try:
        ws = writer.sheets.get(sheet_name) or writer.sheets.get('Sheet1', None)
        if ws is None or "telephone" not in df_to_save.columns:
            return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            row[0].number_format = '@'
    except Exception:
        pass

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)