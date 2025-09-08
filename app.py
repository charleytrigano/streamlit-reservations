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

CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

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

# ============================== DATA ==============================
BASE_COLS = [
    "paye","nom_client","sms_envoye","post_depart_envoye","plateforme","telephone","email",
    "date_arrivee","date_depart","nuitees","prix_brut","prix_net","commissions","frais_cb","menage","taxes_sejour",
    "res_id","ical_uid","AAAA","MM"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les colonnes et types (tolérant)."""
    if df is None or df.empty:
        return pd.DataFrame(columns=BASE_COLS)
    df = df.copy()

    # Renommage FR -> interne (si besoin)
    rename_map = {
        "Payé": "paye", "Paye": "paye",
        "Client": "nom_client", "Nom": "nom_client",
        "Plateforme": "plateforme",
        "Téléphone": "telephone", "Telephone": "telephone",
        "Email": "email",
        "Arrivée": "date_arrivee", "Arrivee": "date_arrivee",
        "Départ": "date_depart", "Depart": "date_depart",
        "Nuits": "nuitees", "Nuitées": "nuitees",
        "Brut (€)": "prix_brut", "Brut": "prix_brut",
        "Commissions": "commissions",
        "Frais CB": "frais_cb",
        "Ménage": "menage", "Menage": "menage",
        "Taxes séjour": "taxes_sejour", "Taxes sejour": "taxes_sejour",
        "UID": "ical_uid", "UID_ICS": "ical_uid",
    }
    df.rename(columns={c: rename_map.get(c, c) for c in df.columns}, inplace=True)

    # Dates -> date (on tente yearfirst puis dayfirst)
    for c in ["date_arrivee","date_depart"]:
        s = pd.to_datetime(df.get(c), errors="coerce", yearfirst=True)
        if s.isna().mean() > 0.5:
            s = pd.to_datetime(df.get(c), errors="coerce", dayfirst=True)
        df[c] = s.dt.date

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        if b not in df.columns: df[b] = False
        df[b] = df[b].astype(str).str.strip().str.lower().isin(["true","1","oui","vrai","yes"]).fillna(False)

    # Numériques (nettoyés)
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees"]:
        if n not in df.columns: df[n] = 0
        df[n] = (df[n].astype(str)
                 .str.replace("€","",regex=False).str.replace(",",".",regex=False)
                 .str.replace(" ","",regex=False))
        df[n] = pd.to_numeric(df[n], errors="coerce").fillna(0.0)

    # Prix net
    df["prix_net"] = df.get("prix_brut",0) - df.get("commissions",0) - df.get("frais_cb",0)

    # IDs
    if "res_id" not in df.columns: df["res_id"] = None
    if "ical_uid" not in df.columns: df["ical_uid"] = None
    miss = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss.any():
        df.loc[miss, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss.sum()))]

    # Année / Mois (depuis date_arrivee)
    dta = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = dta.dt.year
    df["MM"]   = dta.dt.month

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns: df[c] = None

    return df[BASE_COLS]

@st.cache_data
def charger_donnees():
    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=";")
    except Exception:
        df = pd.DataFrame()
    df = ensure_schema(df)

    try:
        df_pal = pd.read_csv(CSV_PLATEFORMES, delimiter=";")
        palette = dict(zip(df_pal["plateforme"], df_pal["couleur"]))
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

def _ensure_year_month(df: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(df, pd.DataFrame) or df.empty:
        return df
    dta = pd.to_datetime(df.get("date_arrivee"), errors="coerce")
    if "AAAA" not in df.columns: df["AAAA"] = dta.dt.year
    if "MM"   not in df.columns: df["MM"]   = dta.dt.month
    return df

def _years_from_dates(df: pd.DataFrame):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return []
    yrs = pd.to_datetime(df.get("date_arrivee"), errors="coerce").dt.year.dropna()
    yrs = yrs.astype(int).unique().tolist()
    yrs.sort(reverse=True)
    return yrs

# ============================== VUES ==============================
def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if not isinstance(df, pd.DataFrame) or df.empty:
        st.info("Aucune réservation.")
        return

    # Toujours recalculer année/mois depuis date_arrivee
    dta = pd.to_datetime(df.get("date_arrivee"), errors="coerce")
    df = df.copy()
    df["__year"]  = dta.dt.year
    df["__month"] = dta.dt.month

    # Filtres (robustes si aucune année trouvée)
    years = sorted([int(y) for y in df["__year"].dropna().unique()], reverse=True)
    if not years:
        st.warning("Aucune date d'arrivée valide dans vos données.")
        st.dataframe(df, use_container_width=True)
        return

    annee_sel = st.sidebar.selectbox("Année", ["Toutes"] + years, index=0)
    mois_sel  = st.sidebar.selectbox("Mois", ["Tous"] + list(range(1, 12+1)), index=0)
    plats_all = sorted(df.get("plateforme", pd.Series(dtype=str)).dropna().astype(str).unique().tolist())
    plat_sel  = st.sidebar.selectbox("Plateforme", ["Toutes"] + plats_all, index=0)

    data = df.copy()
    if annee_sel != "Toutes":
        data = data[data["__year"] == int(annee_sel)]
    if mois_sel != "Tous":
        data = data[data["__month"] == int(mois_sel)]
    if plat_sel != "Toutes":
        data = data[data["plateforme"] == plat_sel]

    if data.empty:
        st.info("Aucune ligne après filtres.")
        return

    # KPI
    brut = float(pd.to_numeric(data.get("prix_brut", 0), errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(data.get("prix_net", 0), errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(data.get("nuitees", 0), errors="coerce").fillna(0).sum())
    adr  = (net/nuits) if nuits > 0 else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Revenu brut", f"{brut:,.2f} €".replace(",", " "))
    c2.metric("Revenu net",  f"{net:,.2f} €".replace(",", " "))
    c3.metric("Nuitées",     f"{nuits}")
    c4.metric("ADR (net)",   f"{adr:,.2f} €".replace(",", " "))

    cols_order = [c for c in [
        "paye","nom_client","plateforme","telephone","email",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour"
    ] if c in data.columns]
    st.dataframe(
        data.sort_values("date_arrivee", ascending=False)[cols_order],
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
            dep = st.date_input("Départ", date.today() + timedelta(days=1))
        with c2:
            plat = st.selectbox("Plateforme", list(palette.keys()))
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye = st.checkbox("Payé", value=False)

        submitted = st.form_submit_button("✅ Ajouter")
        if submitted:
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
                st.success("Modifié ✅")
                st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé.")
                st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Plateformes & couleurs")
    base = pd.DataFrame(list(palette.items()), columns=["plateforme", "couleur"])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    if st.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette enregistrée ✅")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

# --------- CALENDRIER EN GRILLE ----------
def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")
    dfv = df.dropna(subset=['date_arrivee', 'date_depart']).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    years = _years_from_dates(dfv)
    today = date.today()
    annee = st.selectbox("Année", options=years if years else [today.year], index=0 if years else 0)
    mois  = st.selectbox("Mois", options=list(range(1, 13)), index=today.month - 1)

    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True
    )

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
                        color = palette.get(r.get('plateforme'), '#888')
                        name  = str(r.get('nom_client') or '')[:22]
                        cell += f"<div class='resa-pill' style='background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Détails du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    mois_rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()
    if mois_rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        mois_rows = mois_rows.sort_values("date_arrivee")
        st.dataframe(
            mois_rows[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "paye"]],
            use_container_width=True
        )

def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if not isinstance(df, pd.DataFrame) or df.empty:
        st.info("Aucune donnée.")
        return

    df = _ensure_year_month(df)
    years  = _years_from_dates(df)
    if not years:
        st.info("Pas d'années détectées (dates manquantes).")
        return

    year   = st.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1, 13))
    month  = st.selectbox("Mois", months, index=0)
    plats  = ["Tous"] + sorted(df.get("plateforme", pd.Series(dtype=str)).dropna().unique().tolist())
    plat   = st.selectbox("Plateforme", plats, index=0)
    metric = st.selectbox("Métrique", ["prix_brut", "prix_net", "menage", "nuitees"], index=0)

    data = df.copy()
    data["year"]  = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.year
    data["month"] = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.month
    data = data[data["year"] == year]
    if month != "Tous":
        data = data[data["month"] == int(month)]
    if plat  != "Tous":
        data = data[data["plateforme"] == plat]
    if data.empty:
        st.warning("Aucune donnée après filtres.")
        return

    data["mois"] = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.to_period("M").astype(str)
    agg = data.groupby(["mois", "plateforme"], as_index=False).agg({metric: "sum"})

    c1, c2 = st.columns(2)
    c1.metric("Total " + metric.replace("_", " "), f"{float(agg[metric].sum()):,.2f}".replace(",", " "))
    c2.metric("Séjours", len(data))

    st.dataframe(agg, use_container_width=True)

    chart = alt.Chart(agg).mark_bar().encode(
        x="mois:N",
        y=alt.Y(f"{metric}:Q", title=metric.replace("_", " ").title()),
        color="plateforme:N",
        tooltip=["mois", "plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True)

# ---- util bouton copier (JS)
def _copy_button_js(label: str, payload: str, key: str = ""):
    st.components.v1.html(
        f"""
        <button onclick="navigator.clipboard.writeText({json.dumps(payload)})"
                style="padding:8px 12px;border-radius:10px;border:1px solid rgba(127,127,127,.35);
                       background:#222;color:#fff;cursor:pointer;margin-top:6px">
            {label}
        </button>
        """,
        height=40,
    )

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # -------- Pré-arrivée (arrivées J+1)
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=["telephone", "nom_client", "date_arrivee"]).copy()
    pre["date_arrivee"] = pd.to_datetime(pre["date_arrivee"], errors="coerce").dt.date
    pre["date_depart"]  = pd.to_datetime(pre["date_depart"], errors="coerce").dt.date
    if "sms_envoye" not in pre.columns: pre["sms_envoye"] = False
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (~pre["sms_envoye"])]

    if pre.empty:
        st.info("Aucun client à contacter pour la date choisie.")
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
                "Nous sommes ravis de vous accueillir bientôt à Nice. Merci de nous indiquer votre heure d'arrivée.\n\n"
                "➡️ Place de parking disponible. Check-in 14:00, check-out 11:00.\n"
                f"Merci de remplir la fiche : {FORM_SHORT_URL}\n\n"
                "EN — Please tell us your arrival time. Parking on request. "
                "Check-in from 2pm, check-out before 11am. "
                f"Form: {FORM_SHORT_URL}\n\n"
                "Annick & Charley"
            )
            enc = quote(msg)
            e164 = _format_phone_e164(r["telephone"])
            wa   = re.sub(r"\D", "", e164)

            st.text_area("Prévisualisation", value=msg, height=220)
            _copy_button_js("📋 Copier le message", msg, key=f"cpy_pre_{i}")

            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")

            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅")
                    st.rerun()

    st.markdown("---")

    # -------- Post-départ (départs du jour)
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = df.dropna(subset=["telephone", "nom_client", "date_depart"]).copy()
    post["date_depart"] = pd.to_datetime(post["date_depart"], errors="coerce").dt.date
    if "post_depart_envoye" not in post.columns: post["post_depart_envoye"] = False
    post = post[(post["date_depart"] == target_depart) & (~post["post_depart_envoye"])]

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
                "Un grand merci d'avoir choisi notre appartement pour votre séjour.\n"
                "Nous espérons que vous avez passé un moment agréable.\n"
                "Si vous souhaitez revenir, notre porte vous sera toujours grande ouverte.\n\n"
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay. "
                "We hope you had a great time — you're always welcome back!\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2)
            e164b = _format_phone_e164(r2["telephone"])
            wab   = re.sub(r"\D", "", e164b)

            st.text_area("Prévisualisation post-départ", value=msg2, height=200)
            _copy_button_js("📋 Copier le message", msg2, key=f"cpy_post_{j}")

            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")

            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                df.loc[r2["_rowid"], "post_depart_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅")
                    st.rerun()

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    if not isinstance(df, pd.DataFrame) or df.empty:
        st.info("Aucune réservation.")
        return

    years = _years_from_dates(df)
    if not years:
        st.warning("Impossible de déterminer les années (dates manquantes).")
        return
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df.get("plateforme", pd.Series(dtype=str)).dropna().unique().tolist())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    data["year"] = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.year
    data = data[data["year"] == year]
    if plat != "Tous":
        data = data[data["plateforme"] == plat]
    if data.empty:
        st.warning("Rien à exporter.")
        return

    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip() == "")
    if miss.any():
        data.loc[miss, "ical_uid"] = data[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _fmt(d): return f"{d.year:04d}{d.month:02d}{d.day:02d}"

    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Villa Tobias//Reservations//FR", "CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r["date_arrivee"], r["date_depart"]
        if not (isinstance(da, date) and isinstance(dd, date)): continue
        summary = f"Villa Tobias — {r.get('nom_client', 'Sans nom')}"
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
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"),
                       file_name=f"reservations_{year}.ics", mime="text/calendar")

# ============================== IMPORT / RESTORE CSV ==============================
def _read_csv_loose(file_bytes: bytes) -> pd.DataFrame:
    errors = []
    for enc in ("utf-8-sig", "utf-8", "cp1252"):
        for sep in (";", ","):
            try:
                df = pd.read_csv(pd.io.common.BytesIO(file_bytes), encoding=enc, sep=sep)
                if isinstance(df, pd.DataFrame):
                    return df
            except Exception as e:
                errors.append(f"[{enc} / '{sep}'] {e}")
    raise ValueError("Impossible de lire le CSV avec encodages/séparateurs classiques.\n" + "\n".join(errors))

def _normalize_dates_ymd(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in ("date_arrivee", "date_depart", "Arrivée", "Arrivee", "Départ", "Depart"):
        if c in df.columns:
            s = pd.to_datetime(df[c], errors="coerce", yearfirst=True)
            if s.isna().mean() > 0.5:
                s = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
            df[c] = s.dt.date
    return df

def vue_import_csv(df_current, palette):
    st.header("🛠️ Import / Restaurer CSV")
    st.write("Charge un **CSV de réservations** (dates `AAAA/mm/dd` acceptées). Le fichier est **validé** avant d'écraser `reservations.csv`.")
    uploaded = st.file_uploader("Sélectionne ton fichier CSV", type=["csv"])
    if not uploaded:
        st.info("Choisis un fichier pour continuer.")
        return
    try:
        raw = uploaded.getvalue()
        df_raw = _read_csv_loose(raw)
        df_raw = _normalize_dates_ymd(df_raw)
        df_norm = ensure_schema(df_raw)
    except Exception as e:
        st.error(f"Lecture impossible : {e}")
        return

    required = {"nom_client", "plateforme", "date_arrivee", "date_depart"}
    missing = required - set(df_norm.columns)
    if missing:
        st.error(f"Colonnes manquantes : {missing}")
        st.stop()

    st.subheader("Aperçu (après normalisation)")
    st.dataframe(df_norm.head(30), use_container_width=True)

    c1, c2 = st.columns([1,1])
    with c1:
        st.caption("Lignes détectées : {}".format(len(df_norm)))
        st.caption("Dates arrivées min/max : {} → {}".format(
            pd.to_datetime(df_norm["date_arrivee"], errors="coerce").min(),
            pd.to_datetime(df_norm["date_arrivee"], errors="coerce").max(),
        ))
    with c2:
        if st.button("✅ Écraser et restaurer maintenant"):
            try:
                df_norm.to_csv(CSV_RESERVATIONS, sep=";", index=False)
                st.cache_data.clear()
                st.success("CSV restauré avec succès. Rechargement…")
                st.rerun()
            except Exception as e:
                st.error(f"Échec de la restauration : {e}")

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

# ============================== ADMIN ==============================
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
            content = up.getvalue()
            df_test = _normalize_dates_ymd(_read_csv_loose(content))
            df_valid = ensure_schema(df_test)
            required = {"nom_client", "plateforme", "date_arrivee", "date_depart"}
            if not required.issubset(set(df_valid.columns)):
                raise ValueError(f"Colonnes manquantes : {required - set(df_valid.columns)}")
            df_valid.to_csv(CSV_RESERVATIONS, sep=";", index=False)
            st.cache_data.clear()
            st.success("Fichier restauré. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

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
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "📝 Google Sheet": vue_google_sheet,
        "🛠️ Import/Restaurer CSV": vue_import_csv,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()