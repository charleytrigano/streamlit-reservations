# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from io import StringIO

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

# ============================== STYLE ==============================
def apply_style(light: bool):
    bg = "#fafafa" if light else "#0e1117"
    fg = "#0f172a" if light else "#e6e6e6"
    side = "#f2f2f2" if light else "#151a23"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
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
            background: {"rgba(255,255,255,0.7)" if light else "rgba(255,255,255,0.06)"};
            border: 1px solid {border}; border-radius: 12px; padding: 12px; margin: 8px 0;
          }}
          .kpi-line .chip {{
            display:inline-block; background: {"#ebebeb" if light else "#1d2430"};
            color:{fg}; padding:6px 10px; border-radius:10px; margin:4px 6px; font-size:0.9rem
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)

# ============================== OUTILS CSV ==============================
def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    """Lit un CSV en testant ; , tab | et retire BOM."""
    if raw is None:
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
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

@st.cache_data
def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _to_bool_series(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series([], dtype=bool)
    return s.astype(str).str.strip().str.lower().isin(
        ["true","1","oui","vrai","yes","y","t"]
    )

def _to_num(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series([], dtype="float64")
    sc = (
        s.astype(str)
         .str.replace("€","", regex=False)
         .str.replace(" ", "", regex=False)
         .str.replace(",", ".", regex=False)
         .str.strip()
    )
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    """Accepte JJ/MM/AAAA, AAAA-MM-JJ, etc. Renvoie .dt.date"""
    if s is None:
        return pd.Series([], dtype="object")
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    # si trop de NaT, retente en YMD explicite
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

# ============================== SCHEMA & CHARGEMENT ==============================
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
    """Normalise et calcule les champs dérivés sans .fillna sur ndarray."""
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Renommages éventuels
    df.rename(columns={
        'Payé':'paye','Client':'nom_client','Plateforme':'plateforme',
        'Arrivée':'date_arrivee','Départ':'date_depart','Nuits':'nuitees',
        'Brut (€)':'prix_brut'
    }, inplace=True)

    # Créer manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)

    # Numériques de base
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Nuitées cohérentes
    mask_ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0)
    except Exception:
        pass

    # Calculs financiers (⚠️ correctif ndarray -> Series)
    brut = _to_num(df["prix_brut"])
    comm = _to_num(df["commissions"])
    fcb  = _to_num(df["frais_cb"])
    df["prix_net"] = (brut - comm - fcb)
    df["charges"]  = (brut - df["prix_net"])
    df["base"]     = (df["prix_net"] - _to_num(df["menage"]) - _to_num(df["taxes_sejour"]))
    with np.errstate(divide="ignore", invalid="ignore"):
        pct_arr = np.where(brut.to_numpy() > 0,
                           (df["charges"].to_numpy() / brut.to_numpy()) * 100,
                           0.0)
    # => forcer en Series avant fillna
    df["%"] = pd.to_numeric(pd.Series(pct_arr, index=df.index), errors="coerce").fillna(0.0)

    # AAAA / MM
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
        df[c] = df[c].astype(str).replace({"nan": "", "None": ""}).str.strip()

    # Final
    return df[BASE_COLS].copy()

@st.cache_data
def charger_donnees():
    # Réservations
    raw = _load_file_bytes(CSV_RESERVATIONS)
    base_df = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base_df)

    # Palette
    palette = DEFAULT_PALETTE.copy()
    rawp = _load_file_bytes(CSV_PLATEFORMES)
    if rawp is not None:
        pal_df = _detect_delimiter_and_read(rawp)
        pal_df.columns = pal_df.columns.astype(str).str.strip()
        if set(["plateforme","couleur"]).issubset(pal_df.columns):
            pal_df = pal_df.dropna(subset=["plateforme","couleur"])
            palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
    return df, palette

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        out = ensure_schema(df).copy()
        # Écrit dates lisibles JJ/MM/AAAA
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde CSV : {e}")
        return False

# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfn = ensure_schema(df)
    arr = dfn[dfn["date_arrivee"] == today][["nom_client","telephone","plateforme"]].copy()
    dep = dfn[dfn["date_depart"]  == today][["nom_client","telephone","plateforme"]].copy()

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr, use_container_width=True) if not arr.empty else st.info("Aucune arrivée.")
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep, use_container_width=True) if not dep.empty else st.info("Aucun départ.")

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfn = ensure_schema(df)

    years_ser  = pd.to_numeric(dfn["AAAA"], errors="coerce")
    months_ser = pd.to_numeric(dfn["MM"],   errors="coerce")

    years  = ["Toutes"] + (sorted(years_ser.dropna().astype(int).unique(), reverse=True).tolist()
                           if not years_ser.dropna().empty else [])
    months = ["Tous"] + (sorted(months_ser.dropna().astype(int).unique()).tolist()
                         if not months_ser.dropna().empty else list(range(1,13)))
    plats = ["Toutes"] + sorted(dfn["plateforme"].dropna().astype(str).str.strip().replace({"":np.nan}).dropna().unique())

    col1, col2, col3 = st.columns(3)
    year  = col1.selectbox("Année", years, index=0)
    month = col2.selectbox("Mois", months, index=0)
    plat  = col3.selectbox("Plateforme", plats, index=0)

    data = dfn.copy()
    if year  != "Toutes": data = data[pd.to_numeric(data["AAAA"], errors="coerce").fillna(-1).astype(int) == int(year)]
    if month != "Tous":   data = data[pd.to_numeric(data["MM"],   errors="coerce").fillna(-1).astype(int) == int(month)]
    if plat  != "Toutes": data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]

    # KPIs
    brut   = float(pd.to_numeric(data["prix_brut"], errors="coerce").sum())
    net    = float(pd.to_numeric(data["prix_net"],  errors="coerce").sum())
    base   = float(pd.to_numeric(data["base"],      errors="coerce").sum())
    charges= float(pd.to_numeric(data["charges"],   errors="coerce").sum())
    nuits  = int(pd.to_numeric(data["nuitees"],     errors="coerce").sum())
    adr    = (net/nuits) if nuits>0 else 0.0

    st.markdown(
        f"""
        <div class='glass kpi-line'>
          <span class='chip'><small>Total brut</small><br><b>{brut:,.2f} €</b></span>
          <span class='chip'><small>Total net</small><br><b>{net:,.2f} €</b></span>
          <span class='chip'><small>Charges</small><br><b>{charges:,.2f} €</b></span>
          <span class='chip'><small>Base</small><br><b>{base:,.2f} €</b></span>
          <span class='chip'><small>Nuitées</small><br><b>{nuits}</b></span>
          <span class='chip'><small>ADR net</small><br><b>{adr:,.2f} €</b></span>
        </div>
        """.replace(",", " "),
        unsafe_allow_html=True
    )
    st.markdown("---")

    # tri arrivée desc si dispo
    order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order]
    st.dataframe(data, use_container_width=True)

