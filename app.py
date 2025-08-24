import streamlit as st
from io_utils import charger_donnees, sauvegarder_donnees, bouton_restaurer, bouton_telecharger
from palette_utils import render_palette_editor_sidebar
from reservations_view import vue_reservations
from calendar_view import vue_calendrier
from rapport_view import vue_rapport
from clients_view import vue_clients

st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

def main():
    # Navigation
    st.sidebar.title("🧭 Navigation")
    page = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations", "📅 Calendrier", "📊 Rapport", "👥 Clients", "🎨 Plateformes"]
    )

    # Chargement des données
    df = charger_donnees()

    # Palette (plateformes)
    render_palette_editor_sidebar()

    # Actions globales
    bouton_restaurer()
    bouton_telecharger(df)

    # Navigation
    if page == "📋 Réservations":
        vue_reservations(df)
    elif page == "📅 Calendrier":
        vue_calendrier(df)
    elif page == "📊 Rapport":
        vue_rapport(df)
    elif page == "👥 Clients":
        vue_clients(df)
    elif page == "🎨 Plateformes":
        st.title("🎨 Gestion des plateformes")
        st.info("Ajoutez, modifiez ou supprimez vos plateformes dans la barre latérale.")

if __name__ == "__main__":
    main()