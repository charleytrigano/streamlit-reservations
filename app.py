# ============================== PART 1/5 — IMPORTS, CONFIG, STYLES, HELPERS ==============================
# -*- coding: utf-8 -*-

# ---- Imports
import os, io, re, uuid, hashlib
from html import escape
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange
from urllib.parse import quote

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

# ---- App config
st.set_page_config(
    page_title="✨ Villa Tobias — Gestion des Réservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---- Constantes (seront remplacées dynamiquement par l'appartement actif)
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"
APARTMENTS_CSV   = "apartments.csv"
CODES_PAYS_CSV   = "country_codes.csv"   # <— nouveau : table indicatifs + drapeaux

DEFAULT_PALETTE = {
    "Booking": "#1b9e77",
    "Airbnb":  "#d95f02",
    "Abritel": "#7570b3",
    "Direct":  "#e7298a",
}

# Google Form & Sheet
FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# ============================== STYLE ==============================
def _apply_custom_css(light: bool):
    """Styles globaux + styles impression (A4 paysage)."""
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    chip_bg = "#eee" if light else "#2a2f3a"
    chip_fg = "#222" if light else "#eee"

    css = f"""
    <style>
      html, body, [data-testid="stAppViewContainer"] {{
        background:{bg}; color:{fg};
      }}
      [data-testid="stSidebar"] {{ background:{side}; border-right:1px solid {border}; }}
      .glass {{ background:{"rgba(255,255,255,.65)" if light else "rgba(255,255,255,.06)"}; 
               border:1px solid {border}; border-radius:12px; padding:12px; margin:10px 0; }}
      .chip {{ display:inline-block; padding:6px 10px; border-radius:12px; margin:4px 6px;
               font-size:.86rem; background:{chip_bg}; color:{chip_fg} }}
      .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; }}
      .cal-cell {{ border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px;
                  position:relative; overflow:hidden; background:{"#fff" if light else "#0b0d12"}; }}
      .cal-cell.outside {{ opacity:.45; }}
      .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
      .resa-pill {{ padding:4px 6px; border-radius:6px; font-size:.84rem; margin-top:22px; color:#fff;
                   white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
      .cal-header {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; font-weight:700;
                     opacity:.8; margin:6px 0 8px; }}

      /* Impression A4 paysage + masquage éléments non-essentiels */
      @page {{ size: A4 landscape; margin: 10mm; }}
      .print-header {{ display:none; }}
      @media print {{
        .print-hide, [data-testid="stSidebar"], header, footer {{ display:none !important; }}
        .print-header {{ display:block !important; font-weight:700; margin-bottom:8px; }}
        .glass {{ box-shadow:none; }}
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def print_buttons(location: str = "main"):
    target = st.sidebar if location == "sidebar" else st
    target.button("🖨️ Imprimer", key=f"print_btn_{location}")
    # Injecte JS pour lancer window.print() au clic
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
        ["true", "1", "oui", "vrai", "yes", "y", "t"]
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

# ============================== COUNTRY CODES (CSV + drapeaux) ==============================
def _ensure_country_csv_exists():
    """Crée un CSV par défaut si absent."""
    if os.path.exists(CODES_PAYS_CSV):
        return
    default = (
        "prefix,country,iso2\n"
        "33,France,FR\n"
        "34,Espagne,ES\n"
        "49,Allemagne,DE\n"
        "44,Royaume-Uni,GB\n"
        "39,Italie,IT\n"
        "41,Suisse,CH\n"
        "32,Belgique,BE\n"
        "352,Luxembourg,LU\n"
        "351,Portugal,PT\n"
        "1,États-Unis/Canada,US\n"
        "61,Australie,AU\n"
        "64,Nouvelle-Zélande,NZ\n"
        "420,Tchéquie,CZ\n"
        "421,Slovaquie,SK\n"
        "36,Hongrie,HU\n"
        "40,Roumanie,RO\n"
        "30,Grèce,GR\n"
        "31,Pays-Bas,NL\n"
        "353,Irlande,IE\n"
        "354,Islande,IS\n"
        "358,Finlande,FI\n"
        "46,Suède,SE\n"
        "47,Norvège,NO\n"
        "48,Pologne,PL\n"
        "43,Autriche,AT\n"
        "45,Danemark,DK\n"
        "90,Turquie,TR\n"
        "212,Maroc,MA\n"
        "216,Tunisie,TN\n"
        "971,Émirats Arabes Unis,AE\n"
    )
    with open(CODES_PAYS_CSV, "w", encoding="utf-8", newline="") as f:
        f.write(default)

def _read_country_codes() -> pd.DataFrame:
    _ensure_country_csv_exists()
    raw = _load_file_bytes(CODES_PAYS_CSV)
    df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame(columns=["prefix","country","iso2"])
    if df is None or df.empty:
        return pd.DataFrame(columns=["prefix", "country", "iso2"])
    df.columns = [str(c).strip().lower() for c in df.columns]
    for c in ("prefix", "country", "iso2"):
        if c not in df.columns:
            df[c] = ""
    df["prefix"] = df["prefix"].astype(str).str.replace(r"\D", "", regex=True)
    df["country"] = df["country"].astype(str).str.strip()
    df["iso2"] = df["iso2"].astype(str).str.upper().str.strip()
    df = df[(df["prefix"] != "") & (df["country"] != "")]
    df = df.drop_duplicates(subset=["prefix"], keep="first")
    return df[["prefix","country","iso2"]]

def _save_country_codes(df_codes: pd.DataFrame):
    save = df_codes.copy()
    save["prefix"] = save["prefix"].astype(str).str.replace(r"\D", "", regex=True)
    save["country"] = save["country"].astype(str).str.strip()
    save["iso2"] = save["iso2"].astype(str).str.upper().str.strip()
    save = save[(save["prefix"]!="") & (save["country"]!="")]
    save = save.drop_duplicates(subset=["prefix"])
    save.to_csv(CODES_PAYS_CSV, index=False, sep=";", encoding="utf-8", lineterminator="\n")
    st.cache_data.clear()

def _flag_emoji(iso2: str) -> str:
    """Retourne le drapeau emoji à partir du code ISO2 (FR → 🇫🇷)."""
    iso = (iso2 or "").upper()
    if len(iso) != 2 or not iso.isalpha():
        return "🏳️"
    base = 127397
    return chr(ord(iso[0]) + base) + chr(ord(iso[1]) + base)

def _phone_country(phone: str, df_codes: pd.DataFrame | None = None) -> str:
    """Déduit le pays via indicatif, en utilisant la table CSV."""
    if df_codes is None:
        df_codes = _read_country_codes()
    p = str(phone or "").strip()
    if not p:
        return ""
    if p.startswith("+"):
        num = p[1:]
    elif p.startswith("00"):
        num = p[2:]
    elif p.startswith("0"):
        return "France"
    else:
        num = p
    # tester longueurs décroissantes
    prefixes = sorted(df_codes["prefix"].unique().tolist(), key=lambda x: -len(x))
    for pref in prefixes:
        if num.startswith(pref):
            row = df_codes[df_codes["prefix"] == pref].iloc[0]
            return row["country"]
    return "Inconnu"

# ============================== NORMALISATION & SAUVEGARDE ==============================
def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Renommages fréquents
    rename_map = {
        "Payé":"paye","Client":"nom_client","Plateforme":"plateforme",
        "Arrivée":"date_arrivee","Départ":"date_depart","Nuits":"nuitees",
        "Brut (€)":"prix_brut"
    }
    df.rename(columns=rename_map, inplace=True)

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = pd.Series([None]*len(df), index=df.index)

    for c in df.columns:
        df[c] = _as_series(df[c], index=df.index)

    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b])

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    mask_ok = pd.notna(df["date_arrivee"]) & pd.notna(df["date_depart"])
    if mask_ok.any():
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)

    prix_brut = _to_num(df["prix_brut"])
    commissions = _to_num(df["commissions"])
    frais_cb = _to_num(df["frais_cb"])
    menage = _to_num(df["menage"])
    taxes  = _to_num(df["taxes_sejour"])

    df["prix_net"] = (prix_brut - commissions - frais_cb).fillna(0.0)
    df["charges"]  = (prix_brut - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - menage - taxes).fillna(0.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        df["%"] = np.where(prix_brut > 0, (df["charges"]/prix_brut*100), 0.0).astype(float)

    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res,"res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    for c in ["nom_client","plateforme","telephone","email","pays"]:
        df[c] = df[c].astype(str).replace({"nan":"","None":""}).str.strip()

    # Compléter pays via indicatif si manquant
    need = df["pays"].eq("") | df["pays"].isna()
    if need.any():
        codes = _read_country_codes()
        df.loc[need, "pays"] = df.loc[need, "telephone"].apply(lambda x: _phone_country(x, codes))

    return df[BASE_COLS]

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations: str, csv_plateformes: str):
    # crée les fichiers s'ils n'existent pas
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

    rawp = _load_file_bytes(csv_plateformes)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if {"plateforme","couleur"}.issubset(pal_df.columns):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception as e:
            st.warning(f"Erreur de palette : {e}")
    return df, palette


# ============================== PART 2/5 — APARTMENTS (sélecteur sans mot de passe) ==============================

def _read_apartments_csv() -> pd.DataFrame:
    """Charge apartments.csv (séparateur auto) et normalise {slug, name}."""
    try:
        if not os.path.exists(APARTMENTS_CSV):
            return pd.DataFrame(columns=["slug", "name"])
        raw = _load_file_bytes(APARTMENTS_CSV)
        df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame(columns=["slug", "name"])

        # colonnes et nettoyage
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
    Affiche le sélecteur d'appartement dans la sidebar et met à jour les chemins
    CSV_RESERVATIONS / CSV_PLATEFORMES en session. Retourne True si la sélection a changé.
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

    changed = (
        slug != st.session_state.get("apt_slug", "") or name != st.session_state.get("apt_name", "")
    )

    # mémorise et synchronise les chemins actifs
    st.session_state["apt_slug"] = slug
    st.session_state["apt_name"] = name
    st.session_state["CSV_RESERVATIONS"] = f"reservations_{slug}.csv"
    st.session_state["CSV_PLATEFORMES"] = f"plateformes_{slug}.csv"

    # met à jour les globales utilisées par les fonctions d’export/restauration
    global CSV_RESERVATIONS, CSV_PLATEFORMES
    CSV_RESERVATIONS = st.session_state["CSV_RESERVATIONS"]
    CSV_PLATEFORMES = st.session_state["CSV_PLATEFORMES"]

    st.sidebar.success(f"Connecté : {name}")
    try:
        print_buttons(location="sidebar")
    except Exception:
        pass

    return changed


def _load_data_for_active_apartment():
    """Charge les données (réservations + palette) pour l'appartement actif."""
    apt = _current_apartment()
    if not apt:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_pal = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
    return charger_donnees(csv_res, csv_pal)


# ============================== PART 3/5 — VUES : ACCUEIL / RÉSERVATIONS / AJOUTER / MODIFIER ==============================

def vue_accueil(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    today = date.today()
    tomorrow = today + timedelta(days=1)
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    if df is None or df.empty:
        c1, c2, c3 = st.columns(3)
        with c1: st.info("Aucune arrivée.")
        with c2: st.info("Aucun départ.")
        with c3: st.info("Aucune arrivée demain.")
        return

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    arr = dfv[dfv["date_arrivee"] == today][["nom_client", "telephone", "plateforme", "pays"]].copy()
    dep = dfv[dfv["date_depart"]  == today][["nom_client", "telephone", "plateforme", "pays"]].copy()
    arr_plus1 = dfv[dfv["date_arrivee"] == tomorrow][["nom_client", "telephone", "plateforme", "pays"]].copy()

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
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")

    years_avail = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1, 12 + 1))
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

    # KPIs
    brut    = float(pd.to_numeric(data["prix_brut"],  errors="coerce").fillna(0).sum())
    net     = float(pd.to_numeric(data["prix_net"],   errors="coerce").fillna(0).sum())
    base    = float(pd.to_numeric(data["base"],       errors="coerce").fillna(0).sum())
    nuits   = int(  pd.to_numeric(data["nuitees"],    errors="coerce").fillna(0).sum())
    charges = float(pd.to_numeric(data["charges"],    errors="coerce").fillna(0).sum())
    adr     = (net / nuits) if nuits > 0 else 0.0

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
        unsafe_allow_html=True
    )
    st.markdown("---")

    order_idx = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order_idx]
    st.dataframe(data.drop(columns=["date_arrivee_dt"]), use_container_width=True)


