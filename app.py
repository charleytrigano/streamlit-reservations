# app.py — Villa Tobias (COMPLET) - Version Google Sheets Finale

import streamlit as st
import pandas as pd
import numpy as np
import os
import calendar
from datetime import date, timedelta

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ============================== CORE DATA FUNCTIONS ==============================
@st.cache_data(ttl=60)
def charger_donnees():
    """Charge les données depuis la Google Sheet via la connexion intégrée."""
    try:
        conn = st.connection("gsheets", type=st.connections.GSheetsConnection)
        
        df = conn.read(worksheet="reservations", ttl=5)
        df_palette = conn.read(worksheet="plateformes", ttl=5)
        
        palette = dict(zip(df_palette['plateforme'], df_palette['couleur']))
        
        return df, palette
    except Exception as e:
        st.error("Impossible de charger les données depuis Google Sheets.")
        st.exception(e)
        return pd.DataFrame(), {}

def sauvegarder_donnees(df, palette):
    """Sauvegarde les données dans la Google Sheet."""
    try:
        conn = st.connection("gsheets", type=st.connections.GSheetsConnection)
        
        df_to_save = df.copy()
        for col in ['date_arrivee', 'date_depart']:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime('%d/%m/%Y')
        
        conn.write(worksheet="reservations", data=df_to_save)
        
        palette_df = pd.DataFrame(list(palette.items()), columns=['plateforme', 'couleur'])
        conn.write(worksheet="plateformes", data=palette_df)

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ... (Le reste de votre code : ensure_schema, les vues, etc., n'a pas besoin de changer)
# ==============================  SCHEMA & DATA VALIDATION  ==============================
def ensure_schema(df):
    # ... (fonction inchangée)
    return df

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df, palette = charger_donnees()
    
    # ... (le reste de la fonction main est inchangé)

if __name__ == "__main__":
    main()
