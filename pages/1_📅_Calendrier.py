# pages/1_📅_Calendrier.py
import streamlit as st
import pandas as pd
import calendar
from datetime import date
import utils # Importe notre fichier utils

st.set_page_config(page_title="Calendrier", layout="wide")

st.header("📅 Calendrier des Réservations")

df, palette = utils.charger_donnees_csv()
df_dates_valides = df.dropna(subset=['date_arrivee', 'date_depart', 'AAAA'])

if df_dates_valides.empty:
    st.info("Aucune réservation avec des dates valides à afficher.")
else:
    c1, c2 = st.columns(2)
    today = date.today()
    noms_mois = [calendar.month_name[i] for i in range(1, 13)]
    selected_month_name = c1.selectbox("Mois", options=noms_mois, index=today.month - 1)
    selected_month = noms_mois.index(selected_month_name) + 1
    available_years = sorted(list(df_dates_valides['AAAA'].dropna().astype(int).unique()))
    if not available_years: available_years = [today.year]
    try: default_year_index = available_years.index(today.year)
    except ValueError: default_year_index = len(available_years) - 1
    selected_year = c2.selectbox("Année", options=available_years, index=default_year_index)

    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(selected_year, selected_month)

    st.markdown("""
    <style>
        .calendar-day { border: 1px solid #444; min-height: 120px; padding: 5px; vertical-align: top; }
        .calendar-day.outside-month { background-color: #2e2e2e; }
        .calendar-date { font-weight: bold; font-size: 1.1em; margin-bottom: 5px; text-align: right; }
        .reservation-bar { padding: 3px 6px; margin-bottom: 3px; border-radius: 5px; font-size: 0.9em; overflow: hidden; white-space: nowrap; text-overflow: ellipsis; }
    </style>
    """, unsafe_allow_html=True)
    
    headers = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    st.write(f'<div style="display:grid; grid-template-columns: repeat(7, 1fr); text-align: center; font-weight: bold;">{"".join(f"<div>{h}</div>" for h in headers)}</div>', unsafe_allow_html=True)
    
    for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                day_class = "outside-month" if day.month != selected_month else ""
                day_html = f"<div class='calendar-day {day_class}'><div class='calendar-date'>{day.day}</div>"
                for _, resa in df_dates_valides.iterrows():
                    if isinstance(resa['date_arrivee'], date) and isinstance(resa['date_depart'], date):
                        if resa['date_arrivee'] <= day < resa['date_depart']:
                            color = palette.get(resa['plateforme'], '#888888')
                            text_color = "#FFFFFF" if utils.is_dark_color(color) else "#000000"
                            day_html += f"<div class='reservation-bar' style='background-color:{color}; color:{text_color};' title='{resa['nom_client']}'>{resa['nom_client']}</div>"
                day_html += "</div>"
                st.markdown(day_html, unsafe_allow_html=True)
