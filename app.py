from pathlib import Path

# Contenu complet du fichier app.py corrigé
app_py_content = """
import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
from io import BytesIO

FICHIER = "reservations.xlsx"

def charger_donnees():
    try:
        df = pd.read_excel(FICHIER)
        return df
    except:
        return pd.DataFrame()

def uploader_excel():
    uploaded = st.sidebar.file_uploader("📤 Importer un fichier Excel", type="xlsx")
    if uploaded:
        df = pd.read_excel(uploaded)
        df.to_excel(FICHIER, index=False)
        st.success("✅ Fichier importé avec succès")

def telecharger_fichier_excel(df):
    buffer = BytesIO()
    df.to_excel(buffer, index=False)
    st.sidebar.download_button(
        label="📥 Télécharger le fichier Excel",
        data=buffer.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

def afficher_reservations(df):
    st.header("📋 Réservations")
    st.dataframe(df)

def ajouter_reservation(df):
    st.header("➕ Ajouter une réservation")
    with st.form("form_resa"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        telephone = st.text_input("Téléphone")
        date_arrivee = st.date_input("Date d'arrivée")
        date_depart = st.date_input("Date de départ", min_value=date_arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut", min_value=0.0)
        prix_net = st.number_input("Prix net", min_value=0.0, max_value=prix_brut)

        submit = st.form_submit_button("Enregistrer")

        if submit:
            new_data = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": telephone,
                "date_arrivee": pd.to_datetime(date_arrivee),
                "date_depart": pd.to_datetime(date_depart),
                "prix_brut": round(prix_brut, 2),
                "prix_net": round(prix_net, 2),
                "charges": round(prix_brut - prix_net, 2),
                "%": round(((prix_brut - prix_net) / prix_brut) * 100, 2) if prix_brut else 0,
                "nuitees": (date_depart - date_arrivee).days,
                "AAAA": date_arrivee.year,
                "MM": date_arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([new_data])], ignore_index=True)
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation ajoutée avec succès")

def afficher_calendrier(df):
    st.header("📅 Calendrier mensuel")
    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    # Assurer que les colonnes AAAA et MM sont bien présentes
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce")
        df["AAAA"] = df["date_arrivee"].dt.year
        df["MM"] = df["date_arrivee"].dt.month

    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    annees_dispo = df["AAAA"].dropna().unique()
    annees_dispo = sorted([int(a) for a in annees_dispo if not pd.isna(a)])
    if not annees_dispo:
        st.warning("Aucune année disponible.")
        return
    annee = st.selectbox("Année", annees_dispo)

    mois_index = list(calendar.month_name).index(mois_nom)
    jours = [date(annee, mois_index, i + 1) for i in range(calendar.monthrange(annee, mois_index)[1])]
    planning = {jour: [] for jour in jours}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        debut = pd.to_datetime(row["date_arrivee"], errors="coerce")
        fin = pd.to_datetime(row["date_depart"], errors="coerce")
        if pd.isna(debut) or pd.isna(fin):
            continue
        for jour in jours:
            if debut <= jour < fin:
                icone = couleurs.get(row["plateforme"], "⬜")
                planning[jour].append(f"{icone} {row['nom_client']}")

    table = []
    for semaine in calendar.monthcalendar(annee, mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                jour_date = date(annee, mois_index, jour)
                contenu = f"{jour}\\n" + "\\n".join(planning[jour_date])
                ligne.append(contenu)
        table.append(ligne)

    st.table(pd.DataFrame(table, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

def afficher_rapport(df):
    st.header("📊 Rapport mensuel")
    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    plateformes = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    filtre = st.selectbox("Filtrer par plateforme", plateformes)
    if filtre != "Toutes":
        df = df[df["plateforme"] == filtre]

    # Vérification et création des colonnes nécessaires
    df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = df["date_arrivee"].dt.year
    df["MM"] = df["date_arrivee"].dt.month

    stats = df.groupby(["AAAA", "MM", "plateforme"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois_texte"] = stats["MM"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["AAAA"].astype(str)

    st.dataframe(stats[["période", "plateforme", "prix_brut", "prix_net", "charges", "nuitees"]])

    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))

def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")
    uploader_excel()
    df = charger_donnees()

    # Recalcul des colonnes année/mois si nécessaires
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce")
        df["AAAA"] = df["date_arrivee"].dt.year
        df["MM"] = df["date_arrivee"].dt.month

    telecharger_fichier_excel(df)

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "➕ Ajouter",
        "📅 Calendrier",
        "📊 Rapport"
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)
    elif onglet == "➕ Ajouter":
        ajouter_reservation(df)
    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)
    elif onglet == "📊 Rapport":
        afficher_rapport(df)

if __name__ == "__main__":
    main()
"""

# Sauvegarde du fichier app.py corrigé
app_py_path = Path("/mnt/data/app.py")
app_py_path.write_text(app_py_content.strip(), encoding="utf-8")
app_py_path
