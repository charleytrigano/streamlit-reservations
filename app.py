# -*- coding: utf-8 -*-
import io, csv, re, uuid, hashlib, json
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

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

# Formulaires / Google
FORM_SHORT_URL = "https://urlr.me/kZuH94"
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
          /* Calendar grid */
          .cal-grid {{
            display:grid; grid-template-columns: repeat(7, 1fr);
            gap:8px; margin-top:8px;
          }}
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

# ============================== IMPORT ROBUSTE ==============================
NUMERIC_LIKE = {
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
    "base","charges","pct_charges","%","nuitees"
}
DATE_COLS = {"date_arrivee","date_depart"}
BOOL_COLS = {"paye","sms_envoye","post_depart_envoye"}

def _read_csv_loose(file_bytes: bytes) -> pd.DataFrame:
    """Lecture tolérante : détecte séparateur/encodage et retourne un DataFrame brut en texte."""
    sample = file_bytes[:4096]
    try:
        sniff = csv.Sniffer().sniff(sample.decode("utf-8", errors="ignore"))
        sep_guess = sniff.delimiter
    except Exception:
        sep_guess = ";"

    for enc in ("utf-8-sig","utf-8","cp1252"):
        for sep in (sep_guess, ";", ",", "\t"):
            try:
                df = pd.read_csv(
                    io.BytesIO(file_bytes),
                    sep=sep,
                    encoding=enc,
                    dtype=str,
                    na_values=["", "None", "none", "NULL", "NaN"],
                    keep_default_na=True,
                )
                df.columns = df.columns.map(lambda c: str(c).strip())
                return df
            except Exception:
                continue
    raise ValueError("Impossible de lire le CSV : encodage/séparateur non détecté.")

def _normalize_headers(df: pd.DataFrame) -> pd.DataFrame:
    ren = {
        " base ": "base",
        "base ": "base",
        " base": "base",
        " charges": "charges",
        "charges ": "charges",
        "%": "pct_charges",
    }
    clean = {}
    for c in df.columns:
        cc = " ".join(str(c).strip().split())
        clean[c] = ren.get(cc, cc)
    return df.rename(columns=clean)

def _clean_numeric_series(s: pd.Series) -> pd.Series:
    s = (s.astype(str)
           .str.replace("\u00A0", " ", regex=False)
           .str.replace("€", "", regex=False)
           .str.replace(" ", "", regex=False)
           .str.replace(",", ".", regex=False)
           .str.strip())
    s = s.replace({"": pd.NA, "None": pd.NA, "none": pd.NA, "NULL": pd.NA})
    return pd.to_numeric(s, errors="coerce")

def normalize_raw_dataframe(df_raw: pd.DataFrame) -> pd.DataFrame:
    """Nettoyage complet avant ensure_schema (€, virgules, dates, booléens, espaces)."""
    df = df_raw.copy()
    df = _normalize_headers(df)

    for c in df.columns:
        if df[c].dtype == object:
            df[c] = (df[c].astype(str)
                        .str.replace("\u00A0", " ", regex=False)
                        .str.strip()
                        .replace({"None": pd.NA, "none": pd.NA, "NULL": pd.NA}))

    for col in (NUMERIC_LIKE & set(df.columns)):
        df[col] = _clean_numeric_series(df[col])

    for col in (DATE_COLS & set(df.columns)):
        df[col] = pd.to_datetime(df[col], errors="coerce", dayfirst=True).dt.date

    for col in (BOOL_COLS & set(df.columns)):
        df[col] = (df[col].astype(str).str.lower()
                    .isin(["true","1","oui","vrai","yes"])).fillna(False)

    return df

