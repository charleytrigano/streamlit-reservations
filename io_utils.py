import streamlit as st
import pandas as pd
import numpy as np
import os
from io import BytesIO

FICHIER = "reservations.xlsx"

BASE_COLS = [
    "paye", "nom_client", "sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan
    return df

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path, engine="openpyxl")

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

def sauvegarder_donnees(df: pd.DataFrame):
    try:
        df.to_excel(FICHIER, index=False, engine="openpyxl")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"])
    if up is not None:
        try:
            df_new = pd.read_excel(up, engine="openpyxl")
            df_new = ensure_schema(df_new)
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    try:
        ensure_schema(df).to_excel(buf, index=False, engine="openpyxl")
        st.sidebar.download_button(
            "💾 Sauvegarde xlsx",
            data=buf.getvalue(),
            file_name="reservations.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")