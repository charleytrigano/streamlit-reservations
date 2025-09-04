# pages/2_✏️_Modifier_Supprimer.py
import streamlit as st
import pandas as pd
from datetime import date
import utils

st.set_page_config(page_title="Modifier Réservation", layout="wide")
st.header("✏️ Modifier / Supprimer une Réservation")

df, palette = utils.charger_donnees_csv()

if df.empty:
    st.warning("Aucune réservation à modifier.")
else:
    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options_resa = {f"{idx}: {row['nom_client']} (Arrivée le {row['date_arrivee'].strftime('%d/%m/%Y')})": row['index'] for idx, row in df_sorted.iterrows() if pd.notna(row['date_arrivee'])}
    
    selection_str = st.selectbox("Sélectionnez une réservation", options=options_resa.keys(), index=None, placeholder="Choisissez une réservation...")
    
    if selection_str:
        original_index = options_resa[selection_str]
        resa_selectionnee = df.loc[original_index].copy()
        with st.form(f"form_modif_{original_index}"):
            st.subheader(f"Modification pour : {resa_selectionnee['nom_client']}")
            c1, c2 = st.columns(2)
            with c1:
                nom_client = st.text_input("**Nom du Client**", value=resa_selectionnee.get('nom_client', ''))
                telephone = st.text_input("Téléphone", value=resa_selectionnee.get('telephone', ''))
                date_arrivee = st.date_input("**Date d'arrivée**", value=resa_selectionnee.get('date_arrivee'))
            with c2:
                plateforme_options = list(palette.keys())
                current_plateforme = resa_selectionnee.get('plateforme')
                plateforme_index = plateforme_options.index(current_plateforme) if current_plateforme in plateforme_options else 0
                plateforme = st.selectbox("**Plateforme**", options=plateforme_options, index=plateforme_index)
                date_depart = st.date_input("**Date de départ**", value=resa_selectionnee.get('date_depart'))
                prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, value=float(resa_selectionnee.get('prix_brut', 0.0)), step=0.01, format="%.2f")
                paye = st.checkbox("Payé", value=bool(resa_selectionnee.get('paye', False)))
            btn_enregistrer, btn_supprimer = st.columns([.8, .2])
            if btn_enregistrer.form_submit_button("💾 Enregistrer"):
                updates = {'nom_client': nom_client, 'telephone': telephone, 'date_arrivee': date_arrivee, 'date_depart': date_depart, 'plateforme': plateforme, 'prix_brut': prix_brut, 'paye': paye}
                for key, value in updates.items():
                    df.loc[original_index, key] = value
                df_final = utils.ensure_schema(df)
                if utils.sauvegarder_donnees_csv(df_final):
                    st.success("Modifications enregistrées !")
            if btn_supprimer.form_submit_button("🗑️ Supprimer"):
                df_final = df.drop(index=original_index)
                if utils.sauvegarder_donnees_csv(df_final):
                    st.warning("Réservation supprimée.")
