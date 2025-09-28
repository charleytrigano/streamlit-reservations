# ============================== PART 1/5 - IMPORTS, CONFIG, STYLES, HELPERS ==============================

import os
import io
import re
import uuid
import hashlib
from html import escape
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange
from urllib.parse import quote

import pandas as pd
import numpy as np
import streamlit as st
import matplotlib.pyplot as plt
import altair as alt

# ============================== CONFIG APP ==============================
st.set_page_config(
    page_title="Villa Tobias - Gestion des Reservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================== CONSTANTES ==============================
# Chemins par defaut (remplaces par appartement actif)
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"
APARTMENTS_CSV   = "apartments.csv"
INDICATIFS_CSV   = "indicatifs_pays.csv"   # ton fichier d'indicatifs

DEFAULT_PALETTE = {
    "Booking": "#1b9e77",
    "Airbnb":  "#d95f02",
    "Abritel": "#7570b3",
    "Direct":  "#e7298a",
}

# Liens Google (adapter si besoin)
FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# ============================== STYLE ==============================
def apply_style(light: bool):
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    st.markdown(
        f"""
        <style>
          html, body, [data-testid="stAppViewContainer"] {{ background:{bg}; color:{fg}; }}
          [data-testid="stSidebar"] {{ background:{side}; border-right:1px solid {border}; }}
          .glass {{ background:{"rgba(255,255,255,.65)" if light else "rgba(255,255,255,.06)"}; 
                   border:1px solid {border}; border-radius:12px; padding:12px; margin:10px 0; }}
          .chip {{ display:inline-block; padding:6px 10px; border-radius:12px; margin:4px 6px; 
                   font-size:.86rem; background:{"#eee" if light else "#2a2f3a"}; color:{"#222" if light else "#eee"} }}
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; }}
          .cal-cell {{ border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px; position:relative; overflow:hidden; background:{"#fff" if light else "#0b0d12"}; }}
          .cal-cell.outside {{ opacity:.45; }}
          .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
          .resa-pill {{ padding:4px 6px; border-radius:6px; font-size:.84rem; margin-top:22px; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
          .cal-header {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; font-weight:700; opacity:.8; margin:6px 0 8px; }}

          @page {{ size: A4 landscape; margin: 10mm; }}
          @media print {{
            [data-testid="stSidebar"], header, footer {{ display:none !important; }}
            .print-header {{ display:block; margin-bottom:8px; }}
            .stDataFrame, .stTable {{ font-size: 12px; }}
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

def print_buttons(location: str = "main"):
    target = st.sidebar if location == "sidebar" else st
    target.button("🖨️ Imprimer", key=f"print_btn_{location}")
    st.markdown(
        """
        <script>
        const labels = Array.from(parent.document.querySelectorAll('button span, button p'));
        const btn = labels.find(n => n.textContent && n.textContent.trim() === "🖨️ Imprimer");
        if (btn) { btn.parentElement.onclick = () => window.print(); }
        </script>
        """,
        unsafe_allow_html=True
    )

# ============================== HELPERS DATA ==============================
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
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff","")
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
    out = s.astype(str).str.strip().str.lower().isin(["true","1","oui","vrai","yes","y","t"])
    return out.fillna(False).astype(bool)

def _to_num(s: pd.Series) -> pd.Series:
    s = _as_series(s)
    sc = (s.astype(str).str.replace("€","",regex=False)
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
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def _df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Reservations"):
    from io import BytesIO
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        return buf.getvalue(), None
    except Exception as e:
        st.warning(f"Impossible de generer un Excel (openpyxl requis) : {e}")
        return None, e

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s:
        return ""
    if s.startswith("33"):
        return "+"+s
    if s.startswith("0"):
        return "+33"+s[1:]
    return "+"+s

# ============================== INDICATIFS PAYS ==============================
@st.cache_data(show_spinner=False)
def load_indicatifs_df(version: int = 0, path: str = INDICATIFS_CSV) -> pd.DataFrame:
    """
    Charge le CSV d'indicatifs {code,country,dial,flag}.
    'version' permet d'invalider ce cache depuis l'UI.
    """
    try:
        df = pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=["code", "country", "dial", "flag"])

    df.columns = [c.strip().lower() for c in df.columns]
    for col in ["code", "country", "dial"]:
        if col not in df.columns:
            df[col] = ""

    df["dial_digits"] = (
        df["dial"].astype(str)
        .str.replace("+", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace("-", "", regex=False)
    )
    df["code"] = df["code"].astype(str).str.strip().str.upper()
    df["country"] = df["country"].astype(str).str.strip()
    df["flag"] = df.get("flag", "").astype(str).str.strip()

    df = df[(df["dial_digits"] != "") & (df["country"] != "")]
    df = df.drop_duplicates(subset=["dial_digits"], keep="first")
    return df

def _clean_phone_for_match(phone: str) -> str:
    s = re.sub(r"\D", "", str(phone or ""))
    if s.startswith("00"):
        s = s[2:]
    return s

def _phone_country(phone: str) -> str:
    """
    Detecte le pays via l'indicatif en prenant le prefixe le plus long.
    Si numero commence par '0' => France. Sinon Inconnu si non trouve.
    """
    p_raw = str(phone or "").strip()
    if not p_raw:
        return "Inconnu"
    if p_raw.startswith("0"):
        return "France"

    s = _clean_phone_for_match(p_raw)
    if not s:
        return "Inconnu"

    ver = st.session_state.get("indicatifs_reload_n", 0)
    ind = load_indicatifs_df(version=ver)
    if ind.empty:
        return "France" if s.startswith("33") else "Inconnu"

    codes = ind["dial_digits"].tolist()
    max_len = max((len(c) for c in codes), default=2)
    max_len = min(5, max_len)

    for L in range(max_len, 0, -1):
        pref = s[:L]
        hit = ind[ind["dial_digits"] == pref]
        if not hit.empty:
            return hit.iloc[0]["country"] or "Inconnu"

    return "France" if s.startswith("33") else "Inconnu"



# ============================== PART 2/5 - NORMALISATION, SAUVEGARDE, CHARGEMENT, APPARTEMENTS ==============================

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Garantit le schema BASE_COLS et recalcule les derivees."""
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Renommages frequents eventuels
    rename_map = {
        "Payé": "paye",
        "Client": "nom_client",
        "Plateforme": "plateforme",
        "Arrivee": "date_arrivee",
        "Arrivée": "date_arrivee",
        "Depart": "date_depart",
        "Départ": "date_depart",
        "Nuits": "nuitees",
        "Brut (€)": "prix_brut",
        "Tarif": "prix_brut",
    }
    df.rename(columns=rename_map, inplace=True)

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = pd.Series([None] * len(df), index=df.index)

    # Serie pour toutes les colonnes
    for c in df.columns:
        df[c] = _as_series(df[c], index=df.index)

    # Bools
    for b in ["paye", "sms_envoye", "post_depart_envoye"]:
        df[b] = _to_bool_series(df[b])

    # Numeriques
    for n in ["prix_brut", "commissions", "frais_cb", "menage", "taxes_sejour", "nuitees", "charges", "%", "base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Nuitees auto si possible
    mask_ok = pd.notna(df["date_arrivee"]) & pd.notna(df["date_depart"])
    if mask_ok.any():
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)

    # Calculs derivees
    prix_brut   = _to_num(df["prix_brut"])
    commissions = _to_num(df["commissions"])
    frais_cb    = _to_num(df["frais_cb"])
    menage      = _to_num(df["menage"])
    taxes       = _to_num(df["taxes_sejour"])

    df["prix_net"] = (prix_brut - commissions - frais_cb).fillna(0.0)
    df["charges"]  = (prix_brut - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - menage - taxes).fillna(0.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        df["%"] = np.where(prix_brut > 0, (df["charges"] / prix_brut * 100), 0.0).astype(float)

    # IDs manquants
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip() == "")
    if miss_res.any():
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip() == "")
    if miss_uid.any():
        df.loc[miss_uid, "ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # Strings nettoyees
    for c in ["nom_client", "plateforme", "telephone", "email", "pays"]:
        df[c] = df[c].astype(str).replace({"nan": "", "None": ""}).str.strip()

    # Pays via indicatif si vide
    need = df["pays"].eq("") | df["pays"].isna()
    if need.any():
        df.loc[need, "pays"] = df.loc[need, "telephone"].apply(_phone_country)

    return df[BASE_COLS]


def _current_res_path() -> str:
    """Chemin CSV reservations actif (par appartement)."""
    return st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)


def _current_pal_path() -> str:
    """Chemin CSV plateformes actif (par appartement)."""
    return st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)


