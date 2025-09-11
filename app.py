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

# --- HARD CLEAR : purger cache au chargement du script ---
try:
    try: st.cache_data.clear()
    except Exception: pass
    try: st.cache_resource.clear()
    except Exception: pass
except Exception:
    pass

CSV_RESERVATIONS = "reservations_normalise.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# ============================== STYLE ==============================
def apply_style(light: bool):
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    st.markdown(
        f"""
        <style>
          html, body, [data-testid="stAppViewContainer"] {{
            background: {bg}; color: {fg};
          }}
          [data-testid="stSidebar"] {{
            background: {side}; border-right: 1px solid {border};
          }}
          .glass {{
            background: {"rgba(255,255,255,0.65)" if light else "rgba(255,255,255,0.06)"};
            border: 1px solid {border}; border-radius: 12px; padding: 12px; margin: 8px 0;
          }}
          .chip {{
            display:inline-block; background:#444; color:#fff;
            padding:6px 10px; border-radius:12px; margin:4px 6px; font-size:0.82rem
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

# ============================== DATA ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid","AAAA","MM"
]

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3:
                return df
        except Exception: continue
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _to_bool_series(s: pd.Series) -> pd.Series:
    return pd.Series(s.astype(str).str.strip().str.lower().isin(["true","1","oui","yes","y"]), index=s.index)

def _to_num(s: pd.Series) -> pd.Series:
    sc = (
        s.astype(str)
         .str.replace("€","",regex=False)
         .str.replace(" ","",regex=False)
         .str.replace(",",".",regex=False)
         .str.strip()
    )
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)
    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()
    for c in BASE_COLS:
        if c not in df.columns: df[c] = None
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])
    mask = df["date_arrivee"].notna() & df["date_depart"].notna()
    if mask.any():
        da = pd.to_datetime(df.loc[mask,"date_arrivee"])
        dd = pd.to_datetime(df.loc[mask,"date_depart"])
        df.loc[mask,"nuitees"] = (dd - da).dt.days.clip(lower=0)
    df["prix_net"] = (_to_num(df["prix_brut"]) - _to_num(df["commissions"]) - _to_num(df["frais_cb"])).fillna(0.0)
    df["charges"]  = (_to_num(df["prix_brut"]) - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - _to_num(df["menage"]) - _to_num(df["taxes_sejour"])).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(_to_num(df["prix_brut"])>0, (df["charges"]/_to_num(df["prix_brut"])*100), 0)
    df["%"] = pd.Series(pct, index=df.index).fillna(0.0)
    da_all = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = pd.to_numeric(da_all.dt.year, errors="coerce")
    df["MM"]   = pd.to_numeric(da_all.dt.month, errors="coerce")
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res,"res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]
    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = df[c].astype(str).replace({"nan":"","None":""}).str.strip()
    return df[BASE_COLS]

@st.cache_data
def _load_file_bytes(path: str):
    try:
        with open(path,"rb") as f: return f.read()
    except Exception: return None

@st.cache_data
def charger_donnees():
    raw = _load_file_bytes(CSV_RESERVATIONS)
    base_df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
    df = ensure_schema(base_df)
    rawp = _load_file_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if rawp:
        pal_df = _detect_delimiter_and_read(rawp)
        if set(["plateforme","couleur"]).issubset(pal_df.columns):
            palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
    return df, palette


# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    arr = df[df["date_arrivee"] == today][["nom_client","telephone","plateforme"]]
    dep = df[df["date_depart"] == today][["nom_client","telephone","plateforme"]]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame([{"nom_client":"—","telephone":"—","plateforme":"—"}]))
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame([{"nom_client":"—","telephone":"—","plateforme":"—"}]))

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty:
        st.info("Aucune réservation.")
        return

    years_ser  = pd.to_numeric(df["AAAA"], errors="coerce")
    months_ser = pd.to_numeric(df["MM"],   errors="coerce")

    years  = ["Toutes"] + sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True)
    months = ["Tous"]   + sorted(months_ser.dropna().astype(int).unique().tolist())
    plats  = ["Toutes"] + sorted(df["plateforme"].dropna().unique())

    colf1, colf2, colf3 = st.columns(3)
    year  = colf1.selectbox("Année", years, index=0)
    month = colf2.selectbox("Mois", months, index=0)
    plat  = colf3.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    if year != "Toutes": data = data[data["AAAA"]==int(year)]
    if month != "Tous":  data = data[data["MM"]==int(month)]
    if plat != "Toutes": data = data[data["plateforme"]==plat]

    brut = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(data["prix_net"], errors="coerce").fillna(0).sum())
    base = float(pd.to_numeric(data["base"], errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(data["nuitees"], errors="coerce").fillna(0).sum())

    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'>Total brut : {brut:,.2f} €</span>
          <span class='chip'>Net : {net:,.2f} €</span>
          <span class='chip'>Base : {base:,.2f} €</span>
          <span class='chip'>Nuitées : {nuits}</span>
        </div>
        """.replace(",", " "),
        unsafe_allow_html=True
    )

    st.dataframe(data, use_container_width=True)

