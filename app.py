# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# ============================== STYLE ==============================
def apply_style():
    st.markdown(
        """
        <style>
        [data-testid="stSidebar"] {
            background: #171923; color: #fff;
        }
        .glass {
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(124,92,255,.16);
            border-radius: 12px;
            padding: 12px; margin: 8px 0;
        }
        .cal-grid {
            display:grid; grid-template-columns: repeat(7, 1fr);
            gap:6px; margin-top:8px;
        }
        .cal-cell {
            border:1px solid rgba(124,92,255,.16);
            border-radius:8px; min-height:100px; padding:6px;
            position:relative; overflow:hidden;
        }
        .cal-cell.outside { opacity:.4; }
        .cal-date {
            position:absolute; top:4px; right:6px;
            font-weight:700; font-size:.8rem; opacity:.7;
        }
        .resa-pill {
            padding:3px 5px; border-radius:6px; font-size:.75rem;
            margin-top:20px; color:#fff; overflow:hidden;
            text-overflow:ellipsis; white-space:nowrap;
        }
        .cal-header {
            display:grid; grid-template-columns: repeat(7, 1fr);
            font-weight:700; opacity:.8; margin-top:10px;
        }
        </style>
        """,
        unsafe_allow_html=True)
    )

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)

# ============================== DATA ==============================
BASE_COLS = [
    "paye","nom_client","sms_envoye","post_depart_envoye","plateforme","telephone","email",
    "date_arrivee","date_depart","nuitees","prix_brut","prix_net","commissions","frais_cb","menage","taxes_sejour",
    "res_id","ical_uid","AAAA","MM"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=BASE_COLS)
    df = df.copy()

    for c in ["date_arrivee","date_depart"]:
        df[c] = pd.to_datetime(df.get(c), errors="coerce").dt.date

    for b in ["paye","sms_envoye","post_depart_envoye"]:
        if b not in df.columns: df[b] = False
        df[b] = df[b].astype(str).str.lower().isin(["true","1","oui","yes","vrai"]).fillna(False)

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees"]:
        df[n] = pd.to_numeric(df.get(n), errors="coerce").fillna(0.0)

    df["prix_net"] = df["prix_brut"] - df["commissions"] - df["frais_cb"]

    if "res_id" not in df.columns: df["res_id"] = None
    miss = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss.any():
        df.loc[miss, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss.sum()))]

    df["AAAA"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year
    df["MM"]   = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.month

    for c in BASE_COLS:
        if c not in df.columns: df[c] = None

    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=";")
    except Exception:
        df = pd.DataFrame()
    df = ensure_schema(df)

    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";")
        palette = dict(zip(df_pal["plateforme"], df_pal["couleur"]))
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

# ============================== VUES ==============================
def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty:
        st.info("Aucune réservation.")
        return

    # filtres
    annees = ["Toutes"] + sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True).tolist()
    annee_sel = st.sidebar.selectbox("Année", annees, index=0)
    mois_opts = ["Tous"] + list(range(1, 13))
    mois_sel = st.sidebar.selectbox("Mois", mois_opts, index=0)
    plats = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    plat_sel = st.sidebar.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    if annee_sel != "Toutes": data = data[data["AAAA"] == int(annee_sel)]
    if mois_sel != "Tous":   data = data[data["MM"] == int(mois_sel)]
    if plat_sel != "Toutes": data = data[data["plateforme"] == plat_sel]

    brut  = float(data["prix_brut"].sum())
    net   = float(data["prix_net"].sum())
    nuits = int(data["nuitees"].sum())
    adr   = (net/nuits) if nuits>0 else 0.0
    menage = float(data["menage"].sum())
    taxes  = float(data["taxes_sejour"].sum())
    comm   = float(data["commissions"].sum())

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("Revenu brut", f"{brut:,.0f} €".replace(",", " "))
    c2.metric("Revenu net", f"{net:,.0f} €".replace(",", " "))
    c3.metric("Nuitées", f"{nuits}")
    c4.metric("ADR (net)", f"{adr:,.0f} €".replace(",", " "))
    c5.metric("Commissions", f"{comm:,.0f} €".replace(",", " "))
    c6.metric("Taxes séjour", f"{taxes:,.0f} €".replace(",", " "))

    st.dataframe(data.sort_values("date_arrivee", ascending=False), use_container_width=True)

# --------- CALENDRIER ----------
def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")
    dfv = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(dfv['date_arrivee'].apply(lambda d: d.year).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])

    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    def day_resas(d):
        mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)
    html = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(annee, mois):
        for d in week:
            outside = (d.month != mois)
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'>"
            cell += f"<div class='cal-date'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                for _, r in rs.iterrows():
                    color = palette.get(r.get('plateforme'), '#888')
                    name  = str(r.get('nom_client') or '')[:18]
                    cell += f"<div class='resa-pill' style='background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Détails du mois sélectionné")
    mois_rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()
    if mois_rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        st.dataframe(mois_rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)

