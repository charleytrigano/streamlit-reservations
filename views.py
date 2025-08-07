# views.py (ajout progressif)
import streamlit as st
import pandas as pd

FICHIER = "reservations.xlsx"

def afficher_reservations(df):
    st.title("📋 Réservations")
    if df.empty:
        st.info("Aucune réservation à afficher.")
    else:
        if "identifiant" in df.columns:
            df = df.drop(columns=["identifiant"])
        st.dataframe(df)