def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    """Sauvegarde le CSV de reservations au chemin actif."""
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee", "date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(_current_res_path(), sep=";", index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False


@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations: str, csv_plateformes: str):
    """Charge reservations et palette. Cree des fichiers minimaux s'ils n'existent pas."""
    # Creer fichiers vides structures minimales
    for fichier, header in [
        (csv_reservations, "nom_client,email,telephone,plateforme,date_arrivee,date_depart,nuitees,prix_brut\n"),
        (csv_plateformes,  "plateforme,couleur\nBooking,#1b9e77\nAirbnb,#d95f02\nAbritel,#7570b3\nDirect,#e7298a\n"),
    ]:
        if not os.path.exists(fichier):
            try:
                with open(fichier, "w", encoding="utf-8", newline="") as f:
                    f.write(header)
            except Exception:
                pass

    # Reservations
    raw = _load_file_bytes(csv_reservations)
    base_df = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base_df)

    # Palette
    rawp = _load_file_bytes(csv_plateformes)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if {"plateforme", "couleur"}.issubset(pal_df.columns):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception as e:
            st.warning(f"Erreur de palette : {e}")

    return df, palette


# ============================== APARTMENTS - LECTURE/SELECTION ==============================

def _read_apartments_csv() -> pd.DataFrame:
    """Lit apartments.csv, normalise les colonnes slug/name."""
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
    slug = st.session_state.get("apt_slug", "")
    name = st.session_state.get("apt_name", "")
    if slug and name:
        return {"slug": slug, "name": name}
    return None


