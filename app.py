# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib, json
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# Fichiers locaux
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

# Palette par défaut
DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# Formulaire & Google Sheet (affichage)
FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"
OWNER_EMAIL = "charley@trigano.org"

# ============================== STYLE ==============================
def apply_style(light: bool):
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    chip_bg = "#e8e8e8" if light else "#333"
    chip_fg = "#222" if light else "#eee"

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

          /* KPI petites puces (réservations + calendrier détail) */
          .kpi-row {{ display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 10px 0; }}
          .kpi-chip {{
            background:rgba(127,127,127,.10);
            border:1px solid rgba(127,127,127,.22);
            padding:4px 8px;
            border-radius:10px;
            font-size:0.82rem;
            line-height:1.05;
          }}
          .kpi-chip b {{ font-size:0.88rem; }}

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

          /* Totaux rapport */
          .tot-chip {{
            display:inline-block; background:rgba(0,128,0,.08); border:1px solid rgba(0,128,0,.25);
            padding:6px 10px; border-radius:10px; margin:6px 8px 10px 0; font-size:0.9rem;
          }}
          .tot-chip b {{ margin-right:6px; }}
        </style>
        """,
        unsafe_allow_html=True
    )

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)

# ============================== DATA — Schéma & I/O ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye","plateforme",
    "telephone","date_arrivee","date_depart","nuitees","prix_brut","commissions",
    "frais_cb","prix_net","menage","taxes_sejour","res_id","ical_uid","AAAA","MM"
]

def _coerce_bool(s):
    return pd.Series(s).astype(str).str.strip().str.lower().isin(
        ["true","1","oui","vrai","yes","y","o"]
    )

def _num_clean(x):
    # Accept "1 234,56 €" or "1234.56"
    return pd.to_numeric(
        pd.Series(x)
          .astype(str)
          .str.replace("€","", regex=False)
          .str.replace("\u00A0","", regex=False)  # espace insécable
          .str.replace(" ", "", regex=False)
          .str.replace(",", ".", regex=False)
          .str.strip(),
        errors="coerce"
    ).fillna(0.0)

def _parse_date_any(s):
    s = pd.Series(s)
    # tenter d'abord jour/mois/année
    d1 = pd.to_datetime(s, errors="coerce", dayfirst=True)
    # puis ISO/US si encore NaT
    mask_nat = d1.isna()
    if mask_nat.any():
        d2 = pd.to_datetime(s[mask_nat], errors="coerce")
        d1.loc[mask_nat] = d2
    return d1.dt.date

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df.copy()
    # Strip noms de colonnes (et corrige " base ")
    df.columns = [c.strip() for c in df.columns]
    if "base" in df.columns:
        pass  # ignoré (non utilisé)
    if " base " in df.columns:
        df.rename(columns={" base ": "base"}, inplace=True)

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Dates
    df["date_arrivee"] = _parse_date_any(df["date_arrivee"])
    df["date_depart"]  = _parse_date_any(df["date_depart"])

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _coerce_bool(df[b]).fillna(False)

    # Numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees"]:
        df[n] = _num_clean(df[n])

    # Prix net (recalcul)
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).fillna(0.0)

    # Nuits si absent
    mask_dates = df["date_arrivee"].notna() & df["date_depart"].notna()
    df.loc[mask_dates, "nuitees"] = df.loc[mask_dates].apply(
        lambda r: max((r["date_depart"] - r["date_arrivee"]).days, 0), axis=1
    )

    # IDs internes
    if "res_id" not in df.columns:
        df["res_id"] = None
    miss = df["res_id"].isna() | (df["res_id"].astype(str).str.strip() == "")
    if miss.any():
        df.loc[miss, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss.sum()))]

    # AAAA / MM
    aa = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = aa.dt.year
    df["MM"]   = aa.dt.month

    # Tri des colonnes
    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    # Chargement CSV réservations
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=";")
    except Exception:
        df = pd.DataFrame()
    df = ensure_schema(df)

    # Chargement palette
    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";")
        df_pal.columns = df_pal.columns.str.strip()
        if "plateforme" in df_pal.columns and "couleur" in df_pal.columns:
            palette = {str(r["plateforme"]): str(r["couleur"]) for _, r in df_pal.iterrows() if pd.notna(r["plateforme"]) and pd.notna(r["couleur"])}
        else:
            palette = DEFAULT_PALETTE.copy()
    except Exception:
        palette = DEFAULT_PALETTE.copy()

    # Merge palettes (defaults first, then file overrides)
    palette_merged = DEFAULT_PALETTE.copy()
    palette_merged.update(palette)
    return df, palette_merged

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        df2 = ensure_schema(df)
        # Formater dates en JJ/MM/AAAA à l'export
        df_save = df2.copy()
        for c in ["date_arrivee","date_depart"]:
            df_save[c] = pd.to_datetime(df_save[c], errors="coerce").dt.strftime("%d/%m/%Y")
        df_save.to_csv(CSV_RESERVATIONS, sep=";", index=False)
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

# ============================== VUES (PARTIE 2) ==============================

# Helpers sûrs
def _safe_int_series(s):
    if s is None:
        return pd.Series([], dtype="int64")
    try:
        return pd.to_numeric(s, errors="coerce").dropna().astype(int)
    except Exception:
        return pd.Series([], dtype="int64")

def _safe_float_series(s):
    if s is None:
        return pd.Series([], dtype="float64")
    try:
        return pd.to_numeric(s, errors="coerce").fillna(0.0).astype(float)
    except Exception:
        return pd.Series([], dtype="float64")

def _safe_bool_series(s):
    if s is None:
        return pd.Series([], dtype="bool")
    return s.astype(str).str.lower().isin(["true","1","oui","vrai","yes"])

def _safe_date(v, fallback=None):
    """Retourne un objet date sûr pour st.date_input."""
    if isinstance(v, date):
        return v
    d = pd.to_datetime(v, errors="coerce")
    if pd.isna(d):
        return fallback if isinstance(fallback, date) else date.today()
    return d.date()

def _ensure_metrics(df):
    """S'assure que les colonnes numériques existent et sont numériques."""
    for col in ["prix_brut","prix_net","commissions","frais_cb","menage","taxes_sejour","nuitees"]:
        if col not in df.columns:
            df[col] = 0.0
        df[col] = _safe_float_series(df[col])
    return df

