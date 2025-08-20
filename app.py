# app.py
from __future__ import annotations

import os
from pathlib import Path
from datetime import datetime
import calendar

import streamlit as st
import pandas as pd
import numpy as np

# =====================================================================
# Configuration chemins (robuste, indépendants du répertoire courant)
# =====================================================================
APP_DIR = Path(__file__).parent.resolve()
DATA_FILE = APP_DIR / "reservations.xlsx"  # <- attention au nom exact dans le repo
LOGO_FILE = APP_DIR / "logo.png"

# =====================================================================
# UI helpers
# =====================================================================
def render_sidebar_header():
    """Affiche le logo si présent (réduit en icône), sinon un titre sobre."""
    try:
        if LOGO_FILE.exists():
            st.sidebar.image(str(LOGO_FILE), width=100)  # <-- Logo réduit
        else:
            st.sidebar.markdown("### Réservations")
    except Exception:
        st.sidebar.markdown("### Réservations")

def month_name_fr(n: int) -> str:
    """Nom de mois en français pour affichage (1-12)."""
    noms = [
        "janvier", "février", "mars", "avril", "mai", "juin",
        "juillet", "août", "septembre", "octobre", "novembre", "décembre"
    ]
    if 1 <= n <= 12:
        return noms[n - 1]
    return str(n)

# =====================================================================
# Chargement des données
# =====================================================================
@st.cache_data(show_spinner=True)
def load_reservations(path: Path) -> pd.DataFrame:
    """
    Charge le fichier Excel des réservations.
    Essaie d'abord via un éventuel data_loader.py si présent, sinon read_excel direct.
    """
    try:
        import importlib.util
        dl_path = APP_DIR / "data_loader.py"
        if dl_path.exists():
            spec = importlib.util.spec_from_file_location("data_loader", str(dl_path))
            mod = importlib.util.module_from_spec(spec)
            assert spec.loader is not None
            spec.loader.exec_module(mod)  # type: ignore
            if hasattr(mod, "load_data"):
                df = mod.load_data(str(path))
            else:
                df = pd.read_excel(path)
        else:
            df = pd.read_excel(path)
    except Exception:
        df = pd.read_excel(path)

    # Normalisations
    df = df.copy()

    # --- Dates ---
    date_cols = [c for c in df.columns if str(c).strip().lower() in {"date", "check-in", "checkin", "arrivee", "arrivée"}]
    if not date_cols:
        for c in df.columns:
            if np.issubdtype(df[c].dtype, np.datetime64):
                date_cols = [c]
                break

    if date_cols:
        dcol = date_cols[0]
        df[dcol] = pd.to_datetime(df[dcol], errors="coerce")
        df = df.dropna(subset=[dcol])
        df["Année"] = df[dcol].dt.year
        df["Mois"] = df[dcol].dt.month
        df.rename(columns={dcol: "Date"}, inplace=True)
    else:
        df["Année"] = None
        df["Mois"] = None
        df["Date"] = pd.NaT

    # --- Plateforme ---
    if "Plateforme" not in df.columns:
        for c in df.columns:
            if str(c).strip().lower() in {"plateforme", "plateform", "platform", "site"}:
                df.rename(columns={c: "Plateforme"}, inplace=True)
                break
        if "Plateforme" not in df.columns:
            df["Plateforme"] = "Inconnue"

    # --- Statut paiement ---
    statut_col = None
    candidats = ["Statut", "StatutPaiement", "Payé", "Paye", "Paid"]
    for c in df.columns:
        if str(c).strip() in candidats or str(c).strip().lower() in [x.lower() for x in candidats]:
            statut_col = c
            break
    if statut_col is not None and statut_col != "StatutPaiement":
        df.rename(columns={statut_col: "StatutPaiement"}, inplace=True)
    if "StatutPaiement" not in df.columns:
        df["StatutPaiement"] = "Non renseigné"

    # --- Montant ---
    montant_col = None
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl in {"montant", "prix", "total", "revenu", "ca"}:
            montant_col = c
            break
    if montant_col is None:
        df["Montant"] = 0.0
    elif montant_col != "Montant":
        df.rename(columns={montant_col: "Montant"}, inplace=True)

    return df

# =====================================================================
# Filtres & affichage
# =====================================================================
def build_sidebar_filters(df: pd.DataFrame) -> dict:
    render_sidebar_header()
    st.sidebar.markdown("### Filtres")

    # Année
    annees = sorted([int(a) for a in df["Année"].dropna().unique()], reverse=True)
    annee = st.sidebar.selectbox("Année", options=["Toutes"] + annees, index=0)

    # Mois (liste déroulante)
    mois_uniques = sorted([int(m) for m in df["Mois"].dropna().unique()])
    mois_labels = ["Tous"] + [f"{m:02d} - {month_name_fr(m).capitalize()}" for m in range(1, 12 + 1) if m in mois_uniques]
    mois_map = {"Tous": None}
    for m in range(1, 13):
        if m in mois_uniques:
            mois_map[f"{m:02d} - {month_name_fr(m).capitalize()}"] = m
    mois_label = st.sidebar.selectbox("Mois", options=mois_labels, index=0)
    mois = mois_map.get(mois_label, None)

    # Plateforme
    plateformes = sorted(df["Plateforme"].fillna("Inconnue").astype(str).unique())
    plateformes_sel = st.sidebar.multiselect("Plateforme(s)", options=plateformes, default=plateformes)

    # Normalisation payé / non payé
    paid_true_vals = {"payé", "paye", "paid", "ok", "oui", "true", "vrai", "yes"}
    def to_paid(v):
        if pd.isna(v):
            return False
        s = str(v).strip().lower()
        return s in paid_true_vals
    if "PayéBool" not in df.columns:
        df["PayéBool"] = df["StatutPaiement"].map(to_paid)

    statut_map = {"Tous": None, "Payé": True, "Non payé": False}
    statut_label = st.sidebar.selectbox("Statut", options=list(statut_map.keys()), index=0)
    statut_val = statut_map[statut_label]

    return {
        "annee": annee,
        "mois": mois,
        "plateformes": plateformes_sel,
        "statut": statut_val,
    }

