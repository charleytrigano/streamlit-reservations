# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO

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

# ============================== HELPERS ==============================
def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    """Lit un CSV avec tentative ; puis , puis tab puis |"""
    if raw is None: 
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3:
                return df
        except Exception:
            continue
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _to_bool_series(s: pd.Series) -> pd.Series:
    if s is None: 
        return pd.Series([], dtype=bool)
    return s.astype(str).str.strip().str.lower().isin(["true","1","oui","yes","vrai","y","t"])

def _to_num(s: pd.Series) -> pd.Series:
    if s is None: 
        return pd.Series([], dtype="float64")
    sc = (s.astype(str)
            .str.replace("€","",regex=False)
            .str.replace(" ","",regex=False)
            .str.replace(",",".",regex=False)
            .str.strip())
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype="object")
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    return d.dt.date

BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
    "base","charges","%","res_id","ical_uid"
]

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # conversions
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False)

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # nuitées
    mask = df["date_arrivee"].notna() & df["date_depart"].notna()
    df.loc[mask,"nuitees"] = (pd.to_datetime(df.loc[mask,"date_depart"]) - pd.to_datetime(df.loc[mask,"date_arrivee"])).dt.days.clip(lower=0)

    # prix
    df["prix_net"] = df["prix_brut"] - df["commissions"] - df["frais_cb"]
    df["charges"]  = df["prix_brut"] - df["prix_net"]
    df["base"]     = df["prix_net"] - df["menage"] - df["taxes_sejour"]
    with np.errstate(divide="ignore", invalid="ignore"):
        df["%"] = np.where(df["prix_brut"]>0, df["charges"]/df["prix_brut"]*100, 0)

    # ids
    miss = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    df.loc[miss,"res_id"] = [str(uuid.uuid4()) for _ in range(miss.sum())]
    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = df[c].astype(str).replace({"nan":"","None":""}).str.strip()

    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    try:
        with open(CSV_RESERVATIONS,"rb") as f:
            raw = f.read()
        base_df = _detect_delimiter_and_read(raw)
    except Exception:
        base_df = pd.DataFrame()
    df = ensure_schema(base_df)

    palette = DEFAULT_PALETTE.copy()
    try:
        pal = pd.read_csv(CSV_PLATEFORMES, sep=";", dtype=str)
        if {"plateforme","couleur"}.issubset(pal.columns):
            palette = dict(zip(pal["plateforme"], pal["couleur"]))
    except Exception:
        pass

    return df, palette

def sauvegarder_donnees(df: pd.DataFrame):
    out = ensure_schema(df).copy()
    for col in ["date_arrivee","date_depart"]:
        out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
    out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
    st.cache_data.clear()
    return True


# ============================== UI HELPERS ==============================
def _format_money(x: float) -> str:
    try:
        return f"{float(x):,.2f} €".replace(",", " ")
    except Exception:
        return "0.00 €"

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

# ============================== PAGES ==============================
def vue_accueil(df: pd.DataFrame, palette: dict):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfn = ensure_schema(df)

    # Arrivées du jour
    arr_mask = pd.to_datetime(dfn["date_arrivee"], errors="coerce").dt.date == today
    arr = dfn.loc[arr_mask, ["nom_client","telephone","plateforme"]].copy()
    st.subheader("🟢 Arrivées du jour")
    if arr.empty:
        st.info("Aucune arrivée.")
    else:
        st.dataframe(arr, use_container_width=True)

    # Départs du jour
    dep_mask = pd.to_datetime(dfn["date_depart"], errors="coerce").dt.date == today
    dep = dfn.loc[dep_mask, ["nom_client","telephone","plateforme"]].copy()
    st.subheader("🔴 Départs du jour")
    if dep.empty:
        st.info("Aucun départ.")
    else:
        st.dataframe(dep, use_container_width=True)


