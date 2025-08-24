# app.py — Villa Tobias (COMPLET)
# ✅ Plateformes gérées dans un onglet dédié + persistées dans Excel (feuille 'plateformes')
# ✅ Réservations dans la feuille 'reservations' (lecture rétrocompatible 'Sheet1')
# ✅ Toutes les vues (Réservations, Ajouter, Modifier/Supprimer, Calendrier, Rapport, Clients, Export ICS, SMS)
# ✅ Restauration / Téléchargement robustes (BytesIO + engine='openpyxl')

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
RES_SHEET = "reservations"
PAL_SHEET = "plateformes"

st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def _normalize_palette_dict(d: dict) -> dict:
    pal = {}
    if not isinstance(d, dict):
        return DEFAULT_PALETTE.copy()
    for k, v in d.items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4, 7):
            pal[k.strip()] = v.strip()
    return pal or DEFAULT_PALETTE.copy()

def _read_palette_from_excel_if_any() -> dict:
    """Lit la feuille 'plateformes' si présente. Sinon DEFAULT."""
    if not os.path.exists(FICHIER):
        return DEFAULT_PALETTE.copy()
    try:
        xls = pd.ExcelFile(FICHIER, engine="openpyxl")
        if PAL_SHEET in xls.sheet_names:
            dfp = pd.read_excel(xls, sheet_name=PAL_SHEET, engine="openpyxl")
            if {"plateforme", "couleur"}.issubset(set(dfp.columns)):
                pal = {str(r["plateforme"]).strip(): str(r["couleur"]).strip()
                       for _, r in dfp.iterrows() if pd.notna(r.get("plateforme")) and pd.notna(r.get("couleur"))}
                return _normalize_palette_dict(pal)
    except Exception:
        pass
    return DEFAULT_PALETTE.copy()

def get_palette() -> dict:
    # 1) Session
    if "palette" not in st.session_state:
        st.session_state.palette = _read_palette_from_excel_if_any()
    # 2) Nettoyage minimal
    st.session_state.palette = _normalize_palette_dict(st.session_state.palette)
    return st.session_state.palette

def set_palette(palette: dict):
    st.session_state.palette = _normalize_palette_dict(palette)

def save_palette_to_excel(palette: dict):
    """Sauvegarde la palette dans la feuille 'plateformes' en même temps que les données."""
    palette = _normalize_palette_dict(palette)
    # Charger les données réservations actuelles pour réécrire les deux feuilles proprement
    df = charger_donnees(no_error=True)
    df = ensure_schema(df)
    _write_both_sheets(df, palette)
    set_palette(palette)
    st.success("🎨 Palette enregistrée (dans l’onglet Excel 'plateformes').")

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

# ==============================  SCHEMA & CALCULS  ==============================

BASE_COLS = [
    "paye","nom_client","sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%","AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    # colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    # types
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # calculs
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]
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

    ordered = [c for c in BASE_COLS if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

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
def _read_excel_cached(path: str, mtime: float) -> pd.DataFrame:
    """Lecture rétrocompatible: 'reservations' sinon 'Sheet1'."""
    xls = pd.ExcelFile(path, engine="openpyxl")
    read_sheet = RES_SHEET if RES_SHEET in xls.sheet_names else ("Sheet1" if "Sheet1" in xls.sheet_names else xls.sheet_names[0])
    df = pd.read_excel(xls, sheet_name=read_sheet, engine="openpyxl", converters={"telephone": normalize_tel})
    return df

def charger_donnees(no_error: bool=False) -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime)
        return ensure_schema(df)
    except Exception as e:
        if not no_error:
            st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

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

def _write_both_sheets(df: pd.DataFrame, palette: dict):
    """Réécrit le fichier complet: reservations + plateformes."""
    df = ensure_schema(df)
    pal = _normalize_palette_dict(palette)
    with pd.ExcelWriter(FICHIER, engine="openpyxl", mode="w") as w:
        df.to_excel(w, index=False, sheet_name=RES_SHEET)
        _force_telephone_text_format_openpyxl(w, df, RES_SHEET)
        pd.DataFrame({"plateforme": list(pal.keys()), "couleur": list(pal.values())}).to_excel(
            w, index=False, sheet_name=PAL_SHEET
        )
    st.cache_data.clear()

