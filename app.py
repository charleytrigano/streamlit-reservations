# app.py — Villa Tobias (COMPLET + Calendrier coloré + Ajout plateformes)
# - Filtre payé OK
# - Palette plateformes éditable (ajout rapide) + badges
# - Calendrier type grille avec pastilles colorées et légende
# - Réservations éditables (paye / sms_envoye), Ajouter, Modifier, Rapport, Clients, Export ICS, SMS
# - Sauvegarde/Restaurer xlsx + vider cache

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
import json
from urllib.parse import quote

FICHIER = "reservations.xlsx"
PALETTE_FILE = "palette.json"

# ==============================  UTIL PALETTE  ==============================

DEFAULT_PALETTE = {
    "Booking": "#3b82f6",  # blue
    "Airbnb":  "#22c55e",  # green
    "Autre":   "#f97316",  # orange
}

def load_palette() -> dict:
    pal = DEFAULT_PALETTE.copy()
    try:
        if os.path.exists(PALETTE_FILE):
            with open(PALETTE_FILE, "r", encoding="utf-8") as f:
                user_pal = json.load(f)
            pal.update(user_pal or {})
    except Exception:
        pass
    # session copy
    if "palette" not in st.session_state:
        st.session_state["palette"] = pal
    return st.session_state["palette"]

