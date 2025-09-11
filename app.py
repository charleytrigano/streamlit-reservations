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
          .glass {{
            background: {"rgba(255,255,255,0.65)" if light else "rgba(255,255,255,0.06)"};
            border: 1px solid {border}; border-radius: 12px; padding: 12px; margin: 8px 0;
          }}
          .chip {{
            display:inline-block; background:{chip_bg}; color:{chip_fg};
            padding:6px 10px; border-radius:12px; margin:4px 6px; font-size:0.86rem
          }}
          .kpi-line strong {{ font-size:1.05rem; }}

          /* Calendar grid */
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; margin-top:8px; }}
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

# ============================== HELPERS ==============================
def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    """Lit un CSV avec tentative ; puis , puis tab puis | . Enlève BOM."""
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
        # numpy array or scalar
        base = pd.Series(s)
    return base.astype(str).str.strip().str.lower().isin(["true","1","oui","vrai","yes","y","t"])

def _to_num(s) -> pd.Series:
    if isinstance(s, pd.Series):
        base = s
    elif s is None:
        base = pd.Series([], dtype="object")
    else:
        base = pd.Series(s)
    sc = (
        base.astype(str)
            .str.replace("€","", regex=False)
            .str.replace(" ","", regex=False)
            .str.replace(",",";", regex=False)  # éviter conflit avec la virgule
            .str.replace(";",".", regex=False)
            .str.strip()
    )
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s) -> pd.Series:
    """Accepte JJ/MM/AAAA, AAAA-MM-JJ, JJ-MM-AAAA, etc., retourne .dt.date"""
    if isinstance(s, pd.Series):
        ser = s
    elif s is None:
        ser = pd.Series([], dtype="object")
    else:
        ser = pd.Series(s)
    # 1) essai dayfirst (gère JJ/MM/AAAA)
    d = pd.to_datetime(ser, errors="coerce", dayfirst=True)
    # 2) si beaucoup de NaT, essai format Y-m-d
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

