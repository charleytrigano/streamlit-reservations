# -*- coding: utf-8 -*-
# ============================== PARTIE 1/5 — IMPORTS, CONFIG, STYLES, HELPERS, SCHEMA, PERSISTANCE, APPARTS, AUTH ==============================

import os
import re
import uuid
import hashlib
from io import StringIO, BytesIO
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import urlencode, quote

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt
import streamlit.components.v1 as components

# ---------------- CONFIG ----------------
st.set_page_config(page_title="Villa Tobias — Réservations", page_icon="✨", layout="wide")

# Chemins par défaut (remplacés après login par _set_current_apartment)
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb": "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre": "#f59e0b",
}

# Google Form
GOOGLE_FORM_BASE = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GF_RES_ID = "entry.1972868847"
GF_NAME   = "entry.937556468"
GF_PHONE  = "entry.702324920"
GF_ARR    = "entry.1099006415"  # yyyy-mm-dd
GF_DEP    = "entry.2013910918"  # yyyy-mm-dd

# Lien court fourni (utilisé par défaut dans les SMS)
FORM_SHORT_URL = "https://urlr.me/kZuH94"

def build_form_url(res_id: str, nom: str, tel: str, d_arr: date, d_dep: date) -> str:
    """Génère un lien Google Form pré-rempli (utilisé si coché dans SMS)."""
    def _fmt(d):
        try:
            return pd.to_datetime(d).strftime("%Y-%m-%d")
        except Exception:
            return ""
    params = {
        GF_RES_ID: str(res_id or ""),
        GF_NAME:   str(nom or ""),
        GF_PHONE:  str(tel or ""),
        GF_ARR:    _fmt(d_arr),
        GF_DEP:    _fmt(d_dep),
        "usp": "pp_url",
    }
    return f"{GOOGLE_FORM_BASE}?{urlencode(params)}"

# ---------------- STYLES ----------------
def apply_style(light: bool):
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    chip_bg = "#333" if not light else "#e8e8e8"
    chip_fg = "#eee" if not light else "#222"
    st.markdown(
        f"""
        <style>
          html, body, [data-testid="stAppViewContainer"] {{ background:{bg}; color:{fg}; }}
          [data-testid="stSidebar"] {{ background:{side}; border-right:1px solid {border}; }}
          .glass {{ background:{"rgba(255,255,255,0.65)" if light else "rgba(255,255,255,0.06)"}; border:1px solid {border}; border-radius:12px; padding:12px; margin:8px 0; }}
          .chip {{ display:inline-block; background:{chip_bg}; color:{chip_fg}; padding:6px 10px; border-radius:12px; margin:4px 6px; font-size:.86rem }}
          .kpi-line strong {{ font-size:1.05rem; }}
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; margin-top:8px; }}
          .cal-cell {{ border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px; position:relative; overflow:hidden; background:{"#fff" if light else "#0b0d12"}; }}
          .cal-cell.outside {{ opacity:.45; }}
          .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
          .resa-pill {{ padding:4px 6px; border-radius:6px; font-size:.85rem; margin-top:22px; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
          .cal-header {{ display:grid; grid-template-columns: repeat(7, 1fr); font-weight:700; opacity:.8; margin-top:10px; }}
          @media print {{
            .no-print {{ display:none !important; }}
            [data-testid="stSidebar"] {{ display:none !important; }}
            [data-testid="stToolbar"] {{ display:none !important; }}
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

def print_buttons():
    """Bandeau avec nom de l'appartement + bouton Imprimer."""
    apt_name = st.session_state.get("apt_name") or st.session_state.get("apt_slug") or ""
    components.html(
        f"""
        <div style="
          background: rgba(255,255,255,0.65);
          border: 1px solid rgba(17,24,39,.12);
          border-radius: 12px;
          padding: 12px;
          margin: -6px 0 8px 0;
          display: flex;
          align-items: center;
          justify-content: space-between;
          font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;">
          <div style="font-size: 1.75rem; font-weight: 800; letter-spacing: .5px;">
            {apt_name}
          </div>
          <button
            style="border:1px solid rgba(17,24,39,.18); padding:8px 12px; border-radius:10px; background:transparent; cursor:pointer;"
            onclick="parent.window.print()">
            🖨️ Imprimer
          </button>
        </div>
        """,
        height=70,
    )

# ---------------- DATA HELPERS ----------------
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid"
]

@st.cache_data
def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None:
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff","")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 2:
                return df
        except Exception:
            pass
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
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
    sc = (s.astype(str)
          .str.replace("€","",regex=False)
          .str.replace(" ","",regex=False)
          .str.replace(",",".",regex=False)
          .str.strip())
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

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+" + s
    if s.startswith("0"):  return "+33" + s[1:]
    return "+" + s

# Détection pays (simplifiée) par indicatif
PHONE_CC = {
    "33":"France","32":"Belgique","41":"Suisse","49":"Allemagne","34":"Espagne","39":"Italie",
    "44":"Royaume-Uni","351":"Portugal","352":"Luxembourg","31":"Pays-Bas","1":"USA/Canada",
    "212":"Maroc","216":"Tunisie","90":"Turquie","30":"Grèce","353":"Irlande","420":"Tchéquie",
    "43":"Autriche","48":"Pologne","46":"Suède","47":"Norvège","45":"Danemark"
}
def _phone_country(tel: str) -> str:
    s = str(tel or "").strip()
    if not s: return ""
    s = s.replace(" ","")
    if s.startswith("+"): s = s[1:]
    if s.startswith("00"): s = s[2:]
    if s.startswith("0"): return "France"  # 0X régional -> France
    for k in sorted(PHONE_CC.keys(), key=lambda x: -len(x)):
        if s.startswith(k):
            return PHONE_CC[k]
    return "Inconnu"

