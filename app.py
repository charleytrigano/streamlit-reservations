# app.py — Villa Tobias (COMPLET) - Version SQLite
# Version finale avec toutes les corrections

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

    df = ensure_schema(df)
    return df, palette

# ==============================  SCHEMA & DATA VALIDATION  ==============================
def ensure_schema(df):
    df_res = df.copy()
    
    # S'assurer que les colonnes de base existent
    for col in ['paye', 'nom_client', 'date_arrivee', 'date_depart', 'prix_brut', 'commissions']:
        if col not in df_res.columns:
            df_res[col] = None

    # Convertir les dates
    for col in ['date_arrivee', 'date_depart']:
        df_res[col] = pd.to_datetime(df_res[col], errors='coerce').dt.date

    # Nettoyer et convertir les nombres
    numeric_cols = [
        'prix_brut', 'commissions', 'frais_cb', 'prix_net', 'menage', 
        'taxes_sejour', 'base', 'charges', 'nuitees'
    ]
    for col in numeric_cols:
        if col in df_res.columns:
            if df_res[col].dtype == 'object':
                # Gère les formats comme "67 49 €" ou "150,50"
                df_res[col] = df_res[col].astype(str).str.replace('€', '', regex=False).str.replace(',', '.', regex=False).str.replace(' ', '', regex=False).str.strip()
            df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)

    return df_res

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation trouvée dans la base de données.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False, na_position='last').reset_index(drop=True)
    st.dataframe(df_sorted)

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df, palette = charger_donnees()
    
    st.sidebar.title("🧭 Navigation")
    pages = { "📋 Réservations": vue_reservations }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    
    pages[selection](df)

if __name__ == "__main__":
    main()
