# ============================== PART 1/5 — IMPORTS, CONFIG, STYLES, HELPERS ==============================
import os, io, re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange
from urllib.parse import quote

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
from html import escape  # pour échapper les titres dans le calendrier

# ------------------------------ CONFIG APP ------------------------------
st.set_page_config(
    page_title="✨ Villa Tobias — Gestion des Réservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------ CONSTANTES FICHIERS ------------------------------
# Ces chemins sont remplacés dynamiquement selon l'appartement sélectionné
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"
APARTMENTS_CSV   = "apartments.csv"

# Table d'indicatifs personnalisable (avec drapeaux)
INDICATIFS_CSV   = "countries_with_flags.csv"

# Palette par défaut (si plateformes_X.csv absent)
DEFAULT_PALETTE = {
    "Booking": "#1b9e77",
    "Airbnb":  "#d95f02",
    "Abritel": "#7570b3",
    "Direct":  "#e7298a",
}

# Google Form & Sheet (adapter au besoin)
FORM_SHORT_URL = "https://urlr.me/kZuH94"  # lien court public
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# ------------------------------ STYLE GLOBAL + IMPRESSION ------------------------------
def apply_style(light: bool):
    """Applique un thème light/dark + styles calendrier + styles impression A4 paysage."""
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
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
            background:{"rgba(255,255,255,.65)" if light else "rgba(255,255,255,.06)"};
            border:1px solid {border}; border-radius:12px; padding:12px; margin:10px 0;
          }}
          .chip {{
            display:inline-block; padding:6px 10px; border-radius:12px; margin:4px 6px;
            font-size:.86rem; background:{"#eee" if light else "#2a2f3a"}; color:{"#222" if light else "#eee"};
          }}
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; }}
          .cal-cell {{
            border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px;
            position:relative; overflow:hidden; background:{"#fff" if light else "#0b0d12"};
          }}
          .cal-cell.outside {{ opacity:.45; }}
          .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
          .resa-pill {{
            padding:4px 6px; border-radius:6px; font-size:.84rem; margin-top:22px; color:#fff;
            white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
          }}
          .cal-header {{
            display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; font-weight:700; opacity:.8; margin:6px 0 8px;
          }}

          /* Impression A4 paysage + masquage des contrôles techniques */
          @media print {{
            @page {{
              size: A4 landscape;
              margin: 12mm;
            }}
            .print-hide, [data-testid="stSidebar"], header, footer {{
              display: none !important;
              height: 0 !important; width: 0 !important; overflow: hidden !important;
            }}
            .print-header {{
              display: block !important;
              margin-bottom: 8px; font-size: 18px; font-weight: 700;
            }}
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

def print_buttons(location: str = "main"):
    """Bouton Imprimer qui déclenche window.print() côté navigateur."""
    target = st.sidebar if location == "sidebar" else st
    target.button("🖨️ Imprimer", key=f"print_btn_{location}")
    st.markdown(
        """
        <script>
        // attache le click au bon bouton (recherche par label)
        const findPrintBtn = () => {
          const labels = Array.from(parent.document.querySelectorAll('button span, button p'));
          const lab = labels.find(n => n.textContent && n.textContent.trim() === "🖨️ Imprimer");
          if (lab && lab.parentElement) {
            lab.parentElement.onclick = () => window.print();
          }
        };
        setTimeout(findPrintBtn, 300);
        </script>
        """,
        unsafe_allow_html=True
    )

# ------------------------------ COLONNES DE BASE ------------------------------
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","pays",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid"
]

# ------------------------------ HELPERS GÉNÉRAUX ------------------------------
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
    if isinstance(x, pd.Series): return x
    if isinstance(x, (list, tuple, np.ndarray)):
        s = pd.Series(list(x))
        if index is not None and len(index) == len(s): s.index = index
        return s
    if index is None: return pd.Series([x])
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
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

# Fallback embarqué (utilisé si le CSV indicatifs ne contient pas le préfixe)
PHONE_PREFIX_COUNTRY = {
    "33":"France","34":"Espagne","49":"Allemagne","44":"Royaume-Uni","39":"Italie",
    "41":"Suisse","32":"Belgique","352":"Luxembourg","351":"Portugal",
    "1":"États-Unis/Canada","61":"Australie","64":"Nouvelle-Zélande",
    "420":"Tchéquie","421":"Slovaquie","36":"Hongrie","40":"Roumanie",
    "30":"Grèce","31":"Pays-Bas","353":"Irlande","354":"Islande","358":"Finlande",
    "46":"Suède","47":"Norvège","48":"Pologne","43":"Autriche","45":"Danemark",
    "90":"Turquie","212":"Maroc","216":"Tunisie","971":"Émirats Arabes Unis"
}

# ------------------------------ INDICATIFS PAYS (CSV + drapeaux) ------------------------------
def create_indicatifs_csv():
    """Crée un CSV d'indicatifs s'il n'existe pas (colonnes: flag,pays,prefix,code)."""
    if os.path.exists(INDICATIFS_CSV):
        return
    seed = pd.DataFrame([
        {"flag":"🇫🇷","pays":"France","prefix":"+33","code":"FR"},
        {"flag":"🇪🇸","pays":"Espagne","prefix":"+34","code":"ES"},
        {"flag":"🇩🇪","pays":"Allemagne","prefix":"+49","code":"DE"},
        {"flag":"🇬🇧","pays":"Royaume-Uni","prefix":"+44","code":"GB"},
        {"flag":"🇮🇹","pays":"Italie","prefix":"+39","code":"IT"},
        {"flag":"🇧🇪","pays":"Belgique","prefix":"+32","code":"BE"},
    ], dtype=str)
    seed.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8", lineterminator="\n")

@st.cache_data(show_spinner=False)
def load_indicatifs() -> pd.DataFrame:
    """Charge countries_with_flags.csv ; garantit les colonnes et un champ 'prefix_clean'."""
    if not os.path.exists(INDICATIFS_CSV):
        create_indicatifs_csv()
    try:
        df = pd.read_csv(INDICATIFS_CSV, dtype=str).fillna("")
    except Exception:
        df = pd.DataFrame(columns=["flag","pays","prefix","code"])
    for c in ["flag","pays","prefix","code"]:
        if c not in df.columns: df[c] = ""
        df[c] = df[c].astype(str).fillna("").str.strip()
    df["prefix_clean"] = df["prefix"].str.replace("+","", regex=False)
    return df

def save_indicatifs(df: pd.DataFrame) -> bool:
    """Sauvegarde le CSV indicatifs, nettoyé et encodé UTF-8 (garde les emojis)."""
    try:
        out = df.copy()
        for c in ["flag","pays","prefix","code"]:
            if c not in out.columns: out[c] = ""
            out[c] = out[c].astype(str).fillna("").str.strip()
        out = out[["flag","pays","prefix","code"]]
        out.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur enregistrement indicatifs : {e}")
        return False

def _phone_country(phone: str) -> str:
    """Détermine le pays à partir de l'indicatif. Priorité à la table CSV, sinon fallback interne."""
    p = str(phone or "").strip()
    if not p:
        return ""
    digits = re.sub(r"\D","", p)

    # 1) table personnalisée (CSV)
    try:
        ind = load_indicatifs()
        if not ind.empty:
            for pref in sorted(ind["prefix_clean"].dropna().unique(), key=lambda x: -len(str(x))):
                if pref and digits.startswith(str(pref)):
                    row = ind.loc[ind["prefix_clean"] == pref].iloc[0]
                    return row.get("pays") or "Inconnu"
    except Exception:
        pass

    # 2) fallback embarqué
    if p.startswith("+"):  p1 = p[1:]
    elif p.startswith("00"): p1 = p[2:]
    elif p.startswith("0"):  return "France"
    else: p1 = p
    for k in sorted(PHONE_PREFIX_COUNTRY.keys(), key=lambda x: -len(x)):
        if p1.startswith(k):
            return PHONE_PREFIX_COUNTRY[k]
    return "Inconnu"

# ============================== PART 2/5 — NORMALISATION, SAUVEGARDE, CHARGEMENT, APPARTEMENTS ==============================

# ---------- Normalisation du DataFrame des réservations ----------
def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Force les colonnes attendues, types (dates/nombres/bool), calcule prix_net/base/charges/%."""
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

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = pd.Series([None]*len(df), index=df.index)

    # Uniformise types de base
    for c in df.columns:
        df[c] = _as_series(df[c], index=df.index)

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b])

    # Numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base","prix_net"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Nuitées si possible
    mask_ok = pd.notna(df["date_arrivee"]) & pd.notna(df["date_depart"])
    if mask_ok.any():
        da = pd.to_datetime(df.loc[mask_ok,"date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok,"date_depart"])
        df.loc[mask_ok,"nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)

    # Calculs prix_net / charges / base / %
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

    # Identifiants manquants
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res,"res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # Chaînes propres
    for c in ["nom_client","plateforme","telephone","email","pays"]:
        df[c] = df[c].astype(str).replace({"nan":"","None":""}).str.strip()

    # Pays auto si vide (via indicatifs)
    need = (df["pays"]=="") | df["pays"].isna()
    if need.any():
        df.loc[need,"pays"] = df.loc[need,"telephone"].apply(_phone_country)

    return df[BASE_COLS]

# ---------- Sauvegarde ----------
def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    """Sauvegarde le CSV des réservations du logement actif + clear cache."""
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        target = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
        out.to_csv(target, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ---------- Chargement (réservations + palette) ----------
@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations: str, csv_plateformes: str):
    """Charge (et crée si manquant) les CSV du logement actif, retourne (df, palette)."""
    # crée les fichiers s'ils n'existent pas (squelette minimal)
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
                palette = {str(r["plateforme"]): str(r["couleur"]) for _, r in pal_df.dropna(subset=["plateforme"]).iterrows()}
        except Exception as e:
            st.warning(f"Erreur de lecture palette : {e}")
    return df, palette

# ---------- Apartments (sélecteur sans mot de passe) ----------
def _read_apartments_csv() -> pd.DataFrame:
    """Lit apartments.csv et renvoie colonnes normalisées [slug, name]."""
    try:
        if not os.path.exists(APARTMENTS_CSV):
            return pd.DataFrame(columns=["slug","name"])
        raw = _load_file_bytes(APARTMENTS_CSV)
        df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame(columns=["slug","name"])
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "slug" not in df.columns: df["slug"] = ""
        if "name" not in df.columns: df["name"] = ""
        df["slug"] = (df["slug"].astype(str).str.replace("\ufeff","",regex=False)
                      .str.strip().str.replace(" ","-",regex=False).str.replace("_","-",regex=False).str.lower())
        df["name"] = df["name"].astype(str).str.replace("\ufeff","",regex=False).str.strip()
        df = df[(df["slug"]!="") & (df["name"]!="")].drop_duplicates(subset=["slug"], keep="first")
        return df[["slug","name"]]
    except Exception:
        return pd.DataFrame(columns=["slug","name"])

def _current_apartment() -> dict | None:
    """Retourne {{slug, name}} depuis la session, sinon None."""
    slug = st.session_state.get("apt_slug","")
    name = st.session_state.get("apt_name","")
    if slug and name:
        return {"slug": slug, "name": name}
    return None

def _select_apartment_sidebar() -> bool:
    """Sélecteur dans la sidebar + met à jour CSV_RESERVATIONS/CSV_PLATEFORMES en session. Retourne True si changement."""
    st.sidebar.markdown("### Appartement")
    df_apts = _read_apartments_csv()
    if df_apts.empty:
        st.sidebar.warning("Aucun appartement trouvé dans apartments.csv")
        # Propose un contenu par défaut à coller dans Paramètres si besoin
        st.sidebar.caption("Exemple d'apartments.csv :\nslug,name\nvilla-tobias,Villa Tobias\nle-turenne,Le Turenne")
        return False

    options = df_apts["slug"].tolist()
    labels = {r["slug"]: r["name"] for _, r in df_apts.iterrows()}
    cur_slug = st.session_state.get("apt_slug", options[0] if options else "")
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

    changed = (slug != st.session_state.get("apt_slug","") or name != st.session_state.get("apt_name",""))

    st.session_state["apt_slug"] = slug
    st.session_state["apt_name"] = name
    st.session_state["CSV_RESERVATIONS"] = f"reservations_{slug}.csv"
    st.session_state["CSV_PLATEFORMES"]  = f"plateformes_{slug}.csv"

    global CSV_RESERVATIONS, CSV_PLATEFORMES
    CSV_RESERVATIONS = st.session_state["CSV_RESERVATIONS"]
    CSV_PLATEFORMES  = st.session_state["CSV_PLATEFORMES"]

    st.sidebar.success(f"Connecté : {name}")
    try:
        print_buttons(location="sidebar")
    except Exception:
        pass

    return changed

def _load_data_for_active_apartment():
    """Charge les données du logement actif. Tolérant si la session est vide."""
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_pal = st.session_state.get("CSV_PLATEFORMES",  CSV_PLATEFORMES)
    try:
        return charger_donnees(csv_res, csv_pal)
    except TypeError:
        return charger_donnees(CSV_RESERVATIONS, CSV_PLATEFORMES)
    except Exception:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE.copy()

# ============================== PART 3/5 — VUES : ACCUEIL, RÉSERVATIONS, AJOUTER, MODIFIER, PLATEFORMES ==============================

def vue_accueil(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    today = date.today()
    tomorrow = today + timedelta(days=1)
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    arr = dfv[dfv["date_arrivee"] == today][["nom_client","telephone","plateforme","pays"]]
    dep = dfv[dfv["date_depart"]  == today][["nom_client","telephone","plateforme","pays"]]
    arr_plus1 = dfv[dfv["date_arrivee"] == tomorrow][["nom_client","telephone","plateforme","pays"]]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame({"info":["Aucune arrivée."]}), use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame({"info":["Aucun départ."]}), use_container_width=True)
    with c3:
        st.subheader("🟠 Arrivées J+1 (demain)")
        st.dataframe(arr_plus1 if not arr_plus1.empty else pd.DataFrame({"info":["Aucune arrivée demain."]}), use_container_width=True)


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
    months_avail = list(range(1,13))
    plats_avail  = sorted(dfa["plateforme"].astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist())

    c1,c2,c3,c4 = st.columns(4)
    year  = c1.selectbox("Année", ["Toutes"]+years_avail, index=0)
    month = c2.selectbox("Mois",  ["Tous"]+months_avail, index=0)
    plat  = c3.selectbox("Plateforme", ["Toutes"]+plats_avail, index=0)
    payf  = c4.selectbox("Paiement", ["Tous","Payé uniquement","Non payé uniquement"], index=0)

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
    net  = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    base = float(pd.to_numeric(data["base"],     errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(data["nuitees"],   errors="coerce").fillna(0).sum())
    adr  = (net/nuits) if nuits>0 else 0.0
    charges = float(pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum())

    st.markdown(
        f"""
        <div class='glass print-hide'>
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
    st.dataframe(
        data,
        use_container_width=True,
        column_config={
            # Masque les colonnes techniques pendant l'affichage standard
            "res_id": None,
            "ical_uid": None,
            "sms_envoye": None,
            "post_depart_envoye": None,
            "%": st.column_config.NumberColumn("Charges (%)", format="%.1f"),
        }
    )


def vue_ajouter(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter une réservation — {apt_name}")
    print_buttons()

    with st.form("form_add", clear_on_submit=True):
        c1,c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel = st.text_input("Téléphone")
            arr = st.date_input("Arrivée", date.today())
            dep = st.date_input("Départ",  date.today()+timedelta(days=1))
        with c2:
            plat = st.selectbox("Plateforme", list(palette.keys()))
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes  = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye   = st.checkbox("Payé", value=False)

        if st.form_submit_button("✅ Ajouter"):
            if not nom or dep <= arr:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nuitees = (dep-arr).days
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
        c1,c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get("nom_client","") or "")
            email = st.text_input("Email", value=row.get("email","") or "")
            tel = st.text_input("Téléphone", value=row.get("telephone","") or "")
            arrivee = st.date_input("Arrivée", value=row.get("date_arrivee"))
            depart  = st.date_input("Départ",  value=row.get("date_depart"))
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

        b1,b2 = st.columns([0.7,0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            updates = {
                "nom_client": nom, "email": email, "telephone": tel, "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye, "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes
            }
            for k,v in updates.items():
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
    """Edition de la palette de couleurs des plateformes."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes & couleurs — {apt_name}")
    print_buttons()

    # Récupère toutes les plateformes observées + palette existante
    plats_df = sorted(df.get("plateforme", pd.Series([], dtype=str))
                        .astype(str).str.strip().replace({"nan":""}).dropna().unique().tolist())
    all_plats = sorted(set(list(palette.keys()) + plats_df))
    base = pd.DataFrame({"plateforme": all_plats, "couleur": [palette.get(p, "#666666") for p in all_plats]})

    # Détection de st.column_config.ColorColumn (versions récentes de Streamlit)
    HAS_COLORCOL = hasattr(getattr(st, "column_config", object), "ColorColumn")
    if HAS_COLORCOL:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorColumn("Couleur (hex)")
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

    # Aperçu des puces colorées (si pas de ColorColumn)
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

    c1,c2,c3 = st.columns([0.5,0.3,0.2])
    if c1.button("💾 Enregistrer la palette", key="save_palette_btn"):
        try:
            to_save = edited.copy()
            to_save["plateforme"] = to_save["plateforme"].astype(str).str.strip()
            to_save["couleur"]    = to_save["couleur"].astype(str).str.strip()
            to_save = to_save[to_save["plateforme"] != ""].drop_duplicates(subset=["plateforme"])
            if not HAS_COLORCOL:
                ok = to_save["couleur"].str.match(r"^#([0-9A-Fa-f]{6})$")
                to_save.loc[~ok, "couleur"] = "#666666"
            target_pal = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
            to_save.to_csv(target_pal, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("↩️ Palette par défaut", key="restore_palette_btn"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(
                st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES),
                sep=";", index=False, encoding="utf-8", lineterminator="\n"
            )
            st.success("Palette restaurée.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c3.button("🔄 Recharger", key="reload_palette_btn"):
        st.cache_data.clear()
        st.rerun()
# ============================== PART 4/5 — VUES : CALENDRIER, RAPPORT, EXPORT ICS, GOOGLE SHEET, CLIENTS, ID ==============================
from html import escape  # utilisé pour sécuriser les attributs HTML (title)

def vue_calendrier(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier (grille mensuelle) — {apt_name}")
    print_buttons()

    dfv = df.dropna(subset=["date_arrivee","date_depart"]).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])
    years = sorted(pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois",  options=list(range(1,13)), index=today.month-1)

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
        return

    plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
    fplat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
    if fplat != "Toutes":
        rows = rows[rows["plateforme"] == fplat]

    brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(rows["prix_net"],  errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(rows["nuitees"],   errors="coerce").fillna(0).sum())

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
    import altair as alt

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

    years_avail = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1,13))
    plats_avail  = sorted(dfa["plateforme"].astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist())

    dfa["_pays"] = dfa["pays"].replace("", np.nan)
    dfa["_pays"] = dfa["_pays"].fillna(dfa["telephone"].apply(_phone_country)).replace("", "Inconnu")
    pays_avail   = sorted(dfa["_pays"].unique().tolist())
    if "France" in pays_avail:
        pays_avail.remove("France")
        pays_avail = ["France"] + pays_avail

    c1,c2,c3,c4,c5 = st.columns([1,1,1,1.2,1.2])
    year  = c1.selectbox("Année",     ["Toutes"]+years_avail, index=0)
    month = c2.selectbox("Mois",      ["Tous"]+months_avail, index=0)
    plat  = c3.selectbox("Plateforme",["Toutes"]+plats_avail, index=0)
    payf  = c4.selectbox("Pays",      ["Tous"]+pays_avail, index=0)
    metric= c5.selectbox("Métrique",  ["prix_brut","prix_net","base","charges","menage","taxes_sejour","nuitees"], index=1)

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

    # ---- Occupation par mois ----
    st.markdown("---")
    st.subheader("📅 Taux d'occupation")
    data["mois"] = data["date_arrivee_dt"].dt.to_period("M").astype(str)
    data["nuitees"] = (data["date_depart_dt"] - data["date_arrivee_dt"]).dt.days
    occ_mois = data.groupby(["mois","plateforme"], as_index=False)["nuitees"].sum().rename(columns={"nuitees":"nuitees_occupees"})
    def _jours_mois(periode_str):
        an, mo = map(int, periode_str.split("-"))
        return monthrange(an, mo)[1]
    occ_mois["jours_dans_mois"] = occ_mois["mois"].apply(_jours_mois)
    occ_mois["taux_occupation"] = (occ_mois["nuitees_occupees"]/occ_mois["jours_dans_mois"])*100

    col_plat, col_export = st.columns([1,1])
    plat_occ = col_plat.selectbox("Filtrer par plateforme (occupation)", ["Toutes"]+plats_avail, index=0, key="occ_plat")
    occ_filtered = occ_mois if plat_occ == "Toutes" else occ_mois[occ_mois["plateforme"] == plat_occ]
    filtered_nuitees = pd.to_numeric(occ_filtered["nuitees_occupees"], errors="coerce").fillna(0).sum()
    filtered_jours   = pd.to_numeric(occ_filtered["jours_dans_mois"], errors="coerce").fillna(0).sum()
    taux_global_filtered = (filtered_nuitees/filtered_jours)*100 if filtered_jours>0 else 0

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

    occ_export = occ_filtered[["mois","plateforme","nuitees_occupees","jours_dans_mois","taux_occupation"]].copy().sort_values(["mois","plateforme"], ascending=[False,True])
    col_export.download_button(
        "⬇️ Exporter occupation (CSV)",
        data=occ_export.to_csv(index=False).encode("utf-8"),
        file_name="taux_occupation.csv",
        mime="text/csv"
    )
    xlsx_occ, _ = _df_to_xlsx_bytes(occ_export, "Taux d'occupation")
    if xlsx_occ:
        col_export.download_button(
            "⬇️ Exporter occupation (Excel)",
            data=xlsx_occ,
            file_name="taux_occupation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    try:
        chart_occ = alt.Chart(occ_filtered).mark_line(point=True).encode(
            x=alt.X("mois:N", sort=None, title="Mois"),
            y=alt.Y("taux_occupation:Q", title="Taux d'occupation (%)", scale=alt.Scale(domain=[0,100])),
            color=alt.Color("plateforme:N", title="Plateforme"),
            tooltip=["mois","plateforme", alt.Tooltip("taux_occupation:Q", format=".1f")]
        ).properties(height=420)
        st.altair_chart(chart_occ, use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique du taux d'occupation indisponible : {e}")

    # ---- Métriques financières ----
    st.markdown("---")
    st.subheader("💰 Métriques financières")
    agg_mois_plat = data.groupby(["mois","plateforme"], as_index=False)[metric].sum().sort_values(["mois","plateforme"])
    try:
        chart = alt.Chart(agg_mois_plat).mark_bar().encode(
            x=alt.X("mois:N", sort=None, title="Mois"),
            y=alt.Y(f"{metric}:Q", title=metric.replace("_"," ").title()),
            color=alt.Color("plateforme:N", title="Plateforme"),
            tooltip=["mois","plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
        ).properties(height=420)
        st.altair_chart(chart, use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique indisponible : {e}")

    with st.expander("Détail par mois et par plateforme", expanded=False):
        st.dataframe(agg_mois_plat, use_container_width=True)

    # ---- Analyse par pays ----
    st.markdown("---")
    st.subheader("🌍 Analyse par pays")
    data_p = data.copy()
    data_p["nuitees"] = (data_p["date_depart_dt"] - data_p["date_arrivee_dt"]).dt.days
    agg_pays = data_p.groupby("pays", as_index=False).agg(
        reservations=("nom_client","count"),
        nuitees=("nuitees","sum"),
        prix_brut=("prix_brut","sum"),
        prix_net=("prix_net","sum"),
        menage=("menage","sum"),
        taxes_sejour=("taxes_sejour","sum"),
        charges=("charges","sum"),
        base=("base","sum"),
    )
    total_net = float(pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0).sum())
    agg_pays["part_revenu_%"] = np.where(
        total_net>0,
        (pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0)/total_net)*100,
        0.0
    )
    agg_pays["ADR_net"] = np.where(
        pd.to_numeric(agg_pays["nuitees"], errors="coerce").fillna(0)>0,
        pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0)/pd.to_numeric(agg_pays["nuitees"], errors="coerce").fillna(0),
        0.0
    )
    agg_pays = agg_pays.sort_values(["prix_net","reservations"], ascending=[False,False])

    disp = agg_pays.copy()
    for c in ["reservations","nuitees","prix_brut","prix_net","menage","taxes_sejour","charges","base","ADR_net","part_revenu_%"]:
        disp[c] = pd.to_numeric(disp[c], errors="coerce")
    disp["reservations"] = disp["reservations"].fillna(0).astype("int64")
    disp["pays"] = disp["pays"].astype(str).replace({"nan":"Inconnu","":"Inconnu"})
    disp["prix_brut"] = disp["prix_brut"].round(2)
    disp["prix_net"] = disp["prix_net"].round(2)
    disp["ADR_net"] = disp["ADR_net"].round(2)
    disp["part_revenu_%"] = disp["part_revenu_%"].round(1)
    order_cols = ["pays","reservations","nuitees","prix_brut","prix_net","charges","menage","taxes_sejour","base","ADR_net","part_revenu_%"]
    disp = disp[[c for c in order_cols if c in disp.columns]]
    st.dataframe(disp, use_container_width=True)


def vue_export_ics(df: pd.DataFrame, palette: dict):
    """Export iCalendar (.ics) par année, avec UID stable pour éviter les doublons côté agenda."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📆 Export ICS — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    years = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years if years else [date.today().year], index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfa[dfa["date_arrivee_dt"].dt.year == int(year)].copy()
    if plat != "Tous":
        data = data[data["plateforme"] == plat]
    if data.empty:
        st.warning("Rien à exporter.")
        return

    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
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

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        dt_a = pd.to_datetime(r["date_arrivee"], errors="coerce")
        dt_d = pd.to_datetime(r["date_depart"],  errors="coerce")
        if pd.isna(dt_a) or pd.isna(dt_d):
            continue
        summary = f"{apt_name} — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"):
            summary += f" ({r['plateforme']})"
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
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Fiche d'arrivée / Google Sheet — {apt_name}")
    print_buttons()
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")
    st.markdown(f'<iframe src="{GOOGLE_FORM_VIEW}" width="100%" height="900" frameborder="0"></iframe>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("Feuille Google intégrée")
    st.markdown(f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>', unsafe_allow_html=True)
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
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Liste des clients — {apt_name}")
    print_buttons()
    if df.empty:
        st.info("Aucun client.")
        return

    clients = df[['nom_client', 'telephone', 'email', 'plateforme', 'res_id', 'pays']].copy()
    for c in ["nom_client","telephone","email","plateforme","res_id","pays"]:
        clients[c] = clients[c].astype(str).str.strip().replace({"nan": ""})

    need = clients["pays"].eq("") | clients["pays"].isna()
    if need.any():
        clients.loc[need, "pays"] = clients.loc[need, "telephone"].apply(_phone_country)

    cols_order = ["nom_client", "pays", "telephone", "email", "plateforme", "res_id"]
    clients = clients[cols_order]
    clients = clients.loc[clients["nom_client"] != ""].drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)


def vue_id(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🆔 Identifiants des réservations — {apt_name}")
    print_buttons()
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return
    tbl = df[["res_id", "nom_client", "telephone", "email", "plateforme", "pays"]].copy()
    for c in ["nom_client","telephone","email","plateforme","res_id","pays"]:
        tbl[c] = tbl[c].astype(str).str.strip().replace({"nan": ""})
    need = tbl["pays"].eq("") | tbl["pays"].isna()
    if need.any():
        tbl.loc[need, "pays"] = tbl.loc[need, "telephone"].apply(_phone_country)
    tbl = tbl.dropna(subset=["res_id"])
    tbl = tbl[tbl["res_id"] != ""].drop_duplicates()
    st.dataframe(tbl, use_container_width=True)

# ============================== PART 5/5 — SMS, PARAMETRES, MAIN ==============================

def vue_sms(df: pd.DataFrame, palette: dict):
    """Page SMS — messages préformatés avant arrivée et après départ (copier/coller + liens SMS/WhatsApp)."""
    from urllib.parse import quote

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation disponible.")
        return

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    # -------- Pré-arrivée (J+1) --------
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = dfv.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (~_to_bool_series(pre["sms_envoye"]))]

    if pre.empty:
        st.info("Aucun client à contacter pour la date sélectionnée.")
    else:
        pre = pre.sort_values("date_arrivee").reset_index()  # garde l'index original dans la colonne 'index'
        options = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=options, index=None)
        if pick:
            sel_idx = int(pick.split(":")[0])
            r = pre.loc[sel_idx]
            link_form = FORM_SHORT_URL
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
                "nous vous demandons de bien vouloir remplir la fiche que vous trouverez en cliquant sur le lien suivant :\n"
                f"{link_form}\n\n"
                "Un parking est à votre disposition sur place.\n\n"
                "Le check-in se fait à partir de 14:00 et le check-out avant 11:00. Nous serons sur place lors de "
                "votre arrivée pour vous remettre les clés.\n\n"
                "Vous trouverez des consignes à bagages dans chaque quartier, à Nice.\n\n"
                "Nous vous souhaitons un excellent voyage et nous nous réjouissons de vous rencontrer très bientôt.\n\n"
                "Annick & Charley\n\n"
                "******\n\n"
                "Welcome to our establishment!\n\n"
                "We are delighted to welcome you soon to Nice. In order to organize your reception as efficiently as possible, "
                "we kindly ask you to fill out this form:\n"
                f"{link_form}\n\n"
                "Parking is available on site.\n\n"
                "Check-in from 2:00 p.m. — check-out before 11:00 a.m. We will be there when you arrive to give you the keys.\n\n"
                "You will find luggage storage facilities in every district of Nice.\n\n"
                "We wish you a pleasant journey and look forward to meeting you very soon.\n\n"
                "Annick & Charley"
            )

            st.text_area("📋 Copier le message", value=msg, height=360)
            # Liens rapides (sms / whatsapp)
            e164 = _format_phone_e164(r.get("telephone",""))
            only_digits = "".join(ch for ch in e164 if ch.isdigit())
            enc = quote(msg)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits}?text={enc}")

            # Marquer envoyé
            if st.button("✅ Marquer 'SMS envoyé' pour ce client"):
                try:
                    df.loc[r["index"], "sms_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    # -------- Post-départ (départs du jour) --------
    st.markdown("---")
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = dfv.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post = post[(post["date_depart"] == target_depart) & (~_to_bool_series(post["post_depart_envoye"]))]

    if post.empty:
        st.info("Aucun message post-départ à envoyer aujourd’hui.")
    else:
        post = post.sort_values("date_depart").reset_index()
        options2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=options2, index=None)
        if pick2:
            sel_idx2 = int(pick2.split(":")[0])
            r2 = post.loc[sel_idx2]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Un grand merci d'avoir choisi notre appartement pour votre séjour.\n"
                "Nous espérons que vous avez passé un moment agréable.\n"
                "Si vous souhaitez revenir explorer encore un peu la ville, notre porte vous sera toujours grande ouverte.\n\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n"
                "We hope you had a great time — our door is always open if you want to come back.\n\n"
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
                try:
                    df.loc[r2["index"], "post_depart_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")


