# app.py (Version de débogage minimaliste)
import streamlit as st
import pandas as pd
import os

st.set_page_config(layout="wide")
st.title("Test de Démarrage")

st.write("✅ **Étape 1 :** Le script a démarré.")

try:
    CSV_FILE = "reservations.xlsx - Sheet1.csv"
    st.write(f"✅ **Étape 2 :** Le nom du fichier CSV est '{CSV_FILE}'. Vérification de son existence...")

    if not os.path.exists(CSV_FILE):
        st.error(f"❌ **ERREUR :** Le fichier '{CSV_FILE}' n'a pas été trouvé dans le dépôt GitHub.")
    else:
        st.write(f"✅ **Étape 3 :** Le fichier '{CSV_FILE}' a été trouvé.")
        
        df = pd.read_csv(CSV_FILE, delimiter=';')
        st.write(f"✅ **Étape 4 :** Le fichier a été lu par pandas. Il contient {len(df)} lignes.")
        
        st.header("Données Brutes du CSV")
        st.dataframe(df)
        
        st.write("✅ **Étape 5 :** Le script a terminé avec succès.")

except Exception as e:
    st.error("❌ **ERREUR INATTENDUE :** Le script a planté.")
    st.exception(e)
