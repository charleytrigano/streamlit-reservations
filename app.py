# app.py — Villa Tobias (COMPLET)
# - Réservations : cases à cocher Payé / SMS envoyé / Post-départ envoyé (éditables + sauvegarde) + email
# - SMS pré-arrivée : par défaut Arrivées de J+1 (iPhone/Android/WhatsApp), Copier, lien court formulaire
# - SMS post-départ : par défaut Départs du jour (individuel + groupé WhatsApp / iPhone / Android)
# - Google Form prérempli (nom, tél, email, arrivée, départ, plateforme, nuitées, res_id)
# - Rapport **MAXI** : KPI annuels (occupation, ADR, RevPAR, panier), tendances, mix plateformes, heatmap d’occupation, distributions, export CSV
# - Export ICS manuel : UID stables (v5)
# - 🔗 Flux ICS public (BETA) : URL à copier (endpoint ?feed=ics&token=...)
# - Google Form/Sheet : Form intégré (lien court), Feuille intégrée (lien court), lecture CSV

import streamlit as st
import pandas as pd
import numpy as np
import os
import calendar
from datetime import date, timedelta, datetime
from urllib.parse import quote, urlencode, quote_plus
import altair as alt
import uuid, re, unicodedata, json
import hashlib

# ==============================  FICHIERS  ==============================
CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES  = "reservations.xlsx - Plateformes.csv"

# ==============================  GOOGLE FORM / SHEET  ==============================
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
FORM_SHORT_URL = "https://urlr.me/kZuH94"  # lien court à partager (formulaire) — utilisé partout
GOOGLE_SHEET_EMBED_URL = "https://urlr.me/kZuH94"  # intégration
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?gid=1915058425&single=true&output=csv"

# IDs (préremplissage du form) — ceux que tu avais fournis
FORM_ENTRY_NOM        = "entry.937556468"
FORM_ENTRY_TEL        = "entry.702324920"
FORM_ENTRY_EMAIL      = "entry.1712365042"
FORM_ENTRY_ARRIVEE    = "entry.1099006415"
FORM_ENTRY_DEPART     = "entry.2013910918"
FORM_ENTRY_PLATEFORME = "entry.528935650"
FORM_ENTRY_NUITEES    = "entry.473651945"
FORM_ENTRY_RESID      = "entry.2071395456"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE  ==============================
DEFAULT_PALETTE = {"Booking": "#1e90ff", "Airbnb": "#e74c3c", "Autre": "#f59e0b"}

# ==============================  CORE DATA  ==============================
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

# ==============================  SCHEMA  ==============================
BASE_COLS = [
    'paye', 'nom_client', 'email', 'sms_envoye', 'post_depart_envoye', 'plateforme', 'telephone', 'date_arrivee',
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
        out['post_depart_envoye'] = False
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
    mask = pd.notna(df_res["date_arrivee"]) & pd.notna(df_res["date_depart"])
    df_res.loc[mask,"nuitees"] = (df_res.loc[mask,"date_depart"] - df_res.loc[mask,"date_arrivee"]).dt.days
    for col in ["date_arrivee","date_depart"]:
        df_res[col] = df_res[col].dt.date

    for b in ('paye','sms_envoye','post_depart_envoye'):
        df_res[b] = _to_bool_series(df_res[b]).fillna(False).astype(bool)

    for col in ['prix_brut','commissions','frais_cb','menage','taxes_sejour']:
        if df_res[col].dtype == 'object':
            df_res[col] = (df_res[col].astype(str)
                           .str.replace('€','',regex=False)
                           .str.replace(',','.',regex=False)
                           .str.replace(' ','',regex=False)
                           .str.strip())
        df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)

    df_res['prix_net'] = df_res['prix_brut'] - df_res['commissions'] - df_res['frais_cb']
    df_res['charges']  = df_res['prix_brut'] - df_res['prix_net']
    df_res['base']     = df_res['prix_net'] - df_res['menage'] - df_res['taxes_sejour']
    with np.errstate(divide='ignore', invalid='ignore'):
        df_res['%'] = np.where(df_res['prix_brut'] > 0, (df_res['charges'] / df_res['prix_brut'] * 100), 0)

    dt = pd.to_datetime(df_res["date_arrivee"], errors='coerce')
    df_res.loc[pd.notna(dt),'AAAA'] = dt[pd.notna(dt)].dt.year
    df_res.loc[pd.notna(dt),'MM']   = dt[pd.notna(dt)].dt.month
    return df_res

# ==============================  UID STABLE  ==============================
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
    canonical = "|".join([PROPERTY_ID, res_id, _canonize_text(row.get('nom_client','')), _canonize_phone(row.get('telephone',''))])
    return str(uuid.uuid5(NAMESPACE, canonical))

# ==============================  HELPERS GÉNÉRAUX  ==============================
def is_dark_color(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        r,g,b = (int(hex_color[i:i+2],16) for i in (0,2,4))
        return (0.299*r + 0.587*g + 0.114*b) / 255 < 0.5
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

def _ensure_res_id_on_row(df, idx):
    try:
        cur = str(df.at[idx, 'res_id']) if 'res_id' in df.columns else ""
    except Exception:
        cur = ""
    if (cur is None) or (str(cur).strip() == "") or (str(cur).lower() == "nan"):
        new_id = str(uuid.uuid4())
        df.at[idx, 'res_id'] = new_id
        try:
            sauvegarder_donnees_csv(ensure_schema(df))
        except Exception:
            pass
        return new_id
    return cur

def _null_like(v):
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    if isinstance(v, str) and v.strip().lower() in ("", "nan", "none"):
        return True
    return False

def _format_phone_e164(raw_phone: str) -> str:
    raw_phone = str(raw_phone or "")
    clean = re.sub(r"\D", "", raw_phone)
    if raw_phone.strip().startswith("+"):
        return raw_phone.strip()
    if clean.startswith("0") and len(clean) == 10:
        return "+33" + clean[1:]
    if clean:
        return "+33" + clean
    return raw_phone.strip()

# ==============================  PREFILL FORM URL  ==============================
def form_prefill_url(nom=None, tel=None, email=None, date_arrivee=None, date_depart=None,
                     plateforme=None, nuitees=None, res_id=None):
    base = GOOGLE_FORM_URL.split("?")[0]
    def to_ymd(d):
        if _null_like(d): return ""
        if isinstance(d, str): return d
        if isinstance(d, (pd.Timestamp, datetime)): d = d.date()
        if isinstance(d, date): return f"{d.year:04d}-{d.month:02d}-{d.day:02d}"
        return ""
    params = {}
    if not _null_like(nom):        params[FORM_ENTRY_NOM] = str(nom)
    if not _null_like(tel):        params[FORM_ENTRY_TEL] = str(tel)
    if not _null_like(email):      params[FORM_ENTRY_EMAIL] = str(email)
    if not _null_like(date_arrivee): params[FORM_ENTRY_ARRIVEE] = to_ymd(date_arrivee)
    if not _null_like(date_depart):  params[FORM_ENTRY_DEPART]  = to_ymd(date_depart)
    if FORM_ENTRY_PLATEFORME and not _null_like(plateforme):
        params[FORM_ENTRY_PLATEFORME] = str(plateforme)
    if FORM_ENTRY_NUITEES and not _null_like(nuitees):
        try:
            params[FORM_ENTRY_NUITEES] = str(int(nuitees))
        except Exception:
            params[FORM_ENTRY_NUITEES] = str(nuitees)
    if FORM_ENTRY_RESID and not _null_like(res_id):
        params[FORM_ENTRY_RESID] = str(res_id)
    return f"{base}?{urlencode(params, quote_via=quote_plus)}" if params else base

# ==============================  ICS CORE  ==============================
def _fmt_ics_date(d: date) -> str:
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"

def _escape_text(s: str) -> str:
    if s is None: return ""
    return str(s).replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')

def _compute_uid(df_row):
    uid = df_row.get('ical_uid')
    if isinstance(uid, str) and uid.strip():
        return uid
    return build_stable_uid(df_row)

def build_ics_from_df(df_src: pd.DataFrame) -> str:
    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR",
        "CALSCALE:GREGORIAN","METHOD:PUBLISH",
    ]
    for _, r in df_src.iterrows():
        da, dd = r['date_arrivee'], r['date_depart']
        if not isinstance(da, date) or not isinstance(dd, date): continue
        uid = _compute_uid(r)
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get('plateforme'): summary += f" ({r['plateforme']})"
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
    return "\r\n".join(lines) + "\r\n"

