# -*- coding: utf-8 -*-
import time
import re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# --- HARD CLEAR au démarrage (une seule fois) ---
def _hard_clear_once():
    if st.session_state.get("_cleared_on_start", False):
        return
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    st.session_state["_cleared_on_start"] = True
_hard_clear_once()

CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# Lien formulaire court + intégrations Google (lecture seule)
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
            padding:4px 8px; border-radius:10px; margin:2px 4px; font-size:0.85rem
          }}
          .kpi-line small {{
            font-size:.8rem; opacity:.8;
          }}
          .kpi-line strong {{
            font-size:1rem;
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

# ============================== DATA ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye","plateforme","telephone",
    "date_arrivee","date_depart","nuitees","prix_brut","prix_net","commissions","frais_cb","menage","taxes_sejour",
    "base","charges","%","AAAA","MM","res_id","ical_uid"
]

def _to_bool(s):
    return str(s).strip().lower() in {"true","1","oui","vrai","yes","y"}

def _parse_date_mixed(x):
    if pd.isna(x) or x == "":
        return pd.NaT
    s = str(x).strip()
    # essais dd/mm/yyyy, yyyy-mm-dd
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d/%m/%y"):
        try:
            return pd.to_datetime(s, format=fmt, errors="raise")
        except Exception:
            pass
    # fallback: parsing automatique
    return pd.to_datetime(s, errors="coerce")

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df.copy()
    # Harmonise noms possibles
    rename_map = {
        "Payé": "paye", "Client": "nom_client", "Plateforme": "plateforme",
        "Arrivée": "date_arrivee", "Départ": "date_depart", "Nuits": "nuitees",
        "Brut (€)": "prix_brut"
    }
    df.rename(columns=rename_map, inplace=True)

    # Boolean
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        if b not in df.columns:
            df[b] = False
        df[b] = df[b].apply(_to_bool)

    # Dates
    for c in ["date_arrivee","date_depart"]:
        if c not in df.columns:
            df[c] = pd.NaT
        df[c] = df[c].apply(_parse_date_mixed).dt.date

    # Nuité(e)s
    mask_dates = pd.notna(df["date_arrivee"]) & pd.notna(df["date_depart"])
    df.loc[mask_dates, "nuitees"] = (
        pd.to_datetime(df.loc[mask_dates, "date_depart"]) - pd.to_datetime(df.loc[mask_dates, "date_arrivee"])
    ).dt.days
    df["nuitees"] = pd.to_numeric(df.get("nuitees"), errors="coerce").fillna(0).astype(int)

    # Numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        if n not in df.columns: df[n] = 0
        if df[n].dtype == "object":
            df[n] = (
                df[n].astype(str)
                .str.replace("€","", regex=False)
                .str.replace(" ", "", regex=False)
                .str.replace(",", ".", regex=False)
            )
        df[n] = pd.to_numeric(df[n], errors="coerce").fillna(0.0)

    # Dérivés
    df["prix_net"] = df["prix_brut"] - df["commissions"] - df["frais_cb"]
    df["charges"]  = df["prix_brut"] - df["prix_net"]
    df["base"]     = df["prix_net"] - df["menage"] - df["taxes_sejour"]
    with np.errstate(divide="ignore", invalid="ignore"):
        df["%"] = np.where(df["prix_brut"] > 0, df["charges"] / df["prix_brut"] * 100, 0.0)

    # AAAA / MM
    dta = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = dta.dt.year
    df["MM"]   = dta.dt.month

    # IDs
    if "res_id" not in df.columns:
        df["res_id"] = None
    miss = df["res_id"].isna() | (df["res_id"].astype(str).str.strip() == "")
    if miss.any():
        df.loc[miss, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss.sum()))]
    if "ical_uid" not in df.columns:
        df["ical_uid"] = None

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    # Réservations
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=";")
    except Exception:
        df = pd.DataFrame()
    df = ensure_schema(df)

    # Palette
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

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    # Arrivées du jour
    arr = df.dropna(subset=["date_arrivee"]).copy()
    arr = arr[arr["date_arrivee"] == today]
    dep = df.dropna(subset=["date_depart"]).copy()
    dep = dep[dep["date_depart"] == today]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        if arr.empty:
            st.info("Aucune arrivée aujourd'hui.")
        else:
            for _, r in arr.iterrows():
                st.markdown(f"**{r.get('nom_client','')}** — 📞 {r.get('telephone','')}")
    with c2:
        st.subheader("🔴 Départs du jour")
        if dep.empty:
            st.info("Aucun départ aujourd'hui.")
        else:
            for _, r in dep.iterrows():
                st.markdown(f"**{r.get('nom_client','')}** — 📞 {r.get('telephone','')}")

