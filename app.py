# app.py — Villa Tobias (COMPLET, robuste)
# - Fix "DataFrame is ambiguous" : jamais de if df ; on teste .empty / is None
# - Lecture Excel ultra-défensive : force openpyxl, gère dict de DataFrames, choisit Sheet1
# - Restauration via BytesIO
# - Feuille "Plateformes" (palette) optionnelle : nom|couleur
# - Tous les onglets + vidage cache

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
from typing import Tuple, Dict, Any

FICHIER = "reservations.xlsx"
SHEET_RESAS = "Sheet1"
SHEET_PLATF = "Plateformes"

st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# -------------------- utilitaires simples --------------------
def df_or_empty(obj: Any) -> pd.DataFrame:
    """Garantit un DataFrame à partir d'un read_excel qui peut rendre DF ou dict."""
    if isinstance(obj, pd.DataFrame):
        return obj
    if isinstance(obj, dict):
        if SHEET_RESAS in obj:
            return obj[SHEET_RESAS]
        # sinon première feuille
        for _, v in obj.items():
            if isinstance(v, pd.DataFrame):
                return v
    return pd.DataFrame()

def not_empty(x) -> bool:
    return isinstance(x, pd.DataFrame) and (not x.empty)

# -------------------- palette plateformes --------------------
DEFAULT_PALETTE = {"Booking": "#1e90ff", "Airbnb": "#e74c3c", "Autre": "#f59e0b"}

def _clean_palette_dict(d: dict) -> dict:
    out = {}
    for k, v in (d or {}).items():
        if isinstance(k, str) and isinstance(v, str) and k.strip() and v.startswith("#") and len(v) in (4,7):
            out[k.strip()] = v
    return out if out else DEFAULT_PALETTE.copy()

def _read_palette_from_excel(path: str) -> dict:
    try:
        if not os.path.exists(path):
            return DEFAULT_PALETTE.copy()
        xls = pd.ExcelFile(path, engine="openpyxl")
        if SHEET_PLATF not in xls.sheet_names:
            return DEFAULT_PALETTE.copy()
        dfp_raw = pd.read_excel(xls, sheet_name=SHEET_PLATF, engine="openpyxl")
        dfp = df_or_empty(dfp_raw)
        if dfp.empty:
            return DEFAULT_PALETTE.copy()
        cols = {c.lower(): c for c in dfp.columns}
        if "plateforme" not in cols or "couleur" not in cols:
            return DEFAULT_PALETTE.copy()
        pal = dict(zip(dfp[cols["plateforme"]].astype(str), dfp[cols["couleur"]].astype(str)))
        return _clean_palette_dict(pal)
    except Exception:
        return DEFAULT_PALETTE.copy()

def _write_palette_to_excel(writer, palette: dict):
    pal = _clean_palette_dict(palette)
    pd.DataFrame(sorted(pal.items()), columns=["plateforme","couleur"]).to_excel(
        writer, index=False, sheet_name=SHEET_PLATF
    )

def get_palette() -> dict:
    if "palette" in st.session_state:
        return _clean_palette_dict(st.session_state.palette)
    pal = _read_palette_from_excel(FICHIER)
    st.session_state.palette = pal.copy()
    return pal

def save_palette(palette: dict):
    st.session_state.palette = _clean_palette_dict(palette)

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (f'<span style="display:inline-block;width:0.9em;height:0.9em;'
            f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}')

# -------------------- maintenance --------------------
def render_cache_section_sidebar():
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache et relancer"):
        try: st.cache_data.clear()
        except Exception: pass
        try: st.cache_resource.clear()
        except Exception: pass
        st.sidebar.success("Cache vidé. Redémarrage…")
        st.rerun()

# -------------------- outils champs --------------------
def to_date_only(x):
    if pd.isna(x) or x is None: return None
    try: return pd.to_datetime(x).date()
    except Exception: return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)): return ""
    s = str(x).strip().replace(" ","")
    if s.endswith(".0"): s = s[:-2]
    return s

