import streamlit as st
from data_loader import charger_donnees, telecharger_fichier_excel, uploader_excel
from views import (
    afficher_reservations,
    ajouter_reservation,
    modifier_reservation,
    afficher_calendrier,
    afficher_rapport,
    liste_clients
)
from sms import notifier_arrivees_prochaines, historique_sms

def main():
    st.set_page_config(page_title="Réservations Villa Tobias", layout="wide")
    st.sidebar.markdown("## 📤 Importer un fichier Excel")
    uploader_excel()

    df = charger_donnees()
    if df.empty:
        st.warning("Aucune donnée disponible. Veuillez importer un fichier Excel.")
        return

    # 🔔 Envoi automatique des SMS de rappel si arrivée demain
    notifier_arrivees_prochaines(df)

    # Navigation par onglets
    onglet = st.sidebar.radio("Menu", [
        "📋 Réservations",
        "➕ Ajouter",
        "✏️ Modifier / Supprimer",
        "📅 Calendrier",
        "📊 Rapport",
        "👥 Liste clients",
        "✉️ Historique SMS"
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)
        telecharger_fichier_excel(df)

    elif onglet == "➕ Ajouter":
        ajouter_reservation(df)

    elif onglet == "✏️ Modifier / Supprimer":
        modifier_reservation(df)

    elif onglet == "📅 Calendrier":
