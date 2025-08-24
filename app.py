# app.py — Villa Tobias (COMPLET)
# - Onglet Plateformes (persistant dans Excel "Plateformes")
# - Réservations (édition statuts + ajout + modification/suppression)
# - Calendrier mensuel lisible (fond/gradient)
# - Rapport, Liste clients, Export ICS, SMS
# - Sauvegarde/Restauration XLSX robustes
# - Vidage cache

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
from collections import Counter

FICHIER = "reservations.xlsx"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  OUTILS GÉNÉRIQUES ==============================

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

def lighten_color(hex_color: str, factor: float = 0.75) -> str:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) != 6:
        return "#777777"
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    l = min(1.0, l + (1.0 - l) * factor)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"

def ideal_text_color(bg_hex: str) -> str:
    if bg_hex.startswith("linear-gradient"):
        return "#000000"
    bg_hex = bg_hex.lstrip("#")
    if len(bg_hex) != 6:
        return "#000000"
    r = int(bg_hex[0:2], 16)
    g = int(bg_hex[2:4], 16)
    b = int(bg_hex[4:6], 16)
    luminance = (0.299*r + 0.587*g + 0.114*b) / 255
    return "#000000" if luminance > 0.6 else "#ffffff"

# ==============================  SCHÉMA RÉSERVATIONS ==============================

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

    num_cols = ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Calculs auto
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

# ==============================  LECTURE/ÉCRITURE EXCEL ==============================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    # NB: engine explicite pour éviter l'erreur "cannot determine format"
    xls = pd.ExcelFile(path, engine="openpyxl")
    sheets = {name: xls.parse(name, converters={"telephone": normalize_tel}) for name in xls.sheet_names}
    return sheets

def charger_donnees():
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame()), pd.DataFrame(columns=["plateforme","couleur"])
    try:
        mtime = os.path.getmtime(FICHIER)
        sheets = _read_excel_cached(FICHIER, mtime)
        df_resa = ensure_schema(sheets.get("Sheet1", pd.DataFrame()))
        # Plateformes persos
        df_pf = sheets.get("Plateformes", pd.DataFrame(columns=["plateforme","couleur"]))
        if "plateforme" not in df_pf.columns or "couleur" not in df_pf.columns:
            df_pf = pd.DataFrame(columns=["plateforme","couleur"])
        return df_resa, df_pf
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame()), pd.DataFrame(columns=["plateforme","couleur"])

def sauvegarder_donnees(df_resa: pd.DataFrame, df_pf: pd.DataFrame):
    df_resa = ensure_schema(df_resa)
    core, totals = split_totals(df_resa)
    core = sort_core(core)
    out_resa = pd.concat([core, totals], ignore_index=True)

    # nettoyer plateformes
    if df_pf is None or df_pf.empty:
        df_pf = pd.DataFrame(columns=["plateforme","couleur"])
    else:
        df_pf = df_pf.copy()
        df_pf["plateforme"] = df_pf["plateforme"].astype(str).str.strip()
        df_pf["couleur"] = df_pf["couleur"].astype(str).str.strip()

    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out_resa.to_excel(w, index=False, sheet_name="Sheet1")
            df_pf.to_excel(w, index=False, sheet_name="Plateformes")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer(df_resa, df_pf):
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            xls = pd.ExcelFile(bio, engine="openpyxl")
            sheets = {name: xls.parse(name, converters={"telephone": normalize_tel}) for name in xls.sheet_names}
            new_resa = ensure_schema(sheets.get("Sheet1", pd.DataFrame()))
            new_pf = sheets.get("Plateformes", pd.DataFrame(columns=["plateforme","couleur"]))
            if "plateforme" not in new_pf.columns or "couleur" not in new_pf.columns:
                new_pf = pd.DataFrame(columns=["plateforme","couleur"])
            sauvegarder_donnees(new_resa, new_pf)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df_resa, df_pf):
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            ensure_schema(df_resa).to_excel(w, index=False, sheet_name="Sheet1")
            (df_pf if df_pf is not None else pd.DataFrame(columns=["plateforme","couleur"]))\
                .to_excel(w, index=False, sheet_name="Plateformes")
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
        help="Télécharge une copie complète (réservations + plateformes)."
    )