def _format_money(v):
    try:
        return f"{float(v):,.0f} €".replace(",", " ")
    except Exception:
        return "0 €"

# ---------------------- VUE RÉSERVATIONS ----------------------
def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    # Colonnes minimales
    if "AAAA" not in df.columns:
        df["AAAA"] = pd.to_datetime(df.get("date_arrivee"), errors="coerce").dt.year
    if "MM" not in df.columns:
        df["MM"] = pd.to_datetime(df.get("date_arrivee"), errors="coerce").dt.month

    # Séries sûres pour filtres
    years_ser  = _safe_int_series(df.get("AAAA"))
    months_ser = _safe_int_series(df.get("MM"))
    plats_ser  = df.get("plateforme")
    plats_list = sorted(plats_ser.dropna().astype(str).unique().tolist()) if plats_ser is not None else []

    years  = ["Toutes"] + (sorted(years_ser.unique(), reverse=True).tolist() if not years_ser.empty else [])
    months = ["Tous"]   + (sorted(months_ser.unique()) if not months_ser.empty else list(range(1,13)))
    plats  = ["Toutes"] + plats_list

    c1, c2, c3 = st.columns(3)
    ysel = c1.selectbox("Année", years, index=0)
    msel = c2.selectbox("Mois", months, index=0)
    psel = c3.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    # Nettoyage numérique
    data = _ensure_metrics(data)

    # Filtres
    if ysel != "Toutes":
        data = data[data["AAAA"] == int(ysel)]
    if msel != "Tous":
        data = data[data["MM"] == int(msel)]
    if psel != "Toutes":
        data = data[data.get("plateforme").astype(str) == str(psel)]

    if data.empty:
        st.warning("Aucune réservation après application des filtres.")
        return

    # Colonnes utiles éventuellement manquantes
    for col in ["paye","sms_envoye","post_depart_envoye"]:
        if col not in data.columns:
            data[col] = False
    data["paye"] = _safe_bool_series(data["paye"])

    # KPI (valeurs sûres)
    brut    = float(data["prix_brut"].sum())
    net     = float(data["prix_net"].sum())
    nuits   = int(_safe_float_series(data["nuitees"]).sum())
    menage  = float(data["menage"].sum())
    taxes   = float(data["taxes_sejour"].sum())
    basev   = float((data["prix_net"] - data["menage"] - data["taxes_sejour"]).sum())
    charges = float((data["prix_brut"] - data["prix_net"]).sum())
    adr     = (net/nuits) if nuits > 0 else 0.0

    kpi_html = f"""
    <div class="kpi-row">
      <div class="kpi-chip"><b>Brut</b>&nbsp;{_format_money(brut)}</div>
      <div class="kpi-chip"><b>Net</b>&nbsp;{_format_money(net)}</div>
      <div class="kpi-chip"><b>Nuitées</b>&nbsp;{nuits}</div>
      <div class="kpi-chip"><b>ADR (net)</b>&nbsp;{_format_money(adr)}</div>
      <div class="kpi-chip"><b>Ménage</b>&nbsp;{_format_money(menage)}</div>
      <div class="kpi-chip"><b>Taxes</b>&nbsp;{_format_money(taxes)}</div>
      <div class="kpi-chip"><b>Base</b>&nbsp;{_format_money(basev)}</div>
      <div class="kpi-chip"><b>Charges</b>&nbsp;{_format_money(charges)}</div>
    </div>
    """
    st.markdown(kpi_html, unsafe_allow_html=True)

    # Colonnes à montrer
    desired_cols = [
        "paye","sms_envoye","post_depart_envoye",
        "nom_client","plateforme","telephone","email",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
        "res_id","ical_uid"
    ]
    existing_cols = [c for c in desired_cols if c in data.columns and not data[c].isnull().all()]
    if not existing_cols:
        st.info("Aucune colonne exploitable à afficher.")
        return

    # Tri si possible
    if "date_arrivee" in data.columns:
        df_show = data.sort_values("date_arrivee", ascending=False, na_position="last")[existing_cols].copy()
    else:
        df_show = data[existing_cols].copy()

    st.dataframe(df_show, use_container_width=True)

