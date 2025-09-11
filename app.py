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

# ===== ICS HELPERS (safe) =====
from datetime import datetime, date

def _safe_to_date(x):
    """Accepte str/np.nan/date/datetime -> date ou None (ne jette jamais d'exception)."""
    try:
        if isinstance(x, date) and not isinstance(x, datetime):
            return x
        if isinstance(x, datetime):
            return x.date()
        # pandas to_datetime gère pas mal de formats (JJ/MM/AAAA, AAAA-MM-JJ…)
        d = pd.to_datetime(x, errors="coerce", dayfirst=True)
        if pd.isna(d):
            return None
        return d.date()
    except Exception:
        return None

def _ics_uid_for_row(row):
    # UID stable = sha1(res_id + nom + tel) @domaine
    rid = str(row.get("res_id", "") or "")
    nom = str(row.get("nom_client", "") or "")
    tel = str(row.get("telephone", "") or "")
    base = (rid + nom + tel).strip()
    if not base:
        base = str(uuid.uuid4())
    return hashlib.sha1(base.encode("utf-8")).hexdigest() + "@villa-tobias"

def _ics_escape(val: str) -> str:
    if val is None:
        return ""
    s = str(val)
    # Échapper les caractères réservés ICS
    s = s.replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")
    return s

def build_ics_from_df(df: pd.DataFrame) -> str:
    """
    Construit un .ics (VCALENDAR) à partir d’un DF normalisé contenant :
    - date_arrivee, date_depart (dates)
    - nom_client, telephone, plateforme, nuitees, prix_brut, res_id, ical_uid
    Ne lève pas d’exception : ignore poliment les lignes invalides.
    """
    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _fmt_date(d: date) -> str:
        return f"{d.year:04d}{d.month:02d}{d.day:02d}"

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        "CALSCALE:GREGORIAN",
    ]

    if df is None or len(df) == 0:
        lines.append("END:VCALENDAR")
        return "\r\n".join(lines) + "\r\n"

    # On ne suppose rien du type des colonnes.
    for _, r in df.iterrows():
        da = _safe_to_date(r.get("date_arrivee"))
        dd = _safe_to_date(r.get("date_depart"))
        if not (isinstance(da, date) and isinstance(dd, date)):
            continue  # on saute proprement

        uid = str(r.get("ical_uid") or "").strip() or _ics_uid_for_row(r)
        nom = r.get("nom_client", "Sans nom")
        plat = r.get("plateforme", "")
        summary = f"Villa Tobias — {nom}"
        if str(plat).strip():
            summary += f" ({plat})"

        try:
            nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
        except Exception:
            nuitees = 0

        try:
            brut = float(pd.to_numeric(r.get("prix_brut"), errors="coerce") or 0.0)
        except Exception:
            brut = 0.0

        desc = "\n".join([
            f"Client: {nom}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {nuitees}",
            f"Prix brut: {brut:.2f} €",
            f"res_id: {r.get('res_id','')}",
        ])

        lines += [
            "BEGIN:VEVENT",
            f"UID:{_ics_escape(uid)}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt_date(da)}",
            f"DTEND;VALUE=DATE:{_fmt_date(dd)}",  # journée de départ non incluse (standard)
            f"SUMMARY:{_ics_escape(summary)}",
            f"DESCRIPTION:{_ics_escape(desc)}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ===== PAGE : Export ICS =====
def vue_export_ics(df: pd.DataFrame, palette: dict):
    st.header("📆 Export ICS (Google Calendar)")

    if df is None or df.empty:
        st.info("Aucune réservation à exporter.")
        return

    # Années/plateformes (ultra défensif)
    years_ser = pd.to_numeric(df.get("AAAA", pd.Series(dtype="float64")), errors="coerce")
    years = sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True) if not years_ser.dropna().empty else []
    plats = ["Tous"] + sorted(
        df.get("plateforme", pd.Series(dtype="object"))
          .astype(str)
          .str.strip()
          .replace({"": np.nan, "nan": np.nan})
          .dropna()
          .unique()
          .tolist()
    )

    col1, col2 = st.columns(2)
    if years:
        year = col1.selectbox("Année (arrivées)", years, index=0)
        data = df[pd.to_numeric(df["AAAA"], errors="coerce").fillna(-1).astype(int) == int(year)].copy()
    else:
        year = None
        data = df.copy()

    plat = col2.selectbox("Plateforme", plats, index=0)
    if plat != "Tous":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]

    # Génération de UID manquants (safe, en mémoire uniquement)
    if "ical_uid" not in data.columns:
        data["ical_uid"] = None
    miss_uid = data["ical_uid"].astype(str).str.strip().isin(["", "nan", "None"])
    if miss_uid.any():
        data.loc[miss_uid, "ical_uid"] = data.loc[miss_uid].apply(_ics_uid_for_row, axis=1)

    # Construction .ics
    ics_blob = build_ics_from_df(data)
    fname = f"reservations_{year if year else 'toutes'}.ics"
    st.download_button("📥 Télécharger le fichier ICS", data=ics_blob.encode("utf-8"),
                       file_name=fname, mime="text/calendar")

    with st.expander("Aperçu du contenu ICS"):
        st.code(ics_blob[:4000] + ("...\n" if len(ics_blob) > 4000 else ""), language="text")

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# --- HARD CLEAR ---
try:
    st.cache_data.clear()
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
          .chip {{
            display:inline-block; background:{chip_bg}; color:{chip_fg};
            padding:4px 8px; border-radius:12px; margin:4px 6px; font-size:0.8rem
          }}
        </style>
        """,
        unsafe_allow_html=True
    )

# ============================== DATA ==============================
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
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 3:
                return df
        except Exception:
            continue
    return pd.read_csv(StringIO(txt), dtype=str)

def _to_bool_series(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype=bool)
    return s.astype(str).str.strip().str.lower().isin(["true","1","oui","vrai","yes","y","t"])

def _to_num(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype="float64")
    sc = (
        s.astype(str)
         .str.replace("€","",regex=False)
         .str.replace(" ","",regex=False)
         .str.replace(",",".",regex=False)
         .str.strip()
    )
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    if s is None: return pd.Series([], dtype="object")
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest()+"@villa-tobias"

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    mask_ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[mask_ok,"date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok,"date_depart"])
        df.loc[mask_ok,"nuitees"] = (dd-da).dt.days.clip(lower=0)
    except Exception: pass

    df["prix_net"] = (_to_num(df["prix_brut"]) - _to_num(df["commissions"]) - _to_num(df["frais_cb"])).fillna(0.0)
    df["charges"]  = (_to_num(df["prix_brut"]) - _to_num(df["prix_net"])).fillna(0.0)
    df["base"]     = (_to_num(df["prix_net"]) - _to_num(df["menage"]) - _to_num(df["taxes_sejour"])).fillna(0.0)

    # ✅ fix : Series only
    den = _to_num(df["prix_brut"])
    num = _to_num(df["charges"])
    df["%"] = (num / den.replace(0,np.nan) * 100).fillna(0.0)

    da_all = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = pd.to_numeric(da_all.dt.year, errors="coerce")
    df["MM"]   = pd.to_numeric(da_all.dt.month, errors="coerce")

    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res,"res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = df[c].astype(str).replace({"nan":"","None":""}).str.strip()

    return df[BASE_COLS]


# ============================== DATA I/O ==============================
@st.cache_data
def _load_file_bytes(path: str):
    try:
        with open(path,"rb") as f:
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
        st.error(f"Erreur sauvegarde : {e}")
        return False

# ============================== VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")
    arr = df[df["date_arrivee"]==today][["nom_client","telephone","plateforme"]]
    dep = df[df["date_depart"]==today][["nom_client","telephone","plateforme"]]
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame([{"info":"Aucune arrivée"}]))
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame([{"info":"Aucun départ"}]))

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df.empty:
        st.info("Aucune réservation"); return

    years_ser  = pd.to_numeric(df.get("AAAA",pd.Series(dtype="float64")), errors="coerce")
    months_ser = pd.to_numeric(df.get("MM",pd.Series(dtype="float64")), errors="coerce")

    years  = ["Toutes"] + sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True)
    months = ["Tous"]   + sorted(months_ser.dropna().astype(int).unique().tolist())
    plats  = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())

    c1,c2,c3 = st.columns(3)
    year  = c1.selectbox("Année", years)
    month = c2.selectbox("Mois", months)
    plat  = c3.selectbox("Plateforme", plats)

    data = df.copy()
    if year!="Toutes":  data = data[data["AAAA"]==int(year)]
    if month!="Tous":   data = data[data["MM"]==int(month)]
    if plat!="Toutes":  data = data[data["plateforme"]==plat]

    brut = data["prix_brut"].sum()
    net  = data["prix_net"].sum()
    base = data["base"].sum()
    nuits= int(data["nuitees"].sum())
    adr  = (net/nuits) if nuits>0 else 0
    charges = data["charges"].sum()

    st.markdown(f"""
    <div class='chip'>Total brut : {brut:,.2f} €</div>
    <div class='chip'>Total net : {net:,.2f} €</div>
    <div class='chip'>Charges : {charges:,.2f} €</div>
    <div class='chip'>Base : {base:,.2f} €</div>
    <div class='chip'>Nuitées : {nuits}</div>
    <div class='chip'>ADR : {adr:,.2f} €</div>
    """.replace(",", " "), unsafe_allow_html=True)

    st.dataframe(data, use_container_width=True)

def vue_clients(df, palette):
    st.header("👥 Clients")
    if df.empty: st.info("Aucun client"); return
    clients = (df[["nom_client","telephone","email","plateforme","res_id"]]
               .dropna(subset=["nom_client"])
               .drop_duplicates()
               .sort_values("nom_client"))
    st.dataframe(clients, use_container_width=True)

# ============================== ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Admin")
    st.sidebar.download_button(
        "📥 Exporter CSV",
        data=ensure_schema(df).to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )
    up = st.sidebar.file_uploader("📤 Importer CSV", type=["csv"])
    if up is not None:
        try:
            tmp = _detect_delimiter_and_read(up.read())
            tmp = ensure_schema(tmp)
            sauvegarder_donnees(tmp)
            st.success("CSV importé, rechargement…"); st.rerun()
        except Exception as e:
            st.error(f"Erreur import : {e}")

# ============================== MAIN ==============================
def main():
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair", value=False)
    except:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair", value=False)
    apply_style(light=bool(mode_clair))

    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette = charger_donnees()

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "👥 Clients": vue_clients,
        "📆 Export ICS": vue_export_ics,
    }
    choice = st.sidebar.radio("Navigation", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()