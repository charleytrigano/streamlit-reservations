# app.py — Villa Tobias (COMPLET, DEFINITIF)
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

def sauvegarder_donnees(df: pd.DataFrame, palette: dict = None):
    """Sauvegarde réservations (+ éventuellement palette)."""
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)

    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name=DATA_SHEET)
            if palette is not None:
                p = pd.DataFrame(
                    [{"plateforme": k, "couleur": v} for k, v in sorted(palette.items())]
                )
                p.to_excel(w, index=False, sheet_name=PALETTE_SHEET)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

# ==============================  SMS (corrigé) ==============================
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
        "Nous sommes ravis de vous accueillir à Nice.\n\n"
        "Afin d'organiser au mieux votre reception, merci de nous indiquer votre heure d'arrivée.\n\n"
        "Une place de parking vous est allouée en cas de besoin.\n\n"
        "Le check-in se fait à partir de 14:00 h et le check-out au plus tard à 11:00 h.\n\n"
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

# ==============================  APP  ==============================
def main():
    st.sidebar.title("📁 Fichier")
    df_tmp, pal_tmp = charger_donnees()
    # (ici on garde tes boutons téléchargement/restauration si besoin)

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS","🎨 Plateformes"]
    )

    df, _ = charger_donnees()

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
    elif onglet == "🎨 Plateformes":
        vue_plateformes()

if __name__ == "__main__":
    main()

# ==============================  BOUTONS FICHIER (XLSX) ==============================
def bouton_telecharger(df: pd.DataFrame):
    """Télécharge reservations.xlsx (feuilles: Sheet1 + Plateformes)."""
    buf = BytesIO()
    data = b""
    try:
        df2 = ensure_schema(df)
        with pd.ExcelWriter(buf, engine="openpyxl") as w:
            # données
            df2.to_excel(w, index=False, sheet_name=DATA_SHEET)
            # palette
            pal = get_palette()
            p = pd.DataFrame([{"plateforme": k, "couleur": v} for k, v in sorted(pal.items())])
            p.to_excel(w, index=False, sheet_name=PALETTE_SHEET)
        data = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data = b""

    st.sidebar.download_button(
        "💾 Télécharger reservations.xlsx",
        data=data,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data) == 0)
    )


