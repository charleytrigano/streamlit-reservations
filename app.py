# app.py — Villa Tobias (COMPLET, allégé, restauration simplifiée)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, datetime, timezone
from io import BytesIO
import hashlib
import os
import colorsys

FICHIER = "reservations.xlsx"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def get_palette() -> dict:
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = {str(k): str(v) for k, v in palette.items() if k and v}

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{color};border-radius:3px;margin-right:6px;"></span>{name}'

def render_palette_editor_sidebar():
    palette = get_palette()
    st.sidebar.markdown("## 🎨 Plateformes")
    with st.sidebar.expander("➕ Ajouter / modifier des plateformes", expanded=False):
        new_name = st.text_input("Nom de la plateforme", key="pal_new_name")
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
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    return s[:-2] if s.endswith(".0") else s

# ==============================  SCHEMA & CALCULS  ==============================
BASE_COLS = [
    "paye","nom_client","sms_envoye","plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%",
    "AAAA","MM","ical_uid"
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
    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if isinstance(d1, date) and isinstance(d2, date) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)
    return df

def split_totals(df: pd.DataFrame):
    mask = df.apply(lambda r: str(r.get("nom_client","")).lower()=="total", axis=1)
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    return df.sort_values(by=["date_arrivee","nom_client"], na_position="last").reset_index(drop=True)

# ==============================  EXCEL I/O  ==============================
@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path, engine="openpyxl", converters={"telephone": normalize_tel})

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        return ensure_schema(_read_excel_cached(FICHIER, mtime))
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    out = pd.concat([sort_core(core), totals], ignore_index=True)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name="Sheet1")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer un fichier Excel", type=["xlsx"])
    if up is not None:
        try:
            df_new = pd.read_excel(up, engine="openpyxl", converters={"telephone": normalize_tel})
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")


# ==============================  ICS EXPORT  ==============================
def _ics_escape(text: str) -> str:
    return str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n") if text else ""

def _fmt_date_ics(d: date) -> str:
    return d.strftime("%Y%m%d")

def _dtstamp_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def df_to_ics(df: pd.DataFrame, cal_name: str = "Villa Tobias – Réservations") -> str:
    df = ensure_schema(df)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"X-WR-CALNAME:{_ics_escape(cal_name)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for _, row in df.iterrows():
        d1, d2 = row["date_arrivee"], row["date_depart"]
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        summary = f"{row['plateforme']} - {row['nom_client']}"
        desc = f"Tel: {row['telephone']}\\nArrivée: {d1}\\nDépart: {d2}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{hashlib.sha1(summary.encode()).hexdigest()}@vt",
            f"DTSTAMP:{_dtstamp_utc_now()}",
            f"DTSTART;VALUE=DATE:{_fmt_date_ics(d1)}",
            f"DTEND;VALUE=DATE:{_fmt_date_ics(d2)}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

# ==============================  SMS ==============================
def sms_message_arrivee(row: pd.Series) -> str:
    d1, d2 = row["date_arrivee"], row["date_depart"]
    nuitees = row.get("nuitees", 0)
    return (
        f"📢 Villa Tobias\n\n"
        f"Plateforme: {row['plateforme']}\nClient: {row['nom_client']}\n"
        f"Arrivée: {d1} - Départ: {d2} ({nuitees} nuits)\n"
        f"Téléphone: {row['telephone']}"
    )

# ==============================  UI HELPERS ==============================
def kpi_chips(df: pd.DataFrame):
    core, _ = split_totals(df)
    b, n, base, ch = core["prix_brut"].sum(), core["prix_net"].sum(), core["base"].sum(), (core["commissions"].sum()+core["frais_cb"].sum())
    nuits = core["nuitees"].sum()
    pm_nuit = (b/nuits) if nuits else 0
    pct = (ch/b*100) if b else 0
    st.markdown(
        f"**Total Brut:** {b:.2f} € | **Net:** {n:.2f} € | **Base:** {base:.2f} € | "
        f"**Charges:** {ch:.2f} € | **Nuitées:** {int(nuits)} | **Prix/nuit:** {pm_nuit:.2f} € | **Com. moy:** {pct:.2f}%"
    )

# ==============================  VUES ==============================
def vue_reservations(df: pd.DataFrame):
    st.header("📋 Réservations")
    filtre = st.radio("Filtrer payé", ["Tous","Payé","Non payé"])
    if filtre=="Payé":
        df = df[df["paye"]==True]
    elif filtre=="Non payé":
        df = df[df["paye"]==False]
    kpi_chips(df)
    st.dataframe(df, use_container_width=True)

def vue_calendrier(df: pd.DataFrame):
    st.header("📅 Calendrier")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return
    mois = st.selectbox("Mois", list(calendar.month_name)[1:], index=date.today().month-1)
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()), index=0)
    st.write(f"📌 Affichage {mois} {annee}")
    # Simplification: on affiche juste un tableau
    st.dataframe(df[["nom_client","plateforme","date_arrivee","date_depart"]])

def vue_rapport(df: pd.DataFrame):
    st.header("📊 Rapport")
    df = ensure_schema(df)
    if df.empty: return
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()))
    pf = st.selectbox("Plateforme", ["Toutes"]+sorted(df["plateforme"].dropna().unique()))
    data = df[df["AAAA"]==annee]
    if pf!="Toutes": data=data[data["plateforme"]==pf]
    kpi_chips(data)
    st.dataframe(data, use_container_width=True)

# ==============================  MAIN ==============================
def main():
    render_palette_editor_sidebar()
    bouton_restaurer()
    df = charger_donnees()
    menu = st.sidebar.radio("Navigation", ["📋 Réservations","📅 Calendrier","📊 Rapport","📤 Export ICS"])
    if menu=="📋 Réservations": vue_reservations(df)
    elif menu=="📅 Calendrier": vue_calendrier(df)
    elif menu=="📊 Rapport": vue_rapport(df)
    elif menu=="📤 Export ICS":
        st.download_button("Télécharger ICS", data=df_to_ics(df), file_name="reservations.ics", mime="text/calendar")

if __name__=="__main__":
    main()