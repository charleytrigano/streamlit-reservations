from pathlib import Path
from zipfile import ZipFile

# Créer les fichiers nécessaires
app_code = """import streamlit as st
import pandas as pd
import calendar
from datetime import datetime, timedelta, date
import os

FICHIER = "reservations.xlsx"
COULEURS = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
        df["annee"] = pd.to_datetime(df["date_arrivee"]).dt.year
        df["mois"] = pd.to_datetime(df["date_arrivee"]).dt.month
        return df
    else:
        return pd.DataFrame()

def enregistrer_donnees(df):
    df.to_excel(FICHIER, index=False)

def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")

    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    annees = sorted(df["annee"].dropna().unique())
    mois_noms = list(calendar.month_name)[1:]

    col1, col2 = st.columns(2)
    with col1:
        annee = st.selectbox("Année", annees, index=len(annees) - 1)
    with col2:
        mois_nom = st.selectbox("Mois", mois_noms, index=date.today().month - 1)

    mois = mois_noms.index(mois_nom) + 1
    nb_jours = calendar.monthrange(int(annee), mois)[1]
    jours = [date(int(annee), mois, j+1) for j in range(nb_jours)]

    planning = {j: [] for j in jours}

    for _, row in df.iterrows():
        d1, d2 = row["date_arrivee"], row["date_depart"]
        for jour in jours:
            if d1 <= jour < d2:
                icone = COULEURS.get(row["plateforme"], "⬜")
                planning[jour].append(f"{icone} {row['nom_client']}")

    # Générer le tableau
    tableau = []
    for semaine in calendar.monthcalendar(int(annee), mois):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                jour_date = date(int(annee), mois, jour)
                contenu = f"{jour}\\n" + "\\n".join(planning[jour_date])
                ligne.append(contenu)
        tableau.append(ligne)

    st.table(pd.DataFrame(tableau, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

def afficher_reservations(df):
    st.subheader("📋 Réservations")
    st.dataframe(df)

def ajouter_reservation(df):
    st.subheader("➕ Nouvelle Réservation")
    with st.form("form_ajout"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d'arrivée", value=date.today())
        depart = st.date_input("Date de départ", value=arrivee + timedelta(days=1))
        brut = st.number_input("Prix brut", min_value=0.0)
        net = st.number_input("Prix net", min_value=0.0, max_value=brut)
        submit = st.form_submit_button("Enregistrer")

        if submit:
            ligne = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": tel,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "prix_brut": round(brut, 2),
                "prix_net": round(net, 2),
                "charges": round(brut - net, 2),
                "%": round((brut - net) / brut * 100, 2) if brut else 0,
                "nuitees": (depart - arrivee).days,
                "annee": arrivee.year,
                "mois": arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            enregistrer_donnees(df)
            st.success("✅ Réservation ajoutée.")

def main():
    st.set_page_config("📖 Réservations Villa Tobias")
    st.sidebar.title("Menu")
    df = charger_donnees()

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "➕ Ajouter",
        "📅 Calendrier"
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)

    elif onglet == "➕ Ajouter":
        ajouter_reservation(df)

    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)

if __name__ == "__main__":
    main()
"""

# Écriture du fichier
output_path = Path("/mnt/data/app.py")
output_path.write_text(app_code)

# Préparer un fichier ZIP à partir du script unique
zip_path = "/mnt/data/app_streamlit_villa.zip"
with ZipFile(zip_path, "w") as zipf:
    zipf.write(output_path, arcname="app.py")

zip_path
