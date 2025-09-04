# app.py — Villa Tobias (COMPLET) - Version CSV-Direct avec Ajout/Sauvegarde

import streamlit as st
import pandas as pd
import numpy as np

CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv" 

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
        return pd.DataFrame()
    except Exception as e:
        st.error("Une erreur est survenue lors de la lecture du fichier CSV.")
        st.exception(e)
        return pd.DataFrame()

    df = ensure_schema(df)
    return df

def sauvegarder_donnees_csv(df):
    """Sauvegarde le DataFrame dans le fichier CSV."""
    try:
        # On s'assure que les dates sont bien au format texte pour la sauvegarde
        df_to_save = df.copy()
        for col in ['date_arrivee', 'date_depart']:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime('%d/%m/%Y')
        
        df_to_save.to_csv(CSV_RESERVATIONS, sep=';', index=False)
        st.cache_data.clear() # Vider le cache pour refléter les changements
        return True
    except Exception as e:
        st.error("Une erreur est survenue lors de la sauvegarde.")
        st.exception(e)
        return False

# ==============================  SCHEMA & DATA VALIDATION  ==============================
BASE_COLS = [
    'paye', 'nom_client', 'sms_envoye', 'plateforme', 'telephone', 'date_arrivee',
    'date_depart', 'nuitees', 'prix_brut', 'commissions', 'frais_cb',
    'prix_net', 'menage', 'taxes_sejour', 'base', 'charges', '%',
    'AAAA', 'MM', 'ical_uid'
]

def ensure_schema(df):
    df_res = df.copy()
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

    if 'paye' in df_res.columns and df_res['paye'].dtype == 'object':
        df_res['paye'] = df_res['paye'].str.strip().str.upper() == 'VRAI'
    df_res['paye'] = df_res['paye'].fillna(False).astype(bool)

    numeric_cols = ['prix_brut', 'commissions', 'frais_cb', 'menage', 'taxes_sejour']
    for col in numeric_cols:
        if col in df_res.columns and df_res[col].dtype == 'object':
            df_res[col] = df_res[col].astype(str).str.replace('€', '', regex=False).str.replace(',', '.', regex=False).str.replace(' ', '', regex=False).str.strip()
        df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)
    
    # Recalculs
    df_res['prix_net'] = df_res['prix_brut'].fillna(0) - df_res['commissions'].fillna(0) - df_res['frais_cb'].fillna(0)
    df_res['charges'] = df_res['prix_brut'].fillna(0) - df_res['prix_net'].fillna(0)
    
    return df_res

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation trouvée dans le fichier CSV.")
        return
    df_sorted = df.sort_values(by="date_arrivee", ascending=False, na_position='last').reset_index(drop=True)
    st.dataframe(df_sorted)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une Réservation")
    with st.form("form_ajout", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            nom_client = st.text_input("**Nom du Client**")
            date_arrivee = st.date_input("**Date d'arrivée**", pd.to_datetime("today"))
        with c2:
            plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()))
            date_depart = st.date_input("**Date de départ**", pd.to_datetime("today") + pd.DateOffset(days=1))
        with c3:
            prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, step=10.0, format="%.2f")
            paye = st.checkbox("Payé", False)

        submitted = st.form_submit_button("✅ Ajouter la réservation")
        if submitted:
            if not nom_client or date_depart <= date_arrivee:
                st.error("Veuillez entrer un nom et vérifier que les dates sont correctes.")
            else:
                nouvelle_ligne = pd.DataFrame([{
                    'nom_client': nom_client, 'date_arrivee': date_arrivee, 'date_depart': date_depart,
                    'plateforme': plateforme, 'prix_brut': prix_brut, 'paye': paye
                }])
                
                df_a_jour = pd.concat([df, nouvelle_ligne], ignore_index=True)
                df_a_jour = ensure_schema(df_a_jour)
                
                if sauvegarder_donnees_csv(df_a_jour):
                    st.success(f"Réservation pour **{nom_client}** ajoutée !")
                    st.rerun()

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df = charger_donnees_csv()
    palette = DEFAULT_PALETTE # Pour l'instant, on utilise la palette par défaut
    
    st.sidebar.title("🧭 Navigation")
    pages = { 
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    
    page_function = pages[selection]

    if selection == "➕ Ajouter":
        page_function(df, palette)
    else:
        page_function(df)

if __name__ == "__main__":
    main()
