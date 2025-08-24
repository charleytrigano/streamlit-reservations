# app.py — Villa Tobias (COMPLET – 2 feuilles Excel, plateformes persistantes, calendrier coloré)

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

def _cleanup_hex(c: str) -> str:
    if not isinstance(c, str): return "#999999"
    c = c.strip()
    if len(c) in (4,7) and c.startswith("#"):
        return c
    return "#999999"

def get_palette() -> dict:
    """Palette par ordre de priorité: session_state -> feuille Excel -> défauts."""
    # si déjà en mémoire
    if "palette" in st.session_state:
        # nettoyage
        pal = {}
        for k, v in st.session_state.palette.items():
            if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4,7):
                pal[k] = v
        st.session_state.palette = pal
        return st.session_state.palette

    # sinon tenter lecture Excel
    df_res, pal = _read_workbook(FICHIER)
    st.session_state.palette = pal.copy()
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = {str(k): _cleanup_hex(v) for k, v in palette.items() if k and v}
    # sauver en Excel (fusionner avec réservations existantes)
    df = charger_donnees()  # lit la feuille Reservations
    _write_workbook(df, st.session_state.palette)

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
    with st.sidebar.expander("➕ Ajouter / modifier", expanded=False):
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
        st.sidebar.markdown("**Plateformes :**")
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

# ==============================  EXCEL I/O (2 FEUILLES)  ==============================
@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    # Lecture de la feuille Reservations uniquement (utilisé par charger_donnees)
    return pd.read_excel(path, sheet_name="Reservations", engine="openpyxl", converters={"telephone": normalize_tel})

def _read_workbook(path: str):
    """Retourne (df_reservations, palette_dict)"""
    if not os.path.exists(path):
        return ensure_schema(pd.DataFrame()), DEFAULT_PALETTE.copy()
    try:
        xls = pd.ExcelFile(path, engine="openpyxl")
        # Reservations
        if "Reservations" in xls.sheet_names:
            df_res = pd.read_excel(xls, sheet_name="Reservations", converters={"telephone": normalize_tel})
        else:
            df_res = pd.read_excel(path, engine="openpyxl", converters={"telephone": normalize_tel})
        df_res = ensure_schema(df_res)
        # Plateformes
        pal = DEFAULT_PALETTE.copy()
        if "Plateformes" in xls.sheet_names:
            dfp = pd.read_excel(xls, sheet_name="Plateformes")
            for _, r in dfp.iterrows():
                nom = str(r.get("plateforme") or "").strip()
                col = _cleanup_hex(str(r.get("couleur") or "#999999"))
                if nom:
                    pal[nom] = col
        return df_res, pal
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame()), DEFAULT_PALETTE.copy()

def _write_workbook(df_reservations: pd.DataFrame, palette: dict):
    """Écrit les 2 feuilles : Reservations + Plateformes."""
    try:
        df_reservations = ensure_schema(df_reservations.copy())
        dfp = pd.DataFrame(
            [{"plateforme": k, "couleur": v} for k, v in sorted(palette.items(), key=lambda x: x[0].lower())]
        )
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            df_reservations.to_excel(w, index=False, sheet_name="Reservations")
            dfp.to_excel(w, index=False, sheet_name="Plateformes")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Échec écriture Excel : {e}")

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        # créer un classeur vide avec 2 feuilles par défaut
        _write_workbook(ensure_schema(pd.DataFrame()), DEFAULT_PALETTE.copy())
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime)
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    # écrire avec la palette actuelle
    _write_workbook(df, get_palette())
    st.success("💾 Sauvegarde Excel effectuée.")

def bouton_restaurer():
    up = st.sidebar.file_uploader(
        "📤 Restauration xlsx",
        type=["xlsx"],
        key=f"restore_{st.session_state.uploader_key_restore}",
        help="Remplace le fichier actuel (Reservations + Plateformes)"
    )
    if up is not None and st.sidebar.button("Restaurer maintenant"):
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            # Lire les 2 feuilles du fichier uploadé
            xls = pd.ExcelFile(bio, engine="openpyxl")
            if "Reservations" in xls.sheet_names:
                df_new = pd.read_excel(xls, sheet_name="Reservations", converters={"telephone": normalize_tel})
            else:
                df_new = pd.read_excel(bio, engine="openpyxl", converters={"telephone": normalize_tel})
            df_new = ensure_schema(df_new)
            pal = DEFAULT_PALETTE.copy()
            if "Plateformes" in xls.sheet_names:
                dfp = pd.read_excel(xls, sheet_name="Plateformes")
                pal = {}
                for _, r in dfp.iterrows():
                    nom = str(r.get("plateforme") or "").strip()
                    col = _cleanup_hex(str(r.get("couleur") or "#999999"))
                    if nom:
                        pal[nom] = col
                if not pal:
                    pal = DEFAULT_PALETTE.copy()
            # écrire
            _write_workbook(df_new, pal)
            st.session_state.palette = pal.copy()
            st.sidebar.success("✅ Fichier restauré.")
            # reset widget key -> évite le re-run infini
            st.session_state.uploader_key_restore += 1
            st.experimental_rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    try:
        # produire un xlsx contenant les 2 feuilles actuelles
        df = ensure_schema(df)
        pal = get_palette()
        dfp = pd.DataFrame([{"plateforme": k, "couleur": v} for k, v in pal.items()])
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Reservations")
            dfp.to_excel(w, index=False, sheet_name="Plateformes")
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
        help="Fichier complet (2 feuilles)."
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
    base = f"{nom_client}|{plateforme}|{d1}|{d2}|{tel}|{salt}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return f"vt-{h}@villatobias"

def df_to_ics(df: pd.DataFrame, cal_name: str = "Villa Tobias – Réservations") -> str:
    df = ensure_schema(df)
    if df.empty:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//Villa Tobias//Reservations//FR",
            f"X-WR-CALNAME:{_ics_escape(cal_name)}",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
            "END:VCALENDAR",
        ]
        return "\r\n".join(lines) + "\r\n"
    core, _ = split_totals(df)
    core = sort_core(core)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        f"X-WR-CALNAME