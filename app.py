# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO

# =============== 0) CONFIG ===============
st.set_page_config(page_title="✨ Villa Tobias — Réservations (light)", page_icon="✨", layout="wide")

# Purge “douce” au chargement (compatible 1.35)
try:
    st.cache_data.clear()
except Exception:
    pass
try:
    st.cache_resource.clear()
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

FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# =============== 1) STYLE très simple (lisible sombre) ===============
def apply_style(light: bool):
    bg = "#0f1115" if not light else "#fafafa"
    fg = "#eaeef6" if not light else "#0f172a"
    side = "#171923" if not light else "#f2f2f2"
    border = "rgba(124,92,255,.16)" if not light else "rgba(17,24,39,.08)"
    st.markdown(
        f"""
        <style>
          :root {{ color-scheme: {'dark' if not light else 'light'}; }}
          html, body, [data-testid="stAppViewContainer"] {{ background: {bg}; color: {fg}; }}
          [data-testid="stSidebar"] {{ background: {side}; border-right: 1px solid {border}; }}
          .glass {{
            background: {"rgba(255,255,255,0.06)" if not light else "rgba(255,255,255,0.65)"};
            border: 1px solid {border}; border-radius: 12px; padding: 12px; margin: 8px 0;
          }}
          .kpi {{ display:inline-block; padding:6px 10px; border-radius:10px; margin:4px 6px; 
                  background:rgba(127,127,127,.12); font-size:.92rem }}
          .kpi b {{ font-size:1.02rem }}
          .small {{ font-size:.9rem; opacity:.8 }}
        </style>
        """,
        unsafe_allow_html=True
    )

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)

# =============== 2) UTILITAIRES DATA ===============
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid","AAAA","MM"
]

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: 
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    # Essais de séparateurs
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3:
                return df
        except Exception:
            pass
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _to_bool_series(s: pd.Series) -> pd.Series:
    if s is None or not hasattr(s, "astype"): 
        return pd.Series([], dtype=bool)
    return s.astype(str).str.strip().str.lower().isin(["true","1","oui","vrai","yes","y","t"])

def _to_num(s: pd.Series) -> pd.Series:
    if s is None or not hasattr(s, "astype"):
        return pd.Series([], dtype="float64")
    sc = (s.astype(str)
            .str.replace("€","", regex=False)
            .str.replace("\u00A0","", regex=False) # espaces insécables
            .str.replace(" ","", regex=False)
            .str.replace(",", ".", regex=False)
            .str.strip())
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    if s is None or not hasattr(s, "astype"):
        return pd.Series([], dtype="object")
    s = s.astype(str).str.strip().replace({"": np.nan, "nan": np.nan})
    # tentative 1 : dayfirst (JJ/MM/AAAA)
    d1 = pd.to_datetime(s, errors="coerce", dayfirst=True)
    # tentative 2 : Y-M-D
    d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
    # combine (prend d2 si d1 est NaT)
    d = d1.fillna(d2)
    return d.dt.date

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)
    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = pd.Series(dtype=object)

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)

    # Numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Nuitées recalcul si possible
    mask_ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    if mask_ok.any():
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0)

    # Prix dérivés
    df["prix_net"] = (_to_num(df["prix_brut"]) - _to_num(df["commissions"]) - _to_num(df["frais_cb"])).fillna(0.0)
    df["charges"]  = (_to_num(df["prix_brut"]) - _to_num(df["prix_net"])).fillna(0.0)
    df["base"]     = (_to_num(df["prix_net"]) - _to_num(df["menage"]) - _to_num(df["taxes_sejour"])).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        charges = _to_num(df["charges"])
        brut    = _to_num(df["prix_brut"])
        pct = pd.Series(np.where(brut>0, (charges/brut)*100, 0), index=df.index)
    df["%"] = pd.to_numeric(pct, errors="coerce").fillna(0.0)

    # AAAA/MM
    da_all = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = pd.to_numeric(da_all.dt.year, errors="coerce")
    df["MM"]   = pd.to_numeric(da_all.dt.month, errors="coerce")

    # IDs
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid, "ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # Strings propres
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = df[c].astype(str).replace({"nan":"", "None":""}).str.strip()

    return df[BASE_COLS]

@st.cache_data
def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

