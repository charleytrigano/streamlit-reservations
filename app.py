# app.py — Villa Tobias (COMPLET, version stabilisée)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
import colorsys

FICHIER = "reservations.xlsx"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb": "#e74c3c",
    "Autre": "#f59e0b",
}

def get_palette() -> dict:
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    pal = {}
    for k, v in st.session_state.palette.items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#"):
            pal[k] = v
    st.session_state.palette = pal
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = {str(k): str(v) for k, v in palette.items() if k and v}

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
    "paye","nom_client","sms_envoye","plateforme","telephone",
    "date_arrivee","date_depart","nuitees","prix_brut","commissions","frais_cb",
    "prix_net","menage","taxes_sejour","base","charges","%","AAAA","MM","ical_uid"
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
    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [(d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
                         for d1, d2 in zip(df["date_arrivee"], df["date_depart"])]
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")
    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"] = df["ical_uid"].fillna("")
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"] = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"] = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)
    return df

def split_totals(df: pd.DataFrame):
    if df is None or df.empty:
        return df, df
    mask = df["nom_client"].str.lower().eq("total")
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    return df.sort_values(["date_arrivee","nom_client"], na_position="last").reset_index(drop=True)

# ==============================  EXCEL I/O  ==============================
@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path, engine="openpyxl", converters={"telephone": normalize_tel})

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

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    out = pd.concat([sort_core(core), totals], ignore_index=True)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name="Sheet1")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")


# ==============================  RESTAURER / TÉLÉCHARGER  ==============================
from urllib.parse import quote

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer un fichier .xlsx", type=["xlsx"],
                                  help="Charge et remplace le fichier local 'reservations.xlsx'.")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                st.sidebar.error("Fichier vide.")
                return
            bio = BytesIO(raw)
            df_new = pd.read_excel(bio, engine="openpyxl", converters={"telephone": normalize_tel})
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
        "💾 Télécharger 'reservations.xlsx'",
        data=data_xlsx or b"",
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(not data_xlsx),
    )

# ==============================  ICS EXPORT  ==============================
from datetime import timezone

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

import hashlib
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
        tel = str(row.get("telephone") or "").strip()
        brut = float(row.get("prix_brut") or 0.0)
        net  = float(row.get("prix_net")  or 0.0)
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
from urllib.parse import quote

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
        "Le check-in se fait à partir de 14h et le check-out au plus tard 11h.\n\n "
        "Nous vous souhaitons un excellent voyage et nous nous rejouissons de vous rencontrer très bientôt.\n\n "
        "Annick & Charley"
    )

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Un grand merci d’avoir choisi notre appartement pour votre séjour ! "
        "Nous espérons que vous avez passé un bon moment.\n\n"
        "Au plaisir de vous accueillir à nouveau,\n"
        "Annick & Charley"
    )

# ==============================  UI HELPERS (KPI + recherche) ==============================
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

# ==============================  CALENDRIER (fond sombre lisible) ==============================
import colorsys
def lighten_color(hex_color: str, factor: float = 0.75) -> str:
    hex_color = hex_color.lstrip("#")
    if len(hex_color) == 3:
        hex_color = "".join(ch*2 for ch in hex_color)
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    l = min(1.0, l + (1.0 - l) * factor)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"

def ideal_text_color(bg_hex: str) -> str:
    bg_hex = bg_hex.lstrip("#")
    if len(bg_hex) == 3:
        bg_hex = "".join(ch*2 for ch in bg_hex)
    r = int(bg_hex[0:2], 16)
    g = int(bg_hex[2:4], 16)
    b = int(bg_hex[4:6], 16)
    luminance = (0.299*r + 0.587*g + 0.114*b) / 255
    return "#000000" if luminance > 0.6 else "#ffffff"

def vue_calendrier(df: pd.DataFrame):
    palette = get_palette()
    st.title("📅 Calendrier mensuel")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    colm, cola = st.columns(2)
    mois_nom = colm.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = cola.selectbox("Année", annees, index=len(annees)-1)

    m = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(annee, m)[1]
    jours = [date(annee, m, j+1) for j in range(nb_jours)]

    core, _ = split_totals(df)
    planning = {j: [] for j in jours}
    for _, row in core.iterrows():
        d1 = row["date_arrivee"]; d2 = row["date_depart"]
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        pf = str(row["plateforme"] or "Autre")
        nom = str(row["nom_client"] or "")
        for j in jours:
            if d1 <= j < d2:
                planning[j].append((pf, nom))

    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    monthcal = calendar.monthcalendar(annee, m)

    table = []; bg_table = []; fg_table = []
    for semaine in monthcal:
        row_text = []; row_bg = []; row_fg = []
        for jour in semaine:
            if jour == 0:
                row_text.append(""); row_bg.append("transparent"); row_fg.append(None)
            else:
                d = date(annee, m, jour)
                items = planning.get(d, [])
                # Affiche les noms clients, 1 par ligne
                content = [str(jour)] + [nm for _, nm in items[:6]]
                if len(items) > 6:
                    content.append(f"...(+{len(items)-6})")
                row_text.append("\n".join(content))
                if items:
                    base = palette.get(items[0][0], "#777777")
                    bg = lighten_color(base, 0.75)
                    fg = ideal_text_color(bg)
                else:
                    bg = "transparent"; fg = None
                row_bg.append(bg); row_fg.append(fg)
        table.append(row_text); bg_table.append(row_bg); fg_table.append(row_fg)

    df_table = pd.DataFrame(table, columns=headers)

    def style_row(vals, r):
        css = []
        for c in range(len(vals)):
            bg = bg_table[r][c]; fg = fg_table[r][c] or "inherit"
            css.append(f"background-color:{bg};color:{fg};white-space:pre-wrap;border:1px solid rgba(255,255,255,0.15);")
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
    st.dataframe(styler, use_container_width=True, height=460)

