import pandas as pd
import streamlit as st
from datetime import date, datetime, timedelta
import requests
import os

# 🔐 Identifiants Free Mobile (modifier si besoin)
FREE_USER = "12026027"
FREE_API_KEY = "MF7Qjs3C8KxKHz"
NUM_TELEPHONE_PERSO = "+33617722379"

# 📁 Nom du fichier CSV de suivi des SMS
SMS_HISTO = "historique_sms.csv"

# ✉️ Envoi de SMS via Free Mobile
def envoyer_sms(telephone, message):
    url = "https://smsapi.free-mobile.fr/sendmsg"
    params = {
        "user": FREE_USER,
        "pass": FREE_API_KEY,
        "msg": message
    }
    response = requests.get(url, params=params)
    return response.status_code == 200

# 📝 Enregistrement local dans historique_sms.csv
def enregistrer_sms(nom, tel, contenu):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ligne = {"nom": nom, "telephone": tel, "message": contenu, "horodatage": now}
    df_hist = pd.DataFrame([ligne])
    if os.path.exists(SMS_HISTO):
        df_hist = pd.concat([pd.read_csv(SMS_HISTO), df_hist], ignore_index=True)
    df_hist.to_csv(SMS_HISTO, index=False)

# 🔔 Notification automatique la veille de l'arrivée
def notifier_arrivees_prochaines(df):
    demain = date.today() + timedelta(days=1)
    df_notif = df[df["date_arrivee"] == demain]
    for _, row in df_notif.iterrows():
        message = (
            f"VILLA TOBIAS - {row['plateforme']}\n"
            f"Bonjour {row['nom_client']}. Votre séjour est prévu du {row['date_arrivee']} au {row['date_depart']}.\n"
            "Afin de vous accueillir merci de nous confirmer votre heure d’arrivée.\n"
            "Un parking est à votre disposition sur place. À demain"
        )
        envoyer_sms(row["telephone"], message)
        envoyer_sms(NUM_TELEPHONE_PERSO, message)
        enregistrer_sms(row["nom_client"], row["telephone"], message)

# 📄 Affichage de l’historique des SMS
def historique_sms():
    st.subheader("📨 Historique des SMS envoyés")
    if os.path.exists(SMS_HISTO):
        df = pd.read_csv(SMS_HISTO)
        st.dataframe(df)
    else:
        st.info("Aucun SMS envoyé pour le moment.")

