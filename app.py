# -*- coding: utf-8 -*-
import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re, uuid, hashlib, json
from datetime import date, datetime, timedelta
from calendar import monthrange, Calendar
from urllib.parse import quote
from io import StringIO

# ============================== 0) CONFIG & THEME ==============================
st.set_page_config(page_title="✨ Villa Tobias — Réservations", page_icon="✨", layout="wide")

# purge prudente au chargement (ne plante pas si indispo)
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
GOOGLE_FORM_URL = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

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
          padding:6px 10px; border-radius:12px; margin:4px 6px; font-size:.85rem
        }}
        .kpi-line strong {{ font-size:1.05rem; }}
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

# ============================== 1) HELPERS DE TYPE ==============================
def _series(obj, dtype=None):
    """Garantit une Series (évite les ndarray sans fillna)."""
    if isinstance(obj, pd.Series):
        s = obj.copy()
    elif isinstance(obj, (list, tuple, np.ndarray)):
        s = pd.Series(obj)
    else:
        s = pd.Series([]) if obj is None else pd.Series(obj)
    if dtype:
        try: s = s.astype(dtype)
        except Exception: pass
    return s

def _to_bool_series(s) -> pd.Series:
    ser = _series(s, "string").fillna("")
    return ser.str.strip().str.lower().isin(["true","1","oui","vrai","yes","y","t"])

def _to_num(s) -> pd.Series:
    ser = _series(s, "string").fillna("")
    ser = (ser.str.replace("€","", regex=False)
              .str.replace(" ", "", regex=False)
              .str.replace("\u00A0","", regex=False)   # espace insécable
              .str.replace(",", ".", regex=False)
              .str.replace(r"[^\d\.\-]", "", regex=True)
              .str.strip())
    return pd.to_numeric(ser, errors="coerce")

def _to_date(s) -> pd.Series:
    """Accepte JJ/MM/AAAA, AAAA-MM-JJ, JJ-MM-AAAA, retourne date."""
    ser = _series(s, "string").fillna("").str.strip()
    if ser.empty:
        return pd.Series([], dtype="object")
    # 1) tentative flexible dayfirst
    d = pd.to_datetime(ser, errors="coerce", dayfirst=True)
    # 2) complète avec ISO si NaT
    mask_nat = d.isna()
    if mask_nat.any():
        d2 = pd.to_datetime(ser[mask_nat], errors="coerce", format="%Y-%m-%d")
        d = d.where(~mask_nat, d2)
    return d.dt.date

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

# ============================== 2) SCHEMA & IO ==============================
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid","AAAA","MM"
]

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if raw is None: return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff","")
    # essai multi-separateurs
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

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # alias éventuels
    df.rename(columns={
        'Payé':'paye', 'Client':'nom_client', 'Plateforme':'plateforme',
        'Arrivée':'date_arrivee', 'Départ':'date_depart', 'Nuits':'nuitees',
        'Brut (€)':'prix_brut'
    }, inplace=True)

    # ajouter colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # booléens
    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]).fillna(False).astype(bool)

    # numériques
    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    # dates
    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    # recalcul nuitées si possible
    ok = df["date_arrivee"].notna() & df["date_depart"].notna()
    try:
        da = pd.to_datetime(df.loc[ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[ok, "date_depart"])
        df.loc[ok, "nuitees"] = (dd - da).dt.days.clip(lower=0)
    except Exception:
        pass

    # dérivées
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

    # strings propres
    for c in ["nom_client","plateforme","telephone","email"]:
        df[c] = _series(df[c], "string").fillna("").str.replace("nan","").str.replace("None","").str.strip()

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

# ============================== 3) VUES ==============================
def vue_accueil(df, palette):
    st.header("🏠 Accueil")
    today = date.today()
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")
    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])
    arr = dfv[dfv["date_arrivee"] == today][["nom_client","telephone","plateforme"]]
    dep = dfv[dfv["date_depart"]  == today][["nom_client","telephone","plateforme"]]
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame(columns=["nom_client","telephone","plateforme"]),
                     use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame(columns=["nom_client","telephone","plateforme"]),
                     use_container_width=True)

