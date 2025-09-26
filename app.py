# ============================== PART 1/5 — IMPORTS, CONFIG, STYLES, HELPERS, INDICATIFS ==============================
import os, io, re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange
from html import escape
from urllib.parse import quote

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

# --------------------------------- CONFIG APP ---------------------------------
st.set_page_config(
    page_title="✨ Gestion des Réservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------------------------- CONSTANTES ---------------------------------
# Chemins par défaut (remplacés après sélection d’appartement)
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"
APARTMENTS_CSV   = "apartments.csv"

# Fichier d’indicatifs téléphoniques (prise en charge de plusieurs noms possibles)
INDICATIFS_CSV_CANDIDATES = [
    "indicatifs_pays.csv",           # recommandé
    "indicatifs _pays.csv",          # variante avec espace (si déjà présente dans le repo)
    "countries_with_flags.csv",      # ancien nom éventuel
]

DEFAULT_PALETTE = {
    "Booking": "#1b9e77",
    "Airbnb":  "#d95f02",
    "Abritel": "#7570b3",
    "Direct":  "#e7298a",
}

# Google Form & Sheet (adapter si besoin)
FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# --------------------------------- STYLE / THEME ---------------------------------
def apply_style(light: bool):
    """Thème clair/sombre + styles calendrier + impression A4 paysage."""
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

          /* Impression A4 paysage + masquage des contrôles Streamlit */
          @page {{ size: A4 landscape; margin: 12mm; }}
          @media print {{
            [data-testid="stSidebar"], header, footer {{ display:none !important; }}
            .print-hide {{ display:none !important; }}
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

def print_buttons(location: str = "main"):
    """Bouton Imprimer qui déclenche window.print()."""
    target = st.sidebar if location == "sidebar" else st
    target.button("🖨️ Imprimer", key=f"print_btn_{location}")
    st.markdown(
        """
        <script>
        const findPrintBtn = () => {
          const labels = Array.from(parent.document.querySelectorAll('button span, button p'));
          const el = labels.find(n => n.textContent && n.textContent.trim() === "🖨️ Imprimer");
          if (el) { el.parentElement.onclick = () => window.print(); }
        };
        setTimeout(findPrintBtn, 300);
        </script>
        """,
        unsafe_allow_html=True
    )

# --------------------------------- HELPERS DATA ---------------------------------
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
        st.warning(f"Impossible de générer un Excel (openpyxl requis) : {e}")
        return None, e

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s:
        return ""
    if s.startswith("33"):  # France sans +
        return "+" + s
    if s.startswith("0"):   # 0 français
        return "+33" + s[1:]
    return "+" + s

# --------------------------------- INDICATIFS PAYS ---------------------------------
def _indicatifs_csv_path() -> str:
    """Retourne le premier chemin existant parmi les candidats, sinon le nom recommandé."""
    for p in INDICATIFS_CSV_CANDIDATES:
        if os.path.exists(p):
            return p
    return INDICATIFS_CSV_CANDIDATES[0]  # "indicatifs_pays.csv"

def _create_indicatifs_csv_if_missing():
    """Crée un CSV d’indicatifs minimal si absent (UTF-8)."""
    path = _indicatifs_csv_path()
    if os.path.exists(path):
        return
    # jeu minimal mais propre (tu peux remplacer par ton fichier complet)
    rows = [
        {"indicatif":"33",  "emoji":"🇫🇷", "nom":"France"},
        {"indicatif":"34",  "emoji":"🇪🇸", "nom":"Espagne"},
        {"indicatif":"39",  "emoji":"🇮🇹", "nom":"Italie"},
        {"indicatif":"41",  "emoji":"🇨🇭", "nom":"Suisse"},
        {"indicatif":"32",  "emoji":"🇧🇪", "nom":"Belgique"},
        {"indicatif":"44",  "emoji":"🇬🇧", "nom":"Royaume-Uni"},
        {"indicatif":"49",  "emoji":"🇩🇪", "nom":"Allemagne"},
        {"indicatif":"351", "emoji":"🇵🇹", "nom":"Portugal"},
        {"indicatif":"352", "emoji":"🇱🇺", "nom":"Luxembourg"},
        {"indicatif":"1",   "emoji":"🇺🇸", "nom":"États-Unis/Canada"},
        {"indicatif":"61",  "emoji":"🇦🇺", "nom":"Australie"},
        {"indicatif":"64",  "emoji":"🇳🇿", "nom":"Nouvelle-Zélande"},
        {"indicatif":"971", "emoji":"🇦🇪", "nom":"Émirats arabes unis"},
        {"indicatif":"212", "emoji":"🇲🇦", "nom":"Maroc"},
        {"indicatif":"216", "emoji":"🇹🇳", "nom":"Tunisie"},
    ]
    pd.DataFrame(rows).to_csv(path, index=False, encoding="utf-8")

@st.cache_data(show_spinner=False)
def load_indicatifs() -> pd.DataFrame:
    """Charge les indicatifs (indicatif, emoji, nom)."""
    _create_indicatifs_csv_if_missing()
    path = _indicatifs_csv_path()
    try:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    except Exception:
        df = pd.DataFrame(columns=["indicatif","emoji","nom"])
    # nettoyage
    for c in ["indicatif","emoji","nom"]:
        if c not in df.columns:
            df[c] = ""
        df[c] = df[c].astype(str).str.strip()
    # normaliser indicatif (uniquement chiffres)
    df["indicatif"] = df["indicatif"].str.replace("+","", regex=False)
    df["indicatif"] = df["indicatif"].str.replace(r"\D","", regex=True)
    # dédupliquer par indicatif (garde la première)
    df = df[df["indicatif"] != ""].drop_duplicates(subset=["indicatif"], keep="first")
    return df[["indicatif","emoji","nom"]]

def _phone_country_from_table(phone: str, indicatifs_df: pd.DataFrame) -> str:
    """Retourne le pays déduit du numéro via la table d’indicatifs."""
    p = str(phone or "").strip()
    if not p:
        return ""
    # formats: +33..., 0033..., 0X..., 33...
    if p.startswith("+"):
        p1 = p[1:]
    elif p.startswith("00"):
        p1 = p[2:]
    elif p.startswith("0"):
        return "France"  # cas très courant
    else:
        p1 = p
    # trie par longueur d'indicatif (long d'abord)
    codes = indicatifs_df["indicatif"].dropna().astype(str).tolist()
    codes = sorted(set(codes), key=lambda x: -len(x))
    for code in codes:
        if p1.startswith(code):
            row = indicatifs_df[indicatifs_df["indicatif"] == code].iloc[0]
            return str(row.get("nom") or "")
    return "Inconnu"

def _phone_country(phone: str) -> str:
    """Wrapper utilisé partout dans l’app."""
    indicatifs = load_indicatifs()
    return _phone_country_from_table(phone, indicatifs)

# ============================== PART 2/5 — APPARTEMENTS & CHARGEMENT DATA ==============================

def _load_apartments() -> pd.DataFrame:
    """Charge apartments.csv, crée un défaut si absent."""
    if not os.path.exists(APARTMENTS_CSV):
        df = pd.DataFrame([
            {"slug":"villa-tobias","name":"Villa Tobias"},
            {"slug":"le-turenne","name":"Le Turenne"}
        ])
        df.to_csv(APARTMENTS_CSV, index=False, encoding="utf-8")
        return df
    try:
        return pd.read_csv(APARTMENTS_CSV, dtype=str)
    except Exception:
        return pd.DataFrame(columns=["slug","name"])

def _current_apartment() -> dict:
    """Retourne l’appartement sélectionné (slug, name)."""
    slug = st.session_state.get("apartment_slug")
    df = _load_apartments()
    if slug and slug in df["slug"].tolist():
        row = df[df["slug"]==slug].iloc[0].to_dict()
        return row
    return None

def _select_apartment_sidebar() -> bool:
    """Affiche la sélection d’appartement dans la sidebar. Retourne True si changé."""
    df = _load_apartments()
    if df.empty:
        st.sidebar.error("Aucun appartement trouvé dans apartments.csv")
        return False
    options = {r["name"]:r["slug"] for _,r in df.iterrows()}
    inv = {v:k for k,v in options.items()}
    cur = st.session_state.get("apartment_slug") or list(options.values())[0]
    pick = st.sidebar.selectbox("### Appartement", list(options.keys()), index=list(options.values()).index(cur))
    chosen_slug = options[pick]
    st.sidebar.caption(f"Connecté : {pick}")
    if chosen_slug != cur:
        st.session_state["apartment_slug"] = chosen_slug
        # update chemins CSV
        st.session_state["CSV_RESERVATIONS"] = f"{chosen_slug}_reservations.csv"
        st.session_state["CSV_PLATEFORMES"]  = f"{chosen_slug}_plateformes.csv"
        return True
    return False

def _load_data_for_active_apartment():
    """Charge les données réservations et palette de l’appartement courant."""
    apt = _current_apartment()
    if not apt:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE

    res_path = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    plat_path = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)

    # Reservations
    if os.path.exists(res_path):
        try:
            df = pd.read_csv(res_path, dtype=str, sep=";", keep_default_na=False)
        except Exception:
            df = pd.read_csv(res_path, dtype=str, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=BASE_COLS)

    # Plateformes
    if os.path.exists(plat_path):
        try:
            plat = pd.read_csv(plat_path, dtype=str)
            pal = {r["plateforme"]:r["couleur"] for _,r in plat.iterrows() if "plateforme" in r and "couleur" in r}
        except Exception:
            pal = DEFAULT_PALETTE
    else:
        pal = DEFAULT_PALETTE

    return ensure_schema(df), pal

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """S’assure que toutes les colonnes de BASE_COLS existent."""
    if df is None:
        return pd.DataFrame(columns=BASE_COLS)
    dfc = df.copy()
    for c in BASE_COLS:
        if c not in dfc.columns:
            dfc[c] = ""
    return dfc[BASE_COLS]

# ============================== PART 3/5 — VUES: ACCUEIL, RÉSERVATIONS, AJOUTER, MODIFIER, PLATEFORMES ==============================

def vue_accueil(df: pd.DataFrame, palette: dict):
    """Tableau de bord du jour : arrivées, départs, et arrivées J+1."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    today = date.today()
    tomorrow = today + timedelta(days=1)

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    arr = dfv[dfv["date_arrivee"] == today][["nom_client","telephone","plateforme","pays"]]
    dep = dfv[dfv["date_depart"]  == today][["nom_client","telephone","plateforme","pays"]]
    arr_plus1 = dfv[dfv["date_arrivee"] == tomorrow][["nom_client","telephone","plateforme","pays"]]

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
    """Liste des réservations + filtres + totaux (brut, net, charges, base, nuitées, ADR)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    dfa["date_depart_dt"]  = pd.to_datetime(dfa["date_depart"],  errors="coerce")

    years_avail  = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype("Int64").dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1, 12 + 1))
    plats_avail  = sorted(dfa["plateforme"].astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())

    c1, c2, c3, c4 = st.columns(4)
    year  = c1.selectbox("Année", ["Toutes"] + years_avail, index=0)
    month = c2.selectbox("Mois",  ["Tous"] + months_avail, index=0)
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

    brut    = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net     = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    base    = float(pd.to_numeric(data["base"],      errors="coerce").fillna(0).sum())
    nuits   = float(pd.to_numeric(data["nuitees"],   errors="coerce").fillna(0).sum())
    charges = float(pd.to_numeric(data["charges"],   errors="coerce").fillna(0).sum())
    adr     = (net / nuits) if nuits > 0 else 0.0

    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
          <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
          <span class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></span>
          <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
          <span class='chip'><small>Nuitées</small><br><strong>{int(nuits)}</strong></span>
          <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
        </div>
        """.replace(",", " "),
        unsafe_allow_html=True
    )
    st.markdown("---")

    ord_idx = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[ord_idx]
    st.dataframe(data.drop(columns=["date_arrivee_dt","date_depart_dt"], errors="ignore"), use_container_width=True)


def vue_ajouter(df: pd.DataFrame, palette: dict):
    """Ajout d’une réservation."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter une réservation — {apt_name}")
    print_buttons()

    with st.form("form_add_resa", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom   = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel   = st.text_input("Téléphone")
            arr   = st.date_input("Arrivée", date.today())
            dep   = st.date_input("Départ",  date.today() + timedelta(days=1))
        with c2:
            plat   = st.selectbox("Plateforme", list(palette.keys()))
            brut   = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            comm   = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais  = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes  = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye   = st.checkbox("Payé", value=False)

        submitted = st.form_submit_button("✅ Ajouter")
        if submitted:
            if not nom or dep <= arr:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nuitees = (dep - arr).days
                new = pd.DataFrame([{
                    "nom_client": nom, "email": email, "telephone": tel, "plateforme": plat,
                    "date_arrivee": arr, "date_depart": dep, "nuitees": nuitees,
                    "prix_brut": brut, "commissions": comm, "frais_cb": frais,
                    "menage": menage, "taxes_sejour": taxes, "paye": paye
                }])
                df2 = ensure_schema(pd.concat([df, new], ignore_index=True))
                if sauvegarder_donnees(df2):
                    st.success(f"Réservation pour {nom} ajoutée.")
                    st.rerun()


def vue_modifier(df: pd.DataFrame, palette: dict):
    """Modification / suppression d’une ligne de réservation existante."""
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
    row = df.loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom     = st.text_input("Nom", value=row.get("nom_client","") or "")
            email   = st.text_input("Email", value=row.get("email","") or "")
            tel     = st.text_input("Téléphone", value=row.get("telephone","") or "")
            arrivee = st.date_input("Arrivée", value=_to_date(pd.Series([row.get("date_arrivee")])).iloc[0] or date.today())
            depart  = st.date_input("Départ",  value=_to_date(pd.Series([row.get("date_depart")])).iloc[0] or (date.today()+timedelta(days=1)))
        with c2:
            palette_keys = list(palette.keys())
            plat_idx = palette_keys.index(row.get("plateforme")) if row.get("plateforme") in palette_keys else 0
            plat   = st.selectbox("Plateforme", options=palette_keys, index=plat_idx)
            paye   = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut   = float(pd.to_numeric(row.get("prix_brut"), errors="coerce") or 0)
            comm   = float(pd.to_numeric(row.get("commissions"), errors="coerce") or 0)
            frais  = float(pd.to_numeric(row.get("frais_cb"), errors="coerce") or 0)
            menage = float(pd.to_numeric(row.get("menage"), errors="coerce") or 0)
            taxes  = float(pd.to_numeric(row.get("taxes_sejour"), errors="coerce") or 0)

            brut   = st.number_input("Prix brut", min_value=0.0, step=0.01, value=brut)
            comm   = st.number_input("Commissions", min_value=0.0, step=0.01, value=comm)
            frais  = st.number_input("Frais CB", min_value=0.0, step=0.01, value=frais)
            menage = st.number_input("Ménage",   min_value=0.0, step=0.01, value=menage)
            taxes  = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=taxes)

        col_save, col_del = st.columns([0.7, 0.3])
        if col_save.form_submit_button("💾 Enregistrer"):
            updates = {
                "nom_client": nom, "email": email, "telephone": tel,
                "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye,
                "prix_brut": brut, "commissions": comm, "frais_cb": frais,
                "menage": menage, "taxes_sejour": taxes
            }
            for k, v in updates.items():
                df.loc[original_idx, k] = v
            if sauvegarder_donnees(df):
                st.success("Modifié ✅")
                st.rerun()

        if col_del.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé.")
                st.rerun()


