from pathlib import Path

# Recréation du fichier app.py après le reset de l'environnement
app_py_content = """
import streamlit as st
import pandas as pd
import calendar
from datetime import date
from io import BytesIO

FICHIER = "reservations.xlsx"

def charger_donnees():
    try:
        df = pd.read_excel(FICHIER)
        if "AAAA" in df.columns and "MM" in df.columns:
            df["AAAA"] = pd.to_numeric(df["AAAA"], errors='coerce').fillna(0).astype(int)
            df["MM"] = pd.to_numeric(df["MM"], errors='coerce').fillna(0).astype(int)
        return df
    except:
        return pd.DataFrame()

def telecharger_fichier_excel(df):
    output = BytesIO()
    df.to_excel(output, index=False, engine='openpyxl')
    st.sidebar.download_button(
        label="📥 Télécharger le fichier Excel",
        data=output.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

def afficher_calendrier(df):
    st.title("📅 Calendrier mensuel")
    
    if df.empty or "AAAA" not in df.columns or "MM" not in df.columns:
        st.warning("Colonnes AAAA et MM manquantes dans les données.")
        return

    col1, col2 = st.columns(2)
    with col1:
        mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    with col2:
        annees = sorted(df["AAAA"].dropna().unique())
        annee = st.selectbox("Année", annees)

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
    st.title("📊 Rapport mensuel")
    if df.empty or "AAAA" not in df.columns or "MM" not in df.columns:
        st.warning("Colonnes AAAA et MM manquantes.")
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

    stats["mois_texte"] = stats["MM"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["AAAA"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])
    st.markdown("### Revenus bruts vs nets")
    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))
    st.markdown("### Nuitées")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))
    st.markdown("### Charges")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

def main():
    st.set_page_config(page_title="📖 Réservations", layout="wide")
    st.sidebar.title("📁 Menu")

    df = charger_donnees()

    if df.empty:
        st.warning("Aucune donnée disponible. Veuillez importer un fichier Excel.")
        return

    telecharger_fichier_excel(df)

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "📅 Calendrier",
        "📊 Rapport"
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)
    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)
    elif onglet == "📊 Rapport":
        afficher_rapport(df)

if __name__ == "__main__":
    main()
"""

# Enregistrement dans un fichier
app_path = Path("/mnt/data/app.py")
app_path.write_text(app_py_content.strip(), encoding="utf-8")

app_path
