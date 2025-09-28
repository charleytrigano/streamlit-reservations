# ============================== PART 1/5 : IMPORTS, CONFIG, STYLES, HELPERS ==============================

import os
import io
import re
import uuid
import hashlib
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange
from urllib.parse import quote

import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt

# -------------------------------- CONFIG APP --------------------------------
st.set_page_config(
    page_title="✨ Gestion des Réservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------------- CONSTANTES --------------------------------
# Ces chemins sont mis à jour automatiquement selon l'appartement choisi
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES = "plateformes.csv"
APARTMENTS_CSV = "apartments.csv"

# Fichier des indicatifs téléphoniques + drapeaux (code ISO2, country, flag)
INDICATIFS_CSV = "indicatifs_pays.csv"

DEFAULT_PALETTE = {
    "Booking": "#1b9e77",
    "Airbnb": "#d95f02",
    "Abritel": "#7570b3",
    "Direct": "#e7298a",
}

# Google Form / Sheets (adapter si besoin)
FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# -------------------------------- STYLES --------------------------------
def apply_style(light: bool = False):
    """CSS: thème, grille calendrier, boutons impression, styles d'impression A4 paysage."""
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    card_bg = "rgba(255,255,255,.65)" if light else "rgba(255,255,255,.06)"
    chip_bg = "#eee" if light else "#2a2f3a"
    chip_fg = "#222" if light else "#eee"
    cell_bg = "#fff" if light else "#0b0d12"

    st.markdown(
        f"""
<style>
html, body, [data-testid="stAppViewContainer"] {{ background:{bg}; color:{fg}; }}
[data-testid="stSidebar"] {{ background:{side}; border-right:1px solid {border}; }}

.glass {{ background:{card_bg}; border:1px solid {border}; border-radius:12px; padding:12px; margin:10px 0; }}
.chip {{ display:inline-block; padding:6px 10px; border-radius:12px; margin:4px 6px; 
         font-size:.86rem; background:{chip_bg}; color:{chip_fg}; }}

.cal-header {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; font-weight:700; opacity:.8; margin:6px 0 8px; }}
.cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; }}
.cal-cell {{ border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px; position:relative; overflow:hidden; background:{cell_bg}; }}
.cal-cell.outside {{ opacity:.45; }}
.cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
.resa-pill {{ padding:4px 6px; border-radius:6px; font-size:.84rem; margin-top:22px; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}

/* Impression : A4 paysage + masquage colonnes techniques */
@media print {{
  @page {{ size: A4 landscape; margin: 10mm; }}
  .hide-on-print {{ display:none !important; }}
  .print-header {{ display:block !important; }}
}}
.print-header {{ display:none; text-align:center; margin-bottom:12px; }}
</style>
        """,
        unsafe_allow_html=True,
    )

def render_print_header():
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.markdown(f"<div class='print-header'><h2>Réservations — {apt_name}</h2></div>", unsafe_allow_html=True)

def print_buttons(location: str = "main"):
    """Bouton Imprimer avec JS (fonctionne sur navigateur desktop)."""
    target = st.sidebar if location == "sidebar" else st
    target.button("🖨️ Imprimer", key=f"print_btn_{location}")
    st.markdown(
        """
<script>
const labels = Array.from(parent.document.querySelectorAll('button span, button p'));
const node = labels.find(n => n.textContent && n.textContent.trim() === "🖨️ Imprimer");
if (node) { node.parentElement.onclick = () => window.print(); }
</script>
        """,
        unsafe_allow_html=True,
    )

# -------------------------------- HELPERS DATA --------------------------------
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","pays",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid"
]

