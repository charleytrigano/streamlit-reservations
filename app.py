# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from io import StringIO
import re, uuid, hashlib

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

# ============================== STYLES ==============================
def _apply_style():
    st.markdown(
        """
        <style>
          .kpi{display:inline-block; background:#f6f7fb; border:1px solid #e6e8f0; padding:8px 10px; border-radius:10px; margin:4px 6px;}
          .kpi small{display:block; font-size:12px; color:#667085}
          .kpi b{font-size:15px}
          [data-testid="stSidebar"] {border-right: 1px solid #eceff5;}
          .grid-7{display:grid; grid-template-columns: repeat(7, 1fr); gap:8px;}
          .daycell{min-height:110px; border:1px solid #e6e8f0; border-radius:10px; padding:6px; position:relative; background:#fff;}
          .out{opacity:.4}
          .datebadge{position:absolute; right:8px; top:6px; font-weight:700; font-size:.85rem; color:#667085}
          .pill{margin-top:22px; background:#444; color:#fff; border-radius:6px; padding:3px 6px; font-size:.8rem; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;}
        </style>
        """,
        unsafe_allow_html=True
    )

_apply_style()

# ============================== UTILS PARSE ==============================
def _read_csv_flexible(raw_bytes: bytes) -> pd.DataFrame:
    """Essaye ; , tab | puis auto. Retourne un DataFrame (peut être vide)."""
    if not raw_bytes:
        return pd.DataFrame()
    txt = raw_bytes.decode("utf-8", errors="ignore").replace("\ufeff", "")
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

def _to_series(obj, dtype=None) -> pd.Series:
    """Assure une Series (jamais ndarray nu), utile contre erreurs fillna."""
    if isinstance(obj, pd.Series):
        s = obj.copy()
    elif isinstance(obj, (list, tuple, np.ndarray)):
        s = pd.Series(obj)
    else:
        s = pd.Series([], dtype=dtype if dtype else "float64")
    if dtype:
        try: s = s.astype(dtype)
        except Exception: pass
    return s

def _to_bool(s: pd.Series) -> pd.Series:
    s = _to_series(s, dtype=str).str.strip().str.lower()
    return s.isin(["true","1","oui","yes","vrai","y","t"]).fillna(False)

