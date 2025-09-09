# ============================== [1] IMPORTS & CONFIG ==============================
# (PATCH UNIT: 1)
# - Imports standards
# - set_page_config
# - Hard clear cache au chargement
# - Constantes & URLs

# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib, json
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO

st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# HARD CLEAR (sécurisé) : purger cache au chargement du script
try:
    try: st.cache_data.clear()
    except Exception: pass
    try: st.cache_resource.clear()
    except Exception: pass
except Exception:
    pass

CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# Liens Google
FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"


# ============================== [2] STYLE & UI HELPERS ==============================
# (PATCH UNIT: 2)
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
          html, body, [data-testid="stAppViewContainer"] {{
            background: {bg}; color: {fg};
          }}
          [data-testid="stSidebar"] {{
            background: {side}; border-right: 1px solid {border};
          }}
          .glass {{
            background: {"rgba(255,255,255,0.65)" if light else "rgba(255,255,255,0.06)"};
            border: 1px solid {border}; border-radius: 12px; padding: 12px; margin: 8px 0;
          }}
          .chip {{
            display:inline-block; background:{chip_bg}; color:{chip_fg};
            padding:6px 10px; border-radius:12px; margin:4px 6px; font-size:0.86rem
          }}
          .kpi-line strong {{ font-size:0.98rem; }}
          /* Calendar grid */
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; margin-top:8px; }}
          .cal-cell {{
            border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px;
            position:relative; overflow:hidden; background:{"#fff" if light else "#0b0d12"};
          }}
          .cal-cell.outside {{ opacity:.45; }}
          .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
          .resa-pill {{
            padding:4px 6px; border-radius:6px; font-size:.85rem; margin-top:22px;
            color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
          }}
          .cal-header {{
            display:grid; grid-template-columns: repeat(7, 1fr);
            font-weight:700; opacity:.8; margin-top:10px;
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)


# ============================== [3] LECTURE CSV ROBUSTE & CONVERSIONS ==============================
# (PATCH UNIT: 3)
def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    """Lit un CSV en testant ; , \t |. Enlève BOM. Retourne DataFrame (dtype=str)."""
    if raw is None: 
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3:
                return df
        except Exception:
            continue
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _to_bool_series(s: pd.Series) -> pd.Series:
    if s is None: 
        return pd.Series([], dtype=bool)
    return s.astype(str).str.strip().str.lower().isin(["true", "1", "oui", "vrai", "yes", "y", "t"])

def _to_num(s: pd.Series) -> pd.Series:
    if s is None: 
        return pd.Series([], dtype="float64")
    sc = (
        s.astype(str)
         .str.replace("€", "", regex=False)
         .str.replace(" ", "", regex=False)
         .str.replace(",", ".", regex=False)
         .str.strip()
    )
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    """Accepte JJ/MM/AAAA, AAAA-MM-JJ, JJ-MM-AAAA, etc., retourne .dt.date"""
    if s is None:
        return pd.Series([], dtype="object")
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date


# ============================== [4] NORMALISATION SCHEMA ==============================
# (PATCH UNIT: 4)
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid","AAAA","MM"
]

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Normalise le DataFrame pour qu'il respecte BASE_COLS + calcule champs dérivés."""
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Compat noms
    rename_map = {
        'Payé': 'paye', 'Client': 'nom_client', 'Plateforme': 'plateforme',
        'Arrivée': 'date_arrivee', 'Départ': 'date_depart', 'Nuits': 'nuitees',
        'Brut (€)': 'prix_brut'
    }
    df.rename(columns=rename_map, inplace=True)

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)

    # Numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Recalcul nuitees si possible
    mask_ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0)
    except Exception:
        pass

    # Prix net / charges / base / %
    df["prix_net"] = (_to_num(df["prix_brut"]) - _to_num(df["commissions"]) - _to_num(df["frais_cb"])).fillna(0.0)
    df["charges"]  = (_to_num(df["prix_brut"]) - _to_num(df["prix_net"])).fillna(0.0)
    df["base"]     = (_to_num(df["prix_net"]) - _to_num(df["menage"]) - _to_num(df["taxes_sejour"])).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(_to_num(df["prix_brut"])>0, (_to_num(df["charges"]) / _to_num(df["prix_brut"]) * 100), 0)
    df["%"] = pd.to_numeric(pct, errors="coerce").fillna(0.0)

    # AAAA / MM
    da_all = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = pd.to_numeric(da_all.dt.year, errors="coerce")
    df["MM"]   = pd.to_numeric(da_all.dt.month, errors="coerce")

    # IDs stables
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid, "ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # Nettoyage strings clés
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = df[c].astype(str).replace({"nan": "", "None": ""}).str.strip()

    return df[BASE_COLS]


