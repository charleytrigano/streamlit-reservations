import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta, datetime
import os

FICHIER = "reservations.xlsx"

# 🎨 Couleurs par plateforme
COULEURS = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

# 📂 Chargement des données
def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
        return df
    else:
        return pd.DataFrame(columns=[
            "nom_client", "plateforme", "telephone", "date_arrivee", "date_depart",
            "prix_brut", "prix_net", "charges", "%", "nuitees", "annee", "mois"
        ])

# 📤 Uploader manuel
def uploader_excel():
    fichier = st.sidebar.file_uploader("📤 Importer un fichier Excel", type=["xlsx"])
    if fichier:
        df = pd.read_excel(fichier)
        df.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier importé")

# 📥 Télécharger le fichier
def telecharger_fichier_excel(df):
    st.sidebar.download_button(
        label="📥 Télécharger Excel",
        data=df.to_excel(index=False),
        file_name="reservations.xlsx"
    )

# 📋 Affichage des réservations
def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

# ➕ Ajouter une réservation
def ajouter_reservation(df):
    st.subheader("➕ Nouvelle Réservation")
    with st.form("ajout"):
        nom = st.text_input("Nom")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date arrivée")
        depart = st.date_input("Date départ", min_value=arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut", min_value=0.0)
        prix_net = st.number_input("Prix net", min_value=0.0, max_value=prix_brut)
        submit = st.form_submit_button("Enregistrer")
        if submit:
            ligne = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": tel,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "prix_brut": round(prix_brut, 2),
                "prix_net": round(prix_net, 2),
                "charges": round(prix_brut - prix_net, 2),
                "%": round((prix_brut - prix_net) / prix_brut * 100, 2) if prix_brut else 0,
                "nuitees": (depart - arrivee).days,
                "annee": arrivee.year,
                "mois": arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation enregistrée")

# ✏️ Modifier ou supprimer
def modifier_reservation(df):
    st.subheader("✏️ Modifier / Supprimer")
    df["identifiant"] = df["nom_client"] + " | " + df["date_arrivee"].astype(str)
    selection = st.selectbox("Choisissez une réservation", df["identifiant"])
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
            df.at[i, "prix_brut"] = round(brut, 2)
            df.at[i, "prix_net"] = round(net, 2)
            df.at[i, "charges"] = round(brut - net, 2)
            df.at[i, "%"] = round((brut - net) / brut * 100, 2) if brut else 0
            df.at[i, "nuitees"] = (depart - arrivee).days
            df.at[i, "annee"] = arrivee.year
            df.at[i, "mois"] = arrivee.month
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation modifiée")
        if delete:
            df.drop(index=i, inplace=True)
            df.to_excel(FICHIER, index=False)
            st.warning("🗑 Réservation supprimée")

# 📅 Calendrier
def afficher_calendrier(df):
    st.subheader("📅 Calendrier")
    if df.empty:
        st.info("Aucune donnée.")
        return

    col1, col2 = st.columns(2)
    with col1:
        mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    with col2:
        annee = st.selectbox("Année", sorted(df["annee"].dropna().unique()))

    mois_index = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(int(annee), mois_index)[1]
    jours = [date(int(annee), mois_index, i + 1) for i in range(nb_jours)]
    planning = {jour: [] for jour in jours}

    for _, row in df.iterrows():
        debut = row["date_arrivee"]
        fin = row["date_depart"]
        for jour in jours:
            if debut <= jour < fin:
                icone = COULEURS.get(row["plateforme"], "⬜")
                planning[jour].append(f"{icone} {row['nom_client']}")

    table = []
    for semaine in calendar.monthcalendar(int(annee), mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                jour_date = date(int(annee), mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning[jour_date])
                ligne.append(contenu)
        table.append(ligne)
    st.table(pd.DataFrame(table, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

# 📊 Rapport
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")
    if df.empty:
        st.info("Aucune donnée.")
        return

    stats = df.groupby(["annee", "mois", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()
    stats["mois_texte"] = stats["mois"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["annee"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.markdown("### 📈 Revenus bruts")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### 🛌 Nuitées")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))

# 👥 Liste des clients
def liste_clients(df):
    st.subheader("👥 Liste des clients")
    annee = st.selectbox("Année", sorted(df["annee"].dropna().unique()), key="annee_clients")
    mois = st.selectbox("Mois", ["Tous"] + list(range(1, 13)), key="mois_clients")
    data = df[df["annee"] == annee]
    if mois != "Tous":
        data = data[data["mois"] == mois]
    st.dataframe(data)

# ✉️ Historique (factice)
def historique_sms():
    st.subheader("✉️ Historique SMS")
    st.info("Fonction non activée (démo)")

# ▶️ App principale
def main():
    st.set_page_config("📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")
    uploader_excel()
    df = charger_donnees()

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
