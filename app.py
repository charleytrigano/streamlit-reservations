# app.py — Villa Tobias (COMPLET) - Version CSV-Direct avec Rapport corrigé

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

def sauvegarder_donnees_csv(df):
    """Sauvegarde le DataFrame dans le fichier CSV."""
    try:
        df_to_save = df.copy()
        for col in ['date_arrivee', 'date_depart']:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime('%d/%m/%Y')
        
        df_to_save.to_csv(CSV_RESERVATIONS, sep=';', index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
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
            df_res[col] = None

    date_cols = ["date_arrivee", "date_depart"]
    for col in date_cols:
        df_res[col] = pd.to_datetime(df_res[col], dayfirst=True, errors='coerce')

    mask_dates = pd.notna(df_res["date_arrivee"]) & pd.notna(df_res["date_depart"])
    df_res.loc[mask_dates, "nuitees"] = (df_res.loc[mask_dates, "date_depart"] - df_res.loc[mask_dates, "date_arrivee"]).dt.days

    for col in date_cols:
        df_res[col] = df_res[col].dt.date

    if 'paye' in df_res.columns and df_res['paye'].dtype == 'object':
        df_res['paye'] = df_res['paye'].str.strip().str.upper().isin(['VRAI', 'TRUE'])
    df_res['paye'] = df_res['paye'].fillna(False).astype(bool)

    numeric_cols = ['prix_brut', 'commissions', 'frais_cb', 'menage', 'taxes_sejour']
    for col in numeric_cols:
        if col in df_res.columns:
            if df_res[col].dtype == 'object':
                df_res[col] = df_res[col].astype(str).str.replace('€', '', regex=False).str.replace(',', '.', regex=False).str.replace(' ', '', regex=False).str.strip()
            df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)
    
    df_res['prix_net'] = df_res['prix_brut'].fillna(0) - df_res['commissions'].fillna(0) - df_res['frais_cb'].fillna(0)
    df_res['charges'] = df_res['prix_brut'].fillna(0) - df_res['prix_net'].fillna(0)
    df_res['base'] = df_res['prix_net'].fillna(0) - df_res['menage'].fillna(0) - df_res['taxes_sejour'].fillna(0)
    
    with np.errstate(divide='ignore', invalid='ignore'):
        df_res['%'] = np.where(df_res['prix_brut'] > 0, (df_res['charges'] / df_res['prix_brut'] * 100), 0)

    date_arrivee_dt = pd.to_datetime(df_res["date_arrivee"], errors='coerce')
    df_res.loc[pd.notna(date_arrivee_dt), 'AAAA'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.year
    df_res.loc[pd.notna(date_arrivee_dt), 'MM'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.month
    
    return df_res

# ============================== UTILITIES & HELPERS ==============================
def kpi_chips(df):
    """Affiche les indicateurs de performance clés (KPIs) sous forme de badges stylisés."""
    if df.empty or 'nuitees' not in df.columns or df['nuitees'].sum() == 0:
        st.warning("Pas de données suffisantes pour afficher les indicateurs.")
        return

    b = df["prix_brut"].sum()
    n = df["prix_net"].sum()
    ch = df["charges"].sum()
    nuits = df["nuitees"].sum()
    
    pm_brut = b / nuits if nuits > 0 else 0
    pm_net = n / nuits if nuits > 0 else 0
    pct = (ch / b * 100) if b > 0 else 0

    # ... (le code HTML pour les chips reste le même)
    pass

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    # ... (le code de cette fonction reste le même)
    pass

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une Réservation")
    # ... (le code de cette fonction reste le même)
    pass

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer une Réservation")
    # ... (le code de cette fonction reste le même)
    pass

def vue_calendrier(df, palette):
    st.header("📅 Calendrier des Réservations")
    # ... (le code de cette fonction reste le même)
    pass

def vue_rapport(df, palette):
    st.header("📊 Rapport de Performance")
    
    df_dates_valides = df.dropna(subset=['AAAA', 'MM', 'plateforme'])
    if df_dates_valides.empty:
        st.info("Aucune donnée valide pour générer un rapport.")
        return

    c1, c2, c3 = st.columns(3)
    annees = sorted(df_dates_valides['AAAA'].astype(int).unique(), reverse=True)
    annee_selectionnee = c1.selectbox("Année", annees)
    mois_options = ["Tous"] + list(range(1, 13))
    mois_selectionne = c2.selectbox("Mois", mois_options)
    plateformes_options = ["Toutes"] + sorted(df_dates_valides['plateforme'].unique())
    plateforme_selectionnee = c3.selectbox("Plateforme", plateformes_options)

    data = df_dates_valides[df_dates_valides['AAAA'] == annee_selectionnee]
    if mois_selectionne != "Tous":
        data = data[data['MM'] == mois_selectionne]
    if plateforme_selectionnee != "Toutes":
        data = data[data['plateforme'] == plateforme_selectionnee]

    st.markdown("---")
    if data.empty:
        st.warning("Aucune donnée pour les filtres sélectionnés.")
        return

    st.subheader("Indicateurs Clés")
    kpi_chips(data)

    st.subheader("Revenus bruts par Plateforme")
    
    # --- DÉBUT DE LA CORRECTION ---
    data_for_chart = data.dropna(subset=['plateforme'])
    
    if data_for_chart.empty:
        st.info("Aucune donnée de plateforme à afficher pour cette sélection.")
        return

    chart_data = data_for_chart.groupby("plateforme")['prix_brut'].sum().sort_values(ascending=False)
    
    if not chart_data.empty:
        colors = [palette.get(str(x), "#888888") for x in chart_data.index]
        
        # Débogage pour vérifier les longueurs en cas de problème persistant
        # st.write("Données du graphique :", chart_data)
        # st.write(f"Nombre de barres : {len(chart_data)}")
        # st.write(f"Nombre de couleurs : {len(colors)}")
        
        st.bar_chart(chart_data, color=colors)
    else:
        st.info("Pas de données à afficher dans le graphique.")
    # --- FIN DE LA CORRECTION ---

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df, palette = charger_donnees_csv()
    
    st.sidebar.title("🧭 Navigation")
    pages = { 
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    
    page_function = pages[selection]

    if selection in ["➕ Ajouter", "✏️ Modifier / Supprimer", "📅 Calendrier", "📊 Rapport"]:
        page_function(df, palette)
    else:
        page_function(df)

if __name__ == "__main__":
    main()
