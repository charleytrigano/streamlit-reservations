  import streamlit as st
    import pandas as pd
    import os
    import calendar
    from datetime import datetime, date, timedelta
    import requests

    FICHIER = "reservations.xlsx"
    SMS_HISTO = "historique_sms.csv"
    FREE_USER = "12026027"
    FREE_API_KEY = "MF7Qjs3C8KxKHz"
    NUM_TELEPHONE_PERSO = "+33600000000"

    # ========== GESTION FICHIER EXCEL ==========
    def charger_donnees():
        if os.path.exists(FICHIER):
            return pd.read_excel(FICHIER)
        else:
            return pd.DataFrame()

    def uploader_excel():
        uploaded = st.sidebar.file_uploader("📤 Importer un fichier Excel", type=["xlsx"])
        if uploaded:
            df = pd.read_excel(uploaded)
            df.to_excel(FICHIER, index=False)
            st.sidebar.success("✅ Fichier importé avec succès.")

    def telecharger_fichier_excel(df):
        st.sidebar.download_button(
            label="📥 Télécharger Excel",
            data=df.to_excel(index=False),
            file_name="reservations_export.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    # ========== GESTION SMS ==========
    def envoyer_sms(telephone, message):
        url = "https://smsapi.free-mobile.fr/sendmsg"
        params = {"user": FREE_USER, "pass": FREE_API_KEY, "msg": message}
        try:
            response = requests.get(url, params=params)
            return response.status_code == 200
        except Exception as e:
            st.error(f"Erreur SMS : {e}")
            return False

    def enregistrer_sms(nom, tel, contenu):
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        ligne = {"nom": nom, "telephone": tel, "message": contenu, "horodatage": now}
        df_hist = pd.DataFrame([ligne])
        if os.path.exists(SMS_HISTO):
            df_hist = pd.concat([pd.read_csv(SMS_HISTO), df_hist], ignore_index=True)
        df_hist.to_csv(SMS_HISTO, index=False)

    def notifier_arrivees_prochaines(df):
        demain = date.today() + timedelta(days=1)
        df_notif = df[df["date_arrivee"] == demain]
        for _, row in df_notif.iterrows():
            message = f"""VILLA TOBIAS - {row['plateforme']}
Bonjour {row['nom_client']} 👋
Votre séjour commence demain ({row['date_arrivee']} ➡ {row['date_depart']}).
Merci de nous indiquer votre heure d’arrivée 🕐
Parking disponible 🚗"""
            envoyer_sms(row["telephone"], message)
            envoyer_sms(NUM_TELEPHONE_PERSO, message)
            enregistrer_sms(row["nom_client"], row["telephone"], message)

    def historique_sms():
        st.subheader("📨 Historique des SMS")
        if os.path.exists(SMS_HISTO):
            df = pd.read_csv(SMS_HISTO)
            st.dataframe(df)
            st.download_button("📥 Télécharger CSV", df.to_csv(index=False), file_name="historique_sms.csv")
        else:
            st.info("Aucun SMS envoyé.")

    # ========== VUES ==========
    def afficher_reservations(df):
        st.title("📋 Réservations")
        st.dataframe(df)

    def ajouter_reservation(df):
        st.subheader("➕ Nouvelle Réservation")
        with st.form("ajout"):
            nom = st.text_input("Nom")
            plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
            tel = st.text_input("Téléphone")
            arrivee = st.date_input("Date arrivée")
            depart = st.date_input("Date départ", min_value=arrivee + timedelta(days=1))
            prix_brut = st.number_input("Prix brut", min_value=0.0)
            prix_net = st.number_input("Prix net", min_value=0.0, max_value=prix_brut)
            submit = st.form_submit_button("Enregistrer")
            if submit:
                ligne = {
                    "nom_client": nom,
                    "plateforme": plateforme,
                    "telephone": tel,
                    "date_arrivee": arrivee,
                    "date_depart": depart,
                    "prix_brut": round(prix_brut, 2),
                    "prix_net": round(prix_net, 2),
                    "charges": round(prix_brut - prix_net, 2),
                    "%": round((prix_brut - prix_net) / prix_brut * 100, 2) if prix_brut else 0,
                    "nuitees": (depart - arrivee).days,
                    "annee": arrivee.year,
                    "mois": arrivee.month
                }
                df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
                df.to_excel(FICHIER, index=False)
                st.success("✅ Réservation enregistrée")

    def modifier_reservation(df):
        st.subheader("✏️ Modifier / Supprimer")
        df["identifiant"] = df["nom_client"] + " | " + pd.to_datetime(df["date_arrivee"]).astype(str)
        selection = st.selectbox("Choisissez une réservation", df["identifiant"])
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
                df.to_excel(FICHIER, index=False)
                st.success("✅ Réservation modifiée")
            if delete:
                df.drop(index=i, inplace=True)
                df.to_excel(FICHIER, index=False)
                st.warning("🗑 Réservation supprimée")

    def afficher_calendrier(df):
        st.subheader("📅 Calendrier")
        st.info("En construction...")

    def afficher_rapport(df):
        st.subheader("📊 Rapport")
        st.info("En construction...")

    def liste_clients(df):
        st.subheader("👥 Liste des clients")
        st.dataframe(df)

    # ========== MAIN ==========
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