# ---------------------- VUE AJOUTER ----------------------
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
            palette_keys = list(palette.keys()) if isinstance(palette, dict) else list(DEFAULT_PALETTE.keys())
            if not palette_keys:
                palette_keys = list(DEFAULT_PALETTE.keys())
            plat = st.selectbox("Plateforme", palette_keys)
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

# ---------------------- VUE MODIFIER / SUPPRIMER ----------------------
def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer")
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = df.copy()
    if "date_arrivee" in df_sorted.columns:
        df_sorted = df_sorted.sort_values(by="date_arrivee", ascending=False, na_position="last")
    df_sorted = df_sorted.reset_index(drop=False).rename(columns={"index": "_orig"})
    options = [
        f"{i}: {str(r.get('nom_client','') or '')} ({str(r.get('date_arrivee','') or '')})"
        for i, r in df_sorted.iterrows()
    ]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not sel:
        return
    idx = int(sel.split(":")[0])
    original_idx = int(df_sorted.loc[idx, "_orig"])
    row = df.loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=str(row.get("nom_client","") or ""))
            email = st.text_input("Email", value=str(row.get("email","") or ""))
            tel = st.text_input("Téléphone", value=str(row.get("telephone","") or ""))
            arrivee = st.date_input("Arrivée", value=_safe_date(row.get("date_arrivee"), date.today()))
            # Départ : si absent, +1 jour
            dep_default = _safe_date(row.get("date_arrivee"), date.today()) + timedelta(days=1)
            depart  = st.date_input("Départ", value=_safe_date(row.get("date_depart"), dep_default))
        with c2:
            palette_keys = list(palette.keys()) if isinstance(palette, dict) else list(DEFAULT_PALETTE.keys())
            if not palette_keys:
                palette_keys = list(DEFAULT_PALETTE.keys())
            current_plat = str(row.get("plateforme") or "")
            plat_idx = palette_keys.index(current_plat) if current_plat in palette_keys else 0
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