def _to_num(s: pd.Series) -> pd.Series:
    s = _to_series(s, dtype=str).str.replace("€","",regex=False).str.replace(" ","",regex=False).str.replace(",",".",regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    """Accepte JJ/MM/AAAA et AAAA-MM-JJ et variantes. Retourne dtype=object avec date() ou NaN."""
    s = _to_series(s, dtype=str)
    d1 = pd.to_datetime(s, errors="coerce", dayfirst=True)
    # Si beaucoup de NaT, tente Y-m-d
    if d1.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d1 = d1.fillna(d2)
    return d1.dt.date

# ============================== SCHEMA ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","pct",
    "res_id","ical_uid","AAAA","MM"
]

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Alias courants -> noms cibles
    rename_map = {
        "Payé":"paye","Client":"nom_client","Plateforme":"plateforme",
        "Arrivée":"date_arrivee","Départ":"date_depart","Nuits":"nuitees",
        "Brut (€)":"prix_brut","%":"pct"
    }
    df.rename(columns=rename_map, inplace=True)

    # Crée colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Types
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool(df[b]).astype(bool)

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","base","charges","pct"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Recalcul nuitees si possible
    mask = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[mask,"date_arrivee"])
        dd = pd.to_datetime(df.loc[mask,"date_depart"])
        df.loc[mask,"nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)
    except Exception:
        pass

    # prix_net / charges / base / pct
    brut = _to_num(df["prix_brut"])
    comm = _to_num(df["commissions"])
    fcb  = _to_num(df["frais_cb"])
    df["prix_net"] = (brut - comm - fcb).fillna(0.0)
    df["charges"]  = (brut - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - _to_num(df["menage"]) - _to_num(df["taxes_sejour"])).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(brut>0, (df["charges"] / brut) * 100, 0)
    df["pct"] = pd.to_numeric(pct, errors="coerce").fillna(0.0)

    # AAAA / MM
    dser = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["AAAA"] = pd.to_numeric(dser.dt.year, errors="coerce")
    df["MM"]   = pd.to_numeric(dser.dt.month, errors="coerce")

    # IDs
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res,"res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # Strings propres
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = _to_series(df[c], dtype=str).replace({"nan":"", "None":""}).str.strip()

    return df[BASE_COLS]

# ============================== IO ==============================
@st.cache_data
def _load_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

@st.cache_data
def charger_df():
    raw = _load_bytes(CSV_RESERVATIONS)
    if raw is not None:
        base = _read_csv_flexible(raw)
    else:
        base = pd.DataFrame()
    df = ensure_schema(base)

    # palette
    pal_raw = _load_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if pal_raw:
        try:
            pal_df = _read_csv_flexible(pal_raw)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if set(["plateforme","couleur"]).issubset(set(pal_df.columns)):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception:
            pass

    return df, palette

def save_df(df: pd.DataFrame) -> bool:
    try:
        out = ensure_schema(df).copy()
        for c in ["date_arrivee","date_depart"]:
            out[c] = pd.to_datetime(out[c], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur sauvegarde CSV : {e}")
        return False

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def _fmt_eur(x: float) -> str:
    try:
        return f"{x:,.2f} €".replace(",", " ")
    except Exception:
        return "0,00 €".replace(",", " ")

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
        if arr.empty: st.info("Aucune arrivée.")
        else: st.dataframe(arr, use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        if dep.empty: st.info("Aucun départ.")
        else: st.dataframe(dep, use_container_width=True)

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation."); return

    years_ser  = pd.to_numeric(_to_series(dfn.get("AAAA")), errors="coerce")
    months_ser = pd.to_numeric(_to_series(dfn.get("MM")),   errors="coerce")

    years  = ["Toutes"] + (sorted(years_ser.dropna().astype(int).unique(), reverse=True).tolist() if not years_ser.dropna().empty else [])
    months = ["Tous"] + (sorted(months_ser.dropna().astype(int).unique()).tolist() if not months_ser.dropna().empty else list(range(1,13)))
    plats  = ["Toutes"] + sorted(_to_series(dfn["plateforme"], dtype=str).replace({"":np.nan}).dropna().unique().tolist())

    col1, col2, col3 = st.columns(3)
    y = col1.selectbox("Année", years, index=0)
    m = col2.selectbox("Mois", months, index=0)
    p = col3.selectbox("Plateforme", plats, index=0)

    data = dfn.copy()
    if y != "Toutes":
        data = data[pd.to_numeric(data["AAAA"], errors="coerce").fillna(-1).astype(int) == int(y)]
    if m != "Tous":
        data = data[pd.to_numeric(data["MM"], errors="coerce").fillna(-1).astype(int) == int(m)]
    if p != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(p).strip()]

    # KPIs (petite taille)
    brut = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    base = float(pd.to_numeric(data["base"],      errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(data["nuitees"],     errors="coerce").fillna(0).sum())
    adr  = (net/nuits) if nuits>0 else 0.0
    charges = float(pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum())

    st.markdown(
        f"""
        <div>
          <span class="kpi"><small>Total brut</small><b>{_fmt_eur(brut)}</b></span>
          <span class="kpi"><small>Total net</small><b>{_fmt_eur(net)}</b></span>
          <span class="kpi"><small>Charges</small><b>{_fmt_eur(charges)}</b></span>
          <span class="kpi"><small>Base</small><b>{_fmt_eur(base)}</b></span>
          <span class="kpi"><small>Nuitées</small><b>{nuits}</b></span>
          <span class="kpi"><small>ADR (net)</small><b>{_fmt_eur(adr)}</b></span>
        </div>
        """,
        unsafe_allow_html=True
    )
    st.markdown("---")

    # Tri par date d'arrivée
    order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order]

    st.dataframe(data, use_container_width=True)

def vue_clients(df, palette):
    st.header("👥 Clients")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucun client."); return
    clients = dfn[["nom_client","telephone","email","plateforme","res_id"]].copy()
    clients["nom_client"] = _to_series(clients["nom_client"], dtype=str).str.strip()
    clients["telephone"]  = _to_series(clients["telephone"],  dtype=str).str.strip()
    clients["email"]      = _to_series(clients["email"],      dtype=str).str.strip()
    clients = clients.replace({"nan":""})
    clients = clients[clients["nom_client"]!=""]
    clients = clients.drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation."); return

    years = sorted(pd.to_numeric(_to_series(dfn["AAAA"]), errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(_to_series(dfn["plateforme"], dtype=str).replace({"":np.nan}).dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfn[pd.to_numeric(dfn["AAAA"], errors="coerce")==year].copy()
    if plat!="Tous": data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Rien à exporter."); return

    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if miss.any():
        data.loc[miss,"ical_uid"] = data[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    def _fmt(d):
        if isinstance(d, datetime): d = d.date()
        if not isinstance(d, date): return ""
        return f"{d.year:04d}{d.month:02d}{d.day:02d}"
    def _esc(s):
        if s is None: return ""
        return str(s).replace("\\","\\\\").replace("\n","\\n").replace(",","\\,").replace(";","\\;")

    lines = ["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        da, dd = r["date_arrivee"], r["date_depart"]
        if not (isinstance(da,(date,datetime)) and isinstance(dd,(date,datetime))): 
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

def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille)")
    dfn = ensure_schema(df)
    dfx = dfn.dropna(subset=["date_arrivee","date_depart"]).copy()
    if dfx.empty:
        st.info("Aucune réservation à afficher."); return

    years = sorted(pd.to_datetime(dfx["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    y = st.selectbox("Année", years, index=0)
    m = st.selectbox("Mois", list(range(1,13)), index=(date.today().month-1))

    st.markdown("<div class='grid-7' style='font-weight:700;opacity:.75;margin-bottom:6px'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    cal = Calendar(firstweekday=0)  # lundi
    html = ["<div class='grid-7'>"]
    for week in cal.monthdatescalendar(y, m):
        for d in week:
            outside = (d.month != m)
            klass = "daycell out" if outside else "daycell"
            cell = f"<div class='{klass}'><div class='datebadge'>{d.day}</div>"
            if not outside:
                # affichage des réservations du jour
                mask = (dfx["date_arrivee"] <= d) & (dfx["date_depart"] > d)
                rows = dfx[mask]
                for _, r in rows.iterrows():
                    color = palette.get(r.get("plateforme"), "#666")
                    label = str(r.get("nom_client") or "")[:22]
                    cell += f"<div class='pill' style='background:{color}' title='{r.get('nom_client','')}'>{label}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Détail du mois")
    start = date(y,m,1)
    end   = date(y,m, monthrange(y,m)[1])
    rows = dfx[(dfx["date_arrivee"] <= end) & (dfx["date_depart"] > start)].copy()
    if rows.empty:
        st.info("Aucune réservation ce mois.")
    else:
        st.dataframe(rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)

# ============================== ADMIN (Sidebar) ==============================
def admin_sidebar(df):
    st.sidebar.markdown("## ⚙️ Administration")

    # Télécharger CSV
    st.sidebar.download_button(
        "Télécharger CSV",
        data=ensure_schema(df).to_csv(sep=";", index=False).encode("utf-8"),
        file_name=CSV_RESERVATIONS,
        mime="text/csv"
    )

    # Restaurer CSV (accepte ; , tab |)
    up = st.sidebar.file_uploader("Restaurer depuis un CSV", type=["csv"])
    if up is not None and st.sidebar.button("Confirmer restauration"):
        try:
            content = up.read()
            tmp = _read_csv_flexible(content)
            tmp = ensure_schema(tmp)
            out = tmp.copy()
            for c in ["date_arrivee","date_depart"]:
                out[c] = pd.to_datetime(out[c], errors="coerce").dt.strftime("%d/%m/%Y")
            out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.cache_data.clear()
            st.sidebar.success("Fichier restauré. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur restauration : {e}")

    # Vider cache manuel
    if st.sidebar.button("🧹 Vider le cache & recharger"):
        try: st.cache_data.clear()
        except Exception: pass
        st.sidebar.success("Cache vidé.")
        st.rerun()

# ============================== MAIN ==============================
def main():
    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette = charger_df()

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "👥 Clients": vue_clients,
        "📆 Export ICS": vue_export_ics,
        "📅 Calendrier": vue_calendrier,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()