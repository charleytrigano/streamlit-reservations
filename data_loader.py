import streamlit as st
import pandas as pd
from io import BytesIO

FICHIER = "reservations.xlsx"

# 📤 Uploader un fichier Excel
def uploader_excel():
    uploaded_file = st.sidebar.file_uploader("Importer un fichier Excel", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier importé avec succès")

# 📥 Charger le fichier
def charger_donnees():
    try:
        df = pd.read_excel(FICHIER)
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
        df["prix_brut"] = pd.to_numeric(df["prix_brut"], errors="coerce")
        df["prix_net"] = pd.to_numeric(df["prix_net"], errors="coerce")
        df["charges"] = (df["prix_brut"] - df["prix_net"]).round(2)
        df["%"] = ((df["charges"] / df["prix_brut"]) * 100).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
        df["nuitees"] = (pd.to_datetime(df["date_depart"]) - pd.to_datetime(df["date_arrivee"])).dt.days
        df["annee"] = pd.to_datetime(df["date_arrivee"]).dt.year
        df["mois"] = pd.to_datetime(df["date_arrivee"]).dt.month
        return df
    except Exception as e:
        st.error(f"Erreur de chargement : {e}")
        return pd.DataFrame()

# 📤 Bouton de téléchargement Excel
def telecharger_fichier_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    st.download_button(
        label="📥 Télécharger le fichier Excel",
        data=buffer.getvalue(),
        file_name="reservations_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
