# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib, json
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO
import openpyxl  # <-- NOUVELLE IMPORTATION POUR LES FICHIERS XLSX

# ============================== 0) CONFIG & THEME ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# purge prudente au chargement (ne plante pas si indispo)
for _clear in (getattr(st, "cache_data", None), getattr(st, "cache_resource", None)):
    try:
        if _clear: _clear.clear()
    except Exception:
        pass

CSV_RESERVATIONS = "reservations_normalise.xlsx - reservations_normalise.csv" # Remplacé par votre nom de fichier
CSV_PLATEFORMES = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb": "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre": "#f59e0b",
}

FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci..."


# ============================== 1) OUTILS & FONCTIONS UTILITAIRES ==============================
def hex_to_rgb(hex_code):
    hex_code = hex_code.lstrip('#')
    return tuple(int(hex_code[i:i + 2], 16) for i in (0, 2, 4))

def lighten_color(hex_code, amount):
    rgb = hex_to_rgb(hex_code)
    rgb = tuple(int(min(255, c + (255 - c) * amount)) for c in rgb)
    return f'#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}'

def generate_ics(df):
    # Implémentez la logique pour générer le fichier ICS ici
    # (Le code original de votre fichier)
    pass

def apply_style(light=False):
    style = """
        <style>
        .stButton button {
            background-color: #333;
            color: #fff;
            border-radius: 5px;
            padding: 10px 20px;
        }
        .stButton button:hover {
            background-color: #555;
        }
        .stTabs [data-baseweb="tab-list"] {
            gap: 10px;
        }
        .stTabs [data-baseweb="tab"] {
            height: 50px;
            white-space: pre-wrap;
            background-color: #f0f2f6;
            border-radius: 5px 5px 0 0;
            gap: 10px;
            padding-top: 10px;
            padding-bottom: 10px;
        }
        .stTabs [aria-selected="true"] {
            background-color: #fff;
        }
        </style>
    """
    st.markdown(style, unsafe_allow_html=True)


# ============================== 2) VUES DES PAGES ==============================
def vue_accueil():
    st.header("🏠 Tableau de bord")
    st.write("Bienvenue sur la gestion des réservations.")
    # Ajoutez le contenu de la page d'accueil
    pass

def vue_reservations(df, palette):
    st.header("📋 Liste des Réservations")
    df_display = df.copy()
    df_display['date_arrivee'] = pd.to_datetime(df_display['date_arrivee']).dt.strftime('%d/%m/%Y')
    df_display['date_depart'] = pd.to_datetime(df_display['date_depart']).dt.strftime('%d/%m/%Y')
    df_display['platforme_color'] = df_display['plateforme'].apply(lambda x: palette.get(x, '#ccc'))
    st.dataframe(df_display.style.apply(lambda x: [f'background-color: {c}' for c in df_display['platforme_color']], axis=0, subset=pd.IndexSlice[:, ['plateforme']]))

def vue_ajouter():
    st.header("➕ Ajouter une Réservation")
    st.write("Ajouter manuellement une nouvelle réservation.")
    with st.form("ajouter_form"):
        nom_client = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", list(DEFAULT_PALETTE.keys()))
        date_arrivee = st.date_input("Date d'arrivée")
        date_depart = st.date_input("Date de départ")
        submit_button = st.form_submit_button("Ajouter")
        if submit_button:
            # Implémentez la logique d'ajout ici
            st.success("Réservation ajoutée ! (logique à implémenter)")

def vue_modifier():
    st.header("✏️ Modifier / Supprimer")
    st.write("Modifier ou supprimer une réservation existante.")
    # Implémentez la logique de modification ici
    pass

def vue_plateformes(df, palette):
    st.header("🎨 Statistiques par Plateforme")
    plateforme_counts = df['plateforme'].value_counts()
    fig = alt.Chart(plateforme_counts.reset_index()).mark_bar().encode(
        x=alt.X('plateforme', sort='-y', title="Plateforme"),
        y=alt.Y('count', title="Nombre de réservations"),
        color=alt.Color('plateforme', scale=alt.Scale(domain=list(palette.keys()), range=list(palette.values())))
    ).properties(
        title="Nombre de réservations par plateforme"
    )
    st.altair_chart(fig, use_container_width=True)

def vue_calendrier(df, palette):
    st.header("📅 Calendrier des Réservations")
    st.write("Vue mensuelle des réservations.")
    # Implémentez la logique du calendrier ici
    pass

def vue_rapport(df):
    st.header("📊 Rapport Financier")
    st.write("Rapports et analyses financières des réservations.")
    st.write(df.describe())