# ============================== [5] CHARGEMENT & SAUVEGARDE ==============================
# (PATCH UNIT: 5)
@st.cache_data
def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _merge_emails_from_sheet(df: pd.DataFrame) -> pd.DataFrame:
    """Essaie de récupérer les emails depuis la feuille publiée (si accessible) pour combler les manquants."""
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
    except Exception:
        return df  # pas d'accès, on laisse tel quel

    # Heuristiques colonnes
    email_cols = [c for c in rep.columns if "mail" in c.lower() or "email" in c.lower()]
    phone_cols = [c for c in rep.columns if any(k in c.lower() for k in ["phone","téléphone","telephone","tel","mobile"])]
    name_cols  = [c for c in rep.columns if any(k in c.lower() for k in ["nom","name"])]

    if not email_cols:
        return df

    rep2 = rep.copy()
    rep2["_email_"] = rep2[email_cols[0]].astype(str).str.strip()

    # Mapping par téléphone si possible
    if phone_cols:
        rep2["_tel_"] = rep2[phone_cols[0]].astype(str).str.replace(r"\D", "", regex=True).str.lstrip("0")
        tel_email = (rep2[rep2["_email_"]!=""]
                     .groupby("_tel_")["_email_"].last().to_dict())
        df_tel = df["telephone"].astype(str).str.replace(r"\D","",regex=True).str.lstrip("0")
        mask_need = df["email"].astype(str).str.strip().eq("") & df_tel.notna()
        df.loc[mask_need, "email"] = df_tel.map(tel_email)
    # Sinon mapping par nom
    elif name_cols:
        rep2["_nom_"] = rep2[name_cols[0]].astype(str).str.strip().str.lower()
        name_email = (rep2[rep2["_email_"]!=""]
                      .groupby("_nom_")["_email_"].last().to_dict())
        names = df["nom_client"].astype(str).str.strip().str.lower()
        mask_need = df["email"].astype(str).str.strip().eq("") & names.notna()
        df.loc[mask_need, "email"] = names.map(name_email)

    df["email"] = df["email"].fillna("").astype(str)
    return df

@st.cache_data
def charger_donnees():
    # 1) CSV résa
    raw = _load_file_bytes(CSV_RESERVATIONS)
    if raw is not None:
        base_df = _detect_delimiter_and_read(raw)
    else:
        base_df = pd.DataFrame()

    df = ensure_schema(base_df)

    # 1.b) compléter emails depuis la feuille publiée (best-effort)
    try:
        df = _merge_emails_from_sheet(df)
    except Exception:
        pass

    # 2) Palette de plateformes
    rawp = _load_file_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if set(["plateforme","couleur"]).issubset(set(pal_df.columns)):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception:
            pass

    return df, palette

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        df2 = ensure_schema(df)
        out = df2.copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde CSV : {e}")
        return False


# ============================== [6] UTILITAIRES DIVERS ==============================
# (PATCH UNIT: 6)
def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

def _sum_safe(data: pd.DataFrame, col: str) -> float:
    return float(pd.to_numeric(data.get(col, 0), errors="coerce").fillna(0).sum())


