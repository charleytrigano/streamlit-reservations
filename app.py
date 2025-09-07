import streamlit as st
import pandas as pd
import numpy as np
import os, re, json, uuid, hashlib
import altair as alt
from datetime import date, timedelta, datetime
from calendar import monthrange
from urllib.parse import quote, urlencode

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
    """Force la présence des colonnes attendues et les bons types."""
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

    # AAAA / MM
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
    """Construit un UID ICS stable à partir de res_id + nom + tel."""
    base = str(row.get('res_id') or '') + str(row.get('nom_client') or '') + str(row.get('telephone') or '')
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def _format_phone_e164(phone: str) -> str:
    """Transforme un numéro en format international basique."""
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

# ==============================  VUES DE BASE ==============================
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

# ==============================  VUE MODIFIER / SUPPRIMER ==============================
def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer")
    if df.empty:
        st.info("Aucune réservation.")
        return
    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r['nom_client']} ({r['date_arrivee']})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not sel:
        return
    idx = int(sel.split(":")[0])
    original_idx = df_sorted.loc[idx, 'index']
    row = df.loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get('nom_client','') or '')
            tel = st.text_input("Téléphone", value=row.get('telephone','') or '')
            email = st.text_input("Email", value=row.get('email','') or '')
            arr = st.date_input("Arrivée", value=row.get('date_arrivee'))
            dep = st.date_input("Départ", value=row.get('date_depart'))
        with c2:
            plat = st.selectbox("Plateforme", options=list(palette.keys()), index= list(palette.keys()).index(row.get('plateforme')) if row.get('plateforme') in palette else 0)
            paye = st.checkbox("Payé", value=bool(row.get('paye', False)))
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=float(row.get('prix_brut') or 0))
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=float(row.get('commissions') or 0))
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=float(row.get('menage') or 0))
            taxes = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=float(row.get('taxes_sejour') or 0))

        b1, b2 = st.columns([0.7,0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            df.loc[original_idx, 'nom_client'] = nom
            df.loc[original_idx, 'telephone'] = tel
            df.loc[original_idx, 'email'] = email
            df.loc[original_idx, 'date_arrivee'] = arr
            df.loc[original_idx, 'date_depart'] = dep
            df.loc[original_idx, 'plateforme'] = plat
            df.loc[original_idx, 'paye'] = paye
            df.loc[original_idx, 'prix_brut'] = brut
            df.loc[original_idx, 'commissions'] = commissions
            df.loc[original_idx, 'menage'] = menage
            df.loc[original_idx, 'taxes_sejour'] = taxes
            df2 = ensure_schema(df)
            if sauvegarder_donnees(df2):
                st.success("Modifié ✅"); st.rerun()
        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé."); st.rerun()

# ==============================  VUE PLATEFORMES ==============================
def vue_plateformes(df, palette):
    st.header("🎨 Plateformes & couleurs")
    base = pd.DataFrame(list(palette.items()), columns=['plateforme','couleur'])
    edited = st.data_editor(base, num_rows="dynamic", hide_index=True, use_container_width=True)
    if st.button("💾 Enregistrer la palette"):
        try:
            pd.DataFrame(edited).to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette enregistrée ✅")
        except Exception as e:
            st.error(f"Erreur : {e}")

# ==============================  VUE CALENDRIER (simple) ==============================
def vue_calendrier(df, palette):
    st.header("📅 Calendrier (liste du mois)")
    if df.empty:
        st.info("Aucune réservation.")
        return
    today = date.today()
    annee = st.selectbox("Année", sorted(df['AAAA'].dropna().astype(int).unique(), reverse=True).tolist(), index=0 if today.year in df['AAAA'].dropna().astype(int).unique() else 0)
    mois = st.selectbox("Mois", list(range(1,13)), index=today.month-1)
    sel = df[(df['AAAA']==annee) & (df['MM']==mois)].sort_values('date_arrivee')
    st.dataframe(sel[['nom_client','plateforme','date_arrivee','date_depart','nuitees','paye']], use_container_width=True)

# ==============================  VUE SMS & WHATSAPP ==============================
def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")
    # Pré-arrivée (J+1)
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today()+timedelta(days=1), key="pre_date")

    df_tel = df.dropna(subset=['telephone','nom_client','date_arrivee']).copy()
    df_tel['date_arrivee'] = pd.to_datetime(df_tel['date_arrivee'], errors='coerce').dt.date
    df_tel['date_depart']  = pd.to_datetime(df_tel['date_depart'], errors='coerce').dt.date

    df_tel = df_tel[(df_tel['date_arrivee']==target_arrivee) & (~df_tel['sms_envoye'])]
    if df_tel.empty:
        st.info("Aucun client à contacter.")
    else:
        df_tel['_rowid'] = df_tel.index
        df_tel = df_tel.sort_values('date_arrivee')
        options = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in df_tel.reset_index(drop=True).iterrows()]
        sel = st.selectbox("Client", options=options, index=None, key="pre_pick")
        if sel:
            idx = int(sel.split(":")[0])
            resa = df_tel.reset_index(drop=True).loc[idx]
            msg = (
                f"VILLA TOBIAS\n"
                f"Plateforme : {resa.get('plateforme','N/A')}\n"
                f"Arrivée : {resa.get('date_arrivee').strftime('%d/%m/%Y') if pd.notna(resa.get('date_arrivee')) else ''} "
                f"Départ : {resa.get('date_depart').strftime('%d/%m/%Y') if pd.notna(resa.get('date_depart')) else ''} "
                f"Nuitées : {int(resa.get('nuitees') or 0)}\n\n"
                f"Bonjour {resa.get('nom_client')}\n"
                f"Bienvenue ! Merci de nous indiquer votre heure d'arrivée.\n\n"
                f"Fiche d'arrivée : {FORM_SHORT_URL}"
            )
            enc = quote(msg)
            e164 = _format_phone_e164(resa['telephone'])
            wa_num = re.sub(r"\D","",e164)
            c1,c2,c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa_num}?text={enc}")

            if st.button("✅ Marquer 'SMS envoyé'", key=f"mark_pre_{resa['_rowid']}"):
                try:
                    df.loc[resa['_rowid'], 'sms_envoye'] = True
                    if sauvegarder_donnees(ensure_schema(df)):
                        st.success("Marqué ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

    st.markdown("---")
    # Post-départ (J)
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    df_post = df.dropna(subset=['telephone','nom_client','date_depart']).copy()
    df_post['date_depart'] = pd.to_datetime(df_post['date_depart'], errors='coerce').dt.date
    df_post = df_post[(df_post['date_depart']==target_depart) & (~df_post['post_depart_envoye'])]
    if df_post.empty:
        st.info("Aucun message à envoyer.")
    else:
        df_post['_rowid'] = df_post.index
        df_post = df_post.sort_values('date_depart')
        options2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in df_post.reset_index(drop=True).iterrows()]
        sel2 = st.selectbox("Client", options=options2, index=None, key="post_pick")
        if sel2:
            idx2 = int(sel2.split(":")[0])
            resa2 = df_post.reset_index(drop=True).loc[idx2]
            name = str(resa2.get('nom_client') or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Merci d'avoir choisi notre appartement pour votre séjour.\n"
                "Si l'envie vous prend de revenir, notre porte sera toujours ouverte.\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2)
            e164_2 = _format_phone_e164(resa2['telephone'])
            wa_num2 = re.sub(r"\D","",e164_2)
            c1,c2,c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wa_num2}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164_2}?body={enc2}")

            if st.button("✅ Marquer 'post-départ envoyé'", key=f"mark_post_{resa2['_rowid']}"):
                try:
                    df.loc[resa2['_rowid'], 'post_depart_envoye'] = True
                    if sauvegarder_donnees(ensure_schema(df)):
                        st.success("Marqué ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

# ==============================  VUE RAPPORT ==============================
def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée.")
        return
    years = sorted(df['AAAA'].dropna().unique(), reverse=True).tolist()
    year = st.selectbox("Année", years, index=0)
    months_opts = ["Tous"] + list(range(1,13))
    month = st.selectbox("Mois", months_opts, index=0)
    plats = ["Tous"] + sorted(df['plateforme'].dropna().unique())
    plat = st.selectbox("Plateforme", plats, index=0)
    metric = st.selectbox("Métrique", ["prix_brut","prix_net","menage","nuitees"], index=0)

    data = df[df['AAAA']==year].copy()
    if month!="Tous":
        data = data[data['MM']==int(month)]
    if plat!="Tous":
        data = data[data['plateforme']==plat]
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
        tooltip=['mois','plateforme',alt.Tooltip(f'{metric}:Q', format=',.2f')]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True)