def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(io.StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 2:
                return df
        except Exception:
            pass
    try:
        return pd.read_csv(io.StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _as_series(x, index=None):
    if isinstance(x, pd.Series):
        return x
    if isinstance(x, (list, tuple, np.ndarray)):
        s = pd.Series(list(x))
        if index is not None and len(index) == len(s):
            s.index = index
        return s
    if index is None:
        return pd.Series([x])
    return pd.Series([x] * len(index), index=index)

def _to_bool_series(s: pd.Series) -> pd.Series:
    s = _as_series(s)
    out = s.astype(str).str.strip().str.lower().isin(
        ["true","1","oui","vrai","yes","y","t"]
    )
    return out.fillna(False).astype(bool)

def _to_num(s: pd.Series) -> pd.Series:
    s = _as_series(s)
    sc = (s.astype(str)
            .str.replace("€","",regex=False)
            .str.replace(" ","",regex=False)
            .str.replace(",",".",regex=False).str.strip())
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    s = _as_series(s)
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if len(d) and d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-local"

def _df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Reservations"):
    from io import BytesIO
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        return buf.getvalue(), None
    except Exception as e:
        st.warning(f"Impossible de générer un Excel (openpyxl requis) : {e}")
        return None, e

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D", "", str(phone or ""))
    if not s:
        return ""
    if s.startswith("33"):
        return "+" + s
    if s.startswith("0"):
        return "+33" + s[1:]
    return "+" + s

# -------------------------------- INDICATIFS PAYS --------------------------------
# Drapeaux en emoji + code ISO2. Ajoute/édite via la page "Indicateurs pays".
DEFAULT_INDICATIFS = [
    {"code": "FR", "country": "France", "flag": "🇫🇷", "phone_prefix": "33"},
    {"code": "BE", "country": "Belgique", "flag": "🇧🇪", "phone_prefix": "32"},
    {"code": "CH", "country": "Suisse", "flag": "🇨🇭", "phone_prefix": "41"},
    {"code": "ES", "country": "Espagne", "flag": "🇪🇸", "phone_prefix": "34"},
    {"code": "IT", "country": "Italie", "flag": "🇮🇹", "phone_prefix": "39"},
    {"code": "GB", "country": "Royaume-Uni", "flag": "🇬🇧", "phone_prefix": "44"},
    {"code": "DE", "country": "Allemagne", "flag": "🇩🇪", "phone_prefix": "49"},
    {"code": "PT", "country": "Portugal", "flag": "🇵🇹", "phone_prefix": "351"},
    {"code": "LU", "country": "Luxembourg", "flag": "🇱🇺", "phone_prefix": "352"},
    {"code": "MA", "country": "Maroc", "flag": "🇲🇦", "phone_prefix": "212"},
    {"code": "TN", "country": "Tunisie", "flag": "🇹🇳", "phone_prefix": "216"},
    {"code": "US", "country": "États-Unis", "flag": "🇺🇸", "phone_prefix": "1"},
    {"code": "CA", "country": "Canada", "flag": "🇨🇦", "phone_prefix": "1"},
    {"code": "AE", "country": "Émirats Arabes Unis", "flag": "🇦🇪", "phone_prefix": "971"},
]

def create_indicatifs_csv():
    """Crée le CSV indicatifs_pays.csv s'il est absent."""
    if os.path.exists(INDICATIFS_CSV):
        return
    df = pd.DataFrame(DEFAULT_INDICATIFS, columns=["code","country","flag","phone_prefix"])
    df.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8", lineterminator="\n")

@st.cache_data(show_spinner=False)
def load_indicatifs() -> pd.DataFrame:
    """Charge les indicatifs (créé le fichier si nécessaire)."""
    create_indicatifs_csv()
    try:
        df = pd.read_csv(INDICATIFS_CSV, dtype=str)
    except Exception:
        df = pd.DataFrame(DEFAULT_INDICATIFS)
    for col in ["code","country","flag","phone_prefix"]:
        if col not in df.columns:
            df[col] = ""
    df["code"] = df["code"].astype(str).str.upper().str.strip()
    df["phone_prefix"] = df["phone_prefix"].astype(str).str.strip()
    return df[["code","country","flag","phone_prefix"]]

def _phone_country(phone: str) -> str:
    """Déduit le pays à partir de l'indicatif téléphonique via INDICATIFS_CSV."""
    p = str(phone or "").strip()
    if not p:
        return ""
    if p.startswith("+"):
        p1 = p[1:]
    elif p.startswith("00"):
        p1 = p[2:]
    elif p.startswith("0"):
        return "France"
    else:
        p1 = p

    indic = load_indicatifs()
    # tri par longueur du préfixe DESC pour trouver la correspondance la plus longue
    indic = indic.copy()
    indic["len"] = indic["phone_prefix"].astype(str).str.len()
    indic = indic.sort_values("len", ascending=False)

    for _, r in indic.iterrows():
        pref = str(r["phone_prefix"])
        if pref and p1.startswith(pref):
            return str(r["country"])
    return "Inconnu"

# -------------------------------- NORMALISATION / SAUVEGARDE --------------------------------
def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Assure la présence des colonnes standard et calcule les champs dérivés."""
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Renommages fréquents
    rename_map = {
        "Payé": "paye",
        "Client": "nom_client",
        "Plateforme": "plateforme",
        "Arrivée": "date_arrivee",
        "Départ": "date_depart",
        "Nuits": "nuitees",
        "Brut (€)": "prix_brut",
    }
    df.rename(columns=rename_map, inplace=True)

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = pd.Series([None] * len(df), index=df.index)

    for c in df.columns:
        df[c] = _as_series(df[c], index=df.index)

    for b in ["paye", "sms_envoye", "post_depart_envoye"]:
        df[b] = _to_bool_series(df[b])

    for n in ["prix_brut", "commissions", "frais_cb", "menage", "taxes_sejour", "nuitees", "charges", "%", "base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"] = _to_date(df["date_depart"])

    mask_ok = pd.notna(df["date_arrivee"]) & pd.notna(df["date_depart"])
    if mask_ok.any():
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)

    prix_brut = _to_num(df["prix_brut"])
    commissions = _to_num(df["commissions"])
    frais_cb = _to_num(df["frais_cb"])
    menage = _to_num(df["menage"])
    taxes = _to_num(df["taxes_sejour"])

    df["prix_net"] = (prix_brut - commissions - frais_cb).fillna(0.0)
    df["charges"] = (prix_brut - df["prix_net"]).fillna(0.0)
    df["base"] = (df["prix_net"] - menage - taxes).fillna(0.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        df["%"] = np.where(prix_brut > 0, (df["charges"] / prix_brut * 100), 0.0).astype(float)

    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip() == "")
    if miss_res.any():
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip() == "")
    if miss_uid.any():
        df.loc[miss_uid, "ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    for c in ["nom_client", "plateforme", "telephone", "email", "pays"]:
        df[c] = df[c].astype(str).replace({"nan": "", "None": ""}).str.strip()

    need = df["pays"].eq("") | df["pays"].isna()
    if need.any():
        df.loc[need, "pays"] = df.loc[need, "telephone"].apply(_phone_country)

    return df[BASE_COLS]

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    """Sauvegarde le fichier des réservations du logement actif et nettoie le cache."""
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee", "date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        target = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
        out.to_csv(target, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ============================== PART 2/5 : CHARGEMENT, APPARTEMENTS, VUES LISTES ==============================

@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations: str, csv_plateformes: str):
    """Charge les données de réservations et la palette depuis les CSV fournis."""
    # Crée les fichiers s'ils n'existent pas (structure minimale)
    for fichier, header in [
        (csv_reservations, "nom_client,email,telephone,plateforme,date_arrivee,date_depart,nuitees,prix_brut\n"),
        (csv_plateformes,  "plateforme,couleur\nBooking,#1b9e77\nAirbnb,#d95f02\nAbritel,#7570b3\nDirect,#e7298a\n"),
    ]:
        if not os.path.exists(fichier):
            with open(fichier, "w", encoding="utf-8", newline="") as f:
                f.write(header)

    raw = _load_file_bytes(csv_reservations)
    base_df = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base_df)

    # palette
    palette = DEFAULT_PALETTE.copy()
    rawp = _load_file_bytes(csv_plateformes)
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if {"plateforme", "couleur"}.issubset(pal_df.columns):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception as e:
            st.warning(f"Erreur de palette : {e}")

    return df, palette


# ============================== APARTMENTS (sélecteur sans mot de passe) ==============================

def _read_apartments_csv() -> pd.DataFrame:
    """Lit apartments.csv et normalise les colonnes slug/name."""
    try:
        if not os.path.exists(APARTMENTS_CSV):
            return pd.DataFrame(columns=["slug", "name"])
        raw = _load_file_bytes(APARTMENTS_CSV)
        df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame(columns=["slug", "name"])

        df.columns = [str(c).strip().lower() for c in df.columns]
        if "slug" not in df.columns:
            df["slug"] = ""
        if "name" not in df.columns:
            df["name"] = ""

        df["slug"] = (
            df["slug"].astype(str)
            .str.replace("\ufeff", "", regex=False)
            .str.strip()
            .str.replace(" ", "-", regex=False)
            .str.replace("_", "-", regex=False)
            .str.lower()
        )
        df["name"] = df["name"].astype(str).str.replace("\ufeff", "", regex=False).str.strip()

        df = df[(df["slug"] != "") & (df["name"] != "")]
        df = df.drop_duplicates(subset=["slug"], keep="first")
        return df[["slug", "name"]]
    except Exception:
        return pd.DataFrame(columns=["slug", "name"])


def _current_apartment() -> dict | None:
    """Renvoie l’appartement courant (slug, name) depuis la session, sinon None."""
    slug = st.session_state.get("apt_slug", "")
    name = st.session_state.get("apt_name", "")
    if slug and name:
        return {"slug": slug, "name": name}
    return None


def _select_apartment_sidebar() -> bool:
    """
    Affiche le sélecteur d'appartement dans la sidebar et met à jour les chemins
    CSV_RESERVATIONS / CSV_PLATEFORMES dans la session.
    Retourne True si la sélection a changé.
    """
    st.sidebar.markdown("### Appartement")
    apts = _read_apartments_csv()
    if apts.empty:
        st.sidebar.warning("Aucun appartement trouvé dans apartments.csv")
        return False

    options = apts["slug"].tolist()
    labels = {r["slug"]: r["name"] for _, r in apts.iterrows()}

    # index par défaut robuste
    cur_slug = st.session_state.get("apt_slug", options[0])
    if cur_slug not in options:
        cur_slug = options[0]
    default_idx = options.index(cur_slug)

    slug = st.sidebar.selectbox(
        "Choisir un appartement",
        options=options,
        index=default_idx,
        format_func=lambda s: labels.get(s, s),
        key="apt_slug_selectbox",
    )
    name = labels.get(slug, slug)

    changed = (slug != st.session_state.get("apt_slug", "") or name != st.session_state.get("apt_name", ""))

    # mémorise et synchronise les chemins actifs
    st.session_state["apt_slug"] = slug
    st.session_state["apt_name"] = name
    st.session_state["CSV_RESERVATIONS"] = f"reservations_{slug}.csv"
    st.session_state["CSV_PLATEFORMES"] = f"plateformes_{slug}.csv"

    # met à jour les globales utilisées par certaines fonctions
    global CSV_RESERVATIONS, CSV_PLATEFORMES
    CSV_RESERVATIONS = st.session_state["CSV_RESERVATIONS"]
    CSV_PLATEFORMES = st.session_state["CSV_PLATEFORMES"]

    st.sidebar.success(f"Connecté : **{name}**")
    try:
        print_buttons(location="sidebar")
    except Exception:
        pass

    return changed


def _load_data_for_active_apartment():
    """Lit les CSV selon l’appartement actif, avec fallback si besoin."""
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_pal = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
    try:
        return charger_donnees(csv_res, csv_pal)
    except TypeError:
        return charger_donnees(CSV_RESERVATIONS, CSV_PLATEFORMES)
    except Exception:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE.copy()


# ============================== VUES PRINCIPALES (listes, éditions) ==============================

def vue_accueil(df: pd.DataFrame, palette: dict):
    """Vue d’accueil avec arrivées/départs du jour et J+1."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()
    render_print_header()

    today = date.today()
    tomorrow = today + timedelta(days=1)
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"] = _to_date(dfv["date_depart"])

    arr = dfv[dfv["date_arrivee"] == today][["nom_client", "telephone", "plateforme", "pays"]]
    dep = dfv[dfv["date_depart"] == today][["nom_client", "telephone", "plateforme", "pays"]]
    arr_plus1 = dfv[dfv["date_arrivee"] == tomorrow][["nom_client", "telephone", "plateforme", "pays"]]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame({"info": ["Aucune arrivée."]}), use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame({"info": ["Aucun départ."]}), use_container_width=True)
    with c3:
        st.subheader("🟠 Arrivées J+1 (demain)")
        st.dataframe(arr_plus1 if not arr_plus1.empty else pd.DataFrame({"info": ["Aucune arrivée demain."]}),
                     use_container_width=True)


def vue_reservations(df: pd.DataFrame, palette: dict):
    """Liste complète des réservations + KPIs (totaux)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()
    render_print_header()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")

    years_avail = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1, 13))
    plats_avail = sorted(dfa["plateforme"].astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())

    c1, c2, c3, c4 = st.columns(4)
    year = c1.selectbox("Année", ["Toutes"] + years_avail, index=0)
    month = c2.selectbox("Mois", ["Tous"] + months_avail, index=0)
    plat = c3.selectbox("Plateforme", ["Toutes"] + plats_avail, index=0)
    payf = c4.selectbox("Paiement", ["Tous", "Payé uniquement", "Non payé uniquement"], index=0)

    data = dfa.copy()
    if year != "Toutes":
        data = data[data["date_arrivee_dt"].dt.year == int(year)]
    if month != "Tous":
        data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]
    if payf == "Payé uniquement":
        data = data[_to_bool_series(data["paye"]) == True]
    elif payf == "Non payé uniquement":
        data = data[_to_bool_series(data["paye"]) == False]

    brut = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net = float(pd.to_numeric(data["prix_net"], errors="coerce").fillna(0).sum())
    base = float(pd.to_numeric(data["base"], errors="coerce").fillna(0).sum())
    nuits = int(pd.to_numeric(data["nuitees"], errors="coerce").fillna(0).sum())
    adr = (net / nuits) if nuits > 0 else 0.0
    charges = float(pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum())

    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
          <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
          <span class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></span>
          <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
          <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
          <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
        </div>
        """.replace(",", " "),
        unsafe_allow_html=True,
    )
    st.markdown("---")

    order_idx = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order_idx]

    # Masquage colonnes techniques à l’écran
    hide_cols = ["res_id", "ical_uid", "%", "charges", "base"]
    to_show = [c for c in data.columns if c not in hide_cols]
    st.dataframe(data[to_show], use_container_width=True)


