import streamlit as st
import pandas as pd
from datetime import date, datetime, timedelta
import calendar
import requests
import os

SMS_HISTO = "historique_sms.csv"
FREE_USER = "12026027"
FREE_API_KEY = "MF7Qjs3C8KxKHz"
NUM_TELEPHONE_PERSO = "+33617722379"

# ✉️ Envoyer un SMS via Free Mobile API
def envoyer_sms(telephone, message):
    url = f"https://smsapi.free-mobile.fr/sendmsg"
    params = {"user": FREE_USER, "pass": FREE_API_KEY, "msg": message}
    response = requests.get(url, params=params)
    return response.status_code == 200

# 📝 Enregistrer le SMS dans un fichier CSV
def enregistrer_sms(nom, tel, contenu):
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ligne = {"nom": nom, "telephone": tel, "message": contenu, "horodatage": now}
    df_hist = pd.DataFrame([ligne])
    if os.path.exists(SMS_HISTO):
        df_hist = pd.concat([pd.read_csv(SMS_HISTO), df_hist], ignore_index=True)
    df_hist.to_csv(SMS_HISTO, index=False)

# 🔔 Envoyer les SMS de rappel la veille de l'arrivée
def notifier_arrivees_prochaines(df):
    demain = date.today() + timedelta(days=1)
    df_notif = df[df["date_arrivee"] == demain]
    for _, row in df_notif.iterrows():
        message = f"""
        VILLA TOBIAS - {row['plateforme']}
        Bonjour {row['nom_client']}. Votre séjour est prévu du {row['date_arrivee']} au {row['date_depart']}.
        Afin de vous accueillir merci de nous confirmer votre heure d’arrivée.
        Un parking est à votre disposition sur place. À demain
        """
        envoyer_sms(row["telephone"], message)
        envoyer_sms(NUM_TELEPHONE_PERSO, message)
        enregistrer_sms(row["nom_client"], row["telephone"], message)

# 📨 Afficher l'historique des SMS
def historique_sms():
    st.subheader("📨 Historique des SMS envoyés")
    if os.path.exists(SMS_HISTO):
        df = pd.read_csv(SMS_HISTO)
        st.dataframe(df)
    else:
        st.info("Aucun SMS envoyé pour le moment.")