# ============================== DATA / SCHEMA ==============================
BASE_COLS = [
    "paye","nom_client","sms_envoye","post_depart_envoye","plateforme","telephone","email",
    "date_arrivee","date_depart","nuitees","prix_brut","prix_net","commissions","frais_cb","menage","taxes_sejour",
    "base","charges","pct_charges","res_id","ical_uid","AAAA","MM"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df.copy()
    df.columns = df.columns.map(lambda c: str(c).strip())
    df = normalize_raw_dataframe(df)

    # Dates -> date
    for c in ["date_arrivee","date_depart"]:
        df[c] = pd.to_datetime(df.get(c), errors="coerce").dt.date

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        if b not in df.columns: df[b] = False
        df[b] = df[b].astype(str).str.lower().isin(["true","1","oui","vrai","yes"]).fillna(False)

    # Numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","base","charges","pct_charges"]:
        df[n] = pd.to_numeric(df.get(n), errors="coerce").fillna(0.0)

    # Prix net (si absent/recalcul)
    if "prix_net" not in df.columns:
        df["prix_net"] = 0.0
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).fillna(0.0)

    # Base/charges/% si pas fournis
    if "base" in df.columns and df["base"].fillna(0).eq(0).all():
        df["base"] = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).fillna(0.0)
    if "charges" in df.columns and df["charges"].fillna(0).eq(0).all():
        df["charges"] = (df["prix_brut"] - df["prix_net"]).fillna(0.0)
    with np.errstate(divide='ignore', invalid='ignore'):
        df["pct_charges"] = np.where(df["prix_brut"]>0, df["charges"]/df["prix_brut"]*100, 0.0)

    # IDs
    if "res_id" not in df.columns: df["res_id"] = None
    if "ical_uid" not in df.columns: df["ical_uid"] = None
    miss = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss.any():
        df.loc[miss, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss.sum()))]

    # Année / Mois
    df["AAAA"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year
    df["MM"]   = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.month

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns: df[c] = None

    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    # lecture CSV locale ultra-tolérante
    try:
        with open(CSV_RESERVATIONS, "rb") as f:
            raw = f.read()
        df_raw = _read_csv_loose(raw)
        df_raw = normalize_raw_dataframe(df_raw)
    except Exception:
        df_raw = pd.DataFrame()
    df = ensure_schema(df_raw)

    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";", dtype=str)
        df_pal.columns = df_pal.columns.str.strip()
        palette = dict(zip(df_pal["plateforme"].fillna(""), df_pal["couleur"].fillna("#888")))
        palette = {k:v for k,v in palette.items() if k}
        if not palette:
            palette = DEFAULT_PALETTE.copy()
    except Exception:
        palette = DEFAULT_PALETTE.copy()

    return df, palette

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        df2 = ensure_schema(df)
        df2.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde CSV : {e}")
        return False

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

# ============================== KPI SÛRS ==============================
def _safe_eur(x):
    try:
        v = float(x)
        if np.isnan(v):
            return "—"
        return f"{v:,.2f} €".replace(",", " ")
    except Exception:
        return "—"

def _kpis_resa(df):
    # Forcer toutes les colonnes à numérique
    for col in ["prix_brut", "prix_net", "base", "charges", "nuitees"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    brut    = float(pd.to_numeric(df.get("prix_brut"), errors="coerce").sum() or 0.0)
    net     = float(pd.to_numeric(df.get("prix_net"),  errors="coerce").sum() or 0.0)
    base_v  = float(pd.to_numeric(df.get("base"),      errors="coerce").sum() or 0.0)
    charges = float(pd.to_numeric(df.get("charges"),   errors="coerce").sum() or 0.0)
    nuits   = float(pd.to_numeric(df.get("nuitees"),   errors="coerce").sum() or 0.0)

    adr = (net / nuits) if nuits and not np.isnan(nuits) and nuits > 0 else np.nan

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Brut",    _safe_eur(brut))
    c2.metric("Net",     _safe_eur(net))
    c3.metric("Base",    _safe_eur(base_v))
    c4.metric("Charges", _safe_eur(charges))
    c5.metric("Nuitées / ADR", f"{int(nuits)} / {_safe_eur(adr)}" if not np.isnan(adr) else f"{int(nuits)} / —")

# ============================== VUES (réservations/calendrier/plateformes) ==============================
def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty:
        st.info("Aucune réservation.")
        return

    annees = ["Toutes"] + sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True).tolist()
    annee_sel = st.selectbox("Année", annees, index=0)
    mois_opts = ["Tous"] + list(range(1, 13))
    mois_sel = st.selectbox("Mois", mois_opts, index=0)
    plats = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    plat_sel = st.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    if annee_sel != "Toutes": data = data[data["AAAA"] == int(annee_sel)]
    if mois_sel != "Tous":   data = data[data["MM"] == int(mois_sel)]
    if plat_sel != "Toutes": data = data[data["plateforme"] == plat_sel]

    _kpis_resa(data)

    st.dataframe(
        data.sort_values("date_arrivee", ascending=False),
        use_container_width=True
    )

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
    edited = st.data_editor(
        base, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn("Couleur (#hex)")
        }
    )
    if st.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

