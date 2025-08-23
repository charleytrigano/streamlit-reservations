# app.py — Villa Tobias (COMPLET, stable)
# - Réservations / Modifier-Supprimer / Plateformes / Calendrier / Rapport / Clients / ICS / SMS
# - Palette plateformes PERSISTÉE dans l'Excel (feuille 'plateformes')
# - Restauration XLSX robuste (BytesIO + engine='openpyxl')
# - Sauvegarde XLSX -> feuilles: 'reservations' + 'plateformes'
# - Calendrier en grille mensuelle, cases colorées par plateforme (fond pastel), légende
# - KPI, exports, SMS

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

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  CONSTANTES / DEFAULTS  ==============================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",  # bleu
    "Airbnb":  "#e74c3c",  # rouge
    "Autre":   "#f59e0b",  # orange
}

BASE_COLS = [
    "paye", "nom_client", "sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%", "AAAA","MM","ical_uid"
]

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
    s = str(x).strip()
    s = s.replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    # Colonnes minimales
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    # Types / defaults
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(to_date_only)

    df["telephone"] = df["telephone"].apply(normalize_tel)

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

    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"]   = df["ical_uid"].fillna("")

    # Valeurs manquantes -> 0 pour calculs
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    # Calculs
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    # Arrondis
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
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

# ==============================  EXCEL I/O  ==============================

@st.cache_data(show_spinner=False)
def _read_excel_all_sheets(path: str, mtime: float):
    """Lit toutes les feuilles en dict[str, DataFrame] avec openpyxl."""
    return pd.read_excel(path, sheet_name=None, engine="openpyxl", converters={"telephone": normalize_tel})

def _extract_res_df(book: dict) -> pd.DataFrame:
    """Récupère la feuille des réservations (Sheet1 ou reservations)."""
    df = book.get("reservations", None)
    if df is None or df.empty:
        df = book.get("Sheet1", None)
    if df is None or df.empty:
        df = pd.DataFrame()
    return df

def _extract_palette(book: dict) -> dict:
    """Récupère la palette depuis la feuille 'plateformes' (colonnes: plateforme, couleur)."""
    pal_df = book.get("plateformes", None)
    if pal_df is None or pal_df.empty:
        return DEFAULT_PALETTE.copy()
    # normaliser colonnes
    cols_lower = {c.lower(): c for c in pal_df.columns}
    k_pf = cols_lower.get("plateforme") or cols_lower.get("plateformes") or list(pal_df.columns)[0]
    k_col = cols_lower.get("couleur") or cols_lower.get("color") or (list(pal_df.columns)[1] if pal_df.shape[1] > 1 else None)
    palette = {}
    if k_pf and k_col:
        for _, r in pal_df.iterrows():
            name = str(r.get(k_pf) or "").strip()
            col = str(r.get(k_col) or "").strip()
            if name and col.startswith("#") and len(col) in (4,7):
                palette[name] = col
    if not palette:
        palette = DEFAULT_PALETTE.copy()
    return palette

def _palette_df_from_dict(palette: dict) -> pd.DataFrame:
    return pd.DataFrame({"plateforme": list(palette.keys()), "couleur": list(palette.values())})

def charger_donnees():
    """Charge df réservations + palette persistée."""
    # Fichier absent -> df vide + palette par défaut
    if not os.path.exists(FICHIER):
        st.session_state.palette = DEFAULT_PALETTE.copy()
        return ensure_schema(pd.DataFrame())

    try:
        mtime = os.path.getmtime(FICHIER)
        book = _read_excel_all_sheets(FICHIER, mtime)

        # Réservations
        df = _extract_res_df(book)
        df = ensure_schema(df)

        # Palette persistée -> session_state
        pal = _extract_palette(book)
        st.session_state.palette = pal

        return df
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        if "palette" not in st.session_state:
            st.session_state.palette = DEFAULT_PALETTE.copy()
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

def _get_palette() -> dict:
    pal = st.session_state.get("palette", None)
    if not isinstance(pal, dict) or not pal:
        pal = DEFAULT_PALETTE.copy()
        st.session_state.palette = pal
    # nettoyer
    out = {}
    for k, v in pal.items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4,7) and k.strip():
            out[k.strip()] = v
    st.session_state.palette = out
    return out

def sauvegarder_donnees(df: pd.DataFrame):
    """Sauvegarde les réservations + la palette dans 2 feuilles."""
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)

    pal = _get_palette()
    pal_df = _palette_df_from_dict(pal)

    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name="reservations")
            pal_df.to_excel(w, index=False, sheet_name="plateformes")
            _force_telephone_text_format_openpyxl(w, out, "reservations")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")