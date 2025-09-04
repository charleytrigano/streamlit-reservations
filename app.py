# app.py (Version de débogage finale pour forcer l'affichage de l'erreur)
import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="wide")
st.title("🕵️‍♂️ Diagnostic Final du Fichier CSV")

CSV_FILE = "reservations.xlsx - Sheet1.csv"
st.header(f"Tentative de lecture du fichier : `{CSV_FILE}`")

try:
    if not os.path.exists(CSV_FILE):
        st.error(f"**Fichier Introuvable :** Le fichier `{CSV_FILE}` n'existe pas dans votre dépôt GitHub. Veuillez vérifier qu'il a bien été envoyé.")
    else:
        st.success(f"**Fichier Trouvé :** Le fichier `{CSV_FILE}` est bien présent.")
        
        # Lecture du fichier
        df = pd.read_csv(CSV_FILE, delimiter=';')
        st.success(f"**Lecture Réussie :** Le fichier a été lu par pandas et contient {len(df)} lignes.")
        
        # Nettoyage des colonnes
        df.columns = df.columns.str.strip()
        st.success("**Nettoyage des noms de colonnes réussi.**")

        st.subheader("Aperçu des données brutes chargées")
        st.dataframe(df.head())

except Exception as e:
    st.error("❌ UNE ERREUR CRITIQUE EST SURVENUE PENDANT LA LECTURE OU LE TRAITEMENT")
    st.write("Voici les détails exacts de l'erreur :")
    st.exception(e)
