# app.py — Villa Tobias (COMPLET) - Version SQLite
# Schéma de données enrichi et logique de chargement corrigée

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
from urllib.parse import quote
import sqlite3

DB_FILE = "reservations.db"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  SESSION KEYS  ==============================
if "uploader_key_restore" not in st.session_state:
    st.session_state.uploader_key_restore = 0
if "did_clear_cache" not in st.session_state:
    st.session_state.did_clear_cache = False

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

# ============================== DATABASE INITIALIZATION =============================
def init_db():
    """Crée les tables de la base de données si elles n'existent pas."""
    with sqlite3.connect(DB_FILE) as con:
        cur = con.cursor()
        # Schéma de la table des réservations basé sur votre fichier source
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                paye INTEGER,
                nom_client TEXT,
                sms_envoye INTEGER,
                plateforme TEXT,
                telephone TEXT,
                date_arrivee TEXT,
                date_depart TEXT,
                nuitees REAL,
                prix_brut REAL,
                commissions REAL,
                frais_cb REAL,
                prix_net REAL,
                menage REAL,
                taxes_sejour REAL,
                base REAL,
                charges REAL,
                "%" REAL,
                AAAA INTEGER,
                MM INTEGER,
                ical_uid TEXT
            )
        """)
        # Création de la table des plateformes
        cur.execute("""
            CREATE TABLE IF NOT EXISTS plateformes (
                nom TEXT PRIMARY KEY,
                couleur TEXT
            )
        """)
        # Remplir la table des plateformes si elle est vide
        cur.execute("SELECT COUNT(*) FROM plateformes")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO plateformes (nom, couleur) VALUES (?, ?)", DEFAULT_PALETTE.items())
        con.commit()

# ==============================  CORE DATA FUNCTIONS (SQLite Version) ==============================
@st.cache_data
def charger_donnees():
    """Charge les réservations et la palette depuis la base de données SQLite."""
    if not os.path.exists(DB_FILE):
        init_db()
        return pd.DataFrame(), DEFAULT_PALETTE

    with sqlite3.connect(DB_FILE) as con:
        df = pd.read_sql_query("SELECT * FROM reservations", con)
        df_palette = pd.read_sql_query("SELECT * FROM plateformes", con)

    # Traitement de la palette
    if 'nom' not in df_palette.columns and 'plateforme' in df_palette.columns:
        df_palette.rename(columns={'plateforme': 'nom'}, inplace=True)

    if 'nom' in df_palette.columns and 'couleur' in df_palette.columns:
        palette = dict(zip(df_palette['nom'], df_palette['couleur']))
    else:
        palette = DEFAULT_PALETTE.copy()

    # Traitement et nettoyage des réservations
    df = ensure_schema(df)
    return df, palette

def sauvegarder_donnees(df_reservations, palette_dict):
    """Sauvegarde le DataFrame des réservations et la palette dans la BDD SQLite."""
    with sqlite3.connect(DB_FILE) as con:
        df_to_save = df_reservations.copy()
        
        for col in ['paye', 'sms_envoye']:
            if col in df_to_save.columns:
                df_to_save[col] = df_to_save[col].astype(int)
        
        df_to_save.to_sql('reservations', con, if_exists='replace', index=False)

        cur = con.cursor()
        cur.execute("DELETE FROM plateformes")
        if palette_dict:
            cur.executemany("INSERT INTO plateformes (nom, couleur) VALUES (?, ?)", palette_dict.items())
        con.commit()

# ==============================  SCHEMA & DATA VALIDATION  ==============================
BASE_COLS = [
    'paye', 'nom_client', 'sms_envoye', 'plateforme', 'telephone', 'date_arrivee',
    'date_depart', 'nuitees', 'prix_brut', 'commissions', 'frais_cb',
    'prix_net', 'menage', 'taxes_sejour', 'base', 'charges', '%',
    'AAAA', 'MM', 'ical_uid'
]

def ensure_schema(df):
    """Assure que le DataFrame a toutes les colonnes nécessaires et les bons types."""
    df_res = df.copy()
    for col in BASE_COLS:
        if col not in df_res.columns:
            df_res[col] = None

    # Étape 1: Convertir en objets datetime complets pour le calcul
    date_cols_to_convert = ["date_arrivee", "date_depart"]
    for col in date_cols_to_convert:
        df_res[col] = pd.to_datetime(df_res[col], errors='coerce')

    # Étape 2: Calculer les nuitées
    mask_dates = pd.notna(df_res["date_arrivee"]) & pd.notna(df_res["date_depart"])
    df_res.loc[mask_dates, "nuitees"] = (df_res.loc[mask_dates, "date_depart"] - df_res.loc[mask_dates, "date_arrivee"]).dt.days

    # Étape 3: Reconvertir les colonnes de date en objets date simples pour l'affichage
    for col in date_cols_to_convert:
        df_res[col] = df_res[col].dt.date

    for col in ['paye', 'sms_envoye']:
        df_res[col] = df_res[col].fillna(0).astype(bool)

    numeric_cols = ['prix_brut', 'commissions', 'frais_cb', 'menage', 'taxes_sejour']
    for col in numeric_cols:
        df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)

    # Recalculs pour garantir la cohérence
    df_res['prix_net'] = df_res['prix_brut'] - df_res['commissions'] - df_res['frais_cb']
    df_res['base'] = df_res['prix_net'] - df_res['menage'] - df_res['taxes_sejour']
    df_res['charges'] = df_res['prix_brut'] - df_res['prix_net']
    
    with np.errstate(divide='ignore', invalid='ignore'):
        df_res['%'] = np.where(df_res['prix_brut'] > 0, (df_res['charges'] / df_res['prix_brut'] * 100), 0)

    df_res.loc[pd.notna(df_res["date_arrivee"]), 'AAAA'] = pd.to_datetime(df_res.loc[pd.notna(df_res["date_arrivee"]), 'date_arrivee']).dt.year
    df_res.loc[pd.notna(df_res["date_arrivee"]), 'MM'] = pd.to_datetime(df_res.loc[pd.notna(df_res["date_arrivee"]), 'date_arrivee']).dt.month
    
    return df_res[BASE_COLS]

# ==============================  PALETTE HELPERS ==============================
def get_palette():
    if 'palette' in st.session_state:
        return st.session_state.palette
    _, pal = charger_donnees()
    st.session_state.palette = pal
    return pal

def is_dark_color(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
        return luminance < 0.5
    except:
        return True

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation pour le moment.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index(drop=True)
    st.dataframe(df_sorted)

# ... (les autres fonctions "vue_" peuvent être ajoutées ici)

# ==============================  MAIN APP  ==============================
def main():
    init_db()
    st.title("📖 Gestion des Réservations - Villa Tobias")
    
    st.sidebar.markdown("## ⚙️ Administration")
    # bouton_telecharger() et bouton_restaurer() peuvent être ajoutés ici si nécessaire

    df, palette = charger_donnees()
    
    st.session_state.palette = palette

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations", "➕ Ajouter", "🎨 Plateformes"] # Simplifié pour le débogage
    )

    if onglet == "📋 Réservations":
        vue_reservations(df)
    # Les autres vues peuvent être réactivées une par une
    # elif onglet == "➕ Ajouter":
    #     vue_ajouter(df)