def sauvegarder_donnees(df: pd.DataFrame):
    """Sauve toujours les deux feuilles pour garantir la persistance de la palette."""
    try:
        _write_both_sheets(df, get_palette())
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer un .xlsx", type=["xlsx"], help="Remplace le fichier actuel (reservations + plateformes)")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            xls = pd.ExcelFile(bio, engine="openpyxl")

            # Reservations
            read_sheet = RES_SHEET if RES_SHEET in xls.sheet_names else ("Sheet1" if "Sheet1" in xls.sheet_names else xls.sheet_names[0])
            df_new = pd.read_excel(xls, sheet_name=read_sheet, engine="openpyxl", converters={"telephone": normalize_tel})
            df_new = ensure_schema(df_new)

            # Plateformes
            if PAL_SHEET in xls.sheet_names:
                dfp = pd.read_excel(xls, sheet_name=PAL_SHEET, engine="openpyxl")
                if {"plateforme","couleur"}.issubset(dfp.columns):
                    pal = {str(r["plateforme"]).strip(): str(r["couleur"]).strip()
                           for _, r in dfp.iterrows() if pd.notna(r.get("plateforme")) and pd.notna(r.get("couleur"))}
                else:
                    pal = _read_palette_from_excel_if_any()
            else:
                pal = _read_palette_from_excel_if_any()

            _write_both_sheets(df_new, pal)
            set_palette(pal)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    try:
        # on exporte les 2 feuilles dans le même fichier
        with pd.ExcelWriter(buf, engine="openpyxl", mode="w") as w:
            ensure_schema(df).to_excel(w, index=False, sheet_name=RES_SHEET)
            pd.DataFrame({"plateforme": list(get_palette().keys()),
                          "couleur": list(get_palette().values())}).to_excel(
                w, index=False, sheet_name=PAL_SHEET
            )
        st.sidebar.download_button(
            "💾 Télécharger reservations.xlsx",
            data=buf.getvalue(),
            file_name="reservations.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")

# ==============================  ICS ==============================

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
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        f"X-WR-CALNAME:{_ics_escape(cal_name)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    if df.empty:
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    for _, row in df.iterrows():
        d1 = row.get("date_arrivee")
        d2 = row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        plateforme = str(row.get("plateforme") or "").strip()
        nom_client = str(row.get("nom_client") or "").strip()
        tel = str(row.get("telephone") or "").strip()
        summary = " - ".join([x for x in [plateforme, nom_client, tel] if x])
        brut = float(row.get("prix_brut") or 0)
        net  = float(row.get("prix_net")  or 0)
        nuitees = int(row.get("nuitees") or ((d2 - d1).days))

        desc = (
            f"Plateforme: {plateforme}\\n"
            f"Client: {nom_client}\\n"
            f"Téléphone: {tel}\\n"
            f"Arrivee: {d1.strftime('%Y/%m/%d')}\\n"
            f"Depart: {d2.strftime('%Y/%m/%d')}\\n"
            f"Nuitees: {nuitees}\\n"
            f"Brut: {brut:.2f} €\\nNet: {net:.2f} €"
        )

        uid_existing = str(row.get("ical_uid") or "").strip()
        uid = uid_existing if uid_existing else _stable_uid(nom_client, plateforme, d1, d2, tel, salt="v1")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(uid)}",
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
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    d1s = d1.strftime("%Y/%m/%d") if isinstance(d1, date) else ""
    d2s = d2.strftime("%Y/%m/%d") if isinstance(d2, date) else ""
    nuitees = int(row.get("nuitees") or ((d2 - d1).days if isinstance(d1, date) and isinstance(d2, date) else 0))
    plateforme = str(row.get("plateforme") or "")
    nom = str(row.get("nom_client") or "")
    tel_aff = str(row.get("telephone") or "").strip()

    return (
        "VILLA TOBIAS\n"
        f"Plateforme : {plateforme}\n"
        f"Date d'arrivee : {d1s}  Date depart : {d2s}  Nombre de nuitees : {nuitees}\n\n"
        f"Bonjour {nom}\n"
        f"Telephone : {tel_aff}\n\n"
        "Bienvenue chez nous !\n\n"
        "Nous sommes ravis de vous accueillir à Nice. Merci de nous indiquer votre heure d'arrivée.\n\n"
        "Une place de parking vous est allouée.\n\n"
        "Check-in à partir de 14h, check-out au plus tard 11h.\n\n"
        "Bon voyage et à très bientôt,\n"
        "Annick & Charley"
    )

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Merci d’avoir choisi notre appartement pour votre séjour ! "
        "Nous espérons que tout s’est bien passé.\n\n"
        "Au plaisir de vous accueillir à nouveau,\n"
        "Annick & Charley"
    )

