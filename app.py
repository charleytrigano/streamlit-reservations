import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
import os

FICHIER = "reservations.xlsx"

# 🔽 Import manuel depuis un fichier Excel
def uploader_excel():
    fichier = st.sidebar.file_uploader("📤 Importer un fichier .xlsx", type="xlsx")
    if fichier:
        df = pd.read_excel(fichier)
        df.to_excel(FICHIER, index=False)
        st.sidebar.success("✅ Fichier importé avec succès")

# 🔄 Charger les données existantes
def charger_donnees():
    if os.path.exists(FICHIER):
        df = pd.read_excel(FICHIER)
        if "date_arrivee" in df.columns:
            df["date_arrivee"] = pd.to_datetime(df["date_arrivee"]).dt.date
        if "date_depart" in df.columns:
            df["date_depart"] = pd.to_datetime(df["date_depart"]).dt.date
        if "AAAA" not in df.columns:
            df["AAAA"] = pd.to_datetime(df["date_arrivee"]).dt.year
        if "MM" not in df.columns:
            df["MM"] = pd.to_datetime(df["date_arrivee"]).dt.month
        return df
    return pd.DataFrame()

# 💾 Exporter le fichier
def telecharger_fichier_excel(df):
    st.sidebar.download_button(
        label="📥 Télécharger le fichier Excel",
        data=df.to_excel(index=False),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 🔔 SMS fictif (à personnaliser)
def notifier_arrivees_prochaines(df):
    demain = date.today() + timedelta(days=1)
    arrivées = df[df["date_arrivee"] == demain]
    if not arrivées.empty:
        st.sidebar.info(f"🔔 {len(arrivées)} arrivée(s) demain")

def historique_sms():
    st.subheader("✉️ Historique des SMS")
    st.info("Historique fictif")

# 📋 Onglet Réservations
def afficher_reservations(df):
    st.subheader("📋 Réservations")
    st.dataframe(df)

# ➕ Ajouter une réservation
def ajouter_reservation(df):
    st.subheader("➕ Ajouter une réservation")
    with st.form("ajout"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d'arrivée")
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
                "prix_brut": brut,
                "prix_net": net,
                "charges": brut - net,
                "%": round((brut - net) / brut * 100, 2) if brut else 0,
                "nuitees": (depart - arrivee).days,
                "AAAA": arrivee.year,
                "MM": arrivee.month,
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation ajoutée")

# ✏️ Modifier une réservation
def modifier_reservation(df):
    st.subheader("✏️ Modifier / Supprimer")
    df["identifiant"] = df["nom_client"] + " | " + df["date_arrivee"].astype(str)
    selection = st.selectbox("Sélectionner une réservation", df["identifiant"])
    i = df[df["identifiant"] == selection].index[0]

    with st.form("modif"):
        nom = st.text_input("Nom", df.at[i, "nom_client"])
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"], index=["Booking", "Airbnb", "Autre"].index(df.at[i, "plateforme"]))
        tel = st.text_input("Téléphone", df.at[i, "telephone"])
        arrivee = st.date_input("Arrivée", df.at[i, "date_arrivee"])
        depart = st.date_input("Départ", df.at[i, "date_depart"])
        brut = st.number_input("Prix brut", value=float(df.at[i, "prix_brut"]))
        net = st.number_input("Prix net", value=float(df.at[i, "prix_net"]))
        modifier = st.form_submit_button("Modifier")
        supprimer = st.form_submit_button("Supprimer")

        if modifier:
            df.at[i, "nom_client"] = nom
            df.at[i, "plateforme"] = plateforme
            df.at[i, "telephone"] = tel
            df.at[i, "date_arrivee"] = arrivee
            df.at[i, "date_depart"] = depart
            df.at[i, "prix_brut"] = brut
            df.at[i, "prix_net"] = net
            df.at[i, "charges"] = brut - net
            df.at[i, "%"] = round((brut - net) / brut * 100, 2) if brut else 0
            df.at[i, "nuitees"] = (depart - arrivee).days
            df.at[i, "AAAA"] = arrivee.year
            df.at[i, "MM"] = arrivee.month
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation modifiée")

        if supprimer:
            df.drop(index=i, inplace=True)
            df.to_excel(FICHIER, index=False)
            st.warning("❌ Réservation supprimée")

# 📅 Calendrier mensuel
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")

    if df.empty or "AAAA" not in df.columns or "MM" not in df.columns:
        st.warning("Les colonnes AAAA et MM sont manquantes.")
        return

    mois_nom = st.selectbox("Mois", list(calendar.month_name)[1:])
    mois_index = list(calendar.month_name).index(mois_nom)
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()))

    jours_du_mois = [date(int(annee), mois_index, j + 1) for j in range(calendar.monthrange(int(annee), mois_index)[1])]
    planning = {jour: [] for jour in jours_du_mois}
    couleurs = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

    for _, row in df.iterrows():
        debut = row["date_arrivee"]
        fin = row["date_depart"]
        for jour in jours_du_mois:
            if debut <= jour < fin:
                icone = couleurs.get(row["plateforme"], "⬜")
                planning[jour].append(f"{icone} {row['nom_client']}")

    tableau = []
    for semaine in calendar.monthcalendar(int(annee), mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                jour_date = date(int(annee), mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning[jour_date])
                ligne.append(contenu)
        tableau.append(ligne)

    st.table(pd.DataFrame(tableau, columns=["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]))

# 📊 Rapport mensuel
def afficher_rapport(df):
    st.subheader("📊 Rapport mensuel")

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

    st.line_chart(stats.pivot(index="période", columns="plateforme", values="prix_brut").fillna(0))
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="nuitees").fillna(0))
    st.bar_chart(stats.pivot(index="période", columns="plateforme", values="charges").fillna(0))

# 👥 Liste des clients
def liste_clients(df):
    st.subheader("👥 Liste des clients")
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()), key="annee_clients")
    mois = st.selectbox("Mois", ["Tous"] + list(range(1, 13)), key="mois_clients")

    data = df[df["AAAA"] == annee]
    if mois != "Tous":
        data = data[data["MM"] == mois]

    colonnes = ["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "prix_brut", "prix_net", "charges", "%"]
    st.dataframe(data[colonnes])
    st.download_button("📥 Télécharger CSV", data=data[colonnes].to_csv(index=False), file_name="clients.csv", mime="text/csv")

# ▶️ Application principale
def main():
    st.set_page_config("📖 Réservations Villa Tobias", layout="wide")
    st.sidebar.title("📁 Menu")

    uploader_excel()
    df = charger_donnees()

    if df.empty:
        st.warning("Aucune donnée disponible.")
        return

    notifier_arrivees_prochaines(df)

    onglet = st.sidebar.radio("Navigation", [
        "📋 Réservations",
        "➕ Ajouter",
        "✏️ Modifier / Supprimer",
        "📅 Calendrier",
        "📊 Rapport",
        "👥 Liste clients",
        "✉️ Historique SMS"
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
    elif onglet == "✉️ Historique SMS":
        historique_sms()

if __name__ == "__main__":
    main()
