import streamlit as st
import pandas as pd
import numpy as np
import os, calendar, hashlib
from datetime import date, datetime
from io import BytesIO

# =====================
# CONFIGURATION GÉNÉRALE
# =====================

LOGO_FILE = "logo.png"
EXCEL_FILE = "reservations.xlsx"

DEFAULT_PLATFORMS = {
    "Booking": "#1e90ff",
    "Airbnb": "#ff385c",
    "Autre": "#f59e0b",
}

if "PLATFORM_COLORS" not in st.session_state:
    st.session_state["PLATFORM_COLORS"] = dict(DEFAULT_PLATFORMS)

PLATFORM_COLORS = st.session_state["PLATFORM_COLORS"]

# =====================
# OUTILS
# =====================

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Assure que les colonnes essentielles sont présentes"""
    required = ["nom_client", "plateforme", "date_arrivee", "date_depart", "paye", "AAAA", "MM"]
    for col in required:
        if col not in df.columns:
            df[col] = None
    return df

def split_totals(df: pd.DataFrame):
    """Sépare les lignes normales des totaux"""
    if df.empty:
        return df, df
    core = df[~df["nom_client"].astype(str).str.contains("TOTAL", case=False, na=False)]
    totals = df[df["nom_client"].astype(str).str.contains("TOTAL", case=False, na=False)]
    return core, totals

def load_data():
    if not os.path.exists(EXCEL_FILE):
        return pd.DataFrame()
    try:
        df = pd.read_excel(EXCEL_FILE)
    except Exception:
        return pd.DataFrame()

    # Conversion des dates
    for col in ["date_arrivee", "date_depart"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    # Extraire année et mois si absent
    if "AAAA" not in df.columns and "date_arrivee" in df.columns:
        df["AAAA"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year
    if "MM" not in df.columns and "date_arrivee" in df.columns:
        df["MM"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.month

    return ensure_schema(df)

def save_data(df: pd.DataFrame):
    df.to_excel(EXCEL_FILE, index=False)

# =====================
# VUES
# =====================

def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")

    if df.empty:
        st.info("Aucune réservation disponible.")
        return

    # Filtres
    st.sidebar.subheader("🎛️ Options d’affichage")
    filtre_paye = st.sidebar.radio("Filtrer payé", ["Tous", "Payé", "Non payé"])
    plateformes = sorted(df["plateforme"].dropna().unique())
    filtre_pf = st.sidebar.multiselect("Plateformes", plateformes, default=plateformes)

    # Application filtres
    filtered = df.copy()
    if filtre_paye == "Payé":
        filtered = filtered[filtered["paye"] == True]
    elif filtre_paye == "Non payé":
        filtered = filtered[filtered["paye"] == False]

    if filtre_pf:
        filtered = filtered[filtered["plateforme"].isin(filtre_pf)]

    st.dataframe(filtered, use_container_width=True)

    # Ajout rapide plateforme
    st.subheader("➕ Ajouter une nouvelle plateforme")
    new_pf = st.text_input("Nom de la plateforme")
    if st.button("Ajouter"):
        if new_pf.strip():
            if new_pf not in PLATFORM_COLORS:
                # Génère une couleur stable
                h = int(hashlib.sha1(new_pf.encode("utf-8")).hexdigest()[:6], 16)
                color = f"#{(h>>16)&0xFF:02x}{(h>>8)&0xFF:02x}{h&0xFF:02x}"
                PLATFORM_COLORS[new_pf] = color
                st.success(f"Plateforme {new_pf} ajoutée avec couleur {color}")
            else:
                st.warning("Cette plateforme existe déjà.")

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée pour le rapport.")
        return

    core, _ = split_totals(df)

    # Exemple : Total revenu
    total_revenu = core["tarif"].sum() if "tarif" in core.columns else 0
    total_resa = len(core)

    st.metric("Nombre de réservations", total_resa)
    st.metric("Revenu total", f"{total_revenu:.2f} €")

def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier")

    if df.empty:
        st.info("Aucune donnée pour le calendrier.")
        return

    # Choix année + mois
    years = sorted(df["AAAA"].dropna().unique())
    year = st.selectbox("Année", years, index=len(years)-1)

    months = list(range(1, 13))
    month = st.selectbox("Mois", months, index=date.today().month-1)

    # Filtrer
    mask = (df["AAAA"] == year) & (df["MM"] == month)
    subset = df[mask]

    if subset.empty:
        st.warning("Aucune réservation ce mois.")
        return

    # Génération du calendrier
    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(year, month)

    html = "<table style='border-collapse: collapse; width:100%; text-align:center;'>"
    html += "<tr>" + "".join([f"<th>{day}</th>" for day in ["Lun", "Mar", "Mer", "Jeu", "Ven", "Sam", "Dim"]]) + "</tr>"

    for week in month_days:
        html += "<tr>"
        for d in week:
            if d.month != month:
                html += "<td style='background:#f0f0f0; padding:6px;'></td>"
            else:
                # Vérifie les réservations
                cell_content = ""
                cell_color = "#ffffff"
                for _, row in subset.iterrows():
                    if row["date_arrivee"] <= d <= row["date_depart"]:
                        pf = row["plateforme"]
                        color = PLATFORM_COLORS.get(pf, "#999999")
                        client = row["nom_client"]
                        cell_content += f"<div style='background:{color}; color:white; padding:2px; margin:1px; border-radius:4px; font-size:12px;'>{client}</div>"
                html += f"<td style='vertical-align:top; min-width:100px; height:80px; border:1px solid #ddd; padding:2px;'>{d.day}<br>{cell_content}</td>"
        html += "</tr>"
    html += "</table>"

    st.markdown(html, unsafe_allow_html=True)

    # Légende
    st.subheader("🎨 Légende des plateformes")
    cols = st.columns(len(PLATFORM_COLORS))
    for i, (pf, color) in enumerate(PLATFORM_COLORS.items()):
        with cols[i]:
            st.markdown(f"<div style='background:{color}; color:white; padding:4px; border-radius:4px; text-align:center;'>{pf}</div>", unsafe_allow_html=True)

# =====================
# MAIN
# =====================

def main():
    # Logo
    if os.path.exists(LOGO_FILE):
        st.image(LOGO_FILE, width=120)

    df = load_data()

    menu = st.sidebar.radio("Navigation", ["📋 Réservations", "📊 Rapport", "📅 Calendrier"])

    if menu == "📋 Réservations":
        vue_reservations(df)
    elif menu == "📊 Rapport":
        vue_rapport(df)
    elif menu == "📅 Calendrier":
        vue_calendrier(df)

    # Sauvegarde
    if not df.empty:
        buffer = BytesIO()
        df.to_excel(buffer, index=False)
        st.sidebar.download_button(
            "💾 Sauvegarde Excel",
            data=buffer.getvalue(),
            file_name="reservations_sauvegarde.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

if __name__ == "__main__":
    main()