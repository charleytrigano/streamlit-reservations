import streamlit as st
import pandas as pd
import os

FICHIER = "reservations.xlsx"

def uploader_excel():
    uploaded_file = st.file_uploader("Déposez un fichier Excel", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df.to_excel(FICHIER, index=False)
        st.success("✅ Fichier importé avec succès.")

def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)
        return df
    return pd.DataFrame()

def telecharger_fichier_excel(df):
    st.download_button(
        "📥 Télécharger le fichier Excel",
        data=df.to_excel(index=False),
        file_name="reservations_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