def vue_reservations(df, palette):
    st.header("📋 Réservations")
    if df is None or df.empty:
        st.info("Aucune réservation."); return

    years_ser  = pd.to_numeric(_series(df.get("AAAA")), errors="coerce")
    months_ser = pd.to_numeric(_series(df.get("MM")),   errors="coerce")

    years_unique  = sorted(years_ser.dropna().astype(int).unique().tolist(), reverse=True) if not years_ser.dropna().empty else []
    months_unique = sorted(months_ser.dropna().astype(int).unique().tolist()) if not months_ser.dropna().empty else list(range(1,13))

    colf1, colf2, colf3 = st.columns(3)
    year   = colf1.selectbox("Année", ["Toutes"] + years_unique, index=0)
    month  = colf2.selectbox("Mois", ["Tous"] + months_unique, index=0)
    plats_all = sorted(_series(df["plateforme"], "string").fillna("").replace({"": np.nan}).dropna().unique().tolist())
    plat   = colf3.selectbox("Plateforme", ["Toutes"] + plats_all, index=0)

    data = df.copy()
    if year != "Toutes":
        data = data[pd.to_numeric(_series(data["AAAA"]), errors="coerce").fillna(-1).astype(int) == int(year)]
    if month != "Tous":
        data = data[pd.to_numeric(_series(data["MM"]), errors="coerce").fillna(-1).astype(int) == int(month)]
    if plat != "Toutes":
        data = data[_series(data["plateforme"], "string").str.strip() == str(plat).strip()]

    # Nouvelle vérification pour éviter l'erreur
    if data.empty:
        brut, net, commissions, frais_cb, menage, taxes, nuits, nb_resas = 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0, 0
    else:
        brut        = float(pd.to_numeric(data["prix_brut"]).sum())
        net         = float(pd.to_numeric(data["prix_net"]).sum())
        commissions = float(pd.to_numeric(data["commissions"]).sum())
        frais_cb    = float(pd.to_numeric(data["frais_cb"]).sum())
        menage      = float(pd.to_numeric(data["menage"]).sum())
        taxes       = float(pd.to_numeric(data["taxes_sejour"]).sum())
        nuits       = int(pd.to_numeric(data["nuitees"]).sum())
        nb_resas    = len(data)

    st.markdown("---")
    
    # Ligne de totaux principale (revenus)
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(label="Revenu Brut Total", value=f"{brut:,.2f} €".replace(",", " "))
    with col2:
        st.metric(label="Revenu Net Total", value=f"{net:,.2f} €".replace(",", " "))
    with col3:
        st.metric(label="Commissions", value=f"{commissions:,.2f} €".replace(",", " "))

    # Ligne de totaux secondaire (frais et stats)
    col4, col5, col6, col7, col8 = st.columns(5)
    with col4:
        st.metric(label="Frais CB", value=f"{frais_cb:,.2f} €".replace(",", " "))
    with col5:
        st.metric(label="Ménage", value=f"{menage:,.2f} €".replace(",", " "))
    with col6:
        st.metric(label="Taxes", value=f"{taxes:,.2f} €".replace(",", " "))
    with col7:
        st.metric(label="Total Nuitées", value=f"{nuits} nuits")
    with col8:
        st.metric(label="Total Réservations", value=f"{nb_resas} res.")

    st.markdown("---")

    # tri par date d'arrivée
    order = pd.to_datetime(_series(data["date_arrivee"]), errors="coerce").sort_values(ascending=False).index
    data = data.loc[order]
    st.dataframe(data, use_container_width=True)

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une réservation")
    with st.form("form_add", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom du client")
            email = st.text_input("Email (facultatif, sinon via le Form)")
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
                    st.success(f"Réservation pour {nom} ajoutée."); st.rerun()

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer")
    if df.empty: st.info("Aucune réservation."); return
    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client','')} ({r.get('date_arrivee','')})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not sel: return
    idx = int(sel.split(":")[0]); original_idx = df_sorted.loc[idx, "index"]; row = df.loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get("nom_client","") or "")
            email = st.text_input("Email", value=row.get("email","") or "")
            tel = st.text_input("Téléphone", value=row.get("telephone","") or "")
            arrivee = st.date_input("Arrivée", value=row.get("date_arrivee"))
            depart  = st.date_input("Départ", value=row.get("date_depart"))
        with c2:
            keys = list(palette.keys())
            plat_idx = keys.index(row.get("plateforme")) if row.get("plateforme") in keys else 0
            plat = st.selectbox("Plateforme", options=keys, index=plat_idx)
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=float(row.get("prix_brut") or 0))
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=float(row.get("commissions") or 0))
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=float(row.get("frais_cb") or 0))
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=float(row.get("menage") or 0))
            taxes  = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=float(row.get("taxes_sejour") or 0))

        b1, b2 = st.columns([0.7, 0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            updates = {
                "nom_client": nom, "email": email, "telephone": tel, "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye, "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes
            }
            for k, v in updates.items(): df.loc[original_idx, k] = v
            if sauvegarder_donnees(ensure_schema(df)): st.success("Modifié ✅"); st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2): st.warning("Supprimé."); st.rerun()

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
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme","couleur"])\
              .to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8")
            st.success("Palette par défaut restaurée."); st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

