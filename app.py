# app.py — Villa Tobias (COMPLET)
# - Réservations : cases à cocher Payé / SMS envoyé (éditables + sauvegarde) + email
# - SMS : n'affiche que les clients "non cochés" (sms_envoye = False), nettoyage tél, debug, marquage envoyé
#         + Lien Google Form PRÉREMPLI (nom, téléphone, email, arrivée, départ)
# - Rapport : métrique au choix, année/plateformes, barres groupées, empilées, courbes
#             + Total mensuel optionnel + Cumuler (YTD) + Moyenne par nuitée
#             + Export agrégé sans None/NaN + option "Masquer les zéros"
# - Export ICS (Google Calendar) :
#   * UID stables (v5) basés sur res_id + nom + téléphone
#   * Toggle "Créer et sauvegarder les UID manquants"
#   * OPTION B : Toggle "Ignorer les filtres et créer pour toute la base"
# - Google Form/Sheet (Option 2) :
#   * Formulaire intégré PRÉREMPLI pour la réservation choisie
#   * Feuille intégrée (iframe)
#   * Réponses (CSV publié)

import streamlit as st
import pandas as pd
import numpy as np
import os
import calendar
from datetime import date, timedelta, datetime
from urllib.parse import quote, urlencode, quote_plus
import altair as alt
import uuid, re, unicodedata  # pour res_id/UID stables

# --- Configuration des Fichiers ---
CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv"

# --- Google Form / Sheet (fournis) ---
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pubhtml?gid=1915058425&single=true"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?gid=1915058425&single=true&output=csv"

# --- Google Form prefill (IDs extraits du lien prérempli) ---
FORM_ENTRY_NOM = "entry.937556468"
FORM_ENTRY_TEL = "entry.702324920"
FORM_ENTRY_EMAIL = "entry.1712365042"      # optionnel si pas d'email en base
FORM_ENTRY_ARRIVEE = "entry.1099006415"
FORM_ENTRY_DEPART = "entry.2013910918"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = {"Booking": "#1e90ff", "Airbnb": "#e74c3c", "Autre": "#f59e0b"}

# ============================== CORE DATA FUNCTIONS ==============================
@st.cache_data
def charger_donnees_csv():
    df = pd.DataFrame()
    palette = DEFAULT_PALETTE.copy()
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=';')
        df.columns = df.columns.str.strip()
    except FileNotFoundError:
        st.warning(f"Fichier '{CSV_RESERVATIONS}' introuvable.")
    except Exception as e:
        st.error(f"Erreur de lecture de {CSV_RESERVATIONS}: {e}")
    try:
        df_palette = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        palette = dict(zip(df_palette['plateforme'], df_palette['couleur']))
    except:
        pass
    df = ensure_schema(df)
    return df, palette