# ============================== [7] VUES — ACCUEIL ==============================
# (PATCH UNIT: 7)
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfn = ensure_schema(df)
    arr = dfn[dfn["date_arrivee"] == today][["nom_client","telephone","plateforme"]]
    dep = dfn[dfn["date_depart"]  == today][["nom_client","telephone","plateforme"]]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        if arr.empty:
            st.info("Aucune arrivée aujourd'hui.")
        else:
            st.dataframe(arr, use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        if dep.empty:
            st.info("Aucun départ aujourd'hui.")
        else:
            st.dataframe(dep, use_container_width=True)


# ============================== [8] VUES — RÉSERVATIONS ==============================
# (PATCH UNIT: 8)
def vue_reservations(df, palette):
    st.header("📋 Réservations")

    if not isinstance(df, pd.DataFrame) or df.empty:
        st.info("Aucune réservation.")
        return

    dfn = ensure_schema(df)

    years_ser  = pd.to_numeric(dfn.get("AAAA", pd.Series(dtype="float64")), errors="coerce")
    months_ser = pd.to_numeric(dfn.get("MM",   pd.Series(dtype="float64")), errors="coerce")

    years_unique = (
        sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True)
        if years_ser is not None and not years_ser.dropna().empty else []
    )
    months_unique = (
        sorted(months_ser.dropna().astype(int).unique().tolist())
        if months_ser is not None and not months_ser.dropna().empty else list(range(1, 13))
    )
    plats_unique = sorted(
        dfn.get("plateforme", pd.Series([], dtype="object"))
           .astype(str).str.strip().replace({"": np.nan})
           .dropna().unique().tolist()
    )

    years  = ["Toutes"] + years_unique
    months = ["Tous"] + months_unique
    plats  = ["Toutes"] + plats_unique

    c1, c2, c3 = st.columns(3)
    sel_year  = c1.selectbox("Année", years, index=0)
    sel_month = c2.selectbox("Mois", months, index=0)
    sel_plat  = c3.selectbox("Plateforme", plats, index=0)

    data = dfn.copy()
    if sel_year != "Toutes":
        yy = pd.to_numeric(data["AAAA"], errors="coerce").fillna(-1).astype(int)
        data = data[yy == int(sel_year)]
    if sel_month != "Tous":
        mm = pd.to_numeric(data["MM"], errors="coerce").fillna(-1).astype(int)
        data = data[mm == int(sel_month)]
    if sel_plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(sel_plat).strip()]

    # KPI compacts
    brut    = _sum_safe(data, "prix_brut")
    net     = _sum_safe(data, "prix_net")
    base    = _sum_safe(data, "base")
    charges = _sum_safe(data, "charges")
    nuits   = int(pd.to_numeric(data.get("nuitees", 0), errors="coerce").fillna(0).sum())
    adr     = (net / nuits) if nuits > 0 else 0.0

    kpi_html = f"""
    <div class='glass kpi-line'>
      <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
      <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
      <span class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></span>
      <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
      <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
      <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
    </div>
    """.replace(",", " ")
    st.markdown(kpi_html, unsafe_allow_html=True)
    st.markdown("---")

    # Tri par date d’arrivée si dispo
    if "date_arrivee" in data.columns:
        order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
        data = data.loc[order]

    st.dataframe(data, use_container_width=True)


