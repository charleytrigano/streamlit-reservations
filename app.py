import streamlit as st
import pandas as pd
import numpy as np
import uuid
import hashlib
import json
import re
import altair as alt
from urllib.parse import urlencode, quote
from datetime import date, timedelta, datetime
from calendar import monthrange

# ============================== CONFIG ==============================
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pubhtml?gid=1915058425&single=true"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?gid=1915058425&single=true&output=csv"
FORM_SHORT_URL = "https://urlr.me/kZuH94"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb": "#e74c3c",
    "Abritel": "#9b59b6",
    "Autre": "#f59e0b"
}

BASE_COLS = [
    'paye','nom_client','email','telephone','plateforme','date_arrivee','date_depart',
    'nuitees','prix_brut','commissions','frais_cb','prix_net','menage','taxes_sejour',
    'base','charges','%','AAAA','MM','sms_envoye','post_depart_envoye','res_id','ical_uid'
]

# ============================== HELPERS ==============================
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=BASE_COLS)
    for col in BASE_COLS:
        if col not in df.columns:
            df[col] = None
    df['date_arrivee'] = pd.to_datetime(df['date_arrivee'], errors='coerce').dt.date
    df['date_depart']  = pd.to_datetime(df['date_depart'], errors='coerce').dt.date
    mask = df['date_arrivee'].notna() & df['date_depart'].notna()
    df.loc[mask, 'nuitees'] = (pd.to_datetime(df.loc[mask,'date_depart']) - pd.to_datetime(df.loc[mask,'date_arrivee'])).dt.days
    for col in ['paye','sms_envoye','post_depart_envoye']:
        df[col] = df[col].fillna(False).astype(bool)
    for col in ['prix_brut','commissions','frais_cb','menage','taxes_sejour']:
        df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
    df['prix_net'] = df['prix_brut'] - df['commissions'] - df['frais_cb']
    df['charges'] = df['prix_brut'] - df['prix_net']
    df['base'] = df['prix_net'] - df['menage'] - df['taxes_sejour']
    with np.errstate(divide='ignore', invalid='ignore'):
        df['%'] = np.where(df['prix_brut'] > 0, df['charges'] / df['prix_brut'] * 100, 0)
    df['AAAA'] = pd.to_datetime(df['date_arrivee'], errors='coerce').dt.year
    df['MM']   = pd.to_datetime(df['date_arrivee'], errors='coerce').dt.month
    return df

@st.cache_data
def charger_donnees():
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=";")
    except Exception:
        df = pd.DataFrame(columns=BASE_COLS)
    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";")
        palette = dict(zip(df_pal['plateforme'], df_pal['couleur']))
    except Exception:
        palette = DEFAULT_PALETTE.copy()
    return ensure_schema(df), palette

