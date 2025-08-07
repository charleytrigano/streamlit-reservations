
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
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    st.sidebar.markdown("### 📤 Importer un fichier")
    uploader_excel()

    df = charger_donnees()

    if df.empty:
        st.warning("Aucune donnée disponible. Veuillez importer un fichier Excel.")
        return

    notifier_arrivees_prochaines(df)

    onglet = st.sidebar.radio("Navigation", [
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
        afficher_calendrier(df)

    elif onglet == "📊 Rapport":
        afficher_rapport(df)

    elif onglet == "👥 Liste clients":
        liste_clients(df)

    elif onglet == "✉️ Historique SMS":
        historique_sms()

if __name__ == "__main__":
    main()
