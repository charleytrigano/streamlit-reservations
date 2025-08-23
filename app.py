# app.py — Villa Tobias (COMPLET)
# - Onglets : Réservations / Ajouter / Modifier-Supprimer / Calendrier / Rapport / Clients / Export ICS / SMS / Plateformes
# - Palette plateformes PERSISTANTE dans le fichier Excel (feuille "Plateformes")
# - Calendrier mensuel lisible (fond coloré par plateforme + noms clients, texte noir/blanc auto)
# - Restauration XLSX robuste (BytesIO) + lecture/écriture forçant engine="openpyxl"
# - KPI, SMS, ICS
# - Filtre "Payé" corrigé
# - Pas d’expander imbriqué

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
from openpyxl import load_workbook
from openpyxl.workbook import Workbook

FICHIER = "reservations.xlsx"
SHEET_RES = "Sheet1"          # on garde le nom historique
SHEET_PAL = "Plateformes"     # palette persistée

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE PAR DÉFAUT ==============================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",  # bleu
    "Airbnb":  "#e74c3c",  # rouge
    "Autre":   "#f59e0b",  # orange
}

# ==============================  OUTILS PALETTE (EXCEL) ==============================

def _sanitize_palette(pal: dict) -> dict:
    out = {}
    for k, v in (pal or {}).items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4, 7) and k.strip():
            out[k.strip()] = v
    return out or DEFAULT_PALETTE.copy()

def read_palette_from_excel() -> dict:
    """Lit la feuille 'Plateformes' si présente, sinon renvoie DEFAULT_PALETTE."""
    if not os.path.exists(FICHIER):
        return DEFAULT_PALETTE.copy()
    try:
        x = pd.ExcelFile(FICHIER, engine="openpyxl")
        if SHEET_PAL in x.sheet_names:
            dfp = pd.read_excel(x, sheet_name=SHEET_PAL, engine="openpyxl")
            if not dfp.empty and {"plateforme", "couleur"}.issubset(dfp.columns):
                pal = {str(r["plateforme"]).strip(): str(r["couleur"]).strip()
                       for _, r in dfp.iterrows() if pd.notna(r["plateforme"]) and pd.notna(r["couleur"])}
                return _sanitize_palette(pal)
    except Exception:
        pass
    return DEFAULT_PALETTE.copy()

def save_palette_to_excel(palette: dict):
    """Écrit la palette dans la feuille 'Plateformes' (remplace si existe) en préservant la feuille 'Sheet1'."""
    palette = _sanitize_palette(palette)
    df_pal = pd.DataFrame(
        [{"plateforme": k, "couleur": v} for k, v in sorted(palette.items(), key=lambda x: x[0].lower())]
    )

    if os.path.exists(FICHIER):
        # Charger le fichier existant et remplacer/ajouter les feuilles propres
        try:
            wb = load_workbook(FICHIER)
        except Exception:
            wb = Workbook()
        with pd.ExcelWriter(FICHIER, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
            writer.book = wb
            # si la feuille des réservations n'existe pas, ne rien écraser ici (elle est gérée ailleurs)
            df_pal.to_excel(writer, index=False, sheet_name=SHEET_PAL)
    else:
        # Créer un nouveau fichier avec juste la feuille Plateformes
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as writer:
            # Crée une feuille vide de réservations pour garder la structure si on souhaite
            pd.DataFrame().to_excel(writer, index=False, sheet_name=SHEET_RES)
            df_pal.to_excel(writer, index=False, sheet_name=SHEET_PAL)

def get_palette() -> dict:
    # session_state -> lecture Excel une fois
    if "palette" not in st.session_state:
        st.session_state.palette = read_palette_from_excel()
    st.session_state.palette = _sanitize_palette(st.session_state.palette)
    return st.session_state.palette

def set_palette(palette: dict):
    pal = _sanitize_palette(palette)
    st.session_state.palette = pal
    save_palette_to_excel(pal)

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

# ==============================  MAINTENANCE / CACHE  ==============================

def render_cache_section_sidebar():
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache et relancer"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.sidebar.success("Cache vidé. Redémarrage…")
        st.rerun()

# ==============================  OUTILS GÉNÉRAUX  ==============================

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

    df["paye"] = df["paye"].fillna(False).astype(bool)
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
    try:
        x = pd.ExcelFile(path, engine="openpyxl")
        if SHEET_RES in x.sheet_names:
            df = pd.read_excel(x, sheet_name=SHEET_RES, engine="openpyxl", converters={"telephone": normalize_tel})
        else:
            # compat si une autre feuille unique
            df = pd.read_excel(path, engine="openpyxl", converters={"telephone": normalize_tel})
        return df
    except Exception as e:
        raise e

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

def _force_telephone_text_format_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
    try:
        ws = writer.sheets.get(sheet_name) or writer.sheets.get(SHEET_RES, None)
        if ws is None or "telephone" not in df_to_save.columns:
            return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            row[0].number_format = '@'
    except Exception:
        pass

def sauvegarder_donnees(df: pd.DataFrame):
    """Sauvegarde la feuille des réservations ET préserve/écrit la feuille Plateformes."""
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)

    # Lire palette actuelle (depuis session_state ou Excel) pour la réécrire aussi
    pal = get_palette()

    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name=SHEET_RES)
            _force_telephone_text_format_openpyxl(w, out, SHEET_RES)
            # écrire palette
            df_pal = pd.DataFrame(
                [{"plateforme": k, "couleur": v} for k, v in sorted(pal.items(), key=lambda x: x[0].lower())]
            )
            df_pal.to_excel(w, index=False, sheet_name=SHEET_PAL)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            # on ne filtre pas les feuilles : on pose tel quel
            with open(FICHIER, "wb") as f:
                f.write(bio.getvalue())
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    data_xlsx = b""
    try:
        # écrire réservations + palette
        pal = get_palette()
        df = ensure_schema(df)
        core, totals = split_totals(df)
        core = sort_core(core)
        out = pd.concat([core, totals], ignore_index=True)
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name=SHEET_RES)
            df_pal = pd.DataFrame(
                [{"plateforme": k, "couleur": v} for k, v in sorted(pal.items(), key=lambda x: x[0].lower())]
            )
            df_pal.to_excel(w, index=False, sheet_name=SHEET_PAL)
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = b""
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=data_xlsx,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data_xlsx) == 0),
        help="Télécharge une sauvegarde locale."
    )

# ==============================  ICS EXPORT  ==============================

def _ics_escape(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    s = s.replace("\n", "\\n")
    return s

def _fmt_date_ics(d: date) -> str:
    return d.strftime("%Y%m%d")

def _dtstamp_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def _stable_uid(nom_client, plateforme, d1, d2, tel, salt="v1"):
    base = f"{nom_client}|{plateforme}|