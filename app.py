# app.py — Villa Tobias (COMPLET) - Version SQLite
# Version finale avec toutes les fonctionnalités réactivées

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
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                paye INTEGER, nom_client TEXT, sms_envoye INTEGER, plateforme TEXT,
                telephone TEXT, date_arrivee TEXT, date_depart TEXT, nuitees REAL,
                prix_brut REAL, commissions REAL, frais_cb REAL, prix_net REAL,
                menage REAL, taxes_sejour REAL, base REAL, charges REAL,
                "%" REAL, AAAA INTEGER, MM INTEGER, ical_uid TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS plateformes (
                nom TEXT PRIMARY KEY, couleur TEXT
            )
        """)
        cur.execute("SELECT COUNT(*) FROM plateformes")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO plateformes (nom, couleur) VALUES (?, ?)", DEFAULT_PALETTE.items())
        con.commit()

# ==============================  CORE DATA FUNCTIONS ==============================
@st.cache_data
def charger_donnees():
    """Charge les réservations et la palette depuis la base de données SQLite."""
    if not os.path.exists(DB_FILE):
        init_db()
        return pd.DataFrame(), DEFAULT_PALETTE

    with sqlite3.connect(DB_FILE) as con:
        df = pd.read_sql_query("SELECT * FROM reservations", con)
        df_palette = pd.read_sql_query("SELECT * FROM plateformes", con)

    if 'nom' not in df_palette.columns and 'plateforme' in df_palette.columns:
        df_palette.rename(columns={'plateforme': 'nom'}, inplace=True)

    if 'nom' in df_palette.columns and 'couleur' in df_palette.columns and not df_palette.empty:
        palette = dict(zip(df_palette['nom'], df_palette['couleur']))
    else:
        palette = DEFAULT_PALETTE.copy()

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
            cur.executemany("INSERT OR REPLACE INTO plateformes (nom, couleur) VALUES (?, ?)", palette_dict.items())
        con.commit()
    st.cache_data.clear()

# ==============================  SCHEMA & DATA VALIDATION  ==============================
BASE_COLS = [
    'paye', 'nom_client', 'sms_envoye', 'plateforme', 'telephone', 'date_arrivee',
    'date_depart', 'nuitees', 'prix_brut', 'commissions', 'frais_cb',
    'prix_net', 'menage', 'taxes_sejour', 'base', 'charges', '%',
    'AAAA', 'MM', 'ical_uid'
]

def ensure_schema(df):
    df_res = df.copy()
    for col in BASE_COLS:
        if col not in df_res.columns:
            df_res[col] = None

    date_cols = ["date_arrivee", "date_depart"]
    for col in date_cols:
        df_res[col] = pd.to_datetime(df_res[col], errors='coerce')

    mask_dates = pd.notna(df_res["date_arrivee"]) & pd.notna(df_res["date_depart"])
    df_res.loc[mask_dates, "nuitees"] = (df_res.loc[mask_dates, "date_depart"] - df_res.loc[mask_dates, "date_arrivee"]).dt.days

    for col in date_cols:
        df_res[col] = df_res[col].dt.date

    for col in ['paye', 'sms_envoye']:
        df_res[col] = df_res[col].fillna(0).astype(bool)

    numeric_cols = ['prix_brut', 'commissions', 'frais_cb', 'menage', 'taxes_sejour']
    for col in numeric_cols:
        df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)

    df_res['prix_net'] = df_res['prix_brut'] - df_res['commissions'] - df_res['frais_cb']
    df_res['base'] = df_res['prix_net'] - df_res['menage'] - df_res['taxes_sejour']
    df_res['charges'] = df_res['prix_brut'] - df_res['prix_net']
    
    with np.errstate(divide='ignore', invalid='ignore'):
        df_res['%'] = np.where(df_res['prix_brut'] > 0, (df_res['charges'] / df_res['prix_brut'] * 100), 0)

    date_arrivee_dt = pd.to_datetime(df_res["date_arrivee"], errors='coerce')
    df_res.loc[pd.notna(date_arrivee_dt), 'AAAA'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.year
    df_res.loc[pd.notna(date_arrivee_dt), 'MM'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.month
    
    return df_res[BASE_COLS]

# ==============================  UTILITIES & HELPERS ==============================
def to_date_only(dt):
    if isinstance(dt, (datetime, pd.Timestamp)):
        return dt.date()
    return dt

def is_dark_color(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
        return luminance < 0.5
    except (ValueError, TypeError):
        return True # Default to dark background assumptions

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation pour le moment. Ajoutez-en une via l'onglet '➕ Ajouter'.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index(drop=True)
    st.dataframe(df_sorted)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une Réservation")
    with st.form("form_ajout", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            nom_client = st.text_input("**Nom du Client**")
            date_arrivee = st.date_input("**Date d'arrivée**", date.today())
            prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, step=10.0, format="%.2f")
        with c2:
            plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()))
            date_depart = st.date_input("**Date de départ**", date.today() + timedelta(days=1))
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=1.0, format="%.2f")
        with c3:
            telephone = st.text_input("Téléphone")
            paye = st.checkbox("Payé", False)
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.1, format="%.2f")
        
        submitted = st.form_submit_button("✅ Ajouter la réservation")
        if submitted:
            if not nom_client or date_depart <= date_arrivee:
                st.error("Veuillez entrer un nom et vérifier que les dates sont correctes.")
                return
            
            nouvelle_ligne = pd.DataFrame([{
                'nom_client': nom_client, 'date_arrivee': date_arrivee, 'date_depart': date_depart,
                'plateforme': plateforme, 'prix_brut': prix_brut, 'paye': paye,
                'commissions': commissions, 'frais_cb': frais_cb, 'telephone': telephone
            }])
            
            df_a_jour = pd.concat([df, nouvelle_ligne], ignore_index=True)
            df_a_jour = ensure_schema(df_a_jour)
            
            sauvegarder_donnees(df_a_jour, palette)
            st.success(f"Réservation pour **{nom_client}** ajoutée !")
            st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Gestion des Plateformes")
    
    edited_palette = {}
    for p, c in palette.items():
        cols = st.columns([0.8, 0.2])
        new_color = cols[0].color_picker(f"Couleur pour **{p}**", value=c, key=f"color_{p}")
        edited_palette[p] = new_color
        
        if cols[1].button("🗑️", key=f"del_{p}"):
            del edited_palette[p]
            sauvegarder_donnees(df, edited_palette)
            st.rerun()

    st.markdown("---")
    with st.form("new_platform_form", clear_on_submit=True):
        new_name = st.text_input("Ajouter une nouvelle plateforme")
        submitted = st.form_submit_button("Ajouter")
        if submitted and new_name and new_name not in edited_palette:
            edited_palette[new_name] = "#ffffff"
    
    if st.button("💾 Enregistrer les changements"):
        sauvegarder_donnees(df, edited_palette)
        st.success("Palette de couleurs mise à jour !")
        st.rerun()

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    
    df, palette = charger_donnees()
    
    st.sidebar.title("🧭 Navigation")
    pages = {
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "🎨 Plateformes": vue_plateformes,
        # Ajoutez ici d'autres vues que vous souhaitez réactiver
        # "✏️ Modifier / Supprimer": vue_modifier,
        # "📅 Calendrier": vue_calendrier,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))

    page_function = pages[selection]

    # Passer les bons arguments à chaque fonction de vue
    if selection in ["➕ Ajouter", "🎨 Plateformes"]:
        page_function(df, palette)
    else:
        page_function(df)

if __name__ == "__main__":
    main()
