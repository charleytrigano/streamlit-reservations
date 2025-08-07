# app.py

# 📦 1. Imports
import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
import os

FICHIER = "reservations.xlsx"

# 📁 2. Fonctions de gestion du fichier
def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)
        if "AAAA" not in df.columns or "MM" not in df.columns:
            df["AAAA"] = pd.to_datetime(df["date_arrivee"]).dt.year
            df["MM"] = pd.to_datetime(df["date_arrivee"]).dt.month
            df.to_excel(FICHIER, index=False)
        return df
    else:
        return pd.DataFrame()

def sauvegarder_donnees(df):
    df.to_excel(FICHIER, index=False)

def uploader_excel():
    uploaded_file = st.sidebar.file_uploader("📤 Importer un fichier Excel", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        sauvegarder_donnees(df)
        st.sidebar.success("✅ Fichier importé avec succès")

def telecharger_fichier_excel(df):
    st.sidebar.download_button("📥 Télécharger Excel", data=df.to_excel(index=False), file_name="reservations.xlsx")

# 🔔 3. Notification simplifiée
def notifier_arrivees_prochaines(df):
    demain = date.today() + timedelta(days=1)
    df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
    arrivees = df[df["date_arrivee"] == demain]
    if not arrivees.empty:
        st.sidebar.warning(f"📬 {len(arrivees)} arrivée(s) prévue(s) demain !")

# 📋 4. Fonctions vues
def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

def ajouter_reservation(df):
    st.title("➕ Ajouter une réservation")
    with st.form("ajout_resa"):
        nom = st.text_input("Nom")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d’arrivée", date.today())
        depart = st.date_input("Date de départ", arrivee + timedelta(days=1))
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
                "prix_brut": prix_brut,
                "prix_net": prix_net,
                "charges": prix_brut - prix_net,
                "%": round((prix_brut - prix_net) / prix_brut * 100, 2) if prix_brut else 0,
                "nuitees": (depart - arrivee).days,
                "AAAA": arrivee.year,
                "MM": arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            sauvegarder_donnees(df)
            st.success("✅ Réservation enregistrée.")

def modifier_reservation(df):
    st.title("✏️ Modifier / Supprimer")
    df["identifiant"] = df["nom_client"] + " | " + pd.to_datetime(df["date_arrivee"]).astype(str)
    choix = st.selectbox("Choisissez une réservation", df["identifiant"])
    index = df[df["identifiant"] == choix].index[0]

    with st.form("modif_resa"):
        nom = st.text_input("Nom", df.at[index, "nom_client"])
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"], index=["Booking", "Airbnb", "Autre"].index(df.at[index, "plateforme"]))
        tel = st.text_input("Téléphone", df.at[index, "telephone"])
        arrivee = st.date_input("Arrivée", pd.to_datetime(df.at[index, "date_arrivee"]).date())
        depart = st.date_input("Départ", pd.to_datetime(df.at[index, "date_depart"]).date())
        brut = st.number_input("Prix brut", value=float(df.at[index, "prix_brut"]))
        net = st.number_input("Prix net", value=float(df.at[index, "prix_net"]))

        col1, col2 = st.columns(2)
        modifier = col1.form_submit_button("Modifier")
        supprimer = col2.form_submit_button("Supprimer")

        if modifier:
            df.at[index, "nom_client"] = nom
            df.at[index, "plateforme"] = plateforme
            df.at[index, "telephone"] = tel
            df.at[index, "date_arrivee"] = arrivee
            df.at[index, "date_depart"] = depart
            df.at[index, "prix_brut"] = brut
            df.at[index, "prix_net"] = net
            df.at[index, "charges"] = brut - net
            df.at[index, "%"] = round((brut - net) / brut * 100, 2) if brut else 0
            df.at[index, "nuitees"] = (depart - arrivee).days
            df.at[index, "AAAA"] = arrivee.year
            df.at[index, "MM"] = arrivee.month
            sauvegarder_donnees(df)
            st.success("✅ Réservation modifiée")

        if supprimer:
            df.drop(index=index, inplace=True)
            sauvegarder_donnees(df)
            st.warning("❌ Réservation supprimée")

def afficher_calendrier(df):
    st.title("📅 Calendrier mensuel")
    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()))
    mois_index = list(calendar.month_name).index(mois_nom)
    jours = [date(int(annee), mois_index, i+1) for i in range(calendar.monthrange(int(annee), mois_index)[1])]
    planning = {jour: [] for jour in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        debut = pd.to_datetime(row["date_arrivee"]).date()
        fin = pd.to_datetime(row["date_depart"]).date()
        for jour in jours:
            if debut <= jour < fin:
                icone = couleurs.get(row["plateforme"], "⬜")
                planning[jour].append(f"{icone} {row['nom_client']}")

    calendrier = []
    for semaine in calendar.monthcalendar(int(annee), mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                j = date(int(annee), mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning.get(j, []))
                ligne.append(contenu)
        calendrier.append(ligne)

    st.table(pd.DataFrame(calendrier, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

def afficher_rapport(df):
    st.title("📊 Rapport")
    plateforme = st.selectbox("Filtrer par plateforme", ["Toutes"] + sorted(df["plateforme"].dropna().unique()))
    if plateforme != "Toutes":
        df = df[df["plateforme"] == plateforme]

    stats = df.groupby(["AAAA", "MM", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois_texte"] = stats["MM"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["AAAA"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

def liste_clients(df):
    st.title("👥 Liste des clients")
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()))
    mois = st.selectbox("Mois", ["Tous"] + list(range(1, 13)))

    data = df[df["AAAA"] == annee]
    if mois != "Tous":
        data = data[data["MM"] == mois]

    st.dataframe(data[["nom_client", "plateforme", "date_arrivee", "date_depart", "prix_brut", "prix_net", "charges"]])
    st.download_button("📥 Télécharger CSV", data=data.to_csv(index=False).encode("utf-8"), file_name="clients.csv")

def historique_sms():
    st.title("✉️ Historique SMS")
    st.info("Fonctionalité à venir...")

# ▶️ 5. Application principale
def main():
    st.set_page_config("📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    uploader_excel()
    df = charger_donnees()

    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    notifier_arrivees_prochaines(df)

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations", "➕ Ajouter", "✏️ Modifier / Supprimer",
        "📅 Calendrier", "📊 Rapport", "👥 Liste clients", "✉️ Historique SMS"
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
