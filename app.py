import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
import os
from pathlib import Path

FICHIER = "reservations.xlsx"

# 📤 Importer un fichier Excel dans l'application
def uploader_excel():
    fichier = st.sidebar.file_uploader("📤 Importer un fichier Excel", type=["xlsx"])
    if fichier:
        df = pd.read_excel(fichier)
        df.to_excel(FICHIER, index=False)
        st.success("✅ Fichier importé avec succès")

# 📥 Télécharger le fichier Excel actuel
def telecharger_fichier_excel(df):
    st.sidebar.download_button(
        label="📥 Télécharger le fichier Excel",
        data=df.to_excel(index=False),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 📄 Charger les données avec conversion de dates et ajout AAAA/MM
def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)

        # Convertir les colonnes date en format "date" uniquement
        if "date_arrivee" in df.columns:
            df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        if "date_depart" in df.columns:
            df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date

        # Ajouter AAAA et MM si manquantes
        if "AAAA" not in df.columns:
            df["AAAA"] = pd.to_datetime(df["date_arrivee"]).dt.year
        if "MM" not in df.columns:
            df["MM"] = pd.to_datetime(df["date_arrivee"]).dt.month

        return df
    return pd.DataFrame()

# 📋 Réservations
def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

# ➕ Ajout
def ajouter_reservation(df):
    st.subheader("➕ Ajouter une réservation")
    with st.form("ajout_resa"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d'arrivée")
        depart = st.date_input("Date de départ", min_value=arrivee + timedelta(days=1))
        brut = st.number_input("Prix brut", min_value=0.0)
        net = st.number_input("Prix net", min_value=0.0, max_value=brut)
        submit = st.form_submit_button("Enregistrer")
        if submit:
            ligne = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": tel,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "prix_brut": brut,
                "prix_net": net,
                "charges": brut - net,
                "nuitees": (depart - arrivee).days,
                "AAAA": arrivee.year,
                "MM": arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation ajoutée")

# ✏️ Modifier
def modifier_reservation(df):
    st.subheader("✏️ Modifier une réservation")
    if "nom_client" not in df.columns or df.empty:
        st.warning("Aucune donnée disponible.")
        return
    df["identifiant"] = df["nom_client"] + " | " + df["date_arrivee"].astype(str)
    selection = st.selectbox("Choisir une réservation", df["identifiant"])
    i = df[df["identifiant"] == selection].index[0]
    with st.form("modif_form"):
        nom = st.text_input("Nom", df.at[i, "nom_client"])
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"], index=["Booking", "Airbnb", "Autre"].index(df.at[i, "plateforme"]))
        tel = st.text_input("Téléphone", df.at[i, "telephone"])
        arrivee = st.date_input("Date d'arrivée", df.at[i, "date_arrivee"])
        depart = st.date_input("Date de départ", df.at[i, "date_depart"])
        brut = st.number_input("Prix brut", value=float(df.at[i, "prix_brut"]))
        net = st.number_input("Prix net", value=float(df.at[i, "prix_net"]))
        submit = st.form_submit_button("Enregistrer")
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
            df.at[i, "nuitees"] = (depart - arrivee).days
            df.at[i, "AAAA"] = arrivee.year
            df.at[i, "MM"] = arrivee.month
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation modifiée")
        if delete:
            df.drop(index=i, inplace=True)
            df.to_excel(FICHIER, index=False)
            st.warning("❌ Réservation supprimée")

# 📅 Calendrier
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")

    if df.empty:
        st.warning("Aucune donnée.")
        return

    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    annee_dispo = sorted(df["AAAA"].dropna().unique())
    annee = st.selectbox("Année", annee_dispo)

    mois_index = list(calendar.month_name).index(mois_nom)
    jours_du_mois = [date(int(annee), mois_index, j + 1) for j in range(calendar.monthrange(int(annee), mois_index)[1])]
    planning = {jour: [] for jour in jours_du_mois}

    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        debut = row["date_arrivee"]
        fin = row["date_depart"]
        for jour in jours_du_mois:
            if debut <= jour < fin:
                couleur = couleurs.get(row["plateforme"], "⬜")
                planning[jour].append(f"{couleur} {row['nom_client']}")

    table = []
    for semaine in calendar.monthcalendar(int(annee), mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                d = date(int(annee), mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning[d])
                ligne.append(contenu)
        table.append(ligne)

    st.table(pd.DataFrame(table, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

# 📊 Rapport
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")

    if df.empty:
        st.warning("Aucune donnée.")
        return

    stats = df.groupby(["AAAA", "MM", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois_texte"] = stats["MM"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["AAAA"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

# 👥 Clients
def liste_clients(df):
    st.subheader("👥 Liste des clients")
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()))
    mois = st.selectbox("Mois", ["Tous"] + list(range(1, 13)))
    filtres = df[df["AAAA"] == annee]
    if mois != "Tous":
        filtres = filtres[filtres["MM"] == mois]

    if not filtres.empty:
        filtres["prix_brut/nuit"] = filtres["prix_brut"] / filtres["nuitees"]
        filtres["prix_net/nuit"] = filtres["prix_net"] / filtres["nuitees"]
        colonnes = ["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "prix_brut", "prix_net", "charges", "prix_brut/nuit", "prix_net/nuit"]
        st.dataframe(filtres[colonnes])
    else:
        st.info("Aucune donnée pour cette période.")

# ▶️ Lancer l'app
def main():
    st.set_page_config(page_title="Villa Tobias", layout="wide")
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