# --------- RAPPORT ----------
def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée."); return
    years = sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1,13))
    month = st.selectbox("Mois", months, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)
    metric = st.selectbox("Métrique", ["prix_brut","prix_net","nuitees","menage","taxes_sejour","commissions"], index=0)

    data = df[df["AAAA"]==year].copy()
    if month!="Tous": data = data[data["MM"]==int(month)]
    if plat!="Tous":  data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Aucune donnée après filtres."); return

    data["mois"] = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.to_period("M").astype(str)
    agg = data.groupby(["mois","plateforme"], as_index=False).agg({metric:"sum"})
    st.dataframe(agg, use_container_width=True)

    chart = alt.Chart(agg).mark_bar().encode(
        x="mois:N",
        y=alt.Y(f"{metric}:Q", title=metric.replace("_"," ").title()),
        color="plateforme:N",
        tooltip=["mois","plateforme", alt.Tooltip(f"{metric}:Q", format=",.0f")]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True

from urllib.parse import quote

# --------- UTIL pour copier texte ---------
def _copy_button_js(label: str, payload: str, key: str):
    st.components.v1.html(
        f"""
        <button onclick="navigator.clipboard.writeText({json.dumps(payload)})"
                style="padding:6px 10px;border-radius:8px;border:1px solid rgba(127,127,127,.35);
                       background:#222;color:#fff;cursor:pointer;margin-top:4px">
            {label}
        </button>
        """,
        height=36,
    )

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

# --------- SMS ---------
def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # Pré-arrivée
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = date.today() + timedelta(days=1)
    pre = df.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre["date_arrivee"] = pd.to_datetime(pre["date_arrivee"], errors="coerce").dt.date
    pre["date_depart"]  = pd.to_datetime(pre["date_depart"], errors="coerce").dt.date
    pre = pre[(pre["date_arrivee"]==target_arrivee) & (~pre["sms_envoye"])]
    if pre.empty:
        st.info("Aucun client à contacter.")
    else:
        for i, r in pre.iterrows():
            msg = (
                "VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  "
                f"Départ : {r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else ''}  "
                f"Nuitées : {int(r.get('nuitees') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')},\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. "
                "Merci de nous indiquer votre heure d'arrivée.\n\n"
                "➡️ Parking disponible. Check-in 14h, check-out 11h.\n"
                "Merci de remplir la fiche : https://urlr.me/kZuH94\n\n"
                "EN — Please tell us your arrival time. Parking on request. "
                "Check-in from 2pm, check-out before 11am. "
                "Form: https://urlr.me/kZuH94\n\n"
                "Annick & Charley"
            )
            enc = quote(msg)
            e164 = _format_phone_e164(r["telephone"])
            wa = re.sub(r"\D","", e164)

            st.text_area(f"Prévisualisation {r['nom_client']}", value=msg, height=200)
            _copy_button_js("📋 Copier", msg, key=f"cpy_pre_{i}")
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button(f"✅ Marquer envoyé ({r['nom_client']})", key=f"pre_mark_{i}"):
                df.loc[i, "sms_envoye"] = True
                if sauvegarder_donnees(df): st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # Post-départ
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = date.today()
    post = df.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post["date_depart"] = pd.to_datetime(post["date_depart"], errors="coerce").dt.date
    post = post[(post["date_depart"]==target_depart) & (~post["post_depart_envoye"])]
    if post.empty:
        st.info("Aucun message à envoyer.")
    else:
        for j, r in post.iterrows():
            name = str(r.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Un grand merci d'avoir choisi notre appartement pour votre séjour.\n"
                "Nous espérons que vous avez passé un moment agréable.\n"
                "Si vous souhaitez revenir, notre porte vous sera toujours grande ouverte.\n\n"
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay. "
                "We hope you had a great time — you're always welcome back!\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2)
            e164b = _format_phone_e164(r["telephone"])
            wab = re.sub(r"\D","", e164b)

            st.text_area(f"Prévisualisation {name}", value=msg2, height=180)
            _copy_button_js("📋 Copier", msg2, key=f"cpy_post_{j}")
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button(f"✅ Marquer envoyé ({name})", key=f"post_mark_{j}"):
                df.loc[j, "post_depart_envoye"] = True
                if sauvegarder_donnees(df): st.success("Marqué ✅"); st.rerun()

# --------- EXPORT ICS ---------
def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    if df.empty:
        st.info("Aucune réservation."); return
    years = sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = df[df["AAAA"]==year].copy()
    if plat!="Tous": data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Rien à exporter."); return

    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if miss.any():
        data.loc[miss, "ical_uid"] = data[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    def _fmt(d): return f"{d.year:04d}{d.month:02d}{d.day:02d}"
    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r["date_arrivee"], r["date_depart"]
        if not (isinstance(da, date) and isinstance(dd, date)): continue
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"): summary += f" ({r['plateforme']})"
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
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"), file_name=f"reservations_{year}.ics", mime="text/calendar")

# --------- GOOGLE SHEET + FORM ---------
def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée / Google Sheet")
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")

    # Formulaire
    st.markdown(
        f'<iframe src="{GOOGLE_FORM_URL}" width="100%" height="900" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )

    st.markdown("---")
    st.subheader("📑 Feuille Google intégrée")
    st.markdown(
        f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )

    st.markdown("---")
    st.subheader("📊 Réponses (CSV publié)")
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
        st.dataframe(rep, use_container_width=True)
        st.download_button("⬇️ Télécharger CSV", data=rep.to_csv(index=False).encode("utf-8"),
                           file_name="reponses_formulaire.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")

# --------- ADMIN ---------
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    st.sidebar.download_button(
        "⬇️ Télécharger CSV",
        data=df.to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )

    uploaded = st.sidebar.file_uploader("📤 Restaurer depuis un CSV", type=["csv"])
    if uploaded is not None and st.sidebar.button("Confirmer restauration"):
        try:
            with open(CSV_RESERVATIONS, "wb") as f: f.write(uploaded.getvalue())
            st.cache_data.clear()
            st.success("✅ Fichier restauré. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur restauration : {e}")

    if st.sidebar.button("🧹 Vider le cache"):
        st.cache_data.clear()
        st.success("Cache vidé ✅")
        st.rerun()

# --------- MAIN ---------
def main():
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

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

    choice = st.sidebar.radio("📑 Navigation", list(pages.keys()))
    pages[choice](df, palette)

    admin_sidebar(df)

if __name__ == "__main__":
    main()