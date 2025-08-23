# app.py — Villa Tobias (COMPLET)
# - Onglet Plateformes (sauvé dans Excel, feuille `plateformes`)
# - Réservations : ajouter / modifier / supprimer
# - Calendrier mensuel coloré par plateforme (fond pastel)
# - Rapport avec KPI, Liste clients, SMS, Export ICS
# - Restauration & Téléchargement Excel robustes

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

st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def _palette_df_from_dict(pal: dict) -> pd.DataFrame:
    return pd.DataFrame(
        [{"plateforme": k, "couleur": v} for k, v in pal.items()],
        columns=["plateforme","couleur"]
    )

def _palette_dict_from_df(df: pd.DataFrame) -> dict:
    pal = {}
    if df is None or df.empty:
        return DEFAULT_PALETTE.copy()
    for _, r in df.iterrows():
        k = str(r.get("plateforme") or "").strip()
        v = str(r.get("couleur") or "").strip()
        if not k: 
            continue
        if not (isinstance(v, str) and v.startswith("#") and len(v) in (4,7)):
            v = "#999999"
        pal[k] = v
    return pal if pal else DEFAULT_PALETTE.copy()

def get_palette() -> dict:
    # priorité: session -> Excel.sheet `plateformes` -> défaut
    if "palette" in st.session_state and isinstance(st.session_state.palette, dict):
        return st.session_state.palette
    try:
        if os.path.exists(FICHIER):
            book = pd.read_excel(FICHIER, engine="openpyxl", sheet_name=None)
            pal_df = book.get("plateformes", None)
            pal = _palette_dict_from_df(pal_df)
            st.session_state.palette = pal
            return pal
    except Exception:
        pass
    st.session_state.palette = DEFAULT_PALETTE.copy()
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = {str(k): str(v) for k, v in palette.items() if k and v}

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

# ==============================  MAINTENANCE ==============================
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

# ==============================  OUTILS ==============================
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
    if s.endswith(".0"): s = s[:-2]
    return s