# --------- CALENDRIER EN GRILLE ----------
def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")
    dfv = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(dfv['date_arrivee'].apply(lambda d: d.year).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])

    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

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

    st.markdown("---")
    st.subheader("Détails du mois sélectionné")
    mois_rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()
    if mois_rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        mois_rows = mois_rows.sort_values("date_arrivee")
        st.dataframe(mois_rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)

# ============================== RAPPORT / SMS / ICS / SHEET / ADMIN / MAIN ==============================

def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée."); return

    years  = sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True)
    year   = st.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1,13))
    month  = st.selectbox("Mois", months, index=0)
    plats  = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat   = st.selectbox("Plateforme", plats, index=0)

    metrics = {
        "Prix brut": "prix_brut",
        "Prix net": "prix_net",
        "Ménage": "menage",
        "Taxes séjour": "taxes_sejour",
        "Charges": "charges",
        "Base": "base",
        "Nuitées": "nuitees",
    }
    metric_label = st.selectbox("Métrique", list(metrics.keys()), index=0)
    metric = metrics[metric_label]

    data = df[df["AAAA"]==year].copy()
    if month!="Tous":
        data = data[data["MM"]==int(month)]
    if plat!="Tous":
        data = data[data["plateforme"]==plat]

    if data.empty:
        st.warning("Aucune donnée après filtres."); return

    # Série mensuelle
    data["mois"] = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.to_period("M").astype(str)
    agg = data.groupby(["mois","plateforme"], as_index=False).agg({metric:"sum"}).sort_values("mois")

    # Tableau + export
    st.dataframe(agg, use_container_width=True)
    st.download_button(
        "⬇️ Télécharger le CSV agrégé",
        data=agg.to_csv(index=False, sep=";").encode("utf-8"),
        file_name=f"rapport_{year}_{metric}.csv", mime="text/csv"
    )

    # Graph
    chart = alt.Chart(agg).mark_bar().encode(
        x=alt.X("mois:N", title="Mois"),
        y=alt.Y(f"{metric}:Q", title=metric_label),
        color=alt.Color("plateforme:N", title="Plateforme"),
        tooltip=["mois","plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True)


# ---- Bouton copier (JS) ----
def _copy_button_js(label: str, payload: str, key: str):
    st.components.v1.html(
        f"""
        <button onclick="navigator.clipboard.writeText({json.dumps(payload)})"
                style="padding:8px 12px;border-radius:10px;border:1px solid rgba(127,127,127,.35);
                       background:#222;color:#fff;cursor:pointer;margin-top:6px">
            {label}
        </button>
        """,
        height=42,
    )

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # =================== Pré-arrivée (arrivées J+1) ===================
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre["date_arrivee"] = pd.to_datetime(pre["date_arrivee"], errors="coerce").dt.date
    pre["date_depart"]  = pd.to_datetime(pre["date_depart"],  errors="coerce").dt.date
    if "sms_envoye" not in pre.columns:
        pre["sms_envoye"] = False
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
                f"Bonjour {r.get('nom_client')}\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. "
                "Aussi, afin d'organiser au mieux votre réception, merci de nous indiquer votre heure d'arrivée.\n\n"
                "Sachez qu'une place de parking vous est allouée en cas de besoin.\n\n"
                "Le check-in se fait à partir de 14:00 et le check-out avant 11:00.\n"
                "Vous trouverez des consignes à bagages dans chaque quartier à Nice.\n\n"
                "Merci de remplir la fiche d'arrivée : " + FORM_SHORT_URL + "\n\n"
                "Welcome to our home!\n\n"
                "We are delighted to welcome you soon to Nice. "
                "In order to organize your reception as best as possible, please let us know your arrival time.\n\n"
                "Please note that a parking space is available if needed.\n"
                "Check-in is from 2:00 p.m. and check-out is before 11:00 a.m.\n"
                "You will find luggage storage facilities in every neighborhood in Nice.\n\n"
                "Please fill out the arrival form: " + FORM_SHORT_URL + "\n\n"
                "Annick & Charley"
            )
            enc = quote(msg); e164 = _format_phone_e164(r["telephone"]); wa = re.sub(r"\D","", e164)
            st.text_area("Prévisualisation", value=msg, height=260)
            _copy_button_js("📋 Copier le message", msg, key=f"cpy_pre_{i}")
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # =================== Post-départ (départs du jour) ===================
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = df.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post["date_depart"] = pd.to_datetime(post["date_depart"], errors="coerce").dt.date
    if "post_depart_envoye" not in post.columns:
        post["post_depart_envoye"] = False
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
                "Un grand merci d'avoir choisi notre appartement pour votre séjour.\n\n"
                "Nous espérons que vous avez passé un moment aussi agréable que celui que nous avons eu à vous accueillir.\n\n"
                "Si l'envie vous prend de revenir explorer encore un peu notre ville, "
                "sachez que notre porte vous sera toujours grande ouverte.\n\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n\n"
                "We hope you had as enjoyable a time as we did hosting you.\n\n"
                "If you feel like coming back to explore our city a little more, "
                "know that our door will always be open to you.\n\n"
                "We look forward to welcoming you back.\n\n"
                "Annick & Charley"
            )
            enc2  = quote(msg2); e164b = _format_phone_e164(r2["telephone"]); wab = re.sub(r"\D","", e164b)
            st.text_area("Prévisualisation post-départ", value=msg2, height=260)
            _copy_button_js("📋 Copier le message", msg2, key=f"cpy_post_{j}")
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                df.loc[r2["_rowid"], "post_depart_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()


def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    if df.empty:
        st.info("Aucune réservation."); return
    years = sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = df[df["AAAA"]==year].copy()
    if plat!="Tous": data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Rien à exporter."); return

    if "ical_uid" not in data.columns:
        data["ical_uid"] = None
    missing_uid = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if missing_uid.any():
        data.loc[missing_uid, "ical_uid"] = data[missing_uid].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    def _fmt(d): return f"{d.year:04d}{d.month:02d}{d.day:02d}"
    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r["date_arrivee"], r["date_depart"]
        if not (isinstance(da, date) and isinstance(dd, date)): continue
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

    # Formulaire intégré
    st.markdown(
        f'<iframe src="{GOOGLE_FORM_URL}" width="100%" height="900" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )
    _copy_button_js("📋 Copier le lien formulaire", FORM_SHORT_URL, key="cpy_form")

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
        st.download_button("⬇️ Télécharger les réponses (CSV)", data=rep.to_csv(index=False).encode("utf-8"),
                           file_name="reponses_formulaire.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")


# ====== Wrapper plateformes avec restauration CSV ======
def vue_plateformes_wrapper(df, palette):
    vue_plateformes(df, palette)
    st.markdown("---")
    st.subheader("🔁 Restaurer une palette (CSV)")
    upf = st.file_uploader("Importer un CSV ';' avec colonnes plateforme,couleur", type=["csv"], key="restore_palette")
    if upf and st.button("✅ Restaurer cette palette"):
        try:
            pal = pd.read_csv(upf, delimiter=";", dtype=str)
            pal = pal.rename(columns=lambda c: str(c).strip())
            if not {"plateforme","couleur"}.issubset(set(pal.columns)):
                st.error("Le CSV doit contenir les colonnes 'plateforme' et 'couleur'."); return
            pal.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
            st.success("Palette restaurée ✅"); st.cache_data.clear(); st.rerun()
        except Exception as e:
            st.error(f"Erreur de restauration palette : {e}")


# ============================== ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    st.sidebar.download_button(
        "Télécharger CSV (réservations)",
        data=df.to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS, mime="text/csv"
    )

    up = st.sidebar.file_uploader("Restaurer réservations (CSV)", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            raw = up.read()
            df_raw = _read_csv_loose(raw)
            df_norm = normalize_raw_dataframe(df_raw)
            df_ok = ensure_schema(df_norm)
            df_ok.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.sidebar.success("Fichier restauré ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur restauration : {e}")

    # Bouton vider le cache
    if st.sidebar.button("🧹 Vider le cache"):
        try:
            st.cache_data.clear()
            st.sidebar.success("Cache vidé. Actualisation…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Impossible de vider le cache : {e}")


# ============================== MAIN ==============================
def main():
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette_loaded = charger_donnees()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    pages = {
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes_wrapper,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "📝 Google Sheet": vue_google_sheet,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()