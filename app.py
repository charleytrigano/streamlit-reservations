# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib, json
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import urlparse, parse_qs, quote
from io import StringIO

# ============================== CONFIG ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# --- HARD CLEAR léger (ne plante pas si indisponible) ---
try:
    st.cache_data.clear()
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
def apply_style(dark: bool = True):
    bg = "#0f1115" if dark else "#fafafa"
    fg = "#eaeef6" if dark else "#0f172a"
    side = "#171923" if dark else "#f2f2f2"
    border = "rgba(124,92,255,.16)" if dark else "rgba(17,24,39,.08)"
    chip_bg = "#202434" if dark else "#ececec"
    chip_fg = "#e6e6f0" if dark else "#222"

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
            background: {"rgba(255,255,255,0.06)" if dark else "rgba(255,255,255,0.65)"};
            border: 1px solid {border}; border-radius: 12px; padding: 12px; margin: 8px 0;
          }}
          .chip {{
            display:inline-block; background:{chip_bg}; color:{chip_fg};
            padding:6px 10px; border-radius:12px; margin:4px 6px; font-size:.86rem
          }}
          .kpi-line strong {{ font-size:1.02rem; }}
          /* Calendar grid */
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; margin-top:8px; }}
          .cal-cell {{
            border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px;
            position:relative; overflow:hidden; background:{"#0b0d12" if dark else "#fff"};
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
          .small-note {{ opacity:.7; font-size:.9rem; }}
        </style>
        """,
        unsafe_allow_html=True
    )

def card(title: str, content: str):
    st.markdown(f"<div class='glass'><b>{title}</b><br/>{content}</div>", unsafe_allow_html=True)

# ============================== UTIL CSV ROBUSTE ==============================
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
    try:
        return pd.read_csv(StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _series(x) -> pd.Series:
    """Garantit une Series pandas (évite les .fillna sur ndarray)."""
    if isinstance(x, pd.Series):
        return x
    return pd.Series(x)

def _to_bool_series(s) -> pd.Series:
    if s is None:
        return pd.Series([], dtype=bool)
    ser = _series(s).astype(str).str.strip().str.lower()
    return ser.isin(["true","1","oui","vrai","yes","y","t"])

def _to_num(s) -> pd.Series:
    if s is None:
        return pd.Series([], dtype="float64")
    ser = _series(s).astype(str)
    ser = (ser.str.replace("€","", regex=False)
              .str.replace(" ","", regex=False)
              .str.replace(",",".", regex=False)
              .str.strip())
    return pd.to_numeric(ser, errors="coerce")

def _to_date(s) -> pd.Series:
    """Accepte JJ/MM/AAAA, AAAA-MM-JJ, etc. -> .dt.date"""
    if s is None:
        return pd.Series([], dtype="object")
    ser = _series(s)
    d = pd.to_datetime(ser, errors="coerce", dayfirst=True)
    # si beaucoup NaT, tente Y-M-D
    if d.isna().mean() > 0.5:
        d2 = pd.to_datetime(ser, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)

    # Numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # Dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # Recalcul nuitees si possible
    mask = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[mask, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask, "date_depart"])
        df.loc[mask, "nuitees"] = (dd - da).dt.days.clip(lower=0)
    except Exception:
        pass

    df["prix_net"] = (_to_num(df["prix_brut"]) - _to_num(df["commissions"]) - _to_num(df["frais_cb"])).fillna(0.0)
    df["charges"]  = (_to_num(df["prix_brut"]) - _to_num(df["prix_net"])).fillna(0.0)
    df["base"]     = (_to_num(df["prix_net"]) - _to_num(df["menage"]) - _to_num(df["taxes_sejour"])).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(_to_num(df["prix_brut"])>0, (_to_num(df["charges"]) / _to_num(df["prix_brut"]) * 100), 0)
    df["%"] = pd.to_numeric(pct, errors="coerce").fillna(0.0)

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

    # Strings clés nettoyées
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = _series(df[c]).astype(str).replace({"nan": "", "None": ""}).str.strip()

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
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfn = ensure_schema(df)
    arr = dfn[dfn["date_arrivee"] == today][["nom_client","telephone","plateforme"]]
    dep = dfn[dfn["date_depart"]  == today][["nom_client","telephone","plateforme"]]

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        if arr.empty:
            st.info("Aucune arrivée aujourd'hui.")
        else:
            st.dataframe(arr, use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        if dep.empty:
            st.info("Aucun départ aujourd'hui.")
        else:
            st.dataframe(dep, use_container_width=True)

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation."); return

    years_ser  = pd.to_numeric(dfn["AAAA"], errors="coerce")
    months_ser = pd.to_numeric(dfn["MM"],   errors="coerce")
    years  = ["Toutes"] + (sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True) if not years_ser.dropna().empty else [])
    months = ["Tous"]   + (sorted(months_ser.dropna().astype(int).unique().tolist()) if not months_ser.dropna().empty else list(range(1,13)))
    plats  = ["Toutes"] + sorted(dfn["plateforme"].dropna().astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())

    colf1, colf2, colf3 = st.columns(3)
    year   = colf1.selectbox("Année", years, index=0)
    month  = colf2.selectbox("Mois", months, index=0)
    plat   = colf3.selectbox("Plateforme", plats, index=0)

    data = dfn.copy()
    if year != "Toutes":
        data = data[pd.to_numeric(data["AAAA"], errors="coerce").fillna(-1).astype(int) == int(year)]
    if month != "Tous":
        data = data[pd.to_numeric(data["MM"], errors="coerce").fillna(-1).astype(int) == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]

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

    # Tri par date d’arrivée si dispo
    if "date_arrivee" in data.columns:
        order = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
        data = data.loc[order]

    st.dataframe(data, use_container_width=True)

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
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = dfn.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client','')} ({r.get('date_arrivee','')})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not sel: return
    idx = int(sel.split(":")[0])
    original_idx = df_sorted.loc[idx, "index"]
    row = dfn.loc[original_idx]

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
            try:
                plat_idx = palette_keys.index(row.get("plateforme"))
            except Exception:
                plat_idx = 0
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
                dfn.loc[original_idx, k] = v
            df2 = ensure_schema(dfn)
            if sauvegarder_donnees(df2):
                st.success("Modifié ✅"); st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = dfn.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé."); st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Plateformes & couleurs")
    base = pd.DataFrame(list(palette.items()), columns=["plateforme","couleur"])
    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True)
    c1, c2 = st.columns([0.6,0.4])
    if c1.button("💾 Enregistrer la palette"):
        try:
            edited.to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette enregistrée ✅"); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")
    if c2.button("↩️ Restaurer palette par défaut"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"]).to_csv(CSV_PLATEFORMES, sep=";", index=False)
            st.success("Palette par défaut restaurée."); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

# --------- CALENDRIER EN GRILLE ----------
def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")
    dfn = ensure_schema(df)
    dfv = dfn.dropna(subset=['date_arrivee','date_depart']).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

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
    st.subheader("Détail du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()
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


# ============================== RAPPORT ==============================
def vue_rapport(df, palette):
    st.header("📊 Rapport")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune donnée."); return

    years = sorted(pd.to_numeric(dfn["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    months = ["Tous"] + list(range(1,13))
    plats  = ["Tous"] + sorted(dfn["plateforme"].dropna().astype(str).unique())

    c1, c2, c3, c4 = st.columns(4)
    year   = c1.selectbox("Année", years, index=0)
    month  = c2.selectbox("Mois", months, index=0)
    plat   = c3.selectbox("Plateforme", plats, index=0)
    metric = c4.selectbox("Métrique", ["prix_brut","prix_net","base","charges","nuitees","menage","taxes_sejour"], index=1)

    data = dfn[pd.to_numeric(dfn["AAAA"], errors="coerce")==int(year)].copy()
    if month!="Tous": data = data[pd.to_numeric(data["MM"], errors="coerce")==int(month)]
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


# ============================== OUTIL COPIE ==============================
def _copy_button(label: str, payload: str, key: str):
    st.text_area("Aperçu", payload, height=210, key=f"ta_{key}")
    st.caption("Sélectionnez le texte ci-dessus et copiez-le (Ctrl/Cmd+C).")


# ============================== SMS ==============================
def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    dfn = ensure_schema(df).copy()
    dfn["sms_envoye"] = _to_bool_series(dfn["sms_envoye"]).fillna(False)
    dfn["post_depart_envoye"] = _to_bool_series(dfn["post_depart_envoye"]).fillna(False)
    dfn["date_arrivee"] = _to_date(dfn["date_arrivee"])
    dfn["date_depart"]  = _to_date(dfn["date_depart"])

    # Pré-arrivée (J+1)
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = dfn.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"]==target_arrivee) & (~pre["sms_envoye"].astype(bool))]

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
                f"Nuitées : {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')},\n"
                "Bienvenue chez nous ! Pour organiser au mieux votre arrivée, merci de nous indiquer votre heure d'arrivée.\n\n"
                "🚗 Place de parking possible sur demande.\n"
                "⏱ Check-in 14:00 — Check-out 11:00.\n"
                "🧳 Consignes à bagages disponibles dans Nice.\n\n"
                "EN — Please tell us your arrival time.\n"
                "Parking on request. Check-in 2pm, Check-out 11am.\n\n"
                f"📝 Fiche d'arrivée : {FORM_SHORT_URL}\n\n"
                "Annick & Charley"
            )
            enc = quote(msg); e164 = _format_phone_e164(r["telephone"]); wa = re.sub(r"\D","", e164)
            _copy_button("📋 Copier le message", msg, key=f"pre_{i}")
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                dfn.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(dfn):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # Post-départ (J0)
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = dfn.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post = post[(post["date_depart"]==target_depart) & (~post["post_depart_envoye"].astype(bool))]

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
                "Un grand merci d'avoir choisi notre appartement pour votre séjour.\n\n"
                "Nous espérons que vous avez passé un moment aussi agréable que nous à vous accueillir.\n\n"
                "Si l'envie vous prend de revenir explorer encore un peu la ville, notre porte vous sera toujours grande ouverte.\n\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n"
                f"\nHello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n\n"
                "We hope you had as enjoyable a time as we did hosting you.\n\n"
                "If you feel like coming back to explore a little more, our door will always be open to you.\n\n"
                "We look forward to welcoming you back.\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2); e164b = _format_phone_e164(r2["telephone"]); wab = re.sub(r"\D","", e164b)
            _copy_button("📋 Copier le message", msg2, key=f"post_{j}")
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")
            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                dfn.loc[r2["_rowid"], "post_depart_envoye"] = True
                if sauvegarder_donnees(dfn):
                    st.success("Marqué ✅"); st.rerun()


# ============================== EXPORT ICS ==============================
def vue_export_ics(df, palette):
    st.header("📆 Export ICS (Google Calendar)")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucune réservation."); return

    years = sorted(pd.to_numeric(dfn["AAAA"], errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
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
    st.download_button("📥 Télécharger .ics", data=ics.encode("utf-8"), file_name=f"reservations_{year}.ics", mime="text/calendar")


# ============================== IMPORT ICS (Google public) ==============================
def _convert_google_embed_to_ics_url(url: str) -> str:
    """
    Convertit une URL embed Google Calendar en URL .ics publique.
    Exemple:
      https://calendar.google.com/calendar/embed?src=XXXXX
    =>  https://calendar.google.com/calendar/ical/XXXXX/public/basic.ics
    """
    try:
        p = urlparse(url)
        if p.netloc.endswith("google.com") and "calendar" in p.path and "ical" not in p.path:
            qs = parse_qs(p.query)
            src = None
            # support 'src' ou 'cid' selon versions
            if "src" in qs and len(qs["src"])>0:
                src = qs["src"][0]
            elif "cid" in qs and len(qs["cid"])>0:
                src = qs["cid"][0]
            if src:
                return f"https://calendar.google.com/calendar/ical/{src}/public/basic.ics"
        # si ça ressemble déjà à .ics, renvoyer tel quel
        if url.strip().lower().endswith(".ics"):
            return url
    except Exception:
        pass
    return url  # fallback

def _parse_ics(text: str) -> pd.DataFrame:
    """
    Parse minimal d'un ICS: récupère DTSTART, DTEND, SUMMARY.
    Tente d'extraire nom_client & plateforme à partir de SUMMARY:
      "Villa Tobias — John Doe (Booking)" -> nom="John Doe", plateforme="Booking"
    """
    rows = []
    cur = {}
    for line in text.splitlines():
        line = line.strip()
        if line == "BEGIN:VEVENT":
            cur = {}
        elif line == "END:VEVENT":
            if cur:
                rows.append(cur)
            cur = {}
        else:
            if ":" in line:
                k, v = line.split(":", 1)
                cur[k] = v

    def _parse_dt(v):
        # Support YYYYMMDD ou YYYYMMDDT...
        if not v: return None
        v = v.strip()
        if len(v)>=8 and v[:8].isdigit():
            y, m, d = int(v[:4]), int(v[4:6]), int(v[6:8])
            try:
                return date(y,m,d)
            except Exception:
                return None
        return None

    data = []
    for ev in rows:
        dtstart = ev.get("DTSTART") or ev.get("DTSTART;VALUE=DATE")
        dtend   = ev.get("DTEND")   or ev.get("DTEND;VALUE=DATE")
        start = _parse_dt(dtstart)
        end   = _parse_dt(dtend)
        summary = ev.get("SUMMARY","").strip()

        nom_client = summary
        plateforme = None
        # Heuristique: "Villa Tobias — John Doe (Booking)"
        if "—" in summary:
            nom_part = summary.split("—",1)[1].strip()
            nom_client = nom_part
        if "(" in nom_client and nom_client.endswith(")"):
            try:
                plateforme = nom_client[nom_client.rfind("(")+1:-1]
                nom_client = nom_client[:nom_client.rfind("(")].strip()
            except Exception:
                pass

        if start and end:
            nuits = (pd.to_datetime(end) - pd.to_datetime(start)).days
        else:
            nuits = 0

        data.append({
            "nom_client": nom_client or "",
            "plateforme": plateforme or "Autre",
            "date_arrivee": start,
            "date_depart": end,
            "nuitees": max(0, int(nuits)),
        })

    df = pd.DataFrame(data)
    return ensure_schema(df)

def vue_import_ics(df, palette):
    st.header("📥 Import iCal (Google public)")
    st.markdown(
        "Collez ici l’URL **publique** de votre calendrier Google. "
        "Si c’est une URL *embed* (avec `.../embed?src=...`), je la convertis automatiquement en `.ics`."
    )
    default_url = "https://calendar.google.com/calendar/embed?src=c_29689401d77e1c4871f818"
    url = st.text_input("URL iCal publique (.ics ou embed)", value=default_url, placeholder="https://...basic.ics")
    if st.button("🔁 Convertir en .ics"):
        st.write("URL .ics devinée :")
        st.code(_convert_google_embed_to_ics_url(url), language="text")

    uploaded = st.file_uploader("…ou déposez un fichier .ics", type=["ics"])

    # Lecture source
    ics_text = None
    if uploaded is not None:
        try:
            ics_text = uploaded.read().decode("utf-8", errors="ignore")
        except Exception as e:
            st.error(f"Lecture du fichier échouée : {e}")
            return
    elif url:
        try:
            import requests
            ics_url = _convert_google_embed_to_ics_url(url)
            resp = requests.get(ics_url, timeout=20)
            resp.raise_for_status()
            ics_text = resp.text
        except Exception as e:
            st.error(f"Téléchargement iCal échoué : {e}")
            return
    else:
        st.info("Renseignez une URL ou chargez un fichier .ics.")
        return

    try:
        imported = _parse_ics(ics_text)
        if imported.empty:
            st.warning("Aucun événement VEVENT exploitable trouvé dans ce fichier.")
            return
        st.success(f"{len(imported)} événements iCal détectés.")
        st.dataframe(imported[["nom_client","plateforme","date_arrivee","date_depart","nuitees"]], use_container_width=True)

        # Fusion (ajoute sans dédoublonner — vous pouvez filtrer ensuite)
        if st.button("➕ Ajouter ces réservations au CSV"):
            merged = ensure_schema(pd.concat([df, imported], ignore_index=True))
            if sauvegarder_donnees(merged):
                st.success("Import terminé ✅"); st.rerun()
    except Exception as e:
        st.error(f"Erreur pendant le parsing iCal : {e}")


# ============================== CLIENTS ==============================
def vue_clients(df, palette):
    st.header("👥 Liste des clients")
    dfn = ensure_schema(df)
    if dfn.empty:
        st.info("Aucun client."); return
    clients = (dfn[['nom_client','telephone','email','plateforme','res_id']]
               .copy())
    # Nettoyage basique
    clients["nom_client"] = _series(clients["nom_client"]).astype(str).str.strip()
    clients["telephone"]  = _series(clients["telephone"]).astype(str).str.strip()
    clients["email"]      = _series(clients["email"]).astype(str).str.strip()

    clients = clients[clients["nom_client"]!=""]
    clients = clients.drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)


# ============================== ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")

    try:
        st.sidebar.download_button(
            "Télécharger CSV",
            data=ensure_schema(df).to_csv(sep=";", index=False).encode("utf-8"),
            file_name=CSV_RESERVATIONS,
            mime="text/csv"
        )
    except Exception:
        pass

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
    # Thème sombre par défaut (lisible PC)
    try:
        dark_mode = st.sidebar.toggle("🌗 Mode sombre", value=True)
    except Exception:
        dark_mode = True
    apply_style(dark=bool(dark_mode))

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
        "📥 Import iCal (Google)": vue_import_ics,
        "👥 Clients": vue_clients,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)


if __name__ == "__main__":
    main()