from pathlib import Path
from zipfile import ZipFile

# Contenu du fichier app.py corrigé sans write_text
app_py_content = """
import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
from io import BytesIO

FICHIER = "reservations.xlsx"

# Fonction de chargement des données
def charger_donnees():
    try:
        df = pd.read_excel(FICHIER)
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
        df["annee"] = pd.to_datetime(df["date_arrivee"]).dt.year
        df["mois"] = pd.to_datetime(df["date_arrivee"]).dt.month
        return df
    except:
        return pd.DataFrame()

# Fonction de téléchargement
def telecharger_fichier_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    st.download_button(
        label="📥 Télécharger le fichier Excel",
        data=buffer.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Fonction de restauration (upload d'un fichier)
def uploader_excel():
    uploaded_file = st.sidebar.file_uploader("📤 Restaurer depuis un fichier Excel", type=["xlsx"])
    if uploaded_file:
        df_uploaded = pd.read_excel(uploaded_file)
        df_uploaded.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier restauré avec succès.")

# Onglet Réservations
def afficher_reservations(df):
    st.subheader("📋 Réservations")
    df_display = df.copy()
    df_display["date_arrivee"] = pd.to_datetime(df_display["date_arrivee"]).dt.strftime("%Y/%m/%d")
    df_display["date_depart"] = pd.to_datetime(df_display["date_depart"]).dt.strftime("%Y/%m/%d")
    df_display["charges"] = df_display["charges"].round(2)
    df_display["%"] = df_display["%"].round(2)
    st.dataframe(df_display)

# Onglet Calendrier
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")
    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    mois_index = list(calendar.month_name).index(mois_nom)
    annees_disponibles = sorted(df["annee"].dropna().astype(int).unique())
    annee = st.selectbox("Année", annees_disponibles)
    jours_du_mois = [date(int(annee), mois_index, j + 1) for j in range(calendar.monthrange(int(annee), mois_index)[1])]
    calendrier = {jour: [] for jour in jours_du_mois}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}
    for _, row in df.iterrows():
        debut = row["date_arrivee"]
        fin = row["date_depart"]
        for jour in jours_du_mois:
            if debut <= jour < fin:
                icone = couleurs.get(row["plateforme"], "⬜")
                calendrier[jour].append(f"{icone} {row['nom_client']}")
    table = []
    for semaine in calendar.monthcalendar(int(annee), mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                jour_date = date(int(annee), mois_index, jour)
                contenu = f"{jour}\\n" + "\\n".join(calendrier[jour_date])
                ligne.append(contenu)
        table.append(ligne)
    st.table(pd.DataFrame(table, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

# Onglet Rapport
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")
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
    stats["mois_texte"] = stats["mois"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["annee"].astype(str)
    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])
    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

# App principale
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")
    uploader_excel()
    df = charger_donnees()
    if df.empty:
        st.warning("Aucune donnée disponible. Veuillez importer un fichier Excel.")
        return
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
"""

# Sauvegarder dans un fichier .py
app_file_path = Path("/mnt/data/app.py")
app_file_path.write_text(app_py_content.strip(), encoding="utf-8")

# Créer un fichier .zip contenant app.py
zip_path = "/mnt/data/app_complet.zip"
with ZipFile(zip_path, "w") as zipf:
    zipf.write(app_file_path, arcname="app.py")

zip_path