# ==============================  SCHEMA & CALCULS ==============================
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
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # nuitees
    df["nuitees"] = [
        (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
        for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
    ]
    # AAAA/MM
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
    if df is None or df.empty: return df, df
    mask = df.apply(is_total_row, axis=1)
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return df
    by = [c for c in ["date_arrivee","nom_client"] if c in df.columns]
    return df.sort_values(by=by, na_position="last").reset_index(drop=True)

# ==============================  EXCEL I/O ==============================
@st.cache_data(show_spinner=False)
def _read_excel_all(path: str, mtime: float):
    return pd.read_excel(path, engine="openpyxl", sheet_name=None)

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        book = _read_excel_all(FICHIER, mtime)
        df = book.get("Sheet1", None) or book.get("reservations", None) or pd.DataFrame()
        df = ensure_schema(df)
        # charger palette
        pal_df = book.get("plateformes", None)
        pal = _palette_dict_from_df(pal_df)
        save_palette(pal)
        return df
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def _force_telephone_text_format_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
    try:
        ws = writer.sheets.get(sheet_name) or writer.sheets.get('Sheet1', None)
        if ws is None or "telephone" not in df_to_save.columns: return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            row[0].number_format = '@'
    except Exception:
        pass

def _save_both_sheets(df: pd.DataFrame, palette: dict):
    df = ensure_schema(df)
    pal_df = _palette_df_from_dict(palette)
    with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
        _force_telephone_text_format_openpyxl(w, df, "Sheet1")
        pal_df.to_excel(w, index=False, sheet_name="plateformes")

def sauvegarder_donnees(df: pd.DataFrame):
    try:
        _save_both_sheets(df, get_palette())
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def sauvegarder_palette_seule():
    try:
        # recharger données puis sauver palette + données
        if os.path.exists(FICHIER):
            book = pd.read_excel(FICHIER, engine="openpyxl", sheet_name=None)
            df = book.get("Sheet1", None) or book.get("reservations", None) or pd.DataFrame()
            df = ensure_schema(df)
        else:
            df = ensure_schema(pd.DataFrame())
        _save_both_sheets(df, get_palette())
        st.cache_data.clear()
        st.success("🎨 Palette sauvegardée dans l’Excel.")
    except Exception as e:
        st.error(f"Échec sauvegarde palette : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            raw = up.read()
            if not raw: raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            book = pd.read_excel(bio, engine="openpyxl", sheet_name=None)
            df_new = book.get("Sheet1", None) or book.get("reservations", None) or pd.DataFrame()
            df_new = ensure_schema(df_new)
            pal_df = book.get("plateformes", None)
            pal = _palette_dict_from_df(pal_df)
            save_palette(pal)
            _save_both_sheets(df_new, pal)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    try:
        # exporter avec palette
        pal_df = _palette_df_from_dict(get_palette())
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            ensure_schema(df).to_excel(w, index=False, sheet_name="Sheet1")
            pal_df.to_excel(w, index=False, sheet_name="plateformes")
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
    )

# ==============================  ICS EXPORT ==============================
def _ics_escape(text: str) -> str:
    if text is None: return ""
    s = str(text).replace("\\","\\\\").replace(";","\\;").replace(",","\\,")
    return s.replace("\n","\\n")

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
    core, _ = split_totals(df)
    core = sort_core(core)
    lines = [
        "BEGIN:VCALENDAR","VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        f"X-WR-CALNAME:{_ics_escape(cal_name)}",
        "CALSCALE:GREGORIAN","METHOD:PUBLISH",
    ]
    for _, row in core.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)): continue
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
        "Merci de nous indiquer votre heure d'arrivée.\n\n"
        "Check-in à partir de 14h, check-out avant 11h.\n"
        "Une place de parking vous est allouée.\n\n"
        "Bon voyage et à très bientôt !\n"
        "Annick & Charley"
    )

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Merci d’avoir choisi notre appartement ! Nous espérons que votre séjour s’est bien passé.\n"
        "Au plaisir de vous accueillir à nouveau.\n\n"
        "Annick & Charley"
    )

# ==============================  UI HELPERS ==============================
def kpi_chips(df: pd.DataFrame):
    core, _ = split_totals(df)
    if core.empty: return
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

def lighten_color(hex_color: str, factor: float = 0.75) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16); g = int(hex_color[2:4], 16); b = int(hex_color[4:6], 16)
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    l = min(1.0, l + (1.0 - l) * factor)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"

def ideal_text_color(bg_hex: str) -> str:
    bg_hex = bg_hex.lstrip("#")
    r = int(bg_hex[0:2], 16); g = int(bg_hex[2:4], 16); b = int(bg_hex[4:6], 16)
    luminance = (0.299*r + 0.587*g + 0.114*b) / 255
    return "#000000" if luminance > 0.6 else "#ffffff"