# ---------------------- VUE PLATEFORMES ----------------------
def vue_plateformes(df, palette):
    st.header("🎨 Plateformes & couleurs")
    base_palette = palette if (isinstance(palette, dict) and palette) else DEFAULT_PALETTE
    base = pd.DataFrame(list(base_palette.items()), columns=["plateforme","couleur"])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    c1, c2 = st.columns([1,1])
    if c1.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette enregistrée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
    if c2.button("🔄 Restaurer palette par défaut"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette par défaut restaurée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

# ---------------------- VUE CALENDRIER ----------------------
def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")
    if df is None or df.empty:
        st.info("Aucune réservation à afficher.")
        return

    dfv = df.copy()
    dfv["date_arrivee"] = pd.to_datetime(dfv.get("date_arrivee"), errors="coerce").dt.date
    dfv["date_depart"]  = pd.to_datetime(dfv.get("date_depart"), errors="coerce").dt.date
    dfv = dfv.dropna(subset=["date_arrivee","date_depart"])
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(pd.to_datetime(dfv['date_arrivee'], errors="coerce").dropna().dt.year.unique(), reverse=True)
    years = [int(y) for y in years] if len(years) else [today.year]
    annee = st.selectbox("Année", options=years, index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    # entête jours
    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    def day_resas(d):
        mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)  # 0 = lundi
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
                        color = (palette.get(r.get('plateforme'), '#888') if isinstance(palette, dict) else '#888')
                        name  = str(r.get('nom_client') or '')[:22]
                        cell += f"<div class='resa-pill' style='background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    # Détails + totaux + filtre plateforme
    st.markdown("---")
    st.subheader("Détails du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    mois_rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()
    if mois_rows.empty:
        st.info("Aucune réservation sur ce mois.")
        return

    plats_local_ser = mois_rows.get("plateforme")
    plats_local = ["Toutes"] + (sorted(plats_local_ser.dropna().astype(str).unique().tolist()) if plats_local_ser is not None else [])
    plat_local = st.selectbox("Filtrer par plateforme (détail du mois)", plats_local, index=0, key=f"cal_plat_{annee}_{mois}")
    data_mois = mois_rows if plat_local == "Toutes" else mois_rows[mois_rows["plateforme"].astype(str)==plat_local]
    data_mois = _ensure_metrics(data_mois)

    brut   = float(data_mois["prix_brut"].sum())
    net    = float(data_mois["prix_net"].sum())
    nuits  = int(_safe_float_series(data_mois["nuitees"]).sum())
    menage = float(data_mois["menage"].sum())
    taxes  = float(data_mois["taxes_sejour"].sum())
    nbres  = int(len(data_mois))

    kpi_html = f"""
    <div class="kpi-row">
      <div class="kpi-chip"><b>Réservations</b>&nbsp;{nbres}</div>
      <div class="kpi-chip"><b>Nuitées</b>&nbsp;{nuits}</div>
      <div class="kpi-chip"><b>Brut</b>&nbsp;{_format_money(brut)}</div>
      <div class="kpi-chip"><b>Net</b>&nbsp;{_format_money(net)}</div>
      <div class="kpi-chip"><b>Ménage</b>&nbsp;{_format_money(menage)}</div>
      <div class="kpi-chip"><b>Taxes</b>&nbsp;{_format_money(taxes)}</div>
    </div>
    """
    st.markdown(kpi_html, unsafe_allow_html=True)

    show_cols = ["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye","prix_brut","prix_net","menage","taxes_sejour"]
    show_cols = [c for c in show_cols if c in data_mois.columns]
    st.dataframe(
        data_mois[show_cols].sort_values("date_arrivee", na_position="last"),
        use_container_width=True
    )

# ---------------------- VUE RAPPORT ----------------------
def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df is None or df.empty:
        st.info("Aucune donnée."); return

    if "AAAA" not in df.columns:
        df["AAAA"] = pd.to_datetime(df.get("date_arrivee"), errors="coerce").dt.year
    if "MM" not in df.columns:
        df["MM"] = pd.to_datetime(df.get("date_arrivee"), errors="coerce").dt.month
    df = _ensure_metrics(df)

    years_ser = _safe_int_series(df.get("AAAA"))
    years = sorted(years_ser.unique(), reverse=True) if not years_ser.empty else [date.today().year]
    year  = st.selectbox("Année", years, index=0)

    months_ser = _safe_int_series(df.get("MM"))
    months = ["Tous"] + (sorted(months_ser.unique()) if not months_ser.empty else list(range(1,13)))
    month = st.selectbox("Mois", months, index=0)

    plats_ser = df.get("plateforme")
    all_plats = sorted(plats_ser.dropna().astype(str).unique().tolist()) if plats_ser is not None else []
    plat_options = ["Tous"] + all_plats
    plats_sel = st.multiselect("Plateformes", plat_options, default=["Tous"])
    if "Tous" in plats_sel or not plats_sel:
        plats_effectifs = all_plats
    else:
        plats_effectifs = [p for p in plats_sel if p != "Tous"]

    metric = st.selectbox("Métrique", ["prix_brut","prix_net","menage","nuitees"], index=0)

    data = df[df.get("AAAA") == year].copy()
    if month!="Tous":
        data = data[data.get("MM") == int(month)]
    if plats_effectifs:
        data = data[data.get("plateforme").astype(str).isin(plats_effectifs)]
    if data.empty:
        st.warning("Aucune donnée après filtres."); return

    data["mois"] = pd.to_datetime(data.get("date_arrivee"), errors="coerce").dt.to_period("M").astype(str)
    agg = data.groupby(["mois","plateforme"], as_index=False).agg({metric:"sum"})

    # Totaux
    total_metric = float(_safe_float_series(agg.get(metric)).sum())
    total_reservations = int(len(data))

    st.markdown(
        f'<span class="tot-chip"><b>Total {metric.replace("_"," ").title()}</b> {_format_money(total_metric)}</span>'
        f'<span class="tot-chip"><b>Réservations</b> {total_reservations}</span>',
        unsafe_allow_html=True
    )

    st.dataframe(agg.sort_values(["mois","plateforme"]), use_container_width=True)

    chart = alt.Chart(agg).mark_bar().encode(
        x="mois:N",
        y=alt.Y(f"{metric}:Q", title=metric.replace("_"," ").title()),
        color="plateforme:N",
        tooltip=["mois","plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True)

# ============================== SMS & WhatsApp ==============================
def _copy_button_js(label: str, payload: str, key: str):
    # Bouton de copie robuste (sans JS complexe, compatible Streamlit Cloud)
    st.text_area(f"{label} (aperçu à copier)", value=payload, height=150, key=f"ta_{key}")
    st.caption("Sélectionne tout (Ctrl/Cmd+A) puis copie (Ctrl/Cmd+C).")

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

def _post_depart_message(name: str) -> str:
    # Message post-départ fourni (FR + EN), conservé intégralement
    return (
f"Bonjour {name},\n\n"
"Un grand merci d'avoir choisi notre appartement pour votre sejour.\n\n"
"Nous esperons que vous avez passe un moment aussi agreable que celui que nous avons eu a vous accueillir.\n\n"
"Si l'envie vous prend de revenir explorer encore un peu notre ville, sachez que notre porte vous sera toujours grande ouverte.\n\n"
"Au plaisir de vous accueillir à nouveau.\n\n"
"Annick & Charley\n\n"
f"Hello {name},\n\n"
"Thank you very much for choosing our apartment for your stay.\n\n"
"We hope you had as enjoyable a time as we did hosting you.\n\n"
"If you feel like coming back to explore our city a little more, know that our door will always be open to you.\n\n"
"We look forward to welcoming you back.\n\n"
"Annick & Charley"
)

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    # Colonnes drapeaux
    for b in ("sms_envoye", "post_depart_envoye"):
        if b not in df.columns:
            df[b] = False
        df[b] = df[b].astype(str).str.lower().isin(["true","1","oui","vrai","yes"])

    # ---------------- Pré-arrivée (J+1) ----------------
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre["date_arrivee"] = pd.to_datetime(pre["date_arrivee"], errors="coerce").dt.date
    pre["date_depart"]  = pd.to_datetime(pre["date_depart"], errors="coerce").dt.date
    pre = pre[(pre["date_arrivee"]==target_arrivee) & (~pre["sms_envoye"])]

    if pre.empty:
        st.info("Aucun client à contacter pour la date choisie (ou déjà marqué).")
    else:
        pre["_rowid"] = pre.index
        pre = pre.sort_values("date_arrivee").reset_index(drop=True)
        options = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=options, index=None)

        if pick:
            i = int(pick.split(":")[0]); r = pre.loc[i]
            # Message FR+EN complet (avec lien court)
            msg = (
                "VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  "
                f"Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')}  "
                f"Nuitées : {int(r.get('nuitees') or 0)}\n\n"
                f"Bonjour {r.get('nom_client','')},\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. "
                "Merci de nous indiquer votre heure d'arrivée.\n\n"
                "➡️ Place de parking disponible. Check-in 14:00, check-out 11:00.\n\n"
                f"Merci de remplir la fiche d'arrivée : {FORM_SHORT_URL}\n\n"
                "EN — We are delighted to welcome you soon to Nice. "
                "Please let us know your arrival time. Parking space available on request. "
                "Check-in from 2pm, check-out before 11am.\n\n"
                f"Arrival form: {FORM_SHORT_URL}\n\n"
                "Annick & Charley"
            )
            enc = quote(msg)
            e164 = _format_phone_e164(r["telephone"])
            wa = re.sub(r"\D", "", e164)

            st.text_area("Prévisualisation", value=msg, height=260)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            _copy_button_js("📋 Copier le message", msg, key=f"pre_{i}")

            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                try:
                    df.loc[r["_rowid"], "sms_envoye"] = True
                    if sauvegarder_donnees(ensure_schema(df)):
                        st.success("Marqué ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    st.markdown("---")

    # ---------------- Post-départ (du jour) ----------------
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = df.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post["date_depart"] = pd.to_datetime(post["date_depart"], errors="coerce").dt.date
    post = post[(post["date_depart"]==target_depart) & (~post["post_depart_envoye"])]

    if post.empty:
        st.info("Aucun message post-départ à envoyer.")
    else:
        post["_rowid"] = post.index
        post = post.sort_values("date_depart").reset_index(drop=True)
        options2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=options2, index=None)

        if pick2:
            j = int(pick2.split(":")[0]); r2 = post.loc[j]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = _post_depart_message(name)
            enc2 = quote(msg2)
            e164b = _format_phone_e164(r2["telephone"])
            wab = re.sub(r"\D", "", e164b)

            st.text_area("Prévisualisation post-départ", value=msg2, height=260)
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            _copy_button_js("📋 Copier le message", msg2, key=f"post_{j}")

            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                try:
                    df.loc[r2["_rowid"], "post_depart_envoye"] = True
                    if sauvegarder_donnees(ensure_schema(df)):
                        st.success("Marqué ✅"); st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")


# ============================== EXPORT ICS ==============================
def build_stable_uid(row) -> str:
    # UID stable basé sur res_id + nom + tel (hash SHA1)
    res_id = str(row.get("res_id") or "")
    nom    = str(row.get("nom_client") or "")
    tel    = str(row.get("telephone") or "")
    base = f"{res_id}|{nom}|{tel}"
    return hashlib.sha1(base.encode("utf-8")).hexdigest() + "@villa-tobias"

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    if df is None or df.empty:
        st.info("Aucune réservation."); return

    # Assure colonnes
    if "AAAA" not in df.columns:
        df["AAAA"] = pd.to_datetime(df.get("date_arrivee"), errors="coerce").dt.year
    df["date_arrivee"] = pd.to_datetime(df.get("date_arrivee"), errors="coerce").dt.date
    df["date_depart"]  = pd.to_datetime(df.get("date_depart"), errors="coerce").dt.date

    years = sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years if len(years) else [date.today().year], index=0)

    plats = df.get("plateforme")
    all_plats = sorted(plats.dropna().astype(str).unique().tolist()) if plats is not None else []
    plat = st.selectbox("Plateforme", ["Tous"] + all_plats, index=0)

    data = df[df["AAAA"]==year].copy()
    if plat!="Tous":
        data = data[data.get("plateforme").astype(str)==plat]
    if data.empty:
        st.warning("Rien à exporter."); return

    # res_id + ical_uid
    if "res_id" not in data.columns:
        data["res_id"] = None
    miss_id = data["res_id"].isna() | (data["res_id"].astype(str).str.strip()=="")
    if miss_id.any():
        data.loc[miss_id, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_id.sum()))]

    if "ical_uid" not in data.columns:
        data["ical_uid"] = None
    miss_uid = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        data.loc[miss_uid, "ical_uid"] = data[miss_uid].apply(build_stable_uid, axis=1)

    # Persiste les ID/UID créés
    try:
        # réaligne sur l'index original quand possible
        join_cols = ["res_id","ical_uid"]
        idx_inter = data.index.intersection(df.index)
        df.loc[idx_inter, join_cols] = data.loc[idx_inter, join_cols]
        sauvegarder_donnees(ensure_schema(df))
    except Exception:
        pass

    def _fmt(d): return f"{d.year:04d}{d.month:02d}{d.day:02d}" if isinstance(d, date) else ""
    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r.get("date_arrivee"), r.get("date_depart")
        if not (isinstance(da, date) and isinstance(dd, date)): 
            continue
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"): summary += f" ({r['plateforme']})"
        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {int(r.get('nuitees') or 0)}",
            f"Prix brut: {float(r.get('prix_brut') or 0):.2f} €",
            f"res_id: {r.get('res_id','')}",
        ])
        uid = r.get("ical_uid") or build_stable_uid(r)
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
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