def _select_apartment_sidebar() -> bool:
    """
    Affiche le selecteur d'appartement et met a jour:
      - st.session_state["CSV_RESERVATIONS"]
      - st.session_state["CSV_PLATEFORMES"]
      - st.session_state["indicatifs_reload_n"] (bouton de reload indicatifs)
    Renvoie True si la selection a change.
    """
    st.sidebar.markdown("### Appartement")
    apts = _read_apartments_csv()
    if apts.empty:
        st.sidebar.warning("Aucun appartement trouve dans apartments.csv")
        # S'assurer que chemins par defaut existent quand meme
        st.session_state.setdefault("CSV_RESERVATIONS", CSV_RESERVATIONS)
        st.session_state.setdefault("CSV_PLATEFORMES",  CSV_PLATEFORMES)
        return False

    options = apts["slug"].tolist()
    labels = {r["slug"]: r["name"] for _, r in apts.iterrows()}

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

    # memorise et synchronise les chemins actifs
    st.session_state["apt_slug"] = slug
    st.session_state["apt_name"] = name
    st.session_state["CSV_RESERVATIONS"] = f"reservations_{slug}.csv"
    st.session_state["CSV_PLATEFORMES"]  = f"plateformes_{slug}.csv"

    # expose aussi en global pour le code legacy
    global CSV_RESERVATIONS, CSV_PLATEFORMES
    CSV_RESERVATIONS = st.session_state["CSV_RESERVATIONS"]
    CSV_PLATEFORMES  = st.session_state["CSV_PLATEFORMES"]

    st.sidebar.success(f"Connecte : {name}")

    # Outils rapides dans la sidebar
    col_a, col_b = st.sidebar.columns(2)
    if col_a.button("Recharger indicatifs", help="Relit indicatifs_pays.csv"):
        st.session_state["indicatifs_reload_n"] = int(st.session_state.get("indicatifs_reload_n", 0)) + 1
        st.cache_data.clear()
        st.rerun()
    if col_b.button("Imprimer", help="A4 paysage"):
        # bouton soft, l'action JS est installee par print_buttons() dans les vues
        pass

    return changed


def _load_data_for_active_apartment():
    """Wrapper robuste pour charger les donnees de l'appartement actif."""
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_pal = st.session_state.get("CSV_PLATEFORMES",  CSV_PLATEFORMES)
    try:
        return charger_donnees(csv_res, csv_pal)
    except TypeError:
        return charger_donnees(CSV_RESERVATIONS, CSV_PLATEFORMES)
    except Exception:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE.copy()



# ============================== PART 3/5 - VUES PRINCIPALES (ACCUEIL, RÉSA, AJOUTER, MODIFIER, PLATEFORMES, CALENDRIER, ICS) ==============================

