import streamlit as st
import pandas as pd
import calendar
from datetime import date
import os

FICHIER = "reservations.xlsx"

def charger_donnees():
    if os.path.exists(FICHIER):
        return pd.read_excel(FICHIER)
    else:
        return pd.DataFrame()

def uploader_excel():
    uploaded_file = st.sidebar.file_uploader("📤 Importer un fichier Excel", type=["xlsx"])
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier importé avec succès")

def telecharger_fichier_excel(df):
    st.sidebar.download_button(
        label="📥 Télécharger le fichier Excel",
        data=df.to_excel(index=False),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")

    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:], index=date.today().month - 1)
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique().astype(int)), index=0)

    mois_index = list(calendar.month_name).index(mois_nom)
    jours = [date(int(annee), mois_index, i+1) for i in range(calendar.monthrange(int(annee), mois_index)[1])]
    planning = {jour: [] for jour in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        try:
            debut = pd.to_datetime(row["date_arrivee"]).date()
            fin = pd.to_datetime(row["date_depart"]).date()
            for jour in jours:
                if debut <= jour < fin:
                    icone = couleurs.get(row.get("plateforme", "Autre"), "⬜")
                    planning[jour].append(f"{icone} {row.get('nom_client', '')}")
        except:
            continue

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

def afficher_rapport(df):
    st.subheader("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    plateformes = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    filtre = st.selectbox("Filtrer par plateforme", plateformes)
    if filtre != "Toutes":
        df = df[df["plateforme"] == filtre]

    stats = df.groupby(["AAAA", "MM", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois_texte"] = stats["MM"].apply(lambda x: f"{calendar.month_abbr[int(x)]}")
    stats["période"] = stats["mois_texte"] + " " + stats["AAAA"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

def main():
    st.set_page_config(page_title="📖 Réservations", layout="wide")
    st.sidebar.title("📁 Menu")

    uploader_excel()
    df = charger_donnees()

    # Correction colonnes AAAA et MM
    if not df.empty:
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors='coerce')
        if "AAAA" not in df.columns or "MM" not in df.columns:
            df["AAAA"] = df["date_arrivee"].dt.year
            df["MM"] = df["date_arrivee"].dt.month
            df.to_excel(FICHIER, index=False)
            st.success("✅ Colonnes AAAA et MM ajoutées.")

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "📅 Calendrier",
        "📊 Rapport"
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)
        telecharger_fichier_excel(df)

    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)

    elif onglet == "📊 Rapport":
        afficher_rapport(df)

if __name__ == "__main__":
    main()