def vue_ajouter(df: pd.DataFrame, palette: dict):
    """Formulaire d’ajout d’une réservation."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter une réservation — {apt_name}")
    print_buttons()

    with st.form("form_add", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel = st.text_input("Téléphone")
            arr = st.date_input("Arrivée", date.today())
            dep = st.date_input("Départ", date.today() + timedelta(days=1))
        with c2:
            plat = st.selectbox("Plateforme", list(palette.keys()))
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye = st.checkbox("Payé", value=False)

        if st.form_submit_button("✅ Ajouter"):
            if not nom or dep <= arr:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nuitees = (dep - arr).days
                new = pd.DataFrame(
                    [
                        {
                            "nom_client": nom,
                            "email": email,
                            "telephone": tel,
                            "plateforme": plat,
                            "date_arrivee": arr,
                            "date_depart": dep,
                            "nuitees": nuitees,
                            "prix_brut": brut,
                            "commissions": commissions,
                            "frais_cb": frais_cb,
                            "menage": menage,
                            "taxes_sejour": taxes,
                            "paye": paye,
                        }
                    ]
                )
                df2 = ensure_schema(pd.concat([df, new], ignore_index=True))
                if sauvegarder_donnees(df2):
                    st.success(f"Réservation pour {nom} ajoutée.")
                    st.rerun()


def vue_modifier(df: pd.DataFrame, palette: dict):
    """Modifier/Supprimer une réservation existante."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()
    if df.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client','')} ({r.get('date_arrivee','')})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not sel:
        return

    idx = int(sel.split(":")[0])
    original_idx = df_sorted.loc[idx, "index"]
    row = df.loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get("nom_client", "") or "")
            email = st.text_input("Email", value=row.get("email", "") or "")
            tel = st.text_input("Téléphone", value=row.get("telephone", "") or "")
            arrivee = st.date_input("Arrivée", value=row.get("date_arrivee"))
            depart = st.date_input("Départ", value=row.get("date_depart"))
        with c2:
            palette_keys = list(palette.keys())
            plat_idx = palette_keys.index(row.get("plateforme")) if row.get("plateforme") in palette_keys else 0
            plat = st.selectbox("Plateforme", options=palette_keys, index=plat_idx)
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut = float(pd.to_numeric(row.get("prix_brut"), errors="coerce") or 0)
            commissions = float(pd.to_numeric(row.get("commissions"), errors="coerce") or 0)
            frais_cb = float(pd.to_numeric(row.get("frais_cb"), errors="coerce") or 0)
            menage = float(pd.to_numeric(row.get("menage"), errors="coerce") or 0)
            taxes = float(pd.to_numeric(row.get("taxes_sejour"), errors="coerce") or 0)
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=brut)
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=commissions)
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=frais_cb)
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=menage)
            taxes = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=taxes)

        csave, cdel = st.columns([0.7, 0.3])
        if csave.form_submit_button("💾 Enregistrer"):
            updates = {
                "nom_client": nom,
                "email": email,
                "telephone": tel,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "plateforme": plat,
                "paye": paye,
                "prix_brut": brut,
                "commissions": commissions,
                "frais_cb": frais_cb,
                "menage": menage,
                "taxes_sejour": taxes,
            }
            for k, v in updates.items():
                df.loc[original_idx, k] = v
            if sauvegarder_donnees(df):
                st.success("Modifié ✅")
                st.rerun()

        if cdel.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé.")
                st.rerun()


