# ==============================  IMPORTS & CONFIG  ==============================
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import hashlib, uuid, json, re, io, os, unicodedata, shutil
from datetime import date, datetime, timedelta
import calendar  # on utilise toujours calendar.monthrange
from urllib.parse import quote, urlencode  # <-- AJOUTÉ

# requests peut être absent des requirements ; on le charge en douceur
try:
    import requests
except Exception:  # pragma: no cover
    requests = None

# --- Fichiers CSV (fallback local) ---
CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES  = "reservations.xlsx - Plateformes.csv"

# --- Liens externes fournis ---
FORM_SHORT_URL = "https://urlr.me/kZuH94"  # lien court à partager
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pubhtml?gid=1915058425&single=true"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?gid=1915058425&single=true&output=csv"

DEFAULT_PALETTE = {"Booking": "#1e90ff", "Airbnb": "#e74c3c", "Autre": "#f59e0b"}

st.set_page_config(page_title="📖 Réservations Villa Tobias", page_icon="✨", layout="wide")

# ==============================  STYLE (clair/sombre) ==============================
def apply_modern_style(mode="dark"):
    if mode == "light":
        bg, panel, text, muted, chip = "#f6f7fb", "#ffffff", "#0f172a", "#475569", "#eef2ff"
        border, accent, grid = "rgba(17,24,39,.08)", "#7c5cff", "#e5e7eb"
        sidebar_bg, sidebar_border = "linear-gradient(180deg,#fff,#f9fafb)", "1px solid rgba(17,24,39,.08)"
    else:
        bg, panel, text, muted, chip = "#0f1115", "#171923", "#eaeef6", "#a0aec0", "#1f2230"
        border, accent, grid = "rgba(124,92,255,.16)", "#7c5cff", "#2a2f45"
        sidebar_bg, sidebar_border = "linear-gradient(180deg,#171923,#1e2130)", "1px solid rgba(124,92,255,.15)"

    st.markdown(f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap');
    body, [data-testid="stAppViewContainer"]{{background:{bg};}}
    * {{ font-family: 'Inter', system-ui, -apple-system, Segoe UI, Roboto, sans-serif; }}
    [data-testid="stSidebar"]{{background:{sidebar_bg};border-right:{sidebar_border};}}
    [data-testid="stSidebar"] *{{color:{text} !important;}}
    .glass{{background:{panel};border:1px solid {border};border-radius:16px;padding:16px;}}
    .chip{{background:{chip};border:1px solid {border};border-radius:12px;padding:10px 14px;}}
    .chip .lbl{{color:{muted};font-size:.85rem;}}
    .chip .val{{color:{text};font-weight:700;}}
    .stTabs [data-baseweb="tab"]{{background:{panel};color:{text};border:1px solid {border};}}
    .stTabs [aria-selected="true"]{{background:{bg};border-color:{accent};}}
    .calendar-day{{border:1px solid {grid}; background:{panel};}}
    .calendar-day.outside-month{{background: {'#1a1d2b' if mode=='dark' else '#f1f5f9'};}}
    .chips{{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0 16px 0;}}
    </style>
    """, unsafe_allow_html=True)

def enable_altair_theme():
    def _theme():
        return {"config":{
            "axis":{"labelColor":"#cbd5e1","titleColor":"#eaeef6","gridColor":"#2a2f45"},
            "legend":{"labelColor":"#cbd5e1","titleColor":"#eaeef6"},
            "title":{"color":"#eaeef6","font":"Inter","fontWeight":700}
        }}
    alt.themes.register("tobias", _theme); alt.themes.enable("tobias")

def card(title, body_md):
    st.markdown(f"<div class='glass'><div style='font-weight:700'>{title}</div><div>{body_md}</div></div>", unsafe_allow_html=True)

# ==============================  STORAGE MODE & PROXY  ==============================
def _get_storage_mode():
    try: return st.secrets["storage"]["mode"]
    except Exception: return "csv"

def _proxy_conf():
    try:
        conf = st.secrets["sheets_proxy"]
        base = conf["base_url"].rstrip("/")
        token = conf["token"]
        res_ws = conf.get("reservations_ws", "Reservations")
        plat_ws = conf.get("plateformes_ws", "Plateformes")
        return base, token, res_ws, plat_ws
    except Exception as e:
        raise RuntimeError(f"Configuration sheets_proxy manquante: {e}")

def proxy_read_ws(ws_name: str) -> pd.DataFrame:
    if requests is None:
        st.error("Le module 'requests' n'est pas installé. Bascule en CSV local.")
        return pd.DataFrame()
    base, token, _, _ = _proxy_conf()
    try:
        r = requests.get(base, params={"token": token, "ws": ws_name}, timeout=20)
        r.raise_for_status()
        payload = r.json()
        headers = payload.get("headers", [])
        rows = payload.get("rows", [])
        if not headers:
            return pd.DataFrame()
        return pd.DataFrame(rows, columns=headers)
    except Exception as e:
        st.error(f"Proxy GET échec ({ws_name}) : {e}")
        return pd.DataFrame()

def _df_to_rows(df: pd.DataFrame, date_cols=("date_arrivee","date_depart")):
    df2 = df.copy()
    for col in date_cols:
        if col in df2.columns:
            df2[col] = pd.to_datetime(df2[col], errors="coerce").dt.strftime("%d/%m/%Y")
    df2 = df2.astype(object).where(pd.notna(df2), "")
    headers = list(df2.columns)
    rows = df2.values.tolist()
    return headers, rows

def proxy_replace_ws(ws_name: str, df: pd.DataFrame) -> bool:
    if requests is None:
        st.error("Le module 'requests' n'est pas installé. Bascule en CSV local.")
        return False
    base, token, _, _ = _proxy_conf()
    try:
        headers, rows = _df_to_rows(df)
        r = requests.post(
            base,
            json={"token": token, "action": "replace", "ws": ws_name, "headers": headers, "rows": rows},
            timeout=30
        )
        r.raise_for_status()
        ok = r.json().get("ok", False)
        return bool(ok)
    except Exception as e:
        st.error(f"Proxy REPLACE échec ({ws_name}) : {e}")
        return False

# ==============================  SCHEMA & CLEAN ==============================
BASE_COLS = [
    'res_id','ical_uid',
    'paye','sms_envoye','post_depart_envoye',
    'nom_client','email','telephone','lang',
    'plateforme',
    'date_arrivee','date_depart','nuitees',
    'prix_brut','prix_net','commissions','frais_cb','menage','taxes_sejour',
    'base','charges','%','AAAA','MM'
]

def ensure_schema(df):
    if not isinstance(df, pd.DataFrame) or df is None or df.empty:
        return pd.DataFrame(columns=BASE_COLS)
    df_res = df.copy()

    for col in BASE_COLS:
        if col not in df_res.columns: df_res[col] = None

    for col in ["date_arrivee","date_depart"]:
        df_res[col] = pd.to_datetime(df_res[col], dayfirst=True, errors='coerce').dt.date

    mask = df_res['date_arrivee'].notna() & df_res['date_depart'].notna()
    df_res.loc[mask,'nuitees'] = (
        pd.to_datetime(df_res.loc[mask,'date_depart']) - pd.to_datetime(df_res.loc[mask,'date_arrivee'])
    ).dt.days

    df_res['AAAA'] = pd.to_datetime(df_res['date_arrivee'], errors='coerce').dt.year
    df_res['MM']   = pd.to_datetime(df_res['date_arrivee'], errors='coerce').dt.month

    def _to_bool(s):
        return s.astype(str).str.strip().str.lower().isin(['true','vrai','1','oui','yes'])
    for bcol in ['paye','sms_envoye','post_depart_envoye']:
        df_res[bcol] = _to_bool(df_res[bcol]).fillna(False).astype(bool)

    for col in ['prix_brut','commissions','frais_cb','menage','taxes_sejour','prix_net']:
        df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0.0)
    df_res['prix_net'] = df_res['prix_brut'] - df_res['commissions'] - df_res['frais_cb']
    df_res['charges']  = df_res['prix_brut'] - df_res['prix_net']
    df_res['base']     = df_res['prix_net']  - df_res['menage'] - df_res['taxes_sejour']
    with np.errstate(divide='ignore', invalid='ignore'):
        df_res['%'] = np.where(df_res['prix_brut']>0, df_res['charges']/df_res['prix_brut']*100, 0)

    df_res['lang'] = (df_res['lang'].fillna('FR').astype(str).str.upper()).replace({'NAN':'FR'})

    if 'res_id' in df_res.columns:
        missing = df_res['res_id'].isna() | (df_res['res_id'].astype(str).str.strip()=="")
        df_res.loc[missing,'res_id'] = [str(uuid.uuid4()) for _ in range(int(missing.sum()))]

    return df_res

# ==============================  CHARGEMENT / SAUVEGARDE ==============================
@st.cache_data
def charger_donnees():
    mode = _get_storage_mode()

    if mode == "sheets_proxy":
        try:
            _, _, res_ws, plat_ws = _proxy_conf()
            df_res = proxy_read_ws(res_ws)
            df_pal = proxy_read_ws(plat_ws)
            df_res = ensure_schema(df_res)
            palette = DEFAULT_PALETTE.copy()
            if not df_pal.empty and {"plateforme","couleur"} <= set(df_pal.columns):
                palette.update(dict(zip(df_pal["plateforme"], df_pal["couleur"])))
            return df_res, palette
        except Exception as e:
            st.error(f"Lecture Google Sheets impossible : {e}. Bascule CSV local.")

    try:
        df_res = pd.read_csv(CSV_RESERVATIONS, delimiter=";")
        df_res.columns = df_res.columns.str.strip()
    except Exception:
        df_res = pd.DataFrame()
    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";")
        palette = DEFAULT_PALETTE | dict(zip(df_pal["plateforme"], df_pal["couleur"]))
    except Exception:
        palette = DEFAULT_PALETTE.copy()
    return ensure_schema(df_res), palette

def sauvegarder_donnees(df, palette=None):
    try:
        if os.path.exists(CSV_RESERVATIONS):
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            shutil.copyfile(CSV_RESERVATIONS, f"{CSV_RESERVATIONS}.backup_{stamp}")
    except Exception:
        pass

    mode = _get_storage_mode()

    if mode == "sheets_proxy":
        try:
            _, _, res_ws, plat_ws = _proxy_conf()
            df_to_save = ensure_schema(df.copy())
            cols = [c for c in BASE_COLS if c in df_to_save.columns] or list(df_to_save.columns)
            ok1 = proxy_replace_ws(res_ws, df_to_save[cols])
            ok2 = True
            if palette is not None:
                df_p = pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"])
                ok2 = proxy_replace_ws(plat_ws, df_p)
            if ok1 and ok2:
                st.cache_data.clear()
                return True
            st.error("Écriture proxy incomplète (Reservations/Plateformes).")
            return False
        except Exception as e:
            st.error(f"Erreur de sauvegarde via proxy : {e}")
            return False

    try:
        df.to_csv(CSV_RESERVATIONS, sep=";", index=False)
        if palette is not None:
            pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"]).to_csv(CSV_PLATEFORMES, sep=";", index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde (CSV) : {e}")
        return False

# ==============================  HELPERS GÉNÉRAUX ==============================
def _safe_div(a,b): 
    try:
        a = float(a); b = float(b)
        return (a/b) if b else None
    except: return None

def _fmt_eur(x): 
    try: return f"{float(x):,.2f} €".replace(",", " ")
    except: return "—"

def _format_phone_e164(raw_phone: str) -> str:
    raw_phone = str(raw_phone or "")
    clean = re.sub(r"\D", "", raw_phone)
    if raw_phone.strip().startswith("+"):  # déjà international
        return raw_phone.strip()
    if clean.startswith("0") and len(clean) == 10:  # FR
        return "+33" + clean[1:]
    if clean:
        return "+33" + clean
    return raw_phone.strip()

# ==============================  UID STABLE & ICS  ==============================
PROPERTY_ID = "villa-tobias"
NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://villa-tobias.fr/reservations")

def _canonize_text(s: str) -> str:
    if s is None: return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize('NFKD', s)
    return "".join(ch for ch in s if not unicodedata.combining(ch))

def _canonize_phone(s: str) -> str:
    if s is None: return ""
    return re.sub(r"\D", "", str(s))

def build_stable_uid(row) -> str:
    res_id = str(row.get('res_id') or "").strip()
    canonical = "|".join([PROPERTY_ID, res_id, _canonize_text(row.get('nom_client','')), _canonize_phone(row.get('telephone',''))])
    return str(uuid.uuid5(NAMESPACE, canonical))

def _compute_uid(r):
    uid = r.get('ical_uid')
    if isinstance(uid, str) and uid.strip(): return uid
    return build_stable_uid(r)

def _fmt_ics_date(d: date) -> str:
    return f"{d.year:04d}{d.month:02d}{d.day:02d}"

def _escape_text(s: str) -> str:
    if s is None: return ""
    return str(s).replace('\\','\\\\').replace(';','\\;').replace(',','\\,').replace('\n','\\n')

def build_ics_from_df(df_src: pd.DataFrame) -> str:
    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR",
        "CALSCALE:GREGORIAN","METHOD:PUBLISH",
    ]
    for _, r in df_src.iterrows():
        da, dd = r['date_arrivee'], r['date_depart']
        if not isinstance(da, date) or not isinstance(dd, date): 
            continue
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

# ==============================  VUES DE BASE ==============================
def kpi_chips(df, title="Indicateurs Clés"):
    st.subheader(title)
    if df.empty:
        st.warning("Pas de données à afficher."); return
    totals = {
        "Total Brut": df["prix_brut"].sum(),
        "Total Net": df["prix_net"].sum(),
        "Total Commissions": df["commissions"].sum(),
        "Total Frais CB": df["frais_cb"].sum(),
        "Total Ménage": df["menage"].sum(),
        "Total Base": df["base"].sum(),
        "Nuitées": df["nuitees"].sum(),
    }
    chips = "".join([
        f'<div class="chip"><div class="lbl">{k}</div><div class="val">{(f"{v:,.2f} €".replace(",", " ")) if "Nuitées" not in k else int(v)}</div></div>'
        for k,v in totals.items()
    ])
    st.markdown(f"<div class='chips'>{chips}</div>", unsafe_allow_html=True)

def vue_reservations(df, palette):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation."); return
    df_valid = df.dropna(subset=['AAAA','MM'])
    c1, c2, c3 = st.columns(3)
    annees = ["Toutes"] + sorted(df_valid['AAAA'].dropna().astype(int).unique(), reverse=True)
    mois_options = ["Tous"] + list(range(1,13))
    mois_selectionne = c2.selectbox("Filtrer par Mois", mois_options)
    plats_opts = ["Toutes"] + sorted(df_valid['plateforme'].dropna().unique())
    annee_selectionnee = c1.selectbox("Filtrer par Année", annees)
    plateforme_selectionnee = c3.selectbox("Filtrer par Plateforme", plats_opts)

    data = df_valid.copy()
    if annee_selectionnee != "Toutes": data = data[data['AAAA'] == annee_selectionnee]
    if mois_selectionne != "Tous": data = data[data['MM'] == mois_selectionne]
    if plateforme_selectionnee != "Toutes": data = data[data['plateforme'] == plateforme_selectionnee]

    kpi_chips(data, "Totaux pour la sélection")
    st.markdown("---")

    df_sorted = data.sort_values(by="date_arrivee", ascending=False, na_position='last').reset_index(drop=True)
    colcfg = {
        "paye": st.column_config.CheckboxColumn("Payé"),
        "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
        "post_depart_envoye": st.column_config.CheckboxColumn("Post-départ envoyé"),
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
    }
    edited = st.data_editor(
        df_sorted,
        use_container_width=True,
        column_config=colcfg,
        disabled=[],
        hide_index=True
    )
    if not edited.equals(df_sorted):
        df_copy = df.copy()
        for i, row in edited.iterrows():
            mask = df_copy['res_id'] == row.get('res_id')
            if not (mask.any()):
                mask = (df_copy['nom_client']==row.get('nom_client')) & \
                       (df_copy['date_arrivee']==row.get('date_arrivee')) & \
                       (df_copy['date_depart']==row.get('date_depart'))
            for col in ['paye','sms_envoye','post_depart_envoye','prix_brut','commissions','frais_cb','menage','taxes_sejour','plateforme','telephone','email','lang']:
                if col in df_copy.columns and col in row.index:
                    df_copy.loc[mask, col] = row[col]
        df_final = ensure_schema(df_copy)
        if sauvegarder_donnees(df_final):
            st.success("Modifications enregistrées."); st.rerun()

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une Réservation")
    with st.form("form_ajout", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom_client = st.text_input("Nom du Client")
            email = st.text_input("Email (optionnel)")
            telephone = st.text_input("Téléphone")
            lang = st.selectbox("Langue", ["FR","EN"], index=0)
        with c2:
            date_arrivee = st.date_input("Date d'arrivée", date.today())
            date_depart = st.date_input("Date de départ", date.today() + timedelta(days=1))
            plateforme = st.selectbox("Plateforme", options=list(palette.keys()))
            paye = st.checkbox("Payé", False)
        c3, c4, c5 = st.columns(3)
        with c3:
            prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, step=0.01, format="%.2f")
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01, format="%.2f")
        with c4:
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01, format="%.2f")
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01, format="%.2f")
        with c5:
            taxes_sejour = st.number_input("Taxes Séjour (€)", min_value=0.0, step=0.01, format="%.2f")

        submitted = st.form_submit_button("✅ Ajouter la réservation")
        if submitted:
            if not nom_client or date_depart <= date_arrivee:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nouvelle = pd.DataFrame([{
                    'res_id': str(uuid.uuid4()),
                    'nom_client': nom_client, 'email': email if email else "",
                    'telephone': telephone, 'lang': lang,
                    'date_arrivee': date_arrivee, 'date_depart': date_depart,
                    'plateforme': plateforme, 'paye': paye,
                    'prix_brut': prix_brut, 'commissions': commissions, 'frais_cb': frais_cb,
                    'menage': menage, 'taxes_sejour': taxes_sejour
                }])
                df_new = ensure_schema(pd.concat([df, nouvelle], ignore_index=True))
                if sauvegarder_donnees(df_new):
                    st.success(f"Réservation pour {nom_client} ajoutée."); st.rerun()

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer une Réservation")
    if df.empty:
        st.warning("Aucune réservation."); return
    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {row['nom_client']} ({row['date_arrivee']})" for i, row in df_sorted.iterrows() if pd.notna(row['date_arrivee'])]
    selection = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if selection:
        idx = int(selection.split(":")[0])
        original_index = df_sorted.loc[idx, 'index']
        resa = df.loc[original_index].copy()
        with st.form(f"form_modif_{original_index}"):
            c1, c2 = st.columns(2)
            with c1:
                nom_client = st.text_input("Nom du Client", value=resa.get('nom_client',''))
                email      = st.text_input("Email", value=resa.get('email','') or '')
                telephone  = st.text_input("Téléphone", value=resa.get('telephone','') or '')
                lang       = st.selectbox("Langue", ["FR","EN"], index=0 if (resa.get('lang','FR')=='FR') else 1)
                date_arrivee = st.date_input("Date d'arrivée", value=resa.get('date_arrivee'))
                date_depart  = st.date_input("Date de départ", value=resa.get('date_depart'))
            with c2:
                plateforme_options = list(palette.keys())
                cur_plat = resa.get('plateforme')
                p_index = plateforme_options.index(cur_plat) if cur_plat in plateforme_options else 0
                plateforme = st.selectbox("Plateforme", options=plateforme_options, index=p_index)
                prix_brut   = st.number_input("Prix Brut (€)", min_value=0.0, value=float(resa.get('prix_brut',0.0)), step=0.01, format="%.2f")
                commissions = st.number_input("Commissions (€)", min_value=0.0, value=float(resa.get('commissions',0.0)), step=0.01, format="%.2f")
                frais_cb    = st.number_input("Frais CB (€)", min_value=0.0, value=float(resa.get('frais_cb',0.0)), step=0.01, format="%.2f")
                menage      = st.number_input("Ménage (€)", min_value=0.0, value=float(resa.get('menage',0.0)), step=0.01, format="%.2f")
                taxes_sejour= st.number_input("Taxes Séjour (€)", min_value=0.0, value=float(resa.get('taxes_sejour',0.0)), step=0.01, format="%.2f")
                paye        = st.checkbox("Payé", value=bool(resa.get('paye', False)))
            b1, b2 = st.columns([.8,.2])
            if b1.form_submit_button("💾 Enregistrer"):
                updates = {
                    'nom_client': nom_client, 'email': email, 'telephone': telephone, 'lang': lang,
                    'date_arrivee': date_arrivee, 'date_depart': date_depart,
                    'plateforme': plateforme, 'prix_brut': prix_brut, 'commissions': commissions,
                    'frais_cb': frais_cb, 'menage': menage, 'taxes_sejour': taxes_sejour, 'paye': paye
                }
                for k,v in updates.items(): df.loc[original_index, k] = v
                df_final = ensure_schema(df)
                if sauvegarder_donnees(df_final):
                    st.success("Modifications enregistrées !"); st.rerun()
            if b2.form_submit_button("🗑️ Supprimer"):
                df_final = df.drop(index=original_index)
                if sauvegarder_donnees(df_final):
                    st.warning("Réservation supprimée."); st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Gestion des Plateformes")
    df_palette = pd.DataFrame(list(palette.items()), columns=['plateforme','couleur'])
    edited = st.data_editor(df_palette, num_rows="dynamic", use_container_width=True, hide_index=True,
                            column_config={"plateforme": "Plateforme", "couleur": st.column_config.TextColumn("Couleur (hex)")})
    if st.button("💾 Enregistrer la palette"):
        nouvelle = dict(zip(edited['plateforme'], edited['couleur']))
        if sauvegarder_donnees(df, palette=nouvelle):
            st.success("Palette mise à jour !"); st.rerun()

def vue_calendrier(df, palette):
    st.header("📅 Calendrier des Réservations")
    dfv = df.dropna(subset=['date_arrivee','date_depart','AAAA'])
    if dfv.empty:
        st.info("Aucune réservation."); return
    c1, c2 = st.columns(2)
    today = date.today()
    noms_mois = [calendar.month_name[i] for i in range(1,13)]
    selected_month_name = c1.selectbox("Mois", options=noms_mois, index=today.month-1)
    selected_month = noms_mois.index(selected_month_name) + 1
    years = sorted(dfv['AAAA'].dropna().astype(int).unique())
    default_year_index = years.index(today.year) if today.year in years else len(years)-1
    selected_year = c2.selectbox("Année", options=years, index=default_year_index)
    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(selected_year, selected_month)
    st.markdown("""<style>.calendar-day{min-height:120px;padding:5px;vertical-align:top;border-radius:8px}.calendar-date{font-weight:700;font-size:1.1em;margin-bottom:5px;text-align:right}.reservation-bar{padding:3px 6px;margin-bottom:3px;border-radius:5px;font-size:.9em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}</style>""", unsafe_allow_html=True)
    headers = ["Lundi","Mardi","Mercredi","Jeudi","Vendredi","Samedi","Dimanche"]
    st.write(f'<div style="display:grid;grid-template-columns:repeat(7,1fr);text-align:center;font-weight:700">{"".join(f"<div>{h}</div>" for h in headers)}</div>', unsafe_allow_html=True)
    for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                day_class = "outside-month" if day.month != selected_month else ""
                day_html = f"<div class='calendar-day {day_class}'><div class='calendar-date'>{day.day}</div>"
                for _, resa in dfv.iterrows():
                    if isinstance(resa['date_arrivee'], date) and isinstance(resa['date_depart'], date):
                        if resa['date_arrivee'] <= day < resa['date_depart']:
                            color = palette.get(resa['plateforme'], '#888'); text_color = "#FFF"
                            day_html += f"<div class='reservation-bar' style='background-color:{color};color:{text_color}' title='{resa['nom_client']}'>{resa['nom_client']}</div>"
                day_html += "</div>"
                st.markdown(day_html, unsafe_allow_html=True)

# ==============================  RAPPORT ==============================
def _available_nights_by_month(year: int):
    return {date(year, m, 1): calendar.monthrange(year, m)[1] for m in range(1,13)}

def _expand_to_daily(df):
    rows = []
    for _, r in df.iterrows():
        da, dd = r.get("date_arrivee"), r.get("date_depart")
        if isinstance(da, date) and isinstance(dd, date) and dd > da:
            cur = da
            while cur < dd:
                rows.append({"day": cur, "plateforme": r.get("plateforme"),
                             "prix_brut": float(r.get("prix_brut") or 0),
                             "prix_net": float(r.get("prix_net") or 0),
                             "res_id": r.get("res_id")})
                cur += timedelta(days=1)
    return pd.DataFrame(rows)

def vue_rapport(df, palette):
    enable_altair_theme()
    st.header("📊 Rapport de Performance")
    card("Mode d'emploi", "Choisissez **Année/Mois/Plateformes** et la **métrique**. Explorez les tendances et exportez le CSV.")
    base = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if base.empty:
        st.info("Aucune donnée pour générer un rapport."); return

    c0, c1, c2, c3 = st.columns([1,1.2,1.2,1.8])
    years = sorted({d.year for d in base['date_arrivee'] if isinstance(d, date)}, reverse=True)
    annee = c0.selectbox("Année", years, index=0)

    mois_labels = ["Jan","Fév","Mar","Avr","Mai","Juin","Juil","Aoû","Sep","Oct","Nov","Déc"]
    mois_opts = ["Tous"] + [f"{i:02d} — {mois_labels[i-1]}" for i in range(1,13)]
    mois_sel = c1.multiselect("Mois", mois_opts, default=["Tous"])

    all_plats = sorted([p for p in base['plateforme'].dropna().unique()])
    plats_sel = c2.multiselect("Plateformes (déroulant)", ["Tous"]+all_plats, default=["Tous"])
    plats_effectifs = all_plats if ("Tous" in plats_sel or not plats_sel) else [p for p in plats_sel if p!="Tous"]

    paid_only  = c3.toggle("Uniquement réservations payées", value=False)
    metric_mode = st.radio("Mode de revenu", ["Brut","Net"], index=0, horizontal=True)
    mcol = "prix_brut" if metric_mode=="Brut" else "prix_net"

    data = base[(pd.Series([isinstance(d, date) and d.year==annee for d in base['date_arrivee']]))].copy()
    mois_int = list(range(1,13)) if ("Tous" in mois_sel or not mois_sel) else [int(s.split(" — ")[0]) for s in mois_sel]
    data = data[data['date_arrivee'].apply(lambda d: d.month in mois_int)]
    if plats_effectifs: data = data[data['plateforme'].isin(plats_effectifs)]
    if paid_only: data = data[data['paye']==True]
    if data.empty:
        st.warning("Aucune donnée après filtres."); return

    nb_res = len(data)
    nuits = int(data['nuitees'].fillna(0).sum())
    rev_total = float(data[mcol].fillna(0).sum())
    adr = _safe_div(rev_total, nuits)
    avail_by_month = _available_nights_by_month(annee)
    avail_year = sum(avail_by_month[date(annee, m, 1)] for m in mois_int)
    occ = _safe_div(nuits, avail_year)
    revpar = _safe_div(rev_total, avail_year)

    with st.container():
        st.markdown("<div class='glass'>", unsafe_allow_html=True)
        k1,k2,k3,k4,k5,k6 = st.columns(6)
        k1.metric("Réservations", f"{nb_res}")
        k2.metric("Nuitées vendues", f"{nuits}")
        k3.metric(f"Revenu {metric_mode.lower()}", _fmt_eur(rev_total))
        k4.metric(f"ADR {metric_mode.lower()}", _fmt_eur(adr) if pd.notna(adr) else "—")
        k5.metric("Taux d’occupation", f"{(occ or 0)*100:,.1f} %".replace(",", " "))
        k6.metric(f"RevPAR {metric_mode.lower()}", _fmt_eur(revpar) if pd.notna(revpar) else "—")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")
    data['mois'] = data['date_arrivee'].apply(lambda d: date(d.year,d.month,1))
    grp = (data.groupby(['plateforme','mois'], as_index=False).agg({mcol:'sum','nuitees':'sum'}))
    months_all = [date(annee, m, 1) for m in mois_int]
    frames=[]
    plats_loop = plats_effectifs if plats_effectifs else all_plats
    for p in plats_loop:
        g = grp[grp['plateforme']==p].set_index('mois').reindex(months_all).fillna({mcol:0.0,'nuitees':0.0})
        g['plateforme']=p; g=g.reset_index().rename(columns={'index':'mois'}); frames.append(g)
    grp_full = pd.concat(frames, ignore_index=True)
    avail_map = {date(annee,m,1): _available_nights_by_month(annee)[date(annee,m,1)] for m in mois_int}
    grp_full['available'] = grp_full['mois'].map(avail_map)
    grp_full['adr']    = grp_full.apply(lambda r: _safe_div(r[mcol], r['nuitees']), axis=1)
    grp_full['occ']    = grp_full.apply(lambda r: _safe_div(r['nuitees'], r['available']), axis=1)
    grp_full['revpar'] = grp_full.apply(lambda r: _safe_div(r[mcol], r['available']), axis=1)

    st.subheader("Tendances par mois")
    colA, colB = st.columns(2)
    choix_serie = colA.selectbox("Série", [f"Revenu {metric_mode.lower()}","Nuitées",f"ADR {metric_mode.lower()}","Occupation",f"RevPAR {metric_mode.lower()}"])
    stack = colB.toggle("Empiler (total mensuel)", value=False)
    serie_map = {
        f"Revenu {metric_mode.lower()}": ("value", mcol, ".2f"),
        "Nuitées": ("nuitees","nuitees",".0f"),
        f"ADR {metric_mode.lower()}": ("adr","adr",".2f"),
        "Occupation": ("occ","occ",".1%"),
        f"RevPAR {metric_mode.lower()}": ("revpar","revpar",".2f"),
    }
    yfield, realfield, fmt = serie_map[choix_serie]
    grp_full[yfield] = grp_full[realfield]
    color_map = {p: DEFAULT_PALETTE.get(p, '#888') for p in plats_loop}
    domain_sel = list(color_map.keys()); range_sel = [color_map[p] for p in domain_sel]

    base_chart = alt.Chart(grp_full).encode(
        x=alt.X('yearmonth(mois):T', title='Mois'),
        color=alt.Color('plateforme:N', scale=alt.Scale(domain=domain_sel, range=range_sel), title="Plateforme"),
        tooltip=[alt.Tooltip('plateforme:N'), alt.Tooltip('yearmonth(mois):T', title='Mois'), alt.Tooltip(f'{yfield}:Q', title=choix_serie, format=fmt)]
    )
    if choix_serie in [f"Revenu {metric_mode.lower()}","Nuitées"] and stack:
        chart = base_chart.mark_bar().encode(y=alt.Y(f'{yfield}:Q', title=choix_serie, stack='zero'))
    else:
        if choix_serie in [f"Revenu {metric_mode.lower()}","Nuitées"]:
            chart = base_chart.mark_bar().encode(y=alt.Y(f'{yfield}:Q', title=choix_serie), xOffset=alt.X('plateforme:N', title=None))
        else:
            chart = base_chart.mark_line(point=True).encode(y=alt.Y(f'{yfield}:Q', title=choix_serie))
    st.altair_chart(chart.properties(height=420).interactive(), use_container_width=True)

    st.markdown("---")
    st.subheader("Répartition par plateforme")
    mix = (data.groupby("plateforme", as_index=False).agg(revenu=(mcol,'sum'), nuitées=('nuitees','sum'), sejours=('res_id','count')))
    c1,c2 = st.columns([2,1])
    chart_mix = alt.Chart(mix).mark_bar().encode(
        x=alt.X('plateforme:N', title='Plateforme'),
        y=alt.Y('revenu:Q', title=f'Revenu {metric_mode.lower()}'),
        color=alt.Color('plateforme:N', legend=None, scale=alt.Scale(domain=domain_sel, range=range_sel)),
        tooltip=[alt.Tooltip('plateforme:N'), alt.Tooltip('revenu:Q', format='.2f'), alt.Tooltip('nuitées:Q'), alt.Tooltip('sejours:Q')]
    )
    c1.altair_chart(chart_mix.properties(height=320), use_container_width=True)
    c2.dataframe(mix.sort_values('revenu', ascending=False), use_container_width=True)

    st.markdown("---")
    st.subheader("Heatmap d’occupation")
    daily = _expand_to_daily(data)
    if daily.empty:
        st.info("Pas assez de données.")
    else:
        daily['mois'] = daily['day'].apply(lambda d: date(d.year, d.month, 1))
        occ_days = (daily.groupby('day', as_index=False).agg(occ=('res_id','nunique'))); occ_days['occ']=occ_days['occ'].clip(0,1)
        all_days=[]
        for m in mois_int:
            rng = pd.date_range(f"{annee}-{m:02d}-01", f"{annee}-{m:02d}-{calendar.monthrange(annee, m)[1]}", freq="D").date
            all_days += list(rng)
        all_days = pd.DataFrame({"day": all_days})
        all_days = all_days.merge(occ_days[['day','occ']], on='day', how='left').fillna({'occ':0})
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
    st.subheader("Export CSV")
    with st.expander("Données mensuelles"):
        export = grp_full[['mois','plateforme', mcol, 'nuitees', 'adr', 'occ', 'revpar']].copy()
        export = export.rename(columns={'mois':'Mois','plateforme':'Plateforme', mcol:f"Revenu_{metric_mode.lower()}",
                                        'nuitees':'Nuitées','adr':f"ADR_{metric_mode.lower()}",
                                        'occ':'Occupation','revpar':f"RevPAR_{metric_mode.lower()}"})
        export = export[export['Plateforme'].notna() & (export['Plateforme'].astype(str).str.strip()!="")]
        st.dataframe(export.sort_values(['Mois','Plateforme']), use_container_width=True)
        st.download_button("⬇️ Télécharger CSV mensuel", data=export.to_csv(index=False, sep=';').encode('utf-8'),
                           file_name=f"rapport_{annee}_{metric_mode.lower()}_mois_{'-'.join([f'{m:02d}' for m in mois_int])}.csv",
                           mime="text/csv")

# ==============================  SMS & WHATSAPP ==============================
LANG_TEMPLATES = {
    "FR": {
        "pre_arrivee": """VILLA TOBIAS
Plateforme : {plateforme}
Arrivée : {arrivee} Départ : {depart} Nuitées : {nuitees}

Bonjour {nom}
Téléphone : {tel}

Bienvenue chez nous !

Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre arrivée, merci de nous indiquer votre heure d'arrivée.

Une place de parking est disponible si besoin.
Check-in : 14:00 — Check-out : 11:00.

Nous vous souhaitons un excellent voyage et avons hâte de vous rencontrer.

Annick & Charley

Merci de remplir la fiche d'arrivée :
{form_link}""",
        "post_depart": """Bonjour {nom},

Un grand merci d'avoir choisi notre appartement pour votre séjour.
Nous espérons que vous avez passé un moment agréable.

Si l'envie vous prend de revenir explorer encore un peu notre ville, notre porte vous sera toujours ouverte.

Au plaisir de vous accueillir à nouveau.

Annick & Charley"""
    },
    "EN": {
        "pre_arrivee": """VILLA TOBIAS
Platform: {plateforme}
Arrival: {arrivee} Departure: {depart} Nights: {nuitees}

Hello {nom}
Phone: {tel}

Welcome!

We're delighted to host you soon in Nice. To best arrange your arrival, please share your ETA.

A parking spot is available if needed.
Check-in: 2:00 PM — Check-out: 11:00 AM.

We wish you a pleasant trip and look forward to meeting you.

Annick & Charley

Please fill out the arrival form:
{form_link}""",
        "post_depart": """Hello {nom},

Thank you very much for choosing our apartment for your stay.
We hope you had a wonderful time.

If you feel like coming back to explore our city more, our door will always be open to you.

We look forward to welcoming you back.

Annick & Charley"""
    }
}

def _post_depart_message(name: str, lang: str="FR") -> str:
    tpl = LANG_TEMPLATES.get(lang, LANG_TEMPLATES['FR'])["post_depart"]
    return tpl.format(nom=(name or "").strip())

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")
    card("Aide", "Pré-arrivée (**arrivées J+1**) et **post-départ** (départs du jour). Le lien formulaire est **court**.")

    # --- Sécurisation d'entrée ---
    if not isinstance(df, pd.DataFrame):
        try:
            df = pd.DataFrame(df if df is not None else [])
        except Exception:
            df = pd.DataFrame()
    df = ensure_schema(df)

    # Colonnes bool assurées
    for colb in ('sms_envoye', 'post_depart_envoye'):
        if colb not in df.columns:
            df[colb] = False
        df[colb] = df[colb].fillna(False).astype(bool)

    # =====================  PRÉ-ARRIVÉE (J+1)  =====================
    st.subheader("🛬 Messages pré-arrivée (J+1)")
    target_arrivee = st.date_input("Cibler les arrivées du", date.today() + timedelta(days=1), key="prearrivee_date")

    df_tel = df.dropna(subset=['telephone', 'nom_client', 'date_arrivee']).copy()
    for c in ('date_arrivee', 'date_depart'):
        if c in df_tel.columns:
            df_tel[c] = pd.to_datetime(df_tel[c], errors='coerce').dt.date

    df_tel = df_tel[(df_tel['date_arrivee'] == target_arrivee) & (~df_tel['sms_envoye'])].copy()
    if not df_tel.empty:
        df_tel['tel_clean'] = df_tel['telephone'].astype(str).str.replace(r'\D', '', regex=True).str.lstrip('0')
        df_tel = df_tel[df_tel['tel_clean'].str.len().between(9, 15)].copy()
        df_tel["_rowid"] = df_tel.index

    st.components.v1.html(
        f"""
        <button onclick="navigator.clipboard.writeText('{FORM_SHORT_URL}')"
                style="margin-bottom:10px;padding:8px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#222;color:#fff;cursor:pointer">
            📋 Copier le lien (formulaire)
        </button>
        """,
        height=48
    )

    if df_tel.empty:
        st.info("Aucun client à contacter (ou déjà marqué 'SMS envoyé').")
    else:
        df_sorted = df_tel.sort_values(by="date_arrivee").reset_index(drop=True)
        options = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in df_sorted.iterrows()]
        selection = st.selectbox(
            "Sélectionnez un client (pré-arrivée)",
            options=options,
            index=None,
            key="prearrival_select"
        )
        if selection:
            idx = int(selection.split(":")[0])
            resa = df_sorted.loc[idx]
            lang = str(resa.get('lang') or 'FR').upper()
            tpl = LANG_TEMPLATES.get(lang, LANG_TEMPLATES['FR'])["pre_arrivee"]
            message_body = tpl.format(
                plateforme=resa.get('plateforme', 'N/A'),
                arrivee=resa.get('date_arrivee').strftime('%d/%m/%Y') if pd.notna(resa.get('date_arrivee')) else '',
                depart=resa.get('date_depart').strftime('%d/%m/%Y') if pd.notna(resa.get('date_depart')) else '',
                nuitees=int(resa.get('nuitees') or 0),
                nom=resa.get('nom_client') or '',
                tel=resa.get('telephone') or '',
                form_link=FORM_SHORT_URL
            )
            enc = quote(message_body)
            e164 = _format_phone_e164(resa['telephone'])
            wa_num = re.sub(r"\D", "", e164)

            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa_num}?text={enc}")

            st.components.v1.html(
                f"""
                <div style="margin-top:8px;display:flex;gap:8px;flex-wrap:wrap">
                  <button onclick="navigator.clipboard.writeText({json.dumps(message_body)})"
                          style="padding:8px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#222;color:#fff;cursor:pointer">
                      📋 Copier le message
                  </button>
                  <button onclick="navigator.clipboard.writeText('{FORM_SHORT_URL}')"
                          style="padding:8px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#222;color:#fff;cursor:pointer">
                      📋 Copier le lien (formulaire)
                  </button>
                </div>
                """,
                height=60
            )

            # --- CLÉ UNIQUE POUR ÉVITER CONFLIT ---
            if st.button("✅ Marquer 'SMS envoyé'", key=f"mark_pre_sent_{resa['_rowid']}"):
                try:
                    df.loc[resa["_rowid"], 'sms_envoye'] = True
                    df_final = ensure_schema(df)
                    if sauvegarder_donnees(df_final):
                        st.success("Marqué 'SMS envoyé' ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    # =====================  POST-DÉPART (J)  =====================
    st.markdown("---")
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="postdepart_date")

    df_safe = ensure_schema(df.copy())
    for col in ('date_arrivee', 'date_depart'):
        if col in df_safe.columns:
            df_safe[col] = pd.to_datetime(df_safe[col], errors='coerce').dt.date
    if 'post_depart_envoye' not in df_safe.columns:
        df_safe['post_depart_envoye'] = False
    df_safe['post_depart_envoye'] = df_safe['post_depart_envoye'].fillna(False).astype(bool)

    needed_cols = ['telephone', 'nom_client', 'date_depart']
    if not all(c in df_safe.columns for c in needed_cols):
        st.warning("Colonnes indispensables manquantes (telephone/nom_client/date_depart).")
        df_post = pd.DataFrame()
    else:
        df_post = df_safe.dropna(subset=needed_cols).copy()
        df_post = df_post[(df_post['date_depart'] == target_depart) & (~df_post['post_depart_envoye'])].copy()

    if not df_post.empty:
        df_post['tel_clean'] = df_post['telephone'].astype(str).str.replace(r'\D', '', regex=True).str.lstrip('0')
        df_post = df_post[df_post['tel_clean'].str.len().between(9, 15)].copy()
        df_post["_rowid"] = df_post.index

    if df_post.empty:
        st.info("Aucun message post-départ à envoyer aujourd’hui.")
    else:
        try:
            df_sorted2 = df_post.sort_values(by="date_depart").reset_index(drop=True)
        except Exception:
            df_sorted2 = df_post.reset_index(drop=True)

        options_post = [
            f"{i}: {r['nom_client']} — départ {r['date_depart']}"
            for i, r in df_sorted2.iterrows()
        ]
        selection2 = st.selectbox(
            "Sélectionnez un client (post-départ)",
            options=options_post,
            index=None,
            key="post_select"
        )

        if selection2:
            idx2 = int(selection2.split(":")[0])
            resa2 = df_sorted2.loc[idx2]
            lang = str(resa2.get('lang') or 'FR').upper()
            msg = _post_depart_message(resa2.get('nom_client'), lang)
            enc = quote(msg)
            e164 = _format_phone_e164(resa2['telephone'])
            wa_num = re.sub(r"\D", "", e164)

            cwa, cios, cand = st.columns(3)
            cwa.link_button("🟢 WhatsApp", f"https://wa.me/{wa_num}?text={enc}")
            cios.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            cand.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")

            st.components.v1.html(
                f"""
                <button onclick="navigator.clipboard.writeText({json.dumps(msg)})"
                        style="margin-top:8px;padding:8px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#222;color:#fff;cursor:pointer">
                    📋 Copier le message post-départ
                </button>
                """,
                height=50
            )

            # --- CLÉ UNIQUE POUR ÉVITER CONFLIT ---
            if st.button("✅ Marquer 'post-départ envoyé'", key=f"mark_post_sent_{resa2['_rowid']}"):
                try:
                    df.loc[resa2["_rowid"], 'post_depart_envoye'] = True
                    df_final = ensure_schema(df)
                    if sauvegarder_donnees(df_final):
                        st.success("Marqué 'post-départ envoyé' ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

        # Envoi groupé
        st.markdown("---")
        st.subheader("📦 Envoi groupé post-départ")
        cold1, cold2 = st.columns(2)
        default_end = date.today()
        default_start = default_end - timedelta(days=7)
        d_start = cold1.date_input("Départs à partir de", default_start)
        d_end   = cold2.date_input("Jusqu'au (inclus)", default_end)

        elig = df_safe.dropna(subset=['telephone','nom_client','date_depart']).copy()
        elig = elig[(elig['date_depart'] >= d_start) & (elig['date_depart'] <= d_end) & (~elig['post_depart_envoye'])].copy()
        elig['tel_clean'] = elig['telephone'].astype(str).str.replace(r'\D','',regex=True).str.lstrip('0')
        elig = elig[elig['tel_clean'].str.len().between(9,15)]
        if elig.empty:
            st.info("Aucun client dans la plage sélectionnée.")
        else:
            rows_ui, all_messages = [], []
            for ridx, r in elig.iterrows():
                name = str(r.get('nom_client') or "").strip()
                lang = str(r.get('lang') or 'FR').upper()
                msg = _post_depart_message(name, lang)
                e164 = _format_phone_e164(r['telephone'])
                wa_num = re.sub(r"\D","",e164)
                enc = quote(msg)
                rows_ui.append({
                    "index": ridx,
                    "nom": name,
                    "tel": r['telephone'],
                    "depart": r['date_depart'],
                    "wa": f"https://wa.me/{wa_num}?text={enc}",
                    "sms_ios": f"sms:&body={enc}",
                    "sms_android": f"sms:{e164}?body={enc}",
                    "msg": msg,
                })
                all_messages.append(msg)

            st.write(f"Clients éligibles : **{len(rows_ui)}**")
            cgb1, cgb2 = st.columns(2)
            if cgb1.button("📋 Tout copier (messages)"):
                clipboard_text = "\n\n---\n".join(all_messages)
                st.components.v1.html(
                    f"""
                    <script>
                      navigator.clipboard.writeText({json.dumps(clipboard_text)});
                    </script>
                    <div style="color:#aaa">Messages copiés dans le presse-papiers.</div>
                    """,
                    height=10
                )
                st.success("Messages copiés.")
            if cgb2.button("✅ Tout marquer 'post-départ envoyé'", key="mark_post_bulk"):
                try:
                    idxs = [row["index"] for row in rows_ui]
                    df.loc[idxs, 'post_depart_envoye'] = True
                    df_final = ensure_schema(df)
                    if sauvegarder_donnees(df_final):
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

# ==============================  EXPORT ICS & FLUX PUBLIC ==============================
def _get_query_params():
    try: return st.query_params
    except Exception:
        try: return st.experimental_get_query_params()
        except Exception: return {}

def _as_list(v):
    if v is None: return []
    if isinstance(v,list): return v
    return [v]

def icspublic_endpoint(df):
    params = _get_query_params()
    feed = params.get("feed", [""])[0] if isinstance(params.get("feed"), list) else params.get("feed", "")
    if str(feed).lower() != "ics": return False
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
        except: pass
    if plats:
        plats_norm = [p for p in plats if p]
        if plats_norm: data = data[data['plateforme'].isin(plats_norm)]
    if inc_np in ("0","false","False"): data = data[data['paye']==True]
    if inc_sms in ("0","false","False"): data = data[data['sms_envoye']==False]

    ics = build_ics_from_df(data)
    st.text(ics); st.stop()

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    card("Info", "Générez un **fichier .ics** à importer dans Google Calendar. UID stables pour éviter les doublons.")
    base = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if base.empty:
        st.warning("Aucune réservation avec dates valides."); return
    col1, col2 = st.columns(2)
    years = sorted(base['date_arrivee'].apply(lambda d: d.year).unique()); annee = col1.selectbox("Année (arrivée)", years, index=len(years)-1)
    all_plats = sorted(base['plateforme'].dropna().unique()); plats_sel = col2.multiselect("Plateformes (déroulant)", ["Tous"]+list(all_plats), default=["Tous"])
    plats_effectifs = list(all_plats) if ("Tous" in plats_sel or not plats_sel) else [p for p in plats_sel if p!="Tous"]
    c3, c4, c5 = st.columns(3)
    create_missing_uid = c3.toggle("Créer et sauvegarder les UID manquants", value=True)
    include_paid       = c4.toggle("Inclure non payées", value=True)
    include_sms_sent   = c5.toggle("Inclure déjà 'SMS envoyé'", value=True)
    apply_to_all = st.toggle("Ignorer les filtres et créer pour toute la base", value=False)

    df_filtre = base[(base['date_arrivee'].apply(lambda d: d.year)==annee)].copy()
    if plats_effectifs: df_filtre = df_filtre[df_filtre['plateforme'].isin(plats_effectifs)]
    if not include_paid: df_filtre = df_filtre[df_filtre['paye']==True]
    if not include_sms_sent: df_filtre = df_filtre[df_filtre['sms_envoye']==False]
    if df_filtre.empty: st.warning("Rien à exporter avec ces filtres.")
    df_to_gen = base.copy() if apply_to_all else df_filtre.copy()

    if not df_to_gen.empty:
        missing_res_id = df_to_gen['res_id'].isna() | (df_to_gen['res_id'].astype(str).str.strip()=="")
        if create_missing_uid and missing_res_id.any():
            df_to_gen.loc[missing_res_id,'res_id'] = [str(uuid.uuid4()) for _ in range(int(missing_res_id.sum()))]
            try:
                df.loc[df_to_gen.index,'res_id'] = df_to_gen['res_id']
                if sauvegarder_donnees(df): st.success(f"ID internes créés pour {int(missing_res_id.sum())} réservation(s).")
            except Exception as e:
                st.error(f"Impossible de sauvegarder les ID internes : {e}")
        missing_uid = df_to_gen['ical_uid'].isna() | (df_to_gen['ical_uid'].astype(str).str.strip()=="")
        if missing_uid.any():
            df_to_gen.loc[missing_uid,'ical_uid'] = df_to_gen[missing_uid].apply(build_stable_uid, axis=1)
        if create_missing_uid and missing_uid.any():
            try:
                df.loc[df_to_gen.index,'ical_uid'] = df_to_gen['ical_uid']
                if sauvegarder_donnees(df): st.success(f"UID ICS créés/sauvegardés pour {int(missing_uid.sum())} réservation(s).")
            except Exception as e:
                st.error(f"Impossible de sauvegarder les UID : {e}")
        if not df_filtre.empty:
            inter = df_to_gen.index.intersection(df_filtre.index)
            df_filtre.loc[inter,'res_id']   = df_to_gen.loc[inter,'res_id']
            df_filtre.loc[inter,'ical_uid'] = df_to_gen.loc[inter,'ical_uid']

    ics = build_ics_from_df(df_filtre)
    st.download_button("📥 Télécharger ICS", data=ics.encode('utf-8'), file_name=f"villa_tobias_{annee}.ics", mime="text/calendar")

def vue_flux_ics_public(df, palette):
    st.header("🔗 Flux ICS public (BETA)")
    card("Utilisation", "Collez l’URL générée dans Google Calendar → **Ajouter un agenda** → **À partir de l’URL**.")
    base_url = st.text_input("URL de base de l'app (telle qu'affichée dans votre navigateur)", value="")
    years = sorted([d.year for d in df['date_arrivee'].dropna().unique()]) if 'date_arrivee' in df.columns else []
    year = st.selectbox("Année (arrivées)", options=years if years else [date.today().year], index=len(years)-1 if years else 0)
    all_plats = sorted(df['plateforme'].dropna().unique()) if 'plateforme' in df.columns else []
    plats_sel = st.multiselect("Plateformes (déroulant)", ["Tous"]+list(all_plats), default=["Tous"])
    plats_effectifs = list(all_plats) if ("Tous" in plats_sel or not plats_sel) else [p for p in plats_sel if p!="Tous"]
    c3, c4 = st.columns(2); incl_np = c3.toggle("Inclure non payées", value=True); incl_sms = c4.toggle("Inclure déjà 'SMS envoyé'", value=True)
    token_default = hashlib.sha256(f"villa-tobias-{year}".encode()).hexdigest()[:16]
    token = st.text_input("Token (clé simple)", value=token_default)

    def build_url(base, params):
        if not base: return ""
        base_clean = base.split("?")[0]
        return base_clean + "?" + urlencode(params, doseq=True)

    query = {"feed":"ics","token":token,"year":str(year),"incl_np":"1" if incl_np else "0","incl_sms":"1" if incl_sms else "0"}
    if plats_effectifs and len(plats_effectifs)!=len(all_plats):
        for p in plats_effectifs: query.setdefault("plats", []).append(p)

    flux_url = build_url(base_url, query)
    if flux_url:
        st.code(flux_url, language="text"); st.link_button("📋 Copier / Ouvrir l’URL de flux", flux_url)

    with st.expander("Aperçu ICS"):
        data = df.dropna(subset=['date_arrivee','date_depart']).copy()
        data = data[data['date_arrivee'].apply(lambda d: isinstance(d, date) and d.year==year)]
        if plats_effectifs and len(plats_effectifs)!=len(all_plats): data = data[data['plateforme'].isin(plats_effectifs)]
        if not incl_np: data = data[data['paye']==True]
        if not incl_sms: data = data[data['sms_envoye']==False]
        st.text(build_ics_from_df(data))

# ==============================  GOOGLE FORM / SHEET intégrés ==============================
def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée & Feuille Google")
    card("Infos", "Le bouton **Copier le lien** insère l’URL **courte** du formulaire.")
    tab_form, tab_sheet, tab_csv = st.tabs(["Formulaire (intégré)", "Feuille intégrée", "Réponses (CSV)"])

    with tab_form:
        st.markdown(f"**Lien à partager (court)** : {FORM_SHORT_URL}")
        st.components.v1.html(f"""
            <button onclick="navigator.clipboard.writeText('{FORM_SHORT_URL}')"
                    style="margin-top:6px;padding:8px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#222;color:#fff;cursor:pointer">
                📋 Copier le lien
            </button>
        """, height=50)
        st.components.v1.iframe(GOOGLE_FORM_URL, height=950, scrolling=True)

    with tab_sheet:
        st.caption("Affichage intégré (lecture seule) — lien raccourci.")
        st.components.v1.iframe(GOOGLE_SHEET_EMBED_URL, height=900, scrolling=True)

    with tab_csv:
        st.caption("Lecture via l’URL publiée (CSV).")
        try:
            reposes = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
            st.markdown("<div class='glass'>", unsafe_allow_html=True)
            st.dataframe(reposes, use_container_width=True)
            st.markdown("</div>", unsafe_allow_html=True)
            st.download_button("⬇️ Télécharger les réponses (CSV)",
                               data=reposes.to_csv(index=False).encode("utf-8"),
                               file_name="reponses_formulaire.csv", mime="text/csv")
        except Exception as e:
            st.error(f"Impossible de charger les réponses : {e}")
            st.info("Vérifie que la feuille est bien publiée en CSV et accessible.")

# ==============================  SIDEBAR ADMIN ==============================
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
                st.success("Fichier restauré. L'application va se recharger."); st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur de restauration: {e}")

# ==============================  MAIN  ==============================
def main():
    with st.sidebar:
        mode_clair = st.toggle("🌓 Mode clair (PC)", value=False)

    apply_modern_style(mode="light" if mode_clair else "dark")
    enable_altair_theme()

    df, palette_loaded = charger_donnees()

    params = _get_query_params()
    if str(params.get("feed", [""])[0]).lower() == "ics":
        icspublic_endpoint(df); return

    st.title("✨ Villa Tobias — Gestion des Réservations")
    st.sidebar.title("🧭 Navigation")

    palette_eff = DEFAULT_PALETTE.copy()
    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        palette_eff.update(dict(zip(df_pal['plateforme'], df_pal['couleur'])))
    except Exception:
        palette_eff.update(palette_loaded or {})

    pages = {
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "🔗 Flux ICS public": vue_flux_ics_public,
        "📝 Fiche d'arrivée / Google Sheet": vue_google_sheet,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    page_function = pages[selection]
    page_function(df, palette_eff)
    admin_sidebar(df)

if __name__ == "__main__":
    main()