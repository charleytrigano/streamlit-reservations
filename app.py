# app.py (Version de diagnostic pour trouver le point de blocage)
import streamlit as st
import pandas as pd
import numpy as np

st.set_page_config(layout="wide")
st.title("🕵️‍♂️ Diagnostic du Chargement des Données")

CSV_FILE = "reservations.xlsx - Sheet1.csv"

try:
    st.write("---")
    st.write("✅ **Étape 1 :** Démarrage du script.")
    
    # Étape 2 : Lecture du fichier CSV
    df = pd.read_csv(CSV_FILE, delimiter=';')
    st.write(f"✅ **Étape 2 :** Fichier CSV lu avec succès. {len(df)} lignes trouvées.")
    
    # Étape 3 : Nettoyage des noms de colonnes (espaces)
    df.columns = df.columns.str.strip()
    st.write("✅ **Étape 3 :** Les espaces dans les noms de colonnes ont été nettoyés.")
    
    # Étape 4 : Renommage des colonnes
    rename_map = { 
        'Payé': 'paye', 'Client': 'nom_client', 'Plateforme': 'plateforme', 
        'Arrivée': 'date_arrivee', 'Départ': 'date_depart', 'Nuits': 'nuitees',
        'Brut (€)': 'prix_brut', 'Charges (€)': 'charges', 'Net (€)': 'prix_net',
        'Charges (%)': '%'
    }
    df.rename(columns=rename_map, inplace=True)
    st.write("✅ **Étape 4 :** Les colonnes ont été renommées pour être utilisées par le code.")
    
    # Étape 5 : Nettoyage et conversion des nombres
    numeric_cols = ['prix_brut', 'commissions', 'frais_cb', 'menage', 'taxes_sejour']
    for col in numeric_cols:
        if col in df.columns:
            if df[col].dtype == 'object':
                df[col] = df[col].astype(str).str.replace('€', '', regex=False).str.replace(',', '.', regex=False).str.replace(' ', '', regex=False).str.strip()
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)
    st.write("✅ **Étape 5 :** Les colonnes de chiffres (prix, commissions, etc.) ont été nettoyées et converties.")
    
    st.markdown("---")
    st.success("🎉 Le diagnostic est terminé avec succès ! Toutes les étapes ont fonctionné.")
    st.subheader("Aperçu final des données nettoyées :")
    st.dataframe(df.head())

except FileNotFoundError:
    st.error(f"❌ ERREUR à l'étape 2 : Le fichier '{CSV_FILE}' est introuvable.")
except Exception as e:
    st.error(f"❌ ERREUR INATTENDUE : Le script a planté.")
    st.exception(e)
