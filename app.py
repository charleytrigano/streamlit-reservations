# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import os, re, json, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import monthrange
from urllib.parse import quote, urlencode

# ============================== CONFIG ==============================
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# Liens (formulaire / Google Sheet)
FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# ============================== STYLE ==============================
def apply_modern_style(light: bool):
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    st.markdown(f"""
    <style>
      html, body, [data-testid="stAppViewContainer"] {{
        background: {bg};
        color: {fg};
      }}
      [data-testid="stSidebar"] {{
        background: {side};
        border-right: 1px solid {border};
      }}
      .glass {{
        background: rgba(255,255,255,{0.6 if light else 0.06});
        border: 1px solid {border};
        border-radius: 12px; padding: 12px; margin: 8px 0;
      }}
    </style>
    """, unsafe_allow_html=True)

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)

# ============================== DONNÉES ==============================
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    base_cols = [
        'res_id','ical_uid',
        'paye','sms_envoye','post_depart_envoye',
        'nom_client','email','telephone','plateforme',
        'date_arrivee','date_depart','nuitees',
        'prix_brut','prix_net','commissions','frais_cb','menage','taxes_sejour',
        'AAAA','MM'
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=base_cols)

    df = df.copy()

    # Dates -> date
    for c in ['date_arrivee','date_depart']:
        df[c] = pd.to_datetime(df.get(c), errors='coerce').dt.date

    # Booléens
    for b in ['paye','sms_envoye','post_depart_envoye']:
        if b not in df.columns: df[b] = False
        df[b] = df[b].astype(str).str.lower().isin(['true','1','oui','vrai','yes']).fillna(False)

    # Numériques
    for n in ['prix_brut','prix_net','commissions','frais_cb','menage','taxes_sejour','nuitees']:
        df[n] = pd.to_numeric(df.get(n), errors='coerce').fillna(0.0)

    # ID / UID
    if 'res_id' not in df.columns: df['res_id'] = None
    if 'ical_uid' not in df.columns: df['ical_uid'] = None
    if 'res_id' in df.columns:
        miss = df['res_id'].isna() | (df['res_id'].astype(str).str.strip()=="")
        df.loc[miss,'res_id'] = [str(uuid.uuid4()) for _ in range(int(miss.sum()))]

    # Prix net si absent
    if 'prix_net' in df.columns:
        df['prix_net'] = df['prix_brut'] - df['commissions'] - df['frais_cb']

    # Année/Mois
    df['AAAA'] = pd.to_datetime(df['date_arrivee'], errors='coerce').dt.year
    df['MM']   = pd.to_datetime(df['date_arrivee'], errors='coerce').dt.month

    # Colonnes manquantes
    for c in base_cols:
        if c not in df.columns: df[c] = None

    return df[base_cols]