def vue_plateformes(df: pd.DataFrame, palette: dict):
    """Edition des couleurs par plateforme."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes & couleurs — {apt_name}")
    print_buttons()

    HAS_COLORCOL = hasattr(getattr(st, "column_config", object), "ColorColumn")

    # Collecte des plateformes vues dans les données + celles existantes
    plats_df = sorted(
        df.get("plateforme", pd.Series([], dtype=str))
        .astype(str)
        .str.strip()
        .replace({"nan": ""})
        .dropna()
        .unique()
        .tolist()
    )
    all_plats = sorted(set(list(palette.keys()) + plats_df))
    base = pd.DataFrame(
        {"plateforme": all_plats, "couleur": [palette.get(p, "#666666") for p in all_plats]}
    )

    if HAS_COLORCOL:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorColumn("Couleur (hex)"),
        }
    else:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn(
                "Couleur (hex)", help="Ex: #1b9e77", validate=r"^#([0-9A-Fa-f]{6})$", width="small"
            ),
        }

    edited = st.data_editor(
        base, num_rows="dynamic", use_container_width=True, hide_index=True, column_config=col_cfg, key="palette_editor"
    )

    # Aperçu (si pas de ColorColumn natif)
    if not HAS_COLORCOL and not edited.empty:
        chips = []
        for _, r in edited.iterrows():
            plat = str(r["plateforme"]).strip()
            col = str(r["couleur"]).strip()
            if not plat:
                continue
            ok = bool(re.match(r"^#([0-9A-Fa-f]{6})$", col or ""))
            chips.append(
                "<span style='display:inline-block;margin:4px 6px;padding:6px 10px;"
                f"border-radius:12px;background:{col if ok else '#666'};color:#fff;'>{plat} {col}</span>"
            )
        if chips:
            st.markdown("".join(chips), unsafe_allow_html=True)

    c1, c2, c3 = st.columns([0.5, 0.3, 0.2])
    if c1.button("💾 Enregistrer la palette", key="save_palette_btn"):
        try:
            to_save = edited.copy()
            to_save["plateforme"] = to_save["plateforme"].astype(str).str.strip()
            to_save["couleur"] = to_save["couleur"].astype(str).str.strip()
            to_save = to_save[to_save["plateforme"] != ""].drop_duplicates(subset=["plateforme"])
            if not HAS_COLORCOL:
                ok = to_save["couleur"].str.match(r"^#([0-9A-Fa-f]{6})$")
                to_save.loc[~ok, "couleur"] = "#666666"
            target = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
            to_save.to_csv(target, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("↩️ Palette par défaut", key="restore_palette_btn"):
        try:
            target = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme", "couleur"]).to_csv(
                target, sep=";", index=False, encoding="utf-8", lineterminator="\n"
            )
            st.success("Palette restaurée.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c3.button("🔄 Recharger", key="reload_palette_btn"):
        st.cache_data.clear()
        st.rerun()

# ============================== PART 3/5 : CALENDRIER & EXPORT ICS ==============================

def vue_calendrier(df: pd.DataFrame, palette: dict):
    """Calendrier mensuel en grille + récap du mois sélectionné."""
    from calendar import Calendar, monthrange
    from html import escape

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier (grille mensuelle) — {apt_name}")
    print_buttons()
    render_print_header()

    dfv = df.dropna(subset=["date_arrivee", "date_depart"]).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    # Casting dates
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"] = _to_date(dfv["date_depart"])

    # Choix période
    today = date.today()
    years = sorted(
        pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique()
    )
    if not years:
        years = [today.year]
    default_year_idx = 0 if years and years[0] == today.year else 0
    annee = st.selectbox("Année", options=years, index=default_year_idx)
    mois = st.selectbox("Mois", options=list(range(1, 12 + 1)), index=today.month - 1)

    # En-tête jours
    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div>"
        "<div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True,
    )

    # Sélecteur de réservations pour un jour donné
    def day_resas(d):
        mask = (dfv["date_arrivee"] <= d) & (dfv["date_depart"] > d)
        return dfv[mask]

    # Grille calendrier
    cal = Calendar(firstweekday=0)  # 0 = lundi
    html_parts = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(annee, mois):
        for d in week:
            outside = (d.month != mois)
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'>"
            cell += f"<div class='cal-date'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                if not rs.empty:
                    for _, r in rs.iterrows():
                        color = palette.get(str(r.get("plateforme") or ""), "#888")
                        name = str(r.get("nom_client") or "")[:22]
                        title_txt = escape(str(r.get("nom_client") or ""), quote=True)
                        cell += (
                            "<div class='resa-pill' "
                            f"style='background:{color}' "
                            f"title='{title_txt}'>"
                            f"{name}</div>"
                        )
            cell += "</div>"
            html_parts.append(cell)
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Détail du mois sélectionné")

    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfv[(dfv["date_arrivee"] <= fin_mois) & (dfv["date_depart"] > debut_mois)].copy()

    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        plats = ["Toutes"] + sorted(rows["plateforme"].dropna().astype(str).unique().tolist())
        plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
        if plat != "Toutes":
            rows = rows[rows["plateforme"] == plat]

        # KPIs du mois
        brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
        net = float(pd.to_numeric(rows["prix_net"], errors="coerce").fillna(0).sum())
        nuits = int(pd.to_numeric(rows["nuitees"], errors="coerce").fillna(0).sum())

        st.markdown(
            f"""
            <div class='glass'>
              <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
              <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
              <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
            </div>
            """.replace(",", " "),
            unsafe_allow_html=True,
        )

        st.dataframe(
            rows[
                ["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "paye", "pays"]
            ],
            use_container_width=True,
        )


def vue_export_ics(df: pd.DataFrame, palette: dict):
    """Export de réservations au format .ics (par année et filtre plateforme)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📆 Export ICS — {apt_name}")
    print_buttons()
    render_print_header()

    if df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    years = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique(), reverse=True)
    year = st.selectbox("Année (arrivées)", years if years else [date.today().year], index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().astype(str).unique())
    plat = st.selectbox("Plateforme", plats, index=0)

    data = dfa[dfa["date_arrivee_dt"].dt.year == int(year)].copy()
    if plat != "Tous":
        data = data[data["plateforme"] == plat]
    if data.empty:
        st.warning("Rien à exporter.")
        return

    # UIDs manquants
    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip() == "")
    if miss.any():
        data.loc[miss, "ical_uid"] = data.loc[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _fmt(d):
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, date):
            return f"{d.year:04d}{d.month:02d}{d.day:02d}"
        try:
            return pd.to_datetime(d, errors="coerce").strftime("%Y%m%d")
        except Exception:
            return ""

    def _esc(s):
        if s is None:
            return ""
        return (
            str(s)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(",", "\\,")
            .replace(";", "\\;")
        )

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        "CALSCALE:GREGORIAN",
    ]
    for _, r in data.iterrows():
        dt_a = pd.to_datetime(r["date_arrivee"], errors="coerce")
        dt_d = pd.to_datetime(r["date_depart"], errors="coerce")
        if pd.isna(dt_a) or pd.isna(dt_d):
            continue
        summary = f"{apt_name} — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"):
            summary += f" ({r['plateforme']})"
        desc = "\n".join(
            [
                f"Client: {r.get('nom_client','')}",
                f"Téléphone: {r.get('telephone','')}",
                f"Nuitées: {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}",
                f"Prix brut: {float(pd.to_numeric(r.get('prix_brut'), errors='coerce') or 0):.2f} €",
                f"res_id: {r.get('res_id','')}",
            ]
        )
        lines += [
            "BEGIN:VEVENT",
            f"UID:{r['ical_uid']}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt(dt_a)}",
            f"DTEND;VALUE=DATE:{_fmt(dt_d)}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"

    st.download_button(
        "📥 Télécharger .ics",
        data=ics.encode("utf-8"),
        file_name=f"reservations_{year}.ics",
        mime="text/calendar",
    )

# ============================== PART 4/5 : RAPPORT, GOOGLE SHEET, CLIENTS, ID ==============================

def vue_rapport(df: pd.DataFrame, palette: dict):
    """Tableaux de bord et KPIs par plateforme et par pays."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📊 Rapport — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune donnée disponible.")
        return

    dfr = ensure_schema(df).copy()
    dfr["date_arrivee"] = _to_date(dfr["date_arrivee"])
    dfr["date_depart"] = _to_date(dfr["date_depart"])
    dfr["nuitees"] = pd.to_numeric(dfr["nuitees"], errors="coerce").fillna(0).astype(int)
    dfr["revenu"] = pd.to_numeric(dfr["tarif"], errors="coerce").fillna(0)

    # ---- KPIs principaux ----
    total_resa = len(dfr)
    total_nuitees = dfr["nuitees"].sum()
    total_revenu = dfr["revenu"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Réservations", f"{total_resa}")
    c2.metric("Nuitées", f"{total_nuitees}")
    c3.metric("Revenu total", f"{total_revenu:,.0f} €".replace(",", " "))

    st.markdown("---")

    # ---- Agrégation par plateforme ----
    agg = (
        dfr.groupby("plateforme")
        .agg(
            reservations=("plateforme", "count"),
            nuitees=("nuitees", "sum"),
            revenu_total=("revenu", "sum"),
        )
        .reset_index()
    )
    if total_revenu > 0:
        agg["part_revenu_%"] = (agg["revenu_total"] / total_revenu * 100).round(1)
    else:
        agg["part_revenu_%"] = 0

    disp = agg.copy()
    disp["reservations"] = disp["reservations"].astype(int)
    disp["nuitees"] = disp["nuitees"].astype(int)
    disp["revenu_total"] = pd.to_numeric(disp["revenu_total"], errors="coerce").round(0)
    disp["part_revenu_%"] = pd.to_numeric(disp["part_revenu_%"], errors="coerce").round(1)

    st.subheader("Par plateforme")
    st.dataframe(disp, use_container_width=True)

    # ---- Graphique ----
    if not agg.empty:
        fig, ax = plt.subplots()
        ax.pie(
            agg["revenu_total"],
            labels=agg["plateforme"],
            autopct="%1.1f%%",
            colors=[palette.get(p, "#999999") for p in agg["plateforme"]],
        )
        ax.set_title("Répartition du revenu par plateforme")
        st.pyplot(fig)

    st.markdown("---")

    # ---- Agrégation par pays ----
    if "pays" in dfr.columns:
        agg_pays = (
            dfr.groupby("pays")
            .agg(
                reservations=("pays", "count"),
                nuitees=("nuitees", "sum"),
                revenu_total=("revenu", "sum"),
            )
            .reset_index()
        )
        agg_pays = agg_pays.sort_values("revenu_total", ascending=False).head(20)
        if total_revenu > 0:
            agg_pays["part_revenu_%"] = (agg_pays["revenu_total"] / total_revenu * 100).round(1)
        else:
            agg_pays["part_revenu_%"] = 0

        disp2 = agg_pays.copy()
        disp2["reservations"] = disp2["reservations"].astype(int)
        disp2["nuitees"] = disp2["nuitees"].astype(int)
        disp2["revenu_total"] = pd.to_numeric(disp2["revenu_total"], errors="coerce").round(0)
        disp2["part_revenu_%"] = pd.to_numeric(disp2["part_revenu_%"], errors="coerce").round(1)

        st.subheader("Top 20 pays")
        st.dataframe(disp2, use_container_width=True)

        fig2, ax2 = plt.subplots()
        ax2.barh(agg_pays["pays"], agg_pays["revenu_total"], color="skyblue")
        ax2.set_xlabel("Revenu (€)")
        ax2.set_ylabel("Pays")
        st.pyplot(fig2)


# ---------------- GOOGLE SHEET ----------------
def vue_google_sheet(df: pd.DataFrame, palette: dict):
    """Placeholder Google Sheet (future intégration API)."""
    st.header("📝 Google Sheet")
    st.info("⚠️ Fonctionnalité à venir — export automatique vers Google Sheets.")


# ---------------- CLIENTS ----------------
def vue_clients(df: pd.DataFrame, palette: dict):
    """Liste simple des clients avec téléphone et pays."""
    st.header("👥 Clients")
    if df is None or df.empty:
        st.info("Aucun client.")
        return

    dfx = df.copy()
    dfx["pays"] = dfx["telephone"].apply(_phone_country)

    st.dataframe(dfx[["nom_client", "telephone", "pays"]], use_container_width=True)


# ---------------- ID ----------------
def vue_id(df: pd.DataFrame, palette: dict):
    """Affiche les numéros de réservation et ID uniques."""
    st.header("🆔 Identifiants")
    if df is None or df.empty:
        st.info("Aucun enregistrement.")
        return

    st.dataframe(df[["id", "numero_reservation", "plateforme"]], use_container_width=True)




# ============================== PART 5/5 : SMS, INDICATEURS PAYS, PARAMÈTRES, MAIN ==============================

def vue_sms(df: pd.DataFrame, palette: dict):
    """SMS pré-arrivée (J+1) et post-départ — copier/coller + liens SMS/WhatsApp."""
    from urllib.parse import quote

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation disponible.")
        return

    dfx = ensure_schema(df).copy()
    dfx["date_arrivee"] = _to_date(dfx["date_arrivee"])
    dfx["date_depart"] = _to_date(dfx["date_depart"])

    # -------- Pré-arrivée (J+1) --------
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = dfx.dropna(subset=["telephone", "nom_client", "date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (~_to_bool_series(pre["sms_envoye"]))]

    if pre.empty:
        st.info("Aucun client à contacter pour la date sélectionnée.")
    else:
        pre = pre.sort_values("date_arrivee").reset_index()
        options = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=options, index=None, key="pre_pick")
        if pick:
            i = int(pick.split(":")[0])
            r = pre.loc[i]
            link_form = FORM_SHORT_URL
            nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
            arr_txt = r["date_arrivee"].strftime("%d/%m/%Y") if pd.notna(r["date_arrivee"]) else ""
            dep_txt = r["date_depart"].strftime("%d/%m/%Y") if pd.notna(r["date_depart"]) else ""

            # Message FR + EN (texte simple, pas d'apostrophes non échappées)
            msg = (
                f"{apt_name.upper()}\n"
                f"Plateforme : {r.get('plateforme', 'N/A')}\n"
                f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuitees}\n\n"
                f"Bonjour {r.get('nom_client','')}\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre réception, "
                "nous vous demandons de bien vouloir remplir la fiche que vous trouverez en cliquant sur le lien suivant :\n"
                f"{link_form}\n\n"
                "Un parking est à votre disposition sur place.\n\n"
                "Le check-in se fait à partir de 14:00 et le check-out avant 11:00. Nous serons sur place lors de "
                "votre arrivée pour vous remettre les cles.\n\n"
                "Vous trouverez des consignes à bagages dans chaque quartier, à Nice.\n\n"
                "Nous vous souhaitons un excellent voyage et nous nous rejouissons de vous rencontrer tres bientot.\n\n"
                "Annick & Charley\n\n"
                "******\n\n"
                "Welcome to our establishment!\n\n"
                "We are delighted to welcome you soon to Nice. In order to organize your reception as efficiently as possible, "
                "we kindly ask you to fill out the form at the following link:\n"
                f"{link_form}\n\n"
                "Parking is available on site.\n\n"
                "Check-in is from 2:00 p.m. and check-out is before 11:00 a.m. We will be there when you arrive to give you the keys.\n\n"
                "You will find luggage storage facilities in every district of Nice.\n\n"
                "We wish you a pleasant journey and look forward to meeting you very soon.\n\n"
                "Annick & Charley"
            )

            st.text_area("📋 Copier le message", value=msg, height=360, key="pre_msg")
            e164 = _format_phone_e164(r.get("telephone", ""))
            only_digits = "".join(ch for ch in e164 if ch.isdigit())
            enc = quote(msg)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}", key="pre_sms_ios")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}", key="pre_sms_android")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits}?text={enc}", key="pre_wa")

            if st.button("✅ Marquer 'SMS envoyé' pour ce client", key="pre_mark_sent"):
                try:
                    df.loc[r["index"], "sms_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    st.markdown("---")

    # -------- Post-départ (J0) --------
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = dfx.dropna(subset=["telephone", "nom_client", "date_depart"]).copy()
    post = post[(post["date_depart"] == target_depart) & (~_to_bool_series(post["post_depart_envoye"]))]

    if post.empty:
        st.info("Aucun message post-départ à envoyer aujourd'hui.")
    else:
        post = post.sort_values("date_depart").reset_index()
        options2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=options2, index=None, key="post_pick")
        if pick2:
            j = int(pick2.split(":")[0])
            r2 = post.loc[j]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Un grand merci d'avoir choisi notre appartement pour votre sejour.\n"
                "Nous esperons que vous avez passe un moment agreable.\n"
                "Si vous souhaitez revenir explorer encore un peu la ville, notre porte vous sera toujours grande ouverte.\n\n"
                "Au plaisir de vous accueillir a nouveau.\n\n"
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n"
                "We hope you had a great time — our door is always open if you want to come back.\n\n"
                "Annick & Charley"
            )
            st.text_area("📋 Copier le message", value=msg2, height=280, key="post_msg")
            e164b = _format_phone_e164(r2.get("telephone", ""))
            only_digits_b = "".join(ch for ch in e164b if ch.isdigit())
            enc2 = quote(msg2)
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits_b}?text={enc2}", key="post_wa")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}", key="post_sms_ios")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}", key="post_sms_android")

            if st.button("✅ Marquer 'post-départ envoyé' pour ce client", key="post_mark_sent"):
                try:
                    df.loc[r2["index"], "post_depart_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")


# ---------------- INDICATEURS / INDICATIFS PAYS ----------------

def _load_indicatifs_df() -> pd.DataFrame:
    """Charge le CSV d'indicatifs pays (crée un squelette si absent)."""
    path = INDICATIFS_CSV if os.path.exists(INDICATIFS_CSV) else "indicatifs_pays.csv"
    if not os.path.exists(path):
        base = pd.DataFrame(
            [
                {"code": "FR", "country": "France", "dial": "+33", "flag": "🇫🇷"},
                {"code": "GB", "country": "United Kingdom", "dial": "+44", "flag": "🇬🇧"},
                {"code": "ES", "country": "Spain", "dial": "+34", "flag": "🇪🇸"},
            ]
        )
        base.to_csv(path, index=False, encoding="utf-8")
    try:
        return pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=["code", "country", "dial", "flag"])

