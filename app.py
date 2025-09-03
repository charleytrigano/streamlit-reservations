# app.py — Villa Tobias (COMPLET) - Version SQLite
# Version finale basée sur les données réelles

import streamlit as st
import pandas as pd
import numpy as np
import sqlite3
import os

DB_FILE = "reservations.db"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = { "Booking": "#1e90ff", "Airbnb":  "#e74c3c", "Autre":   "#f59e0b" }

# ============================== CORE DATA FUNCTIONS ==============================
@st.cache_data
def charger_donnees():
    """Charge les données depuis la base de données SQLite."""
    if not os.path.exists(DB_FILE):
        return pd.DataFrame(), DEFAULT_PALETTE

    with sqlite3.connect(DB_FILE) as con:
        df = pd.read_sql_query("SELECT * FROM reservations", con)
        try:
            df_palette = pd.read_sql_query("SELECT * FROM plateformes", con)
            if 'nom' not in df_palette.columns and 'plateforme' in df_palette.columns:
                df_palette.rename(columns={'plateforme': 'nom'}, inplace=True)
            palette = dict(zip(df_palette['nom'], df_palette['couleur']))
        except:
            palette = DEFAULT_PALETTE.copy()

    # Convertir les colonnes de dates qui sont stockées en texte
    for col in ['date_arrivee', 'date_depart']:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

    return df, palette

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation trouvée dans la base de données.")
        return

    # S'assurer que les colonnes numériques existent avant de les utiliser
    numeric_cols = ['prix_brut', 'commissions', 'frais_cb', 'prix_net', 'menage', 'taxes_sejour', 'base', 'charges']
    for col in numeric_cols:
        if col not in df.columns:
            df[col] = 0 # Ajoute la colonne avec des zéros si elle manque
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    df_sorted = df.sort_values(by="date_arrivee", ascending=False, na_position='last').reset_index(drop=True)
    st.dataframe(df_sorted)

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df, palette = charger_donnees()
    
    st.sidebar.title("🧭 Navigation")
    pages = {
        "📋 Réservations": vue_reservations,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    
    pages[selection](df)

if __name__ == "__main__":
    main()
