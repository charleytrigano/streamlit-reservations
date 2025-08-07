import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
import os

FICHIER = "reservations.xlsx"

# 🔁 Restaurer un fichier Excel modifié par l'utilisateur
def restaurer_fichier_excel():
    st.sidebar.markdown("### 🔁 Restaurer un fichier modifié")
    fichier = st.sidebar.file_uploader("Sélectionner un fichier Excel (.xlsx)", type=["xlsx"], key="restore")

    if fichier:
        with open(FICHIER, "wb") as f:
            f.write(fichier.read())
        st.sidebar.success("✅ Fichier restauré avec succès.")
        df_recharge = pd.read_excel(FICHIER)
        return df_recharge
    return None

# 📥 Charger les données existantes
def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)
        if "annee" not in df.columns or "mois" not in df.columns:
            df["date_arrivee"] = pd.to_datetime(df["date_arrivee"])
            df["annee"] = df["date_arrivee"].dt.year
            df["mois"] = df["date_arrivee"].dt.month
            df.to_excel(FICHIER, index=False)
        return df
    else:
        return pd.DataFrame()

# 📤 Télécharger les données Excel actuelles
def telecharger_fichier_excel(df):
    st.sidebar.download_button(
        label="📥 Télécharger le fichier Excel",
        data=df.to_excel(index=False),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 📋 Réservations
def afficher_reservations(df):
    st.subheader("📋 Réservations")
    st.dataframe(df)

# ➕ Ajouter une réservation
def ajouter_reservation(df):
    st.subheader("➕ Nouvelle Réservation")
    with st.form("ajouter"):
        nom = st.text_input("Nom")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        telephone = st.text_input("Téléphone")
        arrivee = st.date_input("Date d'arrivée")
        depart = st.date_input("Date de départ", min_value=arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut", min_value=0.0)
        prix_net = st.number_input("Prix net", min_value=0.0, max_value=prix_brut)
        submit = st.form_submit_button("Enregistrer")
        if submit:
            ligne = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": telephone,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "prix_brut": prix_brut,
                "prix_net": prix_net,
                "charges": prix_brut - prix_net,
                "%": round(((prix_brut - prix_net) / prix_brut) * 100, 2) if prix_brut else 0,
                "nuitees": (depart - arrivee).days,
                "annee": arrivee.year,
                "mois": arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation ajoutée avec succès.")

# ✏️ Modifier / Supprimer
def modifier_reservation(df):
    st.subheader("✏️ Modifier / Supprimer une réservation")
    df["identifiant"] = df["nom_client"] + " | " + df["date_arrivee"].astype(str)
    selection = st.selectbox("Sélectionnez une réservation", df["identifiant"])
    i = df[df["identifiant"] == selection].index[0]
    with st.form("modifier"):
        nom = st.text_input("Nom", df.at[i, "nom_client"])
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"], index=["Booking", "Airbnb", "Autre"].index(df.at[i, "plateforme"]))
        telephone = st.text_input("Téléphone", df.at[i, "telephone"])
        arrivee = st.date_input("Date d'arrivée", df.at[i, "date_arrivee"])
        depart = st.date_input("Date de départ", df.at[i, "date_depart"])
        prix_brut = st.number_input("Prix brut", value=float(df.at[i, "prix_brut"]))
        prix_net = st.number_input("Prix net", value=float(df.at[i, "prix_net"]))
        modifier = st.form_submit_button("Modifier")
        supprimer = st.form_submit_button("Supprimer")

        if modifier:
            df.at[i, "nom_client"] = nom
            df.at[i, "plateforme"] = plateforme
            df.at[i, "telephone"] = telephone
            df.at[i, "date_arrivee"] = arrivee
            df.at[i, "date_depart"] = depart
            df.at[i, "prix_brut"] = prix_brut
            df.at[i, "prix_net"] = prix_net
            df.at[i, "charges"] = prix_brut - prix_net
            df.at[i, "%"] = round(((prix_brut - prix_net) / prix_brut) * 100, 2) if prix_brut else 0
            df.at[i, "nuitees"] = (depart - arrivee).days
            df.at[i, "annee"] = arrivee.year
            df.at[i, "mois"] = arrivee.month
            df.drop(columns="identifiant", inplace=True)
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation modifiée.")

        if supprimer:
            df.drop(index=i, inplace=True)
            df.drop(columns="identifiant", inplace=True)
            df.to_excel(FICHIER, index=False)
            st.warning("❌ Réservation supprimée.")

# 📅 Calendrier mensuel
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")
    if df.empty:
        st.info("Aucune réservation disponible.")
        return

    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    annee = st.selectbox("Année", sorted(df["annee"].dropna().unique()))
    mois_index = list(calendar.month_name).index(mois_nom)

    jours_du_mois = [date(int(annee), mois_index, j + 1) for j in range(calendar.monthrange(int(annee), mois_index)[1])]
    planning = {jour: [] for jour in jours_du_mois}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        debut = pd.to_datetime(row["date_arrivee"]).date()
        fin = pd.to_datetime(row["date_depart"]).date()
        for jour in jours_du_mois:
            if debut <= jour < fin:
                icone = couleurs.get(row["plateforme"], "⬜")
                planning[jour].append(f"{icone} {row['nom_client']}")

    tableau = []
    for semaine in calendar.monthcalendar(int(annee), mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                jour_date = date(int(annee), mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning.get(jour_date, []))
                ligne.append(contenu)
        tableau.append(ligne)

    st.table(pd.DataFrame(tableau, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

# 📊 Rapport
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")
    if df.empty:
        st.info("Aucune donnée à afficher.")
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
    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### 🛌 Nuitées")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))

    st.markdown("### 💸 Charges")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

# 👥 Liste des clients
def liste_clients(df):
    st.subheader("👥 Liste des clients")
    if df.empty:
        st.info("Aucune donnée.")
        return
    st.dataframe(df[["nom_client", "plateforme", "date_arrivee", "date_depart", "prix_brut", "prix_net", "telephone"]])

# ▶️ Point d’entrée
def main():
    st.set_page_config(page_title="📖 Réservations", layout="wide")
    st.sidebar.title("📁 Menu")

    # 🔁 Restauration
    df_restauré = restaurer_fichier_excel()

    # 📊 Chargement des données
    if df_restauré is not None:
        df = df_restauré
    else:
        df = charger_donnees()

    if df.empty:
        st.warning("Veuillez importer ou restaurer un fichier.")
        return

    # 🧭 Navigation
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