def vue_accueil(df: pd.DataFrame, palette: dict):
    """Tableau de bord du jour : arrivées, départs, J+1."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    today = date.today()
    tomorrow = today + timedelta(days=1)
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfv = ensure_schema(df).copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    arr = dfv[dfv["date_arrivee"] == today][["nom_client", "telephone", "plateforme", "pays"]]
    dep = dfv[dfv["date_depart"]  == today][["nom_client", "telephone", "plateforme", "pays"]]
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
        st.dataframe(arr_plus1 if not arr_plus1.empty else pd.DataFrame({"info": ["Aucune arrivée demain."]}), use_container_width=True)


def vue_reservations(df: pd.DataFrame, palette: dict):
    """Liste des réservations + KPIs (brut/net/charges/base/nuits/ADR)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = ensure_schema(df).copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    years_avail = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1, 12 + 1))
    plats_avail  = sorted(dfa["plateforme"].astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())

    c1, c2, c3, c4 = st.columns(4)
    year  = c1.selectbox("Année", ["Toutes"] + years_avail, index=0)
    month = c2.selectbox("Mois", ["Tous"] + months_avail, index=0)
    plat  = c3.selectbox("Plateforme", ["Toutes"] + plats_avail, index=0)
    payf  = c4.selectbox("Paiement", ["Tous", "Payé uniquement", "Non payé uniquement"], index=0)

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

    # KPIs
    brut    = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net     = float(pd.to_numeric(data["prix_net"], errors="coerce").fillna(0).sum())
    base    = float(pd.to_numeric(data["base"], errors="coerce").fillna(0).sum())
    nuits   = int(pd.to_numeric(data["nuitees"], errors="coerce").fillna(0).sum())
    charges = float(pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum())
    adr     = (net / max(nuits, 1)) if nuits > 0 else 0.0

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
    st.dataframe(data.drop(columns=["date_arrivee_dt"]), use_container_width=True)


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
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=0.01, value=0.0)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01, value=0.0)
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01, value=0.0)
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01, value=0.0)
            taxes  = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01, value=0.0)
            paye   = st.checkbox("Payé", value=False)

        if st.form_submit_button("✅ Ajouter"):
            if not nom or dep <= arr:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nuitees = (dep - arr).days
                new = pd.DataFrame(
                    [{
                        "nom_client": nom, "email": email, "telephone": tel, "plateforme": plat,
                        "date_arrivee": arr, "date_depart": dep, "nuitees": nuitees,
                        "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                        "menage": menage, "taxes_sejour": taxes, "paye": paye
                    }]
                )
                df2 = ensure_schema(pd.concat([df, new], ignore_index=True))
                if sauvegarder_donnees(df2):
                    st.success(f"Réservation pour {nom} ajoutée.")
                    st.rerun()


