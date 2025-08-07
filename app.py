import streamlit as st
import pandas as pd
import os
import calendar
from datetime import date, timedelta, datetime

# 📂 Nom du fichier
FICHIER = "reservations.xlsx"

# 📦 Charger les données
def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)
        return df
    else:
        return pd.DataFrame()

# 📥 Import manuel d’un fichier Excel
def uploader_excel():
    uploaded_file = st.sidebar.file_uploader("📤 Importer un fichier .xlsx", type="xlsx")
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier importé avec succès")

# 💾 Télécharger les données modifiées
def telecharger_fichier_excel(df):
    df.to_excel(FICHIER, index=False)

# 🔔 Notification arrivée le lendemain (mock simplifié)
def notifier_arrivees_prochaines(df):
    if df.empty:
        return
    if "date_arrivee" in df.columns:
        df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.date
        demain = date.today() + timedelta(days=1)
        alertes = df[df["date_arrivee"] == demain]
        if not alertes.empty:
            st.sidebar.info(f"🔔 {len(alertes)} arrivée(s) prévue(s) demain")

# 📋 Afficher réservations
def afficher_reservations(df):
    st.subheader("📋 Réservations")
    st.dataframe(df)

# ➕ Ajouter une réservation
def ajouter_reservation(df):
    st.subheader("➕ Nouvelle Réservation")
    with st.form("ajout"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d’arrivée")
        depart = st.date_input("Date de départ", min_value=arrivee + timedelta(days=1))
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
            telecharger_fichier_excel(df)
            st.success("✅ Réservation ajoutée.")

# ✏️ Modifier/Supprimer une réservation
def modifier_reservation(df):
    st.subheader("✏️ Modifier / Supprimer")
    if df.empty:
        st.info("Aucune réservation.")
        return
    df["identifiant"] = df["nom_client"] + " | " + pd.to_datetime(df["date_arrivee"]).astype(str)
    selection = st.selectbox("Choisir une réservation", df["identifiant"])
    i = df[df["identifiant"] == selection].index[0]
    with st.form("modif"):
        nom = st.text_input("Nom", df.at[i, "nom_client"])
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"], index=["Booking", "Airbnb", "Autre"].index(df.at[i, "plateforme"]))
        tel = st.text_input("Téléphone", df.at[i, "telephone"])
        arrivee = st.date_input("Arrivée", df.at[i, "date_arrivee"])
        depart = st.date_input("Départ", df.at[i, "date_depart"])
        brut = st.number_input("Prix brut", value=float(df.at[i, "prix_brut"]))
        net = st.number_input("Prix net", value=float(df.at[i, "prix_net"]))
        submit = st.form_submit_button("Modifier")
        delete = st.form_submit_button("Supprimer")
        if submit:
            df.at[i, "nom_client"] = nom
            df.at[i, "plateforme"] = plateforme
            df.at[i, "telephone"] = tel
            df.at[i, "date_arrivee"] = arrivee
            df.at[i, "date_depart"] = depart
            df.at[i, "prix_brut"] = round(brut, 2)
            df.at[i, "prix_net"] = round(net, 2)
            df.at[i, "charges"] = round(brut - net, 2)
            df.at[i, "%"] = round((brut - net) / brut * 100, 2) if brut else 0
            df.at[i, "nuitees"] = (depart - arrivee).days
            df.at[i, "annee"] = arrivee.year
            df.at[i, "mois"] = arrivee.month
            telecharger_fichier_excel(df)
            st.success("✅ Réservation modifiée.")
        if delete:
            df.drop(index=i, inplace=True)
            telecharger_fichier_excel(df)
            st.warning("🗑 Réservation supprimée.")

# 📅 Calendrier mensuel simple
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")

    df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.date
    df["date_depart"] = pd.to_datetime(df["date_depart"], errors="coerce").dt.date

    if df.empty or df["date_arrivee"].isna().all():
        st.warning("Aucune donnée de réservation valide.")
        return

    annee = st.sidebar.selectbox("Année", sorted(df["date_arrivee"].dropna().map(lambda d: d.year).unique()))
    mois = st.sidebar.selectbox("Mois", list(calendar.month_name)[1:])
    mois_index = list(calendar.month_name).index(mois)

    nb_jours = calendar.monthrange(annee, mois_index)[1]
    jours_du_mois = [date(annee, mois_index, j + 1) for j in range(nb_jours)]
    planning = {jour: [] for jour in jours_du_mois}

    for _, row in df.iterrows():
        debut = row["date_arrivee"]
        fin = row["date_depart"]
        if pd.isna(debut) or pd.isna(fin):
            continue
        for jour in jours_du_mois:
            if debut <= jour < fin:
                texte = f"{row['nom_client']} ({row['plateforme']})"
                planning[jour].append(texte)

    table = []
    for semaine in calendar.Calendar().monthdatescalendar(annee, mois_index):
        ligne = []
        for jour in semaine:
            if jour.month != mois_index:
                ligne.append("")
            else:
                contenu = f"{jour.day}\n" + "\n".join(planning.get(jour, []))
                ligne.append(contenu)
        table.append(ligne)

    jours_labels = ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]
    df_calendrier = pd.DataFrame(table, columns=jours_labels)
    st.table(df_calendrier)

# 📊 Rapport simple
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")
    if df.empty:
        st.info("Aucune donnée.")
        return

    df["annee"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year
    df["mois"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.month
    stats = df.groupby(["annee", "mois"]).agg({
        "prix_brut": "sum",
        "prix_net": "sum",
        "charges": "sum",
        "nuitees": "sum"
    }).reset_index()

    stats["mois_texte"] = stats["mois"].apply(lambda x: calendar.month_abbr[int(x)])
    stats["période"] = stats["mois_texte"] + " " + stats["annee"].astype(str)

    st.dataframe(stats[["période", "prix_brut", "prix_net", "charges", "nuitees"]])
    st.line_chart(stats.set_index("période")[["prix_brut", "prix_net"]])
    st.bar_chart(stats.set_index("période")["charges"])

# 👥 Liste clients
def liste_clients(df):
    st.subheader("👥 Liste des clients")
    st.dataframe(df[["nom_client", "plateforme", "date_arrivee", "date_depart", "telephone"]])

# ▶️ Point d’entrée principal
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")
    uploader_excel()
    df = charger_donnees()

    if df.empty:
        st.warning("Aucune donnée disponible. Veuillez importer un fichier Excel.")
        return

    notifier_arrivees_prochaines(df)

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "➕ Ajouter",
        "✏️ Modifier / Supprimer",
        "📅 Calendrier",
        "📊 Rapport",
        "👥 Liste clients"
    ])

    if onglet == "📋 Réservations":
        afficher_reservations(df)
        telecharger_fichier_excel(df)
    elif onglet == "➕ Ajouter":
        ajouter_reservation(df)
    elif onglet == "✏️ Modifier / Supprimer":
        modifier_reservation(df)
    elif onglet == "📅 Calendrier":
        afficher_calendrier(df)
    elif onglet == "📊 Rapport":
        afficher_rapport(df)
    elif onglet == "👥 Liste clients":
        liste_clients(df)

if __name__ == "__main__":
    main()
