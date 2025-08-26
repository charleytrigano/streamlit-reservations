# app.py — Villa Tobias (COMPLET)
# - Réservations / Ajouter / Modifier-Supprimer
# - Plateformes (palette couleurs) avec sauvegarde dans Excel (feuille "Plateformes")
# - Calendrier mensuel "barres style agenda" (lisible en thème sombre)
# - Rapport (KPI + charts), Liste clients, Export ICS, SMS
# - Restauration XLSX robuste (BytesIO)
# - Excel via openpyxl
# - Remplacement total de st.experimental_rerun() -> st.rerun()

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
PALETTE_SHEET = "Plateformes"   # feuille Excel palette
DATA_SHEET = "Sheet1"           # feuille Excel des réservations

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  SESSION KEYS  ==============================
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

def _clean_hex(c: str) -> str:
    if not isinstance(c, str):
        return "#999999"
    c = c.strip()
    if not c.startswith("#"):
        c = "#" + c
    if len(c) == 4 or len(c) == 7:
        return c
    return "#999999"

def get_palette() -> dict:
    """Palette en mémoire (priorité à session_state)."""
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    # nettoyage minimal
    pal = {}
    for k, v in st.session_state.palette.items():
        if isinstance(k, str) and isinstance(v, str):
            pal[k.strip()] = _clean_hex(v)
    st.session_state.palette = pal
    return st.session_state.palette

def set_palette(pal: dict):
    """Remplace la palette en mémoire."""
    st.session_state.palette = {str(k).strip(): _clean_hex(str(v)) for k, v in pal.items() if k and v}

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

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
def _read_workbook(path: str, mtime: float):
    """Retourne (df_reservations, palette_dict) à partir du fichier Excel."""
    try:
        with pd.ExcelFile(path, engine="openpyxl") as xf:
            # Réservations
            if DATA_SHEET in xf.sheet_names:
                df = pd.read_excel(xf, sheet_name=DATA_SHEET, engine="openpyxl",
                                   converters={"telephone": normalize_tel})
            else:
                # si la 1ère feuille existe on la prend
                first = xf.sheet_names[0] if xf.sheet_names else DATA_SHEET
                df = pd.read_excel(xf, sheet_name=first, engine="openpyxl",
                                   converters={"telephone": normalize_tel})
            df = ensure_schema(df)

            # Palette
            pal = DEFAULT_PALETTE.copy()
            if PALETTE_SHEET in xf.sheet_names:
                pf_df = pd.read_excel(xf, sheet_name=PALETTE_SHEET, engine="openpyxl")
                if {"plateforme","couleur"}.issubset(set(pf_df.columns)):
                    for _, r in pf_df.iterrows():
                        name = str(r["plateforme"]).strip()
                        color = _clean_hex(str(r["couleur"]))
                        if name:
                            pal[name] = color
            return df, pal
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame()), DEFAULT_PALETTE.copy()

def charger_donnees():
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame()), get_palette()
    mtime = os.path.getmtime(FICHIER)
    df, pal = _read_workbook(FICHIER, mtime)
    set_palette(pal)
    return df, pal

def _force_tel_text_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
    try:
        ws = writer.sheets.get(sheet_name)
        if ws is None or "telephone" not in df_to_save.columns:
            return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            row[0].number_format = '@'
    except Exception:
        pass