# ==============================  HELPERS RAPPORTS (NOUVEAU)  ==============================
from calendar import monthrange

def _month_start(d: date) -> date:
    return date(d.year, d.month, 1)

def _month_end(d: date) -> date:
    last = monthrange(d.year, d.month)[1]
    return date(d.year, d.month, last)

def _month_span(year: int):
    return [date(year, m, 1) for m in range(1, 13)]

def _available_nights_by_month(year: int):
    return {date(year, m, 1): monthrange(year, m)[1] for m in range(1, 13)}

def _expand_to_daily(df):
    rows = []
    for _, r in df.iterrows():
        da, dd = r.get('date_arrivee'), r.get('date_depart')
        if isinstance(da, date) and isinstance(dd, date) and dd > da:
            cur = da
            while cur < dd:
                rows.append({
                    "day": cur,
                    "plateforme": r.get("plateforme"),
                    "prix_brut": float(r.get("prix_brut") or 0),
                    "prix_net": float(r.get("prix_net") or 0),
                    "res_id": r.get("res_id"),
                })
                cur = cur + timedelta(days=1)
    return pd.DataFrame(rows)

def _safe_div2(a, b):
    return (a / b) if (b and b != 0) else float("nan")

def _fmt_eur(x):
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")

# ==============================  VUES  ==============================
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
    for bcol in ["paye","sms_envoye","post_depart_envoye"]:
        if bcol in df_sorted.columns:
            df_sorted[bcol] = _to_bool_series(df_sorted[bcol]).fillna(False).astype(bool)

    df_edit = df_sorted.copy()
    for c in ['date_arrivee', 'date_depart']:
        if c in df_edit.columns:
            df_edit[c] = pd.to_datetime(df_edit[c], errors='coerce')
    for bcol in ['paye', 'sms_envoye','post_depart_envoye']:
        if bcol in df_edit.columns:
            df_edit[bcol] = _to_bool_series(df_edit[bcol]).fillna(False).astype(bool)
    num_cols = ['AAAA','MM','nuitees','prix_brut','commissions','frais_cb','prix_net',
                'menage','taxes_sejour','base','charges','%']
    for c in num_cols:
        if c in df_edit.columns:
            df_edit[c] = pd.to_numeric(df_edit[c], errors='coerce').astype(float)
    if "_rowid" in df_edit.columns:
        df_edit["_rowid"] = df_edit["_rowid"].astype(str)

    col_order = list(df_edit.columns)
    if "_rowid" in col_order:
        col_order = [c for c in col_order if c != "_rowid"] + ["_rowid"]

    column_config = {}
    for c in df_edit.columns:
        if c in ("paye", "sms_envoye", "post_depart_envoye"):
            pretty = "Payé" if c=="paye" else ("SMS envoyé" if c=="sms_envoye" else "Post-départ envoyé")
            column_config[c] = st.column_config.CheckboxColumn(pretty)
        elif np.issubdtype(df_edit[c].dtype, np.datetime64):
            column_config[c] = st.column_config.DateColumn(
                "Arrivée" if c=="date_arrivee" else ("Départ" if c=="date_depart" else c),
                format="DD/MM/YYYY"
            )
        elif np.issubdtype(df_edit[c].dtype, np.number):
            if c in ("nuitees","AAAA","MM"):
                column_config[c] = st.column_config.NumberColumn(
                    "Nuits" if c=="nuitees" else ("Année" if c=="AAAA" else "Mois"),
                    format="%d"
                )
            elif c in ("prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges"):
                pretty = {
                    "prix_brut":"Prix Brut","commissions":"Commissions","frais_cb":"Frais CB",
                    "prix_net":"Prix Net","menage":"Ménage","taxes_sejour":"Taxes Séjour",
                    "base":"Base","charges":"Charges"
                }[c]
                column_config[c] = st.column_config.NumberColumn(pretty, format="%.2f €")
            elif c == "%":
                column_config[c] = st.column_config.NumberColumn("% Charges", format="%.2f %%")
            else:
                column_config[c] = st.column_config.NumberColumn(c)
        elif c == "_rowid":
            column_config[c] = st.column_config.TextColumn("", help="ID interne (index)", disabled=True)
        elif c == "email":
            column_config[c] = st.column_config.TextColumn("Email")
        elif c == "res_id":
            column_config[c] = st.column_config.TextColumn("res_id", help="Identifiant persistant")
        elif c == "ical_uid":
            column_config[c] = st.column_config.TextColumn("ical_uid", help="UID ICS (ne pas modifier)")
        elif c == "plateforme":
            column_config[c] = st.column_config.TextColumn("Plateforme")
        elif c == "nom_client":
            column_config[c] = st.column_config.TextColumn("Nom du Client")
        elif c == "telephone":
            column_config[c] = st.column_config.TextColumn("Téléphone")
        else:
            column_config[c] = st.column_config.TextColumn(c)

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
            for bcol in ["paye","sms_envoye","post_depart_envoye"]:
                if bcol in edited.columns:
                    edited[bcol] = edited[bcol].fillna(False).astype(bool)
            for _, row in edited.iterrows():
                rid_str = row.get("_rowid")
                if pd.isna(rid_str): continue
                try:
                    rid = int(rid_str)
                except Exception:
                    continue
                for bcol in ["paye","sms_envoye","post_depart_envoye"]:
                    df.loc[rid, bcol] = bool(row.get(bcol, False))
                if "email" in row: df.loc[rid, "email"] = row["email"]
                if isinstance(row.get("res_id"), str) and row["res_id"].strip() != "":
                    df.loc[rid, "res_id"] = row["res_id"].strip()
                if isinstance(row.get("ical_uid"), str) and row["ical_uid"].strip() != "":
                    df.loc[rid, "ical_uid"] = row["ical_uid"].strip()
                for c in ["date_arrivee", "date_depart"]:
                    val = row.get(c)
                    if pd.isna(val):
                        df.loc[rid, c] = pd.NaT
                    else:
                        if isinstance(val, (pd.Timestamp, datetime)):
                            df.loc[rid, c] = val.date()
                        else:
                            df.loc[rid, c] = val

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
            telephone  = st.text_input("Téléphone")
            email      = st.text_input("Email (optionnel)")
            date_arrivee = st.date_input("**Date d'arrivée**", date.today())
            date_depart  = st.date_input("**Date de départ**", date.today() + timedelta(days=1))
        with c2:
            plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()))
            prix_brut   = st.number_input("Prix Brut (€)", min_value=0.0, step=0.01, format="%.2f")
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01, format="%.2f")
            frais_cb    = st.number_input("Frais CB (€)", min_value=0.0, step=0.01, format="%.2f")
            menage      = st.number_input("Ménage (€)", min_value=0.0, step=0.01, format="%.2f")
            taxes_sejour= st.number_input("Taxes Séjour (€)", min_value=0.0, step=0.01, format="%.2f")
        paye = st.checkbox("Payé", False)

        if st.form_submit_button("✅ Ajouter la réservation"):
            if not nom_client or date_depart <= date_arrivee:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nouvelle = pd.DataFrame([{
                    'res_id': str(uuid.uuid4()),
                    'nom_client': nom_client, 'telephone': telephone, 'email': email,
                    'date_arrivee': date_arrivee, 'date_depart': date_depart,
                    'plateforme': plateforme, 'prix_brut': prix_brut, 'commissions': commissions,
                    'frais_cb': frais_cb, 'menage': menage, 'taxes_sejour': taxes_sejour,
                    'paye': paye, 'sms_envoye': False, 'post_depart_envoye': False
                }])
                df2 = pd.concat([df, nouvelle], ignore_index=True)
                df2 = ensure_schema(df2)
                if sauvegarder_donnees_csv(df2):
                    st.success(f"Réservation pour {nom_client} ajoutée.")
                    st.rerun()

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer une Réservation")
    if df.empty:
        st.warning("Aucune réservation à modifier.")
        return
    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options_resa = [f"{idx}: {row['nom_client']} ({row['date_arrivee']})"
                    for idx, row in df_sorted.iterrows() if pd.notna(row['date_arrivee'])]
    selection = st.selectbox("Sélectionnez une réservation", options=options_resa, index=None)
    if selection:
        idx_selection = int(selection.split(":")[0])
        original_index = df_sorted.loc[idx_selection, 'index']
        resa = df.loc[original_index].copy()
        with st.form(f"form_modif_{original_index}"):
            c1, c2 = st.columns(2)
            with c1:
                nom_client = st.text_input("**Nom du Client**", value=resa.get('nom_client',''))
                telephone  = st.text_input("Téléphone", value=resa.get('telephone',''))
                email      = st.text_input("Email (optionnel)", value=resa.get('email','') if 'email' in resa else '')
                date_arrivee = st.date_input("**Date d'arrivée**", value=resa.get('date_arrivee'))
                date_depart  = st.date_input("**Date de départ**", value=resa.get('date_depart'))
            with c2:
                p_opts = list(palette.keys())
                p_cur  = resa.get('plateforme')
                p_idx  = p_opts.index(p_cur) if p_cur in p_opts else 0
                plateforme  = st.selectbox("**Plateforme**", options=p_opts, index=p_idx)
                prix_brut   = st.number_input("Prix Brut (€)", min_value=0.0, value=resa.get('prix_brut',0.0), step=0.01, format="%.2f")
                commissions = st.number_input("Commissions (€)", min_value=0.0, value=resa.get('commissions',0.0), step=0.01, format="%.2f")
                paye        = st.checkbox("Payé", value=bool(resa.get('paye', False)))
            btn_enregistrer, btn_supprimer = st.columns([.8, .2])
            if btn_enregistrer.form_submit_button("💾 Enregistrer"):
                updates = {'nom_client': nom_client,'telephone': telephone,'email': email,
                           'date_arrivee': date_arrivee,'date_depart': date_depart,
                           'plateforme': plateforme,'prix_brut': prix_brut,'commissions': commissions,'paye': paye}
                for k,v in updates.items(): df.loc[original_index, k] = v
                df_final = ensure_schema(df)
                if sauvegarder_donnees_csv(df_final):
                    st.success("Modifications enregistrées !"); st.rerun()
            if btn_supprimer.form_submit_button("🗑️ Supprimer"):
                df_final = df.drop(index=original_index)
                if sauvegarder_donnees_csv(df_final):
                    st.warning("Réservation supprimée."); st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Gestion des Plateformes")
    df_palette = pd.DataFrame(list(palette.items()), columns=['plateforme','couleur'])
    edited_df = st.data_editor(df_palette, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={"plateforme": "Plateforme", "couleur": st.column_config.TextColumn("Couleur (code hex)")})
    if st.button("💾 Enregistrer les modifications"):
        nouvelle_palette = dict(zip(edited_df['plateforme'], edited_df['couleur']))
        df_plateformes_save = pd.DataFrame(list(nouvelle_palette.items()), columns=['plateforme','couleur'])
        try:
            df_plateformes_save.to_csv(CSV_PLATEFORMES, sep=';', index=False)
            st.cache_data.clear()
            st.success("Palette de couleurs mise à jour !"); st.rerun()
        except Exception as e:
            st.error(f"Erreur de sauvegarde de la palette : {e}")

