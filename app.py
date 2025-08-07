import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
import os
from io import BytesIO

FICHIER = "reservations.xlsx"

# 📥 Charger les données depuis le fichier Excel
def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)
        if 'date_arrivee' in df.columns:
            df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        if 'date_depart' in df.columns:
            df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
        if 'date_arrivee' in df.columns and 'annee' not in df.columns:
            df["annee"] = pd.to_datetime(df["date_arrivee"]).dt.year
        if 'date_arrivee' in df.columns and 'mois' not in df.columns:
            df["mois"] = pd.to_datetime(df["date_arrivee"]).dt.month
        return df
    else:
        return pd.DataFrame()

# 📤 Télécharger le fichier Excel
def telecharger_fichier_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False, engine='openpyxl')
    buffer.seek(0)

    st.sidebar.download_button(
        label="📥 Télécharger le fichier Excel",
        data=buffer,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 📤 Importer un nouveau fichier
def uploader_excel():
    uploaded_file = st.sidebar.file_uploader("Importer un fichier Excel", type="xlsx")
    if uploaded_file is not None:
        df = pd.read_excel(uploaded_file)
        df.to_excel(FICHIER, index=False)
        st.success("Fichier importé avec succès !")

# 📋 Affichage des réservations
def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

# ➕ Ajouter une réservation
def ajouter_reservation(df):
    st.subheader("➕ Nouvelle Réservation")
    with st.form("ajout"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d'arrivée")
        depart = st.date_input("Date de départ", min_value=arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut (€)", min_value=0.0)
        prix_net = st.number_input("Prix net (€)", min_value=0.0, max_value=prix_brut)

        submit = st.form_submit_button("Enregistrer")

        if submit:
            ligne = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": tel,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "prix_brut": prix_brut,
                "prix_net": prix_net,
                "charges": prix_brut - prix_net,
                "%": round((prix_brut - prix_net) / prix_brut * 100, 2) if prix_brut else 0,
                "nuitees": (depart - arrivee).days,
                "annee": arrivee.year,
                "mois": arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation ajoutée avec succès.")

# ✏️ Modifier une réservation
def modifier_reservation(df):
    st.subheader("✏️ Modifier / Supprimer une réservation")
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    df["identifiant"] = df["nom_client"] + " - " + pd.to_datetime(df["date_arrivee"]).astype(str)
    selection = st.selectbox("Sélectionner une réservation", df["identifiant"])
    i = df[df["identifiant"] == selection].index[0]

    with st.form("modif"):
        nom = st.text_input("Nom", df.at[i, "nom_client"])
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"], index=["Booking", "Airbnb", "Autre"].index(df.at[i, "plateforme"]))
        tel = st.text_input("Téléphone", df.at[i, "telephone"])
        arrivee = st.date_input("Arrivée", df.at[i, "date_arrivee"])
        depart = st.date_input("Départ", df.at[i, "date_depart"])
        brut = st.number_input("Prix brut", value=float(df.at[i, "prix_brut"]))
        net = st.number_input("Prix net", value=float(df.at[i, "prix_net"]))

        submit = st.form_submit_button("Modifier")
        delete = st.form_submit_button("Supprimer")

        if submit:
            df.at[i, "nom_client"] = nom
            df.at[i, "plateforme"] = plateforme
            df.at[i, "telephone"] = tel
            df.at[i, "date_arrivee"] = arrivee
            df.at[i, "date_depart"] = depart
            df.at[i, "prix_brut"] = brut
            df.at[i, "prix_net"] = net
            df.at[i, "charges"] = brut - net
            df.at[i, "%"] = round((brut - net) / brut * 100, 2) if brut else 0
            df.at[i, "nuitees"] = (depart - arrivee).days
            df.at[i, "annee"] = arrivee.year
            df.at[i, "mois"] = arrivee.month
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation modifiée.")

        if delete:
            df.drop(index=i, inplace=True)
            df.to_excel(FICHIER, index=False)
            st.warning("🗑️ Réservation supprimée.")

# 📅 Calendrier (placeholder)
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")
    st.info("📆 Le calendrier sera intégré prochainement avec filtres et couleurs par plateforme.")

# 📊 Rapport (placeholder)
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")
    st.info("📈 Le rapport mensuel sera réactivé avec filtres par plateforme et graphiques.")

# 👥 Liste clients
def liste_clients(df):
    st.subheader("👥 Liste des clients")
    st.dataframe(df[["nom_client", "plateforme", "telephone", "date_arrivee", "date_depart"]])

# ▶️ App principale
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    uploader_excel()
    df = charger_donnees()

    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "➕ Ajouter",
        "✏️ Modifier / Supprimer",
        "📅 Calendrier",
        "📊 Rapport",
        "👥 Liste clients"
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

if __name__ == "__main__":
    main()