@st.cache_data
def charger_donnees():
    # Réservations
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=";")
    except Exception:
        df = pd.DataFrame()
    df = ensure_schema(df)

    # Palette
    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";")
        palette = dict(zip(df_pal['plateforme'], df_pal['couleur']))
    except Exception:
        palette = DEFAULT_PALETTE.copy()

    return df, palette

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        df2 = ensure_schema(df)
        df2.to_csv(CSV_RESERVATIONS, sep=";", index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde CSV : {e}")
        return False

# ============================== HELPERS ==============================
def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

# ============================== VUES ==============================
def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty:
        st.info("Aucune réservation."); return

    years = ["Toutes"] + sorted(df['AAAA'].dropna().astype(int).unique(), reverse=True).tolist()
    year  = st.sidebar.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1,13))
    month = st.sidebar.selectbox("Mois", months, index=0)
    plats = ["Toutes"] + sorted(df['plateforme'].dropna().unique())
    plat  = st.sidebar.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    if year != "Toutes":
        data = data[data['AAAA']==int(year)]
    if month != "Tous":
        data = data[data['MM']==int(month)]
    if plat != "Toutes":
        data = data[data['plateforme']==plat]

    st.dataframe(data.sort_values('date_arrivee', ascending=False), use_container_width=True)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter")
    with st.form("form_add", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom")
            email = st.text_input("Email", value="")
            tel = st.text_input("Téléphone")
            paye = st.checkbox("Payé", value=False)
        with c2:
            arrivee = st.date_input("Arrivée", date.today())
            depart  = st.date_input("Départ", date.today()+timedelta(days=1))
            plat = st.selectbox("Plateforme", list(palette.keys()))
        c3, c4, c5 = st.columns(3)
        with c3:
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01)
        with c4:
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01)
            menage = st.number_input("Ménage", min_value=0.0, step=0.01)
        with c5:
            taxes = st.number_input("Taxes séjour", min_value=0.0, step=0.01)

        ok = st.form_submit_button("✅ Ajouter")
        if ok:
            if not nom or depart <= arrivee:
                st.error("Nom et dates valides requis.")
            else:
                nuitees = (depart - arrivee).days
                new = pd.DataFrame([{
                    'res_id': str(uuid.uuid4()),
                    'nom_client': nom, 'email': email, 'telephone': tel, 'plateforme': plat,
                    'date_arrivee': arrivee, 'date_depart': depart, 'nuitees': nuitees,
                    'paye': paye, 'prix_brut': brut, 'commissions': commissions,
                    'frais_cb': frais_cb, 'menage': menage, 'taxes_sejour': taxes
                }])
                df2 = ensure_schema(pd.concat([df, new], ignore_index=True))
                if sauvegarder_donnees(df2):
                    st.success("Ajoutée ✅"); st.rerun()

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer")
    if df.empty:
        st.info("Aucune réservation."); return
    df_sorted = df.sort_values("date_arrivee", ascending=False).reset_index()
    opts = [f"{i}: {r['nom_client']} ({r['date_arrivee']})" for i, r in df_sorted.iterrows()]
    choice = st.selectbox("Choisissez", options=opts, index=None)
    if not choice: return
    idx = int(choice.split(":")[0])
    original = df_sorted.loc[idx, 'index']
    row = df.loc[original]

    with st.form(f"form_edit_{original}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get('nom_client','') or '')
            email = st.text_input("Email", value=row.get('email','') or '')
            tel = st.text_input("Téléphone", value=row.get('telephone','') or '')
            arrivee = st.date_input("Arrivée", value=row.get('date_arrivee'))
            depart  = st.date_input("Départ", value=row.get('date_depart'))
        with c2:
            plat = st.selectbox("Plateforme", options=list(palette.keys()),
                                index=list(palette.keys()).index(row.get('plateforme')) if row.get('plateforme') in palette else 0)
            paye = st.checkbox("Payé", value=bool(row.get('paye', False)))
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=float(row.get('prix_brut') or 0))
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=float(row.get('commissions') or 0))
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=float(row.get('frais_cb') or 0))
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=float(row.get('menage') or 0))
            taxes  = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=float(row.get('taxes_sejour') or 0))

        b1, b2 = st.columns([0.7,0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            for k, v in {
                'nom_client':nom,'email':email,'telephone':tel,'date_arrivee':arrivee,'date_depart':depart,
                'plateforme':plat,'paye':paye,'prix_brut':brut,'commissions':commissions,
                'frais_cb':frais_cb,'menage':menage,'taxes_sejour':taxes
            }.items():
                df.loc[original, k] = v
            if sauvegarder_donnees(ensure_schema(df)):
                st.success("Modifié ✅"); st.rerun()
        if b2.form_submit_button("🗑️ Supprimer"):
            if sauvegarder_donnees(df.drop(index=original)):
                st.warning("Supprimé."); st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Plateformes")
    base = pd.DataFrame(list(palette.items()), columns=['plateforme','couleur'])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    if st.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette enregistrée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

def vue_calendrier(df, palette):
    st.header("📅 Calendrier (liste du mois)")
    if df.empty:
        st.info("Aucune réservation."); return
    today = date.today()
    years = sorted(df['AAAA'].dropna().astype(int).unique(), reverse=True)
    year = st.selectbox("Année", options=years, index=0 if today.year in years else 0)
    month = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)
    sel = df[(df['AAAA']==year) & (df['MM']==month)].sort_values('date_arrivee')
    st.dataframe(sel[['nom_client','plateforme','date_arrivee','date_depart','nuitees','paye']], use_container_width=True)

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # --- Pré-arrivée (J+1) ---
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target = st.date_input("Arrivées du", date.today()+timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=['telephone','nom_client','date_arrivee']).copy()
    for c in ['date_arrivee','date_depart']:
        pre[c] = pd.to_datetime(pre[c], errors='coerce').dt.date
    pre = pre[(pre['date_arrivee']==target) & (~pre['sms_envoye'])]
    if pre.empty:
        st.info("Aucun client à contacter.")
    else:
        pre['_rowid'] = pre.index
        pre = pre.sort_values('date_arrivee').reset_index(drop=True)
        opts = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client", options=opts, index=None, key="pre_pick")
        if pick:
            i = int(pick.split(":")[0]); r = pre.loc[i]
            msg = (
                f"VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')} "
                f"Départ : {r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else ''} "
                f"Nuitées : {int(r.get('nuitees') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')}\n"
                f"Merci de nous indiquer votre heure d'arrivée.\n\n"
                f"Fiche d'arrivée : {FORM_SHORT_URL}"
            )
            enc = quote(msg)
            e164 = _format_phone_e164(r['telephone'])
            wa = re.sub(r"\D","", e164)
            c1,c2,c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"mark_pre_{r['_rowid']}"):
                df.loc[r['_rowid'],'sms_envoye'] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")
    # --- Post-départ (J) ---
    st.subheader("📤 Post-départ (départs du jour)")
    tdep = st.date_input("Départs du", date.today(), key="post_date")
    post = df.dropna(subset=['telephone','nom_client','date_depart']).copy()
    post['date_depart'] = pd.to_datetime(post['date_depart'], errors='coerce').dt.date
    post = post[(post['date_depart']==tdep) & (~post['post_depart_envoye'])]
    if post.empty:
        st.info("Aucun message à envoyer.")
    else:
        post['_rowid'] = post.index
        post = post.sort_values('date_depart').reset_index(drop=True)
        opts2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client", options=opts2, index=None, key="post_pick")
        if pick2:
            j = int(pick2.split(":")[0]); r2 = post.loc[j]
            name = str(r2.get('nom_client') or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Merci d'avoir choisi notre appartement pour votre séjour.\n"
                "Si vous souhaitez revenir, notre porte vous sera toujours ouverte.\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2)
            e164b = _format_phone_e164(r2['telephone'])
            wab  = re.sub(r"\D","", e164b)
            c1,c2,c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button("✅ Marquer 'post-départ envoyé'", key=f"mark_post_{r2['_rowid']}"):
                df.loc[r2['_rowid'],'post_depart_envoye'] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée."); return
    years = sorted(df['AAAA'].dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1,13))
    month = st.selectbox("Mois", months, index=0)
    plats = ["Tous"] + sorted(df['plateforme'].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)
    metric = st.selectbox("Métrique", ["prix_brut","prix_net","menage","nuitees"], index=0)

    data = df[df['AAAA']==year].copy()
    if month!="Tous": data = data[data['MM']==int(month)]
    if plat!="Tous":  data = data[data['plateforme']==plat]
    if data.empty:
        st.warning("Aucune donnée après filtres."); return

    data['mois'] = pd.to_datetime(data['date_arrivee'], errors='coerce').dt.to_period('M').astype(str)
    agg = data.groupby(['mois','plateforme'], as_index=False).agg({metric:'sum'})

    st.dataframe(agg, use_container_width=True)

    chart = alt.Chart(agg).mark_bar().encode(
        x='mois:N',
        y=alt.Y(f'{metric}:Q', title=metric.replace('_',' ').title()),
        color='plateforme:N',
        tooltip=['mois','plateforme', alt.Tooltip(f'{metric}:Q', format=',.2f')]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True)

