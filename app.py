# ============================== PART 1/5 - IMPORTS, CONFIG, STYLES, HELPERS ==============================

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

# --------------- CONFIG APP ---------------
st.set_page_config(
    page_title="Villa Tobias — Gestion des Reservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# --------------- CONSTANTES ---------------
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES = "plateformes.csv"
APARTMENTS_CSV = "apartments.csv"

DEFAULT_PALETTE = {
    "Booking": "#1b9e77",
    "Airbnb": "#d95f02",
    "Abritel": "#7570b3",
    "Direct": "#e7298a",
}

FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","pays",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid"
]

# --------------- STYLE ---------------
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
          @media print {{
            @page {{ size: A4 landscape; margin: 12mm; }}
            header, footer, [data-testid="stSidebar"], button, .stDownloadButton {{ display:none !important; }}
          }}
          .print-header {{ display:none; }}
          @media print {{ .print-header {{ display:block; font-size: 14px; margin-bottom: 8px; }} }}
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

# --------------- HELPERS DATA ---------------
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

# --------------- INDICATIFS CSV + FLAGS ---------------
INDICATIFS_PRIMARY = "indicatifs _pays.csv"   # nom exact fourni (avec espace)
INDICATIFS_FALLBACK = "indicatifs_pays.csv"   # secours si renommage

def _indicatifs_path() -> str:
    if os.path.exists(INDICATIFS_PRIMARY):
        return INDICATIFS_PRIMARY
    if os.path.exists(INDICATIFS_FALLBACK):
        return INDICATIFS_FALLBACK
    with open(INDICATIFS_PRIMARY, "w", encoding="utf-8", newline="") as f:
        f.write("pays,indicatif,iso2,flag\n")
    return INDICATIFS_PRIMARY

def _flag_emoji_from_iso2(iso2: str) -> str:
    s = (iso2 or "").strip().upper()
    if len(s) != 2 or not s.isalpha():
        return ""
    base = 127397
    return chr(ord(s[0]) + base) + chr(ord(s[1]) + base)

@st.cache_data(show_spinner=False)
def load_indicatifs() -> pd.DataFrame:
    path = _indicatifs_path()
    try:
        df = pd.read_csv(path, dtype=str)
    except Exception:
        df = pd.DataFrame(columns=["pays","indicatif","iso2","flag"])
    for c in ["pays","indicatif","iso2","flag"]:
        if c not in df.columns:
            df[c] = ""
    df["pays"] = df["pays"].fillna("").str.strip()
    df["indicatif"] = df["indicatif"].fillna("").str.strip()
    df["iso2"] = df["iso2"].fillna("").str.strip()
    need_flag = (df["flag"].fillna("") == "")
    if need_flag.any():
        df.loc[need_flag, "flag"] = df.loc[need_flag, "iso2"].apply(_flag_emoji_from_iso2)
    df["_prefix_digits"] = (
        df["indicatif"].astype(str)
        .str.replace(r"^\+","", regex=True)
        .str.replace(r"^00","", regex=True)
        .str.replace(r"\D","", regex=True)
    )
    return df

def save_indicatifs(df: pd.DataFrame) -> None:
    path = _indicatifs_path()
    out = df.copy()
    for c in ["pays","indicatif","iso2","flag"]:
        if c not in out.columns:
            out[c] = ""
    out["iso2"] = out["iso2"].fillna("").str.strip()
    out["flag"] = out["iso2"].apply(_flag_emoji_from_iso2)
    out = out[["pays","indicatif","iso2","flag"]]
    out.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
    st.cache_data.clear()