# ============================== [9] VUES — AJOUTER / MODIFIER ==============================
# (PATCH UNIT: 9)
def vue_ajouter(df, palette):
    st.header("➕ Ajouter une réservation")
    with st.form("form_add", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel = st.text_input("Téléphone")
            arr = st.date_input("Arrivée", date.today())
            dep = st.date_input("Départ", date.today()+timedelta(days=1))
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

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer")
    if df.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client','')} ({r.get('date_arrivee','')})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not sel: return
    idx = int(sel.split(":")[0])
    original_idx = df_sorted.loc[idx, "index"]
    row = df.loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get("nom_client","") or "")
            email = st.text_input("Email", value=row.get("email","") or "")
            tel = st.text_input("Téléphone", value=row.get("telephone","") or "")
            arrivee = st.date_input("Arrivée", value=row.get("date_arrivee"))
            depart  = st.date_input("Départ", value=row.get("date_depart"))
        with c2:
            palette_keys = list(palette.keys())
            plat_idx = palette_keys.index(row.get("plateforme")) if row.get("plateforme") in palette_keys else 0
            plat = st.selectbox("Plateforme", options=palette_keys, index=plat_idx)
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=float(row.get("prix_brut") or 0))
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=float(row.get("commissions") or 0))
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=float(row.get("frais_cb") or 0))
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=float(row.get("menage") or 0))
            taxes  = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=float(row.get("taxes_sejour") or 0))

        b1, b2 = st.columns([0.7, 0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            for k, v in {
                "nom_client": nom, "email": email, "telephone": tel, "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye, "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes
            }.items():
                df.loc[original_idx, k] = v
            df2 = ensure_schema(df)
            if sauvegarder_donnees(df2):
                st.success("Modifié ✅"); st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé."); st.rerun()


# ============================== [10] VUES — PLATEFORMES ==============================
# (PATCH UNIT: 10)
def vue_plateformes(df, palette):
    st.header("🎨 Plateformes & couleurs")
    base = pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    c1, c2 = st.columns([0.6,0.4])
    if c1.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette enregistrée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
    if c2.button("↩️ Restaurer palette par défaut"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette par défaut restaurée."); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")





# ============================== §11 — VUE_SMS (pré-arrivée & post-départ) ==============================
def _safe_str(x):
    try:
        if pd.isna(x):
            return ""
    except Exception:
        pass
    return str(x or "").strip()

def _safe_int(x, default=0):
    try:
        v = pd.to_numeric(x, errors="coerce")
        if pd.isna(v):
            return default
        return int(v)
    except Exception:
        return default

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D", "", _safe_str(phone))
    if not s:
        return ""
    # France par défaut
    if s.startswith("33"):
        return "+" + s
    if s.startswith("0"):
        return "+33" + s[1:]
    return "+" + s

def _to_date_col(v):
    # Accepte JJ/MM/AAAA, AAAA-MM-JJ, etc.
    ser = pd.to_datetime(v, errors="coerce", dayfirst=True)
    # Si beaucoup NaT, retente YMD strict
    if ser.isna().mean() > 0.7:
        ser2 = pd.to_datetime(v, errors="coerce", format="%Y-%m-%d")
        ser = ser.fillna(ser2)
    return ser.dt.date

def _copy_preview(label: str, payload: str, key: str):
    # Pas de JS (certains environnements le bloquent) — on laisse copier manuellement.
    st.text_area(label, payload, height=200, key=f"ta_{key}")
    st.caption("Sélectionne le texte puis copie (Ctrl/Cmd+C).")

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # --------- PRÉ-ARRIVÉE (J+1) ---------
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    try:
        target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    except Exception:
        target_arrivee = date.today() + timedelta(days=1)

    df_pre = df.copy()
    # Sécurisation types
    if "date_arrivee" in df_pre.columns:
        df_pre["date_arrivee"] = _to_date_col(df_pre["date_arrivee"])
    if "date_depart" in df_pre.columns:
        df_pre["date_depart"] = _to_date_col(df_pre["date_depart"])

    for col in ["telephone","nom_client","plateforme","nuitees","sms_envoye"]:
        if col not in df_pre.columns:
            df_pre[col] = None

    df_pre["sms_envoye"] = df_pre["sms_envoye"].astype(str).str.lower().isin(
        ["true","1","oui","yes","vrai","y","t"]
    )

    mask_ok = (
        df_pre["date_arrivee"].notna()
        & df_pre["date_arrivee"].eq(target_arrivee)
        & df_pre["nom_client"].astype(str).str.strip().ne("")
        & df_pre["telephone"].astype(str).str.strip().ne("")
        & (~df_pre["sms_envoye"])
    )
    pre = df_pre.loc[mask_ok].copy()

    if pre.empty:
        st.info("Aucun client à contacter pour la date choisie (ou déjà marqué 'SMS envoyé').")
    else:
        pre["_rowid"] = pre.index
        pre = pre.sort_values(["date_arrivee","nom_client"]).reset_index(drop=True)
        options = [f"{i}: {_safe_str(r['nom_client'])} ({_safe_str(r['telephone'])})" for i, r in pre.iterrows()]
        choice = st.selectbox("Client (pré-arrivée)", options=options, index=None, key="pre_select")

        if choice:
            i = int(choice.split(":")[0])
            r = pre.loc[i]

            # Construction message complet FR+EN
            nom = _safe_str(r.get("nom_client"))
            tel = _safe_str(r.get("telephone"))
            plat = _safe_str(r.get("plateforme")) or "N/A"
            da = r.get("date_arrivee")
            dd = r.get("date_depart")
            nuitees = _safe_int(r.get("nuitees"))

            arr_txt = da.strftime("%d/%m/%Y") if isinstance(da, date) else ""
            dep_txt = dd.strftime("%d/%m/%Y") if isinstance(dd, date) else ""

            msg = (
                "VILLA TOBIAS\n"
                f"Plateforme : {plat}\n"
                f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuitees}\n\n"
                f"Bonjour {nom}\nTéléphone : {tel}\n\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous acceuillir bientot a Nice. Aussi afin d'organiser au mieux votre reception "
                "merci de nous indiquer votre heure d'arrivee.\n\n"
                "Sachez qu'une place de parking vous est allouee en cas de besoin.\n\n"
                "Le check-in se fait a partir de 14:00 h et le check-out avant 11:00 h.\n\n"
                "Vous trouverez des consignes a bagages dans chaque quartier a Nice.\n\n"
                "Nous vous souhaitons un excellent voyage et nous nous rejouissons de vous rencontrer tres bientot.\n\n"
                "Welcome to our home!\n\n"
                "We are delighted to welcome you soon to Nice. In order to organize your reception as best as possible, "
                "please let us know your arrival time.\n\n"
                "Please note that a parking space is available if needed.\n\n"
                "Check-in is from 2:00 p.m. and check-out is before 11:00 a.m.\n\n"
                "You will find luggage storage facilities in every neighborhood in Nice.\n\n"
                "We wish you a wonderful trip and look forward to meeting you very soon.\n\n"
                "Annick & Charley\n\n"
                "Merci de remplir la fiche d'arrivee / Please fill out the arrival form :\n"
                f"{FORM_SHORT_URL}"
            )

            _copy_preview("Prévisualisation (pré-arrivée)", msg, key=f"pre_{i}")
            enc = quote(msg)
            e164 = _format_phone_e164(tel)
            wa_num = re.sub(r"\D", "", e164)

            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa_num}?text={enc}")

            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                try:
                    df.loc[r["_rowid"], "sms_envoye"] = True
                    if sauvegarder_donnees(ensure_schema(df)):
                        st.success("Marqué ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    st.markdown("---")

    # --------- POST-DÉPART (J0) ---------
    st.subheader("📤 Post-départ (départs du jour)")
    try:
        target_depart = st.date_input("Départs du", date.today(), key="post_date")
    except Exception:
        target_depart = date.today()

    df_post = df.copy()
    if "date_depart" in df_post.columns:
        df_post["date_depart"] = _to_date_col(df_post["date_depart"])
    if "nom_client" not in df_post.columns: df_post["nom_client"] = None
    if "telephone" not in df_post.columns: df_post["telephone"] = None
    if "post_depart_envoye" not in df_post.columns: df_post["post_depart_envoye"] = False

    df_post["post_depart_envoye"] = df_post["post_depart_envoye"].astype(str).str.lower().isin(
        ["true","1","oui","yes","vrai","y","t"]
    )

    mask_pd = (
        df_post["date_depart"].notna()
        & df_post["date_depart"].eq(target_depart)
        & df_post["nom_client"].astype(str).str.strip().ne("")
        & df_post["telephone"].astype(str).str.strip().ne("")
        & (~df_post["post_depart_envoye"])
    )
    post = df_post.loc[mask_pd].copy()

    if post.empty:
        st.info("Aucun message post-départ à envoyer.")
    else:
        post["_rowid"] = post.index
        post = post.sort_values(["date_depart","nom_client"]).reset_index(drop=True)
        options2 = [f"{i}: {_safe_str(r['nom_client'])} — départ {_safe_str(r['date_depart'])}" for i, r in post.iterrows()]
        choice2 = st.selectbox("Client (post-départ)", options=options2, index=None, key="post_select")

        if choice2:
            j = int(choice2.split(":")[0])
            r2 = post.loc[j]
            name = _safe_str(r2.get("nom_client"))
            tel2 = _safe_str(r2.get("telephone"))

            msg2 = (
                f"Bonjour {name},\n\n"
                "Un grand merci d'avoir choisi notre appartement pour votre sejour.\n\n"
                "Nous esperons que vous avez passe un moment aussi agreable que celui que nous avons eu a vous accueillir.\n\n"
                "Si l'envie vous prend de revenir explorer encore un peu notre ville, sachez que notre porte vous sera toujours grande ouverte.\n\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n"
                f"\nHello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n\n"
                "We hope you had as enjoyable a time as we did hosting you.\n\n"
                "If you feel like coming back to explore our city a little more, know that our door will always be open to you.\n\n"
                "We look forward to welcoming you back.\n\n"
                "Annick & Charley"
            )

            _copy_preview("Prévisualisation (post-départ)", msg2, key=f"post_{j}")
            enc2 = quote(msg2)
            e164b = _format_phone_e164(tel2)
            wa_num2 = re.sub(r"\D", "", e164b)

            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wa_num2}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")

            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                try:
                    df.loc[r2["_rowid"], "post_depart_envoye"] = True
                    if sauvegarder_donnees(ensure_schema(df)):
                        st.success("Marqué ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")


