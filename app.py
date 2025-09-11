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

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# Hard clear "soft" (ne casse rien si pas disponible)
for _clear in (getattr(st, "cache_data", None), getattr(st, "cache_resource", None)):
    try:
        if _clear: _clear.clear()
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
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    chip_bg = "#e8e8e8" if light else "#333"
    chip_fg = "#222" if light else "#eee"
    st.markdown(
        f"""
        <style>
          [data-testid="stAppViewContainer"] {{ background:{bg}; color:{fg}; }}
          [data-testid="stSidebar"] {{ background:{side}; border-right:1px solid {border}; }}
          .glass {{
            background: {"rgba(255,255,255,.7)" if light else "rgba(255,255,255,.06)"};
            border:1px solid {border}; border-radius:12px; padding:10px; margin:8px 0;
          }}
          .chip {{
            display:inline-block; background:{chip_bg}; color:{chip_fg};
            padding:6px 10px; border-radius:12px; margin:4px 6px; font-size:.85rem
          }}
          .chip strong {{ font-size:1rem; }}
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; margin-top:8px; }}
          .cal-cell {{
            border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px;
            position:relative; overflow:hidden; background:{"#fff" if light else "#0b0d12"};
          }}
          .cal-cell.outside {{ opacity:.45; }}
          .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
          .resa-pill {{
            padding:4px 6px; border-radius:6px; font-size:.8rem; margin-top:22px;
            color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;
          }}
          .cal-header {{ display:grid; grid-template-columns: repeat(7, 1fr); font-weight:700; opacity:.8; margin-top:10px; }}
        </style>
        """,
        unsafe_allow_html=True
    )

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)

# ============================== UTIL SÛRES ==============================
def _as_series(obj, dtype=None) -> pd.Series:
    """Garanti une Series (évite ndarray.fillna)."""
    if isinstance(obj, pd.Series):
        s = obj
    else:
        s = pd.Series(obj)
    if dtype:
        try:
            s = s.astype(dtype)
        except Exception:
            pass
    return s

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff", "")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 2: return df
        except Exception:
            continue
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _to_bool(s) -> pd.Series:
    s = _as_series(s, dtype=str).str.strip().str.lower()
    return s.isin(["true","1","oui","vrai","yes","y","t"])

def _to_num(s) -> pd.Series:
    s = _as_series(s, dtype=str).str.replace("€","",regex=False).str.replace(" ","",regex=False).str.replace(",",".",regex=False).str.strip()
    return pd.to_numeric(s, errors="coerce")

def _to_date(ser) -> pd.Series:
    s = _as_series(ser)
    # 1/ JJ/MM/AAAA etc. (dayfirst)
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    # 2/ format ISO si beaucoup de NaT
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
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

# ============================== DATA ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
    "base","charges","%",
    "res_id","ical_uid"
]

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # normaliser noms usuels
    df.rename(columns={
        'Payé':'paye','Client':'nom_client','Plateforme':'plateforme',
        'Arrivée':'date_arrivee','Départ':'date_depart','Nuits':'nuitees',
        'Brut (€)':'prix_brut'
    }, inplace=True)

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Types sûrs
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool(df[b]).fillna(False)

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

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
    df["prix_net"] = (_to_num(df["prix_brut"]) - _to_num(df["commissions"]) - _to_num(df["frais_cb"])).fillna(0.0)
    df["charges"]  = (_to_num(df["prix_brut"]) - _to_num(df["prix_net"])).fillna(0.0)
    df["base"]     = (_to_num(df["prix_net"]) - _to_num(df["menage"]) - _to_num(df["taxes_sejour"])).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(_to_num(df["prix_brut"])>0, (_to_num(df["charges"]) / _to_num(df["prix_brut"]) * 100), 0)
    df["%"] = pd.to_numeric(pct, errors="coerce").fillna(0.0)

    # IDs stables
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]
    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid, "ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # Strings propres
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = _as_series(df[c], dtype=str).replace({"nan": "", "None": ""}).str.strip()

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
    base_df = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base_df)

    rawp = _load_file_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal = _detect_delimiter_and_read(rawp)
            pal.columns = pal.columns.astype(str).str.strip()
            if set(["plateforme","couleur"]).issubset(pal.columns):
                palette = dict(zip(pal["plateforme"], pal["couleur"]))
        except Exception:
            pass
    return df, palette

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
        try: st.cache_data.clear()
        except Exception: pass
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
    da = _to_date(dfn["date_arrivee"])
    dd = _to_date(dfn["date_depart"])

    arr = dfn.loc[da == today, ["nom_client","telephone","plateforme"]]
    dep = dfn.loc[dd == today, ["nom_client","telephone","plateforme"]]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        if not arr.empty:
            st.dataframe(arr, use_container_width=True)
        else:
            st.info("Aucune arrivée.")
    with c2:
        st.subheader("🔴 Départs du jour")
        if not dep.empty:
            st.dataframe(dep, use_container_width=True)
        else:
            st.info("Aucun départ.")

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfn = ensure_schema(df)
    da = pd.to_datetime(dfn["date_arrivee"], errors="coerce")
    years = ["Toutes"] + sorted(da.dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months = ["Tous"] + list(range(1,13))
    plats  = ["Toutes"] + sorted(dfn["plateforme"].dropna().astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist())

    c1, c2, c3 = st.columns(3)
    sel_year  = c1.selectbox("Année (arrivée)", years, index=0)
    sel_month = c2.selectbox("Mois", months, index=0)
    sel_plat  = c3.selectbox("Plateforme", plats, index=0)

    data = dfn.copy()
    if sel_year != "Toutes":
        data = data[da.dt.year == int(sel_year)]
    if sel_month != "Tous":
        data = data[da.dt.month == int(sel_month)]
    if sel_plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == sel_plat]

    # KPI compacts
    brut = float(_to_num(data["prix_brut"]).sum())
    net  = float(_to_num(data["prix_net"]).sum())
    base = float(_to_num(data["base"]).sum())
    nuits= int(_to_num(data["nuitees"]).sum())
    charges = float(_to_num(data["charges"]).sum())
    adr  = (net/nuits) if nuits>0 else 0.0

    kpi_html = f"""
    <div class='glass'>
      <span class='chip'><small>Brut</small><br><strong>{brut:,.2f} €</strong></span>
      <span class='chip'><small>Net</small><br><strong>{net:,.2f} €</strong></span>
      <span class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></span>
      <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
      <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
      <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
    </div>
    """.replace(",", " ")
    st.markdown(kpi_html, unsafe_allow_html=True)
    st.markdown("---")

    # Tri par date d’arrivée desc.
    order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order]
    st.dataframe(data, use_container_width=True)