def vue_plateformes(df: pd.DataFrame, palette: dict):
    """Edition des plateformes & couleurs (palette)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes & couleurs — {apt_name}")
    print_buttons()

    # plateformes observées dans les données
    plats_df = sorted(
        df.get("plateforme", pd.Series([], dtype=str))
          .astype(str).str.strip().replace({"nan": ""}).dropna().unique().tolist()
    )
    all_plats = sorted(set(list(palette.keys()) + plats_df))
    base = pd.DataFrame({
        "plateforme": all_plats,
        "couleur": [palette.get(p, "#666666") for p in all_plats]
    })

    has_colorcol = hasattr(getattr(st, "column_config", object), "ColorColumn")
    if has_colorcol:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorColumn("Couleur (hex)")
        }
    else:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn("Couleur (hex)", help="Ex: #1b9e77")
        }

    edited = st.data_editor(
        base, num_rows="dynamic", use_container_width=True, hide_index=True, column_config=col_cfg, key="palette_editor"
    )

    c1, c2, c3 = st.columns([0.5, 0.3, 0.2])
    if c1.button("💾 Enregistrer la palette", key="save_palette_btn"):
        try:
            to_save = edited.copy()
            to_save["plateforme"] = to_save["plateforme"].astype(str).str.strip()
            to_save["couleur"]    = to_save["couleur"].astype(str).str.strip()
            to_save = to_save[to_save["plateforme"] != ""].drop_duplicates(subset=["plateforme"])
            # chemin par appart
            plat_path = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
            to_save.to_csv(plat_path, index=False, encoding="utf-8")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("↩️ Palette par défaut", key="restore_palette_btn"):
        try:
            plat_path = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(
                plat_path, index=False, encoding="utf-8"
            )
            st.success("Palette restaurée.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c3.button("🔄 Recharger", key="reload_palette_btn"):
        st.cache_data.clear()
        st.rerun()

# ============================== PART 4/5 — CALENDRIER, RAPPORT, EXPORT ICS, GOOGLE SHEET, CLIENTS, ID ==============================

def vue_calendrier(df: pd.DataFrame, palette: dict):
    """Calendrier mensuel en grille + récap du mois sélectionné."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier (grille mensuelle) — {apt_name}")
    print_buttons()

    dfv = df.dropna(subset=["date_arrivee", "date_depart"]).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    today = date.today()
    years = sorted(
        pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique().tolist(),
        reverse=True
    ) or [today.year]

    annee = st.selectbox("Année", options=years, index=0, key="cal_year")
    mois  = st.selectbox("Mois",  options=list(range(1, 13)), index=today.month - 1, key="cal_month")

    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div>"
        "<div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True
    )

    def day_resas(d):
        mask = (dfv["date_arrivee"] <= d) & (dfv["date_depart"] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)  # Lundi
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
                        name  = str(r.get("nom_client") or "")[:22]
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
    fin_mois   = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfv[(dfv["date_arrivee"] <= fin_mois) & (dfv["date_depart"] > debut_mois)].copy()

    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
        return

    plats = ["Toutes"] + sorted(rows["plateforme"].dropna().astype(str).unique().tolist())
    plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
    if plat != "Toutes":
        rows = rows[rows["plateforme"].astype(str) == plat]

    # Totaux mois
    brut  = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
    net   = float(pd.to_numeric(rows["prix_net"],  errors="coerce").fillna(0).sum())
    nuits = int(pd.to_numeric(rows["nuitees"],    errors="coerce").fillna(0).sum())

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
        rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye","pays"]],
        use_container_width=True
    )