# ---------------- SCHEMA & PERSISTANCE ----------------
def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    rename_map = {
        'Payé':'paye','Client':'nom_client','Plateforme':'plateforme',
        'Arrivée':'date_arrivee','Départ':'date_depart','Nuits':'nuitees',
        'Brut (€)':'prix_brut'
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
    commissions = _to_num(df["commissions"]); frais_cb = _to_num(df["frais_cb"])
    menage = _to_num(df["menage"]); taxes = _to_num(df["taxes_sejour"])

    df["prix_net"] = (prix_brut - commissions - frais_cb).fillna(0.0)
    df["charges"]  = (prix_brut - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - menage - taxes).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(prix_brut > 0, (df["charges"]/prix_brut*100), 0.0)
    df["%"] = pd.Series(pct, index=df.index).astype(float)

    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip() == "")
    if miss_res.any():
        df.loc[miss_res,"res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip() == "")
    if miss_uid.any():
        df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = df[c].astype(str).replace({"nan":"","None":""}).str.strip()

    return df[BASE_COLS]

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

def _df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Reservations"):
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        return buf.getvalue(), None
    except Exception as e:
        st.warning(f"Impossible de générer l'Excel (openpyxl requis) : {e}")
        return None, e

# ---------------- apartments.csv (lecture & outils) ----------------
@st.cache_data
def _load_apartments_csv(path: str = "apartments.csv") -> pd.DataFrame:
    try:
        if not os.path.exists(path):
            return pd.DataFrame(columns=["slug","name","password_hash"])
        raw = _load_file_bytes(path)
        if raw is None:
            return pd.DataFrame(columns=["slug","name","password_hash"])
        txt = raw.decode("utf-8", errors="ignore").replace("\ufeff","")
        df = pd.DataFrame()
        for sep in [";", ","]:
            try:
                tmp = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
                tmp.columns = [c.strip().lower() for c in tmp.columns]
                if {"slug","name","password_hash"}.issubset(tmp.columns):
                    df = tmp; break
            except Exception:
                pass
        if df.empty:
            df = pd.read_csv(StringIO(txt), dtype=str)
            df.columns = [c.strip().lower() for c in df.columns]
        for c in ["slug","name","password_hash"]:
            if c not in df.columns: df[c] = ""
            df[c] = df[c].astype(str).str.replace("\ufeff","",regex=False).str.strip()
        df = df[(df["slug"]!="") & (df["name"]!="")].drop_duplicates(subset=["slug"]).reset_index(drop=True)
        return df[["slug","name","password_hash"]]
    except Exception as e:
        st.warning(f"Erreur lecture apartments.csv : {e}")
        return pd.DataFrame(columns=["slug","name","password_hash"])

def _debug_apartments_panel():
    path = "apartments.csv"
    with st.expander("🔎 Diagnostic appartements", expanded=False):
        abspath = os.path.abspath(path); exists = os.path.exists(path)
        st.write(f"Fichier : `{path}` — Existe : **{exists}**")
        st.caption(f"Chemin absolu : {abspath}")
        if exists:
            try:
                df_apts = _load_apartments_csv(path)
                st.write(f"Lignes lues : {len(df_apts)}")
                st.dataframe(df_apts, use_container_width=True)
                st.write("Slugs détectés :", ", ".join(df_apts["slug"].tolist()) if not df_apts.empty else "—")
            except Exception as e:
                st.warning(f"Lecture apartments.csv KO : {e}")

def _force_write_apartments_csv(key_prefix: str = "main"):
    with st.expander("🧰 Écraser apartments.csv (outil secours)", expanded=False):
        st.caption("Colle ci-dessous le contenu EXACT de apartments.csv (UTF-8, séparateur virgule).")
        default_csv = (
            "slug,name,password_hash\n"
            "villa-tobias,Villa Tobias,\n"
            "le-turenne,Le Turenne,\n"
        )
        ta_key  = f"{key_prefix}_force_apts_txt"
        btn_key = f"{key_prefix}_force_apts_btn"

        txt = st.text_area("Contenu apartments.csv", value=default_csv, height=140, key=ta_key)
        if st.button("💾 ÉCRASER apartments.csv", key=btn_key):
            try:
                with open("apartments.csv","w",encoding="utf-8",newline="\n") as f:
                    f.write(txt)
                st.cache_data.clear()
                st.success("Écrit ✅ — rechargement…")
                st.rerun()
            except Exception as e:
                st.error(f"Échec écriture : {e}")

# Mapping fichiers par appartement (slug)
def _paths_for_slug(slug: str) -> dict:
    base_slug = slug.strip()
    return {
        "CSV_RESERVATIONS": f"reservations_{base_slug}.csv",
        "CSV_PLATEFORMES":  f"plateformes_{base_slug}.csv",
    }

def _ensure_files_for_slug(slug: str):
    paths = _paths_for_slug(slug)
    if not os.path.exists(paths["CSV_RESERVATIONS"]):
        with open(paths["CSV_RESERVATIONS"], "w", encoding="utf-8") as f:
            f.write("nom_client,email,telephone,plateforme,date_arrivee,date_depart,nuitees,prix_brut,paye\n")
    if not os.path.exists(paths["CSV_PLATEFORMES"]):
        with open(paths["CSV_PLATEFORMES"], "w", encoding="utf-8") as f:
            f.write("plateforme,couleur\nAirbnb,#e74c3c\nBooking,#1e90ff\n")

def _set_current_apartment(slug: str):
    global CSV_RESERVATIONS, CSV_PLATEFORMES
    _ensure_files_for_slug(slug)
    p = _paths_for_slug(slug)
    CSV_RESERVATIONS = p["CSV_RESERVATIONS"]
    CSV_PLATEFORMES  = p["CSV_PLATEFORMES"]

def _debug_sources_panel():
    try:
        slug = st.session_state.get("apt_slug", None) or "(non connecté)"
        if slug and isinstance(slug,str) and slug != "(non connecté)":
            p = _paths_for_slug(slug)
            paths = {"CSV_RESERVATIONS": p["CSV_RESERVATIONS"], "CSV_PLATEFORMES": p["CSV_PLATEFORMES"]}
        else:
            paths = {"CSV_RESERVATIONS": CSV_RESERVATIONS, "CSV_PLATEFORMES": CSV_PLATEFORMES}
        with st.expander("🔎 Diagnostic fichiers", expanded=False):
            st.write(f"**Appartement courant (slug)** : `{slug}`")
            for k, v in paths.items():
                abspath = os.path.abspath(v); exists = os.path.exists(v)
                size = os.path.getsize(v) if exists else 0
                st.write(f"- **{k}** → `{v}`"); st.caption(f"Chemin absolu : {abspath}")
                st.write(f"Existe : {exists} — Taille : {size} octets")
                if exists:
                    raw = _load_file_bytes(v)
                    df_test = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
                    st.write(f"Lignes lues : {len(df_test)} — Colonnes : {list(df_test.columns)}")
    except Exception as e:
        st.warning(f"Diagnostic indisponible : {e}")

def _files_cache_key() -> tuple:
    slug = st.session_state.get("apt_slug", "")
    r = CSV_RESERVATIONS
    p = CSV_PLATEFORMES
    try:
        r_m = os.path.getmtime(r)
    except Exception:
        r_m = 0
    try:
        p_m = os.path.getmtime(p)
    except Exception:
        p_m = 0
    return (slug, r, r_m, p, p_m)

# Changement de mot de passe
def _update_apartment_password(slug: str, new_plain_pwd: str) -> bool:
    try:
        path = "apartments.csv"
        df = _load_apartments_csv(path)
        if df.empty:
            st.error("apartments.csv introuvable ou vide.")
            return False
        if slug not in df["slug"].tolist():
            st.error(f"Appartement {slug} introuvable dans apartments.csv.")
            return False
        new_hash = hashlib.sha256(new_plain_pwd.encode("utf-8")).hexdigest()
        df.loc[df["slug"] == slug, "password_hash"] = new_hash
        df.to_csv(path, index=False, encoding="utf-8")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Échec de mise à jour du mot de passe : {e}")
        return False

# ---------------- CHARGEMENT DONNEES ----------------
@st.cache_data
def charger_donnees(_cache_key: tuple):
    if not os.path.exists(CSV_RESERVATIONS):
        with open(CSV_RESERVATIONS,"w",encoding="utf-8") as f:
            f.write("nom_client,email,telephone,plateforme,date_arrivee,date_depart,nuitees,prix_brut,paye\n")
    if not os.path.exists(CSV_PLATEFORMES):
        with open(CSV_PLATEFORMES,"w",encoding="utf-8") as f:
            f.write("plateforme,couleur\nAirbnb,#e74c3c\nBooking,#1e90ff\n")

    raw = _load_file_bytes(CSV_RESERVATIONS)
    base_df = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base_df)

    rawp = _load_file_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if {"plateforme","couleur"}.issubset(pal_df.columns):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception as e:
            st.warning(f"Palette non chargée : {e}")

    return df, palette