def vue_sms():
    st.header("✉️ Envoi de SMS")
    st.write("Envoyer un SMS de confirmation ou de rappel.")
    # Implémentez la logique d'envoi de SMS ici
    pass

def vue_export_ics(df):
    st.header("📆 Exporter les événements")
    st.write("Télécharger un fichier ICS pour importer dans votre calendrier.")
    ics_file = generate_ics(df)
    st.download_button(
        label="Télécharger le fichier ICS",
        data=ics_file,
        file_name="reservations.ics",
        mime="text/calendar"
    )

def vue_google_sheet():
    st.header("📝 Intégration Google Sheet")
    st.write("Lien vers la feuille Google Sheets pour l'ajout rapide de réservations.")
    st.markdown(f"Cliquez sur ce lien pour ajouter une réservation : [Ajouter une réservation]({GOOGLE_FORM_URL})")

def vue_clients(df):
    st.header("👥 Base de Clients")
    st.write("Informations et historique des clients.")
    st.dataframe(df) # Remplacez par votre logique de vue des clients


# ============================== 3) GESTION DES FICHIERS ==============================
@st.cache_data
def charger_donnees():
    """Charge les données depuis un fichier téléchargé ou le fichier par défaut."""
    # Créer un widget pour le téléchargement de fichiers
    uploaded_file = st.sidebar.file_uploader("📥 Charger un fichier XLSX", type=['xlsx'])

    if uploaded_file is not None:
        # Si un fichier est téléchargé, le lire avec pd.read_excel
        try:
            df = pd.read_excel(uploaded_file, engine='openpyxl')
            st.sidebar.success("Fichier chargé avec succès !")
        except Exception as e:
            st.sidebar.error(f"Erreur lors de la lecture du fichier : {e}")
            df = pd.DataFrame() # Retourne un DataFrame vide en cas d'erreur
    else:
        # Si aucun fichier n'est téléchargé, charger le fichier par défaut
        try:
            df = pd.read_csv(CSV_RESERVATIONS, encoding='utf-8')
        except FileNotFoundError:
            st.sidebar.error(f"Fichier '{CSV_RESERVATIONS}' introuvable. Veuillez le charger.")
            df = pd.DataFrame() # Retourne un DataFrame vide si le fichier par défaut n'existe pas

    # Le reste de votre code de nettoyage et de formatage des données va ici
    df.columns = df.columns.str.lower().str.replace(' ', '_').str.replace('é', 'e').str.strip()
    
    # Nettoyage des colonnes avec des noms spécifiques
    col_mapping = {
        'nom_client': 'nom_client',
        'email': 'email',
        'plateforme': 'plateforme',
        'date_arrivee': 'date_arrivee',
        'date_depart': 'date_depart',
        'nuitees': 'nuitees',
        'prix_brut': 'prix_brut',
        'commissions': 'commissions',
        'frais_cb': 'frais_cb',
        'prix_net': 'prix_net',
        'menage': 'menage',
        'taxes_sejour': 'taxes_sejour',
        'base': 'base',
        'charges': 'charges',
        'res_id': 'res_id',
        'ical_uid': 'ical_uid',
    }
    df.rename(columns=col_mapping, inplace=True)
    
    # Correction de l'erreur 'fillna'
    df.fillna('', inplace=True)
    
    # Votre code de traitement de la palette de couleurs
    palette = {}
    
    return df, palette


# ============================== 4) GESTION DES BOUTONS CACHE ==============================
def manage_cache():
    if st.sidebar.button("🗑️ Vider le cache & recharger"):
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
            st.success("Cache vidé. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    if st.sidebar.button("🧹 Vider le cache & recharger"):
        for _clear in (getattr(st, "cache_data", None), getattr(st, "cache_resource", None)):
            try:
                if _clear: _clear.clear()
            except Exception:
                pass
        st.success("Cache vidé. Rechargement…"); st.rerun()

# ============================== 5) MAIN ==============================
def main():
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette_loaded = charger_donnees()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "📝 Google Sheet": vue_google_sheet,
        "👥 Clients": vue_clients,
    }

    st.sidebar.title("Navigation")
    selection = st.sidebar.radio("Aller à", list(pages.keys()))

    page = pages[selection]

    if selection == "📋 Réservations":
        page(df, palette)
    elif selection == "🎨 Plateformes":
        page(df, palette)
    elif selection == "📅 Calendrier":
        page(df, palette)
    elif selection == "📊 Rapport":
        page(df)
    elif selection == "👥 Clients":
        page(df)
    else:
        page()

    manage_cache()

if __name__ == "__main__":
    main()
