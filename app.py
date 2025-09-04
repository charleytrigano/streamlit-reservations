# app.py — Villa Tobias (COMPLET) - Version Google Sheets (OAuth)

import streamlit as st
import pandas as pd
from streamlit_gsheets import GSheetsConnection
import os
import calendar
from datetime import date, timedelta

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = { "Booking": "#1e90ff", "Airbnb":  "#e74c3c", "Autre":   "#f59e0b" }

# ============================== CORE DATA FUNCTIONS ==============================
@st.cache_data(ttl=60)
def charger_donnees():
    """Charge les données depuis la Google Sheet."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        df = conn.read(worksheet="reservations", usecols=list(range(20)), ttl=5)
        df_palette_raw = conn.read(worksheet="plateformes", usecols=list(range(2)), ttl=5)
        
        palette = dict(zip(df_palette_raw['plateforme'], df_palette_raw['couleur']))
        
        return ensure_schema(df), palette
    except Exception as e:
        st.error("Impossible de charger les données depuis Google Sheets.")
        st.exception(e)
        return pd.DataFrame(), DEFAULT_PALETTE.copy()

def sauvegarder_donnees(df, palette):
    """Sauvegarde les données dans la Google Sheet."""
    try:
        conn = st.connection("gsheets", type=GSheetsConnection)
        
        # Préparer les données pour la sauvegarde
        df_to_save = df.copy()
        for col in ['date_arrivee', 'date_depart']:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime('%d/%m/%Y')
        
        # Sauvegarder les réservations
        conn.write(worksheet="reservations", data=df_to_save)
        
        # Sauvegarder la palette
        palette_df = pd.DataFrame(list(palette.items()), columns=['plateforme', 'couleur'])
        conn.write(worksheet="plateformes", data=palette_df)

        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ... (Le reste de votre code : ensure_schema, les vues, etc., reste identique)
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
