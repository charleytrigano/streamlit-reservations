# app.py — Villa Tobias (COMPLET) - Version CSV-Direct avec correction de la page Plateformes

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
    """Charge les données directement depuis les fichiers CSV."""
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=';')
        df.columns = df.columns.str.strip()
    except FileNotFoundError:
        return pd.DataFrame(), DEFAULT_PALETTE
    except Exception as e:
        st.error(f"Erreur de lecture de {CSV_RESERVATIONS}")
        st.exception(e)
        return pd.DataFrame(), DEFAULT_PALETTE

    try:
        df_palette = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        palette = dict(zip(df_palette['plateforme'], df_palette['couleur']))
    except:
        palette = DEFAULT_PALETTE.copy()

    df = ensure_schema(df)
    return df, palette

def sauvegarder_donnees_csv(df, file_path=CSV_RESERVATIONS):
    """Sauvegarde le DataFrame dans le fichier CSV spécifié."""
    try:
        df_to_save = df.copy()
        for col in ['date_arrivee', 'date_depart']:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime('%d/%m/%Y')
        
        df_to_save.to_csv(file_path, sep=';', index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ==============================  SCHEMA & DATA VALIDATION  ==============================
def ensure_schema(df):
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
        c1, c2 = st.columns(2)
        with c1:
            nom_client = st.text_input("**Nom du Client**")
            telephone = st.text_input("Téléphone")
            date_arrivee = st.date_input("**Date d'arrivée**", date.today())
        with c2:
            plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()))
            date_depart = st.date_input("**Date de départ**", date.today() + timedelta(days=1))
            prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, step=10.0, format="%.2f")
        paye = st.checkbox("Payé", False)

        submitted = st.form_submit_button("✅ Ajouter la réservation")
        if submitted:
            if not nom_client or date_depart <= date_arrivee:
                st.error("Veuillez entrer un nom et vérifier que les dates sont correctes.")
            else:
                nouvelle_ligne = pd.DataFrame([{
                    'nom_client': nom_client, 'telephone': telephone, 'date_arrivee': date_arrivee, 
                    'date_depart': date_depart, 'plateforme': plateforme, 'prix_brut': prix_brut, 
                    'paye': paye
                }])
                
                df_a_jour = pd.concat([df, nouvelle_ligne], ignore_index=True)
                
                if sauvegarder_donnees_csv(df_a_jour):
                    st.success(f"Réservation pour **{nom_client}** ajoutée !")
                    st.rerun()

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
            # --- CORRECTION APPLIQUÉE ICI ---
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
    
    st.info(
        "**Important :** Pour rendre vos modifications permanentes, n'oubliez pas de télécharger le fichier CSV mis à jour depuis l'onglet 'Réservations' et de l'envoyer sur votre dépôt GitHub."
    )

    df, palette = charger_donnees_csv()
    
    st.sidebar.title("🧭 Navigation")
    pages = { 
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "🎨 Plateformes": vue_plateformes,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    
    page_function = pages[selection]

    if selection in ["➕ Ajouter", "🎨 Plateformes"]:
        page_function(df, palette)
    else:
        page_function(df)

if __name__ == "__main__":
    main()
