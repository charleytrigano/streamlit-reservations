# reservations_view.py — Réservations : liste + ajout + modifier/supprimer

import streamlit as st
import pandas as pd
from datetime import date, timedelta

from io_utils import (
    ensure_schema, split_totals, sort_core, format_date_str, normalize_tel,
    sauvegarder_donnees, charger_donnees, charger_plateformes
)

def _kpi_chips(df: pd.DataFrame):
    core, _ = split_totals(df)
    if core.empty:
        return
    b = core["prix_brut"].sum()
    total_comm = core["commissions"].sum()
    total_cb   = core["frais_cb"].sum()
    ch = total_comm + total_cb
    n = core["prix_net"].sum()
    base = core["base"].sum()
    nuits = core["nuitees"].sum()
    pct = (ch / b * 100) if b else 0
    pm_nuit = (b / nuits) if nuits else 0

    html = f"""
    <style>
    .chips-wrap {{ display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 10px 0; }}
    .chip {{ padding:8px 10px; border-radius:10px; background: rgba(127,127,127,0.12);
             border: 1px solid rgba(127,127,127,0.25); font-size:0.9rem