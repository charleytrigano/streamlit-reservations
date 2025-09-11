# -*- coding: utf-8 -*-
# ✨ Villa Tobias — Réservations (app.py) — version robuste

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# Purge douce au démarrage (ne plante pas si indispo)
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

FORM_SHORT_URL = "https://urlr.me/kZuH94"

# ============================== STYLE ==============================
def apply_style(light: bool):
    bg = "#fafafa" if light else "#0e1117"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    st.markdown(
        f"""
        <style>
          [data-testid="stAppViewContainer"]{{background:{bg};color:{fg};}}
          [data-testid="stSidebar"]{{background:{side};border-right:1px solid {border};}}
          .chip {{
            display:inline-block;margin:4px 6px;padding:6px 10px;
            border-radius:12px;border:1px solid {border};font-size:0.85rem
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

# ============================== HELPERS ==============================
def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff","")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 2:
                return df
        except Exception:
            continue
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _to_bool_series(s) -> pd.Series:
    if isinstance(s, pd.Series):
        base = s
    elif s is None:
        base = pd.Series([], dtype="object")
    else:
        base = pd.Series(s)
    vals = base.astype(str).str.strip().str.lower()
    return vals.isin(["true","1","oui","vrai","yes","y","t"])

def _to_num(s) -> pd.Series:
    if isinstance(s, pd.Series):
        base = s.astype(str)
    elif s is None:
        base = pd.Series([], dtype="object")
    else:
        base = pd.Series(s).astype(str)
    sc = (base
          .str.replace("€","", regex=False)
          .str.replace(" ", "", regex=False)
          .str.replace(",", ".", regex=False)
          .str.strip())
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s) -> pd.Series:
    # Accepte JJ/MM/AAAA, AAAA-MM-JJ, JJ-MM-AAAA…
    if isinstance(s, pd.Series):
        ser = s
    elif s is None:
        ser = pd.Series([], dtype="object")
    else:
        ser = pd.Series(s)
    d = pd.to_datetime(ser, errors="coerce", dayfirst=True)
    # fallback explicite Y-M-D si besoin
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(ser, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

# ============================== NORMALISATION ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid","AAAA","MM"
]

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Alias tolerants
    alias = {
        'Payé':'paye','Client':'nom_client','Plateforme':'plateforme',
        'Arrivée':'date_arrivee','Départ':'date_depart','Nuits':'nuitees',
        'Brut (€)':'prix_brut','brut':'prix_brut','Brut':'prix_brut',
        'AAA':'AAAA','MM ':'MM','aaaa':'AAAA','mm':'MM'
    }
    df.rename(columns=alias, inplace=True)

    # Créer les colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Types
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","base","charges","%"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Nuitées (recalcule si possible)
    mask_ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0)
    except Exception:
        pass

    # Net / charges / base / %
    prix_brut = _to_num(df["prix_brut"]).fillna(0)
    commissions = _to_num(df["commissions"]).fillna(0)
    frais_cb = _to_num(df["frais_cb"]).fillna(0)
    menage = _to_num(df["menage"]).fillna(0)
    taxes = _to_num(df["taxes_sejour"]).fillna(0)

    df["prix_net"] = (prix_brut - commissions - frais_cb).fillna(0)
    df["charges"]  = (prix_brut - df["prix_net"]).fillna(0)
    df["base"]     = (df["prix_net"] - menage - taxes).fillna(0)

    denom = prix_brut.replace(0, np.nan)
    pct = (df["charges"] / denom) * 100
    df["%"] = pct.fillna(0.0)

    # AAAA/MM : si absents, déduire des dates
    da_all = pd.to_datetime(df["date_arrivee"], errors="coerce")
    if "AAAA" in df.columns:
        years = pd.to_numeric(df["AAAA"], errors="coerce")
    else:
        years = pd.Series(dtype="float64")
    if years.isna().all():
        years = da_all.dt.year
    df["AAAA"] = pd.to_numeric(years, errors="coerce")

    if "MM" in df.columns:
        months = pd.to_numeric(df["MM"], errors="coerce")
    else:
        months = pd.Series(dtype="float64")
    if months.isna().all():
        months = da_all.dt.month
    df["MM"] = pd.to_numeric(months, errors="coerce")

    # IDs
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]
    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid, "ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # Strings propres
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = df[c].astype(str).replace({"nan":"","None":""}).str.strip()

    return df[BASE_COLS]

# ============================== CHARGEMENT ==============================
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
    base_df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
    df = ensure_schema(base_df)

    rawp = _load_file_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if rawp:
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

# ============================= VUES ============================.                  def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfn = ensure_schema(df)
    dfn["date_arrivee"] = _to_date(dfn["date_arrivee"])
    dfn["date_depart"]  = _to_date(dfn["date_depart"])

    arr = dfn[dfn["date_arrivee"] == today][["nom_client","telephone","plateforme"]].copy()
    dep = dfn[dfn["date_depart"]  == today][["nom_client","telephone","plateforme"]].copy()

    st.subheader("🟢 Arrivées du jour")
    st.dataframe(arr, use_container_width=True) if not arr.empty else st.info("Aucune arrivée.")

    st.subheader("🔴 Départs du jour")
    st.dataframe(dep, use_container_width=True) if not dep.empty else st.info("Aucun départ.")

def _years_months_fallback(dfn: pd.DataFrame):
    """Retourne (years_list, months_list) robustes, sans jamais planter."""
    # Prend AAAA/MM si valides, sinon dérive des dates
    try:
        y_ser = dfn["AAAA"] if "AAAA" in dfn.columns else pd.Series(dtype="float64")
        if isinstance(y_ser, np.ndarray):
            y_ser = pd.Series(y_ser)
        y_ser = pd.to_numeric(y_ser, errors="coerce")
    except Exception:
        y_ser = pd.Series(dtype="float64")

    try:
        m_ser = dfn["MM"] if "MM" in dfn.columns else pd.Series(dtype="float64")
        if isinstance(m_ser, np.ndarray):
            m_ser = pd.Series(m_ser)
        m_ser = pd.to_numeric(m_ser, errors="coerce")
    except Exception:
        m_ser = pd.Series(dtype="float64")

    if y_ser.dropna().empty or m_ser.dropna().empty:
        da = pd.to_datetime(dfn["date_arrivee"], errors="coerce")
        if y_ser.dropna().empty:
            y_ser = da.dt.year
        if m_ser.dropna().empty:
            m_ser = da.dt.month

    years  = sorted(y_ser.dropna().astype(int).unique().tolist(), reverse=True)
    months = sorted(m_ser.dropna().astype(int).unique().tolist())
    if not months:
        months = list(range(1,13))
    return years, months

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfn = ensure_schema(df)

    years_list, months_list = _years_months_fallback(dfn)
    plats_list = sorted(
        dfn["plateforme"].astype(str).str.strip().replace({"nan":"", "None":""}).replace("", np.nan).dropna().unique()
    )

    col1, col2, col3 = st.columns(3)
    year  = col1.selectbox("Année", ["Toutes"] + years_list, index=0)
    month = col2.selectbox("Mois",  ["Tous"]   + months_list, index=0)
    plat  = col3.selectbox("Plateforme", ["Toutes"] + plats_list, index=0)

    data = dfn.copy()
    if year  != "Toutes": data = data[pd.to_numeric(data["AAAA"], errors="coerce").fillna(-1).astype(int) == int(year)]
    if month != "Tous":   data = data[pd.to_numeric(data["MM"],   errors="coerce").fillna(-1).astype(int) == int(month)]
    if plat  != "Toutes": data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]

    brut    = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net     = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    base    = float(pd.to_numeric(data["base"],      errors="coerce").fillna(0).sum())
    charges = float(pd.to_numeric(data["charges"],   errors="coerce").fillna(0).sum())
    nuits   = int(pd.to_numeric(data["nuitees"],     errors="coerce").fillna(0).sum())
    adr     = (net/nuits) if nuits>0 else 0.0

    st.markdown(
        f"""
        <div class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></div>
        <div class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></div>
        <div class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></div>
        <div class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></div>
        <div class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></div>
        <div class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></div>
        """.replace(",", " "),
        unsafe_allow_html=True
    )
    st.markdown("---")

    if "date_arrivee" in data.columns:
        order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
        data = data.loc[order]

    st.dataframe(data, use_container_width=True)

def vue_plateformes(df, palette):
    st.header("🎨 Plateformes & couleurs")
    base = pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    c1, c2 = st.columns([0.6,0.4])
    if c1.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
            st.success("Palette enregistrée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
    if c2.button("↩️ Restaurer palette par défaut"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(
                CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8"
            )
            st.success("Palette par défaut restaurée."); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")
    dfn = ensure_schema(df)
    dfn = dfn.dropna(subset=['date_arrivee','date_depart']).copy()
    if dfn.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(pd.to_datetime(dfn["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    st.markdown(
        "<div style='display:grid;grid-template-columns:repeat(7,1fr);font-weight:700;opacity:.8;margin-top:10px'>"
        "<div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div>"
        "</div>", unsafe_allow_html=True
    )

    dfn["date_arrivee"] = _to_date(dfn["date_arrivee"])
    dfn["date_depart"]  = _to_date(dfn["date_depart"])

    def day_resas(d):
        mask = (dfn['date_arrivee'] <= d) & (dfn['date_depart'] > d)
        return dfn[mask]

    cal = Calendar(firstweekday=0)  # lundi
    html = ["<div style='display:grid;grid-template-columns:repeat(7,1fr);gap:8px;margin-top:8px'>"]
    for week in cal.monthdatescalendar(annee, mois):
        for d in week:
            outside = (d.month != mois)
            op = "opacity:.45" if outside else ""
            cell = f"<div style='border:1px solid rgba(124,92,255,.16);border-radius:10px;min-height:110px;padding:8px;{op};position:relative;overflow:hidden;background:rgba(255,255,255,0.04)'>"
            cell += f"<div style='position:absolute;top:6px;right:8px;font-weight:700;font-size:.9rem;opacity:.7'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                for _, r in rs.iterrows():
                    color = palette.get(r.get('plateforme'), '#888')
                    name  = str(r.get('nom_client') or '')[:22]
                    cell += f"<div style='margin-top:22px;padding:4px 6px;border-radius:6px;font-size:.85rem;color:#fff;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Détail du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfn[(dfn['date_arrivee'] <= fin_mois) & (dfn['date_depart'] > debut_mois)].copy()
    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
        return
    plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
    plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
    if plat != "Toutes":
        rows = rows[rows["plateforme"]==plat]
    brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(rows["prix_net"],  errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(rows["nuitees"],    errors="coerce").fillna(0).sum())
    st.markdown(
        f"""
        <div class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></div>
        <div class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></div>
        <div class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></div>
        """.replace(",", " "), unsafe_allow_html=True
    )
    st.dataframe(rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)

def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df.empty:
        st.info("Aucune donnée."); return
    years = sorted(pd.to_numeric(df["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    if not years:
        st.info("Aucune année détectée."); return
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
        st.warning("Aucune donnée après filtres."); return

    data["mois"] = pd.to_datetime(data["date_arrivee"], errors="coerce").dt.to_period("M").astype(str)
    agg = data.groupby(["mois","plateforme"], as_index=False).agg({metric:"sum"})
    total_val = float(pd.to_numeric(agg[metric], errors="coerce").fillna(0).sum())
    st.markdown(f"**Total {metric.replace('_',' ')} : {total_val:,.2f}**".replace(",", " "))
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

    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")

    dfn = ensure_schema(df).copy()
    dfn["sms_envoye"] = _to_bool_series(dfn["sms_envoye"]).fillna(False).astype(bool)
    dfn["date_arrivee"] = _to_date(dfn["date_arrivee"])
    dfn["date_depart"]  = _to_date(dfn["date_depart"])

    pre = dfn.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
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
                f"VILLA TOBIAS\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  "
                f"Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')}  "
                f"Nuitées : {int(r.get('nuitees') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')}\n"
                "Merci de nous indiquer votre heure d'arrivée. Parking possible.\n"
                "Check-in 14:00, check-out 11:00.\n\n"
                f"Fiche d'arrivée : {FORM_SHORT_URL}\n\n"
                "EN — Please tell us your arrival time. Parking on request.\n"
                "Check-in from 2pm, check-out before 11am."
            )
            enc = quote(msg); e164 = _format_phone_e164(r["telephone"]); wa = re.sub(r"\D","", e164)
            st.text_area("Prévisualisation", value=msg, height=220)
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")

    dfn["post_depart_envoye"] = _to_bool_series(dfn["post_depart_envoye"]).fillna(False).astype(bool)
    post = dfn.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post["date_depart"] = _to_date(post["date_depart"])
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
                "Annick & Charley\n"
                f"\nHello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n\n"
                "We hope you had as enjoyable a time as we did hosting you.\n\n"
                "If you feel like coming back to explore our city a little more, know that our door will always be open to you.\n\n"
                "We look forward to welcoming you back.\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2); e164b = _format_phone_e164(r2["telephone"]); wab = re.sub(r"\D","", e164b)
            st.text_area("Prévisualisation post-départ", value=msg2, height=200)
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
    years = sorted(pd.to_numeric(df["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    if not years:
        st.info("Aucune année détectée."); return
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

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
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"),
                       file_name=f"reservations_{year}.ics", mime="text/calendar")

def vue_clients(df, palette):
    st.header("👥 Clients")
    if df.empty:
        st.info("Aucun client."); return
    dfn = ensure_schema(df)
    clients = (dfn[['nom_client','telephone','email','plateforme','res_id']].copy())
    for c in ["nom_client","telephone","email","plateforme","res_id"]:
        clients[c] = clients[c].astype(str).replace({"nan":"","None":""}).str.strip()
    clients = clients.loc[clients["nom_client"] != ""]
    if clients.empty:
        st.info("Aucun client exploitable."); return
    clients = clients.drop_duplicates().sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)

# ============================== ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    st.sidebar.download_button(
        "Télécharger CSV",
        data=ensure_schema(df).to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            content = up.read()
            tmp = _detect_delimiter_and_read(content)
            tmp = ensure_schema(tmp)
            out = tmp.copy()
            for col in ["date_arrivee","date_depart"]:
                out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
            out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.cache_data.clear()
            st.success("Fichier restauré. Rechargement…"); st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    if st.sidebar.button("🧹 Vider le cache & recharger"):
        try: st.cache_data.clear()
        except Exception: pass
        try: st.cache_resource.clear()
        except Exception: pass
        st.success("Cache vidé. Rechargement…")
        st.rerun()

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
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "👥 Clients": vue_clients,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()