# ---------------- AUTH (sidebar) ----------------
def _auth_gate_in_sidebar() -> bool:
    st.sidebar.subheader("🔐 Appartement")
    _debug_apartments_panel()
    _force_write_apartments_csv(key_prefix="sidebar")

    df_apts = _load_apartments_csv("apartments.csv")
    if df_apts.empty:
        st.sidebar.error("Aucun appartement trouvé dans apartments.csv")
        return False

    choices = [f"{row['name']} ({row['slug']})" for _, row in df_apts.iterrows()]
    default_idx = 0
    last_slug = st.session_state.get("apt_slug")
    if last_slug:
        for i, (_, r) in enumerate(df_apts.iterrows()):
            if r["slug"] == last_slug:
                default_idx = i; break

    pick = st.sidebar.selectbox("Appartement", options=choices, index=default_idx, key="apt_pick")
    slug = pick.split("(")[-1].rstrip(")").strip()
    row = df_apts[df_apts["slug"] == slug].iloc[0]

    pwd = st.sidebar.text_input("Mot de passe", type="password", value="")
    if st.sidebar.button("Se connecter", use_container_width=True):
        ok = True
        ph = str(row.get("password_hash","") or "").strip()
        if ph:
            try:
                test = hashlib.sha256(pwd.encode("utf-8")).hexdigest()
                ok = (test == ph)
            except Exception:
                ok = False
        if ok:
            st.session_state["apt_slug"] = slug
            st.session_state["apt_name"] = row["name"]
            _set_current_apartment(slug)
            st.cache_data.clear()
            st.sidebar.success(f"Connecté à {row['name']} ({slug}) ✅")
            st.rerun()
        else:
            st.sidebar.error("Mot de passe incorrect.")
            return False

    if st.session_state.get("apt_slug"):
        if st.sidebar.button("Changer d'appartement"):
            st.session_state.pop("apt_slug", None)
            st.session_state.pop("apt_name", None)
            st.cache_data.clear()
            st.rerun()

        with st.sidebar.expander("🔑 Changer le mot de passe", expanded=False):
            st.caption("Change le mot de passe de l'appartement courant.")
            old_pwd = st.text_input("Ancien mot de passe", type="password")
            new_pwd = st.text_input("Nouveau mot de passe", type="password")
            new_pwd2 = st.text_input("Confirme le nouveau mot de passe", type="password")
            if st.button("Mettre à jour le mot de passe"):
                df_apts = _load_apartments_csv("apartments.csv")
                row = df_apts[df_apts["slug"] == st.session_state["apt_slug"]].iloc[0]
                ph = str(row.get("password_hash", "") or "")
                ok_old = True
                if ph:
                    try:
                        ok_old = (hashlib.sha256(old_pwd.encode("utf-8")).hexdigest() == ph)
                    except Exception:
                        ok_old = False
                if not ok_old:
                    st.error("Ancien mot de passe incorrect.")
                elif not new_pwd:
                    st.error("Le nouveau mot de passe ne peut pas être vide.")
                elif new_pwd != new_pwd2:
                    st.error("La confirmation ne correspond pas.")
                else:
                    if _update_apartment_password(st.session_state["apt_slug"], new_pwd):
                        st.success("Mot de passe mis à jour ✅ — reconnecte-toi.")
                        st.session_state.pop("apt_slug", None)
                        st.session_state.pop("apt_name", None)
                        st.rerun()

    return bool(st.session_state.get("apt_slug"))


# ============================== PARTIE 2/5 — ACCUEIL, RÉSERVATIONS, AJOUTER, MODIFIER, PLATEFORMES, CALENDRIER ==============================

# ---------- Accueil ----------
def vue_accueil(df: pd.DataFrame, palette: dict):
    st.header("🏠 Accueil")
    print_buttons()
    today = date.today()
    tomorrow = today + timedelta(days=1)
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    arr = dfv[dfv["date_arrivee"] == today][["nom_client","telephone","plateforme"]].copy()
    dep = dfv[dfv["date_depart"]  == today][["nom_client","telephone","plateforme"]].copy()
    arr_plus1 = dfv[dfv["date_arrivee"] == tomorrow][["nom_client","telephone","plateforme"]].copy()

    c1,c2,c3 = st.columns(3)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame(columns=["nom_client","telephone","plateforme"]), use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame(columns=["nom_client","telephone","plateforme"]), use_container_width=True)
    with c3:
        st.subheader("🟠 Arrivées J+1 (demain)")
        st.dataframe(arr_plus1 if not arr_plus1.empty else pd.DataFrame(columns=["nom_client","telephone","plateforme"]), use_container_width=True)


# ---------- Réservations ----------
def vue_reservations(df: pd.DataFrame, palette: dict):
    st.header("📋 Réservations")
    print_buttons()
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")

    years_avail  = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1,13))
    plats_avail  = sorted(dfa["plateforme"].dropna().astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist())

    colf1,colf2,colf3,colf4 = st.columns(4)
    year = colf1.selectbox("Année", ["Toutes"]+years_avail, index=0)
    month = colf2.selectbox("Mois", ["Tous"]+months_avail, index=0)
    plat = colf3.selectbox("Plateforme", ["Toutes"]+plats_avail, index=0)
    pay_filter = colf4.selectbox("Paiement", ["Tous","Payé","Non payé"], index=0)

    data = dfa.copy()
    if year != "Toutes":
        data = data[data["date_arrivee_dt"].dt.year == int(year)]
    if month != "Tous":
        data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]
    if pay_filter != "Tous":
        want = (pay_filter == "Payé")
        data = data[_to_bool_series(data["paye"]) == want]

    brut = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(data["prix_net"], errors="coerce").fillna(0).sum())
    base = float(pd.to_numeric(data["base"], errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(data["nuitees"], errors="coerce").fillna(0).sum())
    adr  = (net/nuits) if nuits>0 else 0.0
    charges = float(pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum())

    html = f"""
    <div class='glass kpi-line'>
      <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
      <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
      <span class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></span>
      <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
      <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
      <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
    </div>
    """.replace(",", " ")
    st.markdown(html, unsafe_allow_html=True)
    st.markdown("---")

    order_idx = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order_idx]
    st.dataframe(data.drop(columns=["date_arrivee_dt"]), use_container_width=True)