def vue_reservations(df: pd.DataFrame, palette: dict):
    st.header("📋 Réservations")

    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation.")
        return

    # Filtres par Année / Mois / Plateforme — dérivés depuis date_arrivee
    dfn["_arr"] = pd.to_datetime(dfn["date_arrivee"], errors="coerce")
    years_list  = sorted(dfn["_arr"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_list = list(range(1,13))
    plats_list  = sorted(dfn["plateforme"].astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist())

    col1, col2, col3 = st.columns(3)
    year  = col1.selectbox("Année (arrivée)", ["Toutes"] + years_list, index=0)
    month = col2.selectbox("Mois (arrivée)",  ["Tous"]   + months_list, index=0)
    plat  = col3.selectbox("Plateforme",      ["Toutes"] + plats_list,  index=0)

    data = dfn.copy()
    if year  != "Toutes":
        data = data[data["_arr"].dt.year == int(year)]
    if month != "Tous":
        data = data[data["_arr"].dt.month == int(month)]
    if plat  != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]

    # KPIs
    brut    = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net     = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    base    = float(pd.to_numeric(data["base"],      errors="coerce").fillna(0).sum())
    charges = float(pd.to_numeric(data["charges"],   errors="coerce").fillna(0).sum())
    nuits   = int(pd.to_numeric(data["nuitees"],     errors="coerce").fillna(0).sum())
    adr     = (net/nuits) if nuits>0 else 0.0

    k1, k2, k3, k4, k5, k6 = st.columns(6)
    k1.metric("Brut",  _format_money(brut))
    k2.metric("Net",   _format_money(net))
    k3.metric("Charges", _format_money(charges))
    k4.metric("Base",  _format_money(base))
    k5.metric("Nuitées", f"{nuits}")
    k6.metric("ADR (net)", _format_money(adr))

    # Tableau
    data = data.drop(columns=["_arr"], errors="ignore")
    data = data.sort_values(by=["date_arrivee"], ascending=False)
    st.dataframe(data, use_container_width=True)


def vue_calendrier(df: pd.DataFrame, palette: dict):
    st.header("📅 Calendrier (grille)")
    dfn = ensure_schema(df)
    dfn["date_arrivee"] = pd.to_datetime(dfn["date_arrivee"], errors="coerce").dt.date
    dfn["date_depart"]  = pd.to_datetime(dfn["date_depart"], errors="coerce").dt.date
    dfa = dfn.dropna(subset=["date_arrivee","date_depart"]).copy()
    if dfa.empty:
        st.info("Aucune réservation.")
        return

    today = date.today()
    years = sorted(pd.to_datetime(dfa["date_arrivee"]).dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    # Style simple grille
    st.markdown("""
    <style>
    .cal-grid{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;}
    .cal-cell{border:1px solid rgba(127,127,127,.25);border-radius:8px;min-height:110px;padding:8px;position:relative}
    .cal-date{position:absolute;top:6px;right:8px;opacity:.7;font-weight:700}
    .resa-pill{margin-top:22px;padding:4px 6px;border-radius:6px;color:#fff;font-size:.85rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    .cal-header{display:grid;grid-template-columns:repeat(7,1fr);font-weight:700;opacity:.8;margin:8px 0}
    .outside{opacity:.45}
    </style>
    """, unsafe_allow_html=True)

    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    def day_resas(d):
        # couvre [arrivée, départ)
        mask = (dfa["date_arrivee"] <= d) & (dfa["date_depart"] > d)
        return dfa.loc[mask]

    cal = Calendar(firstweekday=0)
    html = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(annee, mois):
        for d in week:
            outside = (d.month != mois)
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'><div class='cal-date'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                for _, r in rs.iterrows():
                    color = palette.get(r.get("plateforme"), "#888")
                    name  = str(r.get("nom_client") or "")[:22]
                    cell += f"<div class='resa-pill' style='background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    # Détail mois + totaux
    debut_mois = date(annee, mois, 1)
    fin_mois   = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfa[(dfa["date_arrivee"] <= fin_mois) & (dfa["date_depart"] > debut_mois)].copy()
    st.markdown("---")
    st.subheader("Détail du mois sélectionné")
    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
        plat  = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
        if plat != "Toutes":
            rows = rows[rows["plateforme"] == plat]
        brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
        net  = float(pd.to_numeric(rows["prix_net"],  errors="coerce").fillna(0).sum())
        nuits= int(pd.to_numeric(rows["nuitees"],    errors="coerce").fillna(0).sum())
        k1, k2, k3 = st.columns(3)
        k1.metric("Brut", _format_money(brut))
        k2.metric("Net",  _format_money(net))
        k3.metric("Nuitées", f"{nuits}")
        st.dataframe(rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)


def vue_clients(df: pd.DataFrame, palette: dict):
    st.header("👥 Clients")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucun client.")
        return
    clients = (dfn[["nom_client","telephone","email","plateforme","res_id"]]
                .fillna("")
                .astype(str)
                .copy())
    clients = clients[clients["nom_client"].str.strip() != ""]
    clients = clients.drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)


def vue_sms(df: pd.DataFrame, palette: dict):
    st.header("✉️ SMS & WhatsApp")
    dfn = ensure_schema(df).copy()

    # Pré-arrivée (arrivées J+1)
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    dfn["date_arrivee"] = pd.to_datetime(dfn["date_arrivee"], errors="coerce").dt.date
    dfn["date_depart"]  = pd.to_datetime(dfn["date_depart"],  errors="coerce").dt.date
    dfn["sms_envoye"]   = dfn["sms_envoye"].astype(bool)

    pre = dfn.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (pre["sms_envoye"] == False)]

    if pre.empty:
        st.info("Aucun client à contacter.")
    else:
        pre["_rowid"] = pre.index
        pre = pre.sort_values("date_arrivee").reset_index(drop=True)
        opts = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=opts, index=None)
        if pick:
            i = int(pick.split(":")[0]); r = pre.loc[i]
            msg = (
                f"VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  "
                f"Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')}  "
                f"Nuitées : {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')}\n"
                "Bienvenue à Nice ! Merci de nous indiquer votre heure d'arrivée.\n"
                "Check-in 14:00, check-out 11:00. Parking possible.\n\n"
                "Please tell us your arrival time. Check-in 2pm, check-out 11am.\n"
                f"Formulaire: https://urlr.me/kZuH94\n\n"
                "Annick & Charley"
            )
            st.text_area("Message", value=msg, height=220, key=f"ta_pre_{i}")
            enc = quote(msg)
            e164 = _format_phone_e164(r["telephone"])
            wa   = re.sub(r"\D","", e164)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(df):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # Post-départ (départs du jour)
    st.subheader("📤 Post-départ (départs du jour)")
    dfn["post_depart_envoye"] = dfn["post_depart_envoye"].astype(bool)
    target_depart = st.date_input("Départs du", date.today(), key="post_date")

    post = dfn.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post = post[(post["date_depart"] == target_depart) & (post["post_depart_envoye"] == False)]

    if post.empty:
        st.info("Aucun message à envoyer.")
    else:
        post["_rowid"] = post.index
        post = post.sort_values("date_depart").reset_index(drop=True)
        opts2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=opts2, index=None)
        if pick2:
            j = int(pick2.split(":")[0]); r2 = post.loc[j]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Un grand merci d'avoir choisi notre appartement pour votre séjour.\n"
                "Nous espérons que vous avez passé un moment agréable.\n"
                "Si vous souhaitez revenir explorer encore un peu notre ville, "
                "sachez que notre porte vous sera toujours grande ouverte.\n\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n"
                f"\nHello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n"
                "We hope you had as enjoyable a time as we did hosting you.\n"
                "If you feel like coming back to explore our city a little more, "
                "know that our door will always be open to you.\n\n"
                "We look forward to welcoming you back.\n\n"
                "Annick & Charley"
            )
            st.text_area("Message post-départ", value=msg2, height=200, key=f"ta_post_{j}")
            enc2  = quote(msg2)
            e164b = _format_phone_e164(r2["telephone"])
            wab   = re.sub(r"\D","", e164b)
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                df.loc[r2["_rowid"], "post_depart_envoye"] = True
                if sauvegarder_donnees(df):
                    st.success("Marqué ✅"); st.rerun()


