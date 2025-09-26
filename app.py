# ============================== PART 1/5 — IMPORTS, CONFIG, STYLES, HELPERS ==============================
import os, io, re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange
from urllib.parse import quote
from html import escape

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

# ---------------- CONFIG APP ----------------
st.set_page_config(
    page_title="✨ Villa Tobias — Gestion des Réservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- CONSTANTES ----------------
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"
APARTMENTS_CSV   = "apartments.csv"
INDICATIFS_CSV   = "indicatifs_pays.csv"   # <— nom exact demandé

DEFAULT_PALETTE = {
    "Booking": "#1b9e77",
    "Airbnb":  "#d95f02",
    "Abritel": "#7570b3",
    "Direct":  "#e7298a",
}

FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","pays",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid"
]

# ---------------- STYLES & PRINT ----------------
def apply_style(light: bool):
    bg     = "#fafafa" if light else "#0f1115"
    fg     = "#0f172a" if light else "#eaeef6"
    side   = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    calbg  = "#fff" if light else "#0b0d12"
    chipbg = "#eee" if light else "#2a2f3a"
    chipfg = "#222" if light else "#eee"

    st.markdown(
        f"""
        <style>
          html, body, [data-testid="stAppViewContainer"] {{ background:{bg}; color:{fg}; }}
          [data-testid="stSidebar"] {{ background:{side}; border-right:1px solid {border}; }}
          .glass {{ background:{"rgba(255,255,255,.65)" if light else "rgba(255,255,255,.06)"}; 
                   border:1px solid {border}; border-radius:12px; padding:12px; margin:10px 0; }}
          .chip {{ display:inline-block; padding:6px 10px; border-radius:12px; margin:4px 6px; 
                   font-size:.86rem; background:{chipbg}; color:{chipfg} }}
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; }}
          .cal-cell {{ border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px; position:relative; overflow:hidden; background:{calbg}; }}
          .cal-cell.outside {{ opacity:.45; }}
          .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
          .resa-pill {{ padding:4px 6px; border-radius:6px; font-size:.84rem; margin-top:22px; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
          .cal-header {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; font-weight:700; opacity:.8; margin:6px 0 8px; }}

          /* Impression A4 paysage + colonnes techniques masquées */
          @page {{ size: A4 landscape; margin: 12mm; }}
          @media print {{
            [data-testid="stSidebar"], header, footer {{ display:none !important; }}
            .print-hide {{ display:none !important; }}
            .print-header {{ display:block !important; }}
            .stDataFrame [data-testid="column-header"][aria-label="res_id"],
            .stDataFrame [data-testid="column-header"][aria-label="ical_uid"],
            .stDataFrame [data-testid="column-header"][aria-label="%"] {{
              display:none !important;
            }}
          }}
          .print-header {{ display:none; font-size:14px; margin-bottom:8px; }}
        </style>
        """,
        unsafe_allow_html=True
    )

def print_buttons(location: str = "main"):
    target = st.sidebar if location == "sidebar" else st
    target.button("🖨️ Imprimer", key=f"print_btn_{location}")
    st.markdown(
        """
        <script>
        const labels = Array.from(parent.document.querySelectorAll('button span, button p'));
        const btn = labels.find(n => n.textContent && n.textContent.trim() === "🖨️ Imprimer");
        if (btn) { btn.parentElement.onclick = () => window.print(); }
        </script>
        """,
        unsafe_allow_html=True
    )

# ---------------- HELPERS GÉNÉRIQUES ----------------
def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f: 
            return f.read()
    except Exception:
        return None

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if not raw: return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff","")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(io.StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 2: return df
        except Exception:
            pass
    try:
        return pd.read_csv(io.StringIO(txt), dtype=str)
    except Exception:
        return pd.DataFrame()

def _as_series(x, index=None):
    if isinstance(x, pd.Series): return x
    if isinstance(x, (list, tuple, np.ndarray)):
        s = pd.Series(list(x))
        if index is not None and len(index) == len(s): s.index = index
        return s
    if index is None: return pd.Series([x])
    return pd.Series([x] * len(index), index=index)

