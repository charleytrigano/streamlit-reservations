# pages/1_📅_Calendrier.py
import streamlit as st
import pandas as pd
import calendar
from datetime import date
import utils

st.set_page_config(page_title="Calendrier", layout="wide")

st.header("📅 Calendrier des Réservations")

df, palette = utils.charger_donnees_csv()
df_dates_valides = df.dropna(subset=['date_arrivee', 'date_depart', 'AAAA'])

if df_dates_valides.empty:
    st.info("Aucune réservation à afficher.")
else:
    # ... (le code complet du calendrier que nous avions validé va ici)
    pass
