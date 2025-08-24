# reservations.py — onglet Réservations (lecture + KPI + recherche simple)

import streamlit as st
import pandas as pd
from utils import (
    charger_donnees, ensure_schema, sort_core, format_date_str,
    kpi_chips
)

def _search_box(df: pd.DataFrame) -> pd.DataFrame:
    q = st.text_input("🔎 Recherche (nom, plateforme, téléphone…)", "")
    if not q:
        return df
    ql = q.strip().lower()
    def _match(v):
        s = "" if pd.isna(v) else str(v)
        return ql in s.lower()
    mask = (
        df["nom_client"].apply(_match) |
        df["plateforme"].apply(_match) |
        df["telephone"].apply(_match)
    )
    return df[mask].copy()

def vue_reservations():
    st.title("📋 Réservations")
    df = ensure_schema(charger_donnees())
    if df.empty:
        st.info("Aucune réservation.")
        return

    with st.expander("🎛️ Options", expanded=True):
        show_kpi = st.checkbox("Afficher les KPI", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)

    if enable_search:
        df = _search_box(df)

    df = sort_core(df)

    if show_kpi:
        kpi_chips(df)

    show = df.copy()
    for c in ["date_arrivee","date_depart"]:
        show[c] = show[c].apply(format_date_str)

    cols = [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net",
        "menage","taxes_sejour","base","charges","%","AAAA","MM"
    ]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)