# ============================== PARAMETRES ==============================

def vue_settings(df: pd.DataFrame, palette: dict):
    """Sauvegarde / restauration des données + maintenance apartments.csv + cache."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header("## ⚙️ Paramètres")
    st.subheader(apt_name)
    print_buttons()
    st.caption("Sauvegarde, restauration, cache et outil secours pour apartments.csv.")

    # Sauvegarde (exports)
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

    # Restauration (CSV/XLSX)
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

    # Vider le cache
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
    txt = st.text_area(
        "Contenu apartments.csv",
        value=default_csv,
        height=140,
        key="force_apts_txt_settings",
    )
    if st.button("🧰 Écraser apartments.csv", key="force_apts_btn_settings"):
        try:
            with open(APARTMENTS_CSV, "w", encoding="utf-8", newline="") as f:
                f.write(txt.strip() + "\n")
            st.cache_data.clear()
            st.success("apartments.csv écrasé ✅ — rechargement…")
            st.rerun()
        except Exception as e:
            st.error(f"Impossible d'écrire apartments.csv : {e}")


# ------------------------------- MAIN -------------------------------

def main():
    # Reset cache via URL ?clear=1
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1", "true", "True", "yes"):
        try:
            st.cache_data.clear()
        except Exception:
            pass

    # Sélection appartement (met à jour CSV_RESERVATIONS / CSV_PLATEFORMES)
    changed = _select_apartment_sidebar()
    if changed:
        try:
            st.cache_data.clear()
        except Exception:
            pass

    # Thème
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    # En-tête
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    # Chargement des données spécifiques à l'appartement
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
        "🌍 Indicateurs pays": vue_indicatifs,  # page d’édition/consultation des indicatifs
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