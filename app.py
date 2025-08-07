from pathlib import Path
import zipfile

# Contenu nettoyé et corrigé du fichier app.py (version stable, toutes les fonctionnalités réintégrées)
app_py_content = """
import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, date, timedelta
from io import BytesIO

FICHIER = "reservations.xlsx"

def charger_donnees():
    try:
        df = pd.read_excel(FICHIER)
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
        df["AAAA"] = pd.to_datetime(df["date_arrivee"]).dt.year
        df["MM"] = pd.to_datetime(df["date_arrivee"]).dt.month
        colonnes_float = ["prix_brut", "prix_net", "charges", "%"]
        for col in colonnes_float:
            if col in df.columns:
                df[col] = df[col].round(2)
        return df
    except Exception:
        return pd.DataFrame()

def telecharger_fichier_excel(df):
    with BytesIO() as buffer:
        df.to_excel(buffer, index=False)
        st.download_button(
            label="📥 Télécharger le fichier Excel",
            data=buffer.getvalue(),
            file_name="reservations.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

def uploader_excel():
    fichier = st.sidebar.file_uploader("📤 Importer un fichier Excel", type=["xlsx"])
    if fichier:
        df = pd.read_excel(fichier)
        df.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier importé avec succès.")

def afficher_reservations(df):
    st.subheader("📋 Réservations")
    st.dataframe(df)
    telecharger_fichier_excel(df)

def ajouter_reservation(df):
    st.subheader("➕ Ajouter une réservation")
    with st.form("form_ajout"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        telephone = st.text_input("Téléphone")
        date_arrivee = st.date_input("Date d’arrivée")
        date_depart = st.date_input("Date de départ", min_value=date_arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut (€)", min_value=0.0, step=1.0)
        prix_net = st.number_input("Prix net (€)", min_value=0.0, step=1.0)
        submit = st.form_submit_button("Enregistrer")
        if submit:
            nuitees = (date_depart - date_arrivee).days
            ligne = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": telephone,
                "date_arrivee": date_arrivee,
                "date_depart": date_depart,
                "prix_brut": round(prix_brut, 2),
                "prix_net": round(prix_net, 2),
                "charges": round(prix_brut - prix_net, 2),
                "%": round(((prix_brut - prix_net) / prix_brut * 100) if prix_brut else 0, 2),
                "nuitees": nuitees,
                "AAAA": date_arrivee.year,
                "MM": date_arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation ajoutée.")
            st.experimental_rerun()

def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")
    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:], key="mois_cal")
    annees_dispo = sorted(df["AAAA"].dropna().unique())
    annee = st.selectbox("Année", annees_dispo, key="annee_cal")
    mois_index = list(calendar.month_name).index(mois_nom)
    jours = [date(int(annee), mois_index, j+1) for j in range(calendar.monthrange(int(annee), mois_index)[1])]
    planning = {j: [] for j in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}
    for _, row in df.iterrows():
        debut = row["date_arrivee"]
        fin = row["date_depart"]
        for jour in jours:
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
    st.subheader("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée.")
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

def liste_clients(df):
    st.subheader("👥 Liste clients")
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()), key="annee_clients")
    mois = st.selectbox("Mois", ["Tous"] + list(range(1, 13)), key="mois_clients")
    data = df[df["AAAA"] == annee]
    if mois != "Tous":
        data = data[data["MM"] == mois]
    if not data.empty:
        data["prix_brut/nuit"] = (data["prix_brut"] / data["nuitees"]).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
        data["prix_net/nuit"] = (data["prix_net"] / data["nuitees"]).replace([float("inf"), float("-inf")], 0).fillna(0).round(2)
        colonnes = ["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "prix_brut", "prix_net", "charges", "%", "prix_brut/nuit", "prix_net/nuit"]
        st.dataframe(data[colonnes])
    else:
        st.info("Aucune donnée pour cette période.")

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
        "➕ Ajouter",
        "📅 Calendrier",
        "📊 Rapport",
        "👥 Liste clients"
    ])
    if onglet == "📋 Réservations":
        afficher_reservations(df)
    elif onglet == "➕ Ajouter":
        ajouter_reservation(df)
    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)
    elif onglet == "📊 Rapport":
        afficher_rapport(df)
    elif onglet == "👥 Liste clients":
        liste_clients(df)

if __name__ == "__main__":
    main()
"""

# Sauvegarde dans un fichier temporaire
app_file_path = Path("/mnt/data/app.py")
app_file_path.write_text(app_py_content.strip(), encoding="utf-8")

# Création du zip contenant uniquement app.py
zip_path = "/mnt/data/streamlit_app.zip"
with zipfile.ZipFile(zip_path, "w") as zipf:
    zipf.write(app_file_path, arcname="app.py")

zip_path
