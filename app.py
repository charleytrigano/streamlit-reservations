# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib, json, time
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# Formulaire & Sheet (tu as déjà publié ces URLs)
FORM_SHORT_URL = "https://urlr.me/kZuH94"  # lien court à partager
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# ============================== STYLE ==============================
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
            padding:6px 10px; border-radius:12px; margin:4px 6px; font-size:0.9rem
          }}
          .chips-small .chip {{
            font-size: 0.8rem; padding: 4px 8px;
          }}
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
        </style>
        """,
        unsafe_allow_html=True
    )

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)

# ============================== DATA SCHEMA + IO ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye","plateforme","telephone",
    "date_arrivee","date_depart","nuitees","prix_brut","prix_net","commissions","frais_cb","menage","taxes_sejour",
    "res_id","ical_uid","AAAA","MM"
]

def _clean_money(x):
    # accepte "228,48 €" " 1 234,50 " "1234.56"
    if pd.isna(x): return 0.0
    s = str(x).replace("€","").replace(" ", "").replace("\u00a0","").strip()
    s = s.replace(",", ".")
    try: return float(s)
    except: return 0.0

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        base = pd.DataFrame(columns=BASE_COLS)
        return base

    df = df.copy()

    # Dates (dd/mm/yyyy possible) -> date
    for c in ["date_arrivee","date_depart"]:
        df[c] = pd.to_datetime(df.get(c), dayfirst=True, errors="coerce").dt.date

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        if b not in df.columns: df[b] = False
        df[b] = (df[b].astype(str).str.strip().str.lower()
                 .isin(["true","1","oui","vrai","yes"])).fillna(False)

    # Numériques (tolérant)
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees"]:
        if n in df.columns:
            df[n] = df[n].apply(_clean_money).fillna(0.0)
        else:
            df[n] = 0.0

    # Prix net
    df["prix_net"] = df["prix_brut"] - df["commissions"] - df["frais_cb"]

    # IDs stables
    if "res_id" not in df.columns: df["res_id"] = None
    miss = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss.any():
        df.loc[miss, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss.sum()))]

    if "ical_uid" not in df.columns: df["ical_uid"] = None

    # Année / Mois
    df["AAAA"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year
    df["MM"]   = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.month

    # Email colonne si manquante
    if "email" not in df.columns: df["email"] = ""

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns: df[c] = None

    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    # lecture CSV principal
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=";")
    except Exception:
        df = pd.DataFrame()
    df = ensure_schema(df)

    # palette
    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";")
        palette = dict(zip(df_pal["plateforme"], df_pal["couleur"]))
        if not palette:
            palette = DEFAULT_PALETTE.copy()
    except Exception:
        palette = DEFAULT_PALETTE.copy()

    return df, palette

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        df2 = ensure_schema(df)
        df2.to_csv(CSV_RESERVATIONS, sep=";", index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde CSV : {e}")
        return False

# ============================== EMAIL SYNC (Google Sheet CSV) ==============================
EMAIL_CANDIDATES = ["email","e-mail","adresse e-mail","adresse email","courriel","mail"]
RESID_CANDIDATES = ["res_id","reservation id","id interne","reservationid"]
TEL_CANDIDATES   = ["telephone","téléphone","phone","numéro de téléphone"]
NOM_CANDIDATES   = ["nom","nom complet","client","full name","name"]
ARR_CANDIDATES   = ["date_arrivee","date d'arrivée","arrivée","arrival date"]

def _norm_col(s): return str(s).strip().lower()
def _find_col(columns, candidates):
    cols_norm = {_norm_col(c): c for c in columns}
    for c in candidates:
        if _norm_col(c) in cols_norm: return cols_norm[_norm_col(c)]
    # heuristique : contient un des mots
    for c in columns:
        lc = _norm_col(c)
        if any(_norm_col(k) in lc for k in candidates):
            return c
    return None

def fetch_form_responses() -> pd.DataFrame:
    df_form = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
    if df_form.empty:
        return df_form
    # détecte colonnes utiles
    col_email = _find_col(df_form.columns, EMAIL_CANDIDATES)
    col_resid = _find_col(df_form.columns, RESID_CANDIDATES)
    col_tel   = _find_col(df_form.columns, TEL_CANDIDATES)
    col_nom   = _find_col(df_form.columns, NOM_CANDIDATES)
    col_arr   = _find_col(df_form.columns, ARR_CANDIDATES)

    rename_map = {}
    if col_email: rename_map[col_email] = "email_form"
    if col_resid: rename_map[col_resid] = "res_id_form"
    if col_tel:   rename_map[col_tel]   = "telephone_form"
    if col_nom:   rename_map[col_nom]   = "nom_form"
    if col_arr:   rename_map[col_arr]   = "date_arrivee_form"
    df_form = df_form.rename(columns=rename_map)

    if "date_arrivee_form" in df_form.columns:
        df_form["date_arrivee_form"] = pd.to_datetime(df_form["date_arrivee_form"], errors="coerce").dt.date
    if "email_form" in df_form.columns:
        df_form["email_form"] = df_form["email_form"].astype(str).str.strip()

    return df_form

def sync_emails_from_form(df_resa: pd.DataFrame):
    """Retourne (df_mis_a_jour, stats)"""
    base = ensure_schema(df_resa)
    form = fetch_form_responses()
    stats = {"matched_res_id": 0, "matched_triple": 0, "emails_set": 0}

    if form.empty or ("email_form" not in form.columns):
        return base, stats

    # 1) par res_id
    if "res_id_form" in form.columns:
        f1 = form.dropna(subset=["res_id_form","email_form"]).copy()
        if not f1.empty:
            f1["res_id_form"] = f1["res_id_form"].astype(str).str.strip()
            f1 = f1[f1["res_id_form"] != ""]
            m = base.merge(f1[["res_id_form","email_form"]], left_on="res_id", right_on="res_id_form", how="left")
            mask = m["email"].astype(str).str.strip().eq("") & m["email_form"].notna() & m["email_form"].astype(str).str.contains("@")
            stats["matched_res_id"] = int(mask.sum())
            m.loc[mask, "email"] = m.loc[mask, "email_form"]
            base = m[BASE_COLS].copy()

    # 2) fallback (nom + tel + date_arrivee)
    need = ["nom_form","telephone_form","date_arrivee_form","email_form"]
    if all(c in form.columns for c in need):
        f2 = form.dropna(subset=need).copy()
        if not f2.empty:
            f2["k"] = (
                f2["nom_form"].astype(str).str.strip().str.lower() + "|" +
                f2["telephone_form"].astype(str).str.replace(r"\D","",regex=True).str[-10:] + "|" +
                f2["date_arrivee_form"].astype(str)
            )
            b = base.copy()
            b["k"] = (
                b["nom_client"].astype(str).str.strip().str.lower() + "|" +
                b["telephone"].astype(str).str.replace(r"\D","",regex=True).str[-10:] + "|" +
                pd.to_datetime(b["date_arrivee"], errors="coerce").dt.date.astype(str)
            )
            m2 = b.merge(f2[["k","email_form"]], on="k", how="left")
            mask2 = m2["email"].astype(str).str.strip().eq("") & m2["email_form"].notna() & m2["email_form"].astype(str).str.contains("@")
            stats["matched_triple"] = int(mask2.sum())
            m2.loc[mask2, "email"] = m2.loc[mask2, "email_form"]
            base = m2[BASE_COLS].copy()

    stats["emails_set"] = int((base["email"].astype(str).str.strip() != "").sum())
    return base, stats

# ============================== HELPERS UI ==============================
def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

def _hard_reload():
    try: st.cache_data.clear()
    except Exception: pass
    try: st.cache_resource.clear()
    except Exception: pass
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.experimental_set_query_params(_ts=str(int(time.time())))
    st.experimental_rerun()

# ============================== VUE ACCUEIL ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()

    # Arrivées du jour
    arr = df.dropna(subset=["date_arrivee","nom_client"]).copy()
    arr["date_arrivee"] = pd.to_datetime(arr["date_arrivee"], errors="coerce").dt.date
    arr_today = arr[arr["date_arrivee"]==today][["nom_client","telephone","plateforme"]]
    with st.container():
        st.markdown("<div class='glass'>", unsafe_allow_html=True)
        st.subheader("🟢 Arrivées du jour")
        if arr_today.empty:
            st.info("Aucune arrivée aujourd’hui.")
        else:
            st.dataframe(arr_today.rename(columns={"nom_client":"Client","telephone":"Téléphone","plateforme":"Plateforme"}),
                         use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Départs du jour
    dep = df.dropna(subset=["date_depart","nom_client"]).copy()
    dep["date_depart"] = pd.to_datetime(dep["date_depart"], errors="coerce").dt.date
    dep_today = dep[dep["date_depart"]==today][["nom_client","telephone","plateforme"]]
    with st.container():
        st.markdown("<div class='glass'>", unsafe_allow_html=True)
        st.subheader("🔴 Départs du jour")
        if dep_today.empty:
            st.info("Aucun départ aujourd’hui.")
        else:
            st.dataframe(dep_today.rename(columns={"nom_client":"Client","telephone":"Téléphone","plateforme":"Plateforme"}),
                         use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ============================== VUE RÉSERVATIONS ==============================
def _kpi_chip(label, value, money=False):
    if money:
        val = f"{value:,.2f} €".replace(",", " ")
    else:
        val = f"{value:,.0f}"
    st.markdown(f"<span class='chip'>{label}: <b>{val}</b></span>", unsafe_allow_html=True)

def vue_reservations(df, palette):
    st.header("📋 Réservations")

    if df.empty:
        st.info("Aucune réservation.")
        return

    # Filtres (Année, Mois, Plateforme)
    years_ser = pd.to_numeric(df["AAAA"], errors="coerce").dropna().astype(int)
    years  = ["Toutes"] + (sorted(years_ser.unique(), reverse=True).tolist() if not years_ser.empty else [])
    year_sel = st.selectbox("Année", years, index=0)

    months = ["Tous"] + list(range(1,13))
    month_sel = st.selectbox("Mois", months, index=0)

    plats_all = sorted(df["plateforme"].dropna().astype(str).unique().tolist())
    plats = ["Toutes"] + plats_all
    plat_sel = st.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    if year_sel != "Toutes":
        data = data[pd.to_numeric(data["AAAA"], errors="coerce").astype("Int64") == int(year_sel)]
    if month_sel != "Tous":
        data = data[pd.to_numeric(data["MM"], errors="coerce").astype("Int64") == int(month_sel)]
    if plat_sel != "Toutes":
        data = data[data["plateforme"] == plat_sel]

    # Totaux compacts (taille réduite)
    brut = float(data["prix_brut"].sum())
    net  = float(data["prix_net"].sum())
    nuits= float(data["nuitees"].sum())
    base = float((data["prix_net"] - data["menage"] - data["taxes_sejour"]).sum())
    charges = float((data["prix_brut"] - data["prix_net"]).sum())
    adr  = (net/nuits) if nuits>0 else 0.0

    st.markdown("<div class='glass chips-small'>", unsafe_allow_html=True)
    _kpi_chip("Brut", brut, money=True)
    _kpi_chip("Net", net, money=True)
    _kpi_chip("Base (net - ménage - taxes)", base, money=True)
    _kpi_chip("Charges (comm+CB)", charges, money=True)
    _kpi_chip("Nuitées", nuits, money=False)
    _kpi_chip("ADR (net)", adr, money=True)
    st.markdown("</div>", unsafe_allow_html=True)

    # Tableau
    st.dataframe(
        data.sort_values("date_arrivee", ascending=False),
        use_container_width=True
    )


# ============================== HELPERS (partie 2) ==============================
def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

# ============================== AUTRES VUES ==============================
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

def vue_plateformes(df, palette):
    st.header("🎨 Plateformes & couleurs")
    base = pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette enregistrée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
    if c2.button("↩️ Restaurer palette par défaut"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette par défaut restaurée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")
    dfv = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(dfv['date_arrivee'].apply(lambda d: pd.to_datetime(d).year).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    # entête jours
    st.markdown("<div class='cal-grid' style='grid-template-columns: repeat(7, 1fr); font-weight:700; opacity:.8; gap:8px'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    dfv['date_arrivee'] = pd.to_datetime(dfv['date_arrivee']).dt.date
    dfv['date_depart']  = pd.to_datetime(dfv['date_depart']).dt.date

    def day_resas(d):
        mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)  # lundi
    html = ["<div class='cal-grid'>"]
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
                        color = palette.get(r.get('plateforme'), '#888')
                        name  = str(r.get('nom_client') or '')[:22]
                        cell += f"<div class='resa-pill' style='background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    # Détails du mois
    st.markdown("---")
    st.subheader("Détails du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois   = date(annee, mois, monthrange(annee, mois)[1])
    mois_rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()
    if mois_rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        mois_rows = mois_rows.sort_values("date_arrivee")
        # Totaux en haut
        colA, colB, colC = st.columns(3)
        colA.metric("Brut (mois)", f"{float(mois_rows['prix_brut'].sum()):,.2f} €".replace(",", " "))
        colB.metric("Net (mois)",  f"{float(mois_rows['prix_net'].sum()):,.2f} €".replace(",", " "))
        colC.metric("Nuitées",     f"{int(mois_rows['nuitees'].sum())}")
        # Filtre plateforme
        plats = ["Toutes"] + sorted(mois_rows["plateforme"].dropna().unique().tolist())
        ps = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
        if ps != "Toutes":
            mois_rows = mois_rows[mois_rows["plateforme"]==ps]
        st.dataframe(mois_rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]],
                     use_container_width=True)

def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée."); return
    years = sorted(pd.to_numeric(df["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1,13))
    month = st.selectbox("Mois", months, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)
    metric = st.selectbox("Métrique", ["prix_brut","prix_net","menage","nuitees"], index=0)

    data = df[df["AAAA"]==year].copy()
    if month!="Tous": data = data[data["MM"]==int(month)]
    if plat!="Tous":  data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Aucune donnée après filtres."); return

    data["mois"] = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.to_period("M").astype(str)
    agg = data.groupby(["mois","plateforme"], as_index=False).agg({metric:"sum"})
    # Total global
    total_val = float(agg[metric].sum())
    st.metric("Total sélection", f"{total_val:,.2f}".replace(",", " ") + (" €" if metric.startswith("prix_") else ""))
    st.dataframe(agg, use_container_width=True)

    chart = alt.Chart(agg).mark_bar().encode(
        x="mois:N",
        y=alt.Y(f"{metric}:Q", title=metric.replace("_"," ").title()),
        color="plateforme:N",
        tooltip=["mois","plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True)

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # Pré-arrivée
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre["date_arrivee"] = pd.to_datetime(pre["date_arrivee"], errors="coerce").dt.date
    pre["date_depart"]  = pd.to_datetime(pre["date_depart"], errors="coerce").dt.date
    pre = pre[(pre["date_arrivee"]==target_arrivee) & (~pre["sms_envoye"])]
    if pre.empty:
        st.info("Aucun client à contacter.")
    else:
        pre["_rowid"] = pre.index
        pre = pre.sort_values("date_arrivee").reset_index(drop=True)
        opts = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=opts, index=None)
        if pick:
            i = int(pick.split(":")[0]); r = pre.loc[i]
            msg = (
                "VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  "
                f"Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')}  "
                f"Nuitées : {int(r.get('nuitees') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')},\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. "
                "Merci de nous indiquer votre heure d'arrivée.\n\n"
                "➡️ Place de parking disponible. Check-in 14:00, check-out 11:00.\n"
                f"Merci de remplir la fiche : {FORM_SHORT_URL}\n\n"
                "EN — Please tell us your arrival time. Parking on request. "
                "Check-in from 2pm, check-out before 11am. "
                f"Form: {FORM_SHORT_URL}\n\n"
                "Annick & Charley"
            )
            enc = quote(msg); e164 = _format_phone_e164(r["telephone"]); wa = re.sub(r"\D","", e164)
            st.text_area("Prévisualisation", value=msg, height=240)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # Post-départ
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = df.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post["date_depart"] = pd.to_datetime(post["date_depart"], errors="coerce").dt.date
    post = post[(post["date_depart"]==target_depart) & (~post["post_depart_envoye"])]
    if post.empty:
        st.info("Aucun message à envoyer.")
    else:
        post["_rowid"] = post.index
        post = post.sort_values("date_depart").reset_index(drop=True)
        opts2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=opts2, index=None)
        if pick2:
            j = int(pick2.split(":")[0]); r2 = post.loc[j]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Un grand merci d'avoir choisi notre appartement pour votre sejour. \n\n"
                "Nous esperons que vous avez passe un moment aussi agreable que celui que nous avons eu a vous accueillir. \n\n"
                "Si l'envie vous prend de revenir explorer encore un peu notre ville, sachez que notre porte vous sera toujours grande ouverte. \n\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay. \n\n"
                "We hope you had as enjoyable a time as we did hosting you. \n\n"
                "If you feel like coming back to explore our city a little more, know that our door will always be open to you. \n\n"
                "We look forward to welcoming you back.\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2); e164b = _format_phone_e164(r2["telephone"]); wab = re.sub(r"\D","", e164b)
            st.text_area("Prévisualisation post-départ", value=msg2, height=260)
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤗 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                df.loc[r2["_rowid"], "post_depart_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    if df.empty:
        st.info("Aucune réservation."); return
    years = sorted(pd.to_numeric(df["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = df[df["AAAA"]==year].copy()
    if plat!="Tous": data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Rien à exporter."); return

    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if miss.any():
        data.loc[miss, "ical_uid"] = data[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    def _fmt(d): 
        d = pd.to_datetime(d).date()
        return f"{d.year:04d}{d.month:02d}{d.day:02d}"
    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r["date_arrivee"], r["date_depart"]
        if pd.isna(da) or pd.isna(dd): continue
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"): summary += f" ({r['plateforme']})"
        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {int(r.get('nuitees') or 0)}",
            f"Prix brut: {float(r.get('prix_brut') or 0):.2f} €",
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
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"), file_name=f"reservations_{year}.ics", mime="text/calendar")

def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée / Google Sheet")
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")

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
        st.dataframe(rep, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")

def vue_liste_clients(df, palette):
    st.header("👥 Liste des clients")
    if df.empty:
        st.info("Aucun client."); return
    clients = (df[['nom_client','telephone','plateforme','res_id']]
               .dropna(subset=['nom_client']).drop_duplicates().sort_values('nom_client'))
    st.dataframe(clients, use_container_width=True)

# ============================== ADMIN SIDEBAR ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button(
        "Télécharger CSV",
        data=df.to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            with open(CSV_RESERVATIONS, "wb") as f: f.write(up.getvalue())
            st.success("Fichier restauré. Rechargement…")
            _hard_reload()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    if st.sidebar.button("🧹 Vider le cache / Recharger"):
        _hard_reload()

# ============================== MAIN ==============================
def main():
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette_loaded = charger_donnees(_file_sig())
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
        "👥 Clients": vue_liste_clients,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()