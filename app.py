# app.py — Villa Tobias (COMPLET avec plateformes, ajout/modification/suppression, calendrier coloré, rapport, SMS)

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
FICHIER_PLATEFORMES = "plateformes.xlsx"

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
    st.session_state.palette = {str(k): str(v) for k, v in palette.items() if k and v}

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
    if s.endswith(".0"):
        s = s[:-2]
    return s

# ==============================  SCHEMA ==============================
BASE_COLS = [
    "paye", "nom_client", "sms_envoye", "plateforme", "telephone",
    "date_arrivee", "date_depart", "nuitees",
    "prix_brut", "commissions", "frais_cb", "prix_net",
    "menage", "taxes_sejour", "base", "charges", "%", "AAAA", "MM"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan
    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")
    for c in ["paye","sms_envoye"]:
        df[c] = df[c].fillna(False).astype(bool)
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)
    return df

# ==============================  EXCEL I/O ==============================
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
        st.error(f"Erreur lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            df.to_excel(w, index=False)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec sauvegarde Excel : {e}")

# ==============================  VUES UI ==============================

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    form = st.form("ajout_resa")
    nom = form.text_input("Nom du client")
    pf = form.selectbox("Plateforme", sorted(get_palette().keys()))
    tel = form.text_input("Téléphone")
    d1 = form.date_input("Date arrivée")
    d2 = form.date_input("Date départ")
    brut = form.number_input("Prix brut (€)", min_value=0.0, step=10.0)
    comm = form.number_input("Commissions (€)", min_value=0.0, step=1.0)
    cb   = form.number_input("Frais CB (€)", min_value=0.0, step=1.0)
    menage = form.number_input("Ménage (€)", min_value=0.0, step=1.0)
    taxes  = form.number_input("Taxes séjour (€)", min_value=0.0, step=1.0)

    submitted = form.form_submit_button("💾 Ajouter")
    if submitted:
        new_row = {
            "paye": False, "sms_envoye": False,
            "nom_client": nom, "plateforme": pf, "telephone": tel,
            "date_arrivee": d1, "date_depart": d2,
            "prix_brut": brut, "commissions": comm, "frais_cb": cb,
            "menage": menage, "taxes_sejour": taxes
        }
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        sauvegarder_donnees(df)
        st.success("✅ Réservation ajoutée.")
        st.rerun()


def vue_modifier_supprimer(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)

    if core.empty:
        st.info("Aucune réservation à modifier.")
        return

    options = [f"{i} - {row['nom_client']} ({row['date_arrivee']} → {row['date_depart']})"
               for i, row in core.iterrows()]
    choice = st.selectbox("Choisissez une réservation :", options)

    if not choice:
        return

    idx = int(choice.split(" - ")[0])
    row = core.iloc[idx]

    with st.form("modif_resa"):
        nom = st.text_input("Nom du client", row["nom_client"])
        pf  = st.selectbox("Plateforme", sorted(get_palette().keys()), index=list(get_palette().keys()).index(row["plateforme"]) if row["plateforme"] in get_palette() else 0)
        tel = st.text_input("Téléphone", row["telephone"])
        d1  = st.date_input("Date arrivée", row["date_arrivee"])
        d2  = st.date_input("Date départ", row["date_depart"])
        brut= st.number_input("Prix brut (€)", value=float(row["prix_brut"]))
        comm= st.number_input("Commissions (€)", value=float(row["commissions"]))
        cb  = st.number_input("Frais CB (€)", value=float(row["frais_cb"]))
        men = st.number_input("Ménage (€)", value=float(row["menage"]))
        tax = st.number_input("Taxes séjour (€)", value=float(row["taxes_sejour"]))

        c1, c2 = st.columns(2)
        modif = c1.form_submit_button("💾 Sauvegarder")
        suppr = c2.form_submit_button("🗑 Supprimer")

        if modif:
            df.loc[row.name, ["nom_client","plateforme","telephone","date_arrivee","date_depart","prix_brut","commissions","frais_cb","menage","taxes_sejour"]] = [nom, pf, tel, d1, d2, brut, comm, cb, men, tax]
            sauvegarder_donnees(df)
            st.success("✅ Réservation modifiée.")
            st.rerun()
        if suppr:
            df = df.drop(index=row.name)
            sauvegarder_donnees(df)
            st.success("✅ Réservation supprimée.")
            st.rerun()


def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS")
    df = ensure_schema(df)
    core, _ = split_totals(df)
    core = sort_core(core)

    if core.empty:
        st.info("Aucune réservation disponible.")
        return

    idx = st.selectbox("Choisir une réservation", core.index,
                       format_func=lambda i: f"{core.at[i,'nom_client']} ({core.at[i,'date_arrivee']})")
    row = core.loc[idx]

    st.subheader("Message arrivée")
    st.code(sms_message_arrivee(row))
    st.subheader("Message départ")
    st.code(sms_message_depart(row))


def vue_export_ics(df: pd.DataFrame):
    st.title("📤 Export ICS")
    df = ensure_schema(df)
    ics = df_to_ics(df)
    st.download_button("📥 Télécharger ICS", data=ics, file_name="reservations.ics", mime="text/calendar")


# ==============================  MAIN APP ==============================

def main():
    render_palette_editor_sidebar()
    render_cache_section_sidebar()
    bouton_restaurer()

    df = charger_donnees()

    menu = st.sidebar.radio("🧭 Navigation", [
        "📋 Réservations", "➕ Ajouter", "✏️ Modifier / Supprimer",
        "📅 Calendrier", "📊 Rapport", "👥 Liste clients",
        "📤 Export ICS", "✉️ SMS"
    ])

    if menu == "📋 Réservations":
        vue_reservations(df)
    elif menu == "➕ Ajouter":
        vue_ajouter(df)
    elif menu == "✏️ Modifier / Supprimer":
        vue_modifier_supprimer(df)
    elif menu == "📅 Calendrier":
        vue_calendrier(df)
    elif menu == "📊 Rapport":
        vue_rapport(df)
    elif menu == "👥 Liste clients":
        st.dataframe(df[["nom_client","telephone","plateforme"]], use_container_width=True)
    elif menu == "📤 Export ICS":
        vue_export_ics(df)
    elif menu == "✉️ SMS":
        vue_sms(df)

    bouton_telecharger(df)


if __name__ == "__main__":
    main()