def vue_calendrier(df, palette):
    st.header("📅 Calendrier des Réservations")
    df_ok = df.dropna(subset=['date_arrivee','date_depart','AAAA'])
    if df_ok.empty:
        st.info("Aucune réservation à afficher."); return
    c1, c2 = st.columns(2)
    today = date.today()
    noms_mois = [calendar.month_name[i] for i in range(1,13)]
    selected_month_name = c1.selectbox("Mois", options=noms_mois, index=today.month-1)
    selected_month = noms_mois.index(selected_month_name)+1
    years = sorted(list(df_ok['AAAA'].dropna().astype(int).unique()))
    if not years: years = [today.year]
    try: default_year_index = years.index(today.year)
    except ValueError: default_year_index = len(years)-1
    selected_year = c2.selectbox("Année", options=years, index=default_year_index)
    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(selected_year, selected_month)
    st.markdown("""<style>.calendar-day{border:1px solid #444;min-height:120px;padding:5px;vertical-align:top}.calendar-day.outside-month{background:#2e2e2e}.calendar-date{font-weight:700;font-size:1.1em;margin-bottom:5px;text-align:right}.reservation-bar{padding:3px 6px;margin-bottom:3px;border-radius:5px;font-size:.9em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}</style>""", unsafe_allow_html=True)
    headers = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    st.write(f'<div style="display:grid;grid-template-columns:repeat(7,1fr);text-align:center;font-weight:700">{"".join(f"<div>{h}</div>" for h in headers)}</div>', unsafe_allow_html=True)
    for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                day_class = "outside-month" if day.month != selected_month else ""
                day_html = f"<div class='calendar-day {day_class}'><div class='calendar-date'>{day.day}</div>"
                for _, resa in df_ok.iterrows():
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
    end_of_month   = date(selected_year, selected_month, calendar.monthrange(selected_year, selected_month)[1])
    reservations_du_mois = df_ok[(df_ok['date_arrivee'] <= end_of_month) & df_ok['date_depart'].gt(start_of_month)].sort_values(by="date_arrivee").reset_index()
    if not reservations_du_mois.empty:
        options = {f"{row['nom_client']} ({row['date_arrivee'].strftime('%d/%m')})": idx for idx, row in reservations_du_mois.iterrows()}
        selection_str = st.selectbox("Voir les détails :", options=options.keys(), index=None)
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