def _phone_country(phone: str) -> str:
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
    p1 = re.sub(r"\D","", p1)
    try:
        _dfi = load_indicatifs()
        prefixes = _dfi[["_prefix_digits","pays"]].dropna()
        prefixes = prefixes[prefixes["_prefix_digits"] != ""]
        for pref, pays in sorted(prefixes.values.tolist(), key=lambda t: -len(t[0])):
            if pref and p1.startswith(pref):
                return pays or "Inconnu"
    except Exception:
        pass
    PHONE_PREFIX_COUNTRY = {
        "33":"France","34":"Espagne","49":"Allemagne","44":"Royaume-Uni","39":"Italie",
        "41":"Suisse","32":"Belgique","352":"Luxembourg","351":"Portugal",
        "1":"Etats-Unis/Canada","61":"Australie","64":"Nouvelle-Zelande",
        "420":"Tchequie","421":"Slovaquie","36":"Hongrie","40":"Roumanie",
        "30":"Grece","31":"Pays-Bas","353":"Irlande","354":"Islande","358":"Finlande",
        "46":"Suede","47":"Norvege","48":"Pologne","43":"Autriche","45":"Danemark",
        "90":"Turquie","212":"Maroc","216":"Tunisie","971":"Emirats Arabes Unis"
    }
    for k in sorted(PHONE_PREFIX_COUNTRY.keys(), key=lambda x: -len(x)):
        if p1.startswith(k):
            return PHONE_PREFIX_COUNTRY[k]
    return "Inconnu"