def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille)")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation."); return

    da = _to_date(dfn["date_arrivee"])
    dd = _to_date(dfn["date_depart"])

    years = sorted(pd.to_datetime(da, errors="coerce").dropna().dt.year.astype(int).unique(), reverse=True)
    y = st.selectbox("Année", years if years else [date.today().year], index=0)
    m = st.selectbox("Mois", list(range(1,13)), index=(date.today().month-1))

    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    def day_resas(d):
        mask = (pd.to_datetime(da) <= pd.Timestamp(d)) & (pd.to_datetime(dd) > pd.Timestamp(d))
        return dfn[mask]

    cal = Calendar(firstweekday=0)
    html = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(y, m):
        for d in week:
            outside = (d.month != m)
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'><div class='cal-date'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
                if not rs.empty:
                    for _, r in rs.iterrows():
                        color = palette.get(str(r.get('plateforme') or ''), '#888')
                        name  = str(r.get('nom_client') or '')[:22]
                        cell += f"<div class='resa-pill' style='background:{color}' title='{r.get('nom_client','')}'>{name}</div>"
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Détail du mois")
    debut = date(y, m, 1); fin = date(y, m, monthrange(y, m)[1])
    rows = dfn[(pd.to_datetime(da) <= pd.Timestamp(fin)) & (pd.to_datetime(dd) > pd.Timestamp(debut))].copy()
    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        # totaux + filtre plateforme
        plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
        sel = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
        if sel != "Toutes":
            rows = rows[rows["plateforme"]==sel]
        brut = float(_to_num(rows["prix_brut"]).sum())
        net  = float(_to_num(rows["prix_net"]).sum())
        nuits= int(_to_num(rows["nuitees"]).sum())
        html = f"""
        <div class='glass'>
          <span class='chip'><small>Brut</small><br><strong>{brut:,.2f} €</strong></span>
          <span class='chip'><small>Net</small><br><strong>{net:,.2f} €</strong></span>
          <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
        </div>
        """.replace(",", " ")
        st.markdown(html, unsafe_allow_html=True)
        st.dataframe(rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation."); return

    da = pd.to_datetime(dfn["date_arrivee"], errors="coerce")
    years = sorted(da.dropna().dt.year.astype(int).unique(), reverse=True)
    year = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(dfn["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfn[da.dt.year == year].copy()
    if plat != "Tous":
        data = data[data["plateforme"]==plat]
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
        da_, dd_ = r["date_arrivee"], r["date_depart"]
        if not (isinstance(da_, (date, datetime)) and isinstance(dd_, (date, datetime))): 
            continue
        summary = f"Villa Tobias — {r.get('nom_client','Sans nom')}"
        if r.get("plateforme"): summary += f" ({r['plateforme']})"
        desc = "\n".join([
            f"Client: {r.get('nom_client','')}",
            f"Téléphone: {r.get('telephone','')}",
            f"Nuitées: {int(_to_num([r.get('nuitees')]).iloc[0] or 0)}",
            f"Prix brut: {float(_to_num([r.get('prix_brut')]).iloc[0] or 0):.2f} €",
            f"res_id: {r.get('res_id','')}",
        ])
        lines += [
            "BEGIN:VEVENT",
            f"UID:{r['ical_uid']}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt(da_)}",
            f"DTEND;VALUE=DATE:{_fmt(dd_)}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"), file_name=f"reservations_{year}.ics", mime="text/calendar")

def vue_clients(df, palette):
    st.header("👥 Clients")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucun client."); return
    clients = (dfn[['nom_client','telephone','email','plateforme','res_id']]
               .copy())
    clients["nom_client"] = _as_series(clients["nom_client"], dtype=str).str.strip()
    clients["telephone"]  = _as_series(clients["telephone"], dtype=str).str.strip()
    clients["email"]      = _as_series(clients["email"], dtype=str).str.strip()
    clients = clients.loc[clients["nom_client"] != ""]
    clients = clients.drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)

# ============================== ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    # Sauvegarde
    safe = ensure_schema(df)
    csv_bytes = safe.to_csv(sep=";", index=False).encode("utf-8")
    st.sidebar.download_button("💾 Télécharger CSV", data=csv_bytes, file_name=CSV_RESERVATIONS, mime="text/csv")

    # Restauration
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
            try: st.cache_data.clear()
            except Exception: pass
            st.success("Fichier restauré. Rechargement…")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    # Vider le cache
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
        mode_clair = st.sidebar.toggle("🌓 Mode clair", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair", value=False)
    apply_style(light=bool(mode_clair))

    st.title("✨ Villa Tobias — Gestion des Réservations")
    df, palette_loaded = charger_donnees()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "📅 Calendrier": vue_calendrier,
        "👥 Clients": vue_clients,
        "📆 Export ICS": vue_export_ics,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()