# ==============================  RAPPORT MAXI (NOUVEAU)  ==============================
def vue_rapport(df, palette):
    st.header("📊 Rapport de Performance — complet")

    base = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if base.empty:
        st.info("Aucune donnée pour générer un rapport."); 
        return

    # Filtres principaux
    c0, c1, c2, c3 = st.columns([1,1,1,2])
    years = sorted({d.year for d in base['date_arrivee'] if isinstance(d, date)}, reverse=True)
    annee = c0.selectbox("Année", years, index=0)

    plateformes = sorted([p for p in base['plateforme'].dropna().unique()])
    plats = c1.multiselect("Plateformes", plateformes, default=plateformes)

    paid_only = c2.toggle("Uniquement réservations payées", value=False)
    metric_mode = c3.radio("Mode de revenu", ["Brut", "Net"], index=0, horizontal=True)

    mcol = "prix_brut" if metric_mode == "Brut" else "prix_net"

    data = base[(pd.Series([isinstance(d, date) and d.year == annee for d in base['date_arrivee']]))].copy()
    if plats:
        data = data[data['plateforme'].isin(plats)]
    if paid_only:
        data = data[data['paye'] == True]

    if data.empty:
        st.warning("Aucune donnée après filtres."); 
        return

    # ==== KPI Année ====
    nb_res = len(data)
    nuits = int(data['nuitees'].fillna(0).sum())
    rev_total = float(data[mcol].fillna(0).sum())
    adr = _safe_div2(rev_total, nuits)
    # Occupation & RevPAR (sur l'année complète, 1 logement)
    avail_year = 366 if calendar.isleap(annee) else 365
    occ = _safe_div2(nuits, avail_year)
    revpar = _safe_div2(rev_total, avail_year)
    panier = _safe_div2(rev_total, nb_res)  # panier moyen par séjour

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Réservations", f"{nb_res}")
    k2.metric("Nuitées vendues", f"{nuits}")
    k3.metric(f"Revenu {metric_mode.lower()}", _fmt_eur(rev_total))
    k4.metric(f"ADR {metric_mode.lower()}", _fmt_eur(adr) if pd.notna(adr) else "—")
    k5.metric("Taux d’occupation", f"{occ*100:,.1f} %".replace(",", " ") if pd.notna(occ) else "—")
    k6.metric(f"RevPAR {metric_mode.lower()}", _fmt_eur(revpar) if pd.notna(revpar) else "—")

    st.markdown("---")

    # ==== Agrégats mensuels par plateforme ====
    data['mois'] = data['date_arrivee'].apply(lambda d: date(d.year, d.month, 1))
    grp = (data.groupby(['plateforme','mois'], as_index=False)
               .agg({mcol:'sum', 'nuitees':'sum'}))

    months_all = _month_span(annee)
    frames = []
    for p in (plats if plats else plateformes):
        g = grp[grp['plateforme']==p].set_index('mois').reindex(months_all).fillna({mcol:0.0,'nuitees':0.0})
        g['plateforme'] = p
        g = g.reset_index().rename(columns={'index':'mois'})
        frames.append(g)
    grp_full = pd.concat(frames, ignore_index=True)

    # dérivés: ADR, Occ, RevPAR par mois
    avail_map = _available_nights_by_month(annee)
    grp_full['available'] = grp_full['mois'].map(avail_map)
    grp_full['adr'] = grp_full.apply(lambda r: _safe_div2(r[mcol], r['nuitees']), axis=1)
    grp_full['occ'] = grp_full.apply(lambda r: _safe_div2(r['nuitees'], r['available']), axis=1)
    grp_full['revpar'] = grp_full.apply(lambda r: _safe_div2(r[mcol], r['available']), axis=1)

    st.subheader("Tendances par mois")
    colA, colB = st.columns(2)
    choix_serie = colA.selectbox("Série", [f"Revenu {metric_mode.lower()}", "Nuitées", f"ADR {metric_mode.lower()}", "Occupation", f"RevPAR {metric_mode.lower()}"])
    stack = colB.toggle("Empiler (total mensuel)", value=False)

    serie_map = {
        f"Revenu {metric_mode.lower()}": ("value", mcol, ".2f"),
        "Nuitées": ("nuitees", "nuitees", ".0f"),
        f"ADR {metric_mode.lower()}": ("adr", "adr", ".2f"),
        "Occupation": ("occ", "occ", ".1%"),
        f"RevPAR {metric_mode.lower()}": ("revpar", "revpar", ".2f"),
    }
    yfield, realfield, fmt = serie_map[choix_serie]
    grp_full[yfield] = grp_full[realfield]

    color_map = {p: palette.get(p, '#888') for p in (plats if plats else plateformes)}
    domain_sel = list(color_map.keys())
    range_sel  = [color_map[p] for p in domain_sel]

    base_chart = alt.Chart(grp_full).encode(
        x=alt.X('yearmonth(mois):T', title='Mois'),
        color=alt.Color('plateforme:N', scale=alt.Scale(domain=domain_sel, range=range_sel), title="Plateforme"),
        tooltip=[
            alt.Tooltip('plateforme:N', title='Plateforme'),
            alt.Tooltip('yearmonth(mois):T', title='Mois'),
            alt.Tooltip(f'{yfield}:Q', title=choix_serie, format=fmt),
        ]
    )
    if choix_serie in [f"Revenu {metric_mode.lower()}", "Nuitées"] and stack:
        chart = base_chart.mark_bar().encode(y=alt.Y(f'{yfield}:Q', title=choix_serie, stack='zero'))
    else:
        if choix_serie in [f"Revenu {metric_mode.lower()}", "Nuitées"]:
            chart = base_chart.mark_bar().encode(
                y=alt.Y(f'{yfield}:Q', title=choix_serie),
                xOffset=alt.X('plateforme:N', title=None),
            )
        else:
            chart = base_chart.mark_line(point=True).encode(y=alt.Y(f'{yfield}:Q', title=choix_serie))

    st.altair_chart(chart.properties(height=420).interactive(), use_container_width=True)

    st.markdown("---")

    # ==== Mix plateformes ====
    st.subheader("Répartition par plateforme (année)")
    mix = (data.groupby("plateforme", as_index=False)
              .agg(revenu=(mcol,'sum'), nuitées=('nuitees','sum'), sejours=('res_id','count')))
    c1, c2 = st.columns([2,1])
    chart_mix = alt.Chart(mix).mark_bar().encode(
        x=alt.X('plateforme:N', title='Plateforme'),
        y=alt.Y('revenu:Q', title=f'Revenu {metric_mode.lower()}'),
        color=alt.Color('plateforme:N', legend=None, scale=alt.Scale(domain=domain_sel, range=range_sel)),
        tooltip=[alt.Tooltip('plateforme:N'), alt.Tooltip('revenu:Q', format='.2f'), alt.Tooltip('nuitées:Q'), alt.Tooltip('sejours:Q')]
    )
    c1.altair_chart(chart_mix.properties(height=320), use_container_width=True)
    c2.dataframe(mix.sort_values('revenu', ascending=False), use_container_width=True)

    st.markdown("---")

    # ==== Heatmap d’occupation (12 x jours) ====
    st.subheader("Heatmap d’occupation")
    daily = _expand_to_daily(data)
    if daily.empty:
        st.info("Pas assez de données pour la heatmap.")
    else:
        daily['mois'] = daily['day'].apply(lambda d: date(d.year, d.month, 1))
        occ_days = (daily.groupby('day', as_index=False).agg(occ=('res_id','nunique')))
        occ_days['occ'] = occ_days['occ'].clip(0,1)

        all_days = pd.DataFrame({"day": pd.date_range(f"{annee}-01-01", f"{annee}-12-31", freq="D").date})
        all_days = all_days.merge(occ_days[['day','occ']], on='day', how='left').fillna({'occ': 0})
        all_days['mois'] = all_days['day'].apply(lambda d: date(d.year, d.month, 1))
        all_days['jour'] = all_days['day'].apply(lambda d: d.day)

        heat = alt.Chart(all_days).mark_rect().encode(
            x=alt.X('jour:O', title='Jour'),
            y=alt.Y('month(mois):O', title='Mois'),
            color=alt.Color('occ:Q', title='Occupation', scale=alt.Scale(domain=[0,1], range=['#111', '#26a269'])),
            tooltip=[alt.Tooltip('day:T', title='Date'), alt.Tooltip('occ:Q', title='Occupé', format='.0f')]
        )
        st.altair_chart(heat.properties(height=320), use_container_width=True)

    st.markdown("---")

    # ==== Distributions ====
    st.subheader("Distributions")
    colD1, colD2 = st.columns(2)

    dist_nuitees = alt.Chart(data).mark_bar().encode(
        x=alt.X('nuitees:Q', bin=alt.Bin(maxbins=15), title='Nuitées (par séjour)'),
        y=alt.Y('count()', title='Nombre de séjours'),
        tooltip=[alt.Tooltip('count():Q', title='Séjours')]
    )
    colD1.altair_chart(dist_nuitees.properties(height=280), use_container_width=True)

    adr_per_resa = data.assign(adr_res=lambda x: x.apply(lambda r: _safe_div2(r[mcol], r['nuitees']), axis=1))
    box = alt.Chart(adr_per_resa.dropna(subset=['adr_res'])).mark_boxplot().encode(
        x=alt.X('plateforme:N', title='Plateforme'),
        y=alt.Y('adr_res:Q', title=f'ADR {metric_mode.lower()} par séjour'),
        color=alt.Color('plateforme:N', legend=None, scale=alt.Scale(domain=domain_sel, range=range_sel)),
    )
    colD2.altair_chart(box.properties(height=280), use_container_width=True)

    # ==== Export ====
    with st.expander("Données mensuelles et export CSV"):
        export = grp_full[['mois','plateforme', mcol, 'nuitees', 'adr', 'occ', 'revpar']].copy()
        export = export.rename(columns={
            'mois': 'Mois', 'plateforme': 'Plateforme',
            mcol: f"Revenu_{metric_mode.lower()}",
            'nuitees': 'Nuitées',
            'adr': f"ADR_{metric_mode.lower()}",
            'occ': 'Occupation',
            'revpar': f"RevPAR_{metric_mode.lower()}",
        })
        export = export[export['Plateforme'].notna() & (export['Plateforme'].astype(str).str.strip() != "")]
        st.dataframe(export.sort_values(['Mois','Plateforme']), use_container_width=True)
        st.download_button("⬇️ Télécharger CSV mensuel",
                           data=export.to_csv(index=False, sep=';').encode('utf-8'),
                           file_name=f"rapport_{annee}_{metric_mode.lower()}_mensuel.csv",
                           mime="text/csv")