# ==============================  VUES ==============================
def vue_reservations(df: pd.DataFrame):
    palette = get_palette()
    st.title("📋 Réservations")
    with st.expander("🎛️ Options d’affichage", expanded=True):
        filtre_paye = st.selectbox("Filtrer payé", ["Tous","Payé","Non payé"])
        show_kpi = st.checkbox("Afficher les totaux (KPI)", True)
        enable_search = st.checkbox("Activer la recherche", True)

    st.markdown("### Plateformes")
    if palette:
        badges = " &nbsp;&nbsp;".join([platform_badge(pf, palette) for pf in sorted(palette.keys())])
        st.markdown(badges, unsafe_allow_html=True)

    df = ensure_schema(df)
    if filtre_paye == "Payé": df = df[df["paye"] == True].copy()
    elif filtre_paye == "Non payé": df = df[df["paye"] == False].copy()
    if show_kpi: kpi_chips(df)

    if enable_search:
        q = st.text_input("🔎 Recherche (nom, plateforme, téléphone…)", "")
        if q:
            ql = q.strip().lower()
            def _match(v): s = "" if pd.isna(v) else str(v); return ql in s.lower()
            mask = (df["nom_client"].apply(_match) | df["plateforme"].apply(_match) | df["telephone"].apply(_match))
            df = df[mask].copy()

    core, totals = split_totals(df)
    core = sort_core(core)

    # ---- Ajout rapide / Modifier / Supprimer (boutons) ----
    st.subheader("Actions")
    c1, c2, c3 = st.columns(3)
    if c1.button("➕ Ajouter"):
        st.session_state._action = "add"
    if c2.button("✏️ Modifier"):
        st.session_state._action = "edit"
    if c3.button("🗑 Supprimer"):
        st.session_state._action = "del"

    action = st.session_state.get("_action", None)
    if action == "add":
        with st.form("add_form"):
            nom = st.text_input("Nom client")
            pf = st.selectbox("Plateforme", sorted(palette.keys()))
            tel = st.text_input("Téléphone")
            d1 = st.date_input("Arrivée", date.today())
            d2 = st.date_input("Départ", date.today() + timedelta(days=1), min_value=d1 + timedelta(days=1))
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=10.0)
            comm = st.number_input("Commissions (€)", min_value=0.0, step=1.0)
            cb   = st.number_input("Frais CB (€)", min_value=0.0, step=1.0)
            men  = st.number_input("Ménage (€)", min_value=0.0, step=1.0)
            tax  = st.number_input("Taxes séjour (€)", min_value=0.0, step=1.0)
            submit = st.form_submit_button("💾 Enregistrer")
        if submit:
            new_row = {
                "paye": False, "sms_envoye": False, "nom_client": nom, "plateforme": pf, "telephone": tel,
                "date_arrivee": d1, "date_depart": d2, "prix_brut": brut, "commissions": comm, "frais_cb": cb,
                "menage": men, "taxes_sejour": tax
            }
            df_full = charger_donnees()
            df_full = pd.concat([df_full, pd.DataFrame([new_row])], ignore_index=True)
            sauvegarder_donnees(df_full)
            st.success("✅ Réservation ajoutée.")
            st.session_state._action = None
            st.rerun()

    if action in ("edit","del"):
        core_full, _ = split_totals(charger_donnees())
        core_full = sort_core(core_full)
        if core_full.empty:
            st.info("Aucune réservation.")
        else:
            choix = st.selectbox("Choisir une réservation",
                                 core_full.index,
                                 format_func=lambda i: f"{core_full.at[i,'nom_client']} | {format_date_str(core_full.at[i,'date_arrivee'])}")
            if action == "edit":
                r = core_full.loc[choix]
                with st.form("edit_form"):
                    nom = st.text_input("Nom client", r["nom_client"])
                    pf = st.selectbox("Plateforme", sorted(palette.keys()),
                                      index=sorted(palette.keys()).index(r["plateforme"]) if r["plateforme"] in palette else 0)
                    tel = st.text_input("Téléphone", r["telephone"])
                    d1 = st.date_input("Arrivée", r["date_arrivee"] if isinstance(r["date_arrivee"], date) else date.today())
                    d2 = st.date_input("Départ", r["date_depart"] if isinstance(r["date_depart"], date) else d1 + timedelta(days=1),
                                       min_value=d1 + timedelta(days=1))
                    brut = st.number_input("Prix brut (€)", value=float(r["prix_brut"]))
                    comm = st.number_input("Commissions (€)", value=float(r["commissions"]))
                    cb   = st.number_input("Frais CB (€)", value=float(r["frais_cb"]))
                    men  = st.number_input("Ménage (€)", value=float(r["menage"]))
                    tax  = st.number_input("Taxes séjour (€)", value=float(r["taxes_sejour"]))
                    ok = st.form_submit_button("💾 Sauvegarder")
                if ok:
                    df_full = charger_donnees()
                    for col, val in {
                        "nom_client": nom, "plateforme": pf, "telephone": tel,
                        "date_arrivee": d1, "date_depart": d2,
                        "prix_brut": brut, "commissions": comm, "frais_cb": cb,
                        "menage": men, "taxes_sejour": tax
                    }.items():
                        df_full.at[choix, col] = val
                    sauvegarder_donnees(df_full)
                    st.success("✅ Modifié.")
                    st.session_state._action = None
                    st.rerun()
            else:  # del
                if st.button("Confirmer la suppression"):
                    df_full = charger_donnees()
                    df_full = df_full.drop(index=choix)
                    sauvegarder_donnees(df_full)
                    st.success("✅ Supprimé.")
                    st.session_state._action = None
                    st.rerun()

    # Affichage tableau
    show = core.copy()
    for c in ["date_arrivee","date_depart"]:
        show[c] = show[c].apply(format_date_str)
    cols = [c for c in [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees","prix_brut","commissions",
        "frais_cb","prix_net","menage","taxes_sejour","base","charges","%","AAAA","MM"
    ] if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)

    if not totals.empty:
        st.caption("Lignes de totaux :")
        tot = totals.copy()
        for c in ["date_arrivee","date_depart"]:
            tot[c] = tot[c].apply(format_date_str)
        st.dataframe(tot, use_container_width=True)