def _to_bool_series(s: pd.Series) -> pd.Series:
    s = _as_series(s)
    out = s.astype(str).str.strip().str.lower().isin(["true","1","oui","vrai","yes","y","t"])
    return out.fillna(False).astype(bool)

def _to_num(s: pd.Series) -> pd.Series:
    s = _as_series(s)
    sc = (s.astype(str).str.replace("€","",regex=False)
                  .str.replace(" ","",regex=False)
                  .str.replace(",",".",regex=False).str.strip())
    return pd.to_numeric(sc, errors="coerce")

def _to_date(s: pd.Series) -> pd.Series:
    s = _as_series(s)
    d = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if len(d) and d.isna().mean() > 0.5:
        d2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        d = d.fillna(d2)
    return d.dt.date

def build_stable_uid(row) -> str:
    base = f"{row.get('res_id','')}{row.get('nom_client','')}{row.get('telephone','')}"
    return hashlib.sha1(base.encode()).hexdigest() + "@villa-tobias"

def _df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Reservations"):
    from io import BytesIO
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        return buf.getvalue(), None
    except Exception as e:
        st.warning(f"Impossible de générer un Excel (openpyxl requis) : {e}")
        return None, e

 # ============================== PART 2/5 — APARTMENTS, DATA LOAD, INDICATIFS ==============================

# ---------------- Apartments ----------------
def _load_apartments() -> pd.DataFrame:
    if not os.path.exists(APARTMENTS_CSV):
        df = pd.DataFrame([{"slug": "villa-tobias", "name": "Villa Tobias"}])
        df.to_csv(APARTMENTS_CSV, index=False, encoding="utf-8")
    return pd.read_csv(APARTMENTS_CSV, dtype=str)

def _current_apartment():
    apts = _load_apartments()
    if apts.empty: return None
    slug = st.session_state.get("apartment_slug", apts.iloc[0]["slug"])
    found = apts[apts["slug"] == slug]
    if not found.empty: return found.iloc[0].to_dict()
    return apts.iloc[0].to_dict()

def _select_apartment_sidebar():
    apts = _load_apartments()
    if apts.empty:
        st.sidebar.error("Aucun appartement trouvé dans apartments.csv")
        return False
    slugs = apts["slug"].tolist()
    names = apts["name"].tolist()
    slug_to_name = dict(zip(slugs, names))
    current = st.sidebar.selectbox("### Appartement", slugs,
                                   format_func=lambda x: slug_to_name.get(x, x),
                                   index=slugs.index(st.session_state.get("apartment_slug", slugs[0])))
    if current != st.session_state.get("apartment_slug"):
        st.session_state["apartment_slug"] = current
        st.session_state["CSV_RESERVATIONS"] = f"{current}_reservations.csv"
        st.session_state["CSV_PLATEFORMES"]  = f"{current}_plateformes.csv"
        return True
    st.session_state.setdefault("apartment_slug", current)
    st.session_state.setdefault("CSV_RESERVATIONS", f"{current}_reservations.csv")
    st.session_state.setdefault("CSV_PLATEFORMES",  f"{current}_plateformes.csv")
    return False

# ---------------- Reservations Data ----------------
def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None: df = pd.DataFrame()
    for c in BASE_COLS:
        if c not in df.columns: df[c] = ""
    return df[BASE_COLS].copy()

@st.cache_data
def load_reservations(path: str) -> pd.DataFrame:
    if not os.path.exists(path): return ensure_schema(pd.DataFrame())
    try:
        df = pd.read_csv(path, dtype=str, sep=";")
    except Exception:
        try:
            df = pd.read_csv(path, dtype=str)
        except Exception:
            return ensure_schema(pd.DataFrame())
    return ensure_schema(df)

