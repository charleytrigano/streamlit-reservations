import pandas as pd
import streamlit as st
from io import BytesIO
import base64
import os

FICHIER = "reservations.xlsx"

def charger_donnees():
    if not os.path.exists(FICHIER):
        return pd.DataFrame()
    df = pd.read_excel(FICHIER)
    df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.date
    df["date_depart"] = pd.to_datetime(df["date_depart"], errors="coerce").dt.date
    df = df[df["date_arrivee"].notna() & df["date_depart"].notna()]
    df["prix_brut"] = pd.to_numeric(df["prix_brut"], errors="coerce").round(2)
    df["prix_net"] = pd.to_numeric(df["prix_net"], errors="coerce").round(2)
    df["charges"] = (df["prix_brut"] - df["prix_net"]).round(2)
    df["%"] = ((df["charges"] / df["prix_brut"]) * 100).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
    df["nuitees"] = (pd.to_datetime(df["date_depart"]) - pd.to_datetime(df["date_arrivee"])).dt.days
    df["annee"] = pd.to_datetime(df["date_arrivee"]).dt.year
    df["mois"] = pd.to_datetime(df["date_arrivee"]).dt.month
    return df

def telecharger_fichier_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    buffer.seek(0)
    b64 = base64.b64encode(buffer.read()).decode()
    href = f'<a href="data:application/vnd.openxmlformats-officedocument.spreadsheetml.sheet;base64,{b64}" download="{FICHIER}">📥 Télécharger reservations.xlsx</a>'
    st.markdown(href, unsafe_allow_html=True)

def uploader_excel():
    fichier = st.file_uploader("Importer un fichier Excel", type="xlsx")
    if fichier:
        with open(FICHIER, "wb") as f:
            f.write(fichier.read())
        st.success("✅ Fichier importé avec succès.")