# ============================== §12 — EXPORT ICS (Google Calendar) ==============================
def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    if df is None or df.empty:
        st.info("Aucune réservation."); 
        return

    years = pd.to_numeric(df.get("AAAA"), errors="coerce").dropna().astype(int).sort_values(ascending=False).unique().tolist()
    if not years:
        st.info("Aucune année détectée."); 
        return

    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df.get("plateforme", pd.Series([], dtype=str)).dropna().astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = df[pd.to_numeric(df["AAAA"], errors="coerce")==year].copy()
    if plat!="Tous":
        data = data[data["plateforme"].astype(str).str.strip()==plat]

    if data.empty:
        st.warning("Rien à exporter."); 
        return

    # Compléter les UID manquants
    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if miss.any():
        data.loc[miss, "ical_uid"] = data.loc[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _fmt(d): 
        if not isinstance(d, (date, datetime)): return ""
        if isinstance(d, datetime): d = d.date()
        return f"{d.year:04d}{d.month:02d}{d.day:02d}"

    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r.get("date_arrivee"), r.get("date_depart")
        # Normalise en date
        try:
            da = pd.to_datetime(da, errors="coerce").date()
            dd = pd.to_datetime(dd, errors="coerce").date()
        except Exception:
            da, dd = None, None
        if not (isinstance(da, date) and isinstance(dd, date)): 
            continue

        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        platv = r.get("plateforme")
        if platv: 
            summary += f" ({platv})"

        nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce") if r.get("nuitees") is not None else 0)
        prixb   = float(pd.to_numeric(r.get("prix_brut"), errors="coerce") if r.get("prix_brut") is not None else 0.0)

        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {nuitees}",
            f"Prix brut: {prixb:.2f} €",
            f"res_id: {r.get('res_id','')}",
        ])

        lines += [
            "BEGIN:VEVENT",
            f"UID:{r['ical_uid']}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt(da)}",
            f"DTEND;VALUE=DATE:{_fmt(dd)}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")

    ics = "\r\n".join(lines) + "\r\n"
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"),
                       file_name=f"reservations_{year}.ics", mime="text/calendar")