def sauvegarder_donnees(df: pd.DataFrame):
    try:
        df.to_csv(CSV_RESERVATIONS, sep=";", index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur sauvegarde: {e}")
        return False

def _ensure_res_id_on_row(df, idx):
    if pd.isna(df.at[idx,'res_id']) or not str(df.at[idx,'res_id']).strip():
        df.at[idx,'res_id'] = str(uuid.uuid4())
    return df.at[idx,'res_id']

def build_stable_uid(row):
    base = f"{row.get('res_id','')}_{row.get('nom_client','')}_{row.get('telephone','')}"
    return hashlib.sha256(base.encode()).hexdigest()[:16]

# ============================== VUES ==============================
def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty:
        st.info("Aucune donnée")
        return
    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index(drop=True)
    st.dataframe(df_sorted, use_container_width=True)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter")
    with st.form("ajout"):
        nom = st.text_input("Nom")
        tel = st.text_input("Téléphone")
        email = st.text_input("Email")
        plat = st.selectbox("Plateforme", list(palette.keys()))
        arr  = st.date_input("Arrivée", value=date.today())
        dep  = st.date_input("Départ", value=date.today()+timedelta(days=1))
        brut = st.number_input("Prix brut", 0.0)
        com  = st.number_input("Commissions", 0.0)
        paye = st.checkbox("Payé", value=False)
        ok = st.form_submit_button("Ajouter")
    if ok:
        new = pd.DataFrame([{
            "nom_client": nom, "telephone": tel, "email": email,
            "plateforme": plat, "date_arrivee": arr, "date_depart": dep,
            "prix_brut": brut, "commissions": com, "paye": paye
        }])
        df2 = pd.concat([df,new], ignore_index=True)
        df2 = ensure_schema(df2)
        if sauvegarder_donnees(df2):
            st.success("Ajouté ✅")
            st.rerun()

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer")
    if df.empty:
        st.info("Vide")
        return
    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    opts = [f"{i}: {r['nom_client']} ({r['date_arrivee']})" for i,r in df_sorted.iterrows()]
    sel = st.selectbox("Choisir", opts, index=None)
    if not sel: return
    idx = int(sel.split(":")[0])
    orig = df_sorted.loc[idx,'index']
    row = df.loc[orig]
    with st.form("modif"):
        nom = st.text_input("Nom", row['nom_client'])
        tel = st.text_input("Tel", row['telephone'])
        dep = st.date_input("Départ", row['date_depart'])
        arr = st.date_input("Arrivée", row['date_arrivee'])
        plat = st.selectbox("Plateforme", list(palette.keys()), index=0)
        ok = st.form_submit_button("Enregistrer")
        sup= st.form_submit_button("Supprimer")
    if ok:
        df.loc[orig,'nom_client'] = nom
        df.loc[orig,'telephone'] = tel
        df.loc[orig,'date_arrivee'] = arr
        df.loc[orig,'date_depart'] = dep
        df.loc[orig,'plateforme'] = plat
        if sauvegarder_donnees(df): st.success("Modifié ✅"); st.rerun()
    if sup:
        df2 = df.drop(index=orig)
        if sauvegarder_donnees(df2): st.warning("Supprimé"); st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Plateformes")
    base = pd.DataFrame(list(palette.items()), columns=['plateforme','couleur'])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    if st.button("💾 Enregistrer palette"):
        edited.to_csv(CSV_PLATEFORMES, sep=";", index=False)
        st.success("Palette sauvée ✅")
        st.rerun()

# ============================== SUITE : CALENDRIER / RAPPORT / SMS / ICS / SHEET / ADMIN / MAIN ==============================

# Petit helper (si absent)
def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s:
        return ""
    if s.startswith("33"):
        return "+"+s
    if s.startswith("0"):
        return "+33"+s[1:]
    return "+"+s

# ------------------------------ CALENDRIER (liste mensuelle) ------------------------------
def vue_calendrier(df, palette):
    st.header("📅 Calendrier (liste du mois)")
    if df.empty:
        st.info("Aucune réservation.")
        return
    years = sorted(df['AAAA'].dropna().astype(int).unique(), reverse=True)
    year = st.selectbox("Année", options=years, index=0)
    month = st.selectbox("Mois", options=list(range(1,13)), index=0)
    sel = df[(df['AAAA']==year) & (df['MM']==month)].sort_values('date_arrivee')
    st.dataframe(sel[['nom_client','plateforme','date_arrivee','date_depart','nuitees','paye']], use_container_width=True)

# ------------------------------ RAPPORT ------------------------------
def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée.")
        return
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
        st.warning("Aucune donnée après filtres.")
        return

    data['mois'] = pd.to_datetime(data['date_arrivee'], errors='coerce').dt.to_period('M').astype(str)
    agg = data.groupby(['mois','plateforme'], as_index=False).agg({metric:'sum'})
    st.dataframe(agg, use_container_width=True)

    chart = alt.Chart(agg).mark_bar().encode(
        x='mois:N',
        y=alt.Y(f'{metric}:Q', title=metric.replace('_',' ').title()),
        color='plateforme:N',
        tooltip=['mois','plateforme', alt.Tooltip(f'{metric}:Q', format=",.2f")]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True)

# ------------------------------ SMS & WHATSAPP ------------------------------
def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # Pré-arrivée (J+1)
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today()+timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=['telephone','nom_client','date_arrivee']).copy()
    pre['date_arrivee'] = pd.to_datetime(pre['date_arrivee'], errors='coerce').dt.date
    pre['date_depart']  = pd.to_datetime(pre['date_depart'], errors='coerce').dt.date
    pre = pre[(pre['date_arrivee']==target_arrivee) & (~pre['sms_envoye'])]

    if pre.empty:
        st.info("Aucun client à contacter.")
    else:
        pre['_rowid'] = pre.index
        pre = pre.sort_values('date_arrivee').reset_index(drop=True)
        opts = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=opts, index=None)
        if pick:
            i = int(pick.split(":")[0]); r = pre.loc[i]
            msg = (
                "VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')} "
                f"Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')} "
                f"Nuitées : {int(r.get('nuitees') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')}\n"
                "Merci de nous indiquer votre heure d'arrivée.\n\n"
                f"Fiche d'arrivée : {FORM_SHORT_URL}"
            )
            enc = quote(msg)
            e164 = _format_phone_e164(r['telephone'])
            wa = re.sub(r"\D","", e164)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_{r['_rowid']}"):
                df.loc[r['_rowid'],'sms_envoye'] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # Post-départ (J)
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = df.dropna(subset=['telephone','nom_client','date_depart']).copy()
    post['date_depart'] = pd.to_datetime(post['date_depart'], errors='coerce').dt.date
    post = post[(post['date_depart']==target_depart) & (~post['post_depart_envoye'])]

    if post.empty:
        st.info("Aucun message à envoyer.")
    else:
        post['_rowid'] = post.index
        post = post.sort_values('date_depart').reset_index(drop=True)
        opts2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=opts2, index=None)
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
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_{r2['_rowid']}"):
                df.loc[r2['_rowid'],'post_depart_envoye'] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