def save_palette(pal: dict):
    try:
        with open(PALETTE_FILE, "w", encoding="utf-8") as f:
            json.dump(pal, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    st.session_state["palette"] = pal

def get_palette() -> dict:
    return load_palette()

def set_platform_color(name: str, color: str):
    pal = get_palette().copy()
    pal[name] = color
    save_palette(pal)

def platform_color(name: str) -> str:
    pal = get_palette()
    if name in pal:
        return pal[name]
    # attribue une couleur par défaut si nouvelle plateforme
    set_platform_color(name, "#a855f7")  # violet par défaut
    return "#a855f7"

def platform_badge(name: str) -> str:
    c = platform_color(name)
    txt = name.replace("<","&lt;").replace(">","&gt;")
    return f'''<span style="display:inline-flex;align-items:center;gap:6px;
        padding:4px 8px;border-radius:999px;border:1px solid rgba(0,0,0,.08);
        background:rgba(0,0,0,.03);font-size:0.9rem;margin:2px 6px 2px 0;">
        <span style="width:10px;height:10px;border-radius:50%;background:{c};display:inline-block;"></span>
        {txt}
    </span>'''

def add_platform_inline():
    st.markdown("#### ➕ Ajouter une plateforme")
    col1, col2, col3 = st.columns([2,1,1])
    with col1:
        new_name = st.text_input("Nom de la plateforme", key="pf_new_name", placeholder="Ex: Abritel, VRBO, Direct…")
    with col2:
        new_color = st.color_picker("Couleur", value="#a855f7", key="pf_new_color")
    with col3:
        st.write("")
        st.write("")
        if st.button("Ajouter", key="pf_add_btn"):
            name = (new_name or "").strip()
            if not name:
                st.warning("Entrez un nom de plateforme.")
            else:
                set_platform_color(name, new_color)
                st.success(f"Plateforme « {name} » ajoutée.")
                st.rerun()

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
    """Force la lecture du téléphone en TEXTE, retire .0 éventuel, espaces, et garde le +."""
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

# ==============================  EXCEL I/O  ==============================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path, converters={"telephone": normalize_tel})

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
        ws = writer.sheets.get(sheet_name) or writer.sheets.get('Sheet1', None)
        if ws is None or "telephone" not in df_to_save.columns:
            return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            row[0].number_format = '@'
    except Exception:
        pass

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name="Sheet1")
            _force_telephone_text_format_openpyxl(w, out, "Sheet1")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            df_new = pd.read_excel(up, converters={"telephone": normalize_tel})
            df_new = ensure_schema(df_new)
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    data_xlsx = b""
    try:
        ensure_schema(df).to_excel(buf, index=False, engine="openpyxl")
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=data_xlsx,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data_xlsx) == 0),
        help="Utilisez le bouton Sauvegarde depuis les écrans d’édition."
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
        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Villa Tobias//Reservations//FR\r\n"
            f"X-WR-CALNAME:{_ics_escape(cal_name)}\r\n"
            "CALSCALE:GREGORIAN\r\n"
            "METHOD:PUBLISH\r\n"
            "END:VCALENDAR\r\n"
        )
    core, _ = split_totals(df)
    core = sort_core(core)

    lines = []
    A = lines.append
    A("BEGIN:VCALENDAR")
    A("VERSION:2.0")
    A("PRODID:-//Villa Tobias//Reservations//FR")
    A(f"X-WR-CALNAME:{_ics_escape(cal_name)}")
    A("CALSCALE:GREGORIAN")
    A("METHOD:PUBLISH")

    for _, row in core.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
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

        A("BEGIN:VEVENT")
        A(f"UID:{_ics_escape(uid)}")
        A(f"DTSTAMP:{_dtstamp_utc_now()}")
        A(f"DTSTART;VALUE=DATE:{_fmt_date_ics(d1)}")
        A(f"DTEND;VALUE=DATE:{_fmt_date_ics(d2)}")
        A(f"SUMMARY:{_ics_escape(summary)}")
        A(f"DESCRIPTION:{_ics_escape(desc)}")
        A("END:VEVENT")

    A("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

# ==============================  SMS (MANUEL) ====================

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
        "Bienvenue chez nous !\n\n "
        "Nous sommes ravis de vous accueillir bientot à Nice. Pour organiser au mieux votre reception, merci de nous indiquer "
        "votre heure d'arrivee.\n\n "
        "Sachez egalement qu'une place de parking vous est allouee.\n\n "
        "Nous vous rappelons que le check-inse fait a partir de 2h pm et que le check-outau maximum 11h am.\n\n "
        "Vous trouverez des consignes a bagages des consignes a bagages, en cas de besoin.\n\n "
        "Nous vous souhaitons un excellent voyage et nous nous rejouissons de vous rencontrer tres bientot.\n\n "
        "Annick & Charley"
    )

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Un grand merci d’avoir choisi notre appartement pour votre séjour ! "
        "Nous espérons que vous avez passé un moment aussi agréable que celui que nous avons eu à vous accueillir.\n\n"
        "Si l’envie vous prend de revenir explorer encore un peu notre ville (ou simplement retrouver le confort de notre petit cocon), "
        "sachez que notre porte vous sera toujours grande ouverte.\n\n"
        "Au plaisir de vous accueillir à nouveau,\n"
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
    st.title("📋 Réservations")

    with st.expander("🎛️ Options d’affichage", expanded=True):
        filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"], index=0)
        show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)

    st.markdown("### Plateformes")
    pal = get_palette()
    if pal:
        st.markdown(" ".join(platform_badge(k) for k in sorted(pal.keys())), unsafe_allow_html=True)

    show_add_pf = st.checkbox("➕ Ajouter une nouvelle plateforme (rapide)")
    if show_add_pf:
        add_platform_inline()

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
        sauvegarder_donnees(new_df)
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

    def inline_input(label, widget_fn, key=None, **widget_kwargs):
        col1, col2 = st.columns([1,2])
        with col1: st.markdown(f"**{label}**")
        with col2: return widget_fn(label, key=key, label_visibility="collapsed", **widget_kwargs)

    paye = inline_input("Payé", st.checkbox, key="add_paye", value=False)
    nom = inline_input("Nom", st.text_input, key="add_nom", value="")
    sms_envoye = inline_input("SMS envoyé", st.checkbox, key="add_sms", value=False)

    tel = inline_input("Téléphone (+33...)", st.text_input, key="add_tel", value="")
    # Plateforme : inclure celles de la palette
    pf_opts = sorted(get_palette().keys())
    plateforme = inline_input("Plateforme", st.selectbox, key="add_pf",
                              options=pf_opts, index=pf_opts.index("Booking") if "Booking" in pf_opts else 0)

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
        sauvegarder_donnees(df2)
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
    pf_opts = sorted(get_palette().keys())
    cur_pf = df.at[i,"plateforme"] if df.at[i,"plateforme"] in pf_opts else "Autre"
    plateforme = col[1].selectbox("Plateforme", pf_opts, index=pf_opts.index(cur_pf) if cur_pf in pf_opts else 0)

    arrivee = st.date_input("Arrivée", df.at[i,"date_arrivee"] if isinstance(df.at[i,"date_arrivee"], date) else date.today())
    depart  = st.date_input("Départ",  df.at[i,"date_depart"] if isinstance(df.at[i,"date_depart"], date) else arrivee + timedelta(days=1), min_value=arrivee+timedelta(days=1))

    c1, c2, c3 = st.columns(3)
    brut = c1.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i,"prix_brut"]) if pd.notna(df.at[i,"prix_brut"]) else 0.0, step=1.0, format="%.2f")
    commissions = c2.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i,"commissions"]) if pd.notna(df.at[i,"commissions"]) else 0.0, step=1.0, format="%.2f")
    frais_cb = c3.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i,"frais_cb"]) if pd.notna(df.at[i,"frais_cb"]) else 0.0, step=1.0, format="%.2f")

    net_calc = max(brut - commissions - frais_cb, 0.0)

    d1, d2, d3 = st.columns(3)
    menage = d1.number_input("Ménage (€)", min_value=0.0, value=float(df.at[i,"menage"]) if pd.notna(df.at[i,"menage"]) else 0.0, step=1.0, format="%.2f")
    taxes  = d2.number_input("Taxes séjour (€)", min_value=0.