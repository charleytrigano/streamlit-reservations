# io_utils.py — lecture/écriture Excel, schéma, outils communs

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta, timezone
from io import BytesIO
import os

FICHIER = "reservations.xlsx"
PALETTE_SHEET = "Plateformes"      # feuille palette
DATA_SHEET = "Sheet1"              # feuille réservations (par défaut)

# ---------- Formats & conversions ----------

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

# ---------- Schéma & calculs ----------

BASE_COLS = [
    "paye","nom_client","sms_envoye","plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%","AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["nuitees"] = [
        (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
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
    from datetime import date as _d
    name_is_total = str(row.get("nom_client","")).strip().lower() == "total"
    pf_is_total   = str(row.get("plateforme","")).strip().lower() == "total"
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    no_dates = not isinstance(d1, _d) and not isinstance(d2, _d)
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

# ---------- Excel I/O ----------

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path, engine="openpyxl")

def _read_any_sheet(path: str, sheet: str):
    try:
        return pd.read_excel(path, sheet_name=sheet, engine="openpyxl")
    except ValueError:
        # feuille absente -> essayer la première
        xls = pd.ExcelFile(path, engine="openpyxl")
        first = xls.sheet_names[0]
        return pd.read_excel(path, sheet_name=first, engine="openpyxl")

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        _ = _read_excel_cached(FICHIER, mtime)  # déclenche le cache
        df = _read_any_sheet(FICHIER, DATA_SHEET)
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def read_palette_from_excel() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        # palette par défaut
        return pd.DataFrame({"plateforme":["Booking","Airbnb","Autre"],
                             "couleur":["#1e90ff","#e74c3c","#f59e0b"]})
    try:
        pal = pd.read_excel(FICHIER, sheet_name=PALETTE_SHEET, engine="openpyxl")
        pal = pal.rename(columns={c: c.lower() for c in pal.columns})
        if "plateforme" not in pal or "couleur" not in pal:
            raise ValueError("Feuille Plateformes invalide")
        pal["plateforme"] = pal["plateforme"].astype(str)
        pal["couleur"] = pal["couleur"].astype(str)
        return pal
    except Exception:
        return pd.DataFrame({"plateforme":["Booking","Airbnb","Autre"],
                             "couleur":["#1e90ff","#e74c3c","#f59e0b"]})

def write_palette_to_excel(pal_df: pd.DataFrame, df_resa: pd.DataFrame | None = None):
    pal_df = pal_df.copy()
    pal_df = pal_df[["plateforme","couleur"]]
    # on sauvegarde la base de réservations actuelle si fournie, sinon on relit
    if df_resa is None:
        df_resa = charger_donnees()
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            df_resa.to_excel(w, index=False, sheet_name=DATA_SHEET)
            pal_df.to_excel(w, index=False, sheet_name=PALETTE_SHEET)
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Échec d’écriture palette : {e}")

def sauvegarder_donnees(df: pd.DataFrame, keep_palette: bool = True):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)
    pal = None
    if keep_palette:
        pal = read_palette_from_excel()
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name=DATA_SHEET)
            if pal is not None:
                pal.to_excel(w, index=False, sheet_name=PALETTE_SHEET)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            # validation rapide
            _ = pd.read_excel(bio, engine="openpyxl")
            # on réécrit tel quel
            with open(FICHIER, "wb") as f:
                f.write(raw)
            st.cache_data.clear()
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    data_xlsx = b""
    try:
        pal = read_palette_from_excel()
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            ensure_schema(df).to_excel(w, index=False, sheet_name=DATA_SHEET)
            pal.to_excel(w, index=False, sheet_name=PALETTE_SHEET)
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
        help="Télécharge une copie locale."
    )

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