def vue_modifier(df: pd.DataFrame, palette: dict):
    """Edition/Suppression d’une réservation existante."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client','')} ({r.get('date_arrivee','')})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not sel:
        return

    idx = int(sel.split(":")[0])
    original_idx = df_sorted.loc[idx, "index"]
    row = ensure_schema(df).loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=str(row.get("nom_client", "") or ""))
            email = st.text_input("Email", value=str(row.get("email", "") or ""))
            tel = st.text_input("Téléphone", value=str(row.get("telephone", "") or ""))
            arrivee = st.date_input("Arrivée", value=_to_date(pd.Series([row.get("date_arrivee")])).iloc[0])
            depart  = st.date_input("Départ",  value=_to_date(pd.Series([row.get("date_depart")])).iloc[0])
        with c2:
            palette_keys = list(palette.keys())
            plat_idx = palette_keys.index(row.get("plateforme")) if row.get("plateforme") in palette_keys else 0
            plat = st.selectbox("Plateforme", options=palette_keys, index=plat_idx)
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut = float(pd.to_numeric(row.get("prix_brut"), errors="coerce") or 0)
            commissions = float(pd.to_numeric(row.get("commissions"), errors="coerce") or 0)
            frais_cb = float(pd.to_numeric(row.get("frais_cb"), errors="coerce") or 0)
            menage   = float(pd.to_numeric(row.get("menage"), errors="coerce") or 0)
            taxes    = float(pd.to_numeric(row.get("taxes_sejour"), errors="coerce") or 0)
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=brut)
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=commissions)
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=frais_cb)
            menage   = st.number_input("Ménage",   min_value=0.0, step=0.01, value=menage)
            taxes    = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=taxes)

        b1, b2 = st.columns([0.7, 0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            updates = {
                "nom_client": nom, "email": email, "telephone": tel, "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye, "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes
            }
            for k, v in updates.items():
                df.loc[original_idx, k] = v
            if sauvegarder_donnees(df):
                st.success("Modifié ✅")
                st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé.")
                st.rerun()


def vue_plateformes(df: pd.DataFrame, palette: dict):
    """Edition de la palette couleurs par plateforme (CSV_PLATEFORMES)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes & couleurs — {apt_name}")
    print_buttons()

    HAS_COLORCOL = hasattr(getattr(st, "column_config", object), "ColorColumn")

    existing_plats = sorted(
        ensure_schema(df)
        .get("plateforme", pd.Series([], dtype=str))
        .astype(str).str.strip().replace({"nan": ""}).dropna().unique().tolist()
    )
    all_plats = sorted(set(list(palette.keys()) + existing_plats))
    base = pd.DataFrame({"plateforme": all_plats, "couleur": [palette.get(p, "#666666") for p in all_plats]})

    if HAS_COLORCOL:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorColumn("Couleur (hex)"),
        }
    else:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn("Couleur (hex)", help="Ex: #1b9e77", validate=r"^#([0-9A-Fa-f]{6})$", width="small"),
        }

    edited = st.data_editor(
        base, num_rows="dynamic", use_container_width=True, hide_index=True, column_config=col_cfg, key="palette_editor"
    )

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
            to_save["couleur"]    = to_save["couleur"].astype(str).str.strip()
            to_save = to_save[to_save["plateforme"] != ""].drop_duplicates(subset=["plateforme"])
            if not HAS_COLORCOL:
                ok = to_save["couleur"].str.match(r"^#([0-9A-Fa-f]{6})$")
                to_save.loc[~ok, "couleur"] = "#666666"
            to_save.to_csv(_current_pal_path(), sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("↩️ Palette par défaut", key="restore_palette_btn"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme", "couleur"]).to_csv(
                _current_pal_path(), sep=";", index=False, encoding="utf-8", lineterminator="\n"
            )
            st.success("Palette restaurée.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c3.button("🔄 Recharger", key="reload_palette_btn"):
        st.cache_data.clear()
        st.rerun()


def vue_calendrier(df: pd.DataFrame, palette: dict):
    """Grille mensuelle simple avec pills colorées + récap du mois."""
    from html import escape

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier (grille mensuelle) — {apt_name}")
    print_buttons()

    dfv = ensure_schema(df).dropna(subset=["date_arrivee", "date_depart"]).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1, 13)), index=(today.month - 1))

    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div>"
        "<div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True,
    )

    def day_resas(d):
        mask = (dfv["date_arrivee"] <= d) & (dfv["date_depart"] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)
    html_parts = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(int(annee), int(mois)):
        for d in week:
            outside = (d.month != int(mois))
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'>"
            cell += f"<div class='cal-date'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                if not rs.empty:
                    for _, r in rs.iterrows():
                        color = palette.get(r.get("plateforme"), "#888")
                        name  = str(r.get("nom_client") or "")[:22]
                        title_txt = escape(str(r.get("nom_client", "")), quote=True)
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
    debut_mois = date(int(annee), int(mois), 1)
    fin_mois   = date(int(annee), int(mois), monthrange(int(annee), int(mois))[1])
    rows = dfv[(dfv["date_arrivee"] <= fin_mois) & (dfv["date_depart"] > debut_mois)].copy()

    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
        plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
        if plat != "Toutes":
            rows = rows[rows["plateforme"] == plat]

        brut  = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
        net   = float(pd.to_numeric(rows["prix_net"], errors="coerce").fillna(0).sum())
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
            rows[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "paye", "pays"]],
            use_container_width=True,
        )


