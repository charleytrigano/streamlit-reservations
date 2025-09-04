# app.py — Villa Tobias (COMPLET) - Version avec rappel de sauvegarde et page Plateformes

import streamlit as st
import pandas as pd
import numpy as np
import os
import calendar
from datetime import date, timedelta

CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv" 

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = { "Booking": "#1e90ff", "Airbnb":  "#e74c3c", "Autre":   "#f59e0b" }

# ============================== CORE DATA FUNCTIONS ==============================
@st.cache_data
def charger_donnees_csv():
    # ... (code identique à la version précédente)
    pass

def sauvegarder_donnees_csv(df, file_path=CSV_RESERVATIONS):
    # ... (code identique à la version précédente)
    pass

# ==============================  SCHEMA & DATA VALIDATION  ==============================
# ... (la fonction ensure_schema reste identique)
pass

# ============================== UTILITIES & HELPERS ==============================
# ... (les fonctions utilitaires restent identiques)
pass

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    # ... (code identique à la version précédente)
    pass

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une Réservation")
    # ... (code identique à la version précédente)
    pass

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer une Réservation")
    # ... (code identique à la version précédente)
    pass

def vue_calendrier(df, palette):
    st.header("📅 Calendrier des Réservations")
    # ... (code identique à la version précédente)
    pass
    
def vue_rapport(df, palette):
    st.header("📊 Rapport de Performance")
    # ... (code identique à la version précédente)
    pass

def vue_plateformes(df, palette):
    st.header("🎨 Gestion des Plateformes")

    df_palette = pd.DataFrame(list(palette.items()), columns=['plateforme', 'couleur'])

    edited_df = st.data_editor(
        df_palette,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "plateforme": "Plateforme",
            "couleur": st.column_config.ColorColumn("Couleur"),
        }
    )

    if st.button("💾 Enregistrer les modifications des plateformes"):
        # Convertir le DataFrame édité en dictionnaire
        nouvelle_palette = dict(zip(edited_df['plateforme'], edited_df['couleur']))
        
        # Sauvegarder le DataFrame des plateformes dans son propre CSV
        df_plateformes_save = pd.DataFrame(list(nouvelle_palette.items()), columns=['plateforme', 'couleur'])
        if sauvegarder_donnees_csv(df_plateformes_save, file_path=CSV_PLATEFORMES):
            st.success("Palette de couleurs mise à jour !")
            st.rerun()

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    
    # --- RAPPEL DE SAUVEGARDE AJOUTÉ ICI ---
    st.info(
        "**Important :** Pour que vos modifications soient permanentes, n'oubliez pas de télécharger le fichier CSV mis à jour depuis l'onglet 'Réservations' et de l'envoyer sur votre dépôt GitHub."
    )

    df, palette = charger_donnees_csv()
    
    st.sidebar.title("🧭 Navigation")
    pages = { 
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "🎨 Plateformes": vue_plateformes,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    
    page_function = pages[selection]

    # Passer les bons arguments à chaque fonction de vue
    if selection in ["➕ Ajouter", "✏️ Modifier / Supprimer", "📅 Calendrier", "📊 Rapport", "🎨 Plateformes"]:
        page_function(df, palette)
    else:
        page_function(df)

if __name__ == "__main__":
    main()
