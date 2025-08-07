import pandas as pd
import streamlit as st
import os
from datetime import datetime

FICHIER = "reservations.xlsx"

# 📥 Charger les données du fichier Excel
def charger_donnees():
    if not os.path.exists(FICHIER):
        return pd.DataFrame()

    df = pd.read_excel(FICHIER)

    # ⏱️ Nettoyer les dates et ajouter colonnes annee / mois
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        df["annee"] = pd.to_datetime(df["date_arrivee"]).dt.year
        df["mois"] = pd.to_datetime(df["date_arrivee"]).dt.month

    if "date_depart" in df.columns:
        df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date

    return df

# 📤 Permettre à l'utilisateur d'importer un fichier Excel
def uploader_excel():
    uploaded_file = st.sidebar.file_uploader("📤 Charger un fichier Excel", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier importé et sauvegardé.")

# 💾 Téléchargement du fichier mis à jour
def telecharger_fichier_excel(df):
    st.download_button(
        label="📥 Télécharger le fichier Excel mis à jour",
        data=df.to_excel(index=False),
        file_name="reservations_mis_a_jour.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