def apply_filters(df: pd.DataFrame, flt: dict) -> pd.DataFrame:
    out = df.copy()

    if flt["annee"] != "Toutes":
        out = out[out["Année"] == flt["annee"]]

    if flt["mois"] is not None:
        out = out[out["Mois"] == flt["mois"]]

    if flt["plateformes"]:
        out = out[out["Plateforme"].isin(flt["plateformes"])]

    if flt["statut"] is not None:
        out = out[out["PayéBool"] == flt["statut"]]

    return out

def render_reservations_table(df: pd.DataFrame):
    if df.empty:
        st.info("Aucune réservation pour les filtres sélectionnés.")
        return
    # Colonnes plus lisibles si présentes
    cols_order = [c for c in ["Date", "Année", "Mois", "Plateforme", "StatutPaiement", "Montant"] if c in df.columns]
    rest = [c for c in df.columns if c not in cols_order and not c.endswith("Bool")]
    st.dataframe(df[cols_order + rest], use_container_width=True)

def render_synthese(df: pd.DataFrame):
    col1, col2, col3 = st.columns(3)
    total_res = int(len(df))
    total_montant = float(df.get("Montant", pd.Series(dtype=float)).fillna(0).sum())
    taux_paye = float((df.get("PayéBool", pd.Series(dtype=bool)) == True).mean()) if not df.empty else 0.0

    col1.metric("Réservations", f"{total_res}")
    col2.metric("Montant total", f"{total_montant:,.2f} €".replace(",", " ").replace(".", ","))
    col3.metric("Taux payé", f"{taux_paye*100:.1f} %")

    # Petits tableaux pivot rapides
    with st.expander("Détail par plateforme"):
        if not df.empty:
            ptf = (
                df.groupby("Plateforme", dropna=False)
                  .agg(Reservations=("Plateforme", "size"),
                       Montant=("Montant", "sum"),
                       Payé=("PayéBool", "mean"))
                  .reset_index()
            )
            ptf["Taux payé"] = (ptf["Payé"] * 100).round(1).astype(str) + " %"
            ptf = ptf.drop(columns=["Payé"])
            st.dataframe(ptf, use_container_width=True)
        else:
            st.info("Aucune donnée.")

def render_calendar(df: pd.DataFrame):
    """
    Affiche un mini calendrier du mois filtré (si un mois a été choisi) avec le nombre de réservations par jour.
    Si aucun mois précis n'est sélectionné, on affiche un message.
    """
    if "Année" not in df.columns or "Mois" not in df.columns or "Date" not in df.columns or df.empty:
        st.info("Sélectionnez une année et un mois pour afficher le calendrier.")
        return

    # Déterminer un (année, mois) à partir des données filtrées
    val_annee = df["Année"].dropna().unique()
    val_mois = df["Mois"].dropna().unique()
    if len(val_annee) != 1 or len(val_mois) != 1:
        st.info("Le calendrier s'affiche lorsque **un seul** mois est filtré.")
        return

    annee = int(val_annee[0])
    mois = int(val_mois[0])

    st.subheader(f"Calendrier — {month_name_fr(mois).capitalize()} {annee}")

    # Compte par jour
    counts = df["Date"].dt.day.value_counts().to_dict()

    cal = calendar.Calendar(firstweekday=0)  # lundi=0? En Python, lundi=0 si setfirstweekday(0). Ici 0 = lundi.
    calendar.setfirstweekday(calendar.MONDAY)
    weeks = calendar.monthcalendar(annee, mois)

    # Rendu simple en texte (robuste dans Streamlit)
    for w in weeks:
        cols = st.columns(7)
        for i, d in enumerate(w):
            if d == 0:
                cols[i].markdown("&nbsp;")
            else:
                n = counts.get(d, 0)
                if n > 0:
                    cols[i].markdown(f"**{d}**  \n{n} rés.")
                else:
                    cols[i].markdown(f"{d}")

# =====================================================================
# App
# =====================================================================
def main():
    st.set_page_config(page_title="Réservations", page_icon="📒", layout="wide")

    # Vérif fichiers
    if not DATA_FILE.exists():
        st.error(f"Fichier de données introuvable : `{DATA_FILE.name}`\n\n"
                 "Vérifie le nom exact dans le dépôt (sans accent) et qu'il est bien à la racine.")
        return

    # Chargement
    df = load_reservations(DATA_FILE)

    # Filtres
    flt = build_sidebar_filters(df)
    df_f = apply_filters(df, flt)

    # Onglets
    tab1, tab2, tab3 = st.tabs(["📋 Réservations", "📆 Calendrier", "📊 Synthèse"])

    with tab1:
        render_reservations_table(df_f)

    with tab2:
        render_calendar(df_f)

    with tab3:
        render_synthese(df_f)

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Fichier : `{DATA_FILE.name}`")
    if LOGO_FILE.exists():
        st.sidebar.caption("Logo chargé ✔️")
    else:
        st.sidebar.caption("Logo non trouvé (facultatif)")

if __name__ == "__main__":
    main()