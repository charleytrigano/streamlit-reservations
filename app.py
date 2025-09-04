# app.py (Version de test pour lire le CSV directement)
import streamlit as st
import pandas as pd

CSV_FILE = "reservations.xlsx - Sheet1.csv"

st.set_page_config(layout="wide")
st.title("Test de Lecture du Fichier CSV")

try:
    # On essaie de lire le fichier en utilisant un point-virgule (;) comme séparateur
    df = pd.read_csv(CSV_FILE, delimiter=';')
    
    st.success(f"✅ Fichier CSV lu avec succès ! Il contient {len(df)} lignes.")
    st.write("Voici les premières lignes des données :")
    st.dataframe(df.head())
    
except FileNotFoundError:
    st.error(f"ERREUR : Le fichier '{CSV_FILE}' est introuvable. Assurez-vous qu'il est bien dans votre dépôt GitHub, dans le même dossier que ce script.")
except Exception as e:
    st.error("Une erreur est survenue lors de la lecture du fichier CSV :")
    # st.exception affichera l'erreur complète directement à l'écran
    st.exception(e)
