# ==============================  IMPORTS & CONFIG  ==============================
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import hashlib, uuid, json, re
from datetime import date, timedelta
from calendar import monthrange
from urllib.parse import quote, urlencode

# --- Configuration des Fichiers ---
CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv"

FORM_SHORT_URL = "https://urlr.me/kZuH94"
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
        sidebar_bg, sidebar_border, link = "linear-gradient(180deg,#fff,#f9fafb)", "1px solid rgba(17,24,39,.08)", "#0f172a"
    else:
        bg, panel, text, muted, chip = "#0f1115", "#171923", "#eaeef6", "#a0aec0", "#1f2230"
        border, accent, grid = "rgba(124,92,255,.16)", "#7c5cff", "#2a2f45"
        sidebar_bg, sidebar_border, link = "linear-gradient(180deg,#171923,#1e2130)", "1px solid rgba(124,92,255,.15)", "#eaeef6"

    st.markdown(f"""
    <style>
    body, [data-testid="stAppViewContainer"]{{background:{bg};}}
    [data-testid="stSidebar"]{{background:{sidebar_bg};border-right:{sidebar_border};}}
    [data-testid="stSidebar"] *{{color:{text} !important;}}
    .glass{{background:{panel};border:1px solid {border};border-radius:16px;padding:16px;}}
    .chip{{background:{chip};border:1px solid {border};border-radius:12px;padding:10px 14px;}}
    .chip .lbl{{color:{muted};font-size:.85rem;}}
    .chip .val{{color:{text};font-weight:700;}}
    .stTabs [data-baseweb="tab"]{{background:{panel};color:{text};border:1px solid {border};}}
    .stTabs [aria-selected="true"]{{background:{bg};border-color:{accent};}}
    </style>
    """, unsafe_allow_html=True)

def enable_altair_theme():
    def _theme():
        return {"config":{
            "axis":{"labelColor":"#cbd5e1","titleColor":"#eaeef6","gridColor":"#2a2f45"},
            "legend":{"labelColor":"#cbd5e1","titleColor":"#eaeef6"},
            "title":{"color":"#eaeef6","font":"Inter","fontWeight":700}
        }}
    alt.themes.register("tobias", _theme)
    alt.themes.enable("tobias")

def card(title, body_md):
    st.markdown(f"<div class='glass'><div style='font-weight:700'>{title}</div><div>{body_md}</div></div>", unsafe_allow_html=True)

# ==============================  DATA FUNCTIONS ==============================
@st.cache_data
def charger_donnees_csv():
    df, palette = pd.DataFrame(), DEFAULT_PALETTE.copy()
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=';')
        df.columns = df.columns.str.strip()
    except: pass
    try:
        df_palette = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        palette = dict(zip(df_palette['plateforme'], df_palette['couleur']))
    except: pass
    df = ensure_schema(df)
    return df, palette

def sauvegarder_donnees_csv(df, file_path=CSV_RESERVATIONS):
    try:
        df_to_save = df.copy()
        df_to_save.to_csv(file_path, sep=';', index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ==============================  SCHEMA ==============================
BASE_COLS = [
    'res_id','ical_uid','paye','sms_envoye','post_depart_envoye','nom_client','email','telephone',
    'plateforme','date_arrivee','date_depart','nuitees','prix_brut','prix_net','commissions',
    'frais_cb','menage','taxes_sejour','base','charges','%','AAAA','MM'
]

def ensure_schema(df):
    if df.empty: return pd.DataFrame(columns=BASE_COLS)
    df_res = df.copy()
    for col in BASE_COLS:
        if col not in df_res.columns: df_res[col] = None
    df_res['date_arrivee'] = pd.to_datetime(df_res['date_arrivee'], dayfirst=True, errors='coerce').dt.date
    df_res['date_depart'] = pd.to_datetime(df_res['date_depart'], dayfirst=True, errors='coerce').dt.date
    mask = df_res['date_arrivee'].notna() & df_res['date_depart'].notna()
    df_res.loc[mask,'nuitees'] = (pd.to_datetime(df_res['date_depart']) - pd.to_datetime(df_res['date_arrivee'])).dt.days
    df_res['AAAA'] = pd.to_datetime(df_res['date_arrivee']).dt.year
    df_res['MM'] = pd.to_datetime(df_res['date_arrivee']).dt.month
    df_res['paye'] = df_res['paye'].fillna(False).astype(bool)
    for col in ['prix_brut','prix_net','commissions','frais_cb','menage','taxes_sejour']:
        df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)
    df_res['prix_net'] = df_res['prix_brut'] - df_res['commissions'] - df_res['frais_cb']
    df_res['charges'] = df_res['prix_brut'] - df_res['prix_net']
    df_res['base'] = df_res['prix_net'] - df_res['menage'] - df_res['taxes_sejour']
    return df_res

