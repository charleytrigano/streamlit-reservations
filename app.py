# app.py — Villa Tobias (COMPLET) - Version lisant le CSV directement

import streamlit as st
import pandas as pd
import numpy as np

CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv" # Gardé pour le futur

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = { "Booking": "#1e90ff", "Airbnb":  "#e74c3c", "Autre":   "#f59e0b" }

# ============================== CORE DATA FUNCTIONS ==============================
@st.cache_data
def charger_donnees_csv():
    """Charge les données directement depuis le fichier CSV."""
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=';')
        df.columns = df.columns.str.strip()
    except FileNotFoundError:
        st.error(f"ERREUR : Le fichier '{CSV_RESERVATIONS}' est introuvable.")
        return pd.DataFrame() # Retourne un DataFrame vide
    except Exception as e:
        st.error("Une erreur est survenue lors de la lecture du fichier CSV.")
        st.exception(e)
        return pd.DataFrame()

    df = ensure_schema(df)
    return df

# ==============================  SCHEMA & DATA VALIDATION  ==============================
BASE_COLS = [
    'paye', 'nom_client', 'sms_envoye', 'plateforme', 'telephone', 'date_arrivee',
    'date_depart', 'nuitees', 'prix_brut', 'commissions', 'frais_cb',
    'prix_net', 'menage', 'taxes_sejour', 'base', 'charges', '%',
    'AAAA', 'MM', 'ical_uid'
]

def ensure_schema(df):
    df_res = df.copy()
    # Renommer les colonnes avec des noms plus simples si nécessaire (basé sur le fichier)
    rename_map = {
        'Payé': 'paye', 'Client': 'nom_client', 'Plateforme': 'plateforme', 
        'Arrivée': 'date_arrivee', 'Départ': 'date_depart', 'Nuits': 'nuitees',
        'Brut (€)': 'prix_brut', 'Charges (€)': 'charges', 'Net (€)': 'prix_net',
        'Charges (%)': '%'
    }
    df_res.rename(columns=rename_map, inplace=True)

    for col in BASE_COLS:
        if col not in df_res.columns:
            df_res[col] = 0

    date_cols = ["date_arrivee", "date_depart"]
    for col in date_cols:
        df_res[col] = pd.to_datetime(df_res[col], dayfirst=True, errors='coerce')

    mask_dates = pd.notna(df_res["date_arrivee"]) & pd.notna(df_res["date_depart"])
    df_res.loc[mask_dates, "nuitees"] = (df_res.loc[mask_dates, "date_depart"] - df_res.loc[mask_dates, "date_arrivee"]).dt.days

    for col in date_cols:
        df_res[col] = df_res[col].dt.date

    for col in ['paye', 'sms_envoye']:
        # Gérer les chaînes de caractères 'VRAI'/'FAUX'
        if df_res[col].dtype == 'object':
            df_res[col] = df_res[col].str.strip().str.upper() == 'VRAI'
        df_res[col] = df_res[col].fillna(False).astype(bool)

    numeric_cols = ['prix_brut', 'commissions', 'frais_cb', 'menage', 'taxes_sejour']
    for col in numeric_cols:
        if col in df_res.columns:
            if df_res[col].dtype == 'object':
                df_res[col] = df_res[col].astype(str).str.replace('€', '', regex=False).str.replace(',', '.', regex=False).str.replace(' ', '', regex=False).str.strip()
            df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)

    # Recalculs
    df_res['prix_net'] = df_res['prix_brut'].fillna(0) - df_res['commissions'].fillna(0) - df_res['frais_cb'].fillna(0)
    df_res['base'] = df_res['prix_net'].fillna(0) - df_res['menage'].fillna(0) - df_res['taxes_sejour'].fillna(0)
    df_res['charges'] = df_res['prix_brut'].fillna(0) - df_res['prix_net'].fillna(0)
    
    with np.errstate(divide='ignore', invalid='ignore'):
        df_res['%'] = np.where(df_res['prix_brut'] > 0, (df_res['charges'] / df_res['prix_brut'] * 100), 0)

    date_arrivee_dt = pd.to_datetime(df_res["date_arrivee"], errors='coerce')
    df_res.loc[pd.notna(date_arrivee_dt), 'AAAA'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.year
    df_res.loc[pd.notna(date_arrivee_dt), 'MM'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.month
    
    return df_res

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation trouvée dans le fichier CSV.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False, na_position='last').reset_index(drop=True)
    st.dataframe(df_sorted)

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df = charger_donnees_csv()
    
    st.sidebar.title("🧭 Navigation")
    pages = { "📋 Réservations": vue_reservations }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    
    pages[selection](df)

if __name__ == "__main__":
    main()
