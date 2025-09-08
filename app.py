import streamlit as st
import pandas as pd
import numpy as np
import os, re, json, uuid, hashlib
import altair as alt
from datetime import date, timedelta, datetime
from calendar import monthrange
from urllib.parse import quote

# ==============================  CONFIG  ==============================
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# ==============================  UTILITIES  ==============================
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    base_cols = [
        'paye','nom_client','sms_envoye','post_depart_envoye','plateforme','telephone','email',
        'date_arrivee','date_depart','nuitees','prix_brut','prix_net','commissions',
        'frais_cb','menage','taxes_sejour','res_id','ical_uid','AAAA','MM'
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=base_cols)
    df = df.copy()

    # Dates
    for col in ['date_arrivee','date_depart']:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
        else:
            df[col] = pd.NaT

    # Booléens
    for col in ['paye','sms_envoye','post_depart_envoye']:
        if col not in df.columns:
            df[col] = False
        df[col] = df[col].fillna(False).astype(bool)

    # Numériques
    for col in ['prix_brut','prix_net','commissions','frais_cb','menage','taxes_sejour','nuitees']:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0)

    # ID internes
    if 'res_id' not in df.columns:
        df['res_id'] = None
    if 'ical_uid' not in df.columns:
        df['ical_uid'] = None

    if 'date_arrivee' in df.columns:
        df['AAAA'] = pd.to_datetime(df['date_arrivee'], errors='coerce').dt.year
        df['MM']   = pd.to_datetime(df['date_arrivee'], errors='coerce').dt.month

    return df

def sauvegarder_donnees(df, file_path=CSV_RESERVATIONS):
    try:
        df_to_save = ensure_schema(df)
        df_to_save.to_csv(file_path, sep=";", index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur sauvegarde: {e}")
        return False

@st.cache_data
def charger_donnees():
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=";")
    except Exception:
        df = pd.DataFrame()
    df = ensure_schema(df)

    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";")
        palette = dict(zip(df_pal['plateforme'], df_pal['couleur']))
    except Exception:
        palette = DEFAULT_PALETTE.copy()

    return df, palette

def build_stable_uid(row):
    base = str(row.get('res_id') or '') + str(row.get('nom_client') or '') + str(row.get('telephone') or '')
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def _format_phone_e164(phone: str) -> str:
    if not phone: return ""
    digits = re.sub(r"\D","",str(phone))
    if digits.startswith("33"):
        return "+"+digits
    if digits.startswith("0"):
        return "+33"+digits[1:]
    return "+"+digits

# ==============================  STYLE  ==============================
def apply_modern_style(mode="dark"):
    st.markdown(
        f"""
        <style>
        body {{
            background-color: {"#111" if mode=="dark" else "#fafafa"};
            color: {"#eee" if mode=="dark" else "#111"};
        }}
        .stSidebar {{ background-color: {"#222" if mode=="dark" else "#f2f2f2"}; }}
        .glass {{
            background: rgba(255,255,255,0.06);
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 1rem;
        }}
        </style>
        """,
        unsafe_allow_html=True
    )

def card(title, content):
    st.markdown(f"<div class='glass'><h4>{title}</h4><p>{content}</p></div>", unsafe_allow_html=True)

# ==============================  VUES ==============================
def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty:
        st.info("Aucune réservation.")
        return
    annees = ["Toutes"] + sorted(df['AAAA'].dropna().astype(int).unique(), reverse=True).tolist()
    annee_sel = st.sidebar.selectbox("Année", annees, index=0)
    mois_opts = ["Tous"] + list(range(1,13))
    mois_sel = st.sidebar.selectbox("Mois", mois_opts, index=0)
    plats = ["Toutes"] + sorted(df['plateforme'].dropna().unique())
    plat_sel = st.sidebar.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    if annee_sel!="Toutes":
        data = data[data['AAAA']==int(annee_sel)]
    if mois_sel!="Tous":
        data = data[data['MM']==int(mois_sel)]
    if plat_sel!="Toutes":
        data = data[data['plateforme']==plat_sel]

    st.dataframe(data, use_container_width=True)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une réservation")
    with st.form("form_add", clear_on_submit=True):
        nom = st.text_input("Nom client")
        tel = st.text_input("Téléphone")
        arr = st.date_input("Arrivée", date.today())
        dep = st.date_input("Départ", date.today()+timedelta(days=1))
        plat = st.selectbox("Plateforme", list(palette.keys()))
        brut = st.number_input("Prix brut", min_value=0.0, step=0.01)
        commissions = st.number_input("Commissions", min_value=0.0, step=0.01)
        paye = st.checkbox("Payé")
        if st.form_submit_button("Ajouter"):
            nuitees = (dep-arr).days
            new = pd.DataFrame([{
                'nom_client':nom,'telephone':tel,'date_arrivee':arr,'date_depart':dep,
                'plateforme':plat,'prix_brut':brut,'commissions':commissions,
                'paye':paye,'nuitees':nuitees
            }])
            df2 = pd.concat([df,new],ignore_index=True)
            df2 = ensure_schema(df2)
            if sauvegarder_donnees(df2):
                st.success("Ajoutée ✅")
                st.rerun()

# (… tu rajoutes ici tes autres vues : modifier, plateformes, calendrier, rapport, sms, etc …)

# ==============================  MAIN  ==============================
def main():
    apply_modern_style()
    df, palette = charger_donnees()

    st.title("✨ Villa Tobias — Gestion des Réservations")
    st.sidebar.title("🧭 Navigation")

    pages = {
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        # "✏️ Modifier / Supprimer": vue_modifier,
        # "🎨 Plateformes": vue_plateformes,
        # "📅 Calendrier": vue_calendrier,
        # "📊 Rapport": vue_rapport,
        # "👥 Clients": vue_clients,
        # "✉️ SMS": vue_sms,
        # "📆 Export ICS": vue_export_ics,
        # "🔗 Flux ICS": vue_flux_ics,
        # "📝 Google Sheet": vue_google_sheet,
    }
    choix = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choix](df, palette)

if __name__ == "__main__":
    main()