# ---------- Ajouter ----------
def vue_ajouter(df: pd.DataFrame, palette: dict):
    st.header("➕ Ajouter une réservation")
    print_buttons()
    with st.form("form_add", clear_on_submit=True):
        c1,c2 = st.columns(2)
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


# ---------- Modifier / Supprimer ----------
def vue_modifier(df: pd.DataFrame, palette: dict):
    st.header("✏️ Modifier / Supprimer")
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
    original_idx = df_sorted.loc[idx,"index"]
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
            menage = float(pd.to_numeric(row.get("menage"), errors="coerce") or 0)
            taxes  = float(pd.to_numeric(row.get("taxes_sejour"), errors="coerce") or 0)
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=brut)
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=commissions)
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=frais_cb)
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=menage)
            taxes  = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=taxes)

        b1,b2 = st.columns([0.7,0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            for k, v in {
                "nom_client": nom,"email": email,"telephone": tel,"date_arrivee": arrivee,"date_depart": depart,
                "plateforme": plat,"paye": paye,"prix_brut": brut,"commissions": commissions,"frais_cb": frais_cb,
                "menage": menage,"taxes_sejour": taxes
            }.items():
                df.loc[original_idx, k] = v
            if sauvegarder_donnees(df):
                st.success("Modifié ✅")
                st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé.")
                st.rerun()


# ---------- Plateformes ----------
def vue_plateformes(df: pd.DataFrame, palette: dict):
    st.header("🎨 Plateformes & couleurs")
    print_buttons()
    has_colorcol = hasattr(getattr(st,"column_config",object), "ColorColumn")

    plats_df = sorted(df.get("plateforme", pd.Series([], dtype=str)).astype(str).str.strip()
                      .replace({"nan":""}).dropna().unique().tolist())
    all_plats = sorted(set(list(palette.keys()) + plats_df))
    base = pd.DataFrame({"plateforme": all_plats, "couleur":[palette.get(p,"#666666") for p in all_plats]})

    if has_colorcol:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorColumn("Couleur (hex)")
        }
    else:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn("Couleur (hex)", validate=r"^#([0-9A-Fa-f]{6})$", width="small")
        }
        st.caption("Astuce: ta version de Streamlit ne supporte pas le sélecteur couleur — saisis un hex (#e74c3c).")

    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True, column_config=col_cfg)

    c1,c2 = st.columns([0.6,0.4])
    if c1.button("💾 Enregistrer la palette"):
        try:
            to_save = edited.copy()
            to_save["plateforme"] = to_save["plateforme"].astype(str).str.strip()
            to_save["couleur"]    = to_save["couleur"].astype(str).str.strip()
            to_save = to_save[to_save["plateforme"] != ""].drop_duplicates(subset=["plateforme"])
            if not has_colorcol:
                ok = to_save["couleur"].str.match(r"^#([0-9A-Fa-f]{6})$")
                to_save.loc[~ok, "couleur"] = "#666666"
            to_save.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
            st.success("Palette enregistrée ✅")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("↩️ Restaurer palette par défaut"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(
                CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
            st.success("Palette par défaut restaurée.")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")


# ---------- Calendrier (grille) ----------
def vue_calendrier(df: pd.DataFrame, palette: dict):
    st.header("📅 Calendrier (grille mensuelle)")
    print_buttons()
    dfv = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    def day_resas(d):
        mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)
    html = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(annee, mois):
        for d in week:
            outside = (d.month != mois)
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'><div class='cal-date'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                if not rs.empty:
                    for _, r in rs.iterrows():
                        color = palette.get(r.get('plateforme'), '#888')
                        name = str(r.get('nom_client') or '')[:22]
                        cell += f"<div class='resa-pill' style='background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)


# ============================== PARTIE 3/5 — RAPPORT (KPIs, Occupation, Finances, Pays) ==============================

def vue_rapport(df: pd.DataFrame, palette: dict):
    """Tableaux de bord et KPIs par plateforme et par pays."""
    st.header("📊 Rapport")
    print_buttons()
    if df is None or df.empty:
        st.info("Aucune donnée.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    dfa["date_depart_dt"]  = pd.to_datetime(dfa["date_depart"], errors="coerce")
    dfa["pays"] = dfa["telephone"].apply(_phone_country).replace("", "Inconnu")

    years_avail  = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1,13))
    plats_avail  = sorted(dfa["plateforme"].astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist())
    pays_avail   = sorted(dfa["pays"].unique().tolist())
    if "France" in pays_avail:
        pays_avail = ["France"] + [p for p in pays_avail if p != "France"]

    c1,c2,c3,c4,c5 = st.columns([1,1,1,1.2,1.2])
    year   = c1.selectbox("Année", ["Toutes"]+years_avail, index=0)
    month  = c2.selectbox("Mois", ["Tous"]+months_avail, index=0)
    plat   = c3.selectbox("Plateforme", ["Toutes"]+plats_avail, index=0)
    payf   = c4.selectbox("Pays", ["Tous"]+pays_avail, index=0)
    metric = c5.selectbox("Métrique", ["prix_brut","prix_net","base","charges","menage","taxes_sejour","nuitees"], index=1)

    data = dfa.copy()
    if year != "Toutes": data = data[data["date_arrivee_dt"].dt.year == int(year)]
    if month != "Tous":  data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat != "Toutes": data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]
    if payf != "Tous":   data = data[data["pays"] == payf]
    if data.empty:
        st.warning("Aucune donnée après filtres.")
        return

    # ================= KPIs haut de page =================
    brut    = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net     = float(pd.to_numeric(data["prix_net"], errors="coerce").fillna(0).sum())
    base    = float(pd.to_numeric(data["base"], errors="coerce").fillna(0).sum())
    nuits   = int(pd.to_numeric(data["nuitees"], errors="coerce").fillna(0).sum())
    adr     = (net/nuits) if nuits>0 else 0.0
    charges = float(pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum())

    html = f"""
    <div class='glass kpi-line'>
      <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
      <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
      <span class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></span>
      <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
      <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
      <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
    </div>
    """.replace(",", " ")
    st.markdown(html, unsafe_allow_html=True)

    st.markdown("---")

    # ================= Taux d'occupation =================
    st.subheader("📅 Taux d'occupation")
    data["nuitees_calc"] = (data["date_depart_dt"] - data["date_arrivee_dt"]).dt.days.clip(lower=0)
    data["mois"] = data["date_arrivee_dt"].dt.to_period("M").astype(str)

    occ_mois = data.groupby(["mois","plateforme"], as_index=False)["nuitees_calc"].sum()
    occ_mois.rename(columns={"nuitees_calc":"nuitees_occupees"}, inplace=True)

    def _jours_dans_mois(periode_str):
        annee, mois = map(int, periode_str.split("-"))
        return monthrange(annee, mois)[1]

    occ_mois["jours_dans_mois"] = occ_mois["mois"].apply(_jours_dans_mois)
    occ_mois["taux_occupation"] = (occ_mois["nuitees_occupees"]/occ_mois["jours_dans_mois"])*100

    col_plat, col_export = st.columns([1,1])
    plat_occ = col_plat.selectbox("Filtrer par plateforme (occupation)", ["Toutes"]+plats_avail, index=0)
    occ_filtered = occ_mois if plat_occ == "Toutes" else occ_mois[occ_mois["plateforme"] == plat_occ]

    # KPIs occupation filtrée
    filtered_nuitees = pd.to_numeric(occ_filtered["nuitees_occupees"], errors="coerce").fillna(0).sum()
    filtered_jours   = pd.to_numeric(occ_filtered["jours_dans_mois"], errors="coerce").fillna(0).sum()
    taux_global_filtered = (filtered_nuitees/filtered_jours*100) if filtered_jours>0 else 0

    st.markdown(
        f"""
        <div class='glass kpi-line'>
            <span class='chip'><small>Taux global</small><br><strong>{taux_global_filtered:.1f}%</strong></span>
            <span class='chip'><small>Nuitées occupées</small><br><strong>{int(filtered_nuitees)}</strong></span>
            <span class='chip'><small>Jours disponibles</small><br><strong>{int(filtered_jours)}</strong></span>
            <span class='chip'><small>Pays filtré</small><br><strong>{payf if payf!='Tous' else 'Tous'}</strong></span>
        </div>
        """, unsafe_allow_html=True
    )

    # Export occupation
    occ_export = occ_filtered[["mois","plateforme","nuitees_occupees","jours_dans_mois","taux_occupation"]] \
                 .sort_values(["mois","plateforme"], ascending=[False, True])
    csv_occ = occ_export.to_csv(index=False).encode("utf-8")
    col_export.download_button("⬇️ Export occupation (CSV)", data=csv_occ, file_name="taux_occupation.csv", mime="text/csv")
    xlsx_occ, _ = _df_to_xlsx_bytes(occ_export, "Taux d'occupation")
    if xlsx_occ:
        col_export.download_button("⬇️ Export occupation (Excel)", data=xlsx_occ, file_name="taux_occupation.xlsx",
                                   mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    st.dataframe(occ_export.assign(taux_occupation=lambda x: x["taux_occupation"].round(1)), use_container_width=True)

    # ================= Comparaison annuelle =================
    st.markdown("---")
    st.subheader("📊 Comparaison des taux d'occupation par année")
    data["annee"] = data["date_arrivee_dt"].dt.year
    occ_annee = data.groupby(["annee","plateforme"])["nuitees_calc"].sum().reset_index().rename(columns={"nuitees_calc":"nuitees_occupees"})

    def _jours_dans_annee(a):
        return 366 if ((a % 4 == 0 and a % 100 != 0) or (a % 400 == 0)) else 365

    occ_annee["jours_dans_annee"] = occ_annee["annee"].apply(_jours_dans_annee)
    occ_annee["taux_occupation"]  = (occ_annee["nuitees_occupees"]/occ_annee["jours_dans_annee"])*100

    years_opts = sorted(occ_annee["annee"].unique())
    default_years = years_opts[-2:] if len(years_opts)>=2 else years_opts
    annees_comparaison = st.multiselect("Sélectionner les années à comparer", options=years_opts, default=default_years)

    if annees_comparaison:
        occ_comparaison = occ_annee[occ_annee["annee"].isin(annees_comparaison)].copy()
        try:
            chart_comparaison = alt.Chart(occ_comparaison).mark_bar().encode(
                x=alt.X("annee:N", title="Année"),
                y=alt.Y("taux_occupation:Q", title="Taux d'occupation (%)", scale=alt.Scale(domain=[0,100])),
                color=alt.Color("plateforme:N", title="Plateforme"),
                tooltip=["annee","plateforme", alt.Tooltip("taux_occupation:Q", format=".1f")]
            ).properties(height=400)
            st.altair_chart(chart_comparaison, use_container_width=True)
        except Exception as e:
            st.warning(f"Graphique indisponible : {e}")

        st.dataframe(
            occ_comparaison.sort_values(["annee","plateforme"]).assign(
                taux_occupation=lambda x: x["taux_occupation"].round(1)
            ),
            use_container_width=True
        )

    # ================= Métriques financières =================
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

    # ================= Analyse par pays =================
    st.markdown("---")
    st.subheader("🌍 Analyse par pays")
    data_p = data.copy()
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
        pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0) / total_net * 100,
        0.0
    )
    agg_pays["ADR_net"] = np.where(
        pd.to_numeric(agg_pays["nuitees"], errors="coerce").fillna(0)>0,
        pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0) / pd.to_numeric(agg_pays["nuitees"], errors="coerce").fillna(0),
        0.0
    )

    agg_pays = agg_pays.sort_values(["prix_net","reservations"], ascending=[False,False])
    nb_pays = int(agg_pays["pays"].nunique())
    total_res = int(pd.to_numeric(agg_pays["reservations"], errors="coerce").fillna(0).sum())
    top_pays = agg_pays.iloc[0]["pays"] if not agg_pays.empty else "—"

    st.markdown(
        f"""<div class='glass kpi-line'>
        <span class='chip'><small>Pays distincts</small><br><strong>{nb_pays}</strong></span>
        <span class='chip'><small>Total réservations</small><br><strong>{total_res}</strong></span>
        <span class='chip'><small>Top pays (CA net)</small><br><strong>{top_pays}</strong></span>
        </div>""",
        unsafe_allow_html=True
    )

    # Affichage tableau pays
    cols_show = [c for c in ["pays","reservations","nuitees","prix_brut","prix_net","charges","menage","taxes_sejour","base","ADR_net","part_revenu_%"] if c in agg_pays.columns]
    st.dataframe(
        agg_pays.assign(ADR_net=lambda x: x["ADR_net"].round(2), part_revenu_=lambda x: x["part_revenu_%"].round(1))[cols_show],
        use_container_width=True
    )


