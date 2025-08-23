# app.py — Villa Tobias (COMPLET)
# Réservations, Calendrier, Rapport, ICS, SMS, Sauvegarde/Restaurer

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
import colorsys

FICHIER = "reservations.xlsx"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",  # bleu
    "Airbnb":  "#e74c3c",  # rouge
    "Autre":   "#f59e0b",  # orange
}

def get_palette() -> dict:
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = palette

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

def render_palette_editor_sidebar():
    palette = get_palette()
    st.sidebar.markdown("## 🎨 Plateformes")
    with st.sidebar.expander("➕ Ajouter / modifier des plateformes", expanded=False):
        c1, c2 = st.columns([2,1])
        with c1:
            new_name = st.text_input("Nom de la plateforme", key="pal_new_name")
        with c2:
            new_color = st.color_picker("Couleur", key="pal_new_color", value="#9b59b6")
        if st.button("Ajouter / Mettre à jour"):
            if new_name:
                palette[new_name] = new_color
                save_palette(palette)
                st.success(f"✅ Plateforme « {new_name} » enregistrée.")
        if st.button("Réinitialiser la palette"):
            save_palette(DEFAULT_PALETTE.copy())
            st.success("✅ Palette réinitialisée.")
    if palette:
        st.sidebar.markdown("**Plateformes existantes :**")
        for pf in sorted(palette.keys()):
            st.sidebar.markdown(platform_badge(pf, palette), unsafe_allow_html=True)

# ==============================  OUTILS  ==============================

def to_date_only(x):
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s

# ==============================  SCHEMA & CALCULS  ==============================

BASE_COLS = [
    "paye","nom_client","sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%","AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    df["date_arrivee"] = df["date_arrivee"].apply(to_date_only)
    df["date_depart"] = df["date_depart"].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    df["nuitees"] = [
        (d2 - d1).days if isinstance(d1, date) and isinstance(d2, date) else np.nan
        for d1,d2 in zip(df["date_arrivee"], df["date_depart"])
    ]
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d,date) else np.nan)
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d,date) else np.nan)
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"] = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"] = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    df["%"] = (df["charges"]/df["prix_brut"]*100).fillna(0)
    return df

def split_totals(df: pd.DataFrame):
    mask = df["nom_client"].str.lower().eq("total")
    return df[~mask], df[mask]

def sort_core(df: pd.DataFrame):
    return df.sort_values(["date_arrivee","nom_client"]).reset_index(drop=True)

# ==============================  EXCEL I/O  ==============================

@st.cache_data
def _read_excel(path: str, mtime: float):
    return pd.read_excel(path, engine="openpyxl", converters={"telephone": normalize_tel})

def charger_donnees():
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    mtime = os.path.getmtime(FICHIER)
    return ensure_schema(_read_excel(FICHIER, mtime))

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    out = pd.concat([sort_core(core), totals], ignore_index=True)
    with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
        out.to_excel(w, index=False)
    st.success("💾 Sauvegarde effectuée.")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer fichier Excel", type=["xlsx"])
    if up:
        df_new = pd.read_excel(up, engine="openpyxl", converters={"telephone": normalize_tel})
        sauvegarder_donnees(df_new)
        st.sidebar.success("✅ Fichier restauré.")
        st.rerun()

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    ensure_schema(df).to_excel(buf, index=False, engine="openpyxl")
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=buf.getvalue(),
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ==============================  ICS EXPORT  ==============================

def _fmt_date_ics(d: date): return d.strftime("%Y%m%d")
def _dtstamp(): return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def df_to_ics(df: pd.DataFrame):
    core, _ = split_totals(ensure_schema(df))
    lines = [
        "BEGIN:VCALENDAR","VERSION:2.0","CALSCALE:GREGORIAN","METHOD:PUBLISH"
    ]
    for _, row in core.iterrows():
        d1,d2 = row["date_arrivee"], row["date_depart"]
        if not (isinstance(d1,date) and isinstance(d2,date)): continue
        lines += [
            "BEGIN:VEVENT",
            f"UID:{hashlib.sha1(str(row).encode()).hexdigest()}",
            f"DTSTAMP:{_dtstamp()}",
            f"DTSTART;VALUE=DATE:{_fmt_date_ics(d1)}",
            f"DTEND;VALUE=DATE:{_fmt_date_ics(d2)}",
            f"SUMMARY:{row['plateforme']} - {row['nom_client']}",
            "END:VEVENT"
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)

# ==============================  CALENDRIER ==============================

def vue_calendrier(df: pd.DataFrame):
    palette = get_palette()
    st.title("📅 Calendrier")
    df = ensure_schema(df)
    if df.empty: return st.info("Aucune donnée")
    mois = st.selectbox("Mois", list(calendar.month_name)[1:], index=date.today().month-1)
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()), index=0)
    mois_idx = list(calendar.month_name).index(mois)
    jours = [date(int(annee), mois_idx, j+1) for j in range(calendar.monthrange(int(annee), mois_idx)[1])]
    planning = {j: [] for j in jours}
    for _, row in df.iterrows():
        if isinstance(row["date_arrivee"], date) and isinstance(row["date_depart"], date):
            for j in jours:
                if row["date_arrivee"] <= j < row["date_depart"]:
                    planning[j].append((row["plateforme"], row["nom_client"]))
    monthcal = calendar.monthcalendar(int(annee), mois_idx)
    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    table = []
    for semaine in monthcal:
        row = []
        for j in semaine:
            if j==0: row.append("")
            else:
                d = date(int(annee), mois_idx, j)
                items = planning[d]
                txt = str(j) + "".join([f"\n{n}" for _,n in items])
                row.append(txt)
        table.append(row)
    st.table(pd.DataFrame(table, columns=headers))

# ==============================  RAPPORT ==============================

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport")
    df = ensure_schema(df)
    if df.empty: return
    annees = sorted(df["AAAA"].dropna().unique())
    annee = st.selectbox("Année", annees, index=0)
    st.dataframe(df[df["AAAA"]==annee])

# ==============================  MAIN ==============================

def main():
    render_palette_editor_sidebar()
    bouton_restaurer()
    df = charger_donnees()
    page = st.sidebar.radio("Aller à", ["📋 Réservations","📅 Calendrier","📊 Rapport","📤 Export ICS"])
    if page=="📋 Réservations": vue_reservations(df)
    elif page=="📅 Calendrier": vue_calendrier(df)
    elif page=="📊 Rapport": vue_rapport(df)
    elif page=="📤 Export ICS":
        st.download_button("Exporter ICS", data=df_to_ics(df), file_name="reservations.ics", mime="text/calendar")
    bouton_telecharger(df)

def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")
    st.dataframe(ensure_schema(df))

if __name__ == "__main__":
    main()