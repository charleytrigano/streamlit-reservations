# pages/2_➕_Ajouter.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import utils # Importe notre fichier de fonctions partagées

st.set_page_config(page_title="Ajouter Réservation", layout="wide")

st.header("➕ Ajouter une Réservation")

# Charger les données existantes
df, palette = utils.charger_donnees_csv()

with st.form("form_ajout", clear_on_submit=True):
    c1, c2 = st.columns(2)
    with c1:
        nom_client = st.text_input("**Nom du Client**")
        telephone = st.text_input("Téléphone")
        date_arrivee = st.date_input("**Date d'arrivée**", date.today())
        date_depart = st.date_input("**Date de départ**", date.today() + timedelta(days=1))
    with c2:
        plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()))
        prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, step=0.01, format="%.2f")
        commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01, format="%.2f")
        paye = st.checkbox("Payé", False)

    submitted = st.form_submit_button("✅ Ajouter la réservation")
    if submitted:
        if not nom_client or date_depart <= date_arrivee:
            st.error("Veuillez entrer un nom et des dates valides.")
        else:
            nouvelle_ligne = pd.DataFrame([{
                'nom_client': nom_client, 
                'telephone': telephone, 
                'date_arrivee': date_arrivee, 
                'date_depart': date_depart, 
                'plateforme': plateforme, 
                'prix_brut': prix_brut, 
                'commissions': commissions, 
                'paye': paye
            }])
            
            df_a_jour = pd.concat([df, nouvelle_ligne], ignore_index=True)
            df_a_jour = utils.ensure_schema(df_a_jour) # Nettoyer et calculer les champs
            
            if utils.sauvegarder_donnees_csv(df_a_jour):
                st.success(f"Réservation pour {nom_client} ajoutée.")
                st.info("Les données ont été sauvegardées. Rafraîchissez la page d'accueil pour voir les changements.")
