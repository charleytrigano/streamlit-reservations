# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from io import StringIO
from datetime import date, datetime, timedelta
from calendar import monthrange
import re, uuid, hashlib

# ============================== CONFIG GÉNÉRALE ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

CSV_RESERVATIONS = "reservations.csv"

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Abritel": "#8e44ad",
    "Autre":   "#f59e0b",
}

# ============================== OUTILS GÉNÉRAUX ==============================
def _safe_clear_caches():
    try:
        st.cache_data.clear()
    except Exception:
        pass
    try:
        st.cache_resource.clear()
    except Exception:
        pass

def _detect_delimiter_and_read(raw_bytes: bytes) -> pd.DataFrame:
    """Essaie ; , tab | et fallback. Retourne DataFrame (dtype=str)."""
    if raw_bytes is None:
        return pd.DataFrame()
    txt = raw_bytes.decode("utf-8", errors="ignore")
    txt = txt.replace("\ufeff", "")
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

def _to_bool(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series([], dtype=bool)
    return s.astype(str).str.strip().str.lower().isin(
        ["true","1","oui","vrai","yes","y","t"]
    )

def _to_num(s: pd.Series) -> pd.Series:
    """Toujours renvoyer une Series pandas (jamais un ndarray)."""
    if s is None:
        return pd.Series([], dtype="float64")
    sc = (
        s.astype(str)
         .str.replace("€","",regex=False)
         .str.replace(" ","",regex=False)
         .str.replace(",",".",regex=False)
         .str.strip()
    )
    out = pd.to_numeric(sc, errors="coerce")
    return out

def _to_date(s: pd.Series) -> pd.Series:
    """Accepte JJ/MM/AAAA, AAAA-MM-JJ, JJ-MM-AAAA… et renvoie des objets date."""
    if s is None:
        return pd.Series([], dtype="object")
    # premier essai : dayfirst
    d1 = pd.to_datetime(s, errors="coerce", dayfirst=True)
    # si beaucoup de NaT, on retente en YMD
    if d1.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d1 = d1.fillna(d2)
    return d1.dt.date

# ============================== SCHEMA & CHARGEMENT ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","charges","base","%",
    "res_id","ical_uid","AAAA","MM"
]

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Normalise le DataFrame pour respecter BASE_COLS + calcule champs dérivés."""
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Colonnes manquantes -> ajout
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool(df[b]).fillna(False).astype(bool)

    # Numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","base","%"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Recalcul nuitées si possible
    mask_ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0)
    except Exception:
        pass

    # Prix net / charges / base / %
    prix_brut = _to_num(df["prix_brut"])
    commissions = _to_num(df["commissions"])
    frais_cb = _to_num(df["frais_cb"])
    menage = _to_num(df["menage"])
    taxes = _to_num(df["taxes_sejour"])

    df["prix_net"] = (prix_brut - commissions - frais_cb).fillna(0.0)
    df["charges"]  = (prix_brut - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - menage - taxes).fillna(0.0)

    # % = charges / brut * 100 (en évitant ndarray)
    denom = prix_brut.replace(0, np.nan)
    pct = df["charges"].divide(denom).multiply(100)
    pct = pct.replace([np.inf, -np.inf], np.nan).fillna(0.0)
    df["%"] = pct

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

    # Strings propres
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = df[c].astype(str).replace({"nan":"", "None":""}).str.strip()

    return df[BASE_COLS]

@st.cache_data
def _load_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

@st.cache_data
def charger_donnees():
    raw = _load_bytes(CSV_RESERVATIONS)
    base = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base)
    return df

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        _safe_clear_caches()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde CSV : {e}")
        return False

# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfn = ensure_schema(df).copy()
    dfn["date_arrivee"] = _to_date(dfn["date_arrivee"])
    dfn["date_depart"]  = _to_date(dfn["date_depart"])

    arr = dfn[dfn["date_arrivee"] == today][["nom_client","telephone","plateforme"]].copy()
    dep = dfn[dfn["date_depart"]  == today][["nom_client","telephone","plateforme"]].copy()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        if arr.empty: st.info("Aucune arrivée.")
        else: st.dataframe(arr, use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        if dep.empty: st.info("Aucun départ.")
        else: st.dataframe(dep, use_container_width=True)

def vue_reservations(df, palette):
    st.header("📋 Réservations")

    dfn = ensure_schema(df).copy()
    if dfn.empty:
        st.info("Aucune réservation.")
        return

    years_ser  = pd.to_numeric(dfn["AAAA"], errors="coerce")
    months_ser = pd.to_numeric(dfn["MM"],   errors="coerce")

    years  = ["Toutes"] + (sorted(years_ser.dropna().astype(int).unique(), reverse=True).tolist()
                           if not years_ser.dropna().empty else [])
    months = ["Tous"] + (sorted(months_ser.dropna().astype(int).unique()).tolist()
                         if not months_ser.dropna().empty else list(range(1,13)))
    plats  = ["Toutes"] + sorted(
        dfn["plateforme"].astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist()
    )

    colf1, colf2, colf3 = st.columns(3)
    year  = colf1.selectbox("Année", years, index=0)
    month = colf2.selectbox("Mois", months, index=0)
    plat  = colf3.selectbox("Plateforme", plats, index=0)

    data = dfn.copy()
    if year  != "Toutes": data = data[pd.to_numeric(data["AAAA"], errors="coerce").fillna(-1).astype(int)==int(year)]
    if month != "Tous":   data = data[pd.to_numeric(data["MM"],   errors="coerce").fillna(-1).astype(int)==int(month)]
    if plat  != "Toutes": data = data[data["plateforme"].astype(str).str.strip()==str(plat).strip()]

    # KPIs compacts
    brut = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    charges = float(pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum())
    base = float(pd.to_numeric(data["base"], errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(data["nuitees"], errors="coerce").fillna(0).sum())
    adr  = (net/nuits) if nuits>0 else 0.0

    kpi = f"""
    <div style="display:flex;flex-wrap:wrap;gap:8px;margin:6px 0">
      <span style="background:#eee;border-radius:10px;padding:6px 10px"><small>Brut</small><br><b>{brut:,.2f} €</b></span>
      <span style="background:#eee;border-radius:10px;padding:6px 10px"><small>Net</small><br><b>{net:,.2f} €</b></span>
      <span style="background:#eee;border-radius:10px;padding:6px 10px"><small>Charges</small><br><b>{charges:,.2f} €</b></span>
      <span style="background:#eee;border-radius:10px;padding:6px 10px"><small>Base</small><br><b>{base:,.2f} €</b></span>
      <span style="background:#eee;border-radius:10px;padding:6px 10px"><small>Nuitées</small><br><b>{nuits}</b></span>
      <span style="background:#eee;border-radius:10px;padding:6px 10px"><small>ADR (net)</small><br><b>{adr:,.2f} €</b></span>
    </div>
    """.replace(",", " ")
    st.markdown(kpi, unsafe_allow_html=True)
    st.markdown("---")

    # Tri par date_arrivee décroissante si dispo
    order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order]
    st.dataframe(data, use_container_width=True)

def vue_clients(df, palette):
    st.header("👥 Clients")
    dfn = ensure_schema(df).copy()
    if dfn.empty:
        st.info("Aucun client."); return
    clients = (dfn[['nom_client','telephone','email','plateforme','res_id']]
               .copy())
    for c in ["nom_client","telephone","email","plateforme","res_id"]:
        clients[c] = clients[c].astype(str).replace({"nan":""}).str.strip()
    clients = clients[clients["nom_client"]!=""]
    clients = clients.drop_duplicates().sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)

def vue_export_ics(df, palette):
    st.header("📆 Export ICS")
    dfn = ensure_schema(df).copy()
    if dfn.empty:
        st.info("Aucune réservation."); return

    years = sorted(pd.to_numeric(dfn["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(dfn["plateforme"].astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfn[pd.to_numeric(dfn["AAAA"], errors="coerce")==year].copy()
    if plat!="Tous": data = data[data["plateforme"].astype(str).str.strip()==plat.strip()]
    if data.empty:
        st.warning("Rien à exporter."); return

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

# ============================== ADMIN (SIDEBAR) ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    # Export rapide (CSV normalisé)
    st.sidebar.download_button(
        "⬇️ Télécharger CSV normalisé",
        data=ensure_schema(df).to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )

    # Restauration (accepte ; , tab)
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
            _safe_clear_caches()
            st.success("Fichier restauré. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    if st.sidebar.button("🧹 Vider le cache & recharger"):
        _safe_clear_caches()
        st.success("Cache vidé. Rechargement…")
        st.rerun()

# ============================== MAIN ==============================
def main():
    # Thème clair/sombre simple
    mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    if not mode_clair:
        st.markdown(
            """
            <style>
              [data-testid="stAppViewContainer"] { background:#0f1115; color:#eaeef6; }
              [data-testid="stSidebar"] { background:#171923; }
              .stDataFrame td, .stDataFrame th { color:#eaeef6 !important; }
            </style>
            """, unsafe_allow_html=True
        )

    st.title("✨ Villa Tobias — Gestion des Réservations")
    df = charger_donnees()

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "👥 Clients": vue_clients,
        "📆 Export ICS": vue_export_ics,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, DEFAULT_PALETTE)

    admin_sidebar(df)

if __name__ == "__main__":
    main()