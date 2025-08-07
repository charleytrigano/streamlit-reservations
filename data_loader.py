from pathlib import Path

# Contenu du fichier data_loader.py
data_loader_content = """
import pandas as pd
import os

FICHIER = "reservations.xlsx"

def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)

        # Ajout des colonnes annee et mois à partir de date_arrivee
        if "date_arrivee" in df.columns:
            df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce")
            df["annee"] = df["date_arrivee"].dt.year
            df["mois"] = df["date_arrivee"].dt.month

        return df
    else:
        return pd.DataFrame()

def uploader_excel():
    import streamlit as st
    uploaded_file = st.sidebar.file_uploader("Importer un fichier .xlsx", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df.to_excel(FICHIER, index=False)
        st.success("✅ Fichier importé avec succès.")

def telecharger_fichier_excel(df):
    import streamlit as st
    from io import BytesIO
    output = BytesIO()
    df.to_excel(output, index=False)
    st.download_button(
        label="📥 Télécharger le fichier Excel",
        data=output.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
"""

# Contenu du fichier app.py
app_py_content = """
import streamlit as st
from data_loader import charger_donnees, telecharger_fichier_excel, uploader_excel
from sms import notifier_arrivees_prochaines, historique_sms
from views import (
    afficher_reservations,
    ajouter_reservation,
    modifier_reservation,
    afficher_calendrier,
    afficher_rapport,
    liste_clients
)

def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    # Importer un fichier Excel depuis l'utilisateur
    st.sidebar.markdown("### 📤 Importer un fichier")
    uploader_excel()

    # Charger les données du fichier
    df = charger_donnees()

    if df.empty:
        st.warning("Aucune donnée disponible. Veuillez importer un fichier Excel.")
        return

    # Notification automatique la veille de l'arrivée
    notifier_arrivees_prochaines(df)

    # Menu de navigation
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
"""

# Écriture des fichiers
Path("/mnt/data/data_loader.py").write_text(data_loader_content.strip(), encoding="utf-8")
Path("/mnt/data/app.py").write_text(app_py_content.strip(), encoding="utf-8")

"/mnt/data/app.py", "/mnt/data/data_loader.py"

