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
    """Affiche le logo si présent, sinon un titre sobre, sans jamais faire planter l'app."""
    try:
        if LOGO_FILE.exists():
            st.sidebar.image(str(LOGO_FILE), use_column_width=True)
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
    Colonnes attendues (souples) :
      - Date ou Check-in/Check-out (au moins une date)
      - Plateforme (Airbnb/Booking/Direct/etc.)
      - Montant / Prix / Total
      - Statut (Payé / Non payé) ou booléen payé
    """
    # 1) si un data_loader.py existe avec une fonction load_data(), on l’utilise
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
        # fallback ultra simple
        df = pd.read_excel(path)

    # Normalisations douces de colonnes fréquentes
    df = df.copy()

    # Chercher une colonne date principale
    date_cols = [c for c in df.columns if str(c).strip().lower() in {"date", "check-in", "checkin", "arrivee", "arrivée"}]
    if not date_cols:
        # tente de détecter la première colonne de type date
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
        # s’il n’y a aucune date, on met des champs neutres pour éviter le crash des filtres
        df["Année"] = None
        df["Mois"] = None
        df["Date"] = pd.NaT

    # Colonne Plateforme standard
    if "Plateforme" not in df.columns:
        # essaie de trouver un nom proche
        for c in df.columns:
            if str(c).strip().lower() in {"plateforme", "plateform", "platform", "site"}:
                df.rename(columns={c: "Plateforme"}, inplace=True)
                break
        if "Plateforme" not in df.columns:
            df["Plateforme"] = "Inconnue"

    # Colonne Statut Payé / Non payé
    statut_col = None
    candidats = ["Statut", "StatutPaiement", "Payé", "Paye", "Paid"]
    for c in df.columns:
        if str(c).strip() in candidats or str(c).strip().lower() in [x.lower() for x in candidats]:
            statut_col = c
            break
    if statut_col is not None and statut_col != "StatutPaiement":
        df.rename(columns={statut_col: "StatutPaiement"}, inplace=True)
    if "StatutPaiement" not in df.columns:
        # si on a une colonne booléenne paid
        for c in df.columns:
            if df[c].dropna().isin([True, False, 0, 1, "Oui", "Non"]).all():
                # heuristique : on fabrique le statut
                val = df[c].map(
                    lambda x: "Payé" if str(x).lower() in {"true", "1", "oui", "payé", "paye", "paid"} else "Non payé"
                )
                df["StatutPaiement"] = val
                break
        if "StatutPaiement" not in df.columns:
            df["StatutPaiement"] = "Non renseigné"

    # Colonne Montant
    montant_col = None
    for c in df.columns:
        cl = str(c).strip().lower()
        if cl in {"montant", "prix", "total", "revenu", "ca"}:
            montant_col = c
            break
    if montant_col is None:
        # Pas de montant → crée une colonne à 0 pour éviter les plantages d'agrégations
        df["Montant"] = 0.0
    elif montant_col != "Montant":
        df.rename(columns={montant_col: "Montant"}, inplace=True)

    return df

# =====================================================================
# App
# =====================================================================
def main():
    st.set_page_config(page_title="Réservations", layout="wide")
    render_sidebar_header()

    st.title("Tableau de bord — Réservations")

    # Vérif présence fichier
    if not DATA_FILE.exists():
        st.error(f"Fichier introuvable : `{DATA_FILE.name}` dans le même dossier que `app.py`.")
        st.info("Placez votre fichier Excel dans le repo (même niveau que app.py) et relancez.")
        return

    df = load_reservations(DATA_FILE)

    # =======================
    # Filtres latéraux
    # =======================
    st.sidebar.subheader("Filtres")

    # Année
    annees = sorted([a for a in df["Année"].dropna().unique().tolist() if a is not None])
    annee_sel = st.sidebar.multiselect("Année", annees, default=annees)

    # Mois (liste déroulante)
    mois_uniques = sorted([int(m) for m in df["Mois"].dropna().unique().tolist() if m == m])
    # par défaut : tous les mois (1..12) présents
    mois_labels = {m: month_name_fr(int(m)).capitalize() for m in mois_uniques}
    mois_def = mois_uniques
    mois_sel_labels = st.sidebar.multiselect(
        "Mois",
        options=[mois_labels[m] for m in mois_uniques],
        default=[mois_labels[m] for m in mois_def]
    )
    # remap labels -> numéros
    mois_sel = [m for m in mois_uniques if mois_labels[m] in mois_sel_labels]

    # Plateforme
    plateformes = sorted(df["Plateforme"].astype(str).fillna("Inconnue").unique().tolist())
    platform_sel = st.sidebar.multiselect("Plateforme", plateformes, default=plateformes)

    # Statut paiement
    statuts = sorted(df["StatutPaiement"].astype(str).fillna("Non renseigné").unique().tolist())
    # si on veut seulement Payé / Non payé comme vous l’aviez demandé
    # on force l’ordre si présent
    ordre_statuts = [s for s in ["Payé", "Non payé"] if s in statuts] + [s for s in statuts if s not in {"Payé", "Non payé"}]
    statut_sel = st.sidebar.multiselect("Statut", ordre_statuts, default=ordre_statuts)

    # =======================
    # Application des filtres
    # =======================
    dff = df.copy()
    if annee_sel:
        dff = dff[dff["Année"].isin(annee_sel)]
    if mois_sel:
        dff = dff[dff["Mois"].isin(mois_sel)]
    if platform_sel:
        dff = dff[dff["Plateforme"].astype(str).isin(platform_sel)]
    if statut_sel:
        dff = dff[dff["StatutPaiement"].astype(str).isin(statut_sel)]

    # =======================
    # KPIs simples
    # =======================
    total_resa = len(dff)
    total_revenu = pd.to_numeric(dff.get("Montant", pd.Series(dtype=float)), errors="coerce").fillna(0).sum()
    nb_payees = (dff["StatutPaiement"].astype(str) == "Payé").sum() if "StatutPaiement" in dff.columns else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("Réservations", f"{total_resa:,}".replace(",", " "))
    c2.metric("Revenu total", f"{total_revenu:,.2f} €".replace(",", " "))
    c3.metric("Réservations payées", f"{nb_payees:,}".replace(",", " "))

    st.divider()

    # =======================
    # Tableau détaillé
    # =======================
    with st.expander("Voir le tableau filtré", expanded=True):
        st.dataframe(
            dff.sort_values(by=["Date", "Plateforme"], ascending=[False, True]),
            use_container_width=True,
            hide_index=True
        )

    # =======================
    # Vue "calendrier" simple (par jour)
    # =======================
    # On agrège par date pour une vue rapide “agenda”
    if "Date" in dff.columns and dff["Date"].notna().any():
        agenda = (
            dff.groupby(dff["Date"].dt.date)
            .agg(
                nb=("Date", "count"),
                revenu=("Montant", lambda s: pd.to_numeric(s, errors="coerce").fillna(0).sum())
            )
            .reset_index()
            .rename(columns={"Date": "Jour"})
            .sort_values("Jour")
        )
        st.subheader("Calendrier (agrégé par jour)")
        st.dataframe(agenda, use_container_width=True, hide_index=True)
    else:
        st.info("Aucune colonne de date exploitable pour afficher un calendrier agrégé.")

    st.caption("💡 Astuce : utilisez les filtres à gauche (Année / Mois / Plateforme / Statut).")

# =====================================================================
# Lancement
# =====================================================================
if __name__ == "__main__":
    main()