import streamlit as st
import pandas as pd
import os

from sms import notifier_arrivees_prochaines, historique_sms
from views import afficher_reservations  # 👈 Pour l'instant, on importe uniquement celle-ci
    afficher_reservations,
    ajouter_reservation,
    modifier_reservation,
    afficher_calendrier,
    afficher_rapport,
    liste_clients,
)

FICHIER = "reservations.xlsx"

# 📂 Import manuel d’un fichier Excel
def importer_fichier():
    st.sidebar.markdown("### 📂 Importer un fichier Excel")
    uploaded_file = st.sidebar.file_uploader("Sélectionner un fichier .xlsx", type=["xlsx"])
    if uploaded_file:
        df_new = pd.read_excel(uploaded_file)
        df_new.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier importé avec succès")
        return df_new
    elif os.path.exists(FICHIER):
        return pd.read_excel(FICHIER)
    else:
        st.warning("Aucun fichier disponible.")
        return pd.DataFrame()

def main():
    df = importer_fichier()

    # ✅ Forcer les colonnes de dates au format date uniquement
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.date
    if "date_depart" in df.columns:
        df["date_depart"] = pd.to_datetime(df["date_depart"], errors="coerce").dt.date

    notifier_arrivees_prochaines(df)

    onglet = st.sidebar.radio(
        "Menu",
        [
            "📋 Réservations",
            "➕ Ajouter",
            "✏️ Modifier / Supprimer",
            "📅 Calendrier",
            "📊 Rapport",
            "👥 Liste clients",
            "✉️ Historique SMS",
        ],
    )

    if onglet == "📋 Réservations":
        afficher_reservations(df)
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