def sauvegarder_donnees(df: pd.DataFrame, palette: dict = None):
    """Sauvegarde réservations (+ éventuellement palette) dans le même fichier."""
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)

    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name=DATA_SHEET)
            _force_tel_text_openpyxl(w, out, DATA_SHEET)
            # Écrire palette si fournie
            if palette is not None:
                p = pd.DataFrame(
                    [{"plateforme": k, "couleur": v} for k, v in sorted(palette.items())]
                )
                p.to_excel(w, index=False, sheet_name=PALETTE_SHEET)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader(
        "📤 Restauration xlsx",
        type=["xlsx"],
        key=f"restore_{st.session_state.uploader_key_restore}",
        help="Charge un fichier et remplace le fichier actuel"
    )
    if up is not None and st.sidebar.button("Restaurer maintenant"):
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            with pd.ExcelFile(bio, engine="openpyxl") as xf:
                # Vérifier et lire
                if DATA_SHEET in xf.sheet_names:
                    df_new = pd.read_excel(xf, sheet_name=DATA_SHEET, engine="openpyxl",
                                           converters={"telephone": normalize_tel})
                else:
                    first = xf.sheet_names[0]
                    df_new = pd.read_excel(xf, sheet_name=first, engine="openpyxl",
                                           converters={"telephone": normalize_tel})
                df_new = ensure_schema(df_new)

                palette_new = DEFAULT_PALETTE.copy()
                if PALETTE_SHEET in xf.sheet_names:
                    pal_df = pd.read_excel(xf, sheet_name=PALETTE_SHEET, engine="openpyxl")
                    if {"plateforme","couleur"}.issubset(set(pal_df.columns)):
                        for _, r in pal_df.iterrows():
                            name = str(r["plateforme"]).strip()
                            color = _clean_hex(str(r["couleur"]))
                            if name:
                                palette_new[name] = color

            # Sauvegarder fichier "officiel"
            sauvegarder_donnees(df_new, palette_new)
            set_palette(palette_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.session_state.uploader_key_restore += 1
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    data_xlsx = b""
    try:
        df2 = ensure_schema(df)
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            df2.to_excel(w, index=False, sheet_name=DATA_SHEET)
            pal = get_palette()
            p = pd.DataFrame([{"plateforme": k, "couleur": v} for k, v in sorted(pal.items())])
            p.to_excel(w, index=False, sheet_name=PALETTE_SHEET)
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = b""
    st.sidebar.download_button(
        "💾 Télécharger reservations.xlsx",
        data=data_xlsx,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data_xlsx) == 0)
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
        f"X-WR-CALNAME:{_ics_escape(cal_name)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for _, row in core.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        plateforme = str(row.get("plateforme") or "").strip()
        nom_client = str(row.get("nom_client") or "").strip()
        tel = str(row.get("telephone") or "").strip()
        brut = float(row.get("prix_brut") or 0.0)
        net  = float(row.get("prix_net") or 0.0)
        nuitees = int(row.get("nuitees") or ((d2 - d1).days))
        summary = " - ".join([x for x in [plateforme, nom_client, tel] if x])
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

# ==============================  SMS (MANUEL) ==============================
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
        f"Arrivée : {d1s}  Départ : {d2s}  Nuitées : {nuitees}\n\n"
        f"Bonjour {nom}\n"
        f"Téléphone : {tel_aff}\n\n"
        "Bienvenue chez nous !\n\n"
        "Nous sommes ravis de vous accueillir a Nice.\n\n"
        "Afin d'organiser au mieux votre reception, merci de nous indiquer votre heure d'arrivée.\n\n"
        "Une place de parking vous est allouée en cas de besoin.\n\n"
        "Le check-in se fait à partir de 14:00 et le check-out au plus tard à 11:00.\n\n"
        "Vous trouverez des consignes à bagages dans chaque quartier de Nice.\n\n"
        "Nous vous souhaitons un excellent voyage et nous nous réjouissons de vous rencontrer très bientôt.\n\n"
        "Annick & Charley\n\n"
        "Welcome to our home.\n\n"
        "We are delighted to welcome you to Nice.\n\n"
        "In order to organize your reception as best as possible, please let us know your arrival time.\n\n"
        "A parking space is available if needed.\n\n"
        "Check-in is from 2:00 p.m. and check-out is by 11:00 a.m. at the latest.\n\n"
        "You will find luggage storage facilities in every district of Nice.\n\n"
        "We wish you a wonderful trip and look forward to meeting you very soon.\n\n"
        "Annick & Charley"
    )

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Merci d’avoir choisi notre appartement pour votre séjour ! "
        "Au plaisir de vous accueillir à nouveau.\n\n"
        "Annick & Charley"
    )