def _save_indicatifs_df(df_in: pd.DataFrame) -> bool:
    """Valide et sauvegarde le CSV des indicatifs."""
    try:
        df = df_in.copy()
        df = df[["code", "country", "dial", "flag"]]
        df["code"] = df["code"].astype(str).str.strip().str.upper()
        df["country"] = df["country"].astype(str).str.strip()
        df["dial"] = df["dial"].astype(str).str.strip()
        df["flag"] = df["flag"].astype(str).str.strip()

        df = df[df["code"] != ""]
        df = df.drop_duplicates(subset=["code"], keep="first")

        # normalisation dial : commence par +
        df.loc[~df["dial"].str.startswith("+"), "dial"] = "+" + df["dial"].str.lstrip("+").str.strip()

        df.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8")
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde des indicatifs : {e}")
        return False

def vue_indicatifs(df: pd.DataFrame, palette: dict):
    """Edition et rechargement des indicatifs pays (code, country, dial, flag)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🌍 Indicateurs pays — {apt_name}")
    st.caption("Ajoutez/éditez les pays, indicatifs et drapeaux. Le CSV est chargé et sauvegardé sur disque.")

    base = _load_indicatifs_df()
    with st.expander("Aperçu", expanded=True):
        st.dataframe(base, use_container_width=True)

    st.markdown("### Modifier")
    edited = st.data_editor(
        base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "code": st.column_config.TextColumn("Code"),
            "country": st.column_config.TextColumn("Pays"),
            "dial": st.column_config.TextColumn("Indicatif"),
            "flag": st.column_config.TextColumn("Drapeau (emoji)"),
        },
        key="indicatifs_editor",
    )

    c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
    if c1.button("💾 Enregistrer", key="btn_save_indicatifs"):
        if _save_indicatifs_df(edited):
            st.success("Indicatifs sauvegardés ✅")

    if c2.button("🔄 Recharger depuis le disque", key="btn_reload_indicatifs"):
        st.cache_data.clear()
        st.rerun()

    if c3.button("↩️ Restaurer FR/GB/ES (mini)", key="btn_restore_min_indicatifs"):
        mini = pd.DataFrame(
            [
                {"code": "FR", "country": "France", "dial": "+33", "flag": "🇫🇷"},
                {"code": "GB", "country": "United Kingdom", "dial": "+44", "flag": "🇬🇧"},
                {"code": "ES", "country": "Spain", "dial": "+34", "flag": "🇪🇸"},
            ]
        )
        if _save_indicatifs_df(mini):
            st.success("Mini-jeu de données restauré ✅")
            st.rerun()


# ---------------- PARAMÈTRES ----------------

def vue_settings(df: pd.DataFrame, palette: dict):
    """Sauvegarde / restauration des données + maintenance apartments.csv + cache."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header("## ⚙️ Paramètres")
    st.subheader(apt_name)
    print_buttons()
    st.caption("Sauvegarde, restauration, cache et outil secours pour apartments.csv.")

    # Export CSV
    st.markdown("### 💾 Sauvegarde (exports)")
    try:
        out = ensure_schema(df).copy()
        out["pays"] = out["telephone"].apply(_phone_country)
        for col in ["date_arrivee", "date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        csv_bytes = out.to_csv(sep=";", index=False).encode("utf-8")
    except Exception:
        csv_bytes = b""

    c1, c2 = st.columns(2)
    c1.download_button(
        "⬇️ Exporter réservations (CSV)",
        data=csv_bytes,
        file_name=os.path.basename(st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)),
        mime="text/csv",
        key="dl_res_csv",
    )

    # Export XLSX
    try:
        out_xlsx = ensure_schema(df).copy()
        out_xlsx["pays"] = out_xlsx["telephone"].apply(_phone_country)
        for col in ["date_arrivee", "date_depart"]:
            out_xlsx[col] = pd.to_datetime(out_xlsx[col], errors="coerce").dt.strftime("%d/%m/%Y")
        xlsx_bytes, _ = _df_to_xlsx_bytes(out_xlsx, sheet_name="Reservations")
    except Exception:
        xlsx_bytes = None

    c2.download_button(
        "⬇️ Exporter réservations (XLSX)",
        data=xlsx_bytes or b"",
        file_name=(os.path.splitext(os.path.basename(st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)))[0] + ".xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(xlsx_bytes is None),
        key="dl_res_xlsx",
    )

    # Restauration
    st.markdown("### ♻️ Restauration (remplacer les données)")
    up = st.file_uploader("Restaurer (CSV ou XLSX)", type=["csv", "xlsx"], key="restore_uploader_settings")
    if up is not None:
        try:
            if up.name.lower().endswith(".xlsx"):
                xls = pd.ExcelFile(up)
                sheet = st.selectbox("Feuille Excel", xls.sheet_names, index=0, key="restore_sheet_settings")
                tmp = pd.read_excel(xls, sheet_name=sheet, dtype=str)
            else:
                raw = up.read()
                tmp = _detect_delimiter_and_read(raw)

            prev = ensure_schema(tmp)
            st.success(f"Aperçu chargé ({up.name})")
            with st.expander("Aperçu (10 premières lignes)", expanded=False):
                st.dataframe(prev.head(10), use_container_width=True)

            if st.button("✅ Confirmer la restauration", key="confirm_restore_settings"):
                try:
                    save = prev.copy()
                    for col in ["date_arrivee", "date_depart"]:
                        save[col] = pd.to_datetime(save[col], errors="coerce").dt.strftime("%d/%m/%Y")
                    target_csv = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
                    save.to_csv(target_csv, sep=";", index=False, encoding="utf-8", lineterminator="\n")
                    st.cache_data.clear()
                    st.success("Fichier restauré — rechargement…")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur écriture : {e}")
        except Exception as e:
            st.error(f"Erreur restauration : {e}")

    # Cache
    st.markdown("### 🧹 Vider le cache")
    if st.button("Vider le cache & recharger", key="clear_cache_btn_settings"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    # Outil secours apartments.csv
    st.markdown("### 🧰 Écraser apartments.csv (outil secours)")
    default_csv = "slug,name\nvilla-tobias,Villa Tobias\nle-turenne,Le Turenne\n"
    txt = st.text_area("Contenu apartments.csv", value=default_csv, height=140, key="force_apts_txt_settings")
    if st.button("🧰 Écraser apartments.csv", key="force_apts_btn_settings"):
        try:
            with open(APARTMENTS_CSV, "w", encoding="utf-8", newline="") as f:
                f.write(txt.strip() + "\n")
            st.cache_data.clear()
            st.success("apartments.csv écrasé ✅ — rechargement…")
            st.rerun()
        except Exception as e:
            st.error(f"Impossible d'écrire apartments.csv : {e}")


# ------------------------------- MAIN ---------------------------------

def main():
    # Reset cache via URL ?clear=1
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1", "true", "True", "yes"):
        try:
            st.cache_data.clear()
        except Exception:
            pass

    # Sélecteur d'appartement (met à jour chemins actifs)
    changed = _select_apartment_sidebar()
    if changed:
        try:
            st.cache_data.clear()
        except Exception:
            pass

    # Thème (applique le CSS défini plus haut)
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    # En-tête
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    # Données + palette
    df, palette_loaded = _load_data_for_active_apartment()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    # Pages
    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "📝 Google Sheet": vue_google_sheet,
        "👥 Clients": vue_clients,
        "🆔 ID": vue_id,
        "🌍 Indicateurs pays": vue_indicatifs,
        "⚙️ Paramètres": vue_settings,
    }

    choice = st.sidebar.radio("Aller à", list(pages.keys()), key="nav_radio")
    page_func = pages.get(choice)
    if page_func:
        page_func(df, palette)
    else:
        st.error("Page inconnue.")


if __name__ == "__main__":
    main()