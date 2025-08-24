# app.py — Villa Tobias (COMPLET)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
from urllib.parse import quote
import colorsys

FICHIER = "reservations.xlsx"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  SESSION KEYS (anti-boucle)  ==============================
if "uploader_key_restore" not in st.session_state:
    st.session_state.uploader_key_restore = 0
if "did_clear_cache" not in st.session_state:
    st.session_state.did_clear_cache = False

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def get_palette() -> dict:
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    pal = {}
    for k, v in st.session_state.palette.items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4, 7):
            pal[k] = v
    st.session_state.palette = pal
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = {str(k): str(v) for k, v in palette.items() if k and v}

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

def render_palette_editor_sidebar():
    """Éditeur palette en sidebar (simple, non bloquant)."""
    palette = get_palette()
    st.sidebar.markdown("## 🎨 Plateformes")
    with st.sidebar.expander("➕ Ajouter / modifier des plateformes", expanded=False):
        c1, c2 = st.columns([2,1])
        with c1:
            new_name = st.text_input("Nom de la plateforme", key="pal_new_name", placeholder="Ex: Expedia")
        with c2:
            new_color = st.color_picker("Couleur", key="pal_new_color", value="#9b59b6")
        colA, colB = st.columns(2)
        if colA.button("Ajouter / Mettre à jour"):
            name = (new_name or "").strip()
            if not name:
                st.warning("Entrez un nom de plateforme.")
            else:
                palette[name] = new_color
                save_palette(palette)
                st.success(f"✅ Plateforme « {name} » enregistrée.")
        if colB.button("Réinitialiser la palette"):
            save_palette(DEFAULT_PALETTE.copy())
            st.success("✅ Palette réinitialisée.")
    if palette:
        st.sidebar.markdown("**Plateformes existantes :**")
        for pf in sorted(palette.keys()):
            cols = st.sidebar.columns([1, 3, 1])
            with cols[0]:
                st.markdown(
                    f'<span style="display:inline-block;width:1.1em;height:1.1em;background:{palette[pf]};border-radius:3px;"></span>',
                    unsafe_allow_html=True,
                )
            with cols[1]:
                st.markdown(f"{pf}")
            with cols[2]:
                if st.button("🗑", key=f"del_{pf}"):
                    pal = get_palette()
                    if pf in pal:
                        del pal[pf]
                        save_palette(pal)
                        st.success(f"Plateforme « {pf} » supprimée.")
                        st.experimental_rerun()

# ==============================  MAINTENANCE / CACHE  ==============================
def render_cache_section_sidebar():
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.session_state.did_clear_cache = True
        st.sidebar.success("Cache vidé.")
    if st.session_state.did_clear_cache:
        st.sidebar.caption("✅ Le cache a été vidé sur ce run.")

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
    s = str(x).strip()
    s = s.replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

# ==============================  SCHEMA & CALCULS  ==============================
BASE_COLS = [
    "paye", "nom_client", "sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%", "AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan
    if "paye" in df.columns:
        df["paye"] = df["paye"].fillna(False).astype(bool)
    if "sms_envoye" in df.columns:
        df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")
    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"]   = df["ical_uid"].fillna("")
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)
    ordered_cols = [c for c in BASE_COLS if c in df.columns]
    rest_cols = [c for c in df.columns if c not in ordered_cols]
    return df[ordered_cols + rest_cols]


def is_total_row(row: pd.Series) -> bool:
    name_is_total = str(row.get("nom_client","")).strip().lower() == "total"
    pf_is_total   = str(row.get("plateforme","")).strip().lower() == "total"
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    no_dates = not isinstance(d1, date) and not isinstance(d2, date)
    has_money = any(pd.notna(row.get(c)) and float(row.get(c) or 0) != 0
                    for c in ["prix_brut","prix_net","base","charges"])
    return name_is_total or pf_is_total or (no_dates and has_money)

def split_totals(df: pd.DataFrame):
    if df is None or df.empty:
        return df, df
    mask = df.apply(is_total_row, axis=1)
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    by = [c for c in ["date_arrivee","nom_client"] if c in df.columns]
    return df.sort_values(by=by, na_position="last").reset_index(drop=True)

# ==============================  EXCEL I/O  ==============================
@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path, engine="openpyxl", converters={"telephone": normalize_tel})

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime)
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name="Sheet1")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

# ==============================  CALENDRIER  ==============================
def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier")
    palette = get_palette()
    if df.empty:
        st.info("Aucune réservation à afficher.")
        return
    today = date.today()
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()), index=0)
    mois = st.selectbox("Mois", list(range(1,13)), index=today.month-1)
    cal = calendar.Calendar()
    jours = list(cal.itermonthdates(int(annee), int(mois)))
    rows = []
    for week in range(0, len(jours), 7):
        row = []
        for d in jours[week:week+7]:
            cell = ""
            bg = None
            if d.month == mois:
                resa = df[(df["date_arrivee"] <= d) & (df["date_depart"] > d)]
                if not resa.empty:
                    clients = []
                    for _, r in resa.iterrows():
                        color = palette.get(r["plateforme"], "#555555")
                        clients.append(f"<div style='background:{color};color:white;padding:2px;border-radius:3px;'>{r['nom_client']}</div>")
                    cell = "<br/>".join(clients)
            row.append(f"<td style='vertical-align:top;width:14%;height:80px;border:1px solid #666;padding:2px;'>{d.day}<br/>{cell}</td>")
        rows.append("<tr>" + "".join(row) + "</tr>")
    html = f"""
    <table style='border-collapse:collapse;width:100%;color:white;'>
        <tr>{''.join([f'<th>{j}</th>' for j in ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']])}</tr>
        {''.join(rows)}
    </table>
    """
    st.markdown(html, unsafe_allow_html=True)

# ==============================  RAPPORT  ==============================
def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée.")
        return
    kpi_chips(df)
    st.dataframe(df, use_container_width=True)

# ==============================  CLIENTS ==============================
def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste clients")
    if df.empty:
        st.info("Aucune réservation.")
        return
    st.dataframe(df[["nom_client","telephone","plateforme"]].drop_duplicates(), use_container_width=True)

# ==============================  SMS ==============================
def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS")
    if df.empty:
        st.info("Aucune réservation.")
        return
    for _, r in df.iterrows():
        st.text_area(f"SMS pour {r['nom_client']}", sms_message_arrivee(r), height=150)

# ==============================  MAIN ==============================
def main():
    render_palette_editor_sidebar()
    render_cache_section_sidebar()
    st.sidebar.title("🧭 Navigation")
    choix = st.sidebar.radio("Aller à", [
        "📋 Réservations",
        "➕ Ajouter",
        "✏️ Modifier / Supprimer",
        "📅 Calendrier",
        "📊 Rapport",
        "👥 Liste clients",
        "✉️ SMS",
    ])
    df = charger_donnees()
    if choix == "📋 Réservations":
        vue_reservations(df)
    elif choix == "➕ Ajouter":
        vue_ajouter(df)
    elif choix == "✏️ Modifier / Supprimer":
        vue_modifier(df)
    elif choix == "📅 Calendrier":
        vue_calendrier(df)
    elif choix == "📊 Rapport":
        vue_rapport(df)
    elif choix == "👥 Liste clients":
        vue_clients(df)
    elif choix == "✉️ SMS":
        vue_sms(df)

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        st.error("Une erreur est survenue dans l’application :")
        st.exception(e)