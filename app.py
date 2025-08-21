import streamlit as st
import pandas as pd
import numpy as np
import os
import json
import calendar
from datetime import datetime

# =========================
# CONSTANTES
# =========================
DATA_FILE = "reservations.xlsx"
PLATFORM_FILE = "platform_colors.json"
LOGO_FILE = "logo.png"

# =========================
# FONCTIONS DE DONNÉES
# =========================
@st.cache_data
def load_data():
    if os.path.exists(DATA_FILE):
        return pd.read_excel(DATA_FILE, engine="openpyxl")
    else:
        return pd.DataFrame(columns=[
            "Plateforme","Numéro Réservation","Nom du client",
            "Date arrivée","Date départ","Personnes","Tarif",
            "% comm.","Montant de la commission","Durée (nuits)",
            "Numéro de téléphone","Payé"
        ])

def save_data(df):
    df.to_excel(DATA_FILE, index=False, engine="openpyxl")

def load_platform_colors():
    if os.path.exists(PLATFORM_FILE):
        with open(PLATFORM_FILE, "r") as f:
            return json.load(f)
    return {"Booking": "#1e90ff", "Airbnb": "#ff5a5f", "Abritel": "#00a699", "Autre": "#f59e0b"}

def save_platform_colors(colors):
    with open(PLATFORM_FILE, "w") as f:
        json.dump(colors, f)

# =========================
# CALENDRIER
# =========================
def render_calendar(df, platform_colors):
    st.header("🗓️ Calendrier")

    if df.empty:
        st.info("Aucune réservation à afficher")
        return

    # Sélecteurs année et mois
    years = sorted(df["Date arrivée"].dropna().dt.year.unique())
    year = st.selectbox("Année", years, index=len(years)-1)
    months = list(range(1, 13))
    month = st.selectbox("Mois", months, index=datetime.now().month-1)

    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(year, month)

    # Préparer dict des réservations
    reservations = {}
    for _, row in df.iterrows():
        if pd.isna(row["Date arrivée"]) or pd.isna(row["Date départ"]):
            continue
        start = pd.to_datetime(row["Date arrivée"])
        end = pd.to_datetime(row["Date départ"])
        for d in pd.date_range(start, end - pd.Timedelta(days=1)):
            if d.year == year and d.month == month:
                reservations.setdefault(d.day, []).append((row["Nom du client"], row["Plateforme"]))

    # Générer calendrier
    html = "<table style='border-collapse: collapse; width: 100%; table-layout: fixed;'>"
    html += "<tr>" + "".join([f"<th style='border:1px solid #ddd; padding:4px; background:#f0f0f0;'>{day}</th>" for day in ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]]) + "</tr>"

    for week in month_days:
        html += "<tr>"
        for d in week:
            if d == 0:
                html += "<td style='border:1px solid #ddd; padding:20px; background:#fafafa;'></td>"
            else:
                day_resas = reservations.get(d, [])
                cell_html = f"<div style='font-weight:bold; margin-bottom:4px;'>{d}</div>"
                for client, pf in day_resas:
                    color = platform_colors.get(pf, "#808080")
                    cell_html += f"<div style='background:{color}; color:white; padding:2px; border-radius:4px; margin:1px; font-size:12px;'>{client}</div>"
                html += f"<td style='border:1px solid #ddd; vertical-align:top; padding:4px;'>{cell_html}</td>"
        html += "</tr>"
    html += "</table>"

    st.markdown(html, unsafe_allow_html=True)

    # Légende
    st.subheader("Légende plateformes")
    for pf, color in platform_colors.items():
        st.markdown(f"<span style='background:{color}; color:white; padding:4px; border-radius:4px;'>{pf}</span>", unsafe_allow_html=True)

# =========================
# VUES
# =========================
def vue_reservations(df, platform_colors):
    st.header("📋 Réservations")

    st.sidebar.subheader("🎛️ Options d’affichage")
    filtre_paye = st.sidebar.radio("Filtrer payé", ["Tous","Payé","Non payé"])

    if filtre_paye == "Payé":
        df = df[df["Payé"] == True]
    elif filtre_paye == "Non payé":
        df = df[df["Payé"] == False]

    st.dataframe(df)

    # Sauvegarde Excel
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=df.to_excel(index=False, engine="openpyxl"),
        file_name="reservations_export.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Restauration Excel
    uploaded = st.sidebar.file_uploader("📂 Restaurer depuis Excel", type=["xlsx"])
    if uploaded:
        df_new = pd.read_excel(uploaded, engine="openpyxl")
        save_data(df_new)
        st.sidebar.success("Réservations restaurées avec succès !")
        st.experimental_rerun()

def vue_calendrier(df, platform_colors):
    render_calendar(df, platform_colors)

def vue_rapport(df):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Pas encore de données.")
        return

    total = df["Tarif"].sum()
    commissions = df["Montant de la commission"].sum()
    st.metric("Chiffre d’affaires", f"{total:.2f} €")
    st.metric("Commissions", f"{commissions:.2f} €")

# =========================
# MAIN
# =========================
def main():
    st.set_page_config(page_title="Gestion Réservations", layout="wide")

    if os.path.exists(LOGO_FILE):
        st.image(LOGO_FILE, width=120)

    df = load_data()
    platform_colors = load_platform_colors()

    onglet = st.sidebar.radio("Navigation", ["📋 Réservations","🗓️ Calendrier","📊 Rapport"])

    if onglet == "📋 Réservations":
        vue_reservations(df, platform_colors)
    elif onglet == "🗓️ Calendrier":
        vue_calendrier(df, platform_colors)
    elif onglet == "📊 Rapport":
        vue_rapport(df)

    # Palette plateformes
    st.sidebar.subheader("🎨 Palette des plateformes")
    for pf in df["Plateforme"].dropna().unique():
        new_color = st.sidebar.color_picker(f"{pf}", platform_colors.get(pf, "#808080"))
        platform_colors[pf] = new_color

    if st.sidebar.button("💾 Sauvegarder couleurs"):
        save_platform_colors(platform_colors)
        st.sidebar.success("Palette sauvegardée !")

if __name__ == "__main__":
    main()