# ==============================  UI HELPERS ==============================

def kpi_chips(df: pd.DataFrame):
    df = ensure_schema(df)
    if df.empty:
        return
    b = float(df["prix_brut"].sum())
    total_comm = float(df["commissions"].sum())
    total_cb   = float(df["frais_cb"].sum())
    ch = total_comm + total_cb
    n = float(df["prix_net"].sum())
    base = float(df["base"].sum())
    nuits = float(df["nuitees"].sum())
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
      <div class="chip"><b>Nuitées</b><div class="v">{int(nuits) if not np.isnan(nuits) else 0}</div></div>
      <div class="chip"><b>Commission moy.</b><div class="v">{pct:.2f} %</div></div>
      <div class="chip"><b>Prix moyen/nuit</b><div class="v">{pm_nuit:,.2f} €</div></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def search_box(df: pd.DataFrame) -> pd.DataFrame:
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


# ==============================  PLATEFORMES — Excel I/O + UI  ==============================

PLAT_SHEET = "Plateformes"  # feuille dédiée dans reservations.xlsx

def _is_hex_color(s: str) -> bool:
    if not isinstance(s, str) or not s.startswith("#"):
        return False
    return len(s) in (4, 7) and all(c in "0123456789abcdefABCDEF" for c in s[1:])

@st.cache_data(show_spinner=False)
def _read_palette_excel(path: str, mtime: float) -> pd.DataFrame:
    """Lit la feuille Plateformes si elle existe, sinon DataFrame vide."""
    try:
        xls = pd.ExcelFile(path, engine="openpyxl")
        if PLAT_SHEET in xls.sheet_names:
            dfp = pd.read_excel(xls, sheet_name=PLAT_SHEET, engine="openpyxl")
            return dfp
    except Exception:
        pass
    return pd.DataFrame(columns=["Nom", "Couleur"])

def charger_palette() -> dict:
    """Charge la palette depuis l’onglet Plateformes. Si absent, retourne DEFAULT_PALETTE."""
    if not os.path.exists(FICHIER):
        return DEFAULT_PALETTE.copy()
    try:
        mtime = os.path.getmtime(FICHIER)
        dfp = _read_palette_excel(FICHIER, mtime)
        pal = {}
        for _, r in dfp.iterrows():
            nom = str(r.get("Nom", "")).strip()
            col = str(r.get("Couleur", "")).strip()
            if nom and _is_hex_color(col):
                pal[nom] = col
        if not pal:
            pal = DEFAULT_PALETTE.copy()
        return pal
    except Exception:
        return DEFAULT_PALETTE.copy()

def sauvegarder_palette(palette: dict):
    """Écrit/écrase la feuille Plateformes dans le même fichier Excel."""
    # On conserve la feuille principale (réservations) telle quelle, et on remplace/ajoute la feuille Plateformes.
    # On relit le fichier pour récupérer les autres feuilles intactes.
    try:
        # lire toutes les feuilles existantes
        sheets = {}
        if os.path.exists(FICHIER):
            xls = pd.ExcelFile(FICHIER, engine="openpyxl")
            for name in xls.sheet_names:
                sheets[name] = pd.read_excel(xls, sheet_name=name, engine="openpyxl")

        # convertir la palette -> DataFrame
        dfp = pd.DataFrame(
            [{"Nom": k, "Couleur": v} for k, v in palette.items() if k and _is_hex_color(v)]
        )

        # réécrire toutes les feuilles (remplacer Plateformes)
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            for name, df_sheet in sheets.items():
                # si c'est Plateformes on sautera, on réécrira après
                if name != PLAT_SHEET:
                    df_sheet.to_excel(w, index=False, sheet_name=name)
            # écrire/écraser la feuille palettes
            dfp.to_excel(w, index=False, sheet_name=PLAT_SHEET)

        # purge du cache de lecture
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.success("🎨 Palette enregistrée dans la feuille « Plateformes ».")

    except Exception as e:
        st.error(f"Échec de sauvegarde de la palette : {e}")

def get_palette() -> dict:
    """
    Surcharge de get_palette pour utiliser l’onglet Excel.
    - Si l’utilisateur a modifié la palette pendant la session, on la garde en session_state.
    - Sinon on charge depuis Excel (ou défaut).
    """
    key = "palette_excel"
    if key in st.session_state and isinstance(st.session_state[key], dict) and st.session_state[key]:
        return st.session_state[key]
    pal = charger_palette()
    st.session_state[key] = pal.copy()
    return pal