def vue_export_ics(df, palette):
    st.header("📆 Export ICS")
    if df.empty:
        st.info("Aucune réservation."); return
    years = sorted(df['AAAA'].dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df['plateforme'].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = df[df['AAAA']==year].copy()
    if plat!="Tous": data = data[data['plateforme']==plat]

    # UID stables
    miss = data['ical_uid'].isna() | (data['ical_uid'].astype(str).str.strip()=="")
    if miss.any():
        data.loc[miss,'ical_uid'] = data[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    def _fmt(d): return f"{d.year:04d}{d.month:02d}{d.day:02d}"
    def _esc(s): 
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-/Villa Tobias/","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r['date_arrivee'], r['date_depart']
        if not (isinstance(da, date) and isinstance(dd, date)): continue
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get('plateforme'): summary += f" ({r['plateforme']})"
        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {int(r.get('nuitees') or 0)}",
            f"Prix brut: {float(r.get('prix_brut') or 0):.2f} €",
            f"res_id: {r.get('res_id','')}",
        ])
        lines += [
            "BEGIN:VEVENT",
            f"UID:{r['ical_uid']}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt(da)}",
            f"DTEND;VALUE=DATE:{_fmt(dd)}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"
    st.download_button("📥 Télécharger .ics", data=ics.encode('utf-8'), file_name=f"reservations_{year}.ics", mime="text/calendar")

def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée / Google Sheet")
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")
    st.components.v1.iframe(GOOGLE_FORM_URL, height=900, scrolling=True)
    st.markdown("---")
    st.subheader("Feuille Google intégrée")
    st.components.v1.iframe(GOOGLE_SHEET_EMBED_URL, height=700, scrolling=True)
    st.markdown("---")
    st.subheader("Réponses (CSV publié)")
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
        st.dataframe(rep, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")

def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button("Télécharger CSV",
        data=df.to_csv(sep=';', index=False).encode('utf-8'),
        file_name=CSV_RESERVATIONS, mime="text/csv")
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=['csv'])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            with open(CSV_RESERVATIONS, "wb") as f: f.write(up.getvalue())
            st.cache_data.clear()
            st.success("Fichier restauré. Rechargement…"); st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

# ============================== MAIN ==============================
def main():
    # Pas de context manager: on utilise st.sidebar.toggle/checkbox
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)

    apply_modern_style(light=bool(mode_clair))

    st.title("✨ Villa Tobias — Gestion des Réservations")

    df, palette_loaded = charger_donnees()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    pages = {
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "📝 Fiche d'arrivée / Google Sheet": vue_google_sheet,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()