# ==============================  HELPERS ==============================
def _safe_div2(a, b): return float(a)/float(b) if b else None
def _fmt_eur(x): return f"{x:,.2f} €".replace(",", " ")
def _to_bool_series(s): return s.astype(str).str.lower().isin(["true","vrai","1","yes","oui"])

# (Fonctions ICS et vues Réservations / Ajouter / Modifier / Plateformes / Calendrier suivent ici...)

# ==============================  AUTRES HELPERS (UID, téléphone, Form) ==============================
import uuid, unicodedata
from datetime import datetime

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

def _format_phone_e164(raw_phone: str) -> str:
    raw_phone = str(raw_phone or "")
    clean = re.sub(r"\D", "", raw_phone)
    if raw_phone.strip().startswith("+"):  # déjà en international
        return raw_phone.strip()
    if clean.startswith("0") and len(clean) == 10:  # FR
        return "+33" + clean[1:]
    if clean:
        return "+33" + clean
    return raw_phone.strip()

def form_prefill_url():
    # On privilégie le lien court fourni par l'utilisateur pour le partage
    return FORM_SHORT_URL or GOOGLE_FORM_URL

# ==============================  ICS (export) ==============================
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
        if not isinstance(da, date) or not isinstance(dd, date): 
            continue
        uid = _compute_uid(r)
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
    return "\r\n".join(lines) + "\r\n"

# ==============================  RAPPORT (modernisé) ==============================
def _available_nights_by_month(year: int):
    return {date(year, m, 1): monthrange(year, m)[1] for m in range(1, 13)}

def _expand_to_daily(df):
    rows = []
    for _, r in df.iterrows():
        da, dd = r.get("date_arrivee"), r.get("date_depart")
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