# ============================== DATA LAYER ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid"
]

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Normalise le DataFrame pour qu'il respecte BASE_COLS (sans AAAA/MM)."""
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Créer colonnes manquantes d'abord (en object)
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Numériques de base
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base","prix_net"]:
        df[n] = _to_num(df[n])  # pas .fillna ici → on calcule ensuite proprement

    # Recalcul nuitées si dates cohérentes
    mask_ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(pd.Series(df.loc[mask_ok, "date_arrivee"]), errors="coerce")
        dd = pd.to_datetime(pd.Series(df.loc[mask_ok, "date_depart"]),  errors="coerce")
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0)
    except Exception:
        pass
    df["nuitees"] = pd.to_numeric(df["nuitees"], errors="coerce").fillna(0).astype(int)

    # Prix net / charges / base / %
    prix_brut = pd.to_numeric(df["prix_brut"], errors="coerce").fillna(0.0)
    commissions = pd.to_numeric(df["commissions"], errors="coerce").fillna(0.0)
    frais_cb    = pd.to_numeric(df["frais_cb"], errors="coerce").fillna(0.0)
    menage      = pd.to_numeric(df["menage"], errors="coerce").fillna(0.0)
    taxes       = pd.to_numeric(df["taxes_sejour"], errors="coerce").fillna(0.0)

    df["prix_net"] = (prix_brut - commissions - frais_cb).astype(float)
    df["charges"]  = (prix_brut - df["prix_net"]).astype(float)
    df["base"]     = (df["prix_net"] - menage - taxes).astype(float)

    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(prix_brut > 0, (df["charges"] / prix_brut) * 100.0, 0.0)
    df["%"] = pd.to_numeric(pct, errors="coerce").fillna(0.0)

    # IDs stables
    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if bool(miss_res.any()):
        df.loc[miss_res, "res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if bool(miss_uid.any()):
        df.loc[miss_uid, "ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    # Strings propres
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = df[c].astype(str).replace({"nan": "", "None": ""}).str.strip()

    return df[BASE_COLS]

@st.cache_data
def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f: return f.read()
    except Exception:
        return None

@st.cache_data
def charger_donnees():
    # reservations
    raw = _load_file_bytes(CSV_RESERVATIONS)
    if raw is not None:
        base_df = _detect_delimiter_and_read(raw)
    else:
        base_df = pd.DataFrame()
    df = ensure_schema(base_df)

    # palette plateformes
    rawp = _load_file_bytes(CSV_PLATEFORMES)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if set(["plateforme","couleur"]).issubset(set(pal_df.columns)):
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

# ============================== PAGES ==============================
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
        st.dataframe(arr, use_container_width=True) if not arr.empty else st.info("Aucune arrivée.")
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep, use_container_width=True) if not dep.empty else st.info("Aucun départ.")

def vue_reservations(df, palette):
    st.header("📋 Réservations")

    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation.")
        return

    # Filtres basés sur les dates
    d_dates = pd.to_datetime(dfn["date_arrivee"], errors="coerce")
    years_ser  = pd.Series(d_dates.dt.year,  index=dfn.index)
    months_ser = pd.Series(d_dates.dt.month, index=dfn.index)

    years_list  = sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True)
    months_list = sorted(months_ser.dropna().astype(int).unique().tolist())

    years  = ["Toutes"] + (years_list  if years_list  else [])
    months = ["Tous"]   + (months_list if months_list else list(range(1,13)))
    plats  = ["Toutes"] + sorted(
        dfn["plateforme"].astype(str).str.strip().replace({"": None}).dropna().unique().tolist()
    )

    colf1, colf2, colf3 = st.columns(3)
    year  = colf1.selectbox("Année", years, index=0)
    month = colf2.selectbox("Mois", months, index=0)
    plat  = colf3.selectbox("Plateforme", plats, index=0)

    data = dfn.copy()
    d_arr = pd.to_datetime(data["date_arrivee"], errors="coerce")
    if year  != "Toutes":
        data = data[d_arr.dt.year == int(year)]
        d_arr = pd.to_datetime(data["date_arrivee"], errors="coerce")
    if month != "Tous":
        data = data[d_arr.dt.month == int(month)]
    if plat  != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]

    # KPIs
    brut = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    base = float(pd.to_numeric(data["base"],      errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(data["nuitees"],     errors="coerce").fillna(0).sum())
    adr  = (net/nuits) if nuits>0 else 0.0
    charges = float(pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum())

    html = f"""
    <div class='glass kpi-line'>
      <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
      <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
      <span class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></span>
      <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
      <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
      <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
    </div>
    """.replace(",", " ")
    st.markdown(html, unsafe_allow_html=True)
    st.markdown("---")

    # Affichage
    if "date_arrivee" in data.columns:
        order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
        data = data.loc[order]
    st.dataframe(data, use_container_width=True)

def vue_clients(df, palette):
    st.header("👥 Clients")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucun client."); return
    clients = (dfn[['nom_client','telephone','email','plateforme','res_id']]
               .copy())
    clients["nom_client"] = clients["nom_client"].astype(str).str.strip()
    clients["telephone"]  = clients["telephone"].astype(str).str.strip()
    clients["email"]      = clients["email"].astype(str).str.strip()
    clients = clients[(clients["nom_client"]!="") | (clients["telephone"]!="") | (clients["email"]!="")]
    clients = clients.drop_duplicates()
    if "nom_client" in clients.columns:
        clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)

def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation."); return

    d_arr = pd.to_datetime(dfn["date_arrivee"], errors="coerce")
    years = sorted(d_arr.dt.year.dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years if years else [date.today().year], index=0)
    plats = ["Tous"] + sorted(dfn["plateforme"].dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = dfn[d_arr.dt.year == int(year)].copy()
    if plat!="Tous": data = data[data["plateforme"]==plat]
    if data.empty:
        st.warning("Rien à exporter."); return

    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip()=="")
    if bool(miss.any()):
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
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"), file_name=f"reservations_{year}.ics", mime="text/calendar")

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

    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    def day_resas(d):
        mask = (dfn['date_arrivee'] <= d) & (dfn['date_depart'] > d)
        return dfn[mask]

    cal = Calendar(firstweekday=0)  # lundi
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
    st.subheader("Détail du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfn[(dfn['date_arrivee'] <= fin_mois) & (dfn['date_depart'] > debut_mois)].copy()
    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
        plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
        if plat != "Toutes":
            rows = rows[rows["plateforme"]==plat]
        brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
        net  = float(pd.to_numeric(rows["prix_net"],  errors="coerce").fillna(0).sum())
        nuits= int(pd.to_numeric(rows["nuitees"],    errors="coerce").fillna(0).sum())
        html = f"""
        <div class='glass kpi-line'>
          <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
          <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
          <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
        </div>
        """.replace(",", " ")
        st.markdown(html, unsafe_allow_html=True)
        st.dataframe(rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]], use_container_width=True)

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
        "📅 Calendrier": vue_calendrier,
        "👥 Clients": vue_clients,
        "📆 Export ICS": vue_export_ics,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()