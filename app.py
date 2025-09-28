# ============================== PART 1/5 : IMPORTS, CONFIG, STYLES, HELPERS ==============================

import os
import io
import re
import uuid
import hashlib
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange
from urllib.parse import quote
from html import escape

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
import matplotlib.pyplot as plt


# ------------------------------ CONFIG APP ------------------------------
st.set_page_config(
    page_title="Villa Tobias — Gestion des Réservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ------------------------------ CONSTANTES ------------------------------
# Fichiers (seront remplacés par ceux de l'appartement actif)
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"
APARTMENTS_CSV   = "apartments.csv"
INDICATIFS_CSV   = "indicatifs_pays.csv"   # code, country, flag, prefix (ex: FR, France, 🇫🇷, 33)

# Google Form & Sheet
FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# Palette par défaut
DEFAULT_PALETTE = {
    "Booking": "#1b9e77",
    "Airbnb":  "#d95f02",
    "Abritel": "#7570b3",
    "Direct":  "#e7298a",
}

# Colonnes de base des réservations
BASE_COLS = [
    "paye", "nom_client", "email", "sms_envoye", "post_depart_envoye",
    "plateforme", "telephone", "pays",
    "date_arrivee", "date_depart", "nuitees",
    "prix_brut", "commissions", "frais_cb", "prix_net",
    "menage", "taxes_sejour", "base", "charges", "%",
    "res_id", "ical_uid"
]


# ------------------------------ STYLE / CSS ------------------------------
def apply_style(light: bool):
    """Applique le thème clair/sombre + styles impression A4 paysage."""
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
          html, body, [data-testid="stAppViewContainer"] {{
            background:{bg}; color:{fg};
          }}
          [data-testid="stSidebar"] {{
            background:{side}; border-right:1px solid {border};
          }}
          .glass {{
            background:{card_bg}; border:1px solid {border};
            border-radius:12px; padding:12px; margin:10px 0;
          }}
          .chip {{
            display:inline-block; padding:6px 10px; border-radius:12px;
            margin:4px 6px; font-size:.86rem; background:{chip_bg}; color:{chip_fg};
          }}
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; }}
          .cal-cell {{
            border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px;
            position:relative; overflow:hidden; background:{cell_bg};
          }}
          .cal-cell.outside {{ opacity:.45; }}
          .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
          .resa-pill {{ padding:4px 6px; border-radius:6px; font-size:.84rem; margin-top:22px; color:#fff;
                        white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
          .cal-header {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; font-weight:700; opacity:.8; margin:6px 0 8px; }}

          /* Impression A4 paysage */
          @page {{
            size: A4 landscape;
            margin: 10mm;
          }}
          @media print {{
            .print-hide {{ display:none !important; }}
            .print-only {{ display:block !important; }}
          }}
          .print-only {{ display:none; }}
        </style>
        """,
        unsafe_allow_html=True
    )


def print_buttons(location: str = "main"):
    """Bouton imprimer (JS) — n'interrompt pas l'app."""
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


# ------------------------------ HELPERS I/O ------------------------------
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
    out = (
        s.astype(str)
        .str.strip()
        .str.lower()
        .isin(["true", "1", "oui", "vrai", "yes", "y", "t"])
    )
    return out.fillna(False).astype(bool)


def _to_num(s: pd.Series) -> pd.Series:
    s = _as_series(s)
    sc = (
        s.astype(str)
        .str.replace("€", "", regex=False)
        .str.replace(" ", "", regex=False)
        .str.replace(",", ".", regex=False)
        .str.strip()
    )
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


# ------------------------------ INDICATIFS PAYS ------------------------------
# Fallback minimal si le CSV n'existe pas encore
_INDICATIFS_SEED = [
    ("FR", "France", "🇫🇷", "33"),
    ("BE", "Belgique", "🇧🇪", "32"),
    ("CH", "Suisse", "🇨🇭", "41"),
    ("ES", "Espagne", "🇪🇸", "34"),
    ("IT", "Italie", "🇮🇹", "39"),
    ("DE", "Allemagne", "🇩🇪", "49"),
    ("GB", "Royaume-Uni", "🇬🇧", "44"),
    ("US", "États-Unis/Canada", "🇺🇸", "1"),
    ("MA", "Maroc", "🇲🇦", "212"),
    ("TN", "Tunisie", "🇹🇳", "216"),
]

def create_indicatifs_csv():
    """Crée un CSV d'indicatifs s'il est absent (UTF-8)."""
    if os.path.exists(INDICATIFS_CSV):
        return
    try:
        df = pd.DataFrame(_INDICATIFS_SEED, columns=["code", "country", "flag", "prefix"])
        df.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8", lineterminator="\n")
    except Exception as e:
        st.warning(f"Impossible de créer {INDICATIFS_CSV} : {e}")


@st.cache_data(show_spinner=False)
def load_indicatifs() -> pd.DataFrame:
    """Charge le CSV des indicatifs (garantit l'existence)."""
    create_indicatifs_csv()
    try:
        df = pd.read_csv(INDICATIFS_CSV, dtype=str)
    except Exception:
        df = pd.DataFrame(_INDICATIFS_SEED, columns=["code", "country", "flag", "prefix"])
    # Normalisation
    for c in ["code", "country", "flag", "prefix"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str).fillna("").str.strip()
    # Nettoyage simple
    df = df[df["prefix"] != ""].drop_duplicates(subset=["prefix"], keep="first")
    return df[["code", "country", "flag", "prefix"]]


def _prefix_map() -> dict:
    """Retourne un dict {prefix: country} (priorise le CSV)."""
    dfp = load_indicatifs()
    mp = {str(p): str(c) for p, c in zip(dfp["prefix"], dfp["country"])}
    # Fallback si besoin
    if not mp:
        mp = {p: c for _, c, _, p in _INDICATIFS_SEED}
    return mp


def _phone_country(phone: str) -> str:
    """Déduit le pays à partir de l'indicatif téléphonique."""
    p = str(phone or "").strip()
    if not p:
        return ""
    if p.startswith("+"):
        p1 = p[1:]
    elif p.startswith("00"):
        p1 = p[2:]
    elif p.startswith("0"):
        # Hypothèse France si numéro commençant par 0 et sans indicatif international
        return "France"
    else:
        p1 = p

    mp = _prefix_map()
    # Tri par longueur décroissante pour attraper d'abord les préfixes longs
    for k in sorted(mp.keys(), key=lambda x: -len(x)):
        if p1.startswith(k):
            return mp[k]
    return "Inconnu"


# ------------------------------ NORMALISATION / SAUVEGARDE ------------------------------
def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Force la présence/typage des colonnes et calcule prix_net, base, charges, %, nuitees."""
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Renommages usuels
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

    # Booléens
    for b in ["paye", "sms_envoye", "post_depart_envoye"]:
        df[b] = _to_bool_series(df[b])

    # Nombres
    for n in ["prix_brut", "commissions", "frais_cb", "menage", "taxes_sejour", "nuitees", "charges", "%", "base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"] = _to_date(df["date_depart"])

    mask_ok = pd.notna(df["date_arrivee"]) & pd.notna(df["date_depart"])
    if mask_ok.any():
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)

    # Calculs financiers
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

    # IDs
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip() == "")
    if miss_res.any():
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip() == "")
    if miss_uid.any():
        df.loc[miss_uid, "ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # Strings + pays auto
    for c in ["nom_client", "plateforme", "telephone", "email", "pays"]:
        df[c] = df[c].astype(str).replace({"nan": "", "None": ""}).str.strip()

    need = df["pays"].eq("") | df["pays"].isna()
    if need.any():
        df.loc[need, "pays"] = df.loc[need, "telephone"].apply(_phone_country)

    return df[BASE_COLS]


def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    """Sauvegarde le CSV des réservations pour l'appartement actif."""
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee", "date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        target_csv = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
        out.to_csv(target_csv, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False


@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations: str, csv_plateformes: str):
    """Charge réservations + palette. Crée des fichiers si absents."""
    # Création si absent
    for fichier, header in [
        (csv_reservations, "nom_client,email,telephone,plateforme,date_arrivee,date_depart,nuitees,prix_brut\n"),
        (csv_plateformes, "plateforme,couleur\nBooking,#1b9e77\nAirbnb,#d95f02\nAbritel,#7570b3\nDirect,#e7298a\n"),
    ]:
        if not os.path.exists(fichier):
            with open(fichier, "w", encoding="utf-8", newline="") as f:
                f.write(header)

    # Réservations
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

    # S'assure que le CSV d'indicatifs existe (utile pour la page dédiée)
    create_indicatifs_csv()

    return df, palette

# ============================== PART 2/5 : APARTMENTS + ACCUEIL/RÉSERVATIONS/AJOUTER ==============================

# ------------------------------ APARTMENTS (sélecteur) ------------------------------
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
    """Retourne {{'slug','name'}} de l'appartement actif depuis la session, sinon None."""
    slug = st.session_state.get("apt_slug", "")
    name = st.session_state.get("apt_name", "")
    if slug and name:
        return {"slug": slug, "name": name}
    return None


def _select_apartment_sidebar() -> bool:
    """
    Affiche le sélecteur d'appartement dans la sidebar et met à jour les chemins
    CSV_RESERVATIONS / CSV_PLATEFORMES en session. Retourne True si la sélection a changé.
    """
    st.sidebar.markdown("### Appartement")
    df_apts = _read_apartments_csv()
    if df_apts.empty:
        st.sidebar.warning("Aucun appartement trouvé dans apartments.csv")
        return False

    options = df_apts["slug"].tolist()
    labels = {r["slug"]: r["name"] for _, r in df_apts.iterrows()}
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

    # met à jour les globales (utilisées par export/restauration)
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
    """Charge (ou crée) les fichiers de l'appartement actif."""
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_pal = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
    try:
        return charger_donnees(csv_res, csv_pal)
    except TypeError:
        return charger_donnees(CSV_RESERVATIONS, CSV_PLATEFORMES)
    except Exception:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE.copy()


# ------------------------------ VUE : ACCUEIL ------------------------------
def vue_accueil(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    today = date.today()
    tomorrow = today + timedelta(days=1)
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfv = ensure_schema(df).copy()
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
        st.dataframe(
            arr_plus1 if not arr_plus1.empty else pd.DataFrame({"info": ["Aucune arrivée demain."]}),
            use_container_width=True,
        )


# ------------------------------ VUE : RÉSERVATIONS ------------------------------
def vue_reservations(df: pd.DataFrame, palette: dict):
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
    months_avail = list(range(1, 13))
    plats_avail = sorted(
        dfa["plateforme"].astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist()
    )

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
    st.dataframe(
        data.drop(columns=["date_arrivee_dt"]),
        use_container_width=True,
        hide_index=True,
    )


# ------------------------------ VUE : AJOUTER ------------------------------
def vue_ajouter(df: pd.DataFrame, palette: dict):
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

# ============================== PART 3/5 : MODIFIER/SUPPRIMER + PLATEFORMES + CALENDRIER ==============================

# ------------------------------ VUE : MODIFIER / SUPPRIMER ------------------------------
def vue_modifier(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfx = df.reset_index().copy()
    options = [f"{i}: {r['nom_client']} ({r['date_arrivee']} → {r['date_depart']})" for i, r in dfx.iterrows()]
    choice = st.selectbox("Sélectionnez une réservation", options, index=None)
    if not choice:
        return

    sel = int(choice.split(":")[0])
    rec = dfx.loc[sel]

    with st.form("form_edit"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom du client", rec["nom_client"])
            email = st.text_input("Email", rec.get("email", ""))
            tel = st.text_input("Téléphone", rec["telephone"])
            arr = st.date_input("Arrivée", _to_date(rec["date_arrivee"]))
            dep = st.date_input("Départ", _to_date(rec["date_depart"]))
        with c2:
            plat = st.selectbox("Plateforme", list(palette.keys()), index=list(palette.keys()).index(rec["plateforme"]) if rec["plateforme"] in palette else 0)
            brut = st.number_input("Prix brut (€)", value=float(rec.get("prix_brut", 0) or 0), step=0.01)
            commissions = st.number_input("Commissions (€)", value=float(rec.get("commissions", 0) or 0), step=0.01)
            frais_cb = st.number_input("Frais CB (€)", value=float(rec.get("frais_cb", 0) or 0), step=0.01)
            menage = st.number_input("Ménage (€)", value=float(rec.get("menage", 0) or 0), step=0.01)
            taxes = st.number_input("Taxes séjour (€)", value=float(rec.get("taxes_sejour", 0) or 0), step=0.01)
            paye = st.checkbox("Payé", value=_to_bool(rec.get("paye", False)))

        c1b, c2b = st.columns(2)
        if c1b.form_submit_button("💾 Sauvegarder"):
            if dep <= arr:
                st.error("Dates invalides.")
            else:
                df.at[rec["index"], "nom_client"] = nom
                df.at[rec["index"], "email"] = email
                df.at[rec["index"], "telephone"] = tel
                df.at[rec["index"], "plateforme"] = plat
                df.at[rec["index"], "date_arrivee"] = arr
                df.at[rec["index"], "date_depart"] = dep
                df.at[rec["index"], "nuitees"] = (dep - arr).days
                df.at[rec["index"], "prix_brut"] = brut
                df.at[rec["index"], "commissions"] = commissions
                df.at[rec["index"], "frais_cb"] = frais_cb
                df.at[rec["index"], "menage"] = menage
                df.at[rec["index"], "taxes_sejour"] = taxes
                df.at[rec["index"], "paye"] = paye
                if sauvegarder_donnees(df):
                    st.success("Réservation mise à jour ✅")
                    st.rerun()
        if c2b.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=rec["index"])
            if sauvegarder_donnees(df2):
                st.success("Réservation supprimée ✅")
                st.rerun()


# ------------------------------ VUE : PLATEFORMES ------------------------------
def vue_plateformes(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes — {apt_name}")
    print_buttons()

    plats = sorted(set(df["plateforme"].dropna().unique().tolist() + list(palette.keys())))
    rows = []
    for p in plats:
        rows.append({"plateforme": p, "couleur": palette.get(p, "#cccccc")})
    dfe = pd.DataFrame(rows)

    edited = st.data_editor(dfe, num_rows="dynamic", key="edit_palette")
    if st.button("💾 Sauvegarder couleurs"):
        try:
            pal = {r["plateforme"]: r["couleur"] for _, r in edited.iterrows() if r["plateforme"]}
            save_palette(pal)
            st.success("Palette sauvegardée ✅")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")


# ------------------------------ VUE : CALENDRIER ------------------------------
def vue_calendrier(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune donnée.")
        return

    dfx = df.copy()
    dfx["date_arrivee"] = _to_date(dfx["date_arrivee"])
    dfx["date_depart"] = _to_date(dfx["date_depart"])

    year = st.selectbox("Année", sorted(dfx["date_arrivee"].dt.year.dropna().unique()), index=0)
    month = st.selectbox("Mois", list(range(1, 13)), index=date.today().month - 1)

    start = date(int(year), int(month), 1)
    if month == 12:
        end = date(int(year) + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(int(year), int(month) + 1, 1) - timedelta(days=1)

    st.write(f"📆 {start.strftime('%B %Y')}")

    days = pd.date_range(start, end)
    matrix = []
    week = []
    for d in days:
        txt = d.strftime("%d")
        resa = dfx[(dfx["date_arrivee"] <= d) & (dfx["date_depart"] > d)]
        if not resa.empty:
            plats = resa["plateforme"].unique().tolist()
            colors = [palette.get(p, "#999999") for p in plats]
            txt += " " + "".join([f"<span style='color:{c}'>■</span>" for c in colors])
        week.append(txt)
        if d.weekday() == 6:
            matrix.append(week)
            week = []
    if week:
        matrix.append(week)

    st.write("Calendrier :")
    for w in matrix:
        st.markdown(" | ".join(w), unsafe_allow_html=True)

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
    dfr["date_depart"] = _to_date(dfr["date_depart"])
    dfr["nuitees"] = pd.to_numeric(dfr["nuitees"], errors="coerce").fillna(0).astype(int)

    # Choix du revenu de référence (net si dispo, sinon brut)
    revenu_col = "prix_net" if "prix_net" in dfr.columns else "prix_brut"
    dfr["revenu"] = pd.to_numeric(dfr.get(revenu_col, 0), errors="coerce").fillna(0)

    # ---- KPIs principaux ----
    total_resa = len(dfr)
    total_nuitees = int(dfr["nuitees"].sum())
    total_revenu = float(dfr["revenu"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Réservations", f"{total_resa}")
    c2.metric("Nuitées", f"{total_nuitees}")
    c3.metric("Revenu total", f"{total_revenu:,.0f} €".replace(",", " "))

    st.markdown("---")

    # ---- Filtres rapides ----
    years = sorted(pd.to_datetime(dfr["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique())
    plats = sorted(dfr["plateforme"].dropna().astype(str).unique())
    colf1, colf2 = st.columns(2)
    year_pick = colf1.selectbox("Année (filtre)", ["Toutes"] + years, index=0)
    plat_pick = colf2.selectbox("Plateforme (filtre)", ["Toutes"] + plats, index=0)

    dff = dfr.copy()
    if year_pick != "Toutes":
        dff = dff[pd.to_datetime(dff["date_arrivee"], errors="coerce").dt.year == int(year_pick)]
    if plat_pick != "Toutes":
        dff = dff[dff["plateforme"] == plat_pick]

    # ---- Agrégation par plateforme ----
    if dff.empty:
        st.warning("Aucune donnée après filtres.")
        return

    agg = (
        dff.groupby("plateforme", dropna=False)
           .agg(reservations=("plateforme", "count"),
                nuitees=("nuitees", "sum"),
                revenu_total=("revenu", "sum"))
           .reset_index()
    )
    total_revenu_f = float(agg["revenu_total"].sum())
    agg["part_revenu_%"] = np.where(
        total_revenu_f > 0,
        (agg["revenu_total"] / total_revenu_f * 100).round(1),
        0.0
    )

    st.subheader("Par plateforme")
    st.dataframe(
        agg.assign(
            reservations=lambda x: x["reservations"].astype(int),
            nuitees=lambda x: x["nuitees"].astype(int),
            revenu_total=lambda x: pd.to_numeric(x["revenu_total"], errors="coerce").round(2),
            part_revenu_pct=lambda x: x["part_revenu_%"]
        ).rename(columns={"part_revenu_pct": "part_revenu_%"}),
        use_container_width=True
    )

    # Graphique par plateforme (Altair)
    try:
        chart_plat = alt.Chart(agg).mark_bar().encode(
            x=alt.X("plateforme:N", title="Plateforme", sort="-y"),
            y=alt.Y("revenu_total:Q", title="Revenu (€)"),
            color=alt.Color("plateforme:N", legend=None),
            tooltip=[
                alt.Tooltip("plateforme:N", title="Plateforme"),
                alt.Tooltip("reservations:Q", title="Réservations", format=",.0f"),
                alt.Tooltip("nuitees:Q", title="Nuitées", format=",.0f"),
                alt.Tooltip("revenu_total:Q", title="Revenu (€)", format=",.2f"),
                alt.Tooltip("part_revenu_%:Q", title="Part (%)", format=".1f"),
            ]
        ).properties(height=380)
        st.altair_chart(chart_plat, use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique plateformes indisponible : {e}")

    st.markdown("---")

    # ---- Agrégation par pays ----
    if "pays" in dff.columns:
        agg_pays = (
            dff.groupby("pays", dropna=False)
               .agg(reservations=("pays", "count"),
                    nuitees=("nuitees", "sum"),
                    revenu_total=("revenu", "sum"))
               .reset_index()
        )
        agg_pays["pays"] = agg_pays["pays"].replace("", "Inconnu").fillna("Inconnu")
        agg_pays = agg_pays.sort_values("revenu_total", ascending=False)
        agg_pays["part_revenu_%"] = np.where(
            total_revenu_f > 0,
            (agg_pays["revenu_total"] / total_revenu_f * 100).round(1),
            0.0
        )

        st.subheader("Par pays (Top 20)")
        topN = st.slider("Nombre de pays à afficher", 5, 30, 20, 1)
        disp_pays = agg_pays.head(topN).copy()
        st.dataframe(
            disp_pays.assign(
                reservations=lambda x: x["reservations"].astype(int),
                nuitees=lambda x: x["nuitees"].astype(int),
                revenu_total=lambda x: pd.to_numeric(x["revenu_total"], errors="coerce").round(2),
                part_revenu_pct=lambda x: x["part_revenu_%"]
            ).rename(columns={"part_revenu_pct": "part_revenu_%"}),
            use_container_width=True
        )

        try:
            chart_pays = alt.Chart(disp_pays).mark_bar().encode(
                y=alt.Y("pays:N", sort="-x", title="Pays"),
                x=alt.X("revenu_total:Q", title="Revenu (€)"),
                tooltip=[
                    alt.Tooltip("pays:N", title="Pays"),
                    alt.Tooltip("reservations:Q", title="Réservations", format=",.0f"),
                    alt.Tooltip("nuitees:Q", title="Nuitées", format=",.0f"),
                    alt.Tooltip("revenu_total:Q", title="Revenu (€)", format=",.2f"),
                    alt.Tooltip("part_revenu_%:Q", title="Part (%)", format=".1f"),
                ],
                color=alt.Color("pays:N", legend=None)
            ).properties(height=520)
            st.altair_chart(chart_pays, use_container_width=True)
        except Exception as e:
            st.warning(f"Graphique pays indisponible : {e}")

    # ---- Occupation par mois ----
    st.markdown("---")
    st.subheader("📅 Taux d'occupation (nuits / jours du mois)")
    dff["arr_dt"] = pd.to_datetime(dff["date_arrivee"], errors="coerce")
    dff["dep_dt"] = pd.to_datetime(dff["date_depart"], errors="coerce")
    dff = dff.dropna(subset=["arr_dt", "dep_dt"])
    dff["mois"] = dff["arr_dt"].dt.to_period("M").astype(str)
    occ = (
        dff.groupby("mois", as_index=False)["nuitees"]
           .sum()
           .rename(columns={"nuitees": "nuitees_occupees"})
    )

    def _days_in_month(s):
        y, m = map(int, s.split("-"))
        return monthrange(y, m)[1]

    occ["jours_mois"] = occ["mois"].apply(_days_in_month)
    occ["taux_occupation_%"] = np.where(
        occ["jours_mois"] > 0,
        (occ["nuitees_occupees"] / occ["jours_mois"] * 100).round(1),
        0.0
    )

    st.dataframe(occ, use_container_width=True)
    try:
        chart_occ = alt.Chart(occ).mark_line(point=True).encode(
            x=alt.X("mois:N", sort=None, title="Mois"),
            y=alt.Y("taux_occupation_%:Q", title="Taux d'occupation (%)", scale=alt.Scale(domain=[0, 100])),
            tooltip=[
                alt.Tooltip("mois:N", title="Mois"),
                alt.Tooltip("nuitees_occupees:Q", title="Nuitées", format=",.0f"),
                alt.Tooltip("taux_occupation_%:Q", title="Taux (%)", format=".1f"),
            ],
            color=alt.value("#6c8cff"),
        ).properties(height=380)
        st.altair_chart(chart_occ, use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique occupation indisponible : {e}")


# ---------------- GOOGLE SHEET ----------------
def vue_google_sheet(df: pd.DataFrame, palette: dict):
    """Affiche le formulaire Google et la feuille intégrée + CSV publié si dispo."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Google Sheet — {apt_name}")
    print_buttons()

    st.markdown(f"**Lien court à partager :** {FORM_SHORT_URL}")
    st.markdown(
        f'<iframe src="{GOOGLE_FORM_VIEW}" width="100%" height="900" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )
    st.markdown("---")
    st.subheader("Feuille Google intégrée")
    st.markdown(
        f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )
    st.markdown("---")
    st.subheader("Réponses (CSV publié)")
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
        show_email = st.checkbox("Afficher les colonnes d'email (si présentes)", value=False)
        if not show_email:
            mask_cols = [c for c in rep.columns if "mail" in c.lower() or "email" in c.lower()]
            rep_disp = rep.drop(columns=mask_cols, errors="ignore")
        else:
            rep_disp = rep
        st.dataframe(rep_disp, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")


# ---------------- CLIENTS ----------------
def vue_clients(df: pd.DataFrame, palette: dict):
    """Liste des clients (nom, téléphone, pays, plateforme, res_id)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Clients — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucun client.")
        return

    clients = df[["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]].copy()
    for c in ["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]:
        clients[c] = clients[c].astype(str).str.strip().replace({"nan": ""})

    need = clients["pays"].eq("") | clients["pays"].isna()
    if need.any():
        clients.loc[need, "pays"] = clients.loc[need, "telephone"].apply(_phone_country)

    cols_order = ["nom_client", "pays", "telephone", "email", "plateforme", "res_id"]
    clients = clients[cols_order]
    clients = clients.loc[clients["nom_client"] != ""].drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)


# ---------------- ID ----------------
def vue_id(df: pd.DataFrame, palette: dict):
    """Affiche les identifiants (res_id) avec infos principales."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🆔 Identifiants — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    tbl = df[["res_id", "nom_client", "telephone", "email", "plateforme", "pays"]].copy()
    for c in ["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]:
        tbl[c] = tbl[c].astype(str).str.strip().replace({"nan": ""})
    need = tbl["pays"].eq("") | tbl["pays"].isna()
    if need.any():
        tbl.loc[need, "pays"] = tbl.loc[need, "telephone"].apply(_phone_country)
    tbl = tbl.dropna(subset=["res_id"])
    tbl = tbl[tbl["res_id"] != ""].drop_duplicates()
    st.dataframe(tbl, use_container_width=True)

# ============================== PART 5/5 — SMS, PARAMÈTRES, INDICATIFS, MAIN ==============================

def vue_sms(df: pd.DataFrame, palette: dict):
    """Page SMS — messages préformatés avant arrivée et après départ (copier/coller)."""
    from urllib.parse import quote
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation disponible.")
        return

    dfv = ensure_schema(df).copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"] = _to_date(dfv["date_depart"])

    # ---- Pré-arrivée ----
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arr = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = dfv.dropna(subset=["telephone", "nom_client", "date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"] == target_arr) & (~_to_bool_series(pre["sms_envoye"]))]

    if pre.empty:
        st.info("Aucun client à contacter pour la date sélectionnée.")
    else:
        pre = pre.sort_values("date_arrivee")
        opts = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.reset_index().iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=opts, index=None)
        if pick:
            idx = int(pick.split(":")[0])
            r = pre.reset_index().loc[idx]
            nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
            arr_txt = r["date_arrivee"].strftime("%d/%m/%Y") if pd.notna(r["date_arrivee"]) else ""
            dep_txt = r["date_depart"].strftime("%d/%m/%Y") if pd.notna(r["date_depart"]) else ""

            msg = (
                f"{apt_name.upper()}\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuitees}\n\n"
                f"Bonjour {r.get('nom_client','')}\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre réception, "
                "nous vous demandons de bien vouloir remplir la fiche ci-dessous :\n"
                f"{FORM_SHORT_URL}\n\n"
                "Parking disponible sur place.\n"
                "Check-in à partir de 14:00 et check-out avant 11:00.\n"
                "Nous serons là pour vous remettre les clés.\n\n"
                "Consignes à bagages disponibles en ville.\n\n"
                "Annick & Charley\n\n"
                "******\n\n"
                "Welcome!\n\n"
                "We are delighted to welcome you soon to Nice. To better organize your reception, "
                "please fill this form:\n"
                f"{FORM_SHORT_URL}\n\n"
                "Parking available on site.\n"
                "Check-in from 2:00 p.m. — check-out before 11:00 a.m.\n"
                "We’ll be there when you arrive with the keys.\n\n"
                "Best regards,\nAnnick & Charley"
            )

            st.text_area("📋 Copier le message", value=msg, height=360)
            e164 = _format_phone_e164(r.get("telephone",""))
            only_digits = "".join(ch for ch in e164 if ch.isdigit())
            enc = quote(msg)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé' pour ce client"):
                df.loc[r["index"], "sms_envoye"] = True
                if sauvegarder_donnees(df):
                    st.success("Marqué ✅")
                    st.rerun()

    st.markdown("---")

    # ---- Post-départ ----
    st.subheader("📤 Post-départ (départs du jour)")
    target_dep = st.date_input("Départs du", date.today(), key="post_date")
    post = dfv.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post = post[(post["date_depart"] == target_dep) & (~_to_bool_series(post["post_depart_envoye"]))]

    if post.empty:
        st.info("Aucun message post-départ à envoyer aujourd’hui.")
    else:
        post = post.sort_values("date_depart")
        opts2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.reset_index().iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=opts2, index=None)
        if pick2:
            idx2 = int(pick2.split(":")[0])
            r2 = post.reset_index().loc[idx2]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Un grand merci pour votre séjour, nous espérons que tout s’est bien passé.\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for your stay.\n"
                "We hope you had a great time. Always welcome back!\n\n"
                "Annick & Charley"
            )
            st.text_area("📋 Copier le message", value=msg2, height=280)
            e164b = _format_phone_e164(r2.get("telephone",""))
            only_digits_b = "".join(ch for ch in e164b if ch.isdigit())
            enc2 = quote(msg2)
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits_b}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button("✅ Marquer 'post-départ envoyé' pour ce client"):
                df.loc[r2["index"], "post_depart_envoye"] = True
                if sauvegarder_donnees(df):
                    st.success("Marqué ✅")
                    st.rerun()


# ---------------- PARAMÈTRES ----------------
def vue_settings(df: pd.DataFrame, palette: dict):
    """Sauvegarde / restauration + reset apartments.csv + cache."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header("⚙️ Paramètres")
    st.subheader(apt_name)
    print_buttons()

    # Sauvegarde CSV
    st.markdown("### 💾 Sauvegarde")
    try:
        out = ensure_schema(df).copy()
        out["pays"] = out["telephone"].apply(_phone_country)
        for col in ["date_arrivee", "date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        csv_bytes = out.to_csv(sep=";", index=False).encode("utf-8")
    except Exception:
        csv_bytes = b""
    st.download_button("⬇️ Exporter CSV", data=csv_bytes, file_name="resa_export.csv", mime="text/csv")

    st.markdown("### ♻️ Restauration")
    up = st.file_uploader("Restaurer (CSV ou XLSX)", type=["csv","xlsx"])
    if up is not None:
        try:
            if up.name.lower().endswith(".xlsx"):
                tmp = pd.read_excel(up, dtype=str)
            else:
                tmp = _detect_delimiter_and_read(up.read())
            prev = ensure_schema(tmp)
            st.dataframe(prev.head(10))
            if st.button("✅ Confirmer la restauration"):
                save = prev.copy()
                for col in ["date_arrivee","date_depart"]:
                    save[col] = pd.to_datetime(save[col], errors="coerce").dt.strftime("%d/%m/%Y")
                save.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
                st.cache_data.clear()
                st.success("Fichier restauré — rechargement…")
                st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    st.markdown("### 🧹 Vider le cache")
    if st.button("Vider cache"):
        st.cache_data.clear()
        st.rerun()


# ---------------- INDICATIFS PAYS ----------------
def vue_indicatifs(df: pd.DataFrame, palette: dict):
    """Page pour gérer les indicatifs téléphoniques et pays."""
    st.header("🌍 Indicateurs pays")
    print_buttons()
    indicatifs = load_indicatifs().copy()
    st.dataframe(indicatifs, use_container_width=True)
    if st.button("🔄 Recharger depuis disque"):
        st.cache_data.clear()
        st.success("Indicatifs rechargés.")
        st.rerun()


# ---------------- MAIN ----------------
def main():
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1","true","True","yes"):
        st.cache_data.clear()

    changed = _select_apartment_sidebar()
    if changed:
        st.cache_data.clear()

    mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    df, palette_loaded = _load_data_for_active_apartment()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

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