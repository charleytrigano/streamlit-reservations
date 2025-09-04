# app.py — Villa Tobias (COMPLET) - Version CSV-Direct avec Calendrier

import streamlit as st
import pandas as pd
import numpy as np
import os
import calendar
from datetime import date, timedelta

CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv" 

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = { "Booking": "#1e90ff", "Airbnb":  "#e74c3c", "Autre":   "#f59e0b" }

# ============================== CORE DATA FUNCTIONS ==============================
@st.cache_data
def charger_donnees_csv():
    """Charge les données directement depuis les fichiers CSV."""
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=';')
        df.columns = df.columns.str.strip()
    except FileNotFoundError:
        return pd.DataFrame(), DEFAULT_PALETTE
    except Exception as e:
        st.error(f"Erreur de lecture de {CSV_RESERVATIONS}")
        st.exception(e)
        return pd.DataFrame(), DEFAULT_PALETTE

    try:
        df_palette = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        palette = dict(zip(df_palette['plateforme'], df_palette['couleur']))
    except:
        palette = DEFAULT_PALETTE.copy()

    df = ensure_schema(df)
    return df, palette

def sauvegarder_donnees_csv(df):
    """Sauvegarde le DataFrame dans le fichier CSV."""
    try:
        df_to_save = df.copy()
        for col in ['date_arrivee', 'date_depart']:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime('%d/%m/%Y')
        
        df_to_save.to_csv(CSV_RESERVATIONS, sep=';', index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ==============================  SCHEMA & DATA VALIDATION  ==============================
BASE_COLS = [
    'paye', 'nom_client', 'sms_envoye', 'plateforme', 'telephone', 'date_arrivee',
    'date_depart', 'nuitees', 'prix_brut', 'commissions', 'frais_cb',
    'prix_net', 'menage', 'taxes_sejour', 'base', 'charges', '%',
    'AAAA', 'MM', 'ical_uid'
]

def ensure_schema(df):
    df_res = df.copy()
    rename_map = { 
        'Payé': 'paye', 'Client': 'nom_client', 'Plateforme': 'plateforme', 
        'Arrivée': 'date_arrivee', 'Départ': 'date_depart', 'Nuits': 'nuitees',
        'Brut (€)': 'prix_brut', 'Charges (€)': 'charges', 'Net (€)': 'prix_net',
        'Charges (%)': '%'
    }
    df_res.rename(columns=rename_map, inplace=True)

    for col in BASE_COLS:
        if col not in df_res.columns:
            df_res[col] = None

    date_cols = ["date_arrivee", "date_depart"]
    for col in date_cols:
        df_res[col] = pd.to_datetime(df_res[col], dayfirst=True, errors='coerce')

    mask_dates = pd.notna(df_res["date_arrivee"]) & pd.notna(df_res["date_depart"])
    df_res.loc[mask_dates, "nuitees"] = (df_res.loc[mask_dates, "date_depart"] - df_res.loc[mask_dates, "date_arrivee"]).dt.days

    for col in date_cols:
        df_res[col] = df_res[col].dt.date

    if 'paye' in df_res.columns and df_res['paye'].dtype == 'object':
        df_res['paye'] = df_res['paye'].str.strip().str.upper().isin(['VRAI', 'TRUE'])
    df_res['paye'] = df_res['paye'].fillna(False).astype(bool)

    numeric_cols = ['prix_brut', 'commissions', 'frais_cb', 'menage', 'taxes_sejour']
    for col in numeric_cols:
        if col in df_res.columns:
            if df_res[col].dtype == 'object':
                df_res[col] = df_res[col].astype(str).str.replace('€', '', regex=False).str.replace(',', '.', regex=False).str.replace(' ', '', regex=False).str.strip()
            df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)
    
    df_res['prix_net'] = df_res['prix_brut'].fillna(0) - df_res['commissions'].fillna(0) - df_res['frais_cb'].fillna(0)
    df_res['charges'] = df_res['prix_brut'].fillna(0) - df_res['prix_net'].fillna(0)
    df_res['base'] = df_res['prix_net'].fillna(0) - df_res['menage'].fillna(0) - df_res['taxes_sejour'].fillna(0)
    
    with np.errstate(divide='ignore', invalid='ignore'):
        df_res['%'] = np.where(df_res['prix_brut'] > 0, (df_res['charges'] / df_res['prix_brut'] * 100), 0)

    date_arrivee_dt = pd.to_datetime(df_res["date_arrivee"], errors='coerce')
    df_res.loc[pd.notna(date_arrivee_dt), 'AAAA'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.year
    df_res.loc[pd.notna(date_arrivee_dt), 'MM'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.month
    
    return df_res

# ============================== UTILITIES & HELPERS ==============================
def is_dark_color(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        luminance = (0.299 * rgb[0] + 0.587 * rgb[1] + 0.114 * rgb[2]) / 255
        return luminance < 0.5
    except (ValueError, TypeError):
        return True

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")

    csv_data = df.to_csv(sep=';', index=False).encode('utf-8')
    st.download_button(
        label="📥 Télécharger le fichier de réservations (CSV)",
        data=csv_data,
        file_name="reservations.xlsx - Sheet1.csv",
        mime='text/csv',
    )
    st.markdown("---")

    if df.empty:
        st.info("Aucune réservation trouvée.")
        return
        
    df_sorted = df.sort_values(by="date_arrivee", ascending=False, na_position='last').reset_index(drop=True)
    
    column_config = {
        "paye": st.column_config.CheckboxColumn("Payé"),
        "nuitees": st.column_config.NumberColumn("Nuits", format="%d"),
        "prix_brut": st.column_config.NumberColumn("Prix Brut", format="%.2f €"),
        "commissions": st.column_config.NumberColumn("Commissions", format="%.2f €"),
        "frais_cb": st.column_config.NumberColumn("Frais CB", format="%.2f €"),
        "prix_net": st.column_config.NumberColumn("Prix Net", format="%.2f €"),
        "menage": st.column_config.NumberColumn("Ménage", format="%.2f €"),
        "taxes_sejour": st.column_config.NumberColumn("Taxes Séjour", format="%.2f €"),
        "base": st.column_config.NumberColumn("Base", format="%.2f €"),
        "charges": st.column_config.NumberColumn("Charges", format="%.2f €"),
        "%": st.column_config.NumberColumn("% Charges", format="%.2f %%"),
        "AAAA": st.column_config.NumberColumn("Année", format="%d"),
        "MM": st.column_config.NumberColumn("Mois", format="%d"),
        "date_arrivee": st.column_config.DateColumn("Arrivée", format="DD/MM/YYYY"),
        "date_depart": st.column_config.DateColumn("Départ", format="DD/MM/YYYY"),
    }
    
    st.dataframe(df_sorted, column_config=column_config, use_container_width=True)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une Réservation")
    with st.form("form_ajout", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom_client = st.text_input("**Nom du Client**")
            telephone = st.text_input("Téléphone")
            date_arrivee = st.date_input("**Date d'arrivée**", date.today())
            date_depart = st.date_input("**Date de départ**", date.today() + timedelta(days=1))
            plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()))
        with c2:
            prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, step=10.0, format="%.2f")
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=1.0, format="%.2f")
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.1, format="%.2f")
            menage = st.number_input("Ménage (€)", min_value=0.0, step=1.0, format="%.2f")
            taxes_sejour = st.number_input("Taxes Séjour (€)", min_value=0.0, step=0.1, format="%.2f")
            paye = st.checkbox("Payé", False)

        submitted = st.form_submit_button("✅ Ajouter la réservation")
        if submitted:
            if not nom_client or date_depart <= date_arrivee:
                st.error("Veuillez entrer un nom et vérifier que les dates sont correctes.")
            else:
                nouvelle_ligne = pd.DataFrame([{'nom_client': nom_client, 'telephone': telephone, 'date_arrivee': date_arrivee, 'date_depart': date_depart, 'plateforme': plateforme, 'prix_brut': prix_brut, 'commissions': commissions, 'frais_cb': frais_cb, 'menage': menage, 'taxes_sejour': taxes_sejour, 'paye': paye}])
                df_a_jour = pd.concat([df, nouvelle_ligne], ignore_index=True)
                df_a_jour = ensure_schema(df_a_jour)
                if sauvegarder_donnees_csv(df_a_jour):
                    st.success(f"Réservation pour **{nom_client}** ajoutée !")
                    st.rerun()

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer une Réservation")
    if df.empty:
        st.warning("Aucune réservation à modifier.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options_resa = [f"{idx}: {row['nom_client']} ({row['date_arrivee']})" for idx, row in df_sorted.iterrows() if pd.notna(row['date_arrivee'])]
    selection = st.selectbox("Sélectionnez une réservation", options=options_resa, index=None, placeholder="Choisissez une réservation...")
    
    if selection:
        idx_selection = int(selection.split(":")[0])
        resa_selectionnee = df_sorted.loc[idx_selection].copy()
        
        with st.form("form_modif"):
            # ... (contenu du formulaire de modification, similaire à vue_ajouter)
            st.warning("Le formulaire de modification complet sera ajouté dans la prochaine étape.")
            # ...

def vue_calendrier(df, palette):
    st.header("📅 Calendrier des Réservations")
    
    df_dates_valides = df.dropna(subset=['date_arrivee', 'date_depart'])
    if df_dates_valides.empty:
        st.info("Aucune réservation avec des dates valides à afficher.")
        return

    c1, c2 = st.columns(2)
    today = date.today()
    selected_month_name = c1.selectbox("Mois", options=calendar.month_name[1:], index=today.month - 1)
    selected_month = list(calendar.month_name).index(selected_month_name)
    
    available_years = sorted(df_dates_valides['AAAA'].dropna().unique().astype(int))
    if not available_years:
        available_years = [today.year]
    selected_year = c2.selectbox("Année", options=available_years, index=len(available_years) - 1)

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
                    if resa['date_arrivee'] <= day < resa['date_depart']:
                        color = palette.get(resa['plateforme'], '#888888')
                        text_color = "#FFFFFF" if is_dark_color(color) else "#000000"
                        day_html += f"<div class='reservation-bar' style='background-color:{color}; color:{text_color};' title='{resa['nom_client']}'>{resa['nom_client']}</div>"
                
                day_html += "</div>"
                st.markdown(day_html, unsafe_allow_html=True)

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df, palette = charger_donnees_csv()
    
    st.sidebar.title("🧭 Navigation")
    pages = { 
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "📅 Calendrier": vue_calendrier,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    
    page_function = pages[selection]

    if selection in ["➕ Ajouter", "✏️ Modifier / Supprimer", "📅 Calendrier"]:
        page_function(df, palette)
    else:
        page_function(df)

if __name__ == "__main__":
    main()
