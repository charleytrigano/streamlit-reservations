# pages/3_✏️_Modifier_Supprimer.py
import streamlit as st
import pandas as pd
from datetime import date, timedelta
import utils # Importe notre fichier de fonctions partagées

st.set_page_config(page_title="Modifier Réservation", layout="wide")

st.header("✏️ Modifier / Supprimer une Réservation")

df, palette = utils.charger_donnees_csv()

if df.empty:
    st.warning("Aucune réservation à modifier.")
else:
    # Créer une copie pour éviter de modifier l'original directement dans la session
    df_copy = df.copy()
    df_sorted = df_copy.sort_values(by="date_arrivee", ascending=False).reset_index(drop=True)
    
    # Créer les options pour le selectbox en utilisant le nouvel index (0, 1, 2...)
    options_resa = {
        f"{idx}: {row['nom_client']} (Arrivée le {row['date_arrivee'].strftime('%d/%m/%Y')})": idx 
        for idx, row in df_sorted.iterrows() if pd.notna(row['date_arrivee'])
    }
    
    selection_str = st.selectbox(
        "Sélectionnez une réservation", 
        options=options_resa.keys(), 
        index=None, 
        placeholder="Choisissez une réservation..."
    )
    
    if selection_str:
        # Retrouver l'index (0, 1, 2...) de la ligne sélectionnée dans df_sorted
        idx_selection = options_resa[selection_str]
        resa_selectionnee = df_sorted.loc[idx_selection].copy()
        
        with st.form(f"form_modif_{idx_selection}"):
            st.subheader(f"Modification de la réservation pour : {resa_selectionnee['nom_client']}")
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
            
            if btn_enregistrer.form_submit_button("💾 Enregistrer les modifications"):
                if date_depart <= date_arrivee:
                    st.error("La date de départ doit être après la date d'arrivée.")
                else:
                    updates = {
                        'nom_client': nom_client, 'telephone': telephone, 'date_arrivee': date_arrivee, 
                        'date_depart': date_depart, 'plateforme': plateforme, 'prix_brut': prix_brut, 
                        'paye': paye
                    }
                    # Mettre à jour la ligne directement dans df_sorted
                    for key, value in updates.items():
                        df_sorted.loc[idx_selection, key] = value
                    
                    # Retrouver l'index original pour le mettre à jour dans le df principal
                    original_index = df_sorted.index[idx_selection]
                    df.iloc[original_index] = df_sorted.iloc[idx_selection]

                    df_final = utils.ensure_schema(df)
                    if utils.sauvegarder_donnees_csv(df_final):
                        st.success("Modifications enregistrées !")
                        st.rerun()

            if btn_supprimer.form_submit_button("🗑️ Supprimer"):
                # Retrouver l'index original dans le df non trié
                original_index = df[
                    (df['nom_client'] == resa_selectionnee['nom_client']) &
                    (df['date_arrivee'] == resa_selectionnee['date_arrivee'])
                ].index[0]

                df_final = df.drop(index=original_index)
                if utils.sauvegarder_donnees_csv(df_final):
                    st.warning("Réservation supprimée.")
                    st.rerun()