def vue_clients(df, palette):
    st.header("👥 Clients")
    if df is None or df.empty:
        st.info("Aucun client."); return
    dfn = ensure_schema(df)
    clients = (dfn[['nom_client','telephone','email','plateforme','res_id']]
               .copy())
    # nettoyage
    for c in ["nom_client","telephone","email","plateforme"]:
        clients[c] = clients[c].astype(str).replace({"nan":"","None":""}).str.strip()
    clients = clients[clients["nom_client"] != ""]
    clients = clients.drop_duplicates().sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    if df is None or df.empty:
        st.info("Aucune réservation."); return

    dfn = ensure_schema(df)
    years = sorted(pd.to_numeric(dfn["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years if years else [date.today().year], index=0)
    plats = ["Tous"] + sorted(dfn["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfn[pd.to_numeric(dfn["AAAA"], errors="coerce")==year].copy()
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

# ============================== ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    # Téléchargement du CSV actuel (normalisé)
    st.sidebar.download_button(
        "⬇️ Télécharger CSV",
        data=ensure_schema(df).to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )

    # Restauration CSV (détecte ; , tab)
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
            st.cache_data.clear()
            st.success("Fichier restauré. Rechargement…"); st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    # Gestion palette plateformes
    st.sidebar.markdown("### 🎨 Plateformes")
    try:
        pal_df = pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"])
        st.sidebar.dataframe(pal_df, use_container_width=True, height=160)
    except Exception:
        pass
    if st.sidebar.button("↩️ Restaurer palette par défaut"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette restaurée."); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    # Purge cache
    if st.sidebar.button("🧹 Vider le cache & recharger"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
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
        "👥 Clients": vue_clients,
        "📆 Export ICS": vue_export_ics,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()