def vue_liste_clients(df):
    st.header("👥 Liste des Clients")
    if df.empty:
        st.info("Aucun client."); return
    clients = df[['nom_client','telephone','email','plateforme']].dropna(subset=['nom_client']).drop_duplicates().sort_values('nom_client')
    st.dataframe(clients, use_container_width=True)

def vue_sms(df):
    st.header("✉️ Générateur de SMS")
    for colb in ('sms_envoye','post_depart_envoye'):
        if colb in df.columns:
            df[colb] = _to_bool_series(df[colb]).fillna(False).astype(bool)
        else:
            df[colb] = False

    # ---------- Pré-arrivée (par défaut J+1) ----------
    st.subheader("🛬 Messages pré-arrivée")
    tomorrow_default = date.today() + timedelta(days=1)
    target_arrivee = st.date_input("Cibler les arrivées du", tomorrow_default, key="prearrivee_date")
    df_tel = df.dropna(subset=['telephone','nom_client','date_arrivee']).copy()
    df_tel = df_tel[df_tel['date_arrivee'] == target_arrivee]
    df_tel['tel_clean'] = df_tel['telephone'].astype(str).str.replace(r'\D','',regex=True).str.lstrip('0')
    mask_valid_phone = df_tel['tel_clean'].str.len().between(9,15)
    df_tel = df_tel[~df_tel['sms_envoye'] & mask_valid_phone].copy()
    df_tel["_rowid"] = df_tel.index

    st.components.v1.html("""
        <button onclick="navigator.clipboard.writeText('%s')"
                style="margin-bottom:10px;padding:6px 10px;border-radius:8px;border:1px solid #888;background:#222;color:#fff;cursor:pointer">
            📋 Copier le lien (formulaire)
        </button>
    """ % FORM_SHORT_URL, height=48)

    if df_tel.empty:
        st.info("Aucun client à contacter pour la date choisie (ou déjà marqué 'SMS envoyé').")
    else:
        df_sorted = df_tel.sort_values(by="date_arrivee", ascending=True).reset_index(drop=True)
        options_resa = [f"{idx}: {row['nom_client']} ({row['telephone']})" for idx, row in df_sorted.iterrows()]
        selection = st.selectbox("Sélectionnez un client (pré-arrivée)", options=options_resa, index=None, key="prearrival_select")
        if selection:
            idx = int(selection.split(":")[0])
            resa = df_sorted.loc[idx]
            original_rowid = resa["_rowid"]
            res_id_val = _ensure_res_id_on_row(df, original_rowid)
            email_val = resa.get('email') if 'email' in df_tel.columns else None
            prefill_link = form_prefill_url(
                nom         = resa.get('nom_client'),
                tel         = resa.get('telephone'),
                email       = email_val,
                date_arrivee= resa.get('date_arrivee'),
                date_depart = resa.get('date_depart'),
                plateforme  = resa.get('plateforme'),
                nuitees     = resa.get('nuitees'),
                res_id      = res_id_val
            )
            link_for_message = FORM_SHORT_URL.strip() or prefill_link

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
{link_for_message}"""

            encoded_message = quote(message_body)
            e164_phone = _format_phone_e164(resa['telephone'])
            sms_link_ios = f"sms:&body={encoded_message}"
            sms_link_android = f"sms:{e164_phone}?body={encoded_message}"
            wa_number = re.sub(r"\D", "", e164_phone)
            wa_link = f"https://wa.me/{wa_number}?text={encoded_message}"

            c_ios, c_and, c_wa = st.columns([1,1,1])
            with c_ios: st.link_button("📲 iPhone SMS", sms_link_ios)
            with c_and: st.link_button("🤖 Android SMS", sms_link_android)
            with c_wa:  st.link_button("🟢 WhatsApp", wa_link)

            st.components.v1.html("""
                <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
                  <button onclick="navigator.clipboard.writeText(%s)"
                          style="padding:8px 12px;border-radius:8px;border:1px solid #888;background:#222;color:#fff;cursor:pointer">
                      📋 Copier le message
                  </button>
                  <button onclick="navigator.clipboard.writeText('%s')"
                          style="padding:8px 12px;border-radius:8px;border:1px solid #888;background:#222;color:#fff;cursor:pointer">
                      📋 Copier le lien (formulaire)
                  </button>
                </div>
            """ % (json.dumps(message_body), FORM_SHORT_URL), height=60)

            if st.button("✅ Marquer ce client comme 'SMS envoyé'"):
                try:
                    df.loc[original_rowid,'sms_envoye'] = True
                    df_final = ensure_schema(df)
                    if sauvegarder_donnees_csv(df_final):
                        st.success("Marqué 'SMS envoyé' ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer comme envoyé : {e}")

    st.markdown("---")

    # ---------- Post-départ (individuel) — par défaut départs du jour ----------
    st.subheader("📤 WhatsApp / SMS post-départ (individuel)")
    default_depart = date.today()
    target_depart = st.date_input("Cibler les départs du", default_depart, key="postdepart_date")

    df_post = df.dropna(subset=['telephone','nom_client','date_depart']).copy()
    df_post = df_post[(df_post['date_depart'] == target_depart) & (~df_post['post_depart_envoye'])]

    df_post['tel_clean'] = df_post['telephone'].astype(str).str.replace(r'\D','',regex=True).str.lstrip('0')
    mask_valid_phone2 = df_post['tel_clean'].str.len().between(9,15)
    df_post = df_post[mask_valid_phone2].copy()
    df_post["_rowid"] = df_post.index

    if df_post.empty:
        st.info("Aucun message post-départ à envoyer pour la date choisie.")
    else:
        df_sorted2 = df_post.sort_values(by="date_depart", ascending=True).reset_index(drop=True)
        options_post = [f"{idx}: {row['nom_client']} — départ {row['date_depart']}" for idx, row in df_sorted2.iterrows()]
        selection2 = st.selectbox("Sélectionnez un client (post-départ)", options=options_post, index=None, key="post_select")
        if selection2:
            idx2 = int(selection2.split(":")[0])
            resa2 = df_sorted2.loc[idx2]
            original_rowid2 = resa2["_rowid"]
            name = str(resa2.get('nom_client') or "").strip()

            message_post = f"""Bonjour {name},