def sauvegarder_donnees_csv(df, file_path=CSV_RESERVATIONS):
    try:
        df_to_save = df.copy()
        colonnes_a_sauvegarder = [col for col in BASE_COLS if col in df_to_save.columns]
        df_to_save = df_to_save[colonnes_a_sauvegarder]
        for col in ['date_arrivee', 'date_depart']:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime('%d/%m/%Y')
        df_to_save.to_csv(file_path, sep=';', index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ==============================  SCHEMA & DATA VALIDATION  ==============================
BASE_COLS = [
    'paye', 'nom_client', 'email', 'sms_envoye', 'plateforme', 'telephone', 'date_arrivee',
    'date_depart', 'nuitees', 'prix_brut', 'commissions', 'frais_cb',
    'prix_net', 'menage', 'taxes_sejour', 'base', 'charges', '%',
    'AAAA', 'MM', 'res_id', 'ical_uid'
]

def _to_bool_series(s):
    if s.dtype == 'object':
        return (s.astype(str).str.strip().str.upper().isin(['OUI','VRAI','TRUE','1','YES','Y']))
    return s.fillna(False).astype(bool)

def ensure_schema(df):
    if df.empty:
        out = pd.DataFrame(columns=BASE_COLS)
        out['paye'] = False
        out['sms_envoye'] = False
        return out

    df_res = df.copy()
    rename_map = {'Payé':'paye','Client':'nom_client','Plateforme':'plateforme',
                  'Arrivée':'date_arrivee','Départ':'date_depart','Nuits':'nuitees','Brut (€)':'prix_brut','Email':'email'}
    df_res.rename(columns=rename_map, inplace=True)

    for col in BASE_COLS:
        if col not in df_res.columns:
            df_res[col] = None

    for col in ["date_arrivee","date_depart"]:
        df_res[col] = pd.to_datetime(df_res[col], dayfirst=True, errors='coerce')
    mask_dates = pd.notna(df_res["date_arrivee"]) & pd.notna(df_res["date_depart"])
    df_res.loc[mask_dates,"nuitees"] = (df_res.loc[mask_dates,"date_depart"] - df_res.loc[mask_dates,"date_arrivee"]).dt.days
    for col in ["date_arrivee","date_depart"]:
        df_res[col] = df_res[col].dt.date

    df_res['paye'] = _to_bool_series(df_res['paye']).fillna(False).astype(bool)
    df_res['sms_envoye'] = _to_bool_series(df_res['sms_envoye']).fillna(False).astype(bool)

    for col in ['prix_brut','commissions','frais_cb','menage','taxes_sejour']:
        if df_res[col].dtype == 'object':
            df_res[col] = (df_res[col].astype(str)
                           .str.replace('€','',regex=False)
                           .str.replace(',','.',regex=False)
                           .str.replace(' ','',regex=False)
                           .str.strip())
        df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)

    df_res['prix_net'] = df_res['prix_brut'] - df_res['commissions'] - df_res['frais_cb']
    df_res['charges'] = df_res['prix_brut'] - df_res['prix_net']
    df_res['base'] = df_res['prix_net'] - df_res['menage'] - df_res['taxes_sejour']
    with np.errstate(divide='ignore', invalid='ignore'):
        df_res['%'] = np.where(df_res['prix_brut'] > 0, (df_res['charges'] / df_res['prix_brut'] * 100), 0)

    date_arrivee_dt = pd.to_datetime(df_res["date_arrivee"], errors='coerce')
    df_res.loc[pd.notna(date_arrivee_dt),'AAAA'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.year
    df_res.loc[pd.notna(date_arrivee_dt),'MM'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.month

    return df_res

# ============================== UID STABLE (res_id + nom + téléphone) ==============================
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://villa-tobias.fr/reservations")
PROPERTY_ID = "villa-tobias"

def _canonize_text(s: str) -> str:
    if s is None: return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize('NFKD', s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", s)

def _canonize_phone(s: str) -> str:
    if s is None: return ""
    return re.sub(r"\D", "", str(s))

def build_stable_uid(row) -> str:
    res_id = str(row.get('res_id') or "").strip()
    canonical = "|".join([
        PROPERTY_ID,
        res_id,
        _canonize_text(row.get('nom_client', '')),
        _canonize_phone(row.get('telephone', '')),
    ])
    return str(uuid.uuid5(NAMESPACE, canonical))

# ============================== HELPERS ==============================
def is_dark_color(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        r,g,b = (int(hex_color[i:i+2],16) for i in (0,2,4))
        luminance = (0.299*r + 0.587*g + 0.114*b) / 255
        return luminance < 0.5
    except (ValueError, TypeError):
        return True

def kpi_chips(df, title="Indicateurs Clés"):
    st.subheader(title)
    if df.empty:
        st.warning("Pas de données à afficher pour cette sélection.")
        return
    totals = {
        "Total Brut": df["prix_brut"].sum(),
        "Total Net": df["prix_net"].sum(),
        "Total Commissions": df["commissions"].sum(),
        "Total Frais CB": df["frais_cb"].sum(),
        "Total Ménage": df["menage"].sum(),
        "Total Base": df["base"].sum(),
        "Nuitées": df["nuitees"].sum(),
    }
    html = f"""
    <style>
        .chips-container {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; }}
        .chip {{ background-color:#333; padding:8px 12px; border-radius:16px; font-size:.9rem; text-align:center; }}
        .chip-label {{ display:block; font-size:.8rem; color:#aaa; margin-bottom:4px; }}
        .chip-value {{ font-weight:bold; color:#eee; }}
    </style>
    <div class="chips-container">
        {"".join([f'<div class="chip"><span class="chip-label">{label}</span><span class="chip-value">{value:,.2f} €</span></div>'
                   if "Nuitées" not in label else f'<div class="chip"><span class="chip-label">{label}</span><span class="chip-value">{int(value)}</span></div>'
                   for label, value in totals.items()])}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ------- Helper: URL Google Form préremplie -------
def form_prefill_url(nom=None, tel=None, email=None, date_arrivee=None, date_depart=None):
    """
    Construit l'URL du Google Form préremplie avec les champs disponibles.
    - date_arrivee / date_depart : objets date OU chaînes 'YYYY-MM-DD'
    """
    base = GOOGLE_FORM_URL.split("?")[0]  # garde /viewform sans params

    def to_ymd(d):
        if d is None or (isinstance(d, float) and np.isnan(d)):
            return ""
        if isinstance(d, str):
            return d
        if isinstance(d, (pd.Timestamp, datetime)):
            d = d.date()
        if isinstance(d, date):
            return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
        return ""

    params = {}
    if nom:   params[FORM_ENTRY_NOM] = str(nom)
    if tel:   params[FORM_ENTRY_TEL] = str(tel)
    if email: params[FORM_ENTRY_EMAIL] = str(email)
    if date_arrivee: params[FORM_ENTRY_ARRIVEE] = to_ymd(date_arrivee)
    if date_depart:  params[FORM_ENTRY_DEPART]  = to_ymd(date_depart)

    if not params:
        return base  # formulaire vierge
    return f"{base}?{urlencode(params, quote_via=quote_plus)}"

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation trouvée.")
        return
    df_dates_valides = df.dropna(subset=['AAAA', 'MM'])

    c1, c2, c3 = st.columns(3)
    annees = ["Toutes"] + sorted(df_dates_valides['AAAA'].astype(int).unique(), reverse=True)
    annee_selectionnee = c1.selectbox("Filtrer par Année", annees)
    mois_options = ["Tous"] + list(range(1, 13))
    mois_selectionne = c2.selectbox("Filtrer par Mois", mois_options)
    plateformes_options = ["Toutes"] + sorted(df_dates_valides['plateforme'].dropna().unique())
    plateforme_selectionnee = c3.selectbox("Filtrer par Plateforme", plateformes_options)

    data_filtree = df_dates_valides.copy()
    if annee_selectionnee != "Toutes":
        data_filtree = data_filtree[data_filtree['AAAA'] == annee_selectionnee]
    if mois_selectionne != "Tous":
        data_filtree = data_filtree[data_filtree['MM'] == mois_selectionne]
    if plateforme_selectionnee != "Toutes":
        data_filtree = data_filtree[data_filtree['plateforme'] == plateforme_selectionnee]

    kpi_chips(data_filtree, title="Totaux pour la Sélection")
    st.markdown("---")

    df_sorted = data_filtree.sort_values(by="date_arrivee", ascending=False, na_position='last').copy()
    df_sorted["_rowid"] = df_sorted.index
    for bcol in ["paye","sms_envoye"]:
        if bcol in df_sorted.columns:
            df_sorted[bcol] = _to_bool_series(df_sorted[bcol]).fillna(False).astype(bool)

    column_config = {
        "paye": st.column_config.CheckboxColumn("Payé"),
        "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
        "email": st.column_config.TextColumn("Email"),
        "nuitees": st.column_config.NumberColumn("Nuits", format="%d"),
        "prix_brut": st.column_config.NumberColumn("Prix Brut", format="%.2f €"),
        "commissions": st.column_config.NumberColumn("Commissions", format="%.2f €"),
        "prix_net": st.column_config.NumberColumn("Prix Net", format="%.2f €"),
        "base": st.column_config.NumberColumn("Base", format="%.2f €"),
        "charges": st.column_config.NumberColumn("Charges", format="%.2f €"),
        "%": st.column_config.NumberColumn("% Charges", format="%.2f %%"),
        "AAAA": st.column_config.NumberColumn("Année", format="%d"),
        "MM": st.column_config.NumberColumn("Mois", format="%d"),
        "date_arrivee": st.column_config.DateColumn("Arrivée", format="DD/MM/YYYY"),
        "date_depart": st.column_config.DateColumn("Départ", format="DD/MM/YYYY"),
        "_rowid": st.column_config.TextColumn("", help="ID interne (index)", disabled=True),
        "res_id": st.column_config.TextColumn("res_id", help="Identifiant persistant"),
        "ical_uid": st.column_config.TextColumn("ical_uid", help="UID ICS (ne pas modifier)"),
    }
    col_order = [c for c in df_sorted.columns if c != "_rowid"] + ["_rowid"]

    # --- 👇 CASTS pour compatibilité data_editor ---
    df_edit = df_sorted.copy()

    # Dates en datetime64[ns] pour DateColumn
    for c in ['date_arrivee', 'date_depart']:
        df_edit[c] = pd.to_datetime(df_edit[c], errors='coerce')

    # Booléens pour CheckboxColumn
    for bcol in ['paye', 'sms_envoye']:
        if bcol in df_edit.columns:
            df_edit[bcol] = df_edit[bcol].fillna(False).astype(bool)

    # Entiers "souples" (acceptent NaN) pour AAAA/MM/nuitees
    for c in ['AAAA', 'MM', 'nuitees']:
        if c in df_edit.columns:
            df_edit[c] = pd.to_numeric(df_edit[c], errors='coerce').astype('Int64')

    # Numériques en float
    for c in ['prix_brut', 'commissions', 'frais_cb', 'prix_net', 'menage', 'taxes_sejour', 'base', 'charges', '%']:
        if c in df_edit.columns:
            df_edit[c] = pd.to_numeric(df_edit[c], errors='coerce')

    # 🔑 Correction : forcer _rowid en str pour TextColumn
    df_edit["_rowid"] = df_edit["_rowid"].astype(str)

    # --- Appel éditeur sur df_edit ---
    edited = st.data_editor(
        df_edit,
        column_config=column_config,
        column_order=col_order,
        use_container_width=True,
        num_rows="fixed",
        hide_index=True,
        key="editor_reservations"
    )

    if st.button("💾 Enregistrer les modifications"):
        try:
            # booleans
            for bcol in ["paye","sms_envoye"]:
                if bcol in edited.columns:
                    edited[bcol] = edited[bcol].fillna(False).astype(bool)

            for _, row in edited.iterrows():
                # _rowid est str -> repasser en int
                rid_str = row["_rowid"]
                if pd.isna(rid_str):
                    continue
                try:
                    rid = int(rid_str)
                except Exception:
                    continue

                # simples
                df.loc[rid, "paye"] = bool(row.get("paye", False))
                df.loc[rid, "sms_envoye"] = bool(row.get("sms_envoye", False))
                if "email" in row:
                    df.loc[rid, "email"] = row["email"]
                if isinstance(row.get("res_id"), str) and row["res_id"].strip() != "":
                    df.loc[rid, "res_id"] = row["res_id"].strip()
                if isinstance(row.get("ical_uid"), str) and row["ical_uid"].strip() != "":
                    df.loc[rid, "ical_uid"] = row["ical_uid"].strip()

                # dates : Timestamp -> date
                for c in ["date_arrivee", "date_depart"]:
                    val = row.get(c)
                    if pd.isna(val):
                        df.loc[rid, c] = pd.NaT
                    else:
                        if isinstance(val, (pd.Timestamp, datetime)):
                            df.loc[rid, c] = val.date()
                        else:
                            df.loc[rid, c] = val  # déjà un date

            df_final = ensure_schema(df)
            if sauvegarder_donnees_csv(df_final):
                st.success("Modifications enregistrées ✅")
                st.rerun()
        except Exception as e:
            st.error(f"Impossible de sauvegarder : {e}")

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une Réservation")
    with st.form("form_ajout", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom_client = st.text_input("**Nom du Client**")
            telephone = st.text_input("Téléphone")
            email = st.text_input("Email (optionnel)")
            date_arrivee = st.date_input("**Date d'arrivée**", date.today())
            date_depart = st.date_input("**Date de départ**", date.today() + timedelta(days=1))
        with c2:
            plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()))
            prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, step=0.01, format="%.2f")
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01, format="%.2f")
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01, format="%.2f")
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01, format="%.2f")
            taxes_sejour = st.number_input("Taxes Séjour (€)", min_value=0.0, step=0.01, format="%.2f")
        paye = st.checkbox("Payé", False)

        submitted = st.form_submit_button("✅ Ajouter la réservation")
        if submitted:
            if not nom_client or date_depart <= date_arrivee:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nouvelle_ligne = pd.DataFrame([{
                    'res_id': str(uuid.uuid4()),
                    'nom_client': nom_client, 'telephone': telephone, 'email': email,
                    'date_arrivee': date_arrivee, 'date_depart': date_depart,
                    'plateforme': plateforme, 'prix_brut': prix_brut, 'commissions': commissions,
                    'frais_cb': frais_cb, 'menage': menage, 'taxes_sejour': taxes_sejour,
                    'paye': paye, 'sms_envoye': False
                }])
                df_a_jour = pd.concat([df, nouvelle_ligne], ignore_index=True)
                df_a_jour = ensure_schema(df_a_jour)
                if sauvegarder_donnees_csv(df_a_jour):
                    st.success(f"Réservation pour {nom_client} ajoutée.")
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
        original_index = df_sorted.loc[idx_selection, 'index']
        resa_selectionnee = df.loc[original_index].copy()
        with st.form(f"form_modif_{original_index}"):
            c1, c2 = st.columns(2)
            with c1:
                nom_client = st.text_input("**Nom du Client**", value=resa_selectionnee.get('nom_client', ''))
                telephone = st.text_input("Téléphone", value=resa_selectionnee.get('telephone', ''))
                email = st.text_input("Email (optionnel)", value=resa_selectionnee.get('email', '') if 'email' in resa_selectionnee else '')
                date_arrivee = st.date_input("**Date d'arrivée**", value=resa_selectionnee.get('date_arrivee'))
                date_depart = st.date_input("**Date de départ**", value=resa_selectionnee.get('date_depart'))
            with c2:
                plateforme_options = list(palette.keys())
                current_plateforme = resa_selectionnee.get('plateforme')
                plateforme_index = plateforme_options.index(current_plateforme) if current_plateforme in plateforme_options else 0
                plateforme = st.selectbox("**Plateforme**", options=plateforme_options, index=plateforme_index)
                prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, value=resa_selectionnee.get('prix_brut', 0.0), step=0.01, format="%.2f")
                commissions = st.number_input("Commissions (€)", min_value=0.0, value=resa_selectionnee.get('commissions', 0.0), step=0.01, format="%.2f")
                paye = st.checkbox("Payé", value=bool(resa_selectionnee.get('paye', False)))
            btn_enregistrer, btn_supprimer = st.columns([.8, .2])
            if btn_enregistrer.form_submit_button("💾 Enregistrer"):
                updates = {
                    'nom_client': nom_client, 'telephone': telephone, 'email': email,
                    'date_arrivee': date_arrivee, 'date_depart': date_depart,
                    'plateforme': plateforme, 'prix_brut': prix_brut, 'commissions': commissions, 'paye': paye
                }
                for key, value in updates.items():
                    df.loc[original_index, key] = value
                df_final = ensure_schema(df)
                if sauvegarder_donnees_csv(df_final):
                    st.success("Modifications enregistrées !")
                    st.rerun()
            if btn_supprimer.form_submit_button("🗑️ Supprimer"):
                df_final = df.drop(index=original_index)
                if sauvegarder_donnees_csv(df_final):
                    st.warning("Réservation supprimée.")
                    st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Gestion des Plateformes")
    df_palette = pd.DataFrame(list(palette.items()), columns=['plateforme', 'couleur'])
    edited_df = st.data_editor(df_palette, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={"plateforme": "Plateforme", "couleur": st.column_config.TextColumn("Couleur (code hex)")})
    if st.button("💾 Enregistrer les modifications"):
        nouvelle_palette = dict(zip(edited_df['plateforme'], edited_df['couleur']))
        df_plateformes_save = pd.DataFrame(list(nouvelle_palette.items()), columns=['plateforme', 'couleur'])
        if sauvegarder_donnees_csv(df_plateformes_save, file_path=CSV_PLATEFORMES):
            st.success("Palette de couleurs mise à jour !")
            st.rerun()

def vue_calendrier(df, palette):
    st.header("📅 Calendrier des Réservations")
    df_dates_valides = df.dropna(subset=['date_arrivee','date_depart','AAAA'])
    if df_dates_valides.empty:
        st.info("Aucune réservation à afficher.")
        return
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
    st.markdown("""<style>.calendar-day{border:1px solid #444;min-height:120px;padding:5px;vertical-align:top}.calendar-day.outside-month{background-color:#2e2e2e}.calendar-date{font-weight:700;font-size:1.1em;margin-bottom:5px;text-align:right}.reservation-bar{padding:3px 6px;margin-bottom:3px;border-radius:5px;font-size:.9em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}</style>""", unsafe_allow_html=True)
    headers = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    st.write(f'<div style="display:grid;grid-template-columns:repeat(7,1fr);text-align:center;font-weight:700">{"".join(f"<div>{h}</div>" for h in headers)}</div>', unsafe_allow_html=True)
    for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                day_class = "outside-month" if day.month != selected_month else ""
                day_html = f"<div class='calendar-day {day_class}'><div class='calendar-date'>{day.day}</div>"
                for _, resa in df_dates_valides.iterrows():
                    if isinstance(resa['date_arrivee'], date) and isinstance(resa['date_depart'], date):
                        if resa['date_arrivee'] <= day < resa['date_depart']:
                            color = palette.get(resa['plateforme'], '#888')
                            text_color = "#FFF" if is_dark_color(color) else "#000"
                            day_html += f"<div class='reservation-bar' style='background-color:{color};color:{text_color}' title='{resa['nom_client']}'>{resa['nom_client']}</div>"
                day_html += "</div>"
                st.markdown(day_html, unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("Détails des réservations du mois")
    start_of_month = date(selected_year, selected_month, 1)
    end_of_month = date(selected_year, selected_month, calendar.monthrange(selected_year, selected_month)[1])
    reservations_du_mois = df_dates_valides[(df_dates_valides['date_arrivee'] <= end_of_month) & df_dates_valides['date_depart'].gt(start_of_month)].sort_values(by="date_arrivee").reset_index()
    if not reservations_du_mois.empty:
        options = {f"{row['nom_client']} ({row['date_arrivee'].strftime('%d/%m')})": idx for idx, row in reservations_du_mois.iterrows()}
        selection_str = st.selectbox("Voir les détails :", options=options.keys(), index=None, placeholder="Choisissez une réservation...")
        if selection_str:
            details = reservations_du_mois.loc[options[selection_str]]
            st.markdown(f"**Détails pour {details.get('nom_client')}**")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""- **Téléphone :** {details.get('telephone', 'N/A')}
- **Arrivée :** {details.get('date_arrivee').strftime('%d/%m/%Y') if pd.notna(details.get('date_arrivee')) else 'N/A'}
- **Départ :** {details.get('date_depart').strftime('%d/%m/%Y') if pd.notna(details.get('date_depart')) else 'N/A'}
- **Nuits :** {details.get('nuitees', 0):.0f}""")
            with col2:
                st.markdown(f"""- **Prix Net :** {details.get('prix_net', 0):.2f} €
- **Prix Brut :** {details.get('prix_brut', 0):.2f} €
- **Statut :** {"Payé" if details.get('paye', False) else "Non Payé"}""")
    else:
        st.info("Aucune réservation pour ce mois.")

# ---------------- Rapport ----------------
def _safe_div(num, den):
    return np.where(den > 0, num / den, np.nan)

def vue_rapport(df, palette):
    st.header("📊 Rapport de Performance")

    data = df.dropna(subset=['AAAA','MM','plateforme']).copy()
    if data.empty:
        st.info("Aucune donnée pour générer un rapport.")
        return

    c1, c2, c3 = st.columns([1,1,2])
    annees = sorted(data['AAAA'].astype(int).unique(), reverse=True)
    annee = c1.selectbox("Année", annees, index=0)

    plateformes = sorted(data['plateforme'].dropna().unique())
    plateformes_sel = c2.multiselect("Plateformes", plateformes, default=plateformes)

    metrics = {
        "Prix brut (€)": "prix_brut",
        "Prix net (€)": "prix_net",
        "Ménage (€)": "menage",
        "Commissions (€)": "commissions",
        "Frais CB (€)": "frais_cb",
        "Base (€)": "base",
        "Charges (€)": "charges",
        "Nuitées": "nuitees",
    }
    metric_label = c3.selectbox("Métrique", list(metrics.keys()), index=0)
    metric = metrics[metric_label]

    c4, c5, c6 = st.columns([1,1,1])
    chart_type = c4.selectbox("Type de graphique", ["Barres groupées", "Barres empilées (total mensuel)", "Courbes"], index=0)
    show_totals = c5.toggle("Afficher aussi le total mensuel", value=False)
    avg_per_night = c6.toggle("Moyenne par nuitée", value=False)
    c7 = st.columns(1)[0]
    cumulate = c7.toggle("Cumuler (YTD)", value=False)

    if avg_per_night and metric == "nuitees":
        st.info("ℹ️ La moyenne par nuitée n'est pas applicable à la métrique 'Nuitées'. Option ignorée.")
        avg_per_night = False

    data = data[(data['AAAA'].astype(int) == int(annee)) & (data['plateforme'].isin(plateformes_sel))].copy()
    if data.empty:
        st.warning("Aucune donnée pour les filtres sélectionnés.")
        return

    data['date_mois'] = pd.to_datetime(dict(year=data['AAAA'].astype(int), month=data['MM'].astype(int), day=1))
    grp = (data.groupby(['plateforme','date_mois'], as_index=False)
               .agg({metric:'sum', 'nuitees':'sum'}))

    all_months = pd.date_range(f"{annee}-01-01", f"{annee}-12-01", freq='MS')
    frames = []
    for p in plateformes_sel:
        g = grp[grp['plateforme']==p].set_index('date_mois').reindex(all_months).fillna({metric:0.0,'nuitees':0.0})
        g['plateforme'] = p
        g = g.reset_index().rename(columns={'index':'date_mois'})
        frames.append(g)
    grp_full = pd.concat(frames, ignore_index=True)

    if avg_per_night:
        if cumulate:
            grp_full = grp_full.sort_values(['plateforme','date_mois'])
            grp_full['num_cum'] = grp_full.groupby('plateforme')[metric].cumsum()
            grp_full['den_cum'] = grp_full.groupby('plateforme')['nuitees'].cumsum()
            grp_full['value'] = _safe_div(grp_full['num_cum'], grp_full['den_cum'])
            metric_label_plot = f"{metric_label} / nuit (cumul YTD)"
        else:
            grp_full['value'] = _safe_div(grp_full[metric], grp_full['nuitees'])
            metric_label_plot = f"{metric_label} / nuit"
    else:
        if cumulate:
            grp_full = grp_full.sort_values(['plateforme','date_mois'])
            grp_full['value'] = grp_full.groupby('plateforme')[metric].cumsum()
            metric_label_plot = f"{metric_label} (cumul YTD)"
        else:
            grp_full['value'] = grp_full[metric]
            metric_label_plot = metric_label

    color_map = {p: palette.get(p, '#888') for p in plateformes_sel}
    domain_sel = list(color_map.keys())
    range_sel = [color_map[p] for p in domain_sel]

    if avg_per_night and chart_type == "Barres empilées (total mensuel)":
        st.info("ℹ️ Les barres empilées ne sont pas pertinentes pour une moyenne. Affichage en barres groupées.")
        chart_type = "Barres groupées"

    base = alt.Chart(grp_full).encode(
        x=alt.X('yearmonth(date_mois):T', title='Mois'),
        color=alt.Color('plateforme:N', title="Plateforme", scale=alt.Scale(domain=domain_sel, range=range_sel)),
        tooltip=[
            alt.Tooltip('plateforme:N', title='Plateforme'),
            alt.Tooltip('yearmonth(date_mois):T', title='Mois'),
            alt.Tooltip('value:Q', title=metric_label_plot, format='.2f' if metric != 'nuitees' or avg_per_night else '.0f')
        ]
    )

    if chart_type == "Barres groupées":
        chart = base.mark_bar().encode(
            y=alt.Y('value:Q', title=metric_label_plot),
            xOffset=alt.X('plateforme:N', title=None),
        )
    elif chart_type == "Barres empilées (total mensuel)":
        chart = base.mark_bar().encode(
            y=alt.Y('value:Q', title=metric_label_plot, stack='zero'),
        )
    else:
        chart = base.mark_line(point=True).encode(
            y=alt.Y('value:Q', title=metric_label_plot),
        )

    st.altair_chart(chart.properties(height=420).interactive(), use_container_width=True)

    if show_totals:
        if avg_per_night:
            month_sums = (grp.groupby('date_mois', as_index=False)
                             .agg(num=(metric,'sum'), den=('nuitees','sum')))
            month_sums = month_sums.set_index('date_mois').reindex(all_months, fill_value=0).reset_index()
            if cumulate:
                month_sums['num_cum'] = month_sums['num'].cumsum()
                month_sums['den_cum'] = month_sums['den'].cumsum()
                month_sums['avg'] = _safe_div(month_sums['num_cum'], month_sums['den_cum'])
                ytitle = f"{metric_label} / nuit (cumul YTD - total)"
            else:
                month_sums['avg'] = _safe_div(month_sums['num'], month_sums['den'])
                ytitle = f"{metric_label} / nuit (total)"
            chart_tot = (alt.Chart(month_sums).mark_line(point=True).encode(
                x=alt.X('yearmonth(date_mois):T', title='Mois'),
                y=alt.Y('avg:Q', title=ytitle),
                tooltip=[alt.Tooltip('yearmonth(date_mois):T', title='Mois'),
                         alt.Tooltip('avg:Q', title='Moyenne / nuit', format='.2f')]
            ))
            st.altair_chart(chart_tot.properties(height=320).interactive(), use_container_width=True)
        else:
            st.markdown("**Total mensuel (toutes plateformes)**")
            chart_tot = alt.Chart(grp_full).mark_bar().encode(
                x=alt.X('yearmonth(date_mois):T', title='Mois'),
                y=alt.Y('value:Q', title=metric_label_plot, stack='zero'),
                color=alt.Color('plateforme:N', title="Plateforme", scale=alt.Scale(domain=domain_sel, range=range_sel)),
                tooltip=[alt.Tooltip('plateforme:N', title='Plateforme'),
                         alt.Tooltip('yearmonth(date_mois):T', title='Mois'),
                         alt.Tooltip('value:Q', title=metric_label_plot, format='.2f' if metric != 'nuitees' else '.0f')]
            )
            st.altair_chart(chart_tot.properties(height=320).interactive(), use_container_width=True)

    with st.expander("Afficher les données agrégées et exporter"):
        display = grp_full.copy()
        display['Année'] = display['date_mois'].dt.year
        display['Mois'] = display['date_mois'].dt.month
        out = display[['Année','Mois','plateforme','value']].sort_values(['Année','Mois','plateforme'])
        out = out[out['value'].notna()]
        out = out[out['plateforme'].notna() & (out['plateforme'].astype(str).str.strip() != "")]
        hide_zeros = st.toggle("Masquer les zéros", value=True)
        if hide_zeros:
            out = out[np.abs(out['value']) > 1e-9]
        st.dataframe(out.rename(columns={'plateforme':'Plateforme','value':metric_label_plot}), use_container_width=True)
        csv = out.to_csv(index=False, sep=';').encode('utf-8')
        fname_metric = (metric_label_plot.replace(' ', '_').replace('/', '-')).lower()
        st.download_button("⬇️ Télécharger CSV agrégé", data=csv,
                           file_name=f"rapport_{annee}_{fname_metric}.csv", mime="text/csv")

def vue_liste_clients(df):
    st.header("👥 Liste des Clients")
    if df.empty:
        st.info("Aucun client.")
        return
    clients = df[['nom_client','telephone','email','plateforme']].dropna(subset=['nom_client']).drop_duplicates().sort_values('nom_client')
    st.dataframe(clients, use_container_width=True)

def vue_sms(df):
    st.header("✉️ Générateur de SMS")
    if 'sms_envoye' in df.columns:
        df['sms_envoye'] = _to_bool_series(df['sms_envoye']).fillna(False).astype(bool)
    else:
        df['sms_envoye'] = False
    df_tel = df.dropna(subset=['telephone','nom_client','date_arrivee']).copy()
    df_tel['tel_clean'] = df_tel['telephone'].astype(str).str.replace(r'\D','',regex=True).str.lstrip('0')
    mask_valid_phone = df_tel['tel_clean'].str.len().between(9,15)
    df_tel = df_tel[~df_tel['sms_envoye'] & mask_valid_phone].copy()
    df_tel["_rowid"] = df_tel.index
    with st.expander("🔎 Debug SMS (pourquoi certains clients n'apparaissent pas ?)"):
        total = len(df)
        manquants = len(df) - len(df.dropna(subset=['telephone','nom_client','date_arrivee']))
        df_tmp = df.dropna(subset=['telephone','nom_client','date_arrivee']).copy()
        df_tmp['tel_clean'] = df_tmp['telephone'].astype(str).str.replace(r'\D','',regex=True).str.lstrip('0')
        hors_plage = (~df_tmp['tel_clean'].str.len().between(9,15)).sum()
        deja_coches = df_tmp['sms_envoye'].sum() if 'sms_envoye' in df_tmp.columns else 0
        st.write(f"- Total lignes : {total}")
        st.write(f"- Manquants (tel/nom/date) : {manquants}")
        st.write(f"- Tél. hors plage (après nettoyage) : {hors_plage}")
        st.write(f"- Déjà cochés 'SMS envoyé' : {int(deja_coches)}")
        st.dataframe(df_tel[['nom_client','telephone','email','tel_clean','sms_envoye','date_arrivee']].head(30), use_container_width=True)
    if df_tel.empty:
        st.success("🎉 Aucun SMS en attente : tous les clients sont cochés 'SMS envoyé' ou numéros invalides.")
        return
    df_sorted = df_tel.sort_values(by="date_arrivee", ascending=False).reset_index(drop=True)
    options_resa = [f"{idx}: {row['nom_client']} ({row['telephone']})" for idx, row in df_sorted.iterrows() if pd.notna(row['date_arrivee'])]
    selection = st.selectbox("Sélectionnez un client (SMS non envoyé)", options=options_resa, index=None)
    if selection:
        idx = int(selection.split(":")[0])
        resa = df_sorted.loc[idx]
        original_rowid = resa["_rowid"]

        # 🔗 Lien Google Form PRÉREMPLI
        email_val = resa.get('email') if 'email' in df_tel.columns else None
        prefill_link = form_prefill_url(
            nom         = resa.get('nom_client'),
            tel         = resa.get('telephone'),
            email       = email_val,
            date_arrivee= resa.get('date_arrivee'),
            date_depart = resa.get('date_depart')
        )

        message_body = f"""VILLA TOBIAS
Plateforme : {resa.get('plateforme', 'N/A')}
Arrivée : {resa.get('date_arrivee').strftime('%d/%m/%Y')} Départ : {resa.get('date_depart').strftime('%d/%m/%Y')} Nuitées : {resa.get('nuitees', 0):.0f}

Bonjour {resa.get('nom_client')}
Téléphone : {resa.get('telephone')}

Bienvenue chez nous !

Nous sommes ravis de vous acceuillir bientot a Nice. Aussi afin d'organiser au mieux votre receptionmerci de nous indiquer votre heure d'arrivee. 

Sachez qu'une place de parking vous est allouee en cas de besoin. 

Le check-in se fait a partir de 14:00 h et le check-out avant 11:00 h. 

Vous trouverez des consignes a bagages dans chaque quartier a Nice. 

Nous vous souhaitons un excellent voyage et nous nous rejouissons de vous rencontrer tres bientot. 

Welcome to our home ! 

We are delighted to welcome you soon to Nice. In order to organize your reception as best as possibleplease let us know your arrival time. 

Please note that a parking space is available if needed. 

Check-in is from 2:00 p.m. and check-out is before 11:00 a.m. 

You will find luggage storage facilities in every neighborhood in Nice. 

We wish you a wonderful trip and look forward to meeting you very soon. 

Annick & Charley 

Merci de remplir la fiche d'arrivee / Please fill out the arrival form : 
{prefill_link}"""

        message_area = st.text_area("Message à envoyer", value=message_body, height=420)
        encoded_message = quote(message_area)
        sms_link = f"sms:{resa['telephone']}?&body={encoded_message}"
        st.link_button("📲 Envoyer via Smartphone", sms_link)

        if st.button("✅ Marquer ce client comme 'SMS envoyé'"):
            try:
                df.loc[original_rowid,'sms_envoye'] = True
                df_final = ensure_schema(df)
                if sauvegarder_donnees_csv(df_final):
                    st.success("Marqué 'SMS envoyé' ✅")
                    st.rerun()
            except Exception as e:
                st.error(f"Impossible de marquer comme envoyé : {e}")

# ==============================  EXPORT ICS (Google Calendar) ==============================
def _fmt_ics_date(d: date) -> str:
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"

def _escape_text(s: str) -> str:
    if s is None: return ""
    return str(s).replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")

    st.info("Cet export génère un fichier **.ics** à **importer** dans Google Calendar "
            "(Paramètres ➜ Importer & Exporter ➜ Importer). "
            "Pour une **synchro auto**, il faut publier une **URL ICS** ou implémenter l’**API Google Calendar** (OAuth).")

    base_all = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if base_all.empty:
        st.warning("Aucune réservation avec dates valides.")
        return

    col1, col2 = st.columns(2)
    years = sorted(base_all['date_arrivee'].apply(lambda d: d.year).unique())
    annee = col1.selectbox("Filtrer Année (arrivée)", years, index=len(years)-1)
    plateformes = sorted(base_all['plateforme'].dropna().unique())
    plats = col2.multiselect("Plateformes", plateformes, default=plateformes)

    c3, c4, c5 = st.columns(3)
    create_missing_uid = c3.toggle("Créer et sauvegarder les UID manquants", value=True)
    include_paid = c4.toggle("Inclure les réservations non payées", value=True)
    include_sms_sent = c5.toggle("Inclure celles déjà 'SMS envoyé'", value=True)

    # OPTION B : ignorer les filtres pour la création/persistance
    apply_to_all = st.toggle("Ignorer les filtres et créer pour toute la base", value=False)

    # df_filtre = réservé au contenu du fichier ICS
    df_filtre = base_all[(base_all['date_arrivee'].apply(lambda d: d.year) == annee) & (base_all['plateforme'].isin(plats))].copy()
    if not include_paid:
        df_filtre = df_filtre[df_filtre['paye'] == True]
    if not include_sms_sent:
        df_filtre = df_filtre[df_filtre['sms_envoye'] == False]
    if df_filtre.empty:
        st.warning("Rien à exporter avec ces filtres.")

    # Lignes cibles pour la génération/persistance des IDs
    df_to_gen = base_all.copy() if apply_to_all else df_filtre.copy()
    if df_to_gen.empty:
        st.info("Aucune ligne cible pour la création/persistance des IDs selon les options actuelles.")
    else:
        # res_id
        missing_res_id = df_to_gen['res_id'].isna() | (df_to_gen['res_id'].astype(str).str.strip() == "")
        if create_missing_uid and missing_res_id.any():
            df_to_gen.loc[missing_res_id, 'res_id'] = [str(uuid.uuid4()) for _ in range(int(missing_res_id.sum()))]
            try:
                df.loc[df_to_gen.index, 'res_id'] = df_to_gen['res_id']
                if sauvegarder_donnees_csv(df):
                    st.success(f"ID internes (res_id) créés pour {int(missing_res_id.sum())} réservation(s).")
            except Exception as e:
                st.error(f"Impossible de sauvegarder les ID internes : {e}")

        # ical_uid (v5 sur res_id + nom + téléphone)
        missing_uid_mask = df_to_gen['ical_uid'].isna() | (df_to_gen['ical_uid'].astype(str).str.strip() == "")
        if missing_uid_mask.any():
            df_to_gen.loc[missing_uid_mask, 'ical_uid'] = df_to_gen[missing_uid_mask].apply(build_stable_uid, axis=1)
        if create_missing_uid and missing_uid_mask.any():
            try:
                df.loc[df_to_gen.index, 'ical_uid'] = df_to_gen['ical_uid']
                if sauvegarder_donnees_csv(df):
                    st.success(f"UID (ical_uid) créés et sauvegardés pour {int(missing_uid_mask.sum())} réservation(s).")
            except Exception as e:
                st.error(f"Impossible de sauvegarder les UID : {e}")

        # Propager dans df_filtre si besoin
        if not df_filtre.empty:
            inter = df_to_gen.index.intersection(df_filtre.index)
            df_filtre.loc[inter, 'res_id'] = df_to_gen.loc[inter, 'res_id']
            df_filtre.loc[inter, 'ical_uid'] = df_to_gen.loc[inter, 'ical_uid']

    # Construction ICS (sur df_filtre)
    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for _, r in df_filtre.iterrows():
        da = r['date_arrivee']
        dd = r['date_depart']
        if not isinstance(da, date) or not isinstance(dd, date):
            continue
        uid = r.get('ical_uid') or build_stable_uid(r)
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get('plateforme'):
            summary += f" ({r['plateforme']})"
        desc_parts = [
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Email: {r.get('email','')}",
            f"Plateforme: {r.get('plateforme','')}",
            f"Nuitées: {int(r.get('nuitees') or 0)}",
            f"Prix brut: {float(r.get('prix_brut') or 0):.2f} €",
            f"Prix net: {float(r.get('prix_net') or 0):.2f} €",
            f"Payé: {'Oui' if bool(r.get('paye')) else 'Non'}",
            f"res_id: {r.get('res_id','')}",
            f"UID: {uid}",
        ]
        desc = _escape_text("\n".join(desc_parts))
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt_ics_date(da)}",
            f"DTEND;VALUE=DATE:{_fmt_ics_date(dd)}",
            f"SUMMARY:{_escape_text(summary)}",
            f"DESCRIPTION:{desc}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    ics_content = "\r\n".join(lines) + "\r\n"

    st.download_button("📥 Télécharger le fichier ICS", data=ics_content.encode('utf-8'),
                       file_name=f"villa_tobias_{annee}.ics", mime="text/calendar")

    with st.expander("Aide : éviter les doublons dans Google Calendar"):
        st.markdown("""
- L’**import ICS** ajoute des événements (ne met pas à jour les imports passés).
- Avec des **UID** stables (`ical_uid`), un agenda **abonné à une URL ICS** peut reconnaître et mettre à jour.
- Pour une synchro directe (création/màj/suppression), utiliser l’**API Google Calendar** (OAuth).
        """)

# ==============================  GOOGLE SHEET / FORM (Option 2) ==============================
def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée — Google Form & Sheet")

    tab_form, tab_sheet, tab_csv = st.tabs(["Formulaire (intégré)", "Feuille intégrée", "Réponses (CSV)"])

    with tab_form:
        st.caption("Formulaire Google intégré (prérempli à partir d'une réservation).")
        df_ok = df.dropna(subset=['nom_client','telephone','date_arrivee']).copy()
        if df_ok.empty:
            st.info("Aucune réservation exploitable pour préremplir le formulaire.")
            st.components.v1.iframe(GOOGLE_FORM_URL, height=950, scrolling=True)
        else:
            df_ok = df_ok.sort_values('date_arrivee', ascending=False).reset_index()
            options = {i: f"{row['nom_client']} — arrivée {row['date_arrivee']}" for i, row in df_ok.iterrows()}
            choice = st.selectbox("Préremplir pour :", options=list(options.keys()),
                                  format_func=lambda i: options[i], index=0)
            sel = df_ok.loc[choice]
            email_val = sel.get('email') if 'email' in df_ok.columns else None
            url_prefill = form_prefill_url(
                nom = sel.get('nom_client'),
                tel = sel.get('telephone'),
                email = email_val,
                date_arrivee = sel.get('date_arrivee'),
                date_depart  = sel.get('date_depart')
            )
            st.write("Lien direct :", url_prefill)
            st.components.v1.iframe(url_prefill, height=950, scrolling=True)

    with tab_sheet:
        st.caption("Affichage intégré (lecture seule) de la feuille publiée.")
        st.components.v1.iframe(GOOGLE_SHEET_EMBED_URL, height=900, scrolling=True)

    with tab_csv:
        st.caption("Lecture directe via l’URL 'Publier sur le Web' (CSV).")
        try:
            reponses = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
            st.dataframe(reponses, use_container_width=True)
            st.download_button(
                "⬇️ Télécharger les réponses (CSV)",
                data=reponses.to_csv(index=False).encode("utf-8"),
                file_name="reponses_formulaire.csv",
                mime="text/csv"
            )
        except Exception as e:
            st.error(f"Impossible de charger les réponses : {e}")
            st.info("Vérifie que la feuille est bien 'Publiée sur le Web' au format CSV et accessible.")

def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button(label="Télécharger la sauvegarde (CSV)",
        data=df.to_csv(sep=';', index=False).encode('utf-8'),
        file_name=CSV_RESERVATIONS, mime='text/csv')
    uploaded_file = st.sidebar.file_uploader("Restaurer depuis un fichier CSV", type=['csv'])
    if uploaded_file is not None:
        if st.sidebar.button("Confirmer la restauration"):
            try:
                with open(CSV_RESERVATIONS, "wb") as f: f.write(uploaded_file.getvalue())
                st.cache_data.clear()
                st.success("Fichier restauré. L'application va se recharger.")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur lors de la restauration: {e}")

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df, palette = charger_donnees_csv()
    st.sidebar.title("🧭 Navigation")
    pages = {
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "👥 Liste des Clients": vue_liste_clients,
        "✉️ SMS": vue_sms,
        "📆 Export ICS (Google Calendar)": vue_export_ics,
        "📝 Fiche d'arrivée / Google Sheet": vue_google_sheet,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    page_function = pages[selection]
    if selection in ["➕ Ajouter","✏️ Modifier / Supprimer","🎨 Plateformes","📅 Calendrier","📊 Rapport","📆 Export ICS (Google Calendar)","📝 Fiche d'arrivée / Google Sheet"]:
        page_function(df, palette)
    else:
        page_function(df)
    admin_sidebar(df)

if __name__ == "__main__":
    main()
