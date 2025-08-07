from zipfile import ZipFile
from pathlib import Path

# Création du fichier app.py complet
app_py_content = '''
import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, date, timedelta
from io import BytesIO

FICHIER = "reservations.xlsx"

def charger_donnees():
    try:
        df = pd.read_excel(FICHIER)
        if "date_arrivee" in df.columns:
            df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        if "date_depart" in df.columns:
            df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
        if "aaaa" not in df.columns:
            df["aaaa"] = pd.to_datetime(df["date_arrivee"]).dt.year
        if "mm" not in df.columns:
            df["mm"] = pd.to_datetime(df["date_arrivee"]).dt.month
        return df
    except Exception:
        return pd.DataFrame()

def telecharger_fichier_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    st.download_button(
        label="📥 Télécharger le fichier Excel",
        data=buffer.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def uploader_fichier_excel():
    fichier = st.sidebar.file_uploader("📤 Importer un fichier Excel", type=["xlsx"])
    if fichier:
        with open(FICHIER, "wb") as f:
            f.write(fichier.read())
        st.sidebar.success("Fichier importé avec succès")

def afficher_reservations(df):
    st.header("📋 Réservations")
    if df.empty:
        st.info("Aucune réservation à afficher.")
        return
    afficher = df.copy()
    afficher["date_arrivee"] = pd.to_datetime(afficher["date_arrivee"]).dt.strftime("%Y/%m/%d")
    afficher["date_depart"] = pd.to_datetime(afficher["date_depart"]).dt.strftime("%Y/%m/%d")
    for col in ["prix_brut", "prix_net", "charges", "%"]:
        if col in afficher.columns:
            afficher[col] = afficher[col].apply(lambda x: f"{x:.2f}")
    st.dataframe(afficher)

def afficher_calendrier(df):
    st.header("📅 Calendrier mensuel")
    if "aaaa" not in df.columns or "mm" not in df.columns:
        st.warning("Les colonnes 'aaaa' et 'mm' sont manquantes.")
        return
    annee = st.selectbox("Année", sorted(df["aaaa"].dropna().unique()))
    mois = st.selectbox("Mois", list(calendar.month_name)[1:], index=datetime.now().month - 1)
    mois_index = list(calendar.month_name).index(mois)

    jours_du_mois = [date(int(annee), mois_index, j + 1) for j in range(calendar.monthrange(int(annee), mois_index)[1])]
    planning = {jour: [] for jour in jours_du_mois}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        debut = row["date_arrivee"]
        fin = row["date_depart"]
        for jour in jours_du_mois:
            if debut <= jour < fin:
                couleur = couleurs.get(row["plateforme"], "⬜")
                planning[jour].append(f"{couleur} {row['nom_client']}")

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
    st.header("📊 Rapport mensuel")
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    stats = df.groupby(["aaaa", "mm", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois_texte"] = stats["mm"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["aaaa"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.markdown("### 📈 Revenus bruts vs nets")
    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))

    st.markdown("### 🛌 Nuitées par mois")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))

    st.markdown("### 📊 Charges mensuelles")
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

def main():
    st.set_page_config(page_title="Réservations", layout="wide")
    st.sidebar.title("📁 Menu")
    uploader_fichier_excel()
    df = charger_donnees()

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
'''

# Sauvegarde du fichier app.py
app_file_path = Path("/mnt/data/app.py")
app_file_path.write_text(app_py_content.strip(), encoding="utf-8")

# Création de l'archive ZIP avec app.py
zip_path = "/mnt/data/app_complet_final.zip"
with ZipFile(zip_path, "w") as archive:
    archive.write(app_file_path, arcname="app.py")

zip_path