Un grand merci d'avoir choisi notre appartement pour votre sejour. 

Nous esperons que vous avez passe un moment aussi agreable que celui que nous avons eu a vous accueillir. 

Si l'envie vous prend de revenir explorer encore un peu notre ville, sachez que notre porte vous sera toujours grande ouverte. 

Au plaisir de vous accueillir à nouveau.

Annick & Charley

Hello {name},

Thank you very much for choosing our apartment for your stay. 

We hope you had as enjoyable a time as we did hosting you. 

If you feel like coming back to explore our city a little more, know that our door will always be open to you. 

We look forward to welcoming you back.

Annick & Charley"""

            encoded_post = quote(message_post)
            e164_phone2 = _format_phone_e164(resa2['telephone'])
            wa_number2 = re.sub(r"\D", "", e164_phone2)
            wa_link2 = f"https://wa.me/{wa_number2}?text={encoded_post}"
            sms_link_ios2 = f"sms:&body={encoded_post}"
            sms_link_android2 = f"sms:{e164_phone2}?body={encoded_post}"

            c_wa2, c_ios2, c_and2 = st.columns([1,1,1])
            with c_wa2:  st.link_button("🟢 WhatsApp", wa_link2)
            with c_ios2: st.link_button("📲 iPhone SMS", sms_link_ios2)
            with c_and2: st.link_button("🤖 Android SMS", sms_link_android2)

            st.components.v1.html("""
                <button onclick="navigator.clipboard.writeText(%s)"
                        style="margin-top:8px;padding:8px 12px;border-radius:8px;border:1px solid #888;background:#222;color:#fff;cursor:pointer">
                    📋 Copier le message post-départ
                </button>
            """ % (json.dumps(message_post),), height=50)

            if st.button("✅ Marquer 'post-départ envoyé'"):
                try:
                    df.loc[original_rowid2,'post_depart_envoye'] = True
                    df_final = ensure_schema(df)
                    if sauvegarder_donnees_csv(df_final):
                        st.success("Marqué 'post-départ envoyé' ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    st.markdown("---")

    # ---------- Post-départ (envoi groupé) ----------
    st.subheader("📦 Envoi groupé post-départ")
    cold1, cold2 = st.columns(2)
    default_end = date.today()
    default_start = default_end - timedelta(days=7)
    d_start = cold1.date_input("Départs à partir de", default_start)
    d_end   = cold2.date_input("Jusqu'au (inclus)", default_end)

    elig = df.dropna(subset=['telephone','nom_client','date_depart']).copy()
    elig = elig[(elig['date_depart'] >= d_start) & (elig['date_depart'] <= d_end) & (~elig['post_depart_envoye'])].copy()
    elig['tel_clean'] = elig['telephone'].astype(str).str.replace(r'\D','',regex=True).str.lstrip('0')
    elig = elig[elig['tel_clean'].str.len().between(9,15)]
    if elig.empty:
        st.info("Aucun client dans la plage sélectionnée.")
    else:
        rows_ui = []
        all_messages = []
        for ridx, r in elig.iterrows():
            name = str(r.get('nom_client') or "").strip()
            msg = f"""Bonjour {name},

Un grand merci d'avoir choisi notre appartement pour votre sejour. 

Nous esperons que vous avez passe un moment aussi agreable que celui que nous avons eu a vous accueillir. 

Si l'envie vous prend de revenir explorer encore un peu notre ville, sachez que notre porte vous sera toujours grande ouverte. 

Au plaisir de vous accueillir à nouveau.

Annick & Charley

Hello {name},

Thank you very much for choosing our apartment for your stay. 

We hope you had as enjoyable a time as we did hosting you. 

If you feel like coming back to explore our city a little more, know that our door will always be open to you. 

We look forward to welcoming you back.