def save_reservations(df: pd.DataFrame, path: str) -> bool:
    try:
        df.to_csv(path, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        return True
    except Exception as e:
        st.error(f"Erreur sauvegarde {path} : {e}")
        return False

def _load_data_for_active_apartment():
    res_csv = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    plat_csv = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
    df = load_reservations(res_csv)

    if os.path.exists(plat_csv):
        try:
            pal = pd.read_csv(plat_csv, dtype=str).set_index("plateforme")["couleur"].to_dict()
        except Exception:
            pal = DEFAULT_PALETTE.copy()
    else:
        pal = DEFAULT_PALETTE.copy()
    return df, pal

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    path = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    return save_reservations(df, path)

# ---------------- Indicatifs pays ----------------
def create_indicatifs_csv():
    """Crée un CSV d'indicatifs minimal si absent (UTF-8)."""
    if not os.path.exists(INDICATIFS_CSV):
        base = [
            {"prefix": "33", "country": "France", "flag": "🇫🇷"},
            {"prefix": "34", "country": "Espagne", "flag": "🇪🇸"},
            {"prefix": "39", "country": "Italie", "flag": "🇮🇹"},
            {"prefix": "41", "country": "Suisse", "flag": "🇨🇭"},
            {"prefix": "32", "country": "Belgique", "flag": "🇧🇪"},
        ]
        pd.DataFrame(base).to_csv(INDICATIFS_CSV, index=False, encoding="utf-8")

@st.cache_data
def load_indicatifs() -> pd.DataFrame:
    create_indicatifs_csv()
    try:
        return pd.read_csv(INDICATIFS_CSV, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=["prefix","country","flag"])

def _phone_country(phone: str) -> str:
    if not phone or not isinstance(phone, str): return ""
    digits = re.sub(r"\D","", phone)
    indicatifs = load_indicatifs()
    indicatifs = indicatifs.sort_values("prefix", key=lambda s: s.str.len(), ascending=False)
    for _, row in indicatifs.iterrows():
        if digits.startswith(str(row["prefix"])):
            flag = row.get("flag","")
            return f"{flag} {row['country']}".strip()
    return ""

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if not s.startswith("0") and not s.startswith("+"):
        return "+" + s
    return s

# ============================== PART 3/5 — VUES: ACCUEIL, RÉSERVATIONS, AJOUTER, MODIFIER ==============================

# ---------- Accueil ----------
def vue_accueil(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    today = date.today()
    tomorrow = today + timedelta(days=1)

    work = df.copy()
    work["date_arrivee"] = pd.to_datetime(work["date_arrivee"], errors="coerce").dt.date
    work["date_depart"]  = pd.to_datetime(work["date_depart"], errors="coerce").dt.date

    arr = work[work["date_arrivee"] == today][["nom_client","telephone","plateforme","pays"]]
    dep = work[work["date_depart"]  == today][["nom_client","telephone","plateforme","pays"]]
    arr_plus1 = work[work["date_arrivee"] == tomorrow][["nom_client","telephone","plateforme","pays"]]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame({"info": ["Aucune arrivée."]}), use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame({"info": ["Aucun départ."]}), use_container_width=True)
    with c3:
        st.subheader("🟠 Arrivées J+1 (demain)")
        st.dataframe(arr_plus1 if not arr_plus1.empty else pd.DataFrame({"info": ["Aucune arrivée demain."]}), use_container_width=True)


# ---------- Réservations (liste + KPI) ----------
def _kpi_card(label: str, value: str):
    st.markdown(
        f"<div class='chip'><small>{label}</small><br><strong>{value}</strong></div>",
        unsafe_allow_html=True,
    )

def vue_reservations(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    dfa["date_depart_dt"]  = pd.to_datetime(dfa["date_depart"], errors="coerce")
    dfa["nuitees"] = pd.to_numeric(dfa["nuitees"], errors="coerce").fillna(0)

    years_avail  = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1, 12 + 1))
    plats_avail  = sorted(dfa["plateforme"].astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())

    c1, c2, c3, c4 = st.columns(4)
    year  = c1.selectbox("Année",     ["Toutes"] + years_avail, index=0)
    month = c2.selectbox("Mois",      ["Tous"] + months_avail, index=0)
    plat  = c3.selectbox("Plateforme",["Toutes"] + plats_avail, index=0)
    payf  = c4.selectbox("Paiement",  ["Tous", "Payé uniquement", "Non payé uniquement"], index=0)

    data = dfa.copy()
    if year != "Toutes":
        data = data[data["date_arrivee_dt"].dt.year == int(year)]
    if month != "Tous":
        data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]
    if payf == "Payé uniquement":
        data = data[_to_bool_series(data["paye"]) == True]
    elif payf == "Non payé uniquement":
        data = data[_to_bool_series(data["paye"]) == False]

    # KPI
    brut    = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net     = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    base    = float(pd.to_numeric(data["base"],     errors="coerce").fillna(0).sum())
    charges = float(pd.to_numeric(data["charges"],  errors="coerce").fillna(0).sum())
    nuits   = int(pd.to_numeric(data["nuitees"],    errors="coerce").fillna(0).sum())
    adr     = (net / nuits) if nuits > 0 else 0.0

    st.markdown("<div class='glass'>", unsafe_allow_html=True)
    kc1, kc2, kc3, kc4, kc5, kc6 = st.columns(6)
    with kc1: _kpi_card("Total brut", f"{brut:,.2f} €".replace(",", " "))
    with kc2: _kpi_card("Total net",  f"{net:,.2f} €".replace(",", " "))
    with kc3: _kpi_card("Charges",    f"{charges:,.2f} €".replace(",", " "))
    with kc4: _kpi_card("Base",       f"{base:,.2f} €".replace(",", " "))
    with kc5: _kpi_card("Nuitées",    f"{nuits}")
    with kc6: _kpi_card("ADR (net)",  f"{adr:,.2f} €".replace(",", " "))
    st.markdown("</div>", unsafe_allow_html=True)

    # Tableau principal
    order_idx = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order_idx]
    st.dataframe(data.drop(columns=["date_arrivee_dt", "date_depart_dt"], errors="ignore"), use_container_width=True)