def vue_export_ics(df: pd.DataFrame, palette: dict):
    st.header("📆 Export ICS (Google Calendar)")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation.")
        return

    # Filtre simple
    data = dfn.copy()
    # s’assurer UID
    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if miss.any():
        data.loc[miss, "ical_uid"] = data.loc[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _fmt(d):
        if isinstance(d, datetime): d = d.date()
        if not isinstance(d, date): return ""
        return f"{d.year:04d}{d.month:02d}{d.day:02d}"

    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Villa Tobias//Reservations//FR", "CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r["date_arrivee"], r["date_depart"]
        da = pd.to_datetime(da, errors="coerce")
        dd = pd.to_datetime(dd, errors="coerce")
        if pd.isna(da) or pd.isna(dd): 
            continue
        da = da.date(); dd = dd.date()
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"):
            summary += f" ({r['plateforme']})"
        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}",
            f"Prix brut: {float(pd.to_numeric(r.get('prix_brut'), errors='coerce') or 0):.2f} €",
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
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"), file_name=f"reservations_export.ics", mime="text/calendar")


# ============================== ADMIN ==============================
def admin_sidebar(df: pd.DataFrame):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    # Export CSV actuel
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        csv_bytes = out.to_csv(sep=";", index=False).encode("utf-8")
    except Exception:
        csv_bytes = b""
    st.sidebar.download_button(
        "⬇️ Télécharger CSV",
        data=csv_bytes,
        file_name="reservations.csv",
        mime="text/csv"
    )

    # Restauration CSV ou XLSX
    up = st.sidebar.file_uploader("Restaurer (CSV ou XLSX)", type=["csv","xlsx"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            if up.name.lower().endswith(".xlsx"):
                tmp = pd.read_excel(up, dtype=str)
            else:
                raw = up.read()
                tmp = _detect_delimiter_and_read(raw)
            tmp = ensure_schema(tmp)

            # Sauvegarde normalisée
            save = tmp.copy()
            for col in ["date_arrivee","date_depart"]:
                save[col] = pd.to_datetime(save[col], errors="coerce").dt.strftime("%d/%m/%Y")
            save.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.cache_data.clear()
            st.success("Fichier restauré — rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur restauration : {e}")

    # Purge cache
    if st.sidebar.button("🧹 Vider le cache & recharger"):
        try: st.cache_data.clear()
        except Exception: pass
        st.success("Cache vidé.")
        st.rerun()


# ============================== MAIN ==============================
def main():
    st.title("✨ Villa Tobias — Gestion des Réservations")

    df, palette_loaded = charger_donnees()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "📅 Calendrier": vue_calendrier,
        "👥 Clients": vue_clients,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)


if __name__ == "__main__":
    main()