# ============================== PARTIE 4/5 — SMS, Export ICS, Google Sheet, Clients, ID ==============================

# ---------- Helpers messages SMS ----------
def _build_pre_arrival_message(r: pd.Series, apt_name: str, link: str) -> str:
    arr = pd.to_datetime(r.get("date_arrivee"), errors="coerce")
    dep = pd.to_datetime(r.get("date_depart"), errors="coerce")
    nuits = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
    plat  = str(r.get("plateforme") or "—")
    name  = str(r.get("nom_client") or "").strip()
    arr_txt = arr.strftime("%d/%m/%Y") if pd.notna(arr) else ""
    dep_txt = dep.strftime("%d/%m/%Y") if pd.notna(dep) else ""

    lines = [
        f"{apt_name.upper()}",
        f"Plateforme : {plat}",
        f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuits}",
        "",
        f"Bonjour {name}",
        "Bienvenue chez nous !",
        "",
        "Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre réception, "
        "nous vous demandons de bien vouloir remplir la fiche via le lien suivant :",
        f"{link}",
        "",
        "Un parking est à votre disposition sur place.",
        "",
        "Le check-in se fait à partir de 14:00 et le check-out avant 11:00. "
        "Nous serons sur place lors de votre arrivée pour vous remettre les clés.",
        "",
        "Vous trouverez des consignes à bagages dans chaque quartier, à Nice.",
        "",
        "Nous vous souhaitons un excellent voyage et nous nous réjouissons de vous rencontrer très bientôt.",
        "",
        "Annick & Charley",
        "",
        "******",
        "",
        "Welcome to our establishment!",
        "",
        "We are delighted to welcome you soon to Nice. In order to organize your reception as efficiently as possible, "
        "we kindly ask you to fill out the form at the following link:",
        f"{link}",
        "",
        "Parking is available on site.",
        "",
        "Check-in is from 2:00 p.m. and check-out is before 11:00 a.m. We will be there when you arrive to give you the keys.",
        "",
        "You will find luggage storage facilities in every district of Nice.",
        "",
        "We wish you a pleasant journey and look forward to meeting you very soon.",
        "",
        "Annick & Charley",
    ]
    return "\n".join(lines)