def _kpi_line(df):
    brut = float(df["prix_brut"].sum())
    net  = float(df["prix_net"].sum())
    base = float(df["base"].sum())
    nuits= int(df["nuitees"].sum())
    adr  = (net/nuits) if nuits>0 else 0.0
    html = f"""
    <div class='glass kpi-line'>
      <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
      <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
      <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
      <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
      <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
    </div>
    """.replace(",", " ")
    st.markdown(html, unsafe_allow_html=True)

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty:
        st.info("Aucune réservation.")
        return

    # Filtres
    years_ser = df["AAAA"].dropna().astype(int)
    years  = ["Toutes"] + (sorted(years_ser.unique(), reverse=True).tolist() if not years_ser.empty else [])
    year   = st.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1,13))
    month  = st.selectbox("Mois", months, index=0)
    plats  = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    plat   = st.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    if year != "Toutes": data = data[data["AAAA"] == int(year)]
    if month != "Tous": data = data[data["MM"] == int(month)]
    if plat != "Toutes": data = data[data["plateforme"] == plat]

    _kpi_line(data)

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
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette enregistrée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
    if c2.button("↩️ Restaurer depuis fichier"):
        try:
            df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";")
            st.success("Palette rechargée depuis le CSV.")
            st.experimental_rerun()
        except Exception as e:
            st.error(f"Impossible de restaurer : {e}")

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

    # entête jours
    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    cal = Calendar(firstweekday=0)  # Lundi
    html = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(annee, mois):
        for d in week:
            outside = (d.month != mois)
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'>"
            cell += f"<div class='cal-date'>{d.day}</div>"
            if not outside:
                mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
                rs = dfv[mask]
                for _, r in rs.iterrows():
                    color = palette.get(r.get('plateforme'), '#888')
                    name  = str(r.get('nom_client') or '')[:22]
                    cell += f"<div class='resa-pill' style='background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    # Détails du mois (liste + totaux + filtre plateforme)
    st.markdown("---")
    st.subheader("Détail du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    mois_rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()
    plats = ["Toutes"] + sorted(mois_rows["plateforme"].dropna().unique())
    plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="detail_mois_plat")
    if plat != "Toutes":
        mois_rows = mois_rows[mois_rows["plateforme"] == plat]
    if mois_rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        _kpi_line(mois_rows)
        st.dataframe(mois_rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye","prix_brut","prix_net","base"]], use_container_width=True)

def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée."); return
    years = sorted(df["AAAA"].dropna().astype(int).unique(), reverse=True)
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
    total_val = agg[metric].sum()

    c1, c2 = st.columns([3,1])
    c1.dataframe(agg, use_container_width=True)
    c2.markdown(f"<div class='glass'><b>Total {metric.replace('_',' ')}</b><br><span class='chip'><strong>{total_val:,.2f}</strong></span></div>".replace(",", " "), unsafe_allow_html=True)

    chart = alt.Chart(agg).mark_bar().encode(
        x="mois:N",
        y=alt.Y(f"{metric}:Q", title=metric.replace("_"," ").title()),
        color="plateforme:N",
        tooltip=["mois","plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True)

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # Pré-arrivée (arrivées J+1), message complet
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre["date_arrivee"] = pd.to_datetime(pre["date_arrivee"], errors="coerce").dt.date
    pre["date_depart"]  = pd.to_datetime(pre["date_depart"], errors="coerce").dt.date
    pre = pre[(pre["date_arrivee"]==target_arrivee) & (~pre["sms_envoye"])]
    if pre.empty:
        st.info("Aucun client à contacter (ou déjà marqué 'SMS envoyé').")
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
                "Nous sommes ravis de vous acceuillir bientot a Nice. Aussi afin d'organiser au mieux votre reception merci de nous indiquer votre heure d'arrivee.\n\n"
                "Sachez qu'une place de parking vous est allouee en cas de besoin.\n\n"
                "Le check-in se fait a partir de 14:00 h et le check-out avant 11:00 h.\n\n"
                "Vous trouverez des consignes a bagages dans chaque quartier a Nice.\n\n"
                "Nous vous souhaitons un excellent voyage et nous nous rejouissons de vous rencontrer tres bientot.\n\n"
                "Welcome to our home!\n\n"
                "We are delighted to welcome you soon to Nice. Please let us know your arrival time.\n\n"
                "Please note that a parking space is available if needed.\n\n"
                "Check-in is from 2:00 p.m. and check-out is before 11:00 a.m.\n\n"
                "You will find luggage storage facilities in every neighborhood in Nice.\n\n"
                "We wish you a wonderful trip and look forward to meeting you very soon.\n\n"
                "Annick & Charley\n\n"
                f"Merci de remplir la fiche d'arrivee : {FORM_SHORT_URL}\n"
            )
            enc = quote(msg); e164 = _format_phone_e164(r["telephone"]); wa = re.sub(r"\D","", e164)
            st.text_area("Prévisualisation", value=msg, height=320)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # Post-départ (départs du jour) — message fourni
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
            enc2 = quote(msg2); e164b = _format_phone_e164(r2["telephone"]); wab = re.sub(r"\D","", e164b)
            st.text_area("Prévisualisation post-départ", value=msg2, height=320)
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

    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if miss.any():
        data.loc[miss, "ical_uid"] = data[miss].apply(build_stable_uid, axis=1)

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

    for c in ["plateforme", "nom_client", "telephone", "email", "res_id"]:
        if c not in df.columns:
            df[c] = ""

    if df.empty:
        st.info("Aucun client.")
        return

    clients = (
        df[["plateforme", "nom_client", "telephone", "email", "res_id"]]
        .dropna(subset=["nom_client"])
        .drop_duplicates()
        .sort_values(["plateforme", "nom_client"])
        .rename(
            columns={
                "plateforme": "Plateforme",
                "nom_client": "Client",
                "telephone": "Téléphone",
                "email": "Email",
                "res_id": "ID interne",
            }
        )
    )

    st.dataframe(clients, use_container_width=True)
    st.download_button(
        "⬇️ Exporter les clients (CSV)",
        data=clients.to_csv(index=False, sep=";").encode("utf-8"),
        file_name="clients.csv",
        mime="text/csv",
    )

# ============================== ADMIN ==============================
def _hard_reload():
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass
    for k in list(st.session_state.keys()):
        try:
            del st.session_state[k]
        except Exception:
            pass
    try:
        st.experimental_set_query_params(_ts=str(int(time.time())))
    except Exception:
        pass
    st.experimental_rerun()

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
            st.cache_data.clear(); st.success("Fichier restauré. Rechargement…"); st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    if st.sidebar.button("🧹 Vider le cache / Recharger", use_container_width=True):
        _hard_reload()

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