def vue_rapport(df: pd.DataFrame, palette: dict):
    """Rapports: occupation, comparaisons, métriques financières, analyse par pays."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📊 Rapport — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune donnée.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    dfa["date_depart_dt"]  = pd.to_datetime(dfa["date_depart"],  errors="coerce")

    years_avail  = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1, 13))
    plats_avail  = sorted(dfa["plateforme"].astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())

    # Pays (complète via téléphone si vide)
    dfa["_pays"] = dfa["pays"].astype(str).replace({"": np.nan})
    dfa["_pays"] = dfa["_pays"].fillna(dfa["telephone"].apply(_phone_country)).replace("", "Inconnu")
    pays_avail   = sorted(dfa["_pays"].unique().tolist())
    if "France" in pays_avail:
        pays_avail.remove("France")
        pays_avail = ["France"] + pays_avail

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1.2, 1.2])
    year   = c1.selectbox("Année",     ["Toutes"] + years_avail, index=0)
    month  = c2.selectbox("Mois",      ["Tous"] + months_avail, index=0)
    plat   = c3.selectbox("Plateforme",["Toutes"] + plats_avail, index=0)
    payf   = c4.selectbox("Pays",      ["Tous"] + pays_avail, index=0)
    metric = c5.selectbox("Métrique",  ["prix_brut","prix_net","base","charges","menage","taxes_sejour","nuitees"], index=1)

    data = dfa.copy()
    data["pays"] = data["_pays"]
    if year != "Toutes":
        data = data[data["date_arrivee_dt"].dt.year == int(year)]
    if month != "Tous":
        data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]
    if payf != "Tous":
        data = data[data["pays"] == payf]

    if data.empty:
        st.warning("Aucune donnée après filtres.")
        return

    # ---- Taux d'occupation par mois ----
    st.markdown("---")
    st.subheader("📅 Taux d'occupation")
    data["mois"] = data["date_arrivee_dt"].dt.to_period("M").astype(str)
    data["nuitees_calc"] = (data["date_depart_dt"] - data["date_arrivee_dt"]).dt.days.clip(lower=0)
    occ_mois = data.groupby(["mois", "plateforme"], as_index=False)["nuitees_calc"].sum().rename(
        columns={"nuitees_calc": "nuitees_occupees"}
    )

    def jours_dans_mois(periode_str):
        an, mo = map(int, periode_str.split("-"))
        return monthrange(an, mo)[1]

    occ_mois["jours_dans_mois"] = occ_mois["mois"].apply(jours_dans_mois)
    occ_mois["taux_occupation"] = (occ_mois["nuitees_occupees"] / occ_mois["jours_dans_mois"]) * 100

    col_plat, col_export = st.columns([1, 1])
    plat_occ = col_plat.selectbox("Filtrer par plateforme (occupation)", ["Toutes"] + plats_avail, index=0)
    occ_filtered = occ_mois if plat_occ == "Toutes" else occ_mois[occ_mois["plateforme"] == plat_occ]

    filtered_nuitees = pd.to_numeric(occ_filtered["nuitees_occupees"], errors="coerce").fillna(0).sum()
    filtered_jours   = pd.to_numeric(occ_filtered["jours_dans_mois"], errors="coerce").fillna(0).sum()
    taux_global_filtered = (filtered_nuitees / filtered_jours) * 100 if filtered_jours > 0 else 0

    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'><small>Taux global</small><br><strong>{taux_global_filtered:.1f}%</strong></span>
          <span class='chip'><small>Nuitées occupées</small><br><strong>{int(filtered_nuitees)}</strong></span>
          <span class='chip'><small>Jours dispos</small><br><strong>{int(filtered_jours)}</strong></span>
          <span class='chip'><small>Pays filtré</small><br><strong>{payf if payf!='Tous' else 'Tous'}</strong></span>
        </div>
        """,
        unsafe_allow_html=True
    )

    occ_export = (
        occ_filtered[["mois","plateforme","nuitees_occupees","jours_dans_mois","taux_occupation"]]
        .copy()
        .sort_values(["mois","plateforme"], ascending=[False, True])
    )
    col_export.download_button(
        "⬇️ Exporter occupation (CSV)",
        data=occ_export.to_csv(index=False).encode("utf-8"),
        file_name="taux_occupation.csv", mime="text/csv"
    )
    xlsx_occ, _ = _df_to_xlsx_bytes(occ_export, "Taux d'occupation")
    if xlsx_occ:
        col_export.download_button(
            "⬇️ Exporter occupation (Excel)",
            data=xlsx_occ,
            file_name="taux_occupation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    st.dataframe(occ_export.assign(taux_occupation=lambda x: x["taux_occupation"].round(1)), use_container_width=True)

    # ---- Comparaison des taux d'occupation par année ----
    st.markdown("---")
    st.subheader("📊 Comparaison des taux d'occupation par année")
    data["annee"] = data["date_arrivee_dt"].dt.year
    occ_annee = (
        data.groupby(["annee","plateforme"])["nuitees_calc"].sum()
        .reset_index()
        .rename(columns={"nuitees_calc":"nuitees_occupees"})
    )

    def jours_dans_annee(an):
        return 366 if (an % 4 == 0 and an % 100 != 0) or (an % 400 == 0) else 365

    occ_annee["jours_dans_annee"] = occ_annee["annee"].apply(jours_dans_annee)
    occ_annee["taux_occupation"]  = (occ_annee["nuitees_occupees"] / occ_annee["jours_dans_annee"]) * 100

    default_years = sorted(occ_annee["annee"].unique())[-2:] if occ_annee["annee"].nunique() >= 2 else sorted(occ_annee["annee"].unique())
    annees_comparaison = st.multiselect(
        "Sélectionner les années à comparer",
        options=sorted(occ_annee["annee"].unique()),
        default=default_years
    )
    if annees_comparaison:
        occ_comp = occ_annee[occ_annee["annee"].isin(annees_comparaison)].copy()
        try:
            chart_comparaison = alt.Chart(occ_comp).mark_bar().encode(
                x=alt.X("annee:N", title="Année"),
                y=alt.Y("taux_occupation:Q", title="Taux d'occupation (%)", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("plateforme:N", title="Plateforme"),
                tooltip=["annee","plateforme", alt.Tooltip("taux_occupation:Q", format=".1f")]
            ).properties(height=400)
            st.altair_chart(chart_comparaison, use_container_width=True)
        except Exception as e:
            st.warning(f"Graphique indisponible : {e}")
        st.dataframe(
            occ_comp[["annee","plateforme","nuitees_occupees","taux_occupation"]]
            .sort_values(["annee","plateforme"])
            .assign(taux_occupation=lambda x: x["taux_occupation"].round(1)),
            use_container_width=True
        )

    # ---- Métriques financières ----
    st.markdown("---")
    st.subheader("💰 Métriques financières")
    data["mois"] = data["date_arrivee_dt"].dt.to_period("M").astype(str)
    total_val = float(pd.to_numeric(data[metric], errors="coerce").fillna(0).sum())
    st.markdown(f"**Total {metric.replace('_',' ')} : {total_val:,.2f}**".replace(",", " "))
    agg_mois = data.groupby("mois", as_index=False)[metric].sum().sort_values("mois")
    agg_mois_plat = data.groupby(["mois","plateforme"], as_index=False)[metric].sum().sort_values(["mois","plateforme"])
    with st.expander("Détail par mois", expanded=True):
        st.dataframe(agg_mois, use_container_width=True)
    with st.expander("Détail par mois et par plateforme", expanded=False):
        st.dataframe(agg_mois_plat, use_container_width=True)
    try:
        chart = alt.Chart(agg_mois_plat).mark_bar().encode(
            x=alt.X("mois:N", sort=None, title="Mois"),
            y=alt.Y(f"{metric}:Q", title=metric.replace("_"," ").title()),
            color=alt.Color("plateforme:N", title="Plateforme"),
            tooltip=["mois","plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
        )
        st.altair_chart(chart.properties(height=420), use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique indisponible : {e}")

    # ---- Analyse par pays ----
    st.markdown("---")
    st.subheader("🌍 Analyse par pays")
    years_pays = years_avail
    year_pays = st.selectbox("Année (analyse pays)", ["Toutes"] + years_pays, index=0, key="year_pays")
    data_p = dfa.copy()
    data_p["pays"] = dfa["_pays"]
    if year_pays != "Toutes":
        data_p = data_p[data_p["date_arrivee_dt"].dt.year == int(year_pays)]
    data_p["nuitees_calc"] = (data_p["date_depart_dt"] - data_p["date_arrivee_dt"]).dt.days.clip(lower=0)
    agg_pays = data_p.groupby("pays", as_index=False).agg(
        reservations=("nom_client", "count"),
        nuitees=("nuitees_calc","sum"),
        prix_brut=("prix_brut","sum"),
        prix_net=("prix_net","sum"),
        menage=("menage","sum"),
        taxes_sejour=("taxes_sejour","sum"),
        charges=("charges","sum"),
        base=("base","sum"),
    )
    total_net = float(pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0).sum())
    total_res = int(pd.to_numeric(agg_pays["reservations"], errors="coerce").fillna(0).sum())
    agg_pays["part_revenu_%"] = np.where(
        total_net > 0,
        (pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0) / total_net) * 100,
        0.0
    )
    agg_pays["ADR_net"] = np.where(
        pd.to_numeric(agg_pays["nuitees"], errors="coerce").fillna(0) > 0,
        pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0) / pd.to_numeric(agg_pays["nuitees"], errors="coerce").fillna(0),
        0.0
    )
    agg_pays = agg_pays.sort_values(["prix_net","reservations"], ascending=[False, False])

    nb_pays  = int(agg_pays["pays"].nunique())
    top_pays = agg_pays.iloc[0]["pays"] if not agg_pays.empty else "—"
    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'><small>Année</small><br><strong>{year_pays}</strong></span>
          <span class='chip'><small>Pays distincts</small><br><strong>{nb_pays}</strong></span>
          <span class='chip'><small>Total réservations</small><br><strong>{total_res}</strong></span>
          <span class='chip'><small>Top pays (CA net)</small><br><strong>{top_pays}</strong></span>
        </div>
        """,
        unsafe_allow_html=True
    )

    disp = agg_pays.copy()
    for c in ["reservations","nuitees","prix_brut","prix_net","menage","taxes_sejour","charges","base","ADR_net","part_revenu_%"]:
        disp[c] = pd.to_numeric(disp[c], errors="coerce")
    disp["reservations"] = disp["reservations"].fillna(0).astype("int64")
    disp["pays"] = disp["pays"].astype(str).replace({"nan": "Inconnu", "": "Inconnu"})
    disp["prix_brut"]     = disp["prix_brut"].round(2)
    disp["prix_net"]      = disp["prix_net"].round(2)
    disp["ADR_net"]       = disp["ADR_net"].round(2)
    disp["part_revenu_%"] = disp["part_revenu_%"].round(1)

    order_cols = ["pays","reservations","nuitees","prix_brut","prix_net","charges","menage","taxes_sejour","base","ADR_net","part_revenu_%"]
    disp = disp[[c for c in order_cols if c in disp.columns]]
    st.dataframe(disp, use_container_width=True)

    try:
        topN = st.slider("Afficher les N premiers pays (par CA net)", min_value=3, max_value=20, value=12, step=1)
        chart_pays = alt.Chart(agg_pays.head(topN)).mark_bar().encode(
            x=alt.X("pays:N", sort="-y", title="Pays"),
            y=alt.Y("prix_net:Q", title="CA net (€)"),
            tooltip=[
                "pays",
                alt.Tooltip("reservations:Q", title="Réservations"),
                alt.Tooltip("nuitees:Q", title="Nuitées"),
                alt.Tooltip("ADR_net:Q", title="ADR net", format=",.2f"),
                alt.Tooltip("part_revenu_%:Q", title="Part (%)", format=".1f")
            ]
        ).properties(height=420)
        st.altair_chart(chart_pays, use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique 'Analyse pays' indisponible : {e}")

    # ---- Courbe d'évolution ----
    st.markdown("---")
    st.subheader("📈 Évolution du taux d'occupation")
    try:
        chart_occ = alt.Chart(occ_mois).mark_line(point=True).encode(
            x=alt.X("mois:N", sort=None, title="Mois"),
            y=alt.Y("taux_occupation:Q", title="Taux d'occupation (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("plateforme:N", title="Plateforme"),
            tooltip=["mois","plateforme", alt.Tooltip("taux_occupation:Q", format=".1f")]
        )
        st.altair_chart(chart_occ.properties(height=420), use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique du taux d'occupation indisponible : {e}")


def vue_export_ics(df: pd.DataFrame, palette: dict):
    """Export des réservations au format .ics (Google/Apple Calendar)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📆 Export ICS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    years = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique(), reverse=True) or [date.today().year]
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().astype(str).unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfa[dfa["date_arrivee_dt"].dt.year == int(year)].copy()
    if plat != "Tous":
        data = data[data["plateforme"].astype(str) == plat]
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
        summary = f"{apt_name} — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"):
            summary += f" ({r.get('plateforme')})"
        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}",
            f"Prix brut: {float(pd.to_numeric(r.get('prix_brut'), errors='coerce') or 0):.2f} €",
            f"res_id: {r.get('res_id','')}",
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
        mime="text/calendar"
    )