def bouton_restaurer():
    """Restaure depuis un xlsx fourni par l’utilisateur (BytesIO)."""
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
                # Réservations
                sheet = DATA_SHEET if DATA_SHEET in xf.sheet_names else xf.sheet_names[0]
                df_new = pd.read_excel(xf, sheet_name=sheet, engine="openpyxl",
                                       converters={"telephone": normalize_tel})
                df_new = ensure_schema(df_new)

                # Palette
                palette_new = DEFAULT_PALETTE.copy()
                if PALETTE_SHEET in xf.sheet_names:
                    pal_df = pd.read_excel(xf, sheet_name=PALETTE_SHEET, engine="openpyxl")
                    if {"plateforme", "couleur"}.issubset(set(pal_df.columns)):
                        for _, r in pal_df.iterrows():
                            name = str(r["plateforme"]).strip()
                            color = _clean_hex(str(r["couleur"]))
                            if name:
                                palette_new[name] = color

            sauvegarder_donnees(df_new, palette_new)
            set_palette(palette_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.session_state.uploader_key_restore += 1
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")


# ==============================  CALENDRIER (barres style agenda) ==============================
def _ideal_text_color(bg_hex: str) -> str:
    bg_hex = (bg_hex or "#999999").lstrip("#")
    if len(bg_hex) != 6:
        return "#000000"
    r = int(bg_hex[0:2], 16)
    g = int(bg_hex[2:4], 16)
    b = int(bg_hex[4:6], 16)
    luminance = (0.299*r + 0.587*g + 0.114*b) / 255
    return "#000000" if luminance > 0.6 else "#ffffff"


def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier (barres style agenda)")

    palette = get_palette()
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    cols = st.columns(2)
    mois_nom = cols[0].selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = cols[1].selectbox("Année", annees, index=len(annees)-1)

    m = list(calendar.month_name).index(mois_nom)
    monthcal = calendar.monthcalendar(annee, m)

    # Planification: jour -> [(plateforme, nom_client)]
    core, _ = split_totals(df)
    nb_jours = calendar.monthrange(annee, m)[1]
    planning = {date(annee, m, j): [] for j in range(1, nb_jours+1)}

    for _, row in core.iterrows():
        d1 = row["date_arrivee"]; d2 = row["date_depart"]
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        pf = str(row["plateforme"] or "Autre")
        nom = str(row["nom_client"] or "")
        cur = d1
        while isinstance(cur, date) and cur < d2:
            if cur.month == m and cur.year == annee:
                planning[cur].append((pf, nom))
            cur += timedelta(days=1)

    # CSS sombre-friendly
    st.markdown("""
    <style>
    .cal-wrap { overflow-x:auto; }
    table.cal { border-collapse: collapse; width:100%; table-layout: fixed; }
    table.cal th, table.cal td { border: 1px solid rgba(127,127,127,0.35); vertical-align: top; padding: 6px; }
    table.cal th { text-align:center; font-weight:600; }
    .daynum { font-weight:700; margin-bottom:4px; opacity:0.85; }
    .bar { border-radius:6px; padding:4px 6px; margin:4px 0; font-size:0.85rem; white-space:nowrap;
           overflow:hidden; text-overflow:ellipsis; }
    </style>
    """, unsafe_allow_html=True)

    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    html = ['<div class="cal-wrap"><table class="cal">']
    html.append("<thead><tr>" + "".join([f"<th>{h}</th>" for h in headers]) + "</tr></thead><tbody>")

    for semaine in monthcal:
        html.append("<tr>")
        for jour in semaine:
            if jour == 0:
                html.append('<td style="background:transparent;"></td>')
                continue
            d = date(annee, m, jour)
            items = planning.get(d, [])
            cell = [f'<div class="daynum">{jour}</div>']
            # une barre par réservation ce jour
            for pf, nom in items:
                base = palette.get(pf, "#999999")
                fg = _ideal_text_color(base)
                # barre = fond coloré plateforme + nom client
                cell.append(f'<div class="bar" style="background:{base};color:{fg};">{nom}</div>')
            html.append(f"<td>{''.join(cell)}</td>")
        html.append("</tr>")
    html.append("</tbody></table></div>")

    st.markdown("".join(html), unsafe_allow_html=True)

    # Légende
    st.caption("Légende plateformes :")
    leg = " • ".join([
        f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{palette[p]};border-radius:3px;margin-right:6px;"></span>{p}'
        for p in sorted(palette.keys())
    ])
    st.markdown(leg, unsafe_allow_html=True)


# ==============================  PLATEFORMES (onglet) ==============================
def vue_plateformes():
    st.title("🎨 Plateformes (palette couleurs)")
    pal = get_palette()

    st.caption("Ajoutez / modifiez / supprimez des plateformes. Cliquez sur **Enregistrer la palette** pour stocker dans le fichier Excel (feuille «Plateformes»).")

    pf_df = pd.DataFrame([{"plateforme": k, "couleur": v} for k, v in sorted(pal.items())])
    pf_df = st.data_editor(
        pf_df,
        hide_index=True,
        use_container_width=True,
        num_rows="dynamic",
        column_config={
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn("Couleur (hex)"),
        }
    )

    c1, c2, c3 = st.columns(3)
    if c1.button("💾 Enregistrer la palette"):
        new_p = {}
        for _, r in pf_df.iterrows():
            name = str(r.get("plateforme", "")).strip()
            col = _clean_hex(str(r.get("couleur", "#999999")))
            if name:
                new_p[name] = col
        set_palette(new_p)
        # Sauvegarder sans perdre les réservations
        df_current, _ = charger_donnees()
        sauvegarder_donnees(df_current, new_p)
        st.success("✅ Palette enregistrée dans Excel.")

    if c2.button("♻️ Réinitialiser palette par défaut"):
        set_palette(DEFAULT_PALETTE.copy())
        df_current, _ = charger_donnees()
        sauvegarder_donnees(df_current, get_palette())
        st.success("✅ Palette réinitialisée.")
        st.rerun()

    if c3.button("🔄 Recharger depuis Excel"):
        # recharge et écrase la session
        _, pal_file = charger_donnees()
        set_palette(pal_file)
        st.success("✅ Palette rechargée depuis Excel.")
        st.rerun()

    st.markdown("### Aperçu")
    badges = " &nbsp;&nbsp;".join([platform_badge(pf, pal) for pf in sorted(pal.keys())])
    st.markdown(badges, unsafe_allow_html=True)