import streamlit as st
import pandas as pd
import calendar
from datetime import date
import os

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

# 🧼 Traitement automatique des colonnes annee et mois
def ajouter_colonnes_automatiques(df):
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce")
        df["annee"] = df["date_arrivee"].dt.year
        df["mois"] = df["date_arrivee"].dt.month
    return df

# 📋 Onglets
def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")

    if df.empty or "annee" not in df.columns or df["annee"].dropna().empty:
        st.warning("Aucune année valide disponible.")
        return

    # Choix du mois et de l’année
    col1, col2 = st.columns(2)
    with col1:
        mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    with col2:
        annees = sorted(df["annee"].dropna().unique())
        annee = st.selectbox("Année", annees)

    mois_index = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(int(annee), mois_index)[1]
    jours = [date(int(annee), mois_index, j + 1) for j in range(nb_jours)]

    planning = {jour: [] for jour in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        debut = pd.to_datetime(row["date_arrivee"], errors="coerce")
        fin = pd.to_datetime(row["date_depart"], errors="coerce")
        for jour in jours:
            if pd.notna(debut) and pd.notna(fin) and debut <= jour < fin:
                icone = couleurs.get(row.get("plateforme", "Autre"), "⬜")
                planning[jour].append(f"{icone} {row.get('nom_client', '')}")

    # Création du tableau mensuel
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
    st.subheader("📊 Rapport mensuel")

    if df.empty:
        st.info("Aucune donnée disponible.")
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

    stats["mois_texte"] = stats["mois"].apply(lambda x: calendar.month_abbr[int(x)] if pd.notnull(x) else "")
    stats["période"] = stats["mois_texte"] + " " + stats["annee"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.markdown("### 📈 Revenus bruts par plateforme")
    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### 🛌 Nuitées par plateforme")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))

    st.markdown("### 💸 Charges mensuelles")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

def liste_clients(df):
    st.subheader("👥 Liste des clients")
    st.dataframe(df[["nom_client", "plateforme", "date_arrivee", "date_depart", "telephone"]])

# ▶️ Point d'entrée principal
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    df = importer_fichier()
    if df.empty:
        return

    df = ajouter_colonnes_automatiques(df)

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "📅 Calendrier",
        "📊 Rapport",
        "👥 Liste clients",
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)
    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)
    elif onglet == "📊 Rapport":
        afficher_rapport(df)
    elif onglet == "👥 Liste clients":
        liste_clients(df)

if __name__ == "__main__":
    main()