def vue_rapport(df, palette):
    enable_altair_theme()
    st.header("📊 Rapport de Performance")
    card("Mode d'emploi", "Choisissez **Année/Mois/Plateformes** et la **métrique**. Explorez les tendances et exportez le CSV.")

    base = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if base.empty:
        st.info("Aucune donnée pour générer un rapport.")
        return

    c0, c1, c2, c3 = st.columns([1,1.2,1.2,1.8])
    years = sorted({d.year for d in base['date_arrivee'] if isinstance(d, date)}, reverse=True)
    annee = c0.selectbox("Année", years, index=0)

    mois_labels = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Aoû", "Sep", "Oct", "Nov", "Déc"]
    mois_opts = ["Tous"] + [f"{i:02d} — {mois_labels[i-1]}" for i in range(1,13)]
    mois_sel = c1.multiselect("Mois", mois_opts, default=["Tous"])

    all_plats = sorted([p for p in base['plateforme'].dropna().unique()])
    plat_options = ["Tous"] + all_plats
    plats_sel = c2.multiselect("Plateformes (déroulant)", plat_options, default=["Tous"])
    plats_effectifs = all_plats if ("Tous" in plats_sel or not plats_sel) else [p for p in plats_sel if p != "Tous"]

    paid_only  = c3.toggle("Uniquement réservations payées", value=False)

    metric_mode = st.radio("Mode de revenu", ["Brut", "Net"], index=0, horizontal=True)
    mcol = "prix_brut" if metric_mode == "Brut" else "prix_net"

    data = base[(pd.Series([isinstance(d, date) and d.year == annee for d in base['date_arrivee']]))].copy()
    if ("Tous" in mois_sel) or (len(mois_sel) == 0):
        mois_int = list(range(1,13))
    else:
        mois_int = [int(s.split(" — ")[0]) for s in mois_sel]
    data = data[data['date_arrivee'].apply(lambda d: d.month in mois_int)]
    if plats_effectifs:
        data = data[data['plateforme'].isin(plats_effectifs)]
    if paid_only:
        data = data[data['paye'] == True]

    if data.empty:
        st.warning("Aucune donnée après filtres.")
        return

    # KPI
    nb_res   = len(data)
    nuits    = int(data['nuitees'].fillna(0).sum())
    rev_total = float(data[mcol].fillna(0).sum())
    adr      = _safe_div2(rev_total, nuits)
    avail_by_month = _available_nights_by_month(annee)
    avail_year = sum(avail_by_month[date(annee, m, 1)] for m in mois_int)
    occ     = _safe_div2(nuits, avail_year)
    revpar  = _safe_div2(rev_total, avail_year)

    with st.container():
        st.markdown("<div class='glass'>", unsafe_allow_html=True)
        k1, k2, k3, k4, k5, k6 = st.columns(6)
        k1.metric("Réservations", f"{nb_res}")
        k2.metric("Nuitées vendues", f"{nuits}")
        k3.metric(f"Revenu {metric_mode.lower()}", _fmt_eur(rev_total))
        k4.metric(f"ADR {metric_mode.lower()}", _fmt_eur(adr) if pd.notna(adr) else "—")
        k5.metric("Taux d’occupation", f"{occ*100:,.1f} %".replace(",", " ") if pd.notna(occ) else "—")
        k6.metric(f"RevPAR {metric_mode.lower()}", _fmt_eur(revpar) if pd.notna(revpar) else "—")
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("---")

    # Agrégats mensuels
    data['mois'] = data['date_arrivee'].apply(lambda d: date(d.year, d.month, 1))
    grp = (data.groupby(['plateforme','mois'], as_index=False)
               .agg({mcol:'sum', 'nuitees':'sum'}))
    months_all = [date(annee, m, 1) for m in mois_int]
    frames = []
    for p in (plats_effectifs if plats_effectifs else all_plats):
        g = grp[grp['plateforme']==p].set_index('mois').reindex(months_all).fillna({mcol:0.0,'nuitees':0.0})
        g['plateforme'] = p
        g = g.reset_index().rename(columns={'index':'mois'})
        frames.append(g)
    grp_full = pd.concat(frames, ignore_index=True)

    avail_map = {date(annee, m, 1): _available_nights_by_month(annee)[date(annee, m, 1)] for m in mois_int}
    grp_full['available'] = grp_full['mois'].map(avail_map)
    grp_full['adr']    = grp_full.apply(lambda r: _safe_div2(r[mcol], r['nuitees']), axis=1)
    grp_full['occ']    = grp_full.apply(lambda r: _safe_div2(r['nuitees'], r['available']), axis=1)
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

    color_map = {p: DEFAULT_PALETTE.get(p, '#888') for p in (plats_effectifs if plats_effectifs else all_plats)}
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
    st.subheader("Répartition par plateforme")
    mix = (data.groupby("plateforme", as_index=False)
              .agg(revenu=(mcol,'sum'), nuitées=('nuitees','sum'), sejours=('res_id','count')))
    c1, c2 = st.columns([2,1])
    chart_mix = alt.Chart(mix).mark_bar().encode(
        x=alt.X('plateforme:N', title='Plateforme'),
        y=alt.Y('revenu:Q', title=f'Revenu {metric_mode.lower()}'),
        color=alt.Color('plateforme:N', legend=None,
                        scale=alt.Scale(domain=domain_sel, range=range_sel)),
        tooltip=[alt.Tooltip('plateforme:N'), alt.Tooltip('revenu:Q', format='.2f'),
                 alt.Tooltip('nuitées:Q'), alt.Tooltip('sejours:Q')]
    )
    c1.altair_chart(chart_mix.properties(height=320), use_container_width=True)
    c2.dataframe(mix.sort_values('revenu', ascending=False), use_container_width=True)

    st.markdown("---")
    st.subheader("Heatmap d’occupation")
    daily = _expand_to_daily(data)
    if daily.empty:
        st.info("Pas assez de données pour la heatmap.")
    else:
        daily['mois'] = daily['day'].apply(lambda d: date(d.year, d.month, 1))
        occ_days = (daily.groupby('day', as_index=False).agg(occ=('res_id','nunique')))
        occ_days['occ'] = occ_days['occ'].clip(0,1)
        all_days = []
        for m in mois_int:
            rng = pd.date_range(f"{annee}-{m:02d}-01", f"{annee}-{m:02d}-{monthrange(annee, m)[1]}", freq="D").date
            all_days.extend(list(rng))
        all_days = pd.DataFrame({"day": all_days})
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
    st.subheader("Export CSV")
    with st.expander("Données mensuelles"):
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
                           file_name=f"rapport_{annee}_{metric_mode.lower()}_mois_{'-'.join([f'{m:02d}' for m in mois_int])}.csv",
                           mime="text/csv")