# ============================== GOOGLE SHEET (intégration) ==============================
def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée / Google Sheet")
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")

    # Iframe Form & Sheet via HTML pour compat max
    st.subheader("Formulaire (intégré)")
    st.markdown(
        f'<iframe src="{GOOGLE_FORM_URL}" width="100%" height="900" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )

    st.subheader("Feuille Google (lecture seule)")
    st.markdown(
        f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )

    st.subheader("Réponses (CSV publié)")
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
        st.dataframe(rep, use_container_width=True)
        st.download_button("⬇️ Télécharger réponses (CSV)", data=rep.to_csv(index=False).encode("utf-8"),
                           file_name="reponses_formulaire.csv", mime="text/csv")
    except Exception as e:
        st.error(f"Impossible de charger le CSV publié : {e}")


# ============================== LISTE CLIENTS ==============================
def vue_liste_clients(df, palette):
    st.header("👥 Liste des Clients")
    if df is None or df.empty:
        st.info("Aucun client.")
        return
    cols = [c for c in ["nom_client","telephone","plateforme","res_id"] if c in df.columns]
    if not cols:
        st.info("Colonnes clients manquantes.")
        return
    clients = df[cols].dropna(subset=["nom_client"]).drop_duplicates().sort_values("nom_client")
    st.dataframe(clients, use_container_width=True)


# ============================== ADMIN BAR ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    # Vider le cache (fonctionnel)
    if st.sidebar.button("🧹 Vider le cache (data)"):
        try:
            st.cache_data.clear()
            st.success("Cache vidé. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Échec du nettoyage : {e}")

    # Sauvegarde CSV
    try:
        st.sidebar.download_button(
            "💾 Télécharger CSV (réservations)",
            data=df.to_csv(sep=";", index=False).encode("utf-8"),
            file_name=CSV_RESERVATIONS,
            mime="text/csv"
        )
    except Exception as e:
        st.sidebar.error(f"Export CSV impossible : {e}")

    # Restauration CSV
    up = st.sidebar.file_uploader("📤 Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("✅ Confirmer la restauration"):
        try:
            with open(CSV_RESERVATIONS, "wb") as f:
                f.write(up.getvalue())
            st.cache_data.clear()
            st.success("Fichier restauré. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur de restauration : {e}")


# ============================== MAIN ==============================

def main():
    # Style clair/sombre
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    st.title("✨ Villa Tobias — Gestion des Réservations")

    # Chargement données & palette
    df, palette_loaded = charger_donnees()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    pages = {
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "👥 Liste des Clients": vue_liste_clients,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "📝 Google Sheet": vue_google_sheet,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)

    admin_sidebar(df)


if __name__ == "__main__":
    main()
