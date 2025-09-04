# app.py — Villa Tobias (COMPLET) - Version avec Page Plateformes fonctionnelle

import streamlit as st
import pandas as pd
import numpy as np
import os
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
    """Charge les données directement depuis les fichiers CSV."""
    df = pd.DataFrame() # Initialiser un DataFrame vide
    palette = DEFAULT_PALETTE.copy() # Commencer avec la palette par défaut

    # Charger les réservations
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=';')
        df.columns = df.columns.str.strip()
    except FileNotFoundError:
        st.warning(f"Fichier '{CSV_RESERVATIONS}' introuvable. Vous pouvez commencer par ajouter une réservation.")
    except Exception as e:
        st.error(f"Erreur de lecture de {CSV_RESERVATIONS}")
        st.exception(e)

    # Charger la palette de couleurs
    try:
        df_palette = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        palette = dict(zip(df_palette['plateforme'], df_palette['couleur']))
    except FileNotFoundError:
        st.warning(f"Fichier '{CSV_PLATEFORMES}' introuvable. Utilisation de la palette par défaut.")
    except Exception as e:
        st.error(f"Erreur de lecture de {CSV_PLATEFORMES}")
        st.exception(e)

    df = ensure_schema(df)
    return df, palette

def sauvegarder_donnees_csv(df, file_path=CSV_RESERVATIONS):
    """Sauvegarde le DataFrame dans le fichier CSV spécifié."""
    try:
        df_to_save = df.copy()
        # Convertir les objets date en chaînes de caractères avant la sauvegarde
        for col in df_to_save.select_dtypes(include=['datetime64[ns]', 'object']).columns:
             if isinstance(df_to_save[col].iloc[0], date):
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime('%d/%m/%Y')
        
        df_to_save.to_csv(file_path, sep=';', index=False)
        st.cache_data.clear() # Vider le cache pour forcer la relecture
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ==============================  SCHEMA & DATA VALIDATION  ==============================
def ensure_schema(df):
    if df.empty:
        return pd.DataFrame(columns=BASE_COLS)
        
    df_res = df.copy()
    rename_map = { 
        'Payé': 'paye', 'Client': 'nom_client', 'Plateforme': 'plateforme', 
        'Arrivée': 'date_arrivee', 'Départ': 'date_depart', 'Nuits': 'nuitees',
        'Brut (€)': 'prix_brut', 'Charges (€)': 'charges', 'Net (€)': 'prix_net'
    }
    df_res.rename(columns=rename_map, inplace=True)

    BASE_COLS = [
        'paye', 'nom_client', 'plateforme', 'telephone', 'date_arrivee', 'date_depart', 'nuitees',
        'prix_brut', 'commissions', 'frais_cb', 'prix_net', 'charges'
    ]
    for col in BASE_COLS:
        if col not in df_res.columns:
            df_res[col] = None

    date_cols = ["date_arrivee", "date_depart"]
    for col in date_cols:
        df_res[col] = pd.to_datetime(df_res[col], dayfirst=True, errors='coerce')

    mask_dates = pd.notna(df_res["date_arrivee"]) & pd.notna(df_res["date_depart"])
    df_res.loc[mask_dates, "nuitees"] = (df_res.loc[mask_dates, "date_depart"] - df_res.loc[mask_dates, "date_arrivee"]).dt.days

    for col in date_cols:
        df_res[col] = df_res[col].dt.date

    if 'paye' in df_res.columns:
        if df_res['paye'].dtype == 'object':
            df_res['paye'] = df_res['paye'].str.strip().str.upper().isin(['VRAI', 'TRUE'])
        df_res['paye'] = df_res['paye'].fillna(False).astype(bool)

    numeric_cols = ['prix_brut', 'commissions', 'frais_cb', 'prix_net', 'charges']
    for col in numeric_cols:
        if col in df_res.columns:
            if df_res[col].dtype == 'object':
                df_res[col] = df_res[col].astype(str).str.replace('€', '', regex=False).str.replace(',', '.', regex=False).str.replace(' ', '', regex=False).str.strip()
            df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)
    
    df_res['prix_net'] = df_res['prix_brut'].fillna(0) - df_res['commissions'].fillna(0) - df_res['frais_cb'].fillna(0)
    df_res['charges'] = df_res['prix_brut'].fillna(0) - df_res['prix_net'].fillna(0)
    
    return df_res

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    st.dataframe(df)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une Réservation")
    with st.form("form_ajout", clear_on_submit=True):
        # ... (le code de ce formulaire reste le même)
        pass

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer une Réservation")
    # ... (le code de ce formulaire reste le même)
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
            "couleur": st.column_config.TextColumn("Couleur (code hex, ex: #1e90ff)"),
        }
    )

    if st.button("💾 Enregistrer les modifications des plateformes"):
        nouvelle_palette = dict(zip(edited_df['plateforme'], edited_df['couleur']))
        df_plateformes_save = pd.DataFrame(list(nouvelle_palette.items()), columns=['plateforme', 'couleur'])
        
        if sauvegarder_donnees_csv(df_plateformes_save, file_path=CSV_PLATEFORMES):
            st.success("Palette de couleurs mise à jour !")
            st.rerun()

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df, palette = charger_donnees_csv()
    
    st.sidebar.title("🧭 Navigation")
    pages = { 
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    
    page_function = pages[selection]

    if selection in ["➕ Ajouter", "✏️ Modifier / Supprimer", "🎨 Plateformes"]:
        page_function(df, palette)
    else:
        page_function(df)

if __name__ == "__main__":
    main()