# ==============================  SMS & WhatsApp ==============================
def _post_depart_message(name: str) -> str:
    return f"""Bonjour {name},

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

def _row_buttons_post(r):
    name = str(r.get('nom_client') or "").strip()
    msg = _post_depart_message(name)
    e164 = _format_phone_e164(r['telephone'])
    wa_num = re.sub(r"\D", "", e164)
    enc = quote(msg)
    return {
        "msg": msg,
        "wa": f"https://wa.me/{wa_num}?text={enc}",
        "sms_ios": f"sms:&body={enc}",
        "sms_android": f"sms:{e164}?body={enc}",
    }

def vue_sms(df):
    st.header("✉️ SMS & WhatsApp")
    card("Aide", "Pré-arrivée (par défaut **arrivées J+1**) et **post-départ** (départs du jour). Le lien formulaire est **court**.")

    for colb in ('sms_envoye','post_depart_envoye'):
        if colb in df.columns:
            df[colb] = _to_bool_series(df[colb]).fillna(False).astype(bool)
        else:
            df[colb] = False

    # ---- Pré-arrivée ----
    st.subheader("🛬 Messages pré-arrivée")
    tomorrow_default = date.today() + timedelta(days=1)
    target_arrivee = st.date_input("Cibler les arrivées du", tomorrow_default, key="prearrivee_date")

    df_tel = df.dropna(subset=['telephone','nom_client','date_arrivee']).copy()
    df_tel = df_tel[df_tel['date_arrivee'] == target_arrivee]
    df_tel['tel_clean'] = df_tel['telephone'].astype(str).str.replace(r'\D','',regex=True).str.lstrip('0')
    mask_valid_phone = df_tel['tel_clean'].str.len().between(9,15)
    df_tel = df_tel[~df_tel['sms_envoye'] & mask_valid_phone].copy()
    df_tel["_rowid"] = df_tel.index

    st.components.v1.html(f"""
        <button onclick="navigator.clipboard.writeText('{FORM_SHORT_URL}')"
                style="margin-bottom:10px;padding:8px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#222;color:#fff;cursor:pointer">
            📋 Copier le lien (formulaire)
        </button>
    """, height=48)

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

            link_for_message = form_prefill_url()
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

            st.components.v1.html(f"""
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
            """, height=60)

            if st.button("✅ Marquer ce client comme 'SMS envoyé'"):
                try:
                    df.loc[original_rowid,'sms_envoye'] = True
                    df_final = ensure_schema(df)
                    if sauvegarder_donnees_csv(df_final):
                        st.success("Marqué 'SMS envoyé' ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer comme envoyé : {e}")

st.markdown("---")

def vue_sms_post_depart(df):
    st.subheader("📤 Post-départ (individuel & groupé)")
    default_depart = date.today()
    target_depart = st.date_input("Départs du", default_depart, key="postdepart_date")

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
            links = _row_buttons_post(resa2)

            c_wa2, c_ios2, c_and2 = st.columns([1,1,1])
            with c_wa2:  st.link_button("🟢 WhatsApp", links["wa"])
            with c_ios2: st.link_button("📲 iPhone SMS", links["sms_ios"])
            with c_and2: st.link_button("🤖 Android SMS", links["sms_android"])

            st.components.v1.html(f"""
                <button onclick="navigator.clipboard.writeText({json.dumps(links['msg'])})"
                        style="margin-top:8px;padding:8px 12px;border-radius:12px;border:1px solid rgba(255,255,255,.12);background:#222;color:#fff;cursor:pointer">
                    📋 Copier le message post-départ
                </button>
            """, height=50)

            if st.button("✅ Marquer 'post-départ envoyé'"):
                try:
                    df.loc[original_rowid2,'post_depart_envoye'] = True
                    df_final = ensure_schema(df)
                    if sauvegarder_donnees_csv(df_final):
                        st.success("Marqué 'post-départ envoyé' ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    st.markdown("---")
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
        rows_ui, all_messages = [], []
        for ridx, r in elig.iterrows():
            links = _row_buttons_post(r)
            rows_ui.append({
                "index": ridx,
                "nom": str(r.get('nom_client') or "").strip(),
                "tel": r['telephone'],
                "depart": r['date_depart'],
                "wa": links["wa"],
                "sms_ios": links["sms_ios"],
                "sms_android": links["sms_android"],
                "msg": links["msg"],
            })
            all_messages.append(links["msg"])

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

# ==============================  EXPORT ICS MANUEL + FLUX PUBLIC ==============================
def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    card("Info", "Générez un **fichier .ics** à importer dans Google Calendar. UID stables pour éviter les doublons.")
    base_all = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if base_all.empty:
        st.warning("Aucune réservation avec dates valides."); return

    col1, col2 = st.columns(2)
    years = sorted(base_all['date_arrivee'].apply(lambda d: d.year).unique())
    annee = col1.selectbox("Année (arrivée)", years, index=len(years)-1)

    all_plats = sorted(base_all['plateforme'].dropna().unique())
    plat_options = ["Tous"] + all_plats
    plats_sel = col2.multiselect("Plateformes (déroulant)", plat_options, default=["Tous"])
    plats_effectifs = all_plats if ("Tous" in plats_sel or not plats_sel) else [p for p in plats_sel if p != "Tous"]

    c3, c4, c5 = st.columns(3)
    create_missing_uid = c3.toggle("Créer et sauvegarder les UID manquants", value=True)
    include_paid       = c4.toggle("Inclure les réservations non payées", value=True)
    include_sms_sent   = c5.toggle("Inclure celles déjà 'SMS envoyé'", value=True)
    apply_to_all = st.toggle("Ignorer les filtres et créer pour toute la base", value=False)

    df_filtre = base_all[(base_all['date_arrivee'].apply(lambda d: d.year) == annee)].copy()
    if plats_effectifs:
        df_filtre = df_filtre[df_filtre['plateforme'].isin(plats_effectifs)]
    if not include_paid:
        df_filtre = df_filtre[df_filtre['paye'] == True]
    if not include_sms_sent:
        df_filtre = df_filtre[df_filtre['sms_envoye'] == False]
    if df_filtre.empty:
        st.warning("Rien à exporter avec ces filtres.")

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

# Flux ICS public (GET params)
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
    card("Utilisation", "Copiez l’URL générée dans Google Calendar → **Ajouter un agenda** → **À partir de l’URL**.")
    base_url = st.text_input("URL de base de l'app (telle qu'affichée dans votre navigateur)", value="")

    years = sorted([d.year for d in df['date_arrivee'].dropna().unique()]) if 'date_arrivee' in df.columns else []
    year = st.selectbox("Année (arrivées)", options=years if years else [date.today().year], index=len(years)-1 if years else 0)

    all_plats = sorted(df['plateforme'].dropna().unique()) if 'plateforme' in df.columns else []
    plat_options = ["Tous"] + all_plats
    plats_sel = st.multiselect("Plateformes (déroulant)", plat_options, default=["Tous"])
    plats_effectifs = all_plats if ("Tous" in plats_sel or not plats_sel) else [p for p in plats_sel if p != "Tous"]

    c3, c4 = st.columns(2)
    incl_np  = c3.toggle("Inclure non payées", value=True)
    incl_sms = c4.toggle("Inclure déjà 'SMS envoyé'", value=True)

    token_default = hashlib.sha256(f"villa-tobias-{year}".encode()).hexdigest()[:16]
    token = st.text_input("Token (clé simple)", value=token_default)

    def build_url(base, params):
        if not base: return ""
        base_clean = base.split("?")[0]
        return base_clean + "?" + urlencode(params, doseq=True)

    query = {"feed": "ics", "token": token, "year": str(year),
             "incl_np": "1" if incl_np else "0", "incl_sms": "1" if incl_sms else "0"}
    if plats_effectifs and len(plats_effectifs) != len(all_plats):
        for p in plats_effectifs:
            query.setdefault("plats", []).append(p)

    flux_url = build_url(base_url, query)
    if flux_url:
        st.code(flux_url, language="text")
        st.link_button("📋 Copier / Ouvrir l’URL de flux", flux_url)

    with st.expander("Aperçu ICS"):
        data = df.dropna(subset=['date_arrivee','date_depart']).copy()
        data = data[data['date_arrivee'].apply(lambda d: isinstance(d, date) and d.year == year)]
        if plats_effectifs and len(plats_effectifs) != len(all_plats):
            data = data[data['plateforme'].isin(plats_effectifs)]
        if not incl_np:
            data = data[data['paye'] == True]
        if not incl_sms:
            data = data[data['sms_envoye'] == False]
        st.text(build_ics_from_df(data))

# ==============================  GOOGLE FORM / SHEET ==============================
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
                st.success("Fichier restauré. L'application va se recharger.")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur lors de la restauration: {e}")

# ==============================  MAIN ==============================
def main():
    # Toggle thème dans la sidebar
    with st.sidebar:
        mode_clair = st.toggle("🌓 Mode clair (PC)", value=False)

    apply_modern_style(mode="light" if mode_clair else "dark")
    enable_altair_theme()

    df, palette = charger_donnees_csv()

    # Endpoint ICS public si demandé dans l'URL
    params = _get_query_params()
    if str(params.get("feed", [""])[0]).lower() == "ics":
        icspublic_endpoint(df)
        return

    st.title("✨ Villa Tobias — Gestion des Réservations")
    st.sidebar.title("🧭 Navigation")

    pages = {
        "📋 Réservations": vue_reservations,            # doit être dans la Partie 1
        "➕ Ajouter": vue_ajouter,                      # idem Partie 1
        "✏️ Modifier / Supprimer": vue_modifier,        # idem Partie 1
        "🎨 Plateformes": vue_plateformes,              # idem Partie 1
        "📅 Calendrier": vue_calendrier,                # idem Partie 1
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📤 SMS Post-départ": vue_sms_post_depart,
        "📆 Export ICS (Google Calendar)": vue_export_ics,
        "🔗 Flux ICS public (BETA)": vue_flux_ics_public,
        "📝 Fiche d'arrivée / Google Sheet": vue_google_sheet,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    page_function = pages[selection]

    # Palette effective (défaut + overrides)
    palette_eff = DEFAULT_PALETTE.copy()
    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        palette_eff.update(dict(zip(df_pal['plateforme'], df_pal['couleur'])))
    except:
        pass

    # Appels pages
    if selection in ["📊 Rapport","✉️ SMS","📤 SMS Post-départ","📆 Export ICS (Google Calendar)","🔗 Flux ICS public (BETA)","📝 Fiche d'arrivée / Google Sheet"]:
        page_function(df, palette_eff)
    else:
        # ces pages sont dans la Partie 1 et attendent (df, palette)
        page_function(df, palette_eff)

    admin_sidebar(df)

if __name__ == "__main__":
    main()