def vue_google_sheet(df: pd.DataFrame, palette: dict):
    """Affiche le Google Form / Sheet intégrés + réponses CSV publiées."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Fiche d'arrivée / Google Sheet — {apt_name}")
    print_buttons()
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")

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
            rep_display = rep.drop(columns=mask_cols, errors="ignore")
        else:
            rep_display = rep
        st.dataframe(rep_display, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")


def vue_clients(df: pd.DataFrame, palette: dict):
    """Liste des clients (nom, pays, tel, email, plateforme, res_id)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Liste des clients — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucun client.")
        return

    clients = df[["nom_client","telephone","email","plateforme","res_id","pays"]].copy()
    for c in ["nom_client","telephone","email","plateforme","res_id","pays"]:
        clients[c] = clients[c].astype(str).str.strip().replace({"nan": ""})

    need = clients["pays"].eq("") | clients["pays"].isna()
    if need.any():
        clients.loc[need, "pays"] = clients.loc[need, "telephone"].apply(_phone_country)

    cols_order = ["nom_client","pays","telephone","email","plateforme","res_id"]
    clients = clients[cols_order]
    clients = clients.loc[clients["nom_client"] != ""].drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)


def vue_id(df: pd.DataFrame, palette: dict):
    """Identifiants des réservations (res_id) avec coordonnées."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🆔 Identifiants des réservations — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    tbl = df[["res_id","nom_client","telephone","email","plateforme","pays"]].copy()
    for c in ["nom_client","telephone","email","plateforme","res_id","pays"]:
        tbl[c] = tbl[c].astype(str).str.strip().replace({"nan": ""})

    need = tbl["pays"].eq("") | tbl["pays"].isna()
    if need.any():
        tbl.loc[need, "pays"] = tbl.loc[need, "telephone"].apply(_phone_country)

    tbl = tbl.dropna(subset=["res_id"])
    tbl = tbl[tbl["res_id"] != ""].drop_duplicates()
    st.dataframe(tbl, use_container_width=True)

# ============================== PART 5/5 — SMS, PARAMÈTRES, INDICATIFS PAYS, MAIN ==============================

def vue_sms(df: pd.DataFrame, palette: dict):
    """Page SMS — messages préformatés avant arrivée et après départ."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation disponible.")
        return

    st.subheader("📩 Messages avant l'arrivée")
    for _, r in df.iterrows():
        arr_txt = str(r.get("date_arrivee",""))
        dep_txt = str(r.get("date_depart",""))
        nuitees = str(r.get("nuitees",""))
        msg = f"""
APPARTEMENT {apt_name}
Plateforme : {r.get('plateforme','')}
Arrivée : {arr_txt}   Départ : {dep_txt}   Nuitées : {nuitees}

Bonjour {r.get('nom_client','')}

Bienvenue chez nous !

Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre réception, nous vous demandons de bien vouloir remplir la fiche que vous trouverez en cliquant sur le lien suivant : 
https://urlr.me/kZuH94

Un parking est à votre disposition sur place.

Le check-in se fait à partir de 14:00 h et le check-out avant 11:00 h.

Vous trouverez des consignes à bagages dans chaque quartier, à Nice.

Nous vous souhaitons un excellent voyage et nous nous réjouissons de vous rencontrer très bientôt.

Annick & Charley

******

Welcome to our establishment!

We are delighted to welcome you soon to Nice. In order to organize your reception as efficiently as possible, we kindly ask you to fill out the form that you will find by clicking on the following link:
https://urlr.me/kZuH94

Parking is available on site.

Check-in is from 2:00 p.m. and check-out is before 11:00 a.m.

You will find luggage storage facilities in every district of Nice.

We wish you a pleasant journey and look forward to meeting you very soon.

Annick & Charley
"""
        st.text_area(f"Avant arrivée — {r.get('nom_client','')}", msg.strip(), height=380)

    st.subheader("📩 Messages après le départ")
    for _, r in df.iterrows():
        msg = f"""
Bonjour {r.get('nom_client','')},

Un grand merci d'avoir choisi notre appartement pour votre séjour.
Nous espérons que vous avez passé un moment agréable.
Si vous souhaitez revenir explorer encore un peu la ville, notre porte vous sera toujours grande ouverte.

Au plaisir de vous accueillir à nouveau.

Annick & Charley

******

Hello {r.get('nom_client','')},

Thank you very much for choosing our apartment for your stay.
We hope you had a great time — our door is always open if you want to come back.

Annick & Charley
"""
        st.text_area(f"Après départ — {r.get('nom_client','')}", msg.strip(), height=300)