Annick & Charley"""
            all_messages.append(msg)
            e164 = _format_phone_e164(r['telephone'])
            wa_num = re.sub(r"\D", "", e164)
            enc = quote(msg)
            rows_ui.append({
                "index": ridx,
                "nom": name,
                "tel": r['telephone'],
                "depart": r['date_depart'],
                "wa": f"https://wa.me/{wa_num}?text={enc}",
                "sms_ios": f"sms:&body={enc}",
                "sms_android": f"sms:{e164}?body={enc}",
            })

        st.write(f"Clients éligibles : **{len(rows_ui)}**")
        cgb1, cgb2 = st.columns(2)
        if cgb1.button("📋 Tout copier (messages)"):
            clipboard_text = "\n\n---\n".join(all_messages)
            clipboard_json = json.dumps(clipboard_text)
            st.components.v1.html(
                f"""
                <script>
                  navigator.clipboard.writeText({clipboard_json});
                </script>
                <div style="color:#aaa">Tous les messages ont été copiés dans le presse-papiers.</div>
                """,
                height=10
            )
            st.success("Messages copiés.")
        if cgb2.button("✅ Tout marquer 'post-départ envoyé'"):
            try:
                idxs = [row["index"] for row in rows_ui]
                df.loc[idxs, 'post_depart_envoye'] = True
                df_final = ensure_schema(df)
                if sauvegarder_donnees_csv(df_final):
                    st.success(f"{len(idxs)} réservation(s) marquées comme envoyées."); st.rerun()
            except Exception as e:
                st.error(f"Impossible de marquer en masse : {e}")

        for row in rows_ui:
            with st.container(border=True):
                c1, c2, c3, c4 = st.columns([2,1,1,1])
                c1.markdown(f"**{row['nom']}** — départ {row['depart']}  \n📞 {row['tel']}")
                c2.link_button("🟢 WhatsApp", row["wa"])
                c3.link_button("📲 iPhone SMS", row["sms_ios"])
                c4.link_button("🤖 Android SMS", row["sms_android"])

# ==============================  EXPORT ICS MANUEL  ==============================
def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    st.info("Génère un fichier .ics à importer dans Google Calendar.")

    base_all = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if base_all.empty:
        st.warning("Aucune réservation avec dates valides."); return

    col1, col2 = st.columns(2)
    years = sorted(base_all['date_arrivee'].apply(lambda d: d.year).unique())
    annee = col1.selectbox("Filtrer Année (arrivée)", years, index=len(years)-1)
    plateformes = sorted(base_all['plateforme'].dropna().unique())
    plats = col2.multiselect("Plateformes", plateformes, default=plateformes)

    c3, c4, c5 = st.columns(3)
    create_missing_uid = c3.toggle("Créer et sauvegarder les UID manquants", value=True)
    include_paid       = c4.toggle("Inclure les réservations non payées", value=True)
    include_sms_sent   = c5.toggle("Inclure celles déjà 'SMS envoyé'", value=True)
    apply_to_all = st.toggle("Ignorer les filtres et créer pour toute la base", value=False)

    df_filtre = base_all[(base_all['date_arrivee'].apply(lambda d: d.year) == annee) & (base_all['plateforme'].isin(plats))].copy()
    if not include_paid:     df_filtre = df_filtre[df_filtre['paye'] == True]
    if not include_sms_sent: df_filtre = df_filtre[df_filtre['sms_envoye'] == False]
    if df_filtre.empty: st.warning("Rien à exporter avec ces filtres.")

    df_to_gen = base_all.copy() if apply_to_all else df_filtre.copy()
    if not df_to_gen.empty:
        missing_res_id = df_to_gen['res_id'].isna() | (df_to_gen['res_id'].astype(str).str.strip() == "")
        if create_missing_uid and missing_res_id.any():
            df_to_gen.loc[missing_res_id, 'res_id'] = [str(uuid.uuid4()) for _ in range(int(missing_res_id.sum()))]
            try:
                df.loc[df_to_gen.index, 'res_id'] = df_to_gen['res_id']
                if sauvegarder_donnees_csv(df):
                    st.success(f"ID internes créés pour {int(missing_res_id.sum())} réservation(s).")
            except Exception as e:
                st.error(f"Impossible de sauvegarder les ID internes : {e}")

        missing_uid = df_to_gen['ical_uid'].isna() | (df_to_gen['ical_uid'].astype(str).str.strip() == "")
        if missing_uid.any():
            df_to_gen.loc[missing_uid, 'ical_uid'] = df_to_gen[missing_uid].apply(build_stable_uid, axis=1)
        if create_missing_uid and missing_uid.any():
            try:
                df.loc[df_to_gen.index, 'ical_uid'] = df_to_gen['ical_uid']
                if sauvegarder_donnees_csv(df):
                    st.success(f"UID ICS créés/sauvegardés pour {int(missing_uid.sum())} réservation(s).")
            except Exception as e:
                st.error(f"Impossible de sauvegarder les UID : {e}")

        if not df_filtre.empty:
            inter = df_to_gen.index.intersection(df_filtre.index)
            df_filtre.loc[inter,'res_id']   = df_to_gen.loc[inter,'res_id']
            df_filtre.loc[inter,'ical_uid'] = df_to_gen.loc[inter,'ical_uid']

    ics = build_ics_from_df(df_filtre)
    st.download_button("📥 Télécharger le fichier ICS", data=ics.encode('utf-8'),
                       file_name=f"villa_tobias_{annee}.ics", mime="text/calendar")

# ==============================  FLUX ICS PUBLIC (BETA)  ==============================
def _get_query_params():
    try:
        return st.query_params
    except Exception:
        try:
            return st.experimental_get_query_params()
        except Exception:
            return {}

def _as_list(v):
    if v is None: return []
    if isinstance(v, list): return v
    return [v]

def icspublic_endpoint(df):
    params = _get_query_params()
    feed = params.get("feed", [""])[0] if isinstance(params.get("feed"), list) else params.get("feed", "")
    if str(feed).lower() != "ics":
        return False
    token = params.get("token", [""])[0] if isinstance(params.get("token"), list) else params.get("token", "")
    if not token:
        st.write("Missing token."); st.stop()
    annee  = params.get("year", [""])[0] if isinstance(params.get("year"), list) else params.get("year", "")
    plats  = _as_list(params.get("plats")) if "plats" in params else _as_list(params.get("platform"))
    inc_np = params.get("incl_np", ["1"])[0] if isinstance(params.get("incl_np"), list) else params.get("incl_np", "1")
    inc_sms= params.get("incl_sms", ["1"])[0] if isinstance(params.get("incl_sms"), list) else params.get("incl_sms", "1")

    data = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if annee:
        try:
            an = int(annee)
            data = data[data['date_arrivee'].apply(lambda d: isinstance(d, date) and d.year == an)]
        except:
            pass
    if plats:
        plats_norm = [p for p in plats if p]
        if plats_norm:
            data = data[data['plateforme'].isin(plats_norm)]
    if inc_np in ("0","false","False"):
        data = data[data['paye'] == True]
    if inc_sms in ("0","false","False"):
        data = data[data['sms_envoye'] == False]

    ics = build_ics_from_df(data)
    st.text(ics)
    st.stop()

def vue_flux_ics_public(df, palette):
    st.header("🔗 Flux ICS public (BETA)")
    st.caption("Copie cette URL dans Google Calendar → *Ajouter un agenda* → *À partir de l’URL*. "
               "Si Google refuse, on posera un petit proxy qui renvoie le bon en-tête `text/calendar`.")

    base_url = st.text_input("URL de base de l'app (tel qu'affichée dans ton navigateur)", value=st.request.url if hasattr(st, "request") and hasattr(st.request, "url") else "")
    if not base_url:
        st.info("Renseigne l’URL de l’app telle qu’elle s’affiche dans la barre d’adresse pour générer le lien.")
    col1, col2 = st.columns(2)
    years = sorted([d.year for d in df['date_arrivee'].dropna().unique()]) if 'date_arrivee' in df.columns else []
    year = col1.selectbox("Année (arrivées)", options=years if years else [date.today().year], index=len(years)-1 if years else 0)
    plateformes = sorted(df['plateforme'].dropna().unique()) if 'plateforme' in df.columns else []
    plats = col2.multiselect("Plateformes", plateformes, default=plateformes)

    c3, c4 = st.columns(2)
    incl_np  = c3.toggle("Inclure réservations non payées", value=True)
    incl_sms = c4.toggle("Inclure celles déjà 'SMS envoyé'", value=True)

    token_default = hashlib.sha256(f"villa-tobias-{year}".encode()).hexdigest()[:16]
    token = st.text_input("Token (clé simple, à partager seulement avec Google Calendar)", value=token_default)

    def build_url(base, params):
        if not base:
            return ""
        base_clean = base.split("?")[0]
        return base_clean + "?" + urlencode(params, doseq=True)

    query = {
        "feed": "ics",
        "token": token,
        "year": str(year),
        "incl_np": "1" if incl_np else "0",
        "incl_sms": "1" if incl_sms else "0",
    }
    for p in plats:
        query.setdefault("plats", []).append(p)

    flux_url = build_url(base_url, query)
    if flux_url:
        st.code(flux_url, language="text")
        st.link_button("📋 Copier / Ouvrir l’URL de flux", flux_url)

    with st.expander("Aperçu du contenu ICS (généré avec ces filtres)"):
        data = df.dropna(subset=['date_arrivee','date_depart']).copy()
        data = data[data['date_arrivee'].apply(lambda d: isinstance(d, date) and d.year == year)]
        if plats:
            data = data[data['plateforme'].isin(plats)]
        if not incl_np:
            data = data[data['paye'] == True]
        if not incl_sms:
            data = data[data['sms_envoye'] == False]
        st.text(build_ics_from_df(data))

# ==============================  GOOGLE SHEET / FORM  ==============================
def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée — Google Form & Sheet")
    tab_form, tab_sheet, tab_csv = st.tabs(["Formulaire (intégré)", "Feuille intégrée", "Réponses (CSV)"])

    with tab_form:
        st.caption("Formulaire Google intégré (prérempli à partir d'une réservation).")
        df_ok = df.dropna(subset=['nom_client','telephone','date_arrivee']).copy()
        if df_ok.empty:
            st.info("Aucune réservation exploitable pour préremplir le formulaire.")
            st.components.v1.iframe(GOOGLE_FORM_URL, height=950, scrolling=True)
            st.markdown(f"**Lien à partager (court)** : {FORM_SHORT_URL}")
            st.components.v1.html("""
                <button onclick="navigator.clipboard.writeText('%s')"
                        style="margin-top:6px;padding:6px 10px;border-radius:8px;border:1px solid #888;background:#222;color:#fff;cursor:pointer">
                    📋 Copier le lien
                </button>
            """ % FORM_SHORT_URL, height=50)
        else:
            df_ok = df_ok.sort_values('date_arrivee', ascending=False).reset_index()
            options = {i: f"{row['nom_client']} — arrivée {row['date_arrivee']}" for i, row in df_ok.iterrows()}
            choice = st.selectbox("Préremplir pour :", options=list(options.keys()),
                                  format_func=lambda i: options[i], index=0)
            sel = df_ok.loc[choice]
            res_id_val = _ensure_res_id_on_row(df, sel['index'])
            email_val = sel.get('email') if 'email' in df_ok.columns else None
            url_prefill = form_prefill_url(
                nom = sel.get('nom_client'),
                tel = sel.get('telephone'),
                email = email_val,
                date_arrivee = sel.get('date_arrivee'),
                date_depart  = sel.get('date_depart'),
                plateforme   = sel.get('plateforme'),
                nuitees      = sel.get('nuitees'),
                res_id       = res_id_val
            )
            st.markdown(f"**Lien à partager (court)** : {FORM_SHORT_URL}")
            st.components.v1.html("""
                <button onclick="navigator.clipboard.writeText('%s')"
                        style="margin-top:6px;padding:6px 10px;border-radius:8px;border:1px solid #888;background:#222;color:#fff;cursor:pointer">
                    📋 Copier le lien
                </button>
            """ % FORM_SHORT_URL, height=50)
            st.components.v1.iframe(url_prefill, height=950, scrolling=True)

    with tab_sheet:
        st.caption("Affichage intégré (lecture seule) de la feuille publiée (lien raccourci).")
        st.components.v1.iframe(GOOGLE_SHEET_EMBED_URL, height=900, scrolling=True)

    with tab_csv:
        st.caption("Lecture directe via l’URL 'Publier sur le Web' (CSV).")
        try:
            reponses = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
            st.dataframe(reponses, use_container_width=True)
            st.download_button("⬇️ Télécharger les réponses (CSV)",
                               data=reponses.to_csv(index=False).encode("utf-8"),
                               file_name="reponses_formulaire.csv", mime="text/csv")
        except Exception as e:
            st.error(f"Impossible de charger les réponses : {e}")
            st.info("Vérifie que la feuille est bien 'Publiée sur le Web' au format CSV et accessible.")

def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button(label="Télécharger la sauvegarde (CSV)",
        data=df.to_csv(sep=';', index=False).encode('utf-8'),
        file_name=CSV_RESERVATIONS, mime="text/csv")
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

# ==============================  MAIN  ==============================
def main():
    df, palette = charger_donnees_csv()

    # Endpoint ICS public si demandé par query params
    handled = icspublic_endpoint(df)
    if handled:
        return  # st.stop() est déjà appelé dans la fonction

    st.title("📖 Gestion des Réservations - Villa Tobias")
    st.sidebar.title("🧭 Navigation")
    pages = {
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,  # <- NOUVELLE VERSION
        "👥 Liste des Clients": vue_liste_clients,
        "✉️ SMS": vue_sms,
        "📆 Export ICS (Google Calendar)": vue_export_ics,
        "🔗 Flux ICS public (BETA)": vue_flux_ics_public,
        "📝 Fiche d'arrivée / Google Sheet": vue_google_sheet,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    page_function = pages[selection]
    if selection in ["➕ Ajouter","✏️ Modifier / Supprimer","🎨 Plateformes","📅 Calendrier","📊 Rapport","📆 Export ICS (Google Calendar)","🔗 Flux ICS public (BETA)","📝 Fiche d'arrivée / Google Sheet"]:
        page_function(df, palette)
    else:
        page_function(df)
    admin_sidebar(df)

if __name__ == "__main__":
    main()