def _build_depart_message(r: pd.Series) -> str:
    name = str(r.get("nom_client") or "").strip()
    lines = [
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
        f"Hello {name},",
        "",
        "Thank you very much for choosing our apartment for your stay.",
        "We hope you had a great time — our door is always open if you want to come back.",
        "",
        "Annick & Charley",
    ]
    return "\n".join(lines)

def _copy_block(label: str, payload: str, key: str):
    st.text_area(label, payload, height=260, key=f"ta_{key}")
    st.caption("Sélectionnez puis copiez (Ctrl/Cmd + C).")


# ---------- SMS ----------
def vue_sms(df: pd.DataFrame, palette: dict):
    """SMS pré-arrivée (J+1) et post-départ — copier/coller + liens SMS/WhatsApp."""
    from urllib.parse import quote

    st.header("✉️ SMS & WhatsApp")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    # -------- Pré-arrivée --------
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="sms_pre_date")

    pre = df.dropna(subset=["telephone", "nom_client", "date_arrivee"]).copy()
    pre["date_arrivee"] = _to_date(pre["date_arrivee"])
    pre["date_depart"]  = _to_date(pre["date_depart"])
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (~_to_bool_series(pre["sms_envoye"]))]

    if pre.empty:
        st.info("Aucun client à contacter pour cette date.")
    else:
        pre = pre.sort_values("date_arrivee").reset_index()
        options = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        choice = st.selectbox("Client (pré-arrivée)", options=options, index=None, key="sms_pre_pick")
        if choice:
            i = int(choice.split(":")[0])
            r = pre.loc[i]

            apt_name = st.session_state.get("apt_name") or st.session_state.get("apt_slug") or "Appartement"
            use_prefill = st.checkbox("Utiliser le lien Google Form pré-rempli", value=False, key="sms_use_prefill")
            if use_prefill:
                form_link = build_form_url(
                    r.get("res_id", ""),
                    r.get("nom_client", ""),
                    r.get("telephone", ""),
                    r.get("date_arrivee", ""),
                    r.get("date_depart", "")
                )
            else:
                form_link = FORM_SHORT_URL

            msg = _build_pre_arrival_message(r, apt_name, form_link)
            _copy_block("📋 Message à envoyer", msg, key=f"pre_{i}")

            # Liens d'envoi sûrs
            e164 = _format_phone_e164(r.get("telephone", ""))
            only_digits = "".join(ch for ch in e164 if ch.isdigit())
            enc = quote(msg)

            c1, c2, c3 = st.columns(3)
            # On évite les erreurs Streamlit si e164 est vide
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            if e164:
                c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            else:
                c2.link_button("🤖 Android SMS (n° manquant)", "sms:", disabled=True)
            if only_digits:
                c3.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits}?text={enc}")
            else:
                c3.link_button("🟢 WhatsApp (n° manquant)", "https://wa.me/", disabled=True)

            if st.button("✅ Marquer 'SMS envoyé' pour ce client", key=f"pre_mark_{r['index']}"):
                try:
                    df.loc[r["index"], "sms_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    st.markdown("---")

    # -------- Post-départ --------
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="sms_post_date")

    post = df.dropna(subset=["telephone", "nom_client", "date_depart"]).copy()
    post["date_depart"] = _to_date(post["date_depart"])
    post = post[(post["date_depart"] == target_depart) & (~_to_bool_series(post["post_depart_envoye"]))]

    if post.empty:
        st.info("Aucun message post-départ à envoyer aujourd'hui.")
    else:
        post = post.sort_values("date_depart").reset_index()
        options2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        choice2 = st.selectbox("Client (post-départ)", options=options2, index=None, key="sms_post_pick")
        if choice2:
            j = int(choice2.split(":")[0])
            r2 = post.loc[j]

            msg2 = _build_depart_message(r2)
            _copy_block("📋 Message à envoyer", msg2, key=f"post_{j}")

            e164b = _format_phone_e164(r2.get("telephone", ""))
            only_digits_b = "".join(ch for ch in e164b if ch.isdigit())
            enc2 = quote(msg2)

            c1, c2, c3 = st.columns(3)
            if only_digits_b:
                c1.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits_b}?text={enc2}")
            else:
                c1.link_button("🟢 WhatsApp (n° manquant)", "https://wa.me/", disabled=True)
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            if e164b:
                c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            else:
                c3.link_button("🤖 Android SMS (n° manquant)", "sms:", disabled=True)

            if st.button("✅ Marquer 'post-départ envoyé' pour ce client", key=f"post_mark_{r2['index']}"):
                try:
                    df.loc[r2["index"], "post_depart_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")


# ---------- Export ICS ----------
def vue_export_ics(df: pd.DataFrame, palette: dict):
    st.header("📆 Export ICS (Google Calendar)")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")

    years = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique(), reverse=True)
    year = st.selectbox("Année (arrivées)", years if years else [date.today().year], index=0)
    plats = ["Tous"] + sorted(df["plateforme"].astype(str).dropna().unique())
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

    def _fmt_day(d):
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, date):
            return f"{d.year:04d}{d.month:02d}{d.day:02d}"
        d2 = pd.to_datetime(d, errors="coerce")
        return d2.strftime("%Y%m%d") if pd.notna(d2) else ""

    def _esc(s):
        if s is None:
            return ""
        return str(s).replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Villa Tobias//Reservations//FR", "CALSCALE:GREGORIAN"]

    for _, r in data.iterrows():
        dt_a = pd.to_datetime(r.get("date_arrivee"), errors="coerce")
        dt_d = pd.to_datetime(r.get("date_depart"), errors="coerce")
        if pd.isna(dt_a) or pd.isna(dt_d):
            continue

        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
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
            f"DTSTART;VALUE=DATE:{_fmt_day(dt_a)}",
            f"DTEND;VALUE=DATE:{_fmt_day(dt_d)}",
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