# -------------------- schema & calculs --------------------
BASE_COLS = [
    "paye","nom_client","sms_envoye","plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%","AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None: df = pd.DataFrame()
    df = df_or_empty(df).copy()

    # colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    # types
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee","date_depart"]: df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["nuitees"] = [(d2-d1).days if (isinstance(d1,date) and isinstance(d2,date)) else np.nan
                     for d1,d2 in zip(df["date_arrivee"], df["date_depart"])]

    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d,date) else np.nan).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d,date) else np.nan).astype("Int64")

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
    no_dates = not isinstance(d1,date) and not isinstance(d2,date)
    has_money = any(pd.notna(row.get(c)) and float(row.get(c) or 0) != 0
                    for c in ["prix_brut","prix_net","base","charges"])
    return name_is_total or pf_is_total or (no_dates and has_money)

def split_totals(df: pd.DataFrame):
    if df is None or df.empty: return df, df
    mask = df.apply(is_total_row, axis=1)
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return df
    by = [c for c in ["date_arrivee","nom_client"] if c in df.columns]
    return df.sort_values(by=by, na_position="last").reset_index(drop=True)

# -------------------- Excel I/O --------------------
@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float) -> pd.DataFrame:
    try:
        obj = pd.read_excel(path, engine="openpyxl", sheet_name=SHEET_RESAS,
                            converters={"telephone": normalize_tel})
        return df_or_empty(obj)
    except Exception:
        # Si l’utilisateur a changé la feuille, tente lecture générale
        obj = pd.read_excel(path, engine="openpyxl", sheet_name=None,
                            converters={"telephone": normalize_tel})
        return df_or_empty(obj)

def _read_full_excel(path: str) -> Tuple[pd.DataFrame, Dict[str,str]]:
    df_resa = ensure_schema(pd.DataFrame())
    pal = DEFAULT_PALETTE.copy()
    if not os.path.exists(path):
        return df_resa, pal
    try:
        xls = pd.ExcelFile(path, engine="openpyxl")
        # Réservations
        if SHEET_RESAS in xls.sheet_names:
            obj = pd.read_excel(xls, sheet_name=SHEET_RESAS, engine="openpyxl",
                                converters={"telephone": normalize_tel})
            df_resa = ensure_schema(df_or_empty(obj))
        else:
            obj = pd.read_excel(xls, sheet_name=None, engine="openpyxl",
                                converters={"telephone": normalize_tel})
            df_resa = ensure_schema(df_or_empty(obj))
        # Plateformes
        pal = _read_palette_from_excel(path)
        return df_resa, pal
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {type(e).__name__}: {e}")
        return df_resa, pal

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime)
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {type(e).__name__}: {e}")
        return ensure_schema(pd.DataFrame())

def _force_telephone_text_format_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
    try:
        ws = writer.sheets.get(sheet_name) or writer.sheets.get(SHEET_RESAS, None)
        if ws is None or "telephone" not in df_to_save.columns: return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            row[0].number_format = '@'
    except Exception:
        pass

def sauvegarder_donnees(df: pd.DataFrame, palette: dict = None):
    df = ensure_schema(df)
    core, totals = split_totals(df); core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name=SHEET_RESAS)
            _force_telephone_text_format_openpyxl(w, out, SHEET_RESAS)
            pal = palette if isinstance(palette, dict) else get_palette()
            _write_palette_to_excel(w, pal)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {type(e).__name__}: {e}")

