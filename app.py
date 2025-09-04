# app.py (Page d'accueil)
import streamlit as st
import pandas as pd
import utils

st.set_page_config(page_title="Accueil - Réservations", layout="wide")

st.title("📖 Gestion des Réservations - Villa Tobias")
st.info("**Important :** Pour rendre vos modifications permanentes, téléchargez le fichier CSV et envoyez-le sur GitHub.")

df, palette = utils.charger_donnees_csv()

st.header("📋 Liste des Réservations")
if df.empty:
    st.info("Aucune réservation trouvée.")
else:
    df_sorted = df.sort_values(by="date_arrivee", ascending=False, na_position='last').reset_index(drop=True)
    column_config={ "paye": st.column_config.CheckboxColumn("Payé"), "nuitees": st.column_config.NumberColumn("Nuits", format="%d"), "prix_brut": st.column_config.NumberColumn("Prix Brut", format="%.2f €"), "date_arrivee": st.column_config.DateColumn("Arrivée", format="DD/MM/YYYY"), "date_depart": st.column_config.DateColumn("Départ", format="DD/MM/YYYY"), }
    st.dataframe(df_sorted, column_config=column_config, use_container_width=True)

# Administration dans la barre latérale
st.sidebar.markdown("---")
st.sidebar.header("⚙️ Administration")
st.sidebar.download_button(label="Télécharger la sauvegarde (CSV)", data=df.to_csv(sep=';', index=False).encode('utf-8'), file_name=utils.CSV_RESERVATIONS, mime='text/csv')
# La fonction de restauration sera ajoutée plus tard