# ==============================  UI HELPERS  ==============================
def kpi_chips(df: pd.DataFrame):
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
    .chip {{ padding:8px 10px; border-radius:10px; background: rgba(127,127,127,0.12); border: 1px solid rgba(127,127,127,0.25); font-size:0.9rem; }}
    .chip b {{ display:block; margin-bottom:3px; font-size:0.85rem; opacity:0.8; }}
    .chip .v {{ font-weight:600; }}
    </style>
    <div class="chips-wrap">
      <div class="chip"><b>Total Brut</b><div class="v">{b:,.2f} €</div></div>
      <div class="chip"><b>Total Net</b><div class="v">{n:,.2f} €</div></div>
      <div class="chip"><b>Total Base</b><div class="v">{base:,.2f} €</div></div>
      <div class="chip"><b>Total Charges</b><div class="v">{ch:,.2f} €</div></div>
      <div class="chip"><b>Nuitées</b><div class="v">{int(nuits) if pd.notna(nuits) else 0}</div></div>
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

# ==============================  VUES  ==============================
def vue_reservations(df: pd.DataFrame):
    palette = get_palette()
    st.title("📋 Réservations")

    with st.expander("🎛️ Options d’affichage", expanded=True):
        filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
        show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)

    st.markdown("### Plateformes")
    if palette:
        badges = " &nbsp;&nbsp;".join([platform_badge(pf, palette) for pf in sorted(palette.keys())])
        st.markdown(badges, unsafe_allow_html=True)

    df = ensure_schema(df)
    if filtre_paye == "Payé":
        df = df[df["paye"] == True].copy()
    elif filtre_paye == "Non payé":
        df = df[df["paye"] == False].copy()

    if show_kpi:
        kpi_chips(df)
    if enable_search:
        df = search_box(df)

    core, totals = split_totals(df)
    core = sort_core(core)

    core_edit = core.copy()
    core_edit["__rowid"] = core_edit.index
    core_edit["date_arrivee"] = core_edit["date_arrivee"].apply(format_date_str)
    core_edit["date_depart"]  = core_edit["date_depart"].apply(format_date_str)

    cols_order = [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net",
        "menage","taxes_sejour","base","charges","%","AAAA","MM","__rowid"
    ]
    cols_show = [c for c in cols_order if c in core_edit.columns]

    edited = st.data_editor(
        core_edit[cols_show],
        use_container_width=True,
        hide_index=True,
        column_config={
            "paye": st.column_config.CheckboxColumn("Payé"),
            "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
            "__rowid": st.column_config.Column("id", help="Interne", disabled=True, width="small"),
            "date_arrivee": st.column_config.TextColumn("date_arrivee", disabled=True),
            "date_depart":  st.column_config.TextColumn("date_depart", disabled=True),
            "nom_client":   st.column_config.TextColumn("nom_client", disabled=True),
            "plateforme":   st.column_config.TextColumn("plateforme", disabled=True),
            "telephone":    st.column_config.TextColumn("telephone", disabled=True),
            "nuitees":      st.column_config.NumberColumn("nuitees", disabled=True),
            "prix_brut":    st.column_config.NumberColumn("prix_brut", disabled=True),
            "commissions":  st.column_config.NumberColumn("commissions", disabled=True),
            "frais_cb":     st.column_config.NumberColumn("frais_cb", disabled=True),
            "prix_net":     st.column_config.NumberColumn("prix_net", disabled=True),
            "menage":       st.column_config.NumberColumn("menage", disabled=True),
            "taxes_sejour": st.column_config.NumberColumn("taxes_sejour", disabled=True),
            "base":         st.column_config.NumberColumn("base", disabled=True),
            "charges":      st.column_config.NumberColumn("charges", disabled=True),
            "%":            st.column_config.NumberColumn("%", disabled=True),
            "AAAA":         st.column_config.NumberColumn("AAAA", disabled=True),
            "MM":           st.column_config.NumberColumn("MM", disabled=True),
        }
    )

    c1, _ = st.columns([1,3])
    if c1.button("💾 Enregistrer les cases cochées"):
        for _, r in edited.iterrows():
            ridx = int(r["__rowid"])
            core.at[ridx, "paye"] = bool(r.get("paye", False))
            core.at[ridx, "sms_envoye"] = bool(r.get("sms_envoye", False))
        new_df = pd.concat([core, totals], ignore_index=False).reset_index(drop=True)
        sauvegarder_donnees(new_df, get_palette())
        st.success("✅ Statuts Payé / SMS mis à jour.")
        st.rerun()

    if not totals.empty:
        show_tot = totals.copy()
        for c in ["date_arrivee","date_depart"]:
            show_tot[c] = show_tot[c].apply(format_date_str)
        st.caption("Lignes de totaux (non éditables) :")
        cols_tot = [
            "paye","nom_client","sms_envoye","plateforme","telephone",
            "date_arrivee","date_depart","nuitees",
            "prix_brut","commissions","frais_cb","prix_net",
            "menage","taxes_sejour","base","charges","%","AAAA","MM"
        ]
        cols_tot = [c for c in cols_tot if c in show_tot.columns]
        st.dataframe(show_tot[cols_tot], use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    st.caption("Saisie compacte (libellés inline)")
    palette = get_palette()

    def inline_input(label, widget_fn, key=None, **widget_kwargs):
        col1, col2 = st.columns([1,2])
        with col1:
            st.markdown(f"**{label}**")
        with col2:
            return widget_fn(label, key=key, label_visibility="collapsed", **widget_kwargs)

    paye = inline_input("Payé", st.checkbox, key="add_paye", value=False)
    nom = inline_input("Nom", st.text_input, key="add_nom", value="")
    sms_envoye = inline_input("SMS envoyé", st.checkbox, key="add_sms", value=False)

    tel = inline_input("Téléphone (+33...)", st.text_input, key="add_tel", value="")
    pf_options = sorted(palette.keys())
    pf_index = pf_options.index("Booking") if "Booking" in pf_options else 0
    plateforme = inline_input("Plateforme", st.selectbox, key="add_pf",
                              options=pf_options, index=pf_index)

    arrivee = inline_input("Arrivée", st.date_input, key="add_arrivee", value=date.today())
    min_dep = arrivee + timedelta(days=1)
    depart  = inline_input("Départ",  st.date_input, key="add_depart",
                           value=min_dep, min_value=min_dep)

    brut = inline_input("Prix brut (€)", st.number_input, key="add_brut",
                        min_value=0.0, step=1.0, format="%.2f")
    commissions = inline_input("Commissions (€)", st.number_input, key="add_comm",
                               min_value=0.0, step=1.0, format="%.2f")
    frais_cb = inline_input("Frais CB (€)", st.number_input, key="add_cb",
                            min_value=0.0, step=1.0, format="%.2f")

    net_calc = max(float(brut) - float(commissions) - float(frais_cb), 0.0)
    inline_input("Prix net (calculé)", st.number_input, key="add_net",
                 value=round(net_calc,2), step=0.01, format="%.2f", disabled=True)

    menage = inline_input("Ménage (€)", st.number_input, key="add_menage",
                          min_value=0.0, step=1.0, format="%.2f")
    taxes  = inline_input("Taxes séjour (€)", st.number_input, key="add_taxes",
                          min_value=0.0, step=1.0, format="%.2f")

    base_calc = max(net_calc - float(menage) - float(taxes), 0.0)
    charges_calc = max(float(brut) - net_calc, 0.0)
    pct_calc = (charges_calc / float(brut) * 100) if float(brut) > 0 else 0.0

    inline_input("Base (calculée)", st.number_input, key="add_base",
                 value=round(base_calc,2), step=0.01, format="%.2f", disabled=True)
    inline_input("Commission (%)", st.number_input, key="add_pct",
                 value=round(pct_calc,2), step=0.01, format="%.2f", disabled=True)

    if st.button("Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        ligne = {
            "paye": bool(paye),
            "nom_client": (nom or "").strip(),
            "sms_envoye": bool(sms_envoye),
            "plateforme": plateforme,
            "telephone": normalize_tel(tel),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": float(brut),
            "commissions": float(commissions),
            "frais_cb": float(frais_cb),
            "prix_net": round(net_calc, 2),
            "menage": float(menage),
            "taxes_sejour": float(taxes),
            "base": round(base_calc, 2),
            "charges": round(charges_calc, 2),
            "%": round(pct_calc, 2),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month,
            "ical_uid": ""
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        sauvegarder_donnees(df2, get_palette())
        st.success("✅ Réservation enregistrée")
        st.rerun()

def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune réservation.")
        return

    df["identifiant"] = df["nom_client"].astype(str) + " | " + df["date_arrivee"].apply(format_date_str)
    choix = st.selectbox("Choisir une réservation", df["identifiant"])
    idx = df.index[df["identifiant"] == choix]
    if len(idx) == 0:
        st.warning("Sélection invalide.")
        return
    i = idx[0]

    t0, t1, t2 = st.columns(3)
    paye = t0.checkbox("Payé", value=bool(df.at[i, "paye"]))
    nom = t1.text_input("Nom", df.at[i, "nom_client"])
    sms_envoye = t2.checkbox("SMS envoyé", value=bool(df.at[i, "sms_envoye"]))

    col = st.columns(2)
    tel = col[0].text_input("Téléphone", normalize_tel(df.at[i, "telephone"]))
    palette = get_palette()
    options_pf = sorted(palette.keys())
    cur_pf = df.at[i,"plateforme"]
    pf_index = options_pf.index(cur_pf) if cur_pf in options_pf else 0
    plateforme = col[1].selectbox("Plateforme", options_pf, index=pf_index)

    arrivee = st.date_input("Arrivée", df.at[i,"date_arrivee"] if isinstance(df.at[i,"date_arrivee"], date) else date.today())
    depart  = st.date_input("Départ",  df.at[i,"date_depart"] if isinstance(df.at[i,"date_depart"], date) else arrivee + timedelta(days=1), min_value=arrivee+timedelta(days=1))

    c1, c2, c3 = st.columns(3)
    brut = c1.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i,"prix_brut"]) if pd.notna(df.at[i,"prix_brut"]) else 0.0, step=1.0, format="%.2f")
    commissions = c2.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i,"commissions"]) if pd.notna(df.at[i,"commissions"]) else 0.0, step=1.0, format="%.2f")
    frais_cb = c3.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i,"frais_cb"]) if pd.notna(df.at[i,"frais_cb"]) else 0.0, step=1.0, format="%.2f")

    net_calc = max(brut - commissions - frais_cb, 0.0)

    d1, d2, d3 = st.columns(3)
    menage = d1.number_input("Ménage (€)", min_value=0.0, value=float(df.at[i,"menage"]) if pd.notna(df.at[i,"menage"]) else 0.0, step=1.0, format="%.2f")
    taxes  = d2.number_input("Taxes séjour (€)", min_value=0.0, value=float(df.at[i,"taxes_sejour"]) if pd.notna(df.at[i,"taxes_sejour"]) else 0.0, step=1.0, format="%.2f")
    base_calc = max(net_calc - menage - taxes, 0.0)

    charges_calc = max(brut - net_calc, 0.0)
    pct_calc = (charges_calc / brut * 100) if brut > 0 else 0.0
    d3.markdown(f"**Prix net (calculé)**: {net_calc:.2f} €  \n**Base (calculée)**: {base_calc:.2f} €  \n**%**: {pct_calc:.2f}")

    c_save, c_del = st.columns(2)
    if c_save.button("💾 Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        df.at[i,"paye"] = bool(paye)
        df.at[i,"nom_client"] = nom.strip()
        df.at[i,"sms_envoye"] = bool(sms_envoye)
        df.at[i,"plateforme"] = plateforme
        df.at[i,"telephone"]  = normalize_tel(tel)
        df.at[i,"date_arrivee"] = arrivee
        df.at[i,"date_depart"]  = depart
        df.at[i,"prix_brut"] = float(brut)
        df.at[i,"commissions"] = float(commissions)
        df.at[i,"