# --------------- NORMALISATION & SAUVEGARDE ---------------
def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)
    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()
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
        da = pd.to_datetime(df.loc[mask_ok,"date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok,"date_depart"])
        df.loc[mask_ok,"nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)
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
    need = df["pays"].eq("") | df["pays"].isna()
    if need.any():
        df.loc[need,"pays"] = df.loc[need,"telephone"].apply(_phone_country)
    return df[BASE_COLS]

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
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

@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations: str, csv_plateformes: str):
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

# --------------- APARTMENTS selection ---------------
def _read_apartments_csv() -> pd.DataFrame:
    try:
        if not os.path.exists(APARTMENTS_CSV):
            return pd.DataFrame(columns=["slug","name"])
        raw = _load_file_bytes(APARTMENTS_CSV)
        df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame(columns=["slug","name"])
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "slug" not in df.columns:
            df["slug"] = ""
        if "name" not in df.columns:
            df["name"] = ""
        df["slug"] = (df["slug"].astype(str).str.replace("\ufeff","",regex=False)
                      .str.strip().str.replace(" ","-",regex=False).str.replace("_","-",regex=False).str.lower())
        df["name"] = df["name"].astype(str).str.replace("\ufeff","",regex=False).str.strip()
        df = df[(df["slug"]!="") & (df["name"]!="")].drop_duplicates(subset=["slug"], keep="first")
        return df[["slug","name"]]
    except Exception:
        return pd.DataFrame(columns=["slug","name"])

def _current_apartment() -> dict | None:
    slug = st.session_state.get("apt_slug","")
    name = st.session_state.get("apt_name","")
    if slug and name:
        return {"slug": slug, "name": name}
    return None

def _select_apartment_sidebar() -> bool:
    st.sidebar.markdown("### Appartement")
    df_apts = _read_apartments_csv()
    if df_apts.empty:
        st.sidebar.warning("Aucun appartement trouve dans apartments.csv")
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
    st.sidebar.success(f"Connecte : {name}")
    try:
        print_buttons(location="sidebar")
    except Exception:
        pass
    return changed

def _load_data_for_active_apartment():
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_pal = st.session_state.get("CSV_PLATEFORMES",  CSV_PLATEFORMES)
    try:
        return charger_donnees(csv_res, csv_pal)
    except TypeError:
        return charger_donnees(CSV_RESERVATIONS, CSV_PLATEFORMES)
    except Exception:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE.copy()

# ============================== PART 2/5 - RESERVATIONS, AJOUTER, MODIFIER, PLATEFORMES ==============================

def vue_accueil(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation trouvée.")
        return

    today = date.today()
    tomorrow = today + timedelta(days=1)

    arr_today = df[df["date_arrivee"] == today]
    dep_today = df[df["date_depart"] == today]
    arr_tomorrow = df[df["date_arrivee"] == tomorrow]

    st.subheader("📥 Arrivées aujourd'hui")
    st.dataframe(arr_today[["nom_client","plateforme","telephone","date_depart"]], use_container_width=True)

    st.subheader("📤 Départs aujourd'hui")
    st.dataframe(dep_today[["nom_client","plateforme","telephone","date_arrivee"]], use_container_width=True)

    st.subheader("🛬 Arrivées demain")
    st.dataframe(arr_tomorrow[["nom_client","plateforme","telephone","date_depart"]], use_container_width=True)


# ---------------- Réservations ----------------
def vue_reservations(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    st.dataframe(df, use_container_width=True)


# ---------------- Ajouter ----------------
def vue_ajouter(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter une réservation — {apt_name}")
    print_buttons()

    with st.form("add_form"):
        nom = st.text_input("Nom du client")
        tel = st.text_input("Téléphone")
        email = st.text_input("Email")
        plateforme = st.selectbox("Plateforme", list(palette.keys()))
        arr = st.date_input("Date arrivée", date.today())
        dep = st.date_input("Date départ", date.today() + timedelta(days=1))
        prix = st.number_input("Prix brut (€)", min_value=0.0, step=1.0)
        submit = st.form_submit_button("Ajouter")

    if submit:
        new = {
            "nom_client": nom,
            "telephone": tel,
            "email": email,
            "plateforme": plateforme,
            "date_arrivee": arr,
            "date_depart": dep,
            "nuitees": (dep - arr).days,
            "prix_brut": prix,
            "pays": _phone_country(tel),
        }
        df2 = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
        if sauvegarder_donnees(df2):
            st.success("Réservation ajoutée ✅")
            st.rerun()


# ---------------- Modifier / Supprimer ----------------
def vue_modifier(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation à modifier.")
        return

    choix = st.selectbox("Sélectionner une réservation", df.index, format_func=lambda i: f"{df.loc[i,'nom_client']} ({df.loc[i,'date_arrivee']})")

    if choix is not None:
        r = df.loc[choix]
        with st.form("edit_form"):
            nom = st.text_input("Nom du client", r["nom_client"])
            tel = st.text_input("Téléphone", r["telephone"])
            email = st.text_input("Email", r["email"])
            plateforme = st.selectbox("Plateforme", list(palette.keys()), index=list(palette.keys()).index(r["plateforme"]) if r["plateforme"] in palette else 0)
            arr = st.date_input("Date arrivée", r["date_arrivee"])
            dep = st.date_input("Date départ", r["date_depart"])
            prix = st.number_input("Prix brut (€)", min_value=0.0, value=float(r["prix_brut"] or 0))
            update = st.form_submit_button("Mettre à jour")
            delete = st.form_submit_button("🗑️ Supprimer")

        if update:
            df.at[choix, "nom_client"] = nom
            df.at[choix, "telephone"] = tel
            df.at[choix, "email"] = email
            df.at[choix, "plateforme"] = plateforme
            df.at[choix, "date_arrivee"] = arr
            df.at[choix, "date_depart"] = dep
            df.at[choix, "nuitees"] = (dep - arr).days
            df.at[choix, "prix_brut"] = prix
            df.at[choix, "pays"] = _phone_country(tel)
            if sauvegarder_donnees(df):
                st.success("Réservation mise à jour ✅")
                st.rerun()

        if delete:
            df2 = df.drop(choix).reset_index(drop=True)
            if sauvegarder_donnees(df2):
                st.success("Réservation supprimée 🗑️")
                st.rerun()


# ---------------- Plateformes ----------------
def vue_plateformes(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes — {apt_name}")
    print_buttons()

    plat = pd.DataFrame([
        {"plateforme": p, "couleur": c} for p,c in palette.items()
    ])
    edited = st.data_editor(plat, num_rows="dynamic", use_container_width=True)

    if st.button("💾 Sauvegarder"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur sauvegarde : {e}")

# ============================== PART 3/5 — CALENDRIER & RAPPORT ==============================

def vue_calendrier(df: pd.DataFrame, palette: dict):
    """Grille mensuelle simple + liste des réservations chevauchant le mois choisi."""
    from calendar import Calendar, monthrange
    from html import escape

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation à afficher.")
        return

    # Normalise dates
    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])
    dfv = dfv.dropna(subset=["date_arrivee", "date_depart"])
    if dfv.empty:
        st.info("Aucune réservation avec des dates valides.")
        return

    today = date.today()
    years = sorted({d.year for d in pd.to_datetime(dfv["date_arrivee"]).dt.date}, reverse=True)
    year  = st.selectbox("Année", options=years if years else [today.year], index=0)
    month = st.selectbox("Mois", options=list(range(1, 12+1)), index=(today.month-1))

    # En-têtes jours (Lun -> Dim)
    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div>"
        "<div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True
    )

    def day_resas(d):
        mask = (dfv["date_arrivee"] <= d) & (dfv["date_depart"] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)  # 0=lundi dans calendar ? (en Python, 0=lundi pour isoweekday mais Calendar: 0=lundi)
    html_parts = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(year, month):
        for d in week:
            outside = (d.month != month)
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
                            f"{escape(name)}</div>"
                        )
            cell += "</div>"
            html_parts.append(cell)
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)
    st.markdown("---")

    # Détail du mois
    st.subheader("Détail du mois sélectionné")
    start_m = date(year, month, 1)
    end_m   = date(year, month, monthrange(year, month)[1])
    rows = dfv[(dfv["date_arrivee"] <= end_m) & (dfv["date_depart"] > start_m)].copy()

    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
        return

    plats = ["Toutes"] + sorted(rows["plateforme"].astype(str).replace({"nan": ""}).unique().tolist())
    plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
    if plat != "Toutes":
        rows = rows[rows["plateforme"] == plat]

    # Petites métriques
    for c in ["prix_brut", "prix_net", "nuitees"]:
        rows[c] = pd.to_numeric(rows.get(c, 0), errors="coerce").fillna(0)

    brut = float(rows["prix_brut"].sum())
    net  = float(rows.get("prix_net", 0).sum() if "prix_net" in rows else 0.0)
    nuits= int(rows["nuitees"].sum())

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


def vue_rapport(df: pd.DataFrame, palette: dict):
    """Tableaux de bord simples + graphiques Altair (si disponible)"""
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
    dfa = dfa.dropna(subset=["date_arrivee_dt"])

    # Filtres
    years   = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months  = list(range(1, 12+1))
    plats   = sorted(dfa["plateforme"].astype(str).replace({"nan": ""}).unique().tolist())
    pays_ok = sorted(dfa.get("pays", pd.Series([], dtype=str)).astype(str).replace({"nan": ""}).unique().tolist())

    c1, c2, c3, c4 = st.columns(4)
    year  = c1.selectbox("Année", ["Toutes"] + years, index=0)
    month = c2.selectbox("Mois",  ["Tous"] + months, index=0)
    plat  = c3.selectbox("Plateforme", ["Toutes"] + plats, index=0)
    pay   = c4.selectbox("Pays", ["Tous"] + pays_ok, index=0)

    data = dfa.copy()
    if year != "Toutes":
        data = data[data["date_arrivee_dt"].dt.year == int(year)]
    if month != "Tous":
        data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"] == plat]
    if pay != "Tous" and "pays" in data.columns:
        data = data[data["pays"] == pay]

    if data.empty:
        st.warning("Aucune donnée après filtres.")
        return

    # Métriques
    for c in ["prix_brut", "prix_net", "nuitees", "charges", "base"]:
        if c in data.columns:
            data[c] = pd.to_numeric(data[c], errors="coerce").fillna(0)

    brut = float(data.get("prix_brut", 0).sum())
    net  = float(data.get("prix_net", 0).sum())
    base = float(data.get("base", 0).sum())
    nuits= int(data.get("nuitees", 0).sum())
    adr  = (net / nuits) if nuits > 0 else 0.0
    charges = float(data.get("charges", 0).sum())

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

    # Agrégations mensuelles
    data["mois"] = data["date_arrivee_dt"].dt.to_period("M").astype(str)
    agg_mois = data.groupby("mois", as_index=False)[["prix_net", "prix_brut", "nuitees"]].sum()

    st.markdown("### Détail par mois")
    st.dataframe(agg_mois.sort_values("mois"), use_container_width=True)

    # Graphiques (Altair)
    try:
        cm = data.groupby(["mois", "plateforme"], as_index=False)["prix_net"].sum().sort_values(["mois", "plateforme"])
        chart = alt.Chart(cm).mark_bar().encode(
            x=alt.X("mois:N", sort=None, title="Mois"),
            y=alt.Y("prix_net:Q", title="CA net (€)"),
            color=alt.Color("plateforme:N", title="Plateforme"),
            tooltip=["mois", "plateforme", alt.Tooltip("prix_net:Q", format=",.2f")],
        ).properties(height=420)
        st.altair_chart(chart, use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique indisponible : {e}")

# ============================== PART 4/5 — GOOGLE SHEET, CLIENTS, ID, EXPORT ICS ==============================

def vue_google_sheet(df: pd.DataFrame, palette: dict):
    """Affiche le Google Form/Sheet intégrés + un aperçu des réponses publiées en CSV."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Fiche d'arrivée / Google Sheet — {apt_name}")
    print_buttons()

    # Lien court
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")

    # Formulaire intégré
    st.markdown(
        f'<iframe src="{GOOGLE_FORM_VIEW}" width="100%" height="900" frameborder="0"></iframe>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Feuille intégrée (vue)
    st.subheader("Feuille Google intégrée")
    st.markdown(
        f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>',
        unsafe_allow_html=True,
    )
    st.markdown("---")

    # Réponses publiées (CSV)
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
    """Liste des clients (dédoublonnée), avec pays inféré depuis le téléphone si manquant."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Liste des clients — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucun client.")
        return

    cols = ["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]
    clients = df[cols].copy()
    for c in cols:
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
    """Table légère d'identifiants de réservation pour faciliter les recherches croisées."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🆔 Identifiants des réservations — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    cols = ["res_id", "nom_client", "telephone", "email", "plateforme", "pays"]
    tbl = df[cols].copy()
    for c in cols:
        tbl[c] = tbl[c].astype(str).str.strip().replace({"nan": ""})

    need = tbl["pays"].eq("") | tbl["pays"].isna()
    if need.any():
        tbl.loc[need, "pays"] = tbl.loc[need, "telephone"].apply(_phone_country)

    tbl = tbl.dropna(subset=["res_id"])
    tbl = tbl[tbl["res_id"] != ""].drop_duplicates()

    st.dataframe(tbl, use_container_width=True)


def vue_export_ics(df: pd.DataFrame, palette: dict):
    """Génère un .ics (calendrier) à partir des réservations filtrées par année et plateforme."""
    from datetime import datetime, date

    def _ics_escape(s: str) -> str:
        if s is None:
            return ""
        # RFC5545 escaping
        return (
            str(s)
            .replace("\\", "\\\\")
            .replace("\n", "\\n")
            .replace(",", "\\,")
            .replace(";", "\\;")
        )

    def _fmt_date_yyyymmdd(d) -> str:
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, date):
            return f"{d.year:04d}{d.month:02d}{d.day:02d}"
        try:
            dd = pd.to_datetime(d, errors="coerce")
            if pd.isna(dd):
                return ""
            return dd.strftime("%Y%m%d")
        except Exception:
            return ""

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📆 Export ICS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    dfa["date_depart_dt"]  = pd.to_datetime(dfa["date_depart"], errors="coerce")

    years = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years if years else [date.today().year], index=0)

    plats = ["Tous"] + sorted(dfa["plateforme"].astype(str).replace({"nan": ""}).unique().tolist())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfa[dfa["date_arrivee_dt"].dt.year == int(year)].copy()
    if plat != "Tous":
        data = data[data["plateforme"] == plat]

    if data.empty:
        st.warning("Rien à exporter.")
        return

    # UID stable si manquant
    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip() == "")
    if miss.any():
        data.loc[miss, "ical_uid"] = data.loc[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        "CALSCALE:GREGORIAN",
    ]

    for _, r in data.iterrows():
        dt_a = r.get("date_arrivee_dt")
        dt_d = r.get("date_depart_dt")
        if pd.isna(dt_a) or pd.isna(dt_d):
            continue

        summary = f"{apt_name} — {r.get('nom_client', 'Sans nom')}"
        if r.get("plateforme"):
            summary += f" ({r.get('plateforme')})"

        # Description multi-lignes
        try:
            nuit = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
        except Exception:
            nuit = 0
        try:
            pbrut = float(pd.to_numeric(r.get("prix_brut"), errors="coerce") or 0.0)
        except Exception:
            pbrut = 0.0

        desc = "\n".join(
            [
                f"Client: {r.get('nom_client','')}",
                f"Téléphone: {r.get('telephone','')}",
                f"Nuitées: {nuit}",
                f"Prix brut: {pbrut:.2f} €",
                f"res_id: {r.get('res_id','')}",
            ]
        )

        lines += [
            "BEGIN:VEVENT",
            f"UID:{r.get('ical_uid','')}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt_date_yyyymmdd(dt_a)}",
            f"DTEND;VALUE=DATE:{_fmt_date_yyyymmdd(dt_d)}",
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
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
        key="dl_ics_btn",
    )

# ============================== PART 5/5 — SMS, PARAMÈTRES, MAIN ==============================

def vue_sms(df: pd.DataFrame, palette: dict):
    """Page SMS — messages préformatés (pré-arrivée J+1) et post-départ, avec marquage envoyé."""
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

    # ---------- Pré-arrivée (J+1) ----------
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = dfv.dropna(subset=["telephone", "nom_client", "date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (~_to_bool_series(pre["sms_envoye"]))]

    if pre.empty:
        st.info("Aucun client à contacter pour la date sélectionnée.")
    else:
        pre = pre.sort_values(["date_arrivee", "nom_client"]).reset_index()
        options = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=options, index=None, key="pick_pre")
        if pick:
            sel_idx = int(pick.split(":")[0])
            r = pre.loc[sel_idx]

            arr_txt = r["date_arrivee"].strftime("%d/%m/%Y") if pd.notna(r["date_arrivee"]) else ""
            dep_txt = r["date_depart"].strftime("%d/%m/%Y") if pd.notna(r["date_depart"]) else ""
            nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
            lien_form = FORM_SHORT_URL

            # Message FR + EN construit proprement
            lignes = [
                f"{apt_name.upper()}",
                f"Plateforme : {r.get('plateforme', 'N/A')}",
                f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuitees}",
                "",
                f"Bonjour {r.get('nom_client','')}",
                "Bienvenue chez nous !",
                "",
                "Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre réception,",
                "merci de remplir la fiche en cliquant sur le lien suivant :",
                f"{lien_form}",
                "",
                "Un parking est à votre disposition sur place.",
                "",
                "Le check-in se fait à partir de 14:00 et le check-out avant 11:00.",
                "Nous serons sur place lors de votre arrivée pour vous remettre les clés.",
                "",
                "Vous trouverez des consignes à bagages dans chaque quartier de Nice.",
                "",
                "Nous vous souhaitons un excellent voyage et avons hâte de vous rencontrer très bientôt.",
                "",
                "Annick & Charley",
                "",
                "******",
                "",
                "Welcome to our establishment!",
                "",
                "We are delighted to welcome you soon to Nice. To help us organize your arrival,",
                "please fill in this form:",
                f"{lien_form}",
                "",
                "Parking is available on site.",
                "",
                "Check-in from 2:00 p.m. — check-out before 11:00 a.m.",
                "We will be there when you arrive to give you the keys.",
                "",
                "You will find luggage storage facilities in every district of Nice.",
                "",
                "We wish you a pleasant journey and look forward to meeting you very soon.",
                "",
                "Annick & Charley",
            ]
            msg = "\n".join(lignes)

            st.text_area("📋 Copier le message", value=msg, height=380)

            # Liens rapides (SMS / WhatsApp)
            e164 = _format_phone_e164(r.get("telephone", ""))
            only_digits = "".join(ch for ch in e164 if ch.isdigit())
            enc = quote(msg)

            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}", key="pre_sms_ios")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}", key="pre_sms_android")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits}?text={enc}", key="pre_wa")

            if st.button("✅ Marquer 'SMS envoyé' pour ce client", key="mark_pre_sent"):
                try:
                    df.loc[r["index"], "sms_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    # ---------- Post-départ (départs du jour) ----------
    st.markdown("---")
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = dfv.dropna(subset=["telephone", "nom_client", "date_depart"]).copy()
    post = post[(post["date_depart"] == target_depart) & (~_to_bool_series(post["post_depart_envoye"]))]

    if post.empty:
        st.info("Aucun message post-départ à envoyer aujourd’hui.")
    else:
        post = post.sort_values(["date_depart", "nom_client"]).reset_index()
        options2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=options2, index=None, key="pick_post")
        if pick2:
            sel_idx2 = int(pick2.split(":")[0])
            r2 = post.loc[sel_idx2]
            name = str(r2.get("nom_client") or "").strip()

            lignes2 = [
                f"Bonjour {name},",
                "",
                "Un grand merci d'avoir choisi notre appartement pour votre séjour.",
                "Nous espérons que vous avez passé un moment agréable.",
                "Si vous souhaitez revenir explorer encore un peu la ville, notre porte vous sera toujours grande ouverte.",
                "",
                "Au plaisir de vous accueillir à nouveau.",
                "",
                "Annick & Charley",
                "",
                "******",
                "",
                f"Hello {name},",
                "",
                "Thank you very much for choosing our apartment for your stay.",
                "We hope you had a great time — our door is always open if you want to come back.",
                "",
                "Annick & Charley",
            ]
            msg2 = "\n".join(lignes2)

            st.text_area("📋 Copier le message", value=msg2, height=280)
            e164b = _format_phone_e164(r2.get("telephone", ""))
            only_digits_b = "".join(ch for ch in e164b if ch.isdigit())
            enc2 = quote(msg2)

            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits_b}?text={enc2}", key="post_wa")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}", key="post_sms_ios")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}", key="post_sms_android")

            if st.button("✅ Marquer 'post-départ envoyé' pour ce client", key="mark_post_sent"):
                try:
                    df.loc[r2["index"], "post_depart_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")


# ============================== PARAMÈTRES ==============================

def vue_settings(df: pd.DataFrame, palette: dict):
    """Sauvegarde / restauration des données + maintenance apartments.csv + cache."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header("## ⚙️ Paramètres")
    st.subheader(apt_name)
    print_buttons()
    st.caption("Sauvegarde, restauration, cache et outil secours pour apartments.csv.")

    # ---- Sauvegarde (exports) ----
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

    # ---- Restauration (CSV/XLSX) ----
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

    # ---- Vider le cache ----
    st.markdown("### 🧹 Vider le cache")
    if st.button("Vider le cache & recharger", key="clear_cache_btn_settings"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    # ---- Outil secours apartments.csv ----
    st.markdown("### 🧰 Écraser apartments.csv")
    default_csv = "slug,name\nvilla-tobias,Villa Tobias\nle-turenne,Le Turenne\n"
    txt = st.text_area("Contenu apartments.csv", value=default_csv, height=140, key="force_apts_txt_settings")
    if st.button("🧰 Écraser apartments.csv (outil secours)", key="force_apts_btn_settings"):
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

    # Pages (doivent toutes exister)
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