# app.py — point d'entrée

import streamlit as st

# Vues importées (assure-toi que ces fichiers existent à la racine)
from reservations_view import vue_reservations, vue_ajouter, vue_modifier
from plateformes_view import vue_plateformes
from calendrier_view import vue_calendrier
from rapport_view import vue_rapport
from clients_view import vue_clients
from sms_view import vue_sms
from ics_utils import vue_export_ics

# Outils I/O centralisés
from io_utils import (
    charger_donnees, charger_plateformes,
    bouton_telecharger, bouton_restaurer,
    render_cache_section_sidebar,
)

st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

def main():
    # === Barre latérale : Fichier ===
    st.sidebar.title("📁 Fichier")
    df_tmp = charger_donnees()
    bouton_telecharger(df_tmp)
    bouton_restaurer()

    # === Barre latérale : Maintenance ===
    render_cache_section_sidebar()

    # === Navigation ===
    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        [
            "📋 Réservations",
            "➕ Ajouter",
            "✏️ Modifier / Supprimer",
            "🎨 Plateformes",
            "📅 Calendrier",
            "📊 Rapport",
            "👥 Liste clients",
            "📤 Export ICS",
            "✉️ SMS",
        ],
    )

    # === Données ===
    df = charger_donnees()

    # === Routage ===
    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "➕ Ajouter":
        vue_ajouter(df)
    elif onglet == "✏️ Modifier / Supprimer":
        vue_modifier(df)
    elif onglet == "🎨 Plateformes":
        vue_plateformes(df, charger_plateformes())
    elif onglet == "📅 Calendrier":
        vue_calendrier(df)
    elif onglet == "📊 Rapport":
        vue_rapport(df)
    elif onglet == "👥 Liste clients":
        vue_clients(df)
    elif onglet == "📤 Export ICS":
        vue_export_ics(df)
    elif onglet == "✉️ SMS":
        vue_sms(df)

if __name__ == "__main__":
    main()