# ============================== §13 — GOOGLE FORM / SHEET ==============================
def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée / Google Sheet")
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")

    # Formulaire intégré (HTML pur pour compat max)
    st.markdown(
        f'<iframe src="{GOOGLE_FORM_URL}" width="100%" height="900" frameborder="0"></iframe>',
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
        # Option pour masquer les emails
        show_email = st.checkbox("Afficher les colonnes d'email (si présentes)", value=False)
        if not show_email:
            mask_cols = [c for c in rep.columns if "mail" in c.lower() or "email" in c.lower()]
            rep_display = rep.drop(columns=mask_cols, errors="ignore")
        else:
            rep_display = rep

        st.dataframe(rep_display, use_container_width=True)

        # Bouton pour fusionner emails reçus dans df (si une colonne email existe)
        # Heuristique: nom/telephone/email présents dans la feuille
        cand_name_cols = [c for c in rep.columns if "nom" in c.lower()]
        cand_tel_cols  = [c for c in rep.columns if "tel" in c.lower() or "phone" in c.lower()]
        cand_mail_cols = [c for c in rep.columns if "mail" in c.lower() or "email" in c.lower()]
        if cand_name_cols and cand_tel_cols and cand_mail_cols:
            with st.expander("Fusionner les emails de la feuille vers la base (heuristique)", expanded=False):
                name_col = st.selectbox("Colonne Nom", cand_name_cols, index=0)
                tel_col  = st.selectbox("Colonne Téléphone", cand_tel_cols, index=0)
                mail_col = st.selectbox("Colonne Email", cand_mail_cols, index=0)
                if st.button("🔗 Mettre à jour les emails dans la base"):
                    try:
                        # Normalise téléphone pour jointure simple (chiffres only)
                        tmp = rep[[name_col, tel_col, mail_col]].copy()
                        tmp.columns = ["nom_client","telephone","email_new"]
                        tmp["telephone_key"] = tmp["telephone"].astype(str).str.replace(r"\D","",regex=True)
                        tmp = tmp[tmp["telephone_key"].str.len()>=6]

                        dfn = df.copy()
                        dfn["telephone_key"] = dfn.get("telephone", "").astype(str).str.replace(r"\D","",regex=True)
                        dfn = dfn.merge(tmp[["telephone_key","email_new"]], on="telephone_key", how="left")
                        # Remplace email vide uniquement si email_new dispo
                        need = (dfn.get("email","").astype(str).str.strip()=="") & dfn["email_new"].notna()
                        dfn.loc[need, "email"] = dfn.loc[need, "email_new"]
                        dfn.drop(columns=["telephone_key","email_new"], errors="ignore", inplace=True)

                        if sauvegarder_donnees(ensure_schema(dfn)):
                            st.success("Emails fusionnés avec succès ✅"); st.rerun()
                    except Exception as e:
                        st.error(f"Échec de la fusion : {e}")
        else:
            st.caption("Astuce : si la feuille contient nom/téléphone/email, vous pourrez fusionner automatiquement.")

    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")


# ============================== §14 — LISTE DES CLIENTS ==============================
def vue_clients(df, palette):
    st.header("👥 Liste des clients")
    if df is None or df.empty:
        st.info("Aucun client.")
        return
    cols = [c for c in ["nom_client","telephone","email","plateforme","res_id"] if c in df.columns]
    if not cols:
        st.info("Colonnes clients introuvables.")
        return
    clients = df[cols].copy()
    for c in cols:
        clients[c] = clients[c].astype(str).replace({"nan":"", "None":""}).str.strip()
    if "nom_client" in clients.columns:
        clients = clients[clients["nom_client"]!=""]
    clients = clients.drop_duplicates()
    if "nom_client" in clients.columns:
        clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)


