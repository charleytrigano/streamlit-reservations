# io_utils.py — Excel I/O + helpers + maintenance (compatible vues)
import os
from io import BytesIO
from datetime import date
import pandas as pd
import numpy as np
import streamlit as st

# ============================== Constantes ==============================
FICHIER = "reservations.xlsx"
SHEET_RES = "Reservations"
SHEET_PLAT = "Plateformes"

BASE_COLS = [
    "paye", "nom_client", "sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%",
    "AAAA","MM","ical_uid"
]

# ============================== Helpers de format ==============================
def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def _to_date_only(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

# ============================== Schéma & calculs ==============================
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    # Types/valeurs
    if "paye" in df.columns:
        df["paye"] = df["paye"].fillna(False).astype(bool)
    if "sms_envoye" in df.columns:
        df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(_to_date_only)
    if "telephone" in df.columns:
        df["telephone"] = df["telephone"].apply(normalize_tel)

    num_cols = ["prix_brut","commissions","frais_cb","prix_net",
                "menage","taxes_sejour","base","charges","%","nuitees"]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Nuitéés & AAAA/MM
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    # Défauts
    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"]   = df["ical_uid"].fillna("")
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    # Calculs
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

# ============================== Totaux & tri ==============================
def _is_total_row(row: pd.Series) -> bool:
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
    mask = df.apply(_is_total_row, axis=1)
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    by = [c for c in ["date_arrivee","nom_client"] if c in df.columns]
    return df.sort_values(by=by, na_position="last").reset_index(drop=True)

# ============================== Lecture / écriture Excel ==============================
@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float) -> dict:
    # force engine openpyxl
    xl = pd.ExcelFile(path, engine="openpyxl")
    out = {}
    if SHEET_RES in xl.sheet_names:
        out[SHEET_RES] = pd.read_excel(xl, sheet_name=SHEET_RES, engine="openpyxl",
                                       converters={"telephone": normalize_tel})
    else:
        out[SHEET_RES] = pd.DataFrame()
    if SHEET_PLAT in xl.sheet_names:
        pf = pd.read_excel(xl, sheet_name=SHEET_PLAT, engine="openpyxl")
        out[SHEET_PLAT] = pf.rename(columns=str)
    else:
        out[SHEET_PLAT] = pd.DataFrame(columns=["plateforme","couleur"])
    return out

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        wb = _read_excel_cached(FICHIER, mtime)
        df = wb.get(SHEET_RES, pd.DataFrame())
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def charger_plateformes() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return pd.DataFrame(columns=["plateforme","couleur"])
    try:
        mtime = os.path.getmtime(FICHIER)
        wb = _read_excel_cached(FICHIER, mtime)
        pf = wb.get(SHEET_PLAT, pd.DataFrame(columns=["plateforme","couleur"]))
        pf = pf.rename(columns=str).fillna("")
        if "plateforme" not in pf.columns or "couleur" not in pf.columns:
            pf = pd.DataFrame(columns=["plateforme","couleur"])
        return pf
    except Exception as e:
        st.error(f"Erreur de lecture Plateformes : {e}")
        return pd.DataFrame(columns=["plateforme","couleur"])

def sauvegarder_donnees(df_res: pd.DataFrame, df_pf: pd.DataFrame | None = None):
    df_res = ensure_schema(df_res)
    if df_pf is None:
        df_pf = charger_plateformes()
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            df_res.to_excel(w, index=False, sheet_name=SHEET_RES)
            df_pf.to_excel(w, index=False, sheet_name=SHEET_PLAT)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

# ============================== UI : télécharger / restaurer / cache ==============================
def bouton_telecharger(df: pd.DataFrame):
    """Télécharge une copie de la feuille Reservations uniquement."""
    try:
        buf = BytesIO()
        df.to_excel(buf, index=False, engine="openpyxl", sheet_name=SHEET_RES)
        st.sidebar.download_button(
            "💾 Sauvegarde xlsx",
            data=buf.getvalue(),
            file_name="reservations.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            help="Télécharge une copie instantanée (feuille Reservations).",
        )
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")

def bouton_restaurer():
    """Remplace le fichier Excel actuel par celui choisi (toutes feuilles)."""
    up = st.sidebar.file_uploader("📤 Restaurer (xlsx)", type=["xlsx"],
                                  help="Remplace le fichier actuel (toutes les feuilles).")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            xl = pd.ExcelFile(bio, engine="openpyxl")

            df_res = pd.read_excel(xl, sheet_name=SHEET_RES, engine="openpyxl") \
                        if SHEET_RES in xl.sheet_names else pd.DataFrame()
            df_pf  = pd.read_excel(xl, sheet_name=SHEET_PLAT, engine="openpyxl") \
                        if SHEET_PLAT in xl.sheet_names else pd.DataFrame(columns=["plateforme","couleur"])

            sauvegarder_donnees(ensure_schema(df_res), df_pf)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

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