def bouton_restaurer():
    st.sidebar.markdown("### 🔁 Restaurer un fichier XLSX")
    up = st.sidebar.file_uploader("Choisir un fichier .xlsx", type=["xlsx"])
    if up is not None:
        try:
            raw = up.read()
            if not raw: raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            xls = pd.ExcelFile(bio, engine="openpyxl")
            # Réservations
            if SHEET_RESAS in xls.sheet_names:
                obj = pd.read_excel(xls, sheet_name=SHEET_RESAS, engine="openpyxl",
                                    converters={"telephone": normalize_tel})
                df_new = ensure_schema(df_or_empty(obj))
            else:
                obj = pd.read_excel(xls, sheet_name=None, engine="openpyxl",
                                    converters={"telephone": normalize_tel})
                df_new = ensure_schema(df_or_empty(obj))
            # Plateformes
            pal_new = DEFAULT_PALETTE.copy()
            if SHEET_PLATF in xls.sheet_names:
                dfp = df_or_empty(pd.read_excel(xls, sheet_name=SHEET_PLATF, engine="openpyxl"))
                if not dfp.empty:
                    cols = {c.lower(): c for c in dfp.columns}
                    if "plateforme" in cols and "couleur" in cols:
                        pal_new = dict(zip(dfp[cols["plateforme"]].astype(str), dfp[cols["couleur"]].astype(str)))
                        pal_new = _clean_palette_dict(pal_new)
            save_palette(pal_new)
            sauvegarder_donnees(df_new, pal_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {type(e).__name__}: {e}")

def bouton_telecharger(df: pd.DataFrame):
    st.sidebar.markdown("### 💾 Télécharger une copie XLSX")
    buf = BytesIO(); data = b""
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            ensure_schema(df).to_excel(w, index=False, sheet_name=SHEET_RESAS)
            _force_telephone_text_format_openpyxl(w, ensure_schema(df), SHEET_RESAS)
            _write_palette_to_excel(w, get_palette())
        data = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {type(e).__name__}: {e}")
        data = b""
    st.sidebar.download_button(
        "Télécharger reservations.xlsx",
        data=data,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data) == 0),
    )

# -------------------- ICS --------------------
def _ics_escape(text: str) -> str:
    if text is None: return ""
    s = str(text).replace("\\","\\\\").replace(";","\\;").replace(",","\\,")
    return s.replace("\n","\\n")

def _fmt_date_ics(d: date) -> str: return d.strftime("%Y%m%d")
def _dtstamp_utc_now() -> str: return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def _stable_uid(nom_client, plateforme, d1, d2, tel, salt="v1"):
    base = f"{nom_client}|{plateforme}|{d1}|{d2}|{tel}|{salt}"
    return f"vt-{hashlib.sha1(base.encode('utf-8')).hexdigest()}@villatobias"

def df_to_ics(df: pd.DataFrame, cal_name: str = "Villa Tobias – Réservations") -> str:
    df = ensure_schema(df)
    core, _ = split_totals(df); core = sort_core(core)
    lines = [
        "BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR",
        f"X-WR-CALNAME:{_ics_escape(cal_name)}","CALSCALE:GREGORIAN","METHOD:PUBLISH",
    ]
    if core.empty:
        lines.append("END:VCALENDAR"); return "\r\n".join(lines) + "\r\n"
    for _, row in core.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        if not (isinstance(d1,date) and isinstance(d2,date)): continue
        plateforme = str(row.get("plateforme") or "").strip()
        nom_client = str(row.get("nom_client") or "").strip()
        tel = str(row.get("telephone") or "").strip()
        brut = float(row.get("prix_brut") or 0); net = float(row.get("prix_net") or 0)
        nuitees = int(row.get("nuitees") or ((d2-d1).days))
        summary = " - ".join([x for x in [plateforme, nom_client, tel] if x])
        desc = (f"Plateforme: {plateforme}\\nClient: {nom_client}\\nTéléphone: {tel}\\n"
                f"Arrivee: {d1.strftime('%Y/%m/%d')}\\nDepart: {d2.strftime('%Y/%m/%d')}\\n"
                f"Nuitees: {nuitees}\\nBrut: {brut:.2f} €\\nNet: {net:.2f} €")
        uid_existing = str(row.get("ical_uid") or "").strip()
        uid = uid_existing if uid_existing else _stable_uid(nom_client, plateforme, d1, d2, tel, "v1")
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

