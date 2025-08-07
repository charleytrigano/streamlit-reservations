import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta, datetime
import os

FICHIER = "reservations.xlsx"

# 🔄 Charger les données depuis le fichier Excel
def charger_donnees():
    if not os.path.exists(FICHIER):
        return pd.DataFrame()
    df = pd.read_excel(FICHIER)
    # Conversion des dates
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
    if "date_depart" in df.columns:
        df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
    # Ajouter colonnes année et mois si absentes
    if "annee" not in df.columns or "mois" not in df.columns:
        df["annee"] = pd.to_datetime(df["date_arrivee"]).dt.year
        df["mois"] = pd.to_datetime(df["date_arrivee"]).dt.month
        df.to_excel(FICHIER, index=False)
    return df

# 💾 Sauvegarder les données dans le fichier Excel
def sauvegarder(df):
    df.to_excel(FICHIER, index=False)

# 📋 Réservations
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
            sauvegarder(df)
            st.success("✅ Réservation enregistrée")

# ✏️ Modifier / Supprimer
def modifier_reservation(df):
    st.subheader("✏️ Modifier / Supprimer")
    if df.empty:
        st.warning("Aucune réservation à modifier.")
        return
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
            sauvegarder(df)
            st.success("✅ Réservation modifiée")
        if delete:
            df.drop(index=i, inplace=True)
            sauvegarder(df)
            st.warning("🗑 Réservation supprimée")

# 📅 Calendrier mensuel
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")
    if df.empty:
        st.warning("Aucune donnée disponible.")
        return
    col1, col2 = st.columns(2)
    with col1:
        mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    with col2:
        annees_disponibles = sorted(df["annee"].dropna().unique())
        annee = st.selectbox("Année", annees_disponibles)
    mois_index = list(calendar.month_name).index(mois_nom)
    jours_du_mois = [date(int(annee), mois_index, j + 1) for j in range(calendar.monthrange(int(annee), mois_index)[1])]
    planning = {jour: [] for jour in jours_du_mois}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}
    for _, row in df.iterrows():
        debut = row["date_arrivee"]
        fin = row["date_depart"]
        for jour in jours_du_mois:
            if debut <= jour < fin:
                icone = couleurs.get(row["plateforme"], "⬜")
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
        st.warning("Aucune donnée disponible.")
        return
    plateformes = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    filtre = st.selectbox("Filtrer par plateforme", plateformes)
    if filtre != "Toutes":
        df = df[df["plateforme"] == filtre]
    stats = df.groupby(["annee", "mois", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()
    stats["mois"] = stats["mois"].astype(int)
    stats["mois_texte"] = stats["mois"].apply(lambda x: calendar.month_abbr[x])
    stats["période"] = stats["mois_texte"] + " " + stats["annee"].astype(str)
    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])
    st.markdown("### 📈 Revenus bruts vs nets")
    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))
    st.markdown("### 🛌 Nuitées par mois")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))
    st.markdown("### 📊 Charges mensuelles")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

# 👥 Liste des clients
def liste_clients(df):
    st.subheader("👥 Liste des clients")
    if df.empty:
        st.info("Aucune donnée à afficher.")
        return
    st.dataframe(df)

# ▶️ Application principale
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    df = charger_donnees()

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