def vue_clients(df, palette):
    st.header("👥 Clients")
    if df.empty:
        st.info("Aucun client.")
        return
    clients = df[["nom_client","telephone","email","plateforme","res_id"]].drop_duplicates()
    st.dataframe(clients.sort_values("nom_client"), use_container_width=True)

def vue_export_ics(df, palette):
    st.header("📆 Export ICS")
    if df.empty:
        st.info("Aucune réservation.")
        return
    year = st.selectbox("Année", sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True))
    data = df[df["AAAA"]==year].copy()

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    def _fmt(d):
        if isinstance(d, (date, datetime)):
            if isinstance(d, datetime): d = d.date()
            return f"{d.year:04d}{d.month:02d}{d.day:02d}"
        return ""
    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR"]
    for _, r in data.iterrows():
        da, dd = r["date_arrivee"], r["date_depart"]
        if not da or not dd: continue
        summary = f"{r['nom_client']} ({r['plateforme']})"
        desc = f"Téléphone: {r['telephone']}\\nPrix brut: {r['prix_brut']} €"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{r['ical_uid']}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt(da)}",
            f"DTEND;VALUE=DATE:{_fmt(dd)}",
            f"SUMMARY:{summary}",
            f"DESCRIPTION:{desc}",
            "END:VEVENT"
        ]
    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines)
    st.download_button("📥 Télécharger ICS", data=ics, file_name=f"reservations_{year}.ics", mime="text/calendar")

# ============================== ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button(
        "Télécharger CSV",
        data=ensure_schema(df).to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )
    up = st.sidebar.file_uploader("Restaurer CSV", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        content = up.read()
        tmp_df = _detect_delimiter_and_read(content)
        tmp_df = ensure_schema(tmp_df)
        tmp_df.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        st.cache_data.clear(); st.success("Fichier restauré ✅"); st.rerun()

    if st.sidebar.button("🧹 Vider le cache"):
        st.cache_data.clear(); st.cache_resource.clear(); st.rerun()


from calendar import Calendar, monthrange

def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")

    dfv = df.dropna(subset=["date_arrivee", "date_depart"]).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    # Afficher en-tête du calendrier
    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    def day_resas(d):
        mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)  # lundi
    html = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(annee, mois):
        for d in week:
            outside = (d.month != mois)
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'>"
            cell += f"<div class='cal-date'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                if not rs.empty:
                    for _, r in rs.iterrows():
                        color = palette.get(r.get('plateforme'), '#888')
                        name  = str(r.get('nom_client') or '')[:20]
                        cell += f"<div class='resa-pill' style='background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    # Détail du mois
    st.markdown("---")
    st.subheader("Détail du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()
    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
        plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
        if plat != "Toutes":
            rows = rows[rows["plateforme"] == plat]

        brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
        net  = float(pd.to_numeric(rows["prix_net"],  errors="coerce").fillna(0).sum())
        nuits= int(pd.to_numeric(rows["nuitees"],    errors="coerce").fillna(0).sum())
        html = f"""
        <div class='glass kpi-line'>
          <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
          <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
          <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
        </div>
        """.replace(",", " ")
        st.markdown(html, unsafe_allow_html=True)
        st.dataframe(rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)

# ============================== MAIN ==============================
def main():
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair", value=False)
    except:
        mode_clair = False
    apply_style(light=mode_clair)

    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette = charger_donnees()

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "👥 Clients": vue_clients,
        "📆 Export ICS": vue_export_ics,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()