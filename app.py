# app.py (Test d'inspection des données)
import streamlit as st
import pandas as pd

st.set_page_config(layout="wide")
st.title("Test d'Inspection des Données")

try:
    CSV_FILE = "reservations.xlsx - Sheet1.csv"
    st.write(f"Lecture du fichier '{CSV_FILE}'...")
    df = pd.read_csv(CSV_FILE, delimiter=';')
    st.success(f"Fichier lu ! {len(df)} lignes trouvées.")
    
    st.markdown("---")
    st.subheader("1. Noms exacts des colonnes")
    st.write(df.columns.tolist())
    
    st.markdown("---")
    st.subheader("2. Types des données par colonne")
    st.write(df.dtypes.apply(lambda x: x.name))
    
    st.markdown("---")
    st.subheader("3. Aperçu de la première ligne (données brutes)")
    st.json(df.head(1).to_dict('records'))
    
    st.markdown("---")
    st.subheader("4. Test d'affichage de deux colonnes simples")
    # Assurez-vous que ces noms de colonnes correspondent EXACTEMENT à ceux affichés au point 1
    # J'utilise les noms probables basés sur vos fichiers précédents
    try:
        st.dataframe(df[['Client', 'Plateforme']])
        st.success("L'affichage de deux colonnes simples a fonctionné.")
    except Exception as e_df:
        st.error("L'affichage des deux colonnes a échoué.")
        st.exception(e_df)

except Exception as e:
    st.error("❌ ERREUR LORS DE L'INSPECTION")
    st.exception(e)