def vue_calendrier(df, palette):
    st.header("📅 Calendrier (grille mensuelle)")
    dfv = df.dropna(subset=['date_arrivee','date_depart']).copy()
    if dfv.empty: st.info("Aucune réservation à afficher."); return
    today = date.today()
    years = sorted(pd.to_datetime(_series(dfv["date_arrivee"]), errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois", options=list(range(1,13)), index=today.month-1)

    st.markdown("<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>", unsafe_allow_html=True)

    def day_resas(d):
        mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)
    html = ["<div class='cal-grid'>"]
    for week in cal.monthdatescalendar(annee, mois):
        for d in week:
            outside = (d.month != mois)
            classes = "cal-cell outside" if outside else "cal-cell"
            cell = f"<div class='{classes}'>"
            cell += f"<div class='cal-date'>{d.day}</div>"
            if not outside:
                rs = day_resas(d)
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
    debut_mois = date(annee, mois, 1); fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()
    plats = ["Toutes"] + sorted(_series(rows["plateforme"], "string").fillna("").replace({"": np.nan}).dropna().unique().tolist())
    plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
    if plat != "Toutes": rows = rows[rows["plateforme"]==plat]
    brut = float(pd.to_numeric(_series(rows["prix_brut"]), errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(_series(rows["prix_net"]),  errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(_series(rows["nuitees"]),    errors="coerce").fillna(0).sum())
    html = f"""
    <div class='glass kpi-line'>
      <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
      <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
      <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
    </div>
    """.replace(",", " ")
    st.markdown(html, unsafe_allow_html=True)
    st.dataframe(rows[["nom_client","plateforme","date_arrivee","date_depart","nuitees","paye"]],
                 use_container_width=True)

def vue_rapport(df, palette):
    st.header("📊 Rapport")
    if df.empty: st.info("Aucune donnée."); return
    years = sorted(pd.to_numeric(_series(df["AAAA"]), errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année", years, index=0)
    months = ["Tous"] + list(range(1,13))
    month = st.selectbox("Mois", months, index=0)
    plats = ["Tous"] + sorted(_series(df["plateforme"], "string").fillna("").replace({"": np.nan}).dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)
    metric = st.selectbox("Métrique", ["prix_brut","prix_net","menage","nuitees","charges","base"], index=0)

    data = df[pd.to_numeric(_series(df["AAAA"]), errors="coerce")==year].copy()
    if month!="Tous": data = data[pd.to_numeric(_series(data["MM"]), errors="coerce")==int(month)]
    if plat!="Tous":  data = data[_series(data["plateforme"], "string")==plat]
    if data.empty: st.warning("Aucune donnée après filtres."); return

    data["mois"] = pd.to_datetime(_series(data["date_arrivee"]), errors="coerce").dt.to_period("M").astype(str)
    agg = data.groupby(["mois","plateforme"], as_index=False).agg({metric:"sum"})
    total_val = float(pd.to_numeric(_series(agg[metric]), errors="coerce").fillna(0).sum())

    st.markdown(f"**Total {metric.replace('_',' ')} : {total_val:,.2f}**".replace(",", " "))
    st.dataframe(agg, use_container_width=True)

    chart = alt.Chart(agg).mark_bar().encode(
        x="mois:N",
        y=alt.Y(f"{metric}:Q", title=metric.replace("_"," ").title()),
        color="plateforme:N",
        tooltip=["mois","plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
    )
    st.altair_chart(chart.properties(height=420), use_container_width=True)

def _copy_block(payload: str, height=180, key: str="copy"):
    st.text_area("Aperçu à copier", payload, height=height, key=f"ta_{key}")
    st.caption("Sélectionnez le texte et copiez-le (Ctrl/Cmd + C).")

def vue_sms(df, palette):
    st.header("✉️ SMS & WhatsApp")

    # Pré-arrivée (J+1)
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre["date_arrivee"] = _to_date(pre["date_arrivee"])
    pre["date_depart"]  = _to_date(pre["date_depart"])
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
                f"Bonjour {r.get('nom_client')}\nTéléphone : {r.get('telephone')}\n\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. "
                "Afin d'organiser au mieux votre arrivée, merci de nous indiquer votre heure d'arrivée.\n\n"
                "Parking possible sur demande. Check-in 14:00, check-out 11:00.\n\n"
                "Merci de remplir la fiche d'arrivée :\n"
                f"{FORM_SHORT_URL}\n\n"
                "EN — Please tell us your arrival time. Parking on request. "
                "Check-in 2pm, check-out 11am.\n"
                f"Form: {FORM_SHORT_URL}\n\n"
                "Annick & Charley"
            )
            enc = quote(msg); e164 = _format_phone_e164(r["telephone"]); wa = re.sub(r"\D","", e164)
            _copy_block(msg, key=f"pre_{i}")
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")
            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(ensure_schema(df)):
                    st.success("Marqué ✅"); st.rerun()

    st.markdown("---")

    # Post-départ (J0)
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = df.dropna(subset=["telephone","nom_client","date_depart"]).copy()
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
                "Un grand merci d'avoir choisi notre appartement pour votre séjour.\n\n"
                "Nous espérons que vous avez passé un moment aussi agréable que celui que nous avons eu à vous accueillir.\n\n"
                "Si l'envie vous prend de revenir explorer encore un peu notre ville, sachez que notre porte vous sera toujours grande ouverte.\n\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n\n"
                "We hope you had as enjoyable a time as we did hosting you.\n\n"
                "If you feel like coming back to explore our city a little more, our door will always be open to you.\n\n"
                "We look forward to welcoming you back.\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2); e164b = _format_phone_e164(r2["telephone"]); wab = re.sub(r"\D","", e164b)
            _copy_block(msg2, key=f"post_{j}")
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
    if df.empty: st.info("Aucune réservation."); return
    years = sorted(pd.to_numeric(_series(df["AAAA"]), errors="coerce").dropna().astype(int).unique(), reverse=True)
    year  = st.selectbox("Année (arrivées)", years, index=0)
    plats = ["Tous"] + sorted(_series(df["plateforme"], "string").fillna("").replace({"": np.nan}).dropna().unique())
    plat  = st.selectbox("Plateforme", plats, index=0)

    data = df[pd.to_numeric(_series(df["AAAA"]), errors="coerce")==year].copy()
    if plat!="Tous": data = data[_series(data["plateforme"], "string")==plat]
    if data.empty: st.warning("Rien à exporter."); return

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

def vue_google_sheet(df, palette):
    st.header("📝 Fiche d'arrivée / Google Sheet")
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")
    st.markdown(f'<iframe src="{GOOGLE_FORM_URL}" width="100%" height="900" frameborder="0"></iframe>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("Feuille Google intégrée")
    st.markdown(f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>', unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("Réponses (CSV publié)")
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
        show_email = st.checkbox("Afficher les colonnes d'email (si présentes)", value=False)
        if not show_email:
            mask_cols = [c for c in rep.columns if "mail" in c.lower() or "email" in c.lower()]
            rep = rep.drop(columns=mask_cols, errors="ignore")
        st.dataframe(rep, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")

def vue_clients(df, palette):
    st.header("👥 Liste des clients")
    if df.empty: st.info("Aucun client."); return
    cols = ["nom_client","telephone","email","plateforme","res_id"]
    clients = ensure_schema(df)[cols].copy()
    clients["nom_client"] = _series(clients["nom_client"], "string").fillna("").str.strip()
    clients["telephone"]  = _series(clients["telephone"], "string").fillna("").str.strip()
    clients["email"]      = _series(clients["email"], "string").fillna("").str.strip()
    clients = clients.loc[clients["nom_client"] != ""]
    clients = clients.drop_duplicates().sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)

# ============================== 4) ADMIN ==============================
def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button(
        "📥 Télécharger CSV",
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
            st.cache_data.clear()
            st.success("Fichier restauré. Rechargement…"); st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur : {e}")

    if st.sidebar.button("🧹 Vider le cache & recharger"):
        for _clear in (getattr(st, "cache_data", None), getattr(st, "cache_resource", None)):
            try:
                if _clear: _clear.clear()
            except Exception:
                pass
        st.success("Cache vidé. Rechargement…"); st.rerun()

# ============================== 5) MAIN ==============================
def main():
    # Mode sombre par défaut (lisible PC), toggle pour mode clair
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
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📆 Export ICS": vue_export_ics,
        "📝 Google Sheet": vue_google_sheet,
        "👥 Clients": vue_clients,
    }
    choice = st.sidebar.radio("Aller à", list(pages.keys()))
    pages[choice](df, palette)
    admin_sidebar(df)

if __name__ == "__main__":
    main()