# ---------- Ajouter ----------
def vue_ajouter(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter une réservation — {apt_name}")
    print_buttons()

    if df is None:
        df = ensure_schema(pd.DataFrame())

    with st.form("form_add", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom   = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel   = st.text_input("Téléphone")
            arr   = st.date_input("Arrivée", date.today())
            dep   = st.date_input("Départ",  date.today() + timedelta(days=1))
        with c2:
            plat  = st.selectbox("Plateforme", options=list(palette.keys()) or list(DEFAULT_PALETTE.keys()))
            brut  = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais_cb    = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage      = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes       = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye        = st.checkbox("Payé", value=False)

        submitted = st.form_submit_button("✅ Ajouter")
        if submitted:
            if not nom or dep <= arr:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nuitees = (dep - arr).days
                new = pd.DataFrame([{
                    "paye": paye,
                    "nom_client": nom, "email": email, "sms_envoye": False, "post_depart_envoye": False,
                    "plateforme": plat, "telephone": tel, "pays": "",
                    "date_arrivee": arr, "date_depart": dep, "nuitees": nuitees,
                    "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                    "prix_net": (brut - commissions - frais_cb),
                    "menage": menage, "taxes_sejour": taxes,
                    "base": (brut - commissions - frais_cb - menage - taxes),
                    "charges": (commissions + frais_cb),
                    "%":  0.0, "res_id": str(uuid.uuid4()), "ical_uid": ""
                }])
                df2 = ensure_schema(pd.concat([df, new], ignore_index=True))
                # recalc %
                brut_s = pd.to_numeric(df2["prix_brut"], errors="coerce").fillna(0)
                charges_s = pd.to_numeric(df2["charges"], errors="coerce").fillna(0)
                with np.errstate(divide="ignore", invalid="ignore"):
                    df2["%"] = np.where(brut_s > 0, (charges_s / brut_s * 100), 0.0)
                if sauvegarder_donnees(df2):
                    st.success(f"Réservation pour {nom} ajoutée.")
                    st.rerun()


# ---------- Modifier / Supprimer ----------
def vue_modifier(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = df.reset_index().sort_values(by="date_arrivee", ascending=False)
    options = [f"{i}: {r.get('nom_client','')} ({r.get('date_arrivee','')})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not sel:
        return

    idx = int(sel.split(":")[0])
    original_idx = df_sorted.loc[idx, "index"]
    row = df.loc[original_idx]

    with st.form(f"form_mod_{original_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get("nom_client", "") or "")
            email = st.text_input("Email", value=row.get("email", "") or "")
            tel = st.text_input("Téléphone", value=row.get("telephone", "") or "")
            arrivee = st.date_input("Arrivée", value=pd.to_datetime(row.get("date_arrivee")).date() if row.get("date_arrivee") else date.today())
            depart  = st.date_input("Départ",  value=pd.to_datetime(row.get("date_depart")).date()  if row.get("date_depart")  else date.today())
        with c2:
            palette_keys = list(palette.keys()) or list(DEFAULT_PALETTE.keys())
            plat_idx = palette_keys.index(row.get("plateforme")) if row.get("plateforme") in palette_keys else 0
            plat = st.selectbox("Plateforme", options=palette_keys, index=plat_idx)
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut = float(pd.to_numeric(row.get("prix_brut"), errors="coerce") or 0)
            commissions = float(pd.to_numeric(row.get("commissions"), errors="coerce") or 0)
            frais_cb = float(pd.to_numeric(row.get("frais_cb"), errors="coerce") or 0)
            menage   = float(pd.to_numeric(row.get("menage"), errors="coerce") or 0)
            taxes    = float(pd.to_numeric(row.get("taxes_sejour"), errors="coerce") or 0)
            brut        = st.number_input("Prix brut", min_value=0.0, step=0.01, value=brut)
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=commissions)
            frais_cb    = st.number_input("Frais CB", min_value=0.0, step=0.01, value=frais_cb)
            menage      = st.number_input("Ménage",   min_value=0.0, step=0.01, value=menage)
            taxes       = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=taxes)

        b1, b2 = st.columns([0.7, 0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            updates = {
                "nom_client": nom, "email": email, "telephone": tel,
                "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye,
                "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes,
            }
            for k, v in updates.items():
                df.loc[original_idx, k] = v

            # recalc champs dérivés
            df.loc[original_idx, "prix_net"] = (float(brut) - float(commissions) - float(frais_cb))
            df.loc[original_idx, "charges"]  = (float(commissions) + float(frais_cb))
            df.loc[original_idx, "base"]     = (float(df.loc[original_idx, "prix_net"]) - float(menage) - float(taxes))
            arr_dt = pd.to_datetime(arrivee)
            dep_dt = pd.to_datetime(depart)
            df.loc[original_idx, "nuitees"]  = max((dep_dt - arr_dt).days, 0)

            # pourcentage charges / brut
            brut_s = float(df.loc[original_idx, "prix_brut"] or 0)
            charges_s = float(df.loc[original_idx, "charges"] or 0)
            df.loc[original_idx, "%"] = (charges_s / brut_s * 100) if brut_s > 0 else 0.0

            if sauvegarder_donnees(df):
                st.success("Modifié ✅")
                st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé.")
                st.rerun()

# ============================== PART 4/5 — VUES: PLATEFORMES, CALENDRIER, RAPPORT, INDICATIFS PAYS ==============================

# ---------- Plateformes ----------
def vue_plateformes(df: pd.DataFrame, palette: dict):
    st.header("🎨 Plateformes — couleurs")
    print_buttons()
    if df is None:
        st.info("Aucune donnée.")
        return

    plats = sorted(df["plateforme"].astype(str).dropna().unique().tolist())
    if not plats:
        st.info("Aucune plateforme détectée.")
        return

    st.write("Modifier la couleur associée à chaque plateforme :")
    new_palette = {}
    for p in plats:
        col = st.color_picker(f"{p}", value=palette.get(p, "#666666"))
        new_palette[p] = col

    if st.button("💾 Enregistrer palette"):
        pd.DataFrame(list(new_palette.items()), columns=["plateforme", "couleur"]).to_csv(
            CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8"
        )
        st.success("Palette enregistrée ✅")
        st.cache_data.clear()
        st.rerun()


# ---------- Calendrier ----------
def vue_calendrier(df: pd.DataFrame, palette: dict):
    st.header("📅 Calendrier mensuel")
    print_buttons()
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfc = df.copy()
    dfc["date_arrivee"] = pd.to_datetime(dfc["date_arrivee"], errors="coerce")
    dfc["date_depart"]  = pd.to_datetime(dfc["date_depart"], errors="coerce")

    years  = sorted(dfc["date_arrivee"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months = list(range(1, 12 + 1))
    c1, c2 = st.columns(2)
    year  = c1.selectbox("Année", years, index=0)
    month = c2.selectbox("Mois", months, index=date.today().month - 1)

    start = date(year, month, 1)
    next_month = date(year + (month == 12), (month % 12) + 1, 1)
    end = next_month - timedelta(days=1)

    filt = (dfc["date_arrivee"].dt.date <= end) & (dfc["date_depart"].dt.date >= start)
    sub = dfc[filt]

    days = (end - start).days + 1
    html = "<table border='1' style='border-collapse:collapse;width:100%;font-size:12px;text-align:center;'>"
    html += "<tr>" + "".join(f"<th>{(start+timedelta(days=i)).day}</th>" for i in range(days)) + "</tr>"

    for _, r in sub.iterrows():
        arr, dep = r["date_arrivee"].date(), r["date_depart"].date()
        color = palette.get(r.get("plateforme", ""), "#ddd")
        row = []
        for i in range(days):
            d = start + timedelta(days=i)
            if arr <= d < dep:
                row.append(f"<td style='background:{color}' title='{r['nom_client']}'></td>")
            else:
                row.append("<td></td>")
        html += "<tr>" + "".join(row) + "</tr>"

    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)


# ---------- Rapport ----------
def vue_rapport(df: pd.DataFrame, palette: dict):
    st.header("📊 Rapport")
    print_buttons()
    if df is None or df.empty:
        st.info("Aucune donnée.")
        return

    dfr = df.copy()
    dfr["date_arrivee"] = pd.to_datetime(dfr["date_arrivee"], errors="coerce")
    dfr["year"] = dfr["date_arrivee"].dt.year

    years = sorted(dfr["year"].dropna().astype(int).unique().tolist(), reverse=True)
    year = st.selectbox("Année", ["Toutes"] + years, index=0)

    if year != "Toutes":
        dfr = dfr[dfr["year"] == int(year)]

    agg = dfr.groupby("plateforme").agg({
        "prix_brut": "sum", "prix_net": "sum", "nuitees": "sum", "commissions": "sum"
    }).reset_index()

    st.dataframe(agg, use_container_width=True)

    fig, ax = plt.subplots()
    ax.bar(agg["plateforme"], agg["prix_net"], color=[palette.get(p, "#666") for p in agg["plateforme"]])
    ax.set_ylabel("Revenus nets (€)")
    ax.set_title(f"Revenus par plateforme ({year})")
    st.pyplot(fig)


# ---------- Indicateurs pays ----------
def vue_indicatifs(df: pd.DataFrame, palette: dict):
    st.header("🌍 Indicateurs pays")
    print_buttons()

    if not os.path.exists("indicatifs_pays.csv"):
        st.error("Fichier indicatifs_pays.csv introuvable.")
        return

    data = pd.read_csv("indicatifs_pays.csv", dtype=str)

    st.dataframe(data, use_container_width=True)

    if st.button("🔄 Recharger depuis le disque"):
        st.cache_data.clear()
        st.success("Fichier rechargé ✅")
        st.rerun()

# ============================== PART 5/5 — SMS, PARAMÈTRES, MAIN ==============================

# ---------- SMS ----------
def vue_sms(df: pd.DataFrame, palette: dict):
    """Page SMS — messages avant arrivée et après départ (copier/coller)."""
    from urllib.parse import quote

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation disponible.")
        return

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    # --- Pré-arrivée ---
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = dfv.dropna(subset=["telephone","nom_client","date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (~_to_bool_series(pre.get("sms_envoye")))]

    if pre.empty:
        st.info("Aucun client à contacter pour la date sélectionnée.")
    else:
        for _, r in pre.iterrows():
            arr_txt = r["date_arrivee"].strftime("%d/%m/%Y") if pd.notna(r["date_arrivee"]) else ""
            dep_txt = r["date_depart"].strftime("%d/%m/%Y") if pd.notna(r["date_depart"]) else ""
            nuitees = r.get("nuitees", "")

            msg = (
                f"{apt_name.upper()}\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuitees}\n\n"
                f"Bonjour {r.get('nom_client','')},\n\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre réception, "
                "merci de remplir la fiche suivante :\n"
                "https://urlr.me/kZuH94\n\n"
                "Un parking est disponible sur place.\n"
                "Check-in à partir de 14:00, check-out avant 11:00.\n"
                "Consignes à bagages disponibles en ville.\n\n"
                "Annick & Charley\n\n"
                "******\n\n"
                "Welcome!\n\n"
                "We are delighted to welcome you soon to Nice. Please complete this form:\n"
                "https://urlr.me/kZuH94\n\n"
                "Parking is available on site.\n"
                "Check-in from 2:00 p.m., check-out before 11:00 a.m.\n"
                "Luggage storage facilities available across Nice.\n\n"
                "Annick & Charley"
            )

            st.text_area(f"Pré-arrivée — {r['nom_client']}", value=msg, height=350)

    # --- Post-départ ---
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = dfv.dropna(subset=["telephone","nom_client","date_depart"]).copy()
    post = post[(post["date_depart"] == target_depart) & (~_to_bool_series(post.get("post_depart_envoye")))]

    if post.empty:
        st.info("Aucun message post-départ à envoyer aujourd’hui.")
    else:
        for _, r in post.iterrows():
            name = str(r.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Merci d’avoir choisi notre appartement.\n"
                "Nous espérons que vous avez passé un agréable séjour.\n"
                "Notre porte vous sera toujours ouverte si vous souhaitez revenir.\n\n"
                "Annick & Charley\n\n"
                "******\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment.\n"
                "We hope you had a great time — our door is always open if you want to come back.\n\n"
                "Annick & Charley"
            )
            st.text_area(f"Post-départ — {name}", value=msg2, height=280)


# ---------- Paramètres ----------
def vue_settings(df: pd.DataFrame, palette: dict):
    st.header("⚙️ Paramètres")
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.subheader(apt_name)
    print_buttons()

    st.markdown("### Sauvegarde des données")
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee", "date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        csv_bytes = out.to_csv(sep=";", index=False).encode("utf-8")
    except Exception:
        csv_bytes = b""

    st.download_button("⬇️ Export CSV", data=csv_bytes, file_name="reservations.csv", mime="text/csv")

    # Restauration
    st.markdown("### Restauration")
    up = st.file_uploader("Importer (CSV)", type=["csv"], key="restore_file")
    if up is not None:
        try:
            tmp = pd.read_csv(up, sep=";", dtype=str)
            tmp = ensure_schema(tmp)
            tmp.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8")
            st.success("Fichier restauré ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if st.button("🧹 Vider le cache"):
        st.cache_data.clear()
        st.rerun()


# ---------- Main ----------
def main():
    # Reset via ?clear=1
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1", "true"):
        st.cache_data.clear()

    _select_apartment_sidebar()

    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    df, palette_loaded = _load_data_for_active_apartment()
    palette = palette_loaded or DEFAULT_PALETTE

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "🌍 Indicateurs pays": vue_indicatifs,
        "✉️ SMS": vue_sms,
        "⚙️ Paramètres": vue_settings,
    }

    choice = st.sidebar.radio("Aller à", list(pages.keys()), key="nav_radio")
    if choice in pages:
        pages[choice](df, palette)
    else:
        st.error("Page inconnue")


if __name__ == "__main__":
    main()