def vue_export_ics(df: pd.DataFrame, palette: dict):
    """Export .ics par année et filtre plateforme (UID stable par resa)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📆 Export ICS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = ensure_schema(df).copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    years = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years if years else [date.today().year], index=0)
    plats = ["Tous"] + sorted(dfa["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfa[dfa["date_arrivee_dt"].dt.year == int(year)].copy()
    if plat != "Tous":
        data = data[data["plateforme"] == plat]
    if data.empty:
        st.warning("Rien à exporter.")
        return

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
        return str(s).replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Villa Tobias//Reservations//FR", "CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        dt_a = pd.to_datetime(r["date_arrivee"], errors="coerce")
        dt_d = pd.to_datetime(r["date_depart"],  errors="coerce")
        if pd.isna(dt_a) or pd.isna(dt_d):
            continue
        summary = f"{apt_name} — {r.get('nom_client', 'Sans nom')}"
        if r.get("plateforme"):
            summary += f" ({r['plateforme']})"
        desc = "\n".join([
            f"Client: {r.get('nom_client', '')}",
            f"Téléphone: {r.get('telephone', '')}",
            f"Nuitées: {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}",
            f"Prix brut: {float(pd.to_numeric(r.get('prix_brut'), errors='coerce') or 0):.2f} €",
            f"res_id: {r.get('res_id', '')}",
        ])
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



# ============================== PART 4/5 — RAPPORT, GOOGLE SHEET, CLIENTS, ID ==============================

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
    dfr["date_depart"]  = _to_date(dfr["date_depart"])

    # Nuées / revenus : on s'appuie sur les colonnes normalisées déjà présentes
    dfr["nuitees"]   = pd.to_numeric(dfr["nuitees"], errors="coerce").fillna(0).astype(int)
    dfr["prix_brut"] = pd.to_numeric(dfr["prix_brut"], errors="coerce").fillna(0.0)
    dfr["prix_net"]  = pd.to_numeric(dfr["prix_net"],  errors="coerce").fillna(0.0)
    dfr["base"]      = pd.to_numeric(dfr["base"],      errors="coerce").fillna(0.0)
    dfr["charges"]   = pd.to_numeric(dfr["charges"],   errors="coerce").fillna(0.0)

    total_resa     = int(len(dfr))
    total_nuitees  = int(dfr["nuitees"].sum())
    total_brut     = float(dfr["prix_brut"].sum())
    total_net      = float(dfr["prix_net"].sum())
    adr_net        = (total_net / total_nuitees) if total_nuitees > 0 else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Réservations", f"{total_resa}")
    c2.metric("Nuitées", f"{total_nuitees}")
    c3.metric("CA brut", f"{total_brut:,.0f} €".replace(",", " "))
    c4.metric("ADR net", f"{adr_net:,.2f} €".replace(",", " "))

    st.markdown("---")

    # ---- Agrégation par plateforme ----
    agg = (
        dfr.groupby("plateforme", dropna=False, as_index=False)
        .agg(reservations=("plateforme", "count"),
             nuitees=("nuitees", "sum"),
             prix_brut=("prix_brut", "sum"),
             prix_net=("prix_net", "sum"))
    )
    agg["part_revenu_%"] = np.where(total_net > 0, (agg["prix_net"] / total_net) * 100.0, 0.0)
    agg = agg.sort_values("prix_net", ascending=False)

    st.subheader("Par plateforme")
    st.dataframe(
        agg.assign(
            reservations=lambda x: x["reservations"].astype(int),
            nuitees=lambda x: x["nuitees"].astype(int),
            prix_brut=lambda x: pd.to_numeric(x["prix_brut"]).round(0),
            prix_net=lambda x: pd.to_numeric(x["prix_net"]).round(0),
            part_revenu_pct=lambda x: pd.to_numeric(x["part_revenu_%"]).round(1)
        ).rename(columns={"part_revenu_pct":"part_revenu_%"}),
        use_container_width=True
    )

    # Camembert répartition CA net
    try:
        fig, ax = plt.subplots()
        labels = agg["plateforme"].fillna("—")
        sizes  = agg["prix_net"]
        colors = [palette.get(p, "#999999") for p in labels]
        ax.pie(sizes, labels=labels, autopct="%1.1f%%", colors=colors)
        ax.set_title("Répartition du CA net par plateforme")
        st.pyplot(fig)
    except Exception as e:
        st.warning(f"Graphique indisponible : {e}")

    st.markdown("---")

    # ---- Agrégation par pays ----
    if "pays" in dfr.columns:
        dfr["pays"] = dfr["pays"].astype(str).str.strip().replace({"": "Inconnu"})
        agg_pays = (
            dfr.groupby("pays", dropna=False, as_index=False)
            .agg(reservations=("pays", "count"),
                 nuitees=("nuitees", "sum"),
                 prix_net=("prix_net", "sum"))
            .sort_values("prix_net", ascending=False)
        )
        agg_pays["part_revenu_%"] = np.where(total_net > 0, (agg_pays["prix_net"] / total_net) * 100.0, 0.0)

        st.subheader("Top 20 pays (par CA net)")
        top = agg_pays.head(20).copy()
        st.dataframe(
            top.assign(
                reservations=lambda x: x["reservations"].astype(int),
                nuitees=lambda x: x["nuitees"].astype(int),
                prix_net=lambda x: pd.to_numeric(x["prix_net"]).round(0),
                part_revenu_pct=lambda x: pd.to_numeric(x["part_revenu_%"]).round(1)
            ).rename(columns={"part_revenu_pct":"part_revenu_%"}),
            use_container_width=True
        )

        # Barres horizontales
        try:
            fig2, ax2 = plt.subplots()
            ax2.barh(top["pays"], top["prix_net"])
            ax2.set_xlabel("CA net (€)")
            ax2.set_ylabel("Pays")
            ax2.invert_yaxis()
            st.pyplot(fig2)
        except Exception as e:
            st.warning(f"Graphique pays indisponible : {e}")


# ---------------- GOOGLE SHEET ----------------
def vue_google_sheet(df: pd.DataFrame, palette: dict):
    """Intégration et aperçu des réponses Google Form/Sheet (simplifié)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Google Sheet — {apt_name}")
    print_buttons()
    st.markdown(f"**Lien court à partager (formulaire d'arrivée)** : {FORM_SHORT_URL}")

    # Formulaire embarqué (si autorisé)
    try:
        st.markdown(f'<iframe src="{GOOGLE_FORM_VIEW}" width="100%" height="900" frameborder="0"></iframe>', unsafe_allow_html=True)
    except Exception:
        st.info("Formulaire embarqué indisponible ici.")

    st.markdown("---")
    st.subheader("Feuille Google intégrée")
    try:
        st.markdown(f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>', unsafe_allow_html=True)
    except Exception:
        st.info("Feuille embarquée indisponible.")

    st.markdown("---")
    st.subheader("Réponses (CSV publié)")
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
        show_email = st.checkbox("Afficher les colonnes d'email (si présentes)", value=False)
        if not show_email:
            mask_cols = [c for c in rep.columns if "mail" in c.lower() or "email" in c.lower()]
            rep_display = rep.drop(columns=mask_cols, errors="ignore")
        else:
            rep_display = rep
        st.dataframe(rep_display, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")


# ---------------- CLIENTS ----------------
def vue_clients(df: pd.DataFrame, palette: dict):
    """Liste des clients (pays calculés via indicatifs)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Liste des clients — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucun client.")
        return

    clients = ensure_schema(df).copy()
    for c in ["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]:
        if c not in clients.columns:
            clients[c] = ""
        clients[c] = clients[c].astype(str).str.strip().replace({"nan": ""})

    need = (clients["pays"] == "") | (clients["pays"].isna())
    clients.loc[need, "pays"] = clients.loc[need, "telephone"].apply(_phone_country)

    cols_order = ["nom_client", "pays", "telephone", "email", "plateforme", "res_id"]
    cols_order = [c for c in cols_order if c in clients.columns]
    clients = clients[cols_order]
    clients = clients.loc[clients["nom_client"] != ""].drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)

    st.markdown("---")
    c1, c2 = st.columns([0.5, 0.5])
    with c1:
        if st.button("↻ Recalculer les pays via indicatifs", key="btn_recalc_pays"):
            try:
                df2 = ensure_schema(df).copy()
                df2["pays"] = df2["telephone"].apply(_phone_country)
                if sauvegarder_donnees(df2):
                    st.success("Pays recalculés et sauvegardés ✅")
                    st.rerun()
            except Exception as e:
                st.error(f"Erreur recalcul : {e}")
    with c2:
        st.caption("Astuce : vous pouvez aussi gérer les indicatifs/drapeaux dans le menu **🌍 Indicateurs pays**.")


# ---------------- ID ----------------
def vue_id(df: pd.DataFrame, palette: dict):
    """Affiche les rés_id/UID + infos principales."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🆔 Identifiants — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    tbl = ensure_schema(df)[["res_id", "nom_client", "telephone", "email", "plateforme", "pays"]].copy()
    for c in ["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]:
        tbl[c] = tbl[c].astype(str).str.strip().replace({"nan": ""})
    need = (tbl["pays"] == "") | (tbl["pays"].isna())
    tbl.loc[need, "pays"] = tbl.loc[need, "telephone"].apply(_phone_country)
    tbl = tbl.dropna(subset=["res_id"])
    tbl = tbl[tbl["res_id"] != ""].drop_duplicates()
    st.dataframe(tbl, use_container_width=True)



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

    # -------- Pré-arrivée --------
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = dfx.dropna(subset=["telephone", "nom_client", "date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (~_to_bool_series(pre["sms_envoye"]))]

    if not pre.empty:
        pre = pre.sort_values("date_arrivee").reset_index()
        pick = st.selectbox("Client (pré-arrivée)", [f"{i}: {r['nom_client']}" for i, r in pre.iterrows()], index=None)
        if pick:
            i = int(pick.split(":")[0])
            r = pre.loc[i]
            arr_txt = r["date_arrivee"].strftime("%d/%m/%Y")
            dep_txt = r["date_depart"].strftime("%d/%m/%Y")
            nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)

            msg = (
                f"{apt_name.upper()}\n"
                f"Plateforme : {r.get('plateforme','')}\n"
                f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuitees}\n\n"
                f"Bonjour {r.get('nom_client','')},\n"
                "Bienvenue chez nous ! Merci de remplir la fiche suivante :\n"
                f"{FORM_SHORT_URL}\n\n"
                "Parking disponible. Check-in 14h / Check-out 11h.\n"
                "A bientôt !\n\n"
                "Annick & Charley"
            )
            st.text_area("📋 Message à envoyer", value=msg, height=300)

            # Liens cliquables
            e164 = _format_phone_e164(r.get("telephone", ""))
            only_digits = "".join(ch for ch in e164 if ch.isdigit())
            enc = quote(msg)
            st.markdown(f"[📲 iPhone SMS](sms:&body={enc})  |  [🤖 Android SMS](sms:{e164}?body={enc})  |  [🟢 WhatsApp](https://wa.me/{only_digits}?text={enc})")

            if st.button("✅ Marquer SMS envoyé", key="pre_mark"):
                df.loc[r["index"], "sms_envoye"] = True
                sauvegarder_donnees(df)
                st.rerun()
    else:
        st.info("Aucun SMS pré-arrivée à envoyer.")

    st.markdown("---")

    # -------- Post-départ --------
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = dfx.dropna(subset=["telephone", "nom_client", "date_depart"]).copy()
    post = post[(post["date_depart"] == target_depart) & (~_to_bool_series(post["post_depart_envoye"]))]

    if not post.empty:
        post = post.sort_values("date_depart").reset_index()
        pick2 = st.selectbox("Client (post-départ)", [f"{i}: {r['nom_client']}" for i, r in post.iterrows()], index=None)
        if pick2:
            j = int(pick2.split(":")[0])
            r2 = post.loc[j]
            name = r2.get("nom_client","")

            msg2 = (
                f"Bonjour {name},\n\n"
                "Merci d'avoir choisi notre appartement. Nous espérons que votre séjour a été agréable.\n"
                "Au plaisir de vous revoir.\n\n"
                "Annick & Charley"
            )
            st.text_area("📋 Message post-départ", value=msg2, height=250)

            e164b = _format_phone_e164(r2.get("telephone", ""))
            only_digits_b = "".join(ch for ch in e164b if ch.isdigit())
            enc2 = quote(msg2)
            st.markdown(f"[🟢 WhatsApp](https://wa.me/{only_digits_b}?text={enc2})  |  [📲 iPhone SMS](sms:&body={enc2})  |  [🤖 Android SMS](sms:{e164b}?body={enc2})")

            if st.button("✅ Marquer post-départ envoyé", key="post_mark"):
                df.loc[r2["index"], "post_depart_envoye"] = True
                sauvegarder_donnees(df)
                st.rerun()
    else:
        st.info("Aucun SMS post-départ à envoyer.")


# ---------------- INDICATEURS PAYS ----------------

def vue_indicatifs(df: pd.DataFrame, palette: dict):
    """Gestion du fichier indicatifs_pays.csv"""
    st.header("🌍 Indicateurs pays")
    data = _load_indicatifs_df()
    st.dataframe(data, use_container_width=True)

    edited = st.data_editor(
        data, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={"code": "Code", "country": "Pays", "dial": "Indicatif", "flag": "Drapeau"}
    )

    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer"):
        _save_indicatifs_df(edited)
        st.success("Enregistré ✅")

    if c2.button("🔄 Recharger depuis le disque"):
        st.cache_data.clear()
        data2 = _load_indicatifs_df()
        st.experimental_set_query_params(refresh="1")
        st.rerun()


# ---------------- PARAMÈTRES ----------------

def vue_settings(df: pd.DataFrame, palette: dict):
    """Exports, restauration et cache."""
    st.header("⚙️ Paramètres")

    # Export CSV
    csv_bytes = ensure_schema(df).to_csv(sep=";", index=False).encode("utf-8")
    st.download_button("⬇️ Export CSV", csv_bytes, "reservations.csv", "text/csv")

    # Export XLSX
    try:
        xlsx_bytes, _ = _df_to_xlsx_bytes(ensure_schema(df), "Reservations")
        st.download_button("⬇️ Export XLSX", xlsx_bytes, "reservations.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    except Exception:
        st.warning("Impossible d'exporter en XLSX.")

    # Restauration
    up = st.file_uploader("♻️ Restaurer (CSV/XLSX)", type=["csv","xlsx"])
    if up:
        try:
            if up.name.endswith(".xlsx"):
                tmp = pd.read_excel(up, dtype=str)
            else:
                tmp = pd.read_csv(up, dtype=str, sep=None, engine="python")
            save = ensure_schema(tmp)
            save.to_csv(CSV_RESERVATIONS, sep=";", index=False)
            st.success("Fichier restauré ✅")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur restauration : {e}")

    # Cache
    if st.button("🧹 Vider le cache"):
        st.cache_data.clear()
        st.rerun()


# ---------------- MAIN ----------------

def main():
    changed = _select_apartment_sidebar()
    if changed:
        st.cache_data.clear()

    mode_clair = st.sidebar.checkbox("🌓 Mode clair", value=False)
    apply_style(light=mode_clair)

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    df, palette_loaded = _load_data_for_active_apartment()
    palette = palette_loaded or DEFAULT_PALETTE

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

    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)


if __name__ == "__main__":
    main()