# -------------------- SMS --------------------
def sms_message_arrivee(row: pd.Series) -> str:
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    d1s = d1.strftime("%Y/%m/%d") if isinstance(d1,date) else ""
    d2s = d2.strftime("%Y/%m/%d") if isinstance(d2,date) else ""
    nuitees = int(row.get("nuitees") or ((d2-d1).days if isinstance(d1,date) and isinstance(d2,date) else 0))
    plateforme = str(row.get("plateforme") or "")
    nom = str(row.get("nom_client") or "")
    tel_aff = str(row.get("telephone") or "").strip()
    return ("VILLA TOBIAS\n"
            f"Plateforme : {plateforme}\n"
            f"Date d'arrivee : {d1s}  Date depart : {d2s}  Nombre de nuitees : {nuitees}\n\n"
            f"Bonjour {nom}\n"
            f"Telephone : {tel_aff}\n\n"
            "Bienvenue chez nous !\n\n"
            "Check-in à partir de 14h, check-out au plus tard 11h.\n\n"
            "Nous vous souhaitons un excellent voyage.\n\n"
            "Annick & Charley")

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (f"Bonjour {nom},\n\n"
            "Merci pour votre séjour ! Au plaisir de vous accueillir à nouveau.\n\n"
            "Annick & Charley")