def set_palette(pal: dict):
    st.session_state["palette_excel"] = pal.copy()

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

def vue_plateformes():
    """Page de gestion des plateformes (CRUD) avec persistance Excel."""
    st.title("🔧 Gestion des plateformes")
    pal = get_palette()
    if not pal:
        pal = DEFAULT_PALETTE.copy()
        set_palette(pal)

    # Aperçu
    st.subheader("Aperçu actuel")
    if pal:
        badges = " &nbsp;&nbsp;".join([platform_badge(pf, pal) for pf in sorted(pal.keys())])
        st.markdown(badges, unsafe_allow_html=True)
    else:
        st.info("Aucune plateforme définie.")

    st.divider()

    # Formulaire ajout / mise à jour
    st.subheader("Ajouter / Modifier")
    c1, c2, c3 = st.columns([2,1,1])
    with c1:
        nom_pf = st.text_input("Nom de la plateforme", placeholder="Ex: Expedia")
    with c2:
        col_pf = st.color_picker("Couleur", value="#9b59b6")
    with c3:
        st.write("")
        st.write("")
        if st.button("💾 Ajouter / Mettre à jour"):
            name = (nom_pf or "").strip()
            if not name:
                st.warning("Entrez un nom de plateforme.")
            elif not _is_hex_color(col_pf):
                st.warning("Couleur invalide (utilisez un code hexadécimal ex: #1e90ff).")
            else:
                pal[name] = col_pf
                set_palette(pal)
                st.success(f"✅ Plateforme « {name} » modifiée dans la session (n'oubliez pas d'**Enregistrer dans Excel**).")
                st.rerun()

    st.divider()

    # Tableau éditable
    st.subheader("Modifier en tableau (session)")
    df_edit = pd.DataFrame(
        [{"Nom": k, "Couleur": v} for k, v in sorted(pal.items(), key=lambda kv: kv[0].lower())]
    )
    edited = st.data_editor(
        df_edit,
        use_container_width=True,
        hide_index=True,
        num_rows="dynamic",
        column_config={
            "Nom": st.column_config.TextColumn("Nom"),
            "Couleur": st.column_config.TextColumn("Couleur (ex: #1e90ff)"),
        },
        key="pal_editor"
    )

    cA, cB, cC = st.columns(3)
    if cA.button("🧹 Réinitialiser (valeurs par défaut)"):
        pal = DEFAULT_PALETTE.copy()
        set_palette(pal)
        st.success("Palette réinitialisée dans la session.")
        st.rerun()

    if cB.button("🗑 Supprimer la sélection (par nom exact)"):
        # On lit l'état courant de l'éditeur et on reconstruit la palette propre
        new_pal = {}
        for _, r in edited.iterrows():
            name = str(r.get("Nom", "")).strip()
            col  = str(r.get("Couleur", "")).strip()
            if name and _is_hex_color(col):
                new_pal[name] = col
        # Diff avec pal d'avant pour détecter suppressions
        before_keys = set(pal.keys())
        after_keys  = set(new_pal.keys())
        deleted = before_keys - after_keys
        if deleted:
            set_palette(new_pal)
            st.success(f"Supprimé: {', '.join(sorted(deleted))}")
            st.rerun()
        else:
            st.info("Aucune différence détectée.")

    if cC.button("📄 Enregistrer dans Excel (onglet Plateformes)"):
        # Valider et écrire
        final_pal = {}
        for _, r in edited.iterrows():
            name = str(r.get("Nom", "")).strip()
            col  = str(r.get("Couleur", "")).strip()
            if name and _is_hex_color(col):
                final_pal[name] = col
        if not final_pal:
            st.warning("La palette finale est vide. Ajoutez au moins une ligne avec une couleur valide.")
        else:
            sauvegarder_palette(final_pal)
            set_palette(final_pal)
            st.success("✅ Palette enregistrée et rechargée.")

    st.caption("Astuce : la palette est stockée dans la feuille Excel « Plateformes » (colonnes **Nom**, **Couleur**).")

# ==============================  (INTÉGRATION — NAVIGATION)  ==============================
# Dans votre main(), ajoutez l'entrée "🔧 Plateformes" au menu puis appelez vue_plateformes().
# Exemple:
#   onglet = st.sidebar.radio("Aller à", [
#       "📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
#       "📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS","🔧 Plateformes"
#   ])
#   ...
#   elif onglet == "🔧 Plateformes":
#       vue_plateformes()