# ------------------------------ EXPORT ICS ------------------------------
def vue_export_ics(df, palette):
    st.header("📆 Export ICS")
    if df.empty:
        st.info("Aucune réservation.")
        return
    years = sorted(df['AAAA'].dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df['plateforme'].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = df[df['AAAA']==year].copy()
    if plat!="Tous":
        data = data[data['plateforme']==plat]
    if data.empty:
        st.warning("Rien à exporter avec ces filtres.")
        return

    # UID stables si manquants
    mask_uid = data['ical_uid'].isna() | (data['ical_uid'].astype(str).str.strip()=="")
    if mask_uid.any():
        data.loc[mask_uid,'ical_uid'] = data[mask_uid].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    def _fmt(d): return f"{d.year:04d}{d.month:02d}{d.day:02d}"
    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
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
    st.download_button("📥 Télécharger .ics", data=ics.encode('utf-8'),
                       file_name=f"reservations_{year}.ics", mime="text/calendar")

# ------------------------------ GOOGLE FORM / SHEET ------------------------------
def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée / Google Sheet")
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")

    # IMPORTANT : ne pas passer 'scrolling' (incompatible avec Streamlit 1.35 ici)
    st.components.v1.iframe(GOOGLE_FORM_URL, height=900)

    st.markdown("---")
    st.subheader("Feuille Google intégrée")
    st.components.v1.iframe(GOOGLE_SHEET_EMBED_URL, height=700)

    st.markdown("---")
    st.subheader("Réponses (CSV publié)")
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
        st.dataframe(rep, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")

# ------------------------------ ADMIN SIDEBAR ------------------------------
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button(
        "Télécharger CSV",
        data=df.to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            with open(CSV_RESERVATIONS, "wb") as f:
                f.write(up.getvalue())
            st.cache_data.clear()
            st.success("Fichier restauré. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

# ------------------------------ MAIN ------------------------------
def main():
    st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)

    # style très léger (optionnel)
    st.markdown(
        f"""
        <style>
          html, body, [data-testid="stAppViewContainer"] {{
            background: {"#fafafa" if mode_clair else "#0f1115"};
            color: {"#0f172a" if mode_clair else "#eaeef6"};
          }}
          [data-testid="stSidebar"] {{
            background: {"#f2f2f2" if mode_clair else "#171923"};
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

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
        "📝 Google Sheet": vue_google_sheet,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()