# -------------------- UI helpers --------------------
def kpi_chips(df: pd.DataFrame):
    core, _ = split_totals(df)
    if core.empty: return
    b = core["prix_brut"].sum(); n = core["prix_net"].sum()
    base = core["base"].sum()
    ch = core["commissions"].sum() + core["frais_cb"].sum()
    nuits = core["nuitees"].sum()
    pct = (ch/b*100) if b else 0; pm_nuit = (b/nuits) if nuits else 0
    html = f"""
    <style>
    .chips-wrap {{ display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 10px 0; }}
    .chip {{ padding:8px 10px; border-radius:10px; background: rgba(127,127,127,0.12); border:1px solid rgba(127,127,127,0.25); font-size:0.9rem; }}
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
    if not q: return df
    ql = q.strip().lower()
    def _match(v):
        s = "" if pd.isna(v) else str(v)
        return ql in s.lower()
    mask = (df["nom_client"].apply(_match) |
            df["plateforme"].apply(_match) |
            df["telephone"].apply(_match))
    return df[mask].copy()

# -------------------- VUES --------------------
def vue_reservations(df: pd.DataFrame):
    palette = get_palette()
    st.title("📋 Réservations")
    with st.expander("🎛️ Options d’affichage", expanded=True):
        filtre_paye = st.selectbox("Filtrer payé", ["Tous","Payé","Non payé"])
        show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)
    if isinstance(palette, dict) and len(palette) > 0:
        badges = " &nbsp;&nbsp;".join([platform_badge(pf, palette) for pf in sorted(palette.keys())])
        st.markdown(badges, unsafe_allow_html=True)

    df = ensure_schema(df)
    if filtre_paye == "Payé": df = df[df["paye"] == True].copy()
    elif filtre_paye == "Non payé": df = df[df["paye"] == False].copy()
    if show_kpi: kpi_chips(df)
    if enable_search: df = search_box(df)

    core, totals = split_totals(df); core = sort_core(core)
    core_edit = core.copy()
    core_edit["__rowid"] = core_edit.index
    core_edit["date_arrivee"] = core_edit["date_arrivee"].apply(format_date_str)
    core_edit["date_depart"]  = core_edit["date_depart"].apply(format_date_str)

    cols_order = ["paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees","prix_brut","commissions","frais_cb","prix_net",
        "menage","taxes_sejour","base","charges","%","AAAA","MM","__rowid"]
    cols_show = [c for c in cols_order if c in core_edit.columns]

    edited = st.data_editor(
        core_edit[cols_show], use_container_width=True, hide_index=True,
        column_config={
            "paye": st.column_config.CheckboxColumn("Payé"),
            "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
            "__rowid": st.column_config.Column("id", help="Interne", disabled=True, width="small"),
            "date_arrivee": st.column_config.TextColumn("date_arrivee", disabled=True),
            "date_depart":  st.column_config.TextColumn("date_depart",  disabled=True),
            "nom_client":   st.column_config.TextColumn("nom_client",   disabled=True),
            "plateforme":   st.column_config.TextColumn("plateforme",   disabled=True),
            "telephone":    st.column_config.TextColumn("telephone",    disabled=True),
            "nuitees":      st.column_config.NumberColumn("nuitees",    disabled=True),
            "prix_brut":    st.column_config.NumberColumn("prix_brut",  disabled=True),
            "commissions":  st.column_config.NumberColumn("commissions", disabled=True),
            "frais_cb":     st.column_config.NumberColumn("frais_cb",   disabled=True),
            "prix_net":     st.column_config.NumberColumn("prix_net",   disabled=True),
            "menage":       st.column_config.NumberColumn("menage",     disabled=True),
            "taxes_sejour": st.column_config.NumberColumn("taxes_sejour",disabled=True),
            "base":         st.column_config.NumberColumn("base",       disabled=True),
            "charges":      st.column_config.NumberColumn("charges",    disabled=True),
            "%":            st.column_config.NumberColumn("%",          disabled=True),
            "AAAA":         st.column_config.NumberColumn("AAAA",       disabled=True),
            "MM":           st.column_config.NumberColumn("MM",         disabled=True),
        }
    )

    c1, _ = st.columns([1,3])
    if c1.button("💾 Enregistrer les cases cochées"):
        for _, r in edited.iterrows():
            ridx = int(r["__rowid"])
            core.at[ridx,"paye"] = bool(r.get("paye", False))
            core.at[ridx,"sms_envoye"] = bool(r.get("sms_envoye", False))
        new_df = pd.concat([core, totals], ignore_index=False).reset_index(drop=True)
        sauvegarder_donnees(new_df, get_palette())
        st.success("✅ Statuts Payé / SMS mis à jour.")
        st.rerun()

    if not totals.empty:
        show_tot = totals.copy()
        for c in ["date_arrivee","date_depart"]:
            show_tot[c] = show_tot[c].apply(format_date_str)
        st.caption("Lignes de totaux (non éditables) :")
        cols_tot = ["paye","nom_client","sms_envoye","plateforme","telephone",
            "date_arrivee","date_depart","nuitees","prix_brut","commissions","frais_cb","prix_net",
            "menage","taxes_sejour","base","charges","%","AAAA","MM"]
        cols_tot = [c for c in cols_tot if c in show_tot.columns]
        st.dataframe(show_tot[cols_tot], use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    st.caption("Saisie compacte (libellés inline)")
    palette = get_palette()

    def inline_input(label, widget_fn, key=None, **kwargs):
        col1, col2 = st.columns([1,2])
        with col1: st.markdown(f"**{label}**")
        with col2: return widget_fn(label, key=key, label_visibility="collapsed", **kwargs)

    paye = inline_input("Payé", st.checkbox, key="add_paye", value=False)
    nom = inline_input("Nom", st.text_input, key="add_nom", value="")
    sms_envoye = inline_input("SMS envoyé", st.checkbox, key="add_sms", value=False)
    tel = inline_input("Téléphone (+33...)", st.text_input, key="add_tel", value="")
    pf_options = sorted(palette.keys()) if isinstance(palette, dict) else ["Booking","Airbnb","Autre"]
    pf_index = pf_options.index("Booking") if "Booking" in pf_options else 0
    plateforme = inline_input("Plateforme", st.selectbox, key="add_pf", options=pf_options, index=pf_index)
    arrivee = inline_input("Arrivée", st.date_input, key="add_arrivee", value=date.today())
    min_dep = arrivee + timedelta(days=1)
    depart  = inline_input("Départ",  st.date_input, key="add_depart", value=min_dep, min_value=min_dep)
    brut = inline_input("Prix brut (€)", st.number_input, key="add_brut", min_value=0.0, step=1.0, format="%.2f")
    commissions = inline_input("Commissions (€)", st.number_input, key="add_comm", min_value=0.0, step=1.0, format="%.2f")
    frais_cb = inline_input("Frais CB (€)", st.number_input, key="add_cb", min_value=0.0, step=1.0, format="%.2f")

    net_calc = max(float(brut) - float(commissions) - float(frais_cb), 0.0)
    inline_input("Prix net (calculé)", st.number_input, key="add_net", value=round(net_calc,2), step=0.01, format="%.2f", disabled=True)
    menage = inline_input("Ménage (€)", st.number_input, key="add_menage", min_value=0.0, step=1.0, format="%.2f")
    taxes  = inline_input("Taxes séjour (€)", st.number_input, key="add_taxes", min_value=0.0, step=1.0, format="%.2f")
    base_calc = max(net_calc - float(menage) - float(taxes), 0.0)
    charges_calc = max(float(brut) - net_calc, 0.0)
    pct_calc = (charges_calc / float(brut) * 100) if float(brut) > 0 else 0.0
    inline_input("Base (calculée)", st.number_input, key="add_base", value=round(base_calc,2), step=0.01, format="%.2f", disabled=True)
    inline_input("Commission (%)", st.number_input, key="add_pct", value=round(pct_calc,2), step=0.01, format="%.2f", disabled=True)

    if st.button("Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        ligne = {
            "paye": bool(paye), "nom_client": (nom or "").strip(), "sms_envoye": bool(sms_envoye),
            "plateforme": plateforme, "telephone": normalize_tel(tel),
            "date_arrivee": arrivee, "date_depart": depart,
            "prix_brut": float(brut), "commissions": float(commissions), "frais_cb": float(frais_cb),
            "prix_net": round(net_calc,2), "menage": float(menage), "taxes_sejour": float(taxes),
            "base": round(base_calc,2), "charges": round(charges_calc,2), "%": round(pct_calc,2),
            "nuitees": (depart-arrivee).days, "AAAA": arrivee.year, "MM": arrivee.month, "ical_uid": ""
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        sauvegarder_donnees(df2, get_palette())
        st.success("✅ Réservation enregistrée")
        st.rerun()

def vue_modifier_supprimer(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune réservation."); return
    df["identifiant"] = df["nom_client"].astype(str) + " | " + df["date_arrivee"].apply(format_date_str)
    choix = st.selectbox("Choisir une réservation", df["identifiant"])
    idx = df.index[df["identifiant"] == choix]
    if len(idx) == 0:
        st.warning("Sélection invalide."); return
    i = idx[0]

    t0, t1, t2 = st.columns(3)
    paye = t0.checkbox("Payé", value=bool(df.at[i,"paye"]))
    nom = t1.text_input("Nom", df.at[i,"nom_client"])
    sms_envoye = t2.checkbox("SMS envoyé", value=bool(df.at[i,"sms_envoye"]))

    col = st.columns(2)
    tel = col[0].text_input("Téléphone", normalize_tel(df.at[i,"telephone"]))
    options_pf = sorted(get_palette().keys())
    cur_pf = str(df.at[i,"plateforme"])
    pf_index = options_pf.index(cur_pf) if cur_pf in options_pf else 0
    plateforme = col[1].selectbox("Plateforme", options_pf, index=pf_index)

    arrivee = st.date_input("Arrivée", df.at[i,"date_arrivee"] if isinstance(df.at[i,"date_arrivee"],date) else date.today())
    depart  = st.date_input("Départ",  df.at[i,"date_depart"] if isinstance(df.at[i,"date_depart"],date) else arrivee+timedelta(days=1),
                            min_value=arrivee+timedelta(days=1))

    c1,c2,c3 = st.columns(3)
    brut = c1.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i,"prix_brut"]) if pd.notna(df.at[i,"prix_brut"]) else 0.0, step=1.0, format="%.2f")
    commissions = c2.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i,"commissions"]) if pd.notna(df.at[i,"commissions"]) else 0.0, step=1.0, format="%.2f")
    frais_cb = c3.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i,"frais_cb"]) if pd.notna(df.at[i,"frais_cb"]) else 0.0, step=1.0, format="%.2f")

    net_calc = max(brut - commissions - frais_cb, 0.0)
    d1,d2,d3 = st.columns(3)
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
        df.at[i,"frais_cb"] = float(frais_cb)
        df.at[i,"prix_net"]  = round(net_calc,2)
        df.at[i,"menage"] = float(menage)
        df.at[i,"taxes_sejour"] = float(taxes)
        df.at[i,"base"] = round(base_calc,2)
        df.at[i,"charges"] = round(charges_calc,2)
        df.at[i,"%"] = round(pct_calc,2)
        df.at[i,"nuitees"] = (depart-arrivee).days
        df.at[i,"AAAA"] = arrivee.year
        df.at[i,"MM"]   = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df, get_palette())
        st.success("✅ Modifié")
        st.rerun()

    if c_del.button("🗑 Supprimer"):
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2, get_palette())
        st.warning("Supprimé.")
        st.rerun()

# --- calendrier ---
def lighten_color(hex_color: str, factor: float = 0.75) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2],16); g = int(hex_color[2:4],16); b = int(hex_color[4:6],16)
    h,l,s = colorsys.rgb_to_hls(r/255,g/255,b/255); l = min(1.0, l + (1.0-l)*factor)
    r2,g2,b2 = colorsys.hls_to_rgb(h,l,s)
    return f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"

def ideal_text_color(bg_hex: str) -> str:
    bg_hex = bg_hex.lstrip("#")
    r = int(bg_hex[0:2],16); g = int(bg_hex[2:4],16); b = int(bg_hex[4:6],16)
    luminance = (0.299*r + 0.587*g + 0.114*b)/255
    return "#000000" if luminance > 0.6 else "#ffffff"

def vue_calendrier(df: pd.DataFrame):
    palette = get_palette()
    st.title("📅 Calendrier mensuel (coloré par plateforme)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée."); return

    cols = st.columns(2)
    mois_nom = cols[0].selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if len(annees) == 0:
        st.warning("Aucune année disponible."); return
    annee = cols[1].selectbox("Année", annees, index=len(annees)-1)

    mois_index = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(annee, mois_index)[1]
    jours = [date(annee, mois_index, j+1) for j in range(nb_jours)]

    core, _ = split_totals(df)
    planning = {j: [] for j in jours}
    for _, row in core.iterrows():
        d1 = row["date_arrivee"]; d2 = row["date_depart"]
        if not (isinstance(d1,date) and isinstance(d2,date)): continue
        pf = str(row["plateforme"] or "Autre"); nom = str(row["nom_client"] or "")
        for j in jours:
            if d1 <= j < d2:
                planning[j].append((pf, nom))

    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    monthcal = calendar.monthcalendar(annee, mois_index)

    table = []; bg_table = []; fg_table = []
    for semaine in monthcal:
        row_text = []; row_bg = []; row_fg = []
        for jour in semaine:
            if jour == 0:
                row_text.append(""); row_bg.append("transparent"); row_fg.append(None)
            else:
                d = date(annee, mois_index, jour)
                items = planning.get(d, [])
                if len(items) > 5:
                    content_lines = [str(jour)] + [f"{nom}" for _, nom in items[:5]] + [f"... (+{len(items)-5})"]
                else:
                    content_lines = [str(jour)] + [f"{nom}" for _, nom in items]
                row_text.append("\n".join(content_lines))
                if items:
                    base = palette.get(items[0][0], "#999999")
                    bg = lighten_color(base, 0.75); fg = ideal_text_color(bg)
                else:
                    bg = "transparent"; fg = None
                row_bg.append(bg); row_fg.append(fg)
        table.append(row_text); bg_table.append(row_bg); fg_table.append(row_fg)

    df_table = pd.DataFrame(table, columns=headers)

    def style_row(vals, row_idx):
        css = []
        for col_idx, _ in enumerate(vals):
            bg = bg_table[row_idx][col_idx]
            fg = fg_table[row_idx][col_idx] or "inherit"
            css.append(f"background-color:{bg};color:{fg};white-space:pre-wrap;border:1px solid rgba(127,127,127,0.25);")
        return css

    styler = df_table.style
    for r in range(df_table.shape[0]):
        styler = styler.apply(lambda v, r=r: style_row(v, r), axis=1)

    st.caption("Légende :")
    leg = " • ".join([
        f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{get_palette()[p]};margin-right:6px;border-radius:3px;"></span>{p}'
        for p in sorted(get_palette().keys())
    ])
    st.markdown(leg, unsafe_allow_html=True)
    st.dataframe(styler, use_container_width=True, height=450)

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport (détaillé)")
    df = ensure_schema(df)
    if df.empty: st.info("Aucune donnée."); return
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if len(annees) == 0: st.info("Aucune année disponible."); return
    c1,c2,c3 = st.columns(3)
    annee = c1.selectbox("Année", annees, index=len(annees)-1)
    pf_opt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = c2.selectbox("Plateforme", pf_opt)
    mois_opt = ["Tous"] + [f"{i:02d}" for i in range(1,13)]
    mois_label = c3.selectbox("Mois", mois_opt)

    data = df[df["AAAA"] == int(annee)].copy()
    if pf != "Toutes": data = data[data["plateforme"] == pf]
    if mois_label != "Tous": data = data[data["MM"] == int(mois_label)]
    if data.empty: st.info("Aucune donnée pour ces filtres."); return

    detail = data.copy()
    for c in ["date_arrivee","date_depart"]: detail[c] = detail[c].apply(format_date_str)
    by = [c for c in ["date_arrivee","nom_client"] if c in detail.columns]
    if by: detail = detail.sort_values(by=by, na_position="last").reset_index(drop=True)

    cols_detail = ["paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees","prix_brut","commissions","frais_cb","prix_net",
        "menage","taxes_sejour","base","charges","%"]
    cols_detail = [c for c in cols_detail if c in detail.columns]
    st.dataframe(detail[cols_detail], use_container_width=True)

    core, _ = split_totals(data); kpi_chips(core)

    stats = (data.groupby(["MM","plateforme"], dropna=True)
             .agg(prix_brut=("prix_brut","sum"), prix_net=("prix_net","sum"),
                  base=("base","sum"), charges=("charges","sum"), nuitees=("nuitees","sum"))
             .reset_index()).sort_values(["MM","plateforme"]).reset_index(drop=True)

    def bar_chart_metric(label, col):
        if stats.empty: return
        pvt = stats.pivot(index="MM", columns="plateforme", values=col).fillna(0).sort_index()
        pvt.index = [f"{int(m):02d}" for m in pvt.index]
        st.markdown(f"**{label}**"); st.bar_chart(pvt)

    bar_chart_metric("Revenus bruts", "prix_brut")
    bar_chart_metric("Revenus nets", "prix_net")
    bar_chart_metric("Base", "base")
    bar_chart_metric("Nuitées", "nuitees")

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        detail[cols_detail].to_excel(writer, index=False, sheet_name="detail")
    st.download_button("⬇️ Télécharger le détail (XLSX)", data=buf.getvalue(),
                       file_name=f"rapport_detail_{annee}{'' if mois_label=='Tous' else '_'+mois_label}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste des clients")
    df = ensure_schema(df)
    if df