def vue_settings(df: pd.DataFrame, palette: dict):
    """Page Paramètres — sauvegarde/restauration/export et cache."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header("⚙️ Paramètres")
    st.subheader(apt_name)
    print_buttons()

    # Export CSV
    try:
        out = ensure_schema(df).copy()
        out["pays"] = out["telephone"].apply(_phone_country)
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        csv_bytes = out.to_csv(sep=";", index=False).encode("utf-8")
    except Exception:
        csv_bytes = b""
    st.download_button(
        "⬇️ Exporter réservations (CSV)", data=csv_bytes,
        file_name="reservations.csv", mime="text/csv"
    )

    # Export XLSX
    try:
        out_xlsx = ensure_schema(df).copy()
        out_xlsx["pays"] = out_xlsx["telephone"].apply(_phone_country)
        for col in ["date_arrivee","date_depart"]:
            out_xlsx[col] = pd.to_datetime(out_xlsx[col], errors="coerce").dt.strftime("%d/%m/%Y")
        xlsx_bytes, _ = _df_to_xlsx_bytes(out_xlsx, "Reservations")
    except Exception:
        xlsx_bytes = None
    st.download_button(
        "⬇️ Exporter réservations (XLSX)", data=xlsx_bytes or b"",
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(xlsx_bytes is None)
    )

    st.markdown("---")
    st.subheader("♻️ Restauration")
    up = st.file_uploader("Importer un fichier (CSV/XLSX)", type=["csv","xlsx"])
    if up is not None:
        try:
            if up.name.lower().endswith(".xlsx"):
                tmp = pd.read_excel(up, dtype=str)
            else:
                tmp = pd.read_csv(up, dtype=str, sep=None, engine="python")
            prev = ensure_schema(tmp)
            st.dataframe(prev.head(), use_container_width=True)
            if st.button("✅ Confirmer la restauration"):
                prev.to_csv(st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS),
                            sep=";", index=False, encoding="utf-8")
                st.success("Fichier restauré — rechargement…")
                st.cache_data.clear()
                st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    st.markdown("---")
    if st.button("🧹 Vider le cache et recharger"):
        st.cache_data.clear()
        st.rerun()


def vue_indicatifs(df: pd.DataFrame, palette: dict):
    """Page pour visualiser et recharger les indicatifs pays (avec drapeaux)."""
    st.header("🌍 Indicateurs pays")
    st.caption("Table des indicatifs téléphoniques utilisée pour compléter la colonne Pays.")

    data = load_indicatifs()
    st.dataframe(data, use_container_width=True)

    if st.button("🔄 Recharger depuis le disque"):
        st.cache_data.clear()
        st.rerun()


# ------------------------------- MAIN ---------------------------------

def main():
    # Reset cache via URL ?clear=1
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1","true","yes","True"):
        st.cache_data.clear()

    _select_apartment_sidebar()

    # Thème
    mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

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
    page_func = pages.get(choice)
    if page_func:
        page_func(df, palette)


if __name__ == "__main__":
    main()