# ---------- Google Sheet (intégration simple via iframe de votre Form) ----------
def vue_google_sheet(df: pd.DataFrame, palette: dict):
    st.header("📝 Fiche d'arrivée / Google Form")
    print_buttons()
    st.caption("Le SMS pré-arrivée peut contenir le lien **pré-rempli** ou le **lien court**.")
    # Affiche le formulaire Google (lecture seule) dans l'app
    st.markdown(
        f'<iframe src="{GOOGLE_FORM_BASE}" width="100%" height="900" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )


# ---------- Clients ----------
def vue_clients(df: pd.DataFrame, palette: dict):
    st.header("👥 Liste des clients")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucun client.")
        return

    clients = df[["nom_client", "telephone", "email", "plateforme", "res_id"]].copy()
    for c in clients.columns:
        clients[c] = clients[c].astype(str).str.strip().replace({"nan": ""})

    clients = clients.loc[clients["nom_client"] != ""].drop_duplicates().copy()
    clients["pays"] = clients["telephone"].apply(_phone_country).replace("", "Inconnu")

    cols = ["nom_client", "pays", "telephone", "email", "plateforme", "res_id"]
    st.dataframe(clients.reindex(columns=cols).sort_values(by="nom_client", kind="stable"), use_container_width=True)


# ---------- ID ----------
def vue_id(df: pd.DataFrame, palette: dict):
    st.header("🆔 Identifiants des réservations")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    tbl = df[["res_id", "nom_client", "telephone", "email", "plateforme"]].copy()
    for c in tbl.columns:
        tbl[c] = tbl[c].astype(str).str.strip().replace({"nan": ""})

    tbl = tbl.dropna(subset=["res_id"])
    tbl = tbl[tbl["res_id"] != ""].drop_duplicates()
    tbl["pays"] = tbl["telephone"].apply(_phone_country).replace("", "Inconnu")

    st.dataframe(tbl[["res_id", "nom_client", "pays", "telephone", "email", "plateforme"]], use_container_width=True)


# ============================== PARTIE 5/5 — SMS, INDICATEURS PAYS, PARAMÈTRES, MAIN ==============================

# --- petits utilitaires d'UI sûrs (évite les erreurs de st.link_button selon versions)
def _safe_link(label: str, url: str, key: str = ""):
    if not url:
        return
    lab = label.replace("|", "│")
    st.markdown(
        f"[{lab}]({url})",
        unsafe_allow_html=True,
    )

# --- fallbacks si les builders de message n'existent pas déjà (évite NameError) ---
if "_build_pre_arrival_message" not in globals():
    def _build_pre_arrival_message(r: pd.Series, apt_name: str, link: str) -> str:
        try:
            arr = pd.to_datetime(r.get("date_arrivee"), errors="coerce")
            dep = pd.to_datetime(r.get("date_depart"), errors="coerce")
        except Exception:
            arr, dep = None, None
        arr_txt = arr.strftime("%d/%m/%Y") if pd.notna(arr) else ""
        dep_txt = dep.strftime("%d/%m/%Y") if pd.notna(dep) else ""
        nuits = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
        plat  = str(r.get("plateforme") or "—")
        name  = str(r.get("nom_client") or "").strip()
        msg = (
            f"{apt_name.upper()}\n"
            f"Plateforme : {plat}\n"
            f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuits}\n\n"
            f"Bonjour {name}\n"
            "Bienvenue chez nous !\n\n"
            "Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre réception, "
            "merci de remplir la fiche au lien suivant :\n"
            f"{link}\n\n"
            "Un parking est à votre disposition sur place.\n\n"
            "Check-in à partir de 14:00, check-out avant 11:00.\n\n"
            "******\n\n"
            "Welcome to our establishment!\n\n"
            "Please fill in this form before arrival:\n"
            f"{link}\n\n"
            "Check-in from 2:00 p.m., check-out before 11:00 a.m.\n\n"
            "Annick & Charley"
        )
        return msg

if "_build_depart_message" not in globals():
    def _build_depart_message(r: pd.Series) -> str:
        name = str(r.get("nom_client") or "").strip()
        return (
            f"Bonjour {name},\n\n"
            "Merci d'avoir choisi notre appartement pour votre séjour.\n"
            "Nous espérons que tout s'est bien passé.\n\n"
            "Au plaisir de vous accueillir à nouveau.\n\n"
            "Annick & Charley\n\n"
            f"Hello {name},\n\n"
            "Thank you for your stay — you're always welcome back!\n\n"
            "Annick & Charley"
        )

# ---------------- SMS ----------------
def vue_sms(df: pd.DataFrame, palette: dict):
    """SMS pré-arrivée (J+1) et post-départ (J0) : copier/coller + liens SMS/WhatsApp (compatibles toutes versions)."""
    from urllib.parse import quote

    apt_name = st.session_state.get("apt_name") or st.session_state.get("apt_slug") or "APPARTEMENT"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation disponible.")
        return

    dfx = ensure_schema(df).copy()
    dfx["date_arrivee"] = _to_date(dfx["date_arrivee"])
    dfx["date_depart"]  = _to_date(dfx["date_depart"])

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

            # Choix du lien (pré-rempli ou lien court)
            use_prefill = st.checkbox("Utiliser le lien Google Form pré-rempli", value=False)
            if use_prefill:
                form_link = build_form_url(
                    r.get("res_id", ""),
                    r.get("nom_client", ""),
                    r.get("telephone", ""),
                    r.get("date_arrivee", ""),
                    r.get("date_depart", "")
                )
            else:
                form_link = FORM_SHORT_URL

            msg = _build_pre_arrival_message(r, apt_name, form_link)

            st.text_area("📋 Copier le message", value=msg, height=360, key="pre_msg")
            e164 = _format_phone_e164(r.get("telephone", ""))
            only_digits = "".join(ch for ch in e164 if ch.isdigit())
            enc = quote(msg)

            c1, c2, c3 = st.columns(3)
            _safe_link("📲 iPhone SMS", f"sms:&body={enc}", key="pre_ios")
            _safe_link("🤖 Android SMS", f"sms:{e164}?body={enc}", key="pre_android")
            _safe_link("🟢 WhatsApp", f"https://wa.me/{only_digits}?text={enc}", key="pre_wa")

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
            msg2 = _build_depart_message(r2)

            st.text_area("📋 Copier le message", value=msg2, height=280, key="post_msg")
            e164b = _format_phone_e164(r2.get("telephone", ""))
            only_digits_b = "".join(ch for ch in e164b if ch.isdigit())
            enc2 = quote(msg2)

            c1, c2, c3 = st.columns(3)
            _safe_link("🟢 WhatsApp", f"https://wa.me/{only_digits_b}?text={enc2}", key="post_wa")
            _safe_link("📲 iPhone SMS", f"sms:&body={enc2}", key="post_ios")
            _safe_link("🤖 Android SMS", f"sms:{e164b}?body={enc2}", key="post_android")

            if st.button("✅ Marquer 'post-départ envoyé' pour ce client", key="post_mark_sent"):
                try:
                    df.loc[r2["index"], "post_depart_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

# ---------------- INDICATEURS / INDICATIFS PAYS ----------------
def _indicatifs_path() -> str:
    # Chemin global si défini dans PART 1, sinon défaut local.
    return globals().get("INDICATIFS_CSV", "indicatifs_pays.csv")

def _load_indicatifs_df() -> pd.DataFrame:
    """Charge le CSV d'indicatifs pays (crée un mini-squelette si absent)."""
    path = _indicatifs_path()
    if not os.path.exists(path):
        base = pd.DataFrame(
            [
                {"code": "FR", "country": "France", "dial": "+33", "flag": "🇫🇷"},
                {"code": "GB", "country": "Royaume-Uni", "dial": "+44", "flag": "🇬🇧"},
                {"code": "ES", "country": "Espagne", "dial": "+34", "flag": "🇪🇸"},
            ]
        )
        try:
            base.to_csv(path, index=False, encoding="utf-8")
        except Exception:
            return base
    try:
        return pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=["code", "country", "dial", "flag"])