# ==============================  PALETTE (depuis Excel) ==============================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def palette_from_df(df_pf: pd.DataFrame) -> dict:
    pal = DEFAULT_PALETTE.copy()
    if df_pf is None or df_pf.empty:
        return pal
    for _, r in df_pf.iterrows():
        name = str(r.get("plateforme") or "").strip()
        col = str(r.get("couleur") or "").strip()
        if name and col.startswith("#") and len(col) in (4,7):
            pal[name] = col
    return pal

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

# ==============================  ICS EXPORT ==============================

def _ics_escape(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
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
        tel        = str(row.get("telephone") or "").strip()
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

# ==============================  UI HELPERS ==============================

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

# ==============================  VUE RÉSERVATIONS ==============================

def vue_reservations(df: pd.DataFrame, palette: dict, df_pf: pd.DataFrame):
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

    c1, c2, c3 = st.columns([1,1,6])
    if c1.button("💾 Enregistrer cases cochées"):
        for _, r in edited.iterrows():
            ridx = int(r["__rowid"])
            core.at[ridx, "paye"] = bool(r.get("paye", False))
            core.at[ridx, "sms_envoye"] = bool(r.get("sms_envoye", False))
        new_df = pd.concat([core, totals], ignore_index=False).reset_index(drop=True)
        sauvegarder_donnees(new_df, df_pf)
        st.success("✅ Statuts mis à jour.")
        st.rerun()

    # Boutons Modifier / Supprimer ligne sélectionnée
    if not core.empty:
        indices = core.index.tolist()
        choix = c2.selectbox("Ligne", indices, format_func=lambda i: f"{core.at[i,'nom_client']} | {format_date_str(core.at[i,'date_arrivee'])}")
        if c2.button("🗑 Supprimer cette ligne"):
            df2 = df.drop(index=choix).reset_index(drop=True)
            sauvegarder_donnees(df2, df_pf)
            st.warning("Supprimé.")
            st.rerun()

# ==============================  VUE AJOUT ==============================

def vue_ajouter(df: pd.DataFrame, palette: dict, df_pf: pd.DataFrame):
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
        sauvegarder_donnees(df2, df_pf)
        st.success("✅ Réservation enregistrée")
        st.rerun()

# ==============================  VUE MODIFIER / SUPPRIMER ==============================

def vue_modifier(df: pd.DataFrame, palette: dict, df_pf: pd.DataFrame):
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
        df.at[i,"frais_cb"] = float(frais_cb)
        df.at[i,"prix_net"]  = round(net_calc, 2)
        df.at[i,"menage"] = float(menage)
        df.at[i,"taxes_sejour"] = float(taxes)
        df.at[i,"base"] = round(base_calc, 2)
        df.at[i,"charges"] = round(charges_calc, 2)
        df.at[i,"%"] = round(pct_calc, 2)
        df.at[i,"nuitees"]   = (depart - arrivee).days
        df.at[i,"AAAA"]      = arrivee.year
        df.at[i,"MM"]        = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df, df_pf)
        st.success("✅ Modifié")
        st.rerun()

    if c_del.button("🗑 Supprimer"):
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2, df_pf)
        st.warning("Supprimé.")
        st.rerun()

# ==============================  VUE CALENDRIER ==============================