# ============================== §15 — ADMIN (sauvegarde, restauration, cache) ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    # Télécharger CSV (toujours en ; pour la cohérence)
    safe_csv = ensure_schema(df).copy()
    for col in ["date_arrivee","date_depart"]:
        safe_csv[col] = pd.to_datetime(safe_csv[col], errors="coerce").dt.strftime("%d/%m/%Y")
    st.sidebar.download_button(
        "⬇️ Télécharger CSV",
        data=safe_csv.to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )

    # Restaurer depuis un CSV (on accepte ; , tab | automatiquement)
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("✅ Confirmer restauration"):
        try:
            content = up.read()
            tmp_df = _detect_delimiter_and_read(content)
            tmp_df = ensure_schema(tmp_df)

            out = tmp_df.copy()
            for col in ["date_arrivee","date_depart"]:
                out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
            out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")

            st.cache_data.clear()
            try: st.cache_resource.clear()
            except Exception: pass

            st.success("Fichier restauré. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    # Vider le cache
    if st.sidebar.button("🧹 Vider le cache & recharger"):
        try: st.cache_data.clear()
        except Exception: pass
        try: st.cache_resource.clear()
        except Exception: pass
        st.success("Cache vidé. Rechargement…")
        st.rerun()

# ============================== §16 — MAIN ==============================
def main():
    # Thème
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    st.title("✨ Villa Tobias — Gestion des Réservations")

    # Chargement base
    df, palette_loaded = charger_donnees()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    # Navigation
    pages = {
        "🏠 Accueil": vue_accueil,            # (déjà fourni avant §11)
        "📋 Réservations": vue_reservations,  # (déjà fourni avant §11)
        "➕ Ajouter": vue_ajouter,            # (déjà fourni avant §11)
        "✏️ Modifier / Supprimer": vue_modifier,  # (déjà fourni avant §11)
        "🎨 Plateformes": vue_plateformes,    # (déjà fourni avant §11)
        "📅 Calendrier": vue_calendrier,      # (déjà fourni avant §11)
        "📊 Rapport": vue_rapport,            # (déjà fourni avant §11)
        "✉️ SMS": vue_sms,                    # (§11 ci-dessus)
        "📆 Export ICS": vue_export_ics,      # (§12)
        "📝 Google Sheet": vue_google_sheet,  # (§13)
        "👥 Clients": vue_clients,            # (§14)
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)

    # Admin
    admin_sidebar(df)

if __name__ == "__main__":
    main()
