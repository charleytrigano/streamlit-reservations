
# io_utils.py — I/O Excel, schéma, ICS, palette

import os
import hashlib
from io import BytesIO
from datetime import date, datetime, timezone
import pandas as pd
import numpy as np
import streamlit as st

FICHIER = "reservations.xlsx"

# ===================== Schéma / Nettoyage =====================

BASE_COLS = [
    "paye", "nom_client", "sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%", "AAAA","MM","ical_uid"
]

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def to_date_only(x):
    if x is None or (isinstance(x, float) and np.isnan(x)) or (isinstance(x, str) and x.strip()==""):
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

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["nuitees"] = [
        (d2 - d1).days if isinstance(d1, date) and isinstance(d2, date) else np.nan
        for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
    ]

    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"]   = df["ical_uid"].fillna("")

    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)

    ordered = [c for c in BASE_COLS if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

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

# ===================== Excel I/O =====================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float) -> dict:
    # Charge toutes les feuilles pour avoir à la fois Réservations + Plateformes
    xls = pd.read_excel(path, engine="openpyxl", sheet_name=None, converters={"telephone": normalize_tel})
    return xls

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        sheets = _read_excel_cached(FICHIER, mtime)
        df = sheets.get("Sheet1") or sheets.get("Réservations") or list(sheets.values())[0]
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

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            sheets = pd.read_excel(bio, engine="openpyxl", sheet_name=None, converters={"telephone": normalize_tel})

            # normaliser réservations
            df_res = sheets.get("Sheet1") or sheets.get("Réservations") or ensure_schema(pd.DataFrame())
            df_res = ensure_schema(df_res)

            # palette éventuelle
            df_pal = sheets.get("Plateformes")
            if df_pal is None:
                df_pal = pd.DataFrame([{"plateforme": k, "couleur": v} for k,v in DEFAULT_PALETTE.items()])

            with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
                df_res.to_excel(w, index=False, sheet_name="Sheet1")
                _force_telephone_text_format_openpyxl(w, df_res, "Sheet1")
                df_pal.to_excel(w, index=False, sheet_name="Plateformes")

            st.cache_data.clear()
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    data_xlsx = b""
    try:
        # Tente de lire palette existante
        try:
            mtime = os.path.getmtime(FICHIER)
            sheets = _read_excel_cached(FICHIER, mtime)
            df_pal = sheets.get("Plateformes")
        except Exception:
            df_pal = None

        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            ensure_schema(df).to_excel(w, index=False, sheet_name="Sheet1")
            if isinstance(df_pal, pd.DataFrame):
                df_pal.to_excel(w, index=False, sheet_name="Plateformes")
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = b""
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=data_xlsx,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data_xlsx) == 0),
        help="Sauvegarde le fichier actuel (Réservations + Plateformes si présente)."
    )

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)

    # Lire palette existante
    try:
        mtime = os.path.getmtime(FICHIER)
        sheets = _read_excel_cached(FICHIER, mtime)
        df_pal = sheets.get("Plateformes")
    except Exception:
        df_pal = None

    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name="Sheet1")
            _force_telephone_text_format_openpyxl(w, out, "Sheet1")
            if isinstance(df_pal, pd.DataFrame):
                df_pal.to_excel(w, index=False, sheet_name="Plateformes")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

# ===================== Palette persistante =====================

def get_palette_from_excel() -> dict:
    if not os.path.exists(FICHIER):
        return DEFAULT_PALETTE.copy()
    try:
        mtime = os.path.getmtime(FICHIER)
        sheets = _read_excel_cached(FICHIER, mtime)
        df_pal = sheets.get("Plateformes")
        if df_pal is None or df_pal.empty:
            return DEFAULT_PALETTE.copy()
        pal = {}
        for _, r in df_pal.iterrows():
            name = str(r.get("plateforme") or "").strip()
            col = str(r.get("couleur") or "").strip()
            if name and col and col.startswith("#"):
                pal[name] = col
        if not pal:
            return DEFAULT_PALETTE.copy()
        return pal
    except Exception:
        return DEFAULT_PALETTE.copy()

def save_palette_to_excel(palette: dict):
    # Charger réservations existantes
    if os.path.exists(FICHIER):
        try:
            mtime = os.path.getmtime(FICHIER)
            sheets = _read_excel_cached(FICHIER, mtime)
            df_res = sheets.get("Sheet1") or sheets.get("Réservations") or pd.DataFrame()
        except Exception:
            df_res = pd.DataFrame()
    else:
        df_res = pd.DataFrame()

    df_res = ensure_schema(df_res)

    df_pal = pd.DataFrame(
        [{"plateforme": k, "couleur": v} for k, v in palette.items()]
    )

    with pd.ExcelWriter(FICHIER,