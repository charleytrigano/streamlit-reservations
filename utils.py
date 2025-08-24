# utils.py — outils communs (Excel I/O, schéma, palette, KPI)

import streamlit as st
import pandas as pd
import numpy as np
from datetime import date, datetime, timezone
from io import BytesIO
import os

FICHIER = "reservations.xlsx"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

BASE_COLS = [
    "paye","nom_client","sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%","AAAA","MM","ical_uid"
]

# ---------- Petits helpers ----------

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
    if x is None or (isinstance(x,float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

# ---------- Schéma + calculs ----------

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    # Colonnes minimales
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    # Types / normalisation
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)

    df["telephone"] = df["telephone"].apply(normalize_tel)

    # Numériques
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Nuitées
    df["nuitees"] = [
        (d2 - d1).days if (isinstance(d1,date) and isinstance(d2,date)) else np.nan
        for d1,d2 in zip(df["date_arrivee"], df["date_depart"])
    ]

    # AAAA / MM
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d,date) else np.nan).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d,date) else np.nan).astype("Int64")

    # Valeurs par défaut
    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"]   = df["ical_uid"].fillna("")

    # Calculs
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)

    ordered = [c for c in BASE_COLS if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

def split_totals(df: pd.DataFrame):
    # Ici on ne traite pas des lignes "TOTAL" séparées pour l’étape 1
    return df.copy(), pd.DataFrame(columns=df.columns)

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return df.sort_values(by=[c for c in ["date_arrivee","nom_client"] if c in df.columns],
                          na_position="last").reset_index(drop=True)

# ---------- Palette (session + Excel) ----------

def get_palette_session() -> dict:
    if "palette" not in st.session_state:
        # Charger depuis Excel sinon défaut
        st.session_state.palette = charger_palette_excel() or DEFAULT_PALETTE.copy()
    # petit nettoyage
    pal = {}
    for k,v in st.session_state.palette.items():
        if isinstance(k,str) and isinstance(v,str) and v.startswith("#") and len(v) in (4,7):
            pal[k] = v
    st.session_state.palette = pal if pal else DEFAULT_PALETTE.copy()
    return st.session_state.palette

def set_palette_session(pal: dict):
    st.session_state.palette = {str(k): str(v) for k,v in pal.items() if k and v}

# ---------- Excel I/O ----------

def _pick_reservation_sheet(xls: pd.ExcelFile) -> str:
    # Priorité à "Sheet1", sinon première feuille
    if "Sheet1" in xls.sheet_names:
        return "Sheet1"
    return xls.sheet_names[0]

def read_excel_all(src_path_or_buffer) -> tuple[pd.DataFrame, dict]:
    """Retourne (df_reservations, palette_dict) depuis un chemin OU un buffer BytesIO."""
    try:
        xls = pd.ExcelFile(src_path_or_buffer, engine="openpyxl")
    except Exception as e:
        raise e

    # Réservations
    res_sheet = _pick_reservation_sheet(xls)
    df = pd.read_excel(xls, sheet_name=res_sheet, engine="openpyxl",
                       converters={"telephone": normalize_tel})
    df = ensure_schema(df)

    # Palette
    pal = {}
    if "Plateformes" in xls.sheet_names:
        dfp = pd.read_excel(xls, sheet_name="Plateformes", engine="openpyxl")
        for _,r in dfp.fillna("").iterrows():
            k = str(r.get("plateforme","")).strip()
            v = str(r.get("couleur","")).strip()
            if k and v and v.startswith("#"):
                pal[k] = v
    return df, (pal or None)

def _force_telephone_text_format_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
    try:
        ws = writer.sheets.get(sheet_name) or writer.sheets.get('Sheet1', None)
        if ws is None or "telephone" not in df_to_save.columns:
            return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            row[0].number_format = '@'
    except Exception:
        pass

def sauvegarder_donnees(df: pd.DataFrame, palette: dict | None = None):
    """Écrit *toujours* deux feuilles : Sheet1 (réservations) + Plateformes (palette)."""
    df = ensure_schema(df)
    pal = palette if palette is not None else (st.session_state.get("palette") or DEFAULT_PALETTE)
    dfp = pd.DataFrame(
        [{"plateforme": k, "couleur": v} for k,v in pal.items()],
        columns=["plateforme","couleur"]
    )
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name="Sheet1")
            _force_telephone_text_format_openpyxl(w, df, "Sheet1")
            dfp.to_excel(w, index=False, sheet_name="Plateformes")
        st.cache_data.clear()
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        # astuce cache: utiliser mtime
        mtime = os.path.getmtime(FICHIER)
        @st.cache_data(show_spinner=False)
        def _read(m):
            return read_excel_all(FICHIER)[0]
        return _read(mtime)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def charger_palette_excel() -> dict | None:
    if not os.path.exists(FICHIER):
        return None
    try:
        pal = read_excel_all(FICHIER)[1]
        return pal
    except Exception:
        return None

# ---------- Widgets fichier (restaurer / télécharger) ----------

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer un .xlsx", type=["xlsx"], help="Remplace complètement le fichier actuel")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            df_new, pal_new = read_excel_all(bio)
            # si pas de palette, on conserve la session palette
            if pal_new is None:
                pal_new = get_palette_session()
            sauvegarder_donnees(df_new, pal_new)
            set_palette_session(pal_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import : {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    data_xlsx = b""
    try:
        pal = get_palette_session()
        # écrire en mémoire
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            ensure_schema(df).to_excel(w, index=False, sheet_name="Sheet1")
            pd.DataFrame(
                [{"plateforme":k,"couleur":v} for k,v in pal.items()],
                columns=["plateforme","couleur"]
            ).to_excel(w, index=False, sheet_name="Plateformes")
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = b""
    st.sidebar.download_button(
        "💾 Télécharger reservations.xlsx",
        data=data_xlsx,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data_xlsx)==0),
    )

# ---------- KPI chips ----------

def kpi_chips(df: pd.DataFrame):
    if df is None or df.empty:
        return
    b = float(df["prix_brut"].sum())
    comm = float(df["commissions"].sum())
    cb   = float(df["frais_cb"].sum())
    ch = comm + cb
    n = float(df["prix_net"].sum())
    base = float(df["base"].sum())
    nuits = int(df["nuitees"].sum()) if pd.notna(df["nuitees"].sum()) else 0
    pct = (ch / b * 100) if b else 0.0
    pm_nuit = (b / nuits) if nuits else 0.0

    html = f"""
    <style>
      .chips-wrap {{ display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 10px 0; }}
      .chip {{ padding:8px 10px; border-radius:10px; background: rgba(127,127,127,0.12); border: 1px solid rgba(127,127,127,0.25); font-size:0.9rem; }}
      .chip b {{ display:block; margin-bottom:3px; font-size:0.85rem; opacity:0.8; }}
      .chip .v {{ font-weight:600; }}
    </style>
    <div class="chips-wrap">
      <div class="chip"><b>Total Brut</b><div class="v">{b:,.2f} €</div></div>
      <div class="chip"><b>Total Net</b><div class="v">{n:,.2f} €</div></div>
      <div class="chip"><b>Total Base</b><div class="v">{base:,.2f} €</div></div>
      <div class="chip"><b>Total Charges</b><div class="v">{ch:,.2f} €</div></div>
      <div class="chip"><b>Nuitées</b><div class="v">{nuits}</div></div>
      <div class="chip"><b>Commission moy.</b><div class="v">{pct:.2f} %</div></div>
      <div class="chip"><b>Prix moyen/nuit</b><div class="v">{pm_nuit:,.2f} €</div></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)