def vue_ajouter(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter une réservation — {apt_name}")
    print_buttons()

    with st.form("form_add", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom  = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel  = st.text_input("Téléphone")
            arr  = st.date_input("Arrivée", date.today())
            dep  = st.date_input("Départ",  date.today() + timedelta(days=1))
        with c2:
            plat = st.selectbox("Plateforme", list(palette.keys()))
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage  = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes   = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye    = st.checkbox("Payé", value=False)

        if st.form_submit_button("✅ Ajouter"):
            if not nom or dep <= arr:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nuitees = (dep - arr).days
                new = pd.DataFrame([{
                    "nom_client": nom, "email": email, "telephone": tel, "plateforme": plat,
                    "date_arrivee": arr, "date_depart": dep, "nuitees": nuitees,
                    "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                    "menage": menage, "taxes_sejour": taxes, "paye": paye
                }])
                df2 = ensure_schema(pd.concat([df, new], ignore_index=True))
                if sauvegarder_donnees(df2):
                    st.success(f"Réservation pour {nom} ajoutée.")
                    st.rerun()


def vue_modifier(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client', '')} ({r.get('date_arrivee', '')})" for i, r in df_sorted.iterrows()]
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
            depart  = st.date_input("Départ", value=row.get("date_depart"))
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
                "nom_client": nom, "email": email, "telephone": tel,
                "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye,
                "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes,
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


# ============================== PART 4/5 — VUES : PLATEFORMES / CALENDRIER ==============================

def vue_plateformes(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes & couleurs — {apt_name}")
    print_buttons()

    HAS_COLORCOL = hasattr(getattr(st, "column_config", object), "ColorColumn")

    plats_df = sorted(
        df.get("plateforme", pd.Series([], dtype=str))
          .astype(str).str.strip().replace({"nan": ""})
          .dropna().unique().tolist()
    )
    all_plats = sorted(set(list(palette.keys()) + plats_df))
    base = pd.DataFrame({
        "plateforme": all_plats,
        "couleur": [palette.get(p, "#666666") for p in all_plats],
    })

    if HAS_COLORCOL:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorColumn("Couleur (hex)"),
        }
    else:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn(
                "Couleur (hex)",
                help="Ex: #1b9e77",
                validate=r"^#([0-9A-Fa-f]{6})$",
                width="small",
            ),
        }

    edited = st.data_editor(
        base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
        key="palette_editor",
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
            to_save.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("↩️ Palette par défaut", key="restore_palette_btn"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme", "couleur"]).to_csv(
                CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8", lineterminator="\n"
            )
            st.success("Palette par défaut restaurée.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c3.button("🔄 Recharger", key="reload_palette_btn"):
        st.cache_data.clear()
        st.rerun()


def vue_calendrier(df: pd.DataFrame, palette: dict):
    from html import escape  # local pour éviter une dépendance si oublié en tête
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier (grille mensuelle) — {apt_name}")
    print_buttons()

    dfv = df.dropna(subset=["date_arrivee", "date_depart"]).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois",  options=list(range(1, 13)), index=today.month - 1)

    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div>"
        "<div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True
    )

    def day_resas(d):
        mask = (dfv["date_arrivee"] <= d) & (dfv["date_depart"] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)
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
    debut_mois = date(annee, mois, 1)
    fin_mois   = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfv[(dfv["date_arrivee"] <= fin_mois) & (dfv["date_depart"] > debut_mois)].copy()

    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
        plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
        if plat != "Toutes":
            rows = rows[rows["plateforme"] == plat]

        brut  = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
        net   = float(pd.to_numeric(rows["prix_net"],  errors="coerce").fillna(0).sum())
        nuits = int(pd.to_numeric(rows["nuitees"],     errors="coerce").fillna(0).sum())

        st.markdown(
            f"""
            <div class='glass'>
              <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
              <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
              <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
            </div>
            """.replace(",", " "),
            unsafe_allow_html=True
        )
        st.dataframe(
            rows[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "paye", "pays"]],
            use_container_width=True
        )


# ============================== PART 5/5 — RAPPORT / SMS / GOOGLE SHEET / CLIENTS / ID / PARAMÈTRES ==============================

def vue_rapport(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📊 Rapport — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    annee = st.selectbox("Année", ["Toutes"] + sorted(df["annee"].dropna().unique().tolist()))
    mois  = st.selectbox("Mois", ["Tous"] + sorted(df["mois"].dropna().unique().tolist()))
    plat  = st.selectbox("Plateforme", ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist()))
    paysf = st.selectbox("Pays", ["Tous"] + sorted(df["pays"].dropna().unique().tolist()))

    data = df.copy()
    if annee != "Toutes": data = data[data["annee"] == annee]
    if mois  != "Tous":   data = data[data["mois"] == mois]
    if plat  != "Toutes": data = data[data["plateforme"] == plat]
    if paysf != "Tous":   data = data[data["pays"] == paysf]

    st.metric("Total prix net", f"{data['prix_net'].sum():,.2f} €".replace(",", " "))

    # Occupation
    jours_dispos = (data["date_depart"].max() - data["date_arrivee"].min()).days if not data.empty else 0
    occ = (data["nuitees"].sum() / jours_dispos * 100) if jours_dispos > 0 else 0
    st.markdown(f"**Taux global {occ:.1f}%** — Nuitées {data['nuitees'].sum()} — Jours dispo {jours_dispos}")

    st.bar_chart(data.groupby("mois")["prix_net"].sum())


def vue_sms(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    res = st.selectbox("Choisir une réservation", df["res_id"].astype(str).tolist())
    row = df[df["res_id"].astype(str) == res].iloc[0]

    msg_arr = f"""
APPARTEMENT {apt_name}
Plateforme : {row['plateforme']}
Arrivée : {row['date_arrivee']}  Départ : {row['date_depart']}  Nuitées : {row['nuitees']}

Bonjour {row['nom_client']}
Bienvenue chez nous !

Nous sommes ravis de vous accueillir bientôt à Nice.
Merci de remplir la fiche : https://urlr.me/kZuH94
Parking sur place.
Check-in 14h — Check-out 11h.
Bagageries dispo dans chaque quartier.
À bientôt !
Annick & Charley
"""
    st.text_area("Message avant arrivée", msg_arr, height=220)

    msg_dep = f"""
Bonjour {row['nom_client']},

Un grand merci pour votre séjour.
Nous espérons que vous avez passé un moment agréable.
Notre porte vous sera toujours grande ouverte.

Annick & Charley
"""
    st.text_area("Message après départ", msg_dep, height=150)


def vue_google_sheet(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Google Sheet — {apt_name}")
    print_buttons()
    st.markdown("Intégration Google Form & Sheet (configurer vos URLs).")


def vue_clients(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Clients — {apt_name}")
    print_buttons()
    if df.empty:
        st.info("Aucun client.")
        return
    st.dataframe(df[["nom_client", "pays", "telephone", "email", "plateforme", "res_id"]], use_container_width=True)


def vue_id(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🆔 Identifiants — {apt_name}")
    print_buttons()
    if df.empty:
        st.info("Aucun ID.")
        return
    st.dataframe(df[["res_id", "nom_client", "telephone", "pays"]], use_container_width=True)


def vue_settings(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"⚙️ Paramètres — {apt_name}")
    print_buttons()

    st.subheader("💾 Sauvegarde")
    st.download_button("Exporter réservations", df.to_csv(index=False).encode("utf-8"), "reservations_export.csv")

    st.subheader("♻️ Restauration")
    uploaded = st.file_uploader("Restaurer CSV", type=["csv"])
    if uploaded:
        try:
            new_df = pd.read_csv(uploaded, sep=None, engine="python")
            new_df.to_csv(CSV_RESERVATIONS, index=False)
            st.success("Données restaurées ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")


# ============================== MAIN ==============================
def main():
    st.set_page_config("✨ Villa Tobias — Réservations", layout="wide")
    _apply_custom_css()

    changed = _select_apartment_sidebar()
    df, palette = _load_data_for_active_apartment()

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📝 Google Sheet": vue_google_sheet,
        "👥 Clients": vue_clients,
        "🆔 ID": vue_id,
        "⚙️ Paramètres": vue_settings,
    }

    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)


if __name__ == "__main__":
    main()