# ==============================  AUTRES VUES (CRUD / RAPPORT / CLIENTS / ICS / SMS) ==============================
def vue_reservations(df: pd.DataFrame):
    palette = get_palette()
    st.title("📋 Réservations")
    with st.expander("🎛️ Options d’affichage", expanded=True):
        filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
        show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)

    st.markdown("### Plateformes")
    if palette:
        badges = " &nbsp;&nbsp;".join(
            [f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{get_palette()[pf]};border-radius:3px;margin-right:6px;"></span>{pf}'
             for pf in sorted(palette.keys())]
        )
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

    edit = core.copy()
    edit["__rowid"] = edit.index
    edit["date_arrivee"] = edit["date_arrivee"].apply(format_date_str)
    edit["date_depart"]  = edit["date_depart"].apply(format_date_str)

    cols = [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees","prix_brut","commissions","frais_cb",
        "prix_net","menage","taxes_sejour","base","charges","%","AAAA","MM","__rowid"
    ]
    cols = [c for c in cols if c in edit.columns]

    edited = st.data_editor(
        edit[cols], use_container_width=True, hide_index=True,
        column_config={
            "paye": st.column_config.CheckboxColumn("Payé"),
            "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
            "__rowid": st.column_config.Column("id", disabled=True, width="small"),
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
    if c1.button("💾 Enregistrer Payé / SMS"):
        for _, r in edited.iterrows():
            ridx = int(r["__rowid"])
            core.at[ridx, "paye"] = bool(r.get("paye", False))
            core.at[ridx, "sms_envoye"] = bool(r.get("sms_envoye", False))
        new_df = pd.concat([core, totals], ignore_index=False).reset_index(drop=True)
        sauvegarder_donnees(new_df)
        st.success("✅ Statuts mis à jour.")
        st.rerun()

    if not totals.empty:
        show_tot = totals.copy()
        for c in ["date_arrivee","date_depart"]:
            show_tot[c] = show_tot[c].apply(format_date_str)
        st.caption("Lignes de totaux (non éditables) :")
        st.dataframe(show_tot[[c for c in cols if c in show_tot.columns and c != "__rowid"]],
                     use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    st.caption("Saisie compacte")
    palette = get_palette()

    def inline_input(label, widget_fn, key=None, **kwargs):
        col1, col2 = st.columns([1,2])
        with col1: st.markdown(f"**{label}**")
        with col2: return widget_fn(label, key=key, label_visibility="collapsed", **kwargs)

    paye = inline_input("Payé", st.checkbox, key="add_paye", value=False)
    nom = inline_input("Nom", st.text_input, key="add_nom", value="")
    sms_envoye = inline_input("SMS envoyé", st.checkbox, key="add_sms", value=False)
    tel = inline_input("Téléphone (+33…)", st.text_input, key="add_tel", value="")
    pf_options = sorted(palette.keys())
    pf_index = pf_options.index("Booking") if "Booking" in pf_options else 0
    plateforme = inline_input("Plateforme", st.selectbox, key="add_pf", options=pf_options, index=pf_index)

    arrivee = inline_input("Arrivée", st.date_input, key="add_arrivee", value=date.today())
    min_dep = arrivee + timedelta(days=1)
    depart  = inline_input("Départ", st.date_input, key="add_depart", value=min_dep, min_value=min_dep)

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
        st.warning("Sélection invalide."); return
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
        sauvegarder_donnees(df)
        st.success("✅ Modifié")
        st.rerun()

    if c_del.button("🗑 Supprimer"):
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2)
        st.warning("Supprimé.")
        st.rerun()

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
    detail = detail.sort_values(["date_arrivee","nom_client"], na_position="last").reset_index(drop=True)

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

    cols = ["paye","nom_client","sms_envoye","plateforme","telephone","date_arrivee","date_depart",
            "nuitees","prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","prix_brut/nuit","prix_net/nuit"]
    cols = [c for c in cols if c in show.columns]
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
    st.caption("Google Agenda → Paramètres → Importer & exporter → Importer → .ics.")

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
    with c1:
        st.code(body or "—")
    if tel and body:
        c1, c2 = st.columns(2)
        c1.link_button(f"📞 Appeler {tel}", f"tel:{tel}")
        c2.link_button("📩 Envoyer SMS", f"sms:{tel}?&body={quote(body)}")
    else:
        st.info("Renseignez un téléphone et un message.")

# ==============================  SIDEBAR (Palette + Fichier + Maintenance) ==============================
def render_palette_editor_sidebar():
    palette = get_palette()
    st.sidebar.markdown("## 🎨 Plateformes")
    with st.sidebar.expander("➕ Ajouter / modifier des plateformes", expanded=False):
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
            save_palette({"Booking":"#1e90ff","Airbnb":"#e74c3c","Autre":"#f59e0b"})
            st.success("✅ Palette réinitialisée.")
    if palette:
        st.sidebar.markdown("**Plateformes existantes :**")
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
                        st.rerun()

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

# ==============================  APP  ==============================
def main():
    # Fichier
    st.sidebar.title("📁 Fichier")
    df_tmp = charger_donnees()
    bouton_telecharger(df_tmp)
    bouton_restaurer()

    # Palette + Maintenance
    render_palette_editor_sidebar()
    render_cache_section_sidebar()

    # Navigation
    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS"]
    )

    df = charger_donnees()

    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "➕ Ajouter":
        vue_ajouter(df)
    elif onglet == "✏️ Modifier / Supprimer":
        vue_modifier(df)
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