# ==============================  VUE EXPORT ICS ==============================
def vue_export_ics(df, palette):
    st.header("📆 Export ICS")
    if df.empty:
        st.info("Aucune réservation.")
        return
    years = sorted(df['AAAA'].dropna().unique(), reverse=True).tolist()
    year = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df['plateforme'].dropna().unique())
    plat = st.selectbox("Plateforme", plats, index=0)

    data = df[df['AAAA']==year].copy()
    if plat!="Tous":
        data = data[data['plateforme']==plat]

    # UIDs stables si manquants
    mask_uid = data['ical_uid'].isna() | (data['ical_uid'].astype(str).str.strip()=="")
    if mask_uid.any():
        data.loc[mask_uid, 'ical_uid'] = data[mask_uid].apply(build_stable_uid, axis=1)

    # Construction ICS simple (journées)
    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    def _fmt(d): return f"{d.year:04d}{d.month:02d}{d.day:02d}"
    def _esc(s): 
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r['date_arrivee'], r['date_depart']
        if not (isinstance(da, date) and isinstance(dd, date)): 
            continue
        uid = r['ical_uid']
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get('plateforme'):
            summary += f" ({r['plateforme']})"
        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Email: {r.get('email','')}",
            f"Nuitées: {int(r.get('nuitees') or 0)}",
            f"Prix brut: {float(r.get('prix_brut') or 0):.2f} €",
            f"res_id: {r.get('res_id','')}",
        ])
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
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

# ==============================  VUE GOOGLE SHEET (intégration visuelle) ==============================
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

# ==============================  SIDEBAR ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button("Télécharger CSV", df.to_csv(sep=';', index=False).encode('utf-8'), file_name=CSV_RESERVATIONS, mime="text/csv")
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=['csv'])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            with open(CSV_RESERVATIONS, "wb") as f:
                f.write(up.getvalue())
            st.cache_data.clear()
            st.success("Fichier restauré. Rechargement...")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

# ==============================  MAIN (sans `with st.sidebar:`) ==============================
def main():
    # Sélecteur de thème en sidebar (pas de context manager)
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_modern_style("light" if mode_clair else "dark")

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