@st.cache_data
def charger_donnees():
    raw = _load_file_bytes(CSV_RESERVATIONS)
    if raw is not None:
        base_df = _detect_delimiter_and_read(raw)
    else:
        base_df = pd.DataFrame()
    df = ensure_schema(base_df)

    rawp = _load_file_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if set(["plateforme","couleur"]).issubset(pal_df.columns):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception:
            pass
    return df, palette

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde CSV : {e}")
        return False

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

# =============== 3) PAGES (légères) ===============
def vue_accueil(df, palette):
    st.header("🏠 Accueil (léger)")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    # Petit résumé seulement (pas de gros tableau au chargement)
    dfa = df.copy()
    dfa["date_arrivee"] = _to_date(dfa["date_arrivee"])
    dfa["date_depart"]  = _to_date(dfa["date_depart"])
    arr = dfa[dfa["date_arrivee"] == today][["nom_client","telephone","plateforme"]]
    dep = dfa[dfa["date_depart"]  == today][["nom_client","telephone","plateforme"]]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        if arr.empty: st.info("Aucune arrivée.")
        else:
            st.write(f"<div class='kpi'><b>{len(arr)}</b> arrivée(s)</div>", unsafe_allow_html=True)
            with st.expander("Voir la liste"):
                st.dataframe(arr, use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        if dep.empty: st.info("Aucun départ.")
        else:
            st.write(f"<div class='kpi'><b>{len(dep)}</b> départ(s)</div>", unsafe_allow_html=True)
            with st.expander("Voir la liste"):
                st.dataframe(dep, use_container_width=True)

def vue_reservations(df, palette):
    st.header("📋 Réservations (léger)")
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    years_ser  = pd.to_numeric(df["AAAA"], errors="coerce")
    months_ser = pd.to_numeric(df["MM"],   errors="coerce")
    years = ["Toutes"] + (sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True) if not years_ser.dropna().empty else [])
    months = ["Tous"] + (sorted(months_ser.dropna().astype(int).unique().tolist()) if not months_ser.dropna().empty else list(range(1,13)))
    plats  = ["Toutes"] + sorted(df["plateforme"].dropna().astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist())

    c1,c2,c3 = st.columns(3)
    year  = c1.selectbox("Année", years, index=0)
    month = c2.selectbox("Mois", months, index=0)
    plat  = c3.selectbox("Plateforme", plats, index=0)

    data = df.copy()
    if year != "Toutes":
        data = data[pd.to_numeric(data["AAAA"], errors="coerce").fillna(-1).astype(int) == int(year)]
    if month != "Tous":
        data = data[pd.to_numeric(data["MM"], errors="coerce").fillna(-1).astype(int) == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]

    # KPIs (petits)
    brut = float(pd.to_numeric(data["prix_brut"], errors="coerce").sum())
    net  = float(pd.to_numeric(data["prix_net"],  errors="coerce").sum())
    nuits= int(pd.to_numeric(data["nuitees"],     errors="coerce").sum())
    adr  = (net/nuits) if nuits>0 else 0.0
    st.markdown(
        f"<div class='glass'>"
        f"<span class='kpi'><small>Total brut</small><br><b>{brut:,.2f} €</b></span>"
        f"<span class='kpi'><small>Total net</small><br><b>{net:,.2f} €</b></span>"
        f"<span class='kpi'><small>Nuitées</small><br><b>{nuits}</b></span>"
        f"<span class='kpi'><small>ADR net</small><br><b>{adr:,.2f} €</b></span>"
        f"</div>".replace(",", " "),
        unsafe_allow_html=True
    )

    with st.expander("Afficher le tableau (paresseux)"):
        if "date_arrivee" in data.columns:
            order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
            data = data.loc[order]
        st.dataframe(data, use_container_width=True)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter")
    with st.form("form_add", clear_on_submit=True):
        c1,c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom du client")
            email = st.text_input("Email (souvent reçu via fiche d’arrivée)")
            tel = st.text_input("Téléphone")
            arr = st.date_input("Arrivée", date.today())
            dep = st.date_input("Départ", date.today()+timedelta(days=1))
        with c2:
            plat = st.selectbox("Plateforme", list(palette.keys()))
            brut = st.number_input("Prix brut €", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions €", min_value=0.0, step=0.01)
            frais_cb = st.number_input("Frais CB €", min_value=0.0, step=0.01)
            menage = st.number_input("Ménage €", min_value=0.0, step=0.01)
            taxes = st.number_input("Taxes séjour €", min_value=0.0, step=0.01)
            paye = st.checkbox("Payé", value=False)
        if st.form_submit_button("✅ Ajouter"):
            if not nom or dep <= arr:
                st.error("Nom et dates valides requis.")
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
                    st.success("Ajouté ✅"); st.rerun()

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer")
    if df.empty:
        st.info("Aucune réservation."); return
    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client','')} ({r.get('date_arrivee','')})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez", options=options, index=None)
    if not sel: return
    idx = int(sel.split(":")[0]); original_idx = df_sorted.loc[idx, "index"]; row = df.loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1,c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get("nom_client","") or "")
            email = st.text_input("Email", value=row.get("email","") or "")
            tel = st.text_input("Téléphone", value=row.get("telephone","") or "")
            arrivee = st.date_input("Arrivée", value=row.get("date_arrivee"))
            depart  = st.date_input("Départ", value=row.get("date_depart"))
        with c2:
            keys = list(palette.keys())
            plat = st.selectbox("Plateforme", options=keys, index= keys.index(row.get("plateforme")) if row.get("plateforme") in keys else 0)
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=float(row.get("prix_brut") or 0))
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=float(row.get("commissions") or 0))
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=float(row.get("frais_cb") or 0))
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=float(row.get("menage") or 0))
            taxes  = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=float(row.get("taxes_sejour") or 0))
        b1,b2 = st.columns([0.7,0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            for k,v in {"nom_client":nom, "email":email, "telephone":tel, "date_arrivee":arrivee, "date_depart":depart,
                        "plateforme":plat, "paye":paye, "prix_brut":brut, "commissions":commissions,
                        "frais_cb":frais_cb, "menage":menage, "taxes_sejour":taxes}.items():
                df.loc[original_idx, k] = v
            if sauvegarder_donnees(ensure_schema(df)):
                st.success("Modifié ✅"); st.rerun()
        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé."); st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Plateformes & couleurs (léger)")
    base = pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"])
    with st.expander("Afficher / éditer", expanded=False):
        edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
        c1,c2 = st.columns([0.6,0.4])
        if c1.button("💾 Enregistrer la palette"):
            try:
                edited.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
                st.success("Palette enregistrée ✅"); st.rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")
        if c2.button("↩️ Palette par défaut"):
            try:
                pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
                st.success("Palette par défaut restaurée ✅"); st.rerun()
            except Exception as e:
                st.error(f"Erreur : {e}")

def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle — léger)")
    dfv = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if dfv.empty:
        st.info("Aucune réservation."); return

    years = sorted(pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    today = date.today()
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    with st.expander("Afficher le calendrier", expanded=False):
        st.markdown("<div class='small'>La grille s’affiche uniquement sur demande.</div>", unsafe_allow_html=True)
        def day_resas(d):
            mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
            return dfv[mask]
        cal = Calendar(firstweekday=0)
        html = ["<div class='glass'>"]
        html.append("<div style='display:grid;grid-template-columns:repeat(7,1fr);font-weight:700;opacity:.8;margin:6px 0'>"
                    "<div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>")
        html.append("<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:6px'>")
        for week in cal.monthdatescalendar(annee, mois):
            for d in week:
                outside = (d.month != mois)
                style = "opacity:.45;" if outside else ""
                cell = f"<div style='border:1px solid rgba(128,128,128,.25);border-radius:8px;min-height:90px;padding:6px;{style}'>"
                cell += f"<div style='text-align:right;opacity:.7;font-weight:700'>{d.day}</div>"
                if not outside:
                    rs = day_resas(d)
                    for _, r in rs.iterrows():
                        color = palette.get(r.get('plateforme'), '#888')
                        name  = str(r.get('nom_client') or '')[:22]
                        cell += f"<div title='{r.get('nom_client','')}' style='margin-top:8px;padding:3px 6px;border-radius:6px;background:{color};color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis'>{name}</div>"
                cell += "</div>"
                html.append(cell)
        html.append("</div></div>")
        st.markdown("".join(html), unsafe_allow_html=True)

    # Détail du mois (lazy)
    with st.expander("Détail du mois"):
        debut = date(annee, mois, 1)
        fin   = date(annee, mois, monthrange(annee, mois)[1])
        rows = dfv[(dfv['date_arrivee'] <= fin) & (dfv['date_depart'] > debut)].copy()
        if rows.empty: st.info("Aucune réservation sur ce mois.")
        else:
            plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
            plat = st.selectbox("Filtrer plateforme", plats, index=0, key="cal_plat")
            if plat != "Toutes": rows = rows[rows["plateforme"]==plat]
            brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").sum())
            net  = float(pd.to_numeric(rows["prix_net"],  errors="coerce").sum())
            nuits= int(pd.to_numeric(rows["nuitees"],    errors="coerce").sum())
            st.markdown(f"<div class='glass'>"
                        f"<span class='kpi'><small>Brut</small><br><b>{brut:,.2f} €</b></span>"
                        f"<span class='kpi'><small>Net</small><br><b>{net:,.2f} €</b></span>"
                        f"<span class='kpi'><small>Nuitées</small><br><b>{nuits}</b></span>"
                        f"</div>".replace(",", " "), unsafe_allow_html=True)
            st.dataframe(rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)

def vue_rapport(df, palette):
    st.header("📊 Rapport (léger)")
    if df.empty:
        st.info("Aucune donnée."); return
    years = sorted(pd.to_numeric(df["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1,13))
    month = st.selectbox("Mois", months, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)
    metric = st.selectbox("Métrique", ["prix_brut","prix_net","menage","nuitees"], index=0)

    data = df[pd.to_numeric(df["AAAA"], errors="coerce")==year].copy()
    if month!="Tous": data = data[pd.to_numeric(df["MM"], errors="coerce")==int(month)]
    if plat!="Tous":  data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Aucune donnée."); return

    with st.expander("Afficher les graphiques", expanded=False):
        data["mois"] = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.to_period("M").astype(str)
        agg = data.groupby(["mois","plateforme"], as_index=False).agg({metric:"sum"})
        total_val = float(pd.to_numeric(agg[metric], errors="coerce").sum())
        st.markdown(f"**Total {metric.replace('_',' ')} : {total_val:,.2f}**".replace(",", " "))
        chart = alt.Chart(agg).mark_bar().encode(
            x="mois:N",
            y=alt.Y(f"{metric}:Q", title=metric.replace("_"," ").title()),
            color="plateforme:N",
            tooltip=["mois","plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
        )
        st.altair_chart(chart.properties(height=360), use_container_width=True)
        st.dataframe(agg, use_container_width=True)

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp (léger)")
    # Pré-arrivée
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre["date_arrivee"] = _to_date(pre["date_arrivee"]); pre["date_depart"] = _to_date(pre["date_depart"])
    pre = pre[(pre["date_arrivee"]==target_arrivee) & (~pre["sms_envoye"])]
    if pre.empty:
        st.info("Aucun client.")
    else:
        pre["_rowid"] = pre.index
        pre = pre.sort_values("date_arrivee").reset_index(drop=True)
        opts = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=opts, index=None)
        if pick:
            i = int(pick.split(":")[0]); r = pre.loc[i]
            msg = (
                f"VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  "
                f"Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')}  "
                f"Nuitées : {int(r.get('nuitees') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')}\n"
                "Bienvenue ! Merci de nous indiquer votre heure d'arrivée.\n"
                "Parking sur demande. Check-in 14:00, check-out 11:00.\n\n"
                f"Formulaire d’arrivée : {FORM_SHORT_URL}\n\n"
                "Annick & Charley"
            )
            enc = quote(msg); e164 = _format_phone_e164(r["telephone"]); wa = re.sub(r"\D","", e164)
            st.text_area("Message", value=msg, height=160)
            c1,c2,c3 = st.columns(3)
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
    post["date_depart"] = _to_date(post["date_depart"])
    post = post[(post["date_depart"]==target_depart) & (~post["post_depart_envoye"])]
    if post.empty:
        st.info("Aucun message.")
    else:
        post["_rowid"] = post.index
        post = post.sort_values("date_depart").reset_index(drop=True)
        opts2 = [f"{i}: {r['nom_client']} — {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=opts2, index=None)
        if pick2:
            j = int(pick2.split(":")[0]); r2 = post.loc[j]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Merci d'avoir choisi notre appartement. Nous espérons que tout s'est bien passé !\n"
                "Vous êtes les bienvenus si vous revenez à Nice.\n\n"
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you for staying with us — you’re always welcome back!\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2); e164b = _format_phone_e164(r2["telephone"]); wab = re.sub(r"\D","", e164b)
            st.text_area("Message", value=msg2, height=160)
            c1,c2,c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                df.loc[r2["_rowid"], "post_depart_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (léger)")
    if df.empty:
        st.info("Aucune réservation."); return
    years = sorted(pd.to_numeric(df["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year = st.selectbox("Année", years, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat = st.selectbox("Plateforme", plats, index=0)
    data = df[pd.to_numeric(df["AAAA"], errors="coerce")==year].copy()
    if plat!="Tous": data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Rien à exporter."); return

    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if miss.any():
        data.loc[miss, "ical_uid"] = data[miss].apply(build_stable_uid, axis=1)

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
        da, dd = r["date_arrivee"], r["date_depart"]
        if not (isinstance(da, (date, datetime)) and isinstance(dd, (date, datetime))): 
            continue
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"): summary += f" ({r['plateforme']})"
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
            f"DTSTART;VALUE=DATE:{_fmt(da)}",
            f"DTEND;VALUE=DATE:{_fmt(dd)}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"
    with st.expander("Télécharger .ics", expanded=False):
        st.download_button("📥 Télécharger", data=ics.encode("utf-8"),
                           file_name=f"reservations_{year}.ics", mime="text/calendar")

def vue_google_sheet(df, palette):
    st.header("📝 Google Form / Sheet (léger)")
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")
    with st.expander("Afficher le formulaire (iframe)"):
        st.markdown(f'<iframe src="{GOOGLE_FORM_URL}" width="100%" height="900" frameborder="0"></iframe>', unsafe_allow_html=True)
    with st.expander("Afficher la feuille (iframe)"):
        st.markdown(f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>', unsafe_allow_html=True)
    with st.expander("Réponses (CSV publié)"):
        try:
            rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
            st.dataframe(rep, use_container_width=True)
        except Exception as e:
            st.error(f"Chargement impossible : {e}")

def vue_clients(df, palette):
    st.header("👥 Clients (léger)")
    if df.empty:
        st.info("Aucun client."); return
    clients = (df[['nom_client','telephone','email','plateforme','res_id']]
               .copy())
    # nettoyage
    for c in ["nom_client","telephone","email","plateforme","res_id"]:
        clients[c] = clients[c].astype(str).replace({"nan":""}).str.strip()
    clients = clients[clients["nom_client"]!=""].drop_duplicates()
    st.markdown(f"<div class='small'>Total : <b>{len(clients)}</b></div>", unsafe_allow_html=True)
    with st.expander("Afficher la liste"):
        st.dataframe(clients.sort_values("nom_client"), use_container_width=True)

# =============== 4) ADMIN ===============
def admin_sidebar(df):
    st.sidebar.markdown("## ⚙️ Administration")
    st.sidebar.download_button(
        "Télécharger CSV (séparateur ';')",
        data=ensure_schema(df).to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS, mime="text/csv"
    )
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            content = up.read()
            tmp_df = _detect_delimiter_and_read(content)
            tmp_df = ensure_schema(tmp_df)
            out = tmp_df.copy()
            for col in ["date_arrivee","date_depart"]:
                out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
            out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.cache_data.clear(); st.cache_resource.clear()
            st.success("Fichier restauré. Rechargement…"); st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    if st.sidebar.button("🧹 Vider le cache & recharger"):
        try: st.cache_data.clear()
        except Exception: pass
        try: st.cache_resource.clear()
        except Exception: pass
        st.success("Cache vidé. Rechargement…"); st.rerun()

# =============== 5) MAIN ===============
def main():
    # Thème “clair/sombre” toggle – pas de gros rendu au démarrage
    try:
        light = st.sidebar.toggle("Mode clair", value=False)
    except Exception:
        light = st.sidebar.checkbox("Mode clair", value=False)
    apply_style(light=bool(light))

    st.title("✨ Villa Tobias — Gestion des Réservations (version légère)")
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
        "📝 Google Sheet": vue_google_sheet,
        "👥 Clients": vue_clients,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()