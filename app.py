import streamlit as st
import pandas as pd
import calendar
from datetime import date
from io import BytesIO

FICHIER = "reservations.xlsx"

# 📤 Télécharger le fichier Excel
def telecharger_fichier_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    st.sidebar.download_button(
        label="📥 Télécharger le fichier Excel",
        data=buffer.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 📅 Affichage du calendrier
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")

    if df.empty:
        st.warning("Aucune donnée à afficher.")
        return

    # Vérification colonnes nécessaires
    if "AAAA" not in df.columns or "MM" not in df.columns:
        st.error("Les colonnes 'AAAA' et 'MM' sont requises dans le fichier.")
        return

    # Conversion vers int (parfois float ou str)
    df["AAAA"] = df["AAAA"].astype(int)
    df["MM"] = df["MM"].astype(int)

    annees = sorted(df["AAAA"].dropna().unique())
    mois_noms = list(calendar.month_name)[1:]

    col1, col2 = st.columns(2)
    with col1:
        mois_nom = st.selectbox("Mois", mois_noms)
    with col2:
        annee = st.selectbox("Année", annees)

    mois_index = mois_noms.index(mois_nom) + 1
    jours = [date(annee, mois_index, j + 1) for j in range(calendar.monthrange(annee, mois_index)[1])]

    # Préparer le planning
    planning = {jour: [] for jour in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        try:
            debut = pd.to_datetime(row["date_arrivee"]).date()
            fin = pd.to_datetime(row["date_depart"]).date()
            for jour in jours:
                if debut <= jour < fin:
                    icone = couleurs.get(row.get("plateforme", "Autre"), "⬜")
                    nom = row.get("nom_client", "")
                    planning[jour].append(f"{icone} {nom}")
        except Exception as e:
            st.warning(f"Erreur sur une ligne : {e}")

    # Construire la table
    tableau = []
    for semaine in calendar.monthcalendar(annee, mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                d = date(annee, mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning[d])
                ligne.append(contenu)
        tableau.append(ligne)

    st.table(pd.DataFrame(tableau, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))


# 📊 Rapport mensuel
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")

    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    if "AAAA" not in df.columns or "MM" not in df.columns:
        st.error("Colonnes 'AAAA' et 'MM' manquantes.")
        return

    df["AAAA"] = df["AAAA"].astype(int)
    df["MM"] = df["MM"].astype(int)

    stats = df.groupby(["AAAA", "MM", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois_texte"] = stats["MM"].apply(lambda x: calendar.month_abbr[x])
    stats["période"] = stats["mois_texte"] + " " + stats["AAAA"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.markdown("### Revenus bruts")
    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### Charges")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

    st.markdown("### Nuitées")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))


# 📦 Chargement des données
def charger_donnees():
    try:
        return pd.read_excel(FICHIER)
    except FileNotFoundError:
        st.warning("Fichier non trouvé.")
        return pd.DataFrame()


# ▶️ Application principale
def main():
    st.set_page_config(page_title="Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    df = charger_donnees()
    if df.empty:
        return

    onglet = st.sidebar.radio("Navigation", ["📋 Réservations", "📅 Calendrier", "📊 Rapport"])

    if onglet == "📋 Réservations":
        st.title("📋 Toutes les réservations")
        st.dataframe(df)
        telecharger_fichier_excel(df)

    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)

    elif onglet == "📊 Rapport":
        afficher_rapport(df)

if __name__ == "__main__":
    main()
