import streamlit as st
import pandas as pd
import calendar
from datetime import date
import io
import os

FICHIER = "reservations.xlsx"

# 📂 Charger les données
def charger_donnees():
    if not os.path.exists(FICHIER):
        return pd.DataFrame()
    df = pd.read_excel(FICHIER)
    if "AAAA" not in df.columns:
        df["AAAA"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year
    if "MM" not in df.columns:
        df["MM"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.month
    return df

# 💾 Sauvegarder
def sauvegarder_donnees(df):
    df.to_excel(FICHIER, index=False)

# 📥 Télécharger le fichier
def telecharger_fichier_excel(df):
    towrite = io.BytesIO()
    df.to_excel(towrite, index=False)
    towrite.seek(0)
    st.download_button(
        label="📥 Télécharger le fichier Excel",
        data=towrite,
        file_name=FICHIER,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# 📤 Restaurer
def restaurer_fichier():
    fichier = st.file_uploader("📤 Restaurer un fichier Excel", type=["xlsx"])
    if fichier:
        with open(FICHIER, "wb") as f:
            f.write(fichier.getbuffer())
        st.success("✅ Fichier restauré avec succès")
        st.rerun()

# 📋 Réservations
def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)
    telecharger_fichier_excel(df)
    restaurer_fichier()

# ➕ Ajouter
def vue_ajouter(df):
    st.subheader("➕ Nouvelle Réservation")
    with st.form("ajout"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Abritel", "Autre"])
        date_arrivee = st.date_input("Date arrivée")
        date_depart = st.date_input("Date départ")
        prix = st.number_input("Prix brut (€)", min_value=0.0, format="%.2f")
        commission = st.number_input("Commission (€)", min_value=0.0, format="%.2f")
        submit = st.form_submit_button("Enregistrer")
        if submit:
            nouvelle = {
                "nom": nom,
                "plateforme": plateforme,
                "date_arrivee": date_arrivee.strftime("%Y/%m/%d"),
                "date_depart": date_depart.strftime("%Y/%m/%d"),
                "prix_brut": round(prix, 2),
                "commission": round(commission, 2),
                "AAAA": date_arrivee.year,
                "MM": date_arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([nouvelle])], ignore_index=True)
            sauvegarder_donnees(df)
            st.success("✅ Réservation enregistrée")
            st.rerun()

# ✏️ Modifier / Supprimer
def vue_modifier(df):
    st.subheader("✏️ Modifier / Supprimer")
    if df.empty:
        st.warning("Aucune réservation à modifier")
        return
    index = st.selectbox("Sélectionner une réservation", df.index, format_func=lambda i: f"{df.at[i,'nom']} - {df.at[i,'date_arrivee']}")
    with st.form("modifier"):
        nom = st.text_input("Nom du client", df.at[index, "nom"])
        plateforme = st.text_input("Plateforme", df.at[index, "plateforme"])
        date_arrivee = st.date_input("Date arrivée", pd.to_datetime(df.at[index, "date_arrivee"]))
        date_depart = st.date_input("Date départ", pd.to_datetime(df.at[index, "date_depart"]))
        prix = st.number_input("Prix brut (€)", value=float(df.at[index, "prix_brut"]), format="%.2f")
        commission = st.number_input("Commission (€)", value=float(df.at[index, "commission"]), format="%.2f")
        modifier_btn = st.form_submit_button("Modifier")
        supprimer_btn = st.form_submit_button("Supprimer")
        if modifier_btn:
            df.at[index, "nom"] = nom
            df.at[index, "plateforme"] = plateforme
            df.at[index, "date_arrivee"] = date_arrivee.strftime("%Y/%m/%d")
            df.at[index, "date_depart"] = date_depart.strftime("%Y/%m/%d")
            df.at[index, "prix_brut"] = round(prix, 2)
            df.at[index, "commission"] = round(commission, 2)
            df.at[index, "AAAA"] = date_arrivee.year
            df.at[index, "MM"] = date_arrivee.month
            sauvegarder_donnees(df)
            st.success("✅ Réservation modifiée")
            st.rerun()
        if supprimer_btn:
            df = df.drop(index)
            sauvegarder_donnees(df)
            st.warning("🗑 Réservation supprimée")
            st.rerun()

# 📅 Calendrier
def afficher_calendrier(df):
    st.subheader("📅 Calendrier mensuel")
    if df.empty:
        st.warning("Aucune donnée disponible")
        return
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()), index=0)
    mois = st.selectbox("Mois", range(1, 13), index=date.today().month - 1)
    nb_jours = calendar.monthrange(int(annee), int(mois))[1]
    jours = [date(int(annee), int(mois), j) for j in range(1, nb_jours + 1)]
    for jour in jours:
        reservations_jour = df[pd.to_datetime(df["date_arrivee"]) <= jour]
        reservations_jour = reservations_jour[pd.to_datetime(reservations_jour["date_depart"]) >= jour]
        if not reservations_jour.empty:
            st.write(f"**{jour.strftime('%Y/%m/%d')}**")
            st.table(reservations_jour[["nom", "plateforme", "date_arrivee", "date_depart"]])

# 📊 Rapport
def afficher_rapport(df):
    st.subheader("📊 Rapport")
    if df.empty:
        st.warning("Aucune donnée disponible")
        return
    stats = df.groupby(["AAAA", "MM", "plateforme"]).agg({
        "prix_brut": "sum",
        "commission": "sum"
    }).reset_index()
    stats["période"] = stats["MM"].apply(lambda m: calendar.month_abbr[int(m)]) + " " + stats["AAAA"].astype(str)
    st.dataframe(stats)

# 👥 Liste clients
def liste_clients(df):
    st.subheader("👥 Liste des clients")
    st.dataframe(df[["nom", "plateforme", "date_arrivee", "date_depart"]].drop_duplicates())

# 📜 Historique SMS (fictif)
def historique_sms():
    st.subheader("✉️ Historique SMS")
    st.info("Fonctionnalité en construction.")

# ▶️ Application principale
def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
    df = charger_donnees()

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
    elif onglet == "➕ Ajouter":
        vue_ajouter(df)
    elif onglet == "✏️ Modifier / Supprimer":
        vue_modifier(df)
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