def vue_plateformes():
    st.title("🎨 Plateformes")
    pal = dict(sorted(get_palette().items(), key=lambda kv: kv[0].lower()))
    df_pal = _palette_df_from_dict(pal)
    st.markdown("Ajoutez, modifiez ou supprimez des plateformes. Les couleurs sont utilisées dans le calendrier et les pastilles.")
    edited = st.data_editor(
        df_pal,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn("Couleur (#RRGGBB)"),
        }
    )
    c1, c2 = st.columns(2)
    if c1.button("💾 Sauvegarder la palette"):
        new_pal = _palette_dict_from_df(edited)
        save_palette(new_pal)
        sauvegarder_palette_seule()
        st.rerun()
    if c2.button("↩️ Réinitialiser par défaut"):
        save_palette(DEFAULT_PALETTE.copy())
        sauvegarder_palette_seule()
        st.rerun()

def vue_calendrier(df: pd.DataFrame):
    palette = get_palette()
    st.title("📅 Calendrier mensuel (coloré par plateforme)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return
    cols = st.columns(2)
    mois_nom = cols[0].selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible."); return
    annee = cols[1].selectbox("Année", annees, index=len(annees)-1)
    mois_index = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(annee, mois_index)[1]
    jours = [date(annee, mois_index, j+1) for j in range(nb_jours)]
    core, _ = split_totals(df)
    planning = {j: [] for j in jours}
    for _, row in core.iterrows():
        d1 = row["date_arrivee"]; d2 = row["date_depart"]
        if not (isinstance(d1, date) and isinstance(d2, date)): continue
        pf = str(row["plateforme"] or "Autre")
        nom = str(row["nom_client"] or "")
        for j in jours:
            if d1 <= j < d2:
                planning[j].append((pf, nom))
    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    monthcal = calendar.monthcalendar(annee, mois_index)
    table, bg_table, fg_table = [], [], []
    for semaine in monthcal:
        row_text, row_bg, row_fg = [], [], []
        for jour in semaine:
            if jour == 0:
                row_text.append(""); row_bg.append("transparent"); row_fg.append(None)
            else:
                d = date(annee, mois_index, jour)
                items = planning.get(d, [])
                content_lines = [str(jour)] + [f"{nom}" for _, nom in items[:5]]
                if len(items) > 5:
                    content_lines.append(f"... (+{len(items)-5})")
                row_text.append("\n".join(content_lines))
                if items:
                    base = palette.get(items[0][0], "#999999")
                    bg = lighten_color(base, 0.75)
                    fg = ideal_text_color(bg)
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
            css.append(
                f"background-color:{bg};color:{fg};white-space:pre-wrap;"
                f"border:1px solid rgba(127,127,127,0.25);"
            )
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
    if df.empty:
        st.info("Aucune donnée."); return
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.info("Aucune année disponible."); return
    c1, c2, c3 = st.columns(3)
    annee = c1.selectbox("Année", annees, index=len(annees)-1)
    pf_opt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = c2.selectbox("Plateforme", pf_opt)
    mois_opt = ["Tous"] + [f"{i:02d}" for i in range(1,13)]
    mois_label = c3.selectbox("Mois", mois_opt)
    data = df[df["AAAA"] == int(annee)].copy()
    if pf != "Toutes": data = data[data["plateforme"] == pf]
    if mois_label != "Tous": data = data[data["MM"] == int(mois_label)]
    if data.empty:
        st.info("Aucune donnée pour ces filtres."); return

    detail = data.copy()
    for c in ["date_arrivee","date_depart"]:
        detail[c] = detail[c].apply(format_date_str)
    by = [c for c in ["date_arrivee","nom_client"] if c in detail.columns]
    if by: detail = detail.sort_values(by=by, na_position="last").reset_index(drop=True)
    cols_detail = [c for c in [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"
    ] if c in detail.columns]
    st.dataframe(detail[cols_detail], use_container_width=True)

    core, _ = split_totals(data)
    kpi_chips(core)

    stats = (
        data.groupby(["MM","plateforme"], dropna=True)
            .agg(prix_brut=("prix_brut","sum"),
                 prix_net=("prix_net","sum"),
                 base=("base","sum"),
                 charges=("charges","sum"),
                 nuitees=("nuitees","sum"))
            .reset_index()
    ).sort_values(["MM","plateforme"]).reset_index(drop=True)

    def bar_chart_metric(label, col):
        if stats.empty: return
        pvt = stats.pivot(index="MM", columns="plateforme", values=col).fillna(0).sort_index()
        pvt.index = [f"{int(m):02d}" for m in pvt.index]
        st.markdown(f"**{label}**")
        st.bar_chart(pvt)

    bar_chart_metric("Revenus bruts", "prix_brut")
    bar_chart_metric("Revenus nets", "prix_net")
    bar_chart_metric("Base", "base")
    bar_chart_metric("Nuitées", "nuitees")

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        detail[cols_detail].to_excel(writer, index=False)
    st.download_button(
        "⬇️ Télécharger le détail (XLSX)",
        data=buf.getvalue(),
        file_name=f"rapport_detail_{annee}{'' if mois_label=='Tous' else '_'+mois_label}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste des clients")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée."); return
    c1, c2 = st.columns(2)
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = c1.selectbox("Année", annees, index=len(annees)-1) if annees else None
    mois  = c2.selectbox("Mois", ["Tous"] + [f"{i:02d}" for i in range(1,13)])
    data = df.copy()
    if annee: data = data[data["AAAA"] == int(annee)]
    if mois != "Tous": data = data[data["MM"] == int(mois)]
    if data.empty:
        st.info("Aucune donnée pour cette période."); return
    data["prix_brut/nuit"] = data.apply(lambda r: round((r["prix_brut"]/r["nuitees"]) if r["nuitees"] else 0,2), axis=1)
    data["prix_net/nuit"]  = data.apply(lambda r: round((r["prix_net"]/r["nuitees"])  if r["nuitees"] else 0,2), axis=1)
    show = data.copy()
    for c in ["date_arrivee","date_depart"]:
        show[c] = show[c].apply(format_date_str)
    cols = [c for c in [
        "paye","nom_client","sms_envoye","plateforme","telephone","date_arrivee","date_depart",
        "nuitees","prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","prix_brut/nuit","prix_net/nuit"
    ] if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Télécharger (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

def vue_export_ics(df: pd.DataFrame):
    st.title("📤 Export ICS (Google Agenda – Import manuel)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée à exporter."); return
    c1, c2, c3 = st.columns(3)
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = c1.selectbox("Année", ["Toutes"] + annees, index=len(annees)) if annees else "Toutes"
    mois  = c2.selectbox("Mois", ["Tous"] + list(range(1,13)))
    pfopt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf    = c3.selectbox("Plateforme", pfopt)
    data = df.copy()
    if annee != "Toutes": data = data[data["AAAA"] == int(annee)]
    if mois != "Tous": data = data[data["MM"] == int(mois)]
    if pf != "Toutes": data = data[data["plateforme"] == pf]
    if data.empty:
        st.info("Aucune réservation pour ces filtres."); return
    ics_text = df_to_ics(data)
    st.download_button(
        "⬇️ Télécharger reservations.ics",
        data=ics_text.encode("utf-8"),
        file_name="reservations.ics",
        mime="text/calendar"
    )

def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS (envoi manuel)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée."); return
    today = date.today()
    demain = today + timedelta(days=1)
    hier = today - timedelta(days=1)
    colA, colB = st.columns(2)
    with colA:
        st.subheader("📆 Arrivées demain")
        arrives = df[df["date_arrivee"] == demain].copy()
        if arrives.empty:
            st.info("Aucune arrivée demain.")
        else:
            for _, r in arrives.reset_index(drop=True).iterrows():
                body = sms_message_arrivee(r)
                tel = normalize_tel(r.get("telephone"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                st.markdown(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}")
                st.markdown(f"Arrivée: {format_date_str(r.get('date_arrivee'))} • "
                            f"Départ: {format_date_str(r.get('date_depart'))} • "
                            f"Nuitées: {r.get('nuitees','')}")
                st.code(body)
                c1, c2 = st.columns(2)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                st.divider()
    with colB:
        st.subheader("🕒 Relance +24h après départ")
        dep_24h = df[df["date_depart"] == hier].copy()
        if dep_24h.empty:
            st.info("Aucun départ hier.")
        else:
            for _, r in dep_24h.reset_index(drop=True).iterrows():
                body = sms_message_depart(r)
                tel = normalize_tel(r.get("telephone"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                st.markdown(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}")
                st.code(body)
                c1, c2 = st.columns(2)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                st.divider()

    st.subheader("✍️ Composer un SMS manuel")
    df_pick = df.copy()
    df_pick["id_aff"] = df_pick["nom_client"].astype(str) + " | " + df_pick["plateforme"].astype(str) + " | " + df_pick["date_arrivee"].apply(format_date_str)
    choix = st.selectbox("Choisir une réservation", df_pick["id_aff"])
    r = df_pick.loc[df_pick["id_aff"] == choix].iloc[0]
    tel = normalize_tel(r.get("telephone"))
    choix_type = st.radio("Modèle de message",
                          ["Arrivée (demande d’heure)","Relance après départ","Message libre"],
                          horizontal=True)
    if choix_type == "Arrivée (demande d’heure)":
        body = sms_message_arrivee(r)
    elif choix_type == "Relance après départ":
        body = sms_message_depart(r)
    else:
        body = st.text_area("Votre message", value="", height=160, placeholder="Tapez votre SMS ici…")
    c1, c2 = st.columns(2)
    with c1: st.code(body or "—")
    if tel and body:
        c1, c2 = st.columns(2)
        c1.link_button(f"📞 Appeler {tel}", f"tel:{tel}")
        c2.link_button("📩 Envoyer SMS", f"sms:{tel}?&body={quote(body)}")
    else:
        st.info("Renseignez un téléphone et un message.")

# ==============================  APP ==============================
def main():
    st.sidebar.title("📁 Fichier")
    df_tmp = charger_donnees()
    bouton_telecharger(df_tmp)
    bouton_restaurer()
    render_cache_section_sidebar()

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","🎨 Plateformes","📅 Calendrier",
         "📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS"]
    )

    df = charger_donnees()

    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "🎨 Plateformes":
        vue_plateformes()
    elif onglet == "📅 Calendrier":
        vue_calendrier(df)
    elif onglet == "📊 Rapport":
        vue_rapport(df)
    elif onglet == "👥 Liste clients":
        vue_clients(df)
    elif onglet == "📤 Export ICS":
        vue_export_ics(df)
    elif onglet == "✉️ SMS":
        vue_sms(df)

if __name__ == "__main__":
    main()