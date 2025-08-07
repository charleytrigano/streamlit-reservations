from pathlib import Path

# Génération du code de `app.py` mis à jour
code_app_py = """
import streamlit as st
import pandas as pd
import calendar
from datetime import date
from pathlib import Path

FICHIER = "reservations.xlsx"

def telecharger_fichier_excel(df):
    st.download_button(
        "📥 Télécharger le fichier Excel",
        data=df.to_excel(index=False),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")

    if "aaaa" not in df.columns or "mm" not in df.columns:
        st.warning("Les colonnes 'aaaa' et 'mm' sont requises.")
        return

    col1, col2 = st.columns(2)
    with col1:
        mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
        mois_index = list(calendar.month_name).index(mois_nom)
    with col2:
        annees = sorted(df["aaaa"].dropna().unique())
        annee = st.selectbox("Année", annees)

    jours_du_mois = [
        date(int(annee), mois_index, j + 1)
        for j in range(calendar.monthrange(int(annee), mois_index)[1])
    ]
    planning = {jour: [] for jour in jours_du_mois}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        debut = pd.to_datetime(row["date_arrivee"]).date()
        fin = pd.to_datetime(row["date_depart"]).date()
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
                contenu = f"{jour}\\n" + "\\n".join(planning[jour_date])
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

    stats = df.groupby(["aaaa", "mm", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois_texte"] = stats["mm"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["aaaa"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.markdown("### 📈 Revenus bruts par plateforme")
    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### 🛌 Nuitées par mois")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))

    st.markdown("### 📊 Charges mensuelles")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

def main():
    st.set_page_config("📖 Réservations Villa Tobias", layout="wide")

    if not Path(FICHIER).exists():
        st.warning("Le fichier reservations.xlsx est introuvable.")
        return

    df = pd.read_excel(FICHIER)

    onglet = st.sidebar.radio("Menu", [
        "📋 Réservations",
        "📅 Calendrier",
        "📊 Rapport",
        "📥 Télécharger"
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)
    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)
    elif onglet == "📊 Rapport":
        afficher_rapport(df)
    elif onglet == "📥 Télécharger":
        telecharger_fichier_excel(df)

if __name__ == "__main__":
    main()
"""

# Écriture dans le fichier
Path("/mnt/data/app.py").write_text(code_app_py.strip(), encoding="utf-8")
