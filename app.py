# app.py (Test de chargement simple)
import streamlit as st
import pandas as pd
import utils # Nous utilisons juste les constantes de ce fichier

st.set_page_config(layout="wide")
st.title("Test de Chargement Simple")

st.info("Ce test vide le cache et essaie de lire le fichier CSV sans aucun traitement.")

st.write("Vidage du cache...")
st.cache_data.clear()
st.success("Cache vidé.")

st.write(f"Tentative de chargement des données BRUTES depuis '{utils.CSV_RESERVATIONS}'...")

try:
    df = pd.read_csv(utils.CSV_RESERVATIONS, delimiter=';')
    st.success(f"✅ SUCCÈS ! {len(df)} lignes brutes ont été chargées.")
    st.subheader("Aperçu des données brutes :")
    st.dataframe(df.head())
except Exception as e:
    st.error("❌ ERREUR lors de la lecture simple du fichier CSV.")
    st.exception(e)