def vue_calendrier(df: pd.DataFrame, palette: dict):
    st.title("📅 Calendrier mensuel")

    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    c1, c2 = st.columns(2)
    mois_nom = c1.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = c2.selectbox("Année", annees, index=len(annees)-1)

    mois_idx = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(annee, mois_idx)[1]
    days = [date(annee, mois_idx, j) for j in range(1, nb_jours+1)]

    core, _ = split_totals(df)
    planning = {d: [] for d in days}
    for _, row in core.iterrows():
        d1, d2 = row.get("date_arrivee"), row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        pf = str(row.get("plateforme") or "Autre")
        nm = str(row.get("nom_client") or "")
        for d in days:
            if d1 <= d < d2:
                planning[d].append((pf, nm))

    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    monthcal = calendar.monthcalendar(annee, mois_idx)

    def day_gradient(platforms: list[str]) -> str:
        if not platforms:
            return "none"
        step = 100 / len(platforms)
        cols = []
        start = 0.0
        for pf in platforms:
            base = palette.get(pf, "#777777")
            pastel = lighten_color(base, 0.75)
            end = start + step
            cols.append(f"{pastel} {start:.2f}% {end:.2f}%")
            start = end
        return f"linear-gradient(90deg, {', '.join(cols)})"

    table_text, bg_rules, fg_rules = [], [], []
    for week in monthcal:
        row_text, row_bg, row_fg = [], [], []
        for j in week:
            if j == 0:
                row_text.append("")
                row_bg.append("transparent")
                row_fg.append("inherit")
                continue
            d = date(annee, mois_idx, j)
            items = planning.get(d, [])
            names = [nm for _, nm in items]
            if len(names) > 6:
                lines = [str(j)] + names[:6] + [f"... (+{len(names)-6})"]
            else:
                lines = [str(j)] + names
            row_text.append("\n".join(lines))

            pf_list = [pf for pf, _ in items]
            if len(pf_list) == 0:
                row_bg.append("transparent")
                row_fg.append("inherit")
            elif len(set(pf_list)) == 1:
                base = palette.get(pf_list[0], "#777777")
                pastel = lighten_color(base, 0.75)
                row_bg.append(pastel)
                row_fg.append(ideal_text_color(pastel))
            else:
                grad = day_gradient(pf_list)
                row_bg.append(grad)
                row_fg.append("#000000")
        table_text.append(row_text)
        bg_rules.append(row_bg)
        fg_rules.append(row_fg)

    df_table = pd.DataFrame(table_text, columns=headers)

    def style_row(vals, r_idx):
        css = []
        for c_idx, _ in enumerate(vals):
            bg = bg_rules[r_idx][c_idx]
            fg = fg_rules[r_idx][c_idx]
            if isinstance(bg, str) and bg.startswith("linear-gradient"):
                style = (
                    f"background:{bg};"
                    f"color:{fg};"
                    "white-space:pre-wrap;"
                    "padding:6px;"
                    "border:1px solid rgba(127,127,127,0.25);"
                    "border-radius:6px;"
                )
            else:
                style = (
                    f"background-color:{bg};"
                    f"color:{fg};"
                    "white-space:pre-wrap;"
                    "padding:6px;"
                    "border:1px solid rgba(127,127,127,0.25);"
                    "border-radius:6px;"
                )
            css.append(style)
        return css

    styler = df_table.style
    for r in range(df_table.shape[0]):
        styler = styler.apply(lambda v, r=r: style_row(v, r), axis=1)

    st.caption("Légende plateformes :")
    legend = " • ".join(
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{palette[p]};border-radius:3px;margin-right:6px;"></span>{p}'
        for p in sorted(palette.keys())
    )
    st.markdown(legend, unsafe_allow_html=True)

    st.dataframe(styler, use_container_width=True, height=520)

# ==============================  VUE RAPPORT ==============================

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.info("Aucune année disponible.")
        return

    c1, c2, c3 = st.columns(3)
    annee = c1.selectbox("Année", annees, index=len(annees)-1, key="rapport_annee")
    pf_opt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = c2.selectbox("Plateforme", pf_opt, key="rapport_pf")
    mois_opt = ["Tous"] + [f"{i:02d}" for i in range(1,13)]
    mois_label = c3.selectbox("Mois", mois_opt, key="rapport_mois")

    data = df[df["AAAA"] == int(annee)].copy()
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]
    if mois_label != "Tous":
        data = data[data["MM"] == int(mois_label)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    detail = data.copy()
    for c in ["date_arrivee","date_depart"]:
        detail[c] = detail[c].apply(format_date_str)
    by = [c for c in ["date_arrivee","nom_client"] if c in detail.columns]
    if by:
        detail = detail.sort_values(by=by, na_position="last").reset_index(drop=True)

    cols_detail = [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"
    ]
    cols_detail = [c for c in cols_detail if c in detail.columns]
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
    )
    stats = stats.sort_values(["MM","plateforme"]).reset_index(drop=True)

    def bar_chart_metric(label, col):
        if stats.empty: return
        pvt = stats.pivot(index="MM", columns="plateforme", values=col).fillna(0).sort_index()
        pvt.index = [f"{int(m):02d}" for m in pvt.index]
        st.markdown(f"**{label}**")
        st.bar_chart(pvt)

    bar_chart_metric("Revenus bruts", "prix_brut")
    bar_chart_metric("Revenus nets",  "prix_net")
    bar_chart_metric("Base",          "base")
    bar_chart_metric("Nuitées",       "nuitees")

# ==============================  VUE LISTE CLIENTS ==============================

def vue_clients(df