def _save_indicatifs_df(df_in: pd.DataFrame) -> bool:
    """Valide et sauvegarde le CSV des indicatifs."""
    try:
        df = df_in.copy()
        need = ["code", "country", "dial", "flag"]
        for c in need:
            if c not in df.columns:
                df[c] = ""
        df = df[need]

        df["code"] = df["code"].astype(str).str.strip().str.upper()
        df["country"] = df["country"].astype(str).str.strip()
        df["dial"] = df["dial"].astype(str).str.strip()
        df["flag"] = df["flag"].astype(str).str.strip()

        df = df[df["code"] != ""]
        df = df.drop_duplicates(subset=["code"], keep="first")
        df.loc[df["dial"] != "", "dial"] = "+" + df["dial"].str.lstrip("+").str.strip()

        df.to_csv(_indicatifs_path(), index=False, encoding="utf-8")
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde des indicatifs : {e}")
        return False

def vue_indicatifs(df: pd.DataFrame, palette: dict):
    """Édition et rechargement des indicatifs pays (code, country, dial, flag)."""
    apt_name = st.session_state.get("apt_name") or st.session_state.get("apt_slug") or "—"
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
            "code": st.column_config.TextColumn("Code (ISO2)"),
            "country": st.column_config.TextColumn("Pays"),
            "dial": st.column_config.TextColumn("Indicatif (+NN)"),
            "flag": st.column_config.TextColumn("Drapeau (emoji)"),
        },
        key="indicatifs_editor",
    )

    c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
    if c1.button("💾 Enregistrer", key="btn_save_indicatifs"):
        if _save_indicatifs_df(edited):
            st.success("Indicatifs sauvegardés ✅")

    if c2.button("🔄 Recharger depuis le disque", key="btn_reload_indicatifs"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()

    if c3.button("↩️ Restaurer FR/GB/ES (mini)", key="btn_restore_min_indicatifs"):
        mini = pd.DataFrame(
            [
                {"code": "FR", "country": "France", "dial": "+33", "flag": "🇫🇷"},
                {"code": "GB", "country": "Royaume-Uni", "dial": "+44", "flag": "🇬🇧"},
                {"code": "ES", "country": "Espagne", "dial": "+34", "flag": "🇪🇸"},
            ]
        )
        if _save_indicatifs_df(mini):
            st.success("Mini-jeu de données restauré ✅")
            try:
                st.rerun()
            except Exception:
                st.experimental_rerun()

# ---------------- PARAMÈTRES ----------------
def vue_settings(df: pd.DataFrame, palette: dict):
    """Sauvegarde / restauration des données + cache + outil apartments.csv."""
    apt_name = st.session_state.get("apt_name") or st.session_state.get("apt_slug") or "—"
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
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()

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
            with open("apartments.csv", "w", encoding="utf-8", newline="") as f:
                f.write(txt.strip() + "\n")
            st.cache_data.clear()
            st.success("apartments.csv écrasé ✅ — rechargement…")
            try:
                st.rerun()
            except Exception:
                st.experimental_rerun()
        except Exception as e:
            st.error(f"Impossible d'écrire apartments.csv : {e}")


# ----------------------- APARTMENT SELECTOR (SIDEBAR) -----------------------
def apartment_selector_sidebar():
    """Sélecteur robuste dans la barre latérale + diagnostics.
       Utilise un bouton 'Se connecter' explicite et un bouton 'Changer'."""
    st.sidebar.subheader("🔐 Appartement")

    # 1) S'assurer que apartments.csv existe (mini contenu par défaut)
    apt_path = "apartments.csv"
    if not os.path.exists(apt_path):
        default_csv = (
            "slug,name,password_hash\n"
            "villa-tobias,Villa Tobias,\n"
            "le-turenne,Le Turenne,\n"
        )
        try:
            with open(apt_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(default_csv)
        except Exception as e:
            st.sidebar.error(f"Impossible de créer apartments.csv : {e}")

    # 2) Charger les appartements
    df_apts = _load_apartments_csv(apt_path)
    if df_apts.empty:
        st.sidebar.error("Aucun appartement trouvé dans apartments.csv")
        st.sidebar.caption("Utilise l’outil ci-dessous pour l’écrire.")
        _force_write_apartments_csv(key_prefix="sidebar")
        return  # stop ici (main vérifiera ensuite l’état)

    # 3) Sélecteur + boutons
    options_labels = [f"{row['name']} ({row['slug']})" for _, row in df_apts.iterrows()]
    # Préselection : si déjà connecté, pointer l’option correspondante
    def_idx = 0
    current_slug = st.session_state.get("apt_slug")
    if current_slug:
        for i, (_, r) in enumerate(df_apts.iterrows()):
            if r["slug"] == current_slug:
                def_idx = i
                break

    label_pick = st.sidebar.selectbox("Choisir un appartement", options=options_labels, index=def_idx, key="apt_select_label")
    picked_slug = label_pick.split("(")[-1].rstrip(")").strip()
    picked_row = df_apts[df_apts["slug"] == picked_slug].iloc[0]
    picked_name = picked_row["name"]

    colA, colB = st.sidebar.columns(2)
    if colA.button("Se connecter", use_container_width=True, key="btn_connect_appt"):
        # Connexion explicite
        st.session_state["apt_slug"] = picked_slug
        st.session_state["apt_name"] = picked_name
        _set_current_apartment(picked_slug)  # met à jour CSV_RESERVATIONS / CSV_PLATEFORMES
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    if colB.button("Changer", use_container_width=True, key="btn_logout_appt"):
        # Déconnexion / retour au choix
        st.session_state.pop("apt_slug", None)
        st.session_state.pop("apt_name", None)
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    # 4) Diagnostic rapide
    with st.sidebar.expander("🔎 Diagnostic appartement", expanded=False):
        st.write("Session :", {
            "apt_slug": st.session_state.get("apt_slug"),
            "apt_name": st.session_state.get("apt_name"),
            "CSV_RESERVATIONS": CSV_RESERVATIONS,
            "CSV_PLATEFORMES": CSV_PLATEFORMES,
        })
        st.dataframe(df_apts, use_container_width=True)





# ------------------------------- MAIN 
 main():
    # Reset cache via URL ?clear=1
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1", "true", "True", "yes"):
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
    apt_name = st.session_state.get("apt_name") or st.session_state.get("apt_slug") or "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    # Chargement des données spécifiques à l'appartement
    df, palette_loaded = charger_donnees(_files_cache_key())
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