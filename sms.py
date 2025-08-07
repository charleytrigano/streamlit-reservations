# sms.py simplifié
import streamlit as st
import pandas as pd

def notifier_arrivees_prochaines(df):
    st.info("📬 Notifications d'arrivée (simulation)")
    if not df.empty:
        st.write("Rappels envoyés (simulation).")

def historique_sms():
    st.subheader("📨 Historique des SMS envoyés")
    st.info("Aucun SMS enregistré (version de test).")
