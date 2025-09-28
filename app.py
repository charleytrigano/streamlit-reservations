# ============================== PART 1/5 : IMPORTS, CONFIG, STYLES, HELPERS ==============================
import os, io, re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange
from urllib.parse import quote as urlquote

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

# matplotlib optionnel pour certains graphiques
try:
    import matplotlib.pyplot as plt
except Exception:
    plt = None

# ---------------- CONFIG APP ----------------
st.set_page_config(
    page_title="Villa Tobias — Gestion des Réservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------- CONSTANTES ----------------
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"
APARTMENTS_CSV   = "apartments.csv"
INDICATIFS_CSV   = "indicatifs_pays.csv"   # nom demandé

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

# ---------------- STYLE ----------------
def apply_style(light: bool):
    bg = "#fafafa" if light else "#0f1115"
    fg = "#0f172a" if light else "#eaeef6"
    side = "#f2f2f2" if light else "#171923"
    border = "rgba(17,24,39,.08)" if light else "rgba(124,92,255,.16)"
    st.markdown(
        f"""
        <style>
          html, body, [data-testid="stAppViewContainer"] {{ background:{bg}; color:{fg}; }}
          [data-testid="stSidebar"] {{ background:{side}; border-right:1px solid {border}; }}
          .glass {{ background:{"rgba(255,255,255,.65)" if light else "rgba(255,255,255,.06)"}; 
                   border:1px solid {border}; border-radius:12px; padding:12px; margin:10px 0; }}
          .chip {{ display:inline-block; padding:6px 10px; border-radius:12px; margin:4px 6px; 
                   font-size:.86rem; background:{"#eee" if light else "#2a2f3a"}; color:{"#222" if light else "#eee"} }}
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; }}
          .cal-cell {{ border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px; position:relative; overflow:hidden; background:{"#fff" if light else "#0b0d12"}; }}
          .cal-cell.outside {{ opacity:.45; }}
          .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
          .resa-pill {{ padding:4px 6px; border-radius:6px; font-size:.84rem; margin-top:22px; color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
          .cal-header {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; font-weight:700; opacity:.8; margin:6px 0 8px; }}

          @media print {{
            @page {{ size: A4 landscape; margin: 10mm; }}
            body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
            .print-hide {{ display:none !important; }}
            .print-only {{ display:block !important; }}
          }}
          .print-only {{ display:none; }}
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

# ---------------- HELPERS DATA ----------------
BASE_COLS = [
    "paye","nom_client","email","sms_envoye","post_depart_envoye",
    "plateforme","telephone","pays",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%",
    "res_id","ical_uid"
]

def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f: 
            return f.read()
    except Exception: 
        return None

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    if not raw: 
        return pd.DataFrame()
    txt = raw.decode("utf-8", errors="ignore").replace("\ufeff","")
    for sep in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(io.StringIO(txt), sep=sep, dtype=str)
            if df.shape[1] >= 2: 
                return df
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



# ============================== PART 2/5 : DONNÉES, APARTMENTS, INDICATIFS ==============================

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Ajoute les colonnes manquantes pour cohérence du schéma."""
    if df is None:
        df = pd.DataFrame(columns=BASE_COLS)
    else:
        for c in BASE_COLS:
            if c not in df.columns:
                df[c] = ""
        df = df[BASE_COLS]
    return df


def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    """Sauvegarde les réservations actives sur disque."""
    try:
        target_csv = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
        df2 = ensure_schema(df)
        df2.to_csv(target_csv, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        return True
    except Exception as e:
        st.error(f"Erreur sauvegarde: {e}")
        return False


# ---------------- APARTMENTS ----------------
@st.cache_data
def _load_apartments() -> pd.DataFrame:
    if not os.path.exists(APARTMENTS_CSV):
        base = pd.DataFrame([{"slug": "villa-tobias", "name": "Villa Tobias"}])
        base.to_csv(APARTMENTS_CSV, index=False, encoding="utf-8")
    return pd.read_csv(APARTMENTS_CSV, dtype=str).fillna("")


def _current_apartment():
    apts = _load_apartments()
    if "apt_slug" not in st.session_state:
        st.session_state["apt_slug"] = apts.iloc[0]["slug"]
    slug = st.session_state["apt_slug"]
    row = apts[apts["slug"] == slug]
    return row.iloc[0].to_dict() if not row.empty else None


def _select_apartment_sidebar() -> bool:
    """Sélecteur d'appartement dans le sidebar. Retourne True si changé."""
    apts = _load_apartments()
    slugs = apts["slug"].tolist()
    names = apts["name"].tolist()
    slug_to_name = dict(zip(slugs, names))
    current = st.session_state.get("apt_slug", slugs[0])
    choice = st.sidebar.selectbox("### Appartement\nChoisir un appartement",
                                  slugs, format_func=lambda x: slug_to_name.get(x, x),
                                  index=slugs.index(current) if current in slugs else 0,
                                  key="apt_selector")
    if choice != current:
        st.session_state["apt_slug"] = choice
        return True
    return False


# ---------------- INDICATIFS PAYS ----------------
def _load_indicatifs_df() -> pd.DataFrame:
    """Charge le CSV d’indicatifs (créé si absent)."""
    if not os.path.exists(INDICATIFS_CSV):
        base = pd.DataFrame([
            {"code": "FR", "country": "France", "dial": "+33", "flag": "🇫🇷"},
            {"code": "GB", "country": "United Kingdom", "dial": "+44", "flag": "🇬🇧"},
            {"code": "ES", "country": "Spain", "dial": "+34", "flag": "🇪🇸"},
        ])
        base.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8")
    try:
        return pd.read_csv(INDICATIFS_CSV, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=["code", "country", "dial", "flag"])


def _save_indicatifs_df(df_in: pd.DataFrame) -> bool:
    """Valide et sauvegarde le CSV indicatifs."""
    try:
        df = df_in.copy()
        df = df[["code", "country", "dial", "flag"]]
        df["code"] = df["code"].astype(str).str.upper().str.strip()
        df["dial"] = df["dial"].astype(str).str.strip()
        df["flag"] = df["flag"].astype(str).str.strip()
        df["country"] = df["country"].astype(str).str.strip()

        # normalisation indicatif
        df.loc[~df["dial"].str.startswith("+"), "dial"] = "+" + df["dial"].str.lstrip("+").str.strip()

        df = df[df["code"] != ""].drop_duplicates(subset=["code"])
        df.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8")
        return True
    except Exception as e:
        st.error(f"Erreur sauvegarde indicatifs: {e}")
        return False


def _phone_country(phone: str) -> str:
    """Retourne le pays selon indicatif du numéro."""
    if not phone: 
        return "Inconnu"
    s = re.sub(r"\D", "", str(phone))
    if not s:
        return "Inconnu"
    if not s.startswith("+" ):
        s = "+" + s
    indicatifs = _load_indicatifs_df()
    for _, row in indicatifs.iterrows():
        dial = str(row["dial"]).strip()
        if s.startswith(dial.replace(" ", "")):
            return f"{row['flag']} {row['country']}"
    return "Inconnu"


# ============================== PART 3/5 : ACCUEIL, RÉSERVATIONS, AJOUT, MODIF, PLATEFORMES, CALENDRIER ==============================

def vue_accueil(df: pd.DataFrame, palette: dict):
    """Tableau de bord du jour : arrivées / départs aujourd'hui et arrivées demain."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfx = ensure_schema(df).copy()
    dfx["date_arrivee"] = _to_date(dfx["date_arrivee"])
    dfx["date_depart"] = _to_date(dfx["date_depart"])

    today = date.today()
    tomorrow = today + timedelta(days=1)

    arr = dfx[dfx["date_arrivee"] == today][["nom_client", "telephone", "plateforme"]]
    dep = dfx[dfx["date_depart"] == today][["nom_client", "telephone", "plateforme"]]
    arr_t1 = dfx[dfx["date_arrivee"] == tomorrow][["nom_client", "telephone", "plateforme"]]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame({"info": ["Aucune arrivée."]}), use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame({"info": ["Aucun départ."]}), use_container_width=True)
    with c3:
        st.subheader("🟠 Arrivées demain")
        st.dataframe(arr_t1 if not arr_t1.empty else pd.DataFrame({"info": ["Aucune arrivée demain."]}), use_container_width=True)


def vue_reservations(df: pd.DataFrame, palette: dict):
    """Liste + filtres + KPIs (brut/net/charges/base/nuitées/ADR)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfx = ensure_schema(df).copy()
    dfx["date_arrivee_dt"] = pd.to_datetime(_to_date(dfx["date_arrivee"]), errors="coerce")
    dfx["date_depart_dt"] = pd.to_datetime(_to_date(dfx["date_depart"]), errors="coerce")

    years = sorted(dfx["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    plats = sorted(dfx["plateforme"].astype(str).fillna("").replace({"nan": ""}).unique().tolist())
    c1, c2, c3, c4 = st.columns(4)
    year = c1.selectbox("Année", ["Toutes"] + years, index=0)
    month = c2.selectbox("Mois", ["Tous"] + list(range(1, 12 + 1)), index=0)
    plat = c3.selectbox("Plateforme", ["Toutes"] + plats, index=0)
    pay = c4.selectbox("Paiement", ["Tous", "Payé", "Non payé"], index=0)

    data = dfx.copy()
    if year != "Toutes":
        data = data[data["date_arrivee_dt"].dt.year == int(year)]
    if month != "Tous":
        data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"].astype(str) == plat]
    if pay == "Payé":
        data = data[_to_bool_series(data["paye"]) == True]
    elif pay == "Non payé":
        data = data[_to_bool_series(data["paye"]) == False]

    # KPIs
    brut = pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum()
    net = pd.to_numeric(data["prix_net"], errors="coerce").fillna(0).sum()
    charges = pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum()
    base = pd.to_numeric(data["base"], errors="coerce").fillna(0).sum()
    nuits = pd.to_numeric(data["nuitees"], errors="coerce").fillna(0).sum()
    adr = (net / nuits) if nuits > 0 else 0

    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
          <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
          <span class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></span>
          <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
          <span class='chip'><small>Nuitées</small><br><strong>{int(nuits)}</strong></span>
          <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
        </div>
        """.replace(",", " "),
        unsafe_allow_html=True,
    )

    # Tri anti-casse
    data = data.sort_values(["date_arrivee_dt", "nom_client"], ascending=[False, True])
    to_show = data.drop(columns=["date_arrivee_dt", "date_depart_dt"], errors="ignore")
    st.dataframe(to_show, use_container_width=True)


def vue_ajouter(df: pd.DataFrame, palette: dict):
    """Ajout d'une réservation."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter — {apt_name}")
    print_buttons()

    with st.form("form_add", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel = st.text_input("Téléphone")
            arr = st.date_input("Arrivée", date.today())
            dep = st.date_input("Départ", date.today() + timedelta(days=1))
        with c2:
            plat = st.selectbox("Plateforme", list(palette.keys()))
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye = st.checkbox("Payé", value=False)

        submitted = st.form_submit_button("✅ Ajouter")
        if submitted:
            if (not nom) or (dep <= arr):
                st.error("Veuillez saisir un nom et des dates valides.")
            else:
                nuitees = (dep - arr).days
                new = pd.DataFrame(
                    [
                        {
                            "paye": bool(paye),
                            "nom_client": nom,
                            "email": email,
                            "sms_envoye": False,
                            "post_depart_envoye": False,
                            "plateforme": plat,
                            "telephone": tel,
                            "pays": "",
                            "date_arrivee": arr,
                            "date_depart": dep,
                            "nuitees": nuitees,
                            "prix_brut": brut,
                            "commissions": commissions,
                            "frais_cb": frais_cb,
                            "prix_net": max(0.0, brut - commissions - frais_cb),
                            "menage": menage,
                            "taxes_sejour": taxes,
                            "base": max(0.0, (brut - commissions - frais_cb) - menage - taxes),
                            "charges": (brut - max(0.0, brut - commissions - frais_cb)),
                            "%": 0,
                            "res_id": str(uuid.uuid4()),
                            "ical_uid": "",
                        }
                    ]
                )
                df2 = pd.concat([ensure_schema(df), new], ignore_index=True)
                # recalcul pourcentage
                with np.errstate(divide="ignore", invalid="ignore"):
                    df2["%"] = np.where(
                        pd.to_numeric(df2["prix_brut"], errors="coerce").fillna(0) > 0,
                        (pd.to_numeric(df2["charges"], errors="coerce").fillna(0)
                         / pd.to_numeric(df2["prix_brut"], errors="coerce").fillna(0))
                        * 100,
                        0.0,
                    )
                if sauvegarder_donnees(df2):
                    st.success("Réservation ajoutée ✅")
                    st.rerun()


def vue_modifier(df: pd.DataFrame, palette: dict):
    """Modification / suppression d’une réservation."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()

    dfx = ensure_schema(df).copy()
    if dfx.empty:
        st.info("Aucune réservation.")
        return

    dfx = dfx.reset_index().rename(columns={"index": "__idx"})
    options = [f"{i}: {r['nom_client']} ({r['date_arrivee']})" for i, r in dfx.iterrows()]
    pick = st.selectbox("Sélectionnez une réservation", options=options, index=None)
    if not pick:
        return

    i = int(pick.split(":")[0])
    row = dfx.loc[i]
    real_idx = row["__idx"]

    with st.form(f"form_edit_{real_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=row.get("nom_client", ""))
            email = st.text_input("Email", value=row.get("email", ""))
            tel = st.text_input("Téléphone", value=row.get("telephone", ""))
            arrivee = st.date_input("Arrivée", value=_to_date(pd.Series([row.get("date_arrivee")]))[0])
            depart = st.date_input("Départ", value=_to_date(pd.Series([row.get("date_depart")]))[0])
        with c2:
            plats = list(palette.keys())
            idx = plats.index(row.get("plateforme")) if row.get("plateforme") in plats else 0
            plat = st.selectbox("Plateforme", plats, index=idx)
            paye = st.checkbox("Payé", value=bool(row.get("paye")))
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=0.01, value=float(pd.to_numeric(row.get("prix_brut"), errors="coerce") or 0))
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01, value=float(pd.to_numeric(row.get("commissions"), errors="coerce") or 0))
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01, value=float(pd.to_numeric(row.get("frais_cb"), errors="coerce") or 0))
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01, value=float(pd.to_numeric(row.get("menage"), errors="coerce") or 0))
            taxes = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01, value=float(pd.to_numeric(row.get("taxes_sejour"), errors="coerce") or 0))

        b1, b2 = st.columns([0.7, 0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            df_edit = ensure_schema(df).copy()
            df_edit.loc[real_idx, "nom_client"] = nom
            df_edit.loc[real_idx, "email"] = email
            df_edit.loc[real_idx, "telephone"] = tel
            df_edit.loc[real_idx, "date_arrivee"] = arrivee
            df_edit.loc[real_idx, "date_depart"] = depart
            df_edit.loc[real_idx, "nuitees"] = max(0, (depart - arrivee).days)
            df_edit.loc[real_idx, "plateforme"] = plat
            df_edit.loc[real_idx, "paye"] = bool(paye)
            df_edit.loc[real_idx, "prix_brut"] = float(brut)
            df_edit.loc[real_idx, "commissions"] = float(commissions)
            df_edit.loc[real_idx, "frais_cb"] = float(frais_cb)
            df_edit.loc[real_idx, "menage"] = float(menage)
            df_edit.loc[real_idx, "taxes_sejour"] = float(taxes)
            # recalculs
            net = float(brut) - float(commissions) - float(frais_cb)
            base = net - float(menage) - float(taxes)
            charges = float(brut) - net
            df_edit.loc[real_idx, "prix_net"] = max(0.0, net)
            df_edit.loc[real_idx, "base"] = max(0.0, base)
            df_edit.loc[real_idx, "charges"] = max(0.0, charges)
            with np.errstate(divide="ignore", invalid="ignore"):
                df_edit.loc[real_idx, "%"] = (charges / brut * 100) if brut > 0 else 0.0
            if sauvegarder_donnees(df_edit):
                st.success("Modifié ✅")
                st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            df_del = ensure_schema(df).copy().drop(index=real_idx)
            if sauvegarder_donnees(df_del):
                st.warning("Supprimé.")
                st.rerun()


def vue_plateformes(df: pd.DataFrame, palette: dict):
    """Edition de la palette Plateforme → Couleur."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes — {apt_name}")
    print_buttons()

    # Base d'édition : toutes les plateformes rencontrées + palette existante
    plats_from_df = sorted(set(ensure_schema(df)["plateforme"].astype(str).replace({"nan": ""}).tolist()))
    all_plats = sorted(set(list(palette.keys()) + plats_from_df))
    base = pd.DataFrame({"plateforme": all_plats, "couleur": [palette.get(p, "#666666") for p in all_plats]})

    # ColorColumn si dispo
    HAS_COLORCOL = hasattr(getattr(st, "column_config", object), "ColorColumn")
    if HAS_COLORCOL:
        cfg = {"plateforme": st.column_config.TextColumn("Plateforme"), "couleur": st.column_config.ColorColumn("Couleur")}
    else:
        cfg = {"plateforme": st.column_config.TextColumn("Plateforme"), "couleur": st.column_config.TextColumn("Couleur (hex)")}

    edited = st.data_editor(base, num_rows="dynamic", use_container_width=True, hide_index=True, column_config=cfg, key="palette_editor")

    c1, c2, c3 = st.columns([0.5, 0.3, 0.2])
    if c1.button("💾 Enregistrer la palette", key="save_palette_btn"):
        try:
            to_save = edited.copy()
            to_save["plateforme"] = to_save["plateforme"].astype(str).str.strip()
            to_save["couleur"] = to_save["couleur"].astype(str).str.strip()
            to_save = to_save[to_save["plateforme"] != ""].drop_duplicates(subset=["plateforme"])
            # valid hex si pas ColorColumn
            if not HAS_COLORCOL:
                ok = to_save["couleur"].str.match(r"^#([0-9A-Fa-f]{6})$")
                to_save.loc[~ok, "couleur"] = "#666666"
            target = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
            to_save.to_csv(target, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("↩️ Palette par défaut", key="restore_palette_btn"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme", "couleur"]).to_csv(
                st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES),
                sep=";",
                index=False,
                encoding="utf-8",
                lineterminator="\n",
            )
            st.success("Palette restaurée.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c3.button("🔄 Recharger", key="reload_palette_btn"):
        st.cache_data.clear()
        st.rerun()


def vue_calendrier(df: pd.DataFrame, palette: dict):
    """Calendrier mensuel compact (pills par jour)."""
    from html import escape

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier — {apt_name}")
    print_buttons()

    dfx = ensure_schema(df).dropna(subset=["date_arrivee", "date_depart"]).copy()
    if dfx.empty:
        st.info("Aucune réservation à afficher.")
        return

    dfx["date_arrivee"] = _to_date(dfx["date_arrivee"])
    dfx["date_depart"] = _to_date(dfx["date_depart"])

    years = sorted(pd.to_datetime(dfx["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [date.today().year], index=0)
    mois = st.selectbox("Mois", options=list(range(1, 13)), index=(date.today().month - 1))

    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True,
    )

    def day_resas(d: date) -> pd.DataFrame:
        m = (dfx["date_arrivee"] <= d) & (dfx["date_depart"] > d)
        return dfx[m]

    cal = Calendar(firstweekday=0)  # lundi
    html_parts = ["<div class='cal-grid'>"]
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
                        color = palette.get(str(r.get("plateforme") or ""), "#888")
                        name = str(r.get("nom_client") or "")[:22]
                        title_txt = escape(str(r.get("nom_client", "")), quote=True)
                        cell += (
                            "<div class='resa-pill' "
                            f"style='background:{color}' "
                            f"title='{title_txt}'>"
                            f"{name}</div>"
                        )
            cell += "</div>"
            html_parts.append(cell)
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Détail du mois sélectionné")
    debut = date(annee, mois, 1)
    fin = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfx[(dfx["date_arrivee"] <= fin) & (dfx["date_depart"] > debut)].copy()
    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
    else:
        st.dataframe(
            rows[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "paye"]],
            use_container_width=True,
        )


# ============================== PART 4/5 : RAPPORT, GOOGLE SHEET, CLIENTS, ID ==============================

def vue_rapport(df: pd.DataFrame, palette: dict):
    """Tableaux de bord et KPIs par plateforme et par pays."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📊 Rapport — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune donnée disponible.")
        return

    dfr = ensure_schema(df).copy()
    dfr["date_arrivee"] = _to_date(dfr["date_arrivee"])
    dfr["date_depart"] = _to_date(dfr["date_depart"])
    dfr["nuitees"] = pd.to_numeric(dfr["nuitees"], errors="coerce").fillna(0).astype(int)
    dfr["revenu"] = pd.to_numeric(dfr["prix_net"], errors="coerce").fillna(0)

    # ---- KPIs principaux ----
    total_resa = len(dfr)
    total_nuitees = dfr["nuitees"].sum()
    total_revenu = dfr["revenu"].sum()

    c1, c2, c3 = st.columns(3)
    c1.metric("Réservations", f"{total_resa}")
    c2.metric("Nuitées", f"{total_nuitees}")
    c3.metric("Revenu total", f"{total_revenu:,.0f} €".replace(",", " "))

    st.markdown("---")

    # ---- Agrégation par plateforme ----
    agg = (
        dfr.groupby("plateforme")
        .agg(
            reservations=("plateforme", "count"),
            nuitees=("nuitees", "sum"),
            revenu_total=("revenu", "sum"),
        )
        .reset_index()
    )
    agg["part_revenu_%"] = (agg["revenu_total"] / total_revenu * 100).round(1) if total_revenu > 0 else 0

    st.subheader("Par plateforme")
    st.dataframe(agg, use_container_width=True)

    # ---- Graphique par plateforme ----
    if not agg.empty:
        fig, ax = plt.subplots()
        ax.pie(
            agg["revenu_total"],
            labels=agg["plateforme"],
            autopct="%1.1f%%",
            colors=[palette.get(p, "#999999") for p in agg["plateforme"]],
        )
        ax.set_title("Répartition du revenu par plateforme")
        st.pyplot(fig)

    st.markdown("---")

    # ---- Agrégation par pays ----
    dfr["pays"] = dfr["telephone"].apply(_phone_country)
    agg_pays = (
        dfr.groupby("pays")
        .agg(
            reservations=("pays", "count"),
            nuitees=("nuitees", "sum"),
            revenu_total=("revenu", "sum"),
        )
        .reset_index()
    )
    agg_pays = agg_pays.sort_values("revenu_total", ascending=False).head(20)
    agg_pays["part_revenu_%"] = (agg_pays["revenu_total"] / total_revenu * 100).round(1) if total_revenu > 0 else 0

    st.subheader("Top 20 pays")
    st.dataframe(agg_pays, use_container_width=True)

    if not agg_pays.empty:
        fig2, ax2 = plt.subplots()
        ax2.barh(agg_pays["pays"], agg_pays["revenu_total"], color="skyblue")
        ax2.set_xlabel("Revenu (€)")
        ax2.set_ylabel("Pays")
        st.pyplot(fig2)


# ---------------- GOOGLE SHEET ----------------
def vue_google_sheet(df: pd.DataFrame, palette: dict):
    """Export Google Sheets (simulation pour l’instant)."""
    st.header("📝 Google Sheet")
    st.caption("Export automatique vers Google Sheets (à venir).")

    if df is None or df.empty:
        st.info("Aucune donnée à exporter.")
        return

    if st.button("📤 Exporter vers Google Sheets (simulé)", key="btn_export_gs"):
        st.success("Simulation d’export effectuée ✅")


# ---------------- CLIENTS ----------------
def vue_clients(df: pd.DataFrame, palette: dict):
    """Liste simple des clients avec téléphone et pays."""
    st.header("👥 Clients")
    if df is None or df.empty:
        st.info("Aucun client.")
        return

    dfx = ensure_schema(df).copy()
    dfx["pays"] = dfx["telephone"].apply(_phone_country)

    st.dataframe(dfx[["nom_client", "telephone", "pays"]], use_container_width=True)

    if st.button("🔄 Recalculer les pays", key="btn_recalc_pays"):
        dfx["pays"] = dfx["telephone"].apply(_phone_country)
        if sauvegarder_donnees(dfx):
            st.success("Pays recalculés ✅")
            st.rerun()


# ---------------- ID ----------------
def vue_id(df: pd.DataFrame, palette: dict):
    """Affiche les numéros de réservation et ID uniques."""
    st.header("🆔 Identifiants")
    if df is None or df.empty:
        st.info("Aucun enregistrement.")
        return

    st.dataframe(df[["res_id", "numero_reservation", "plateforme"]], use_container_width=True)



# ============================== PART 5/5 : SMS, INDICATEURS PAYS, PARAMÈTRES, MAIN ==============================

from urllib.parse import quote


# ---------------- SMS ----------------
def vue_sms(df: pd.DataFrame, palette: dict):
    """SMS pré-arrivée (J+1) et post-départ — copier/coller + liens SMS/WhatsApp."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation disponible.")
        return

    dfx = ensure_schema(df).copy()
    dfx["date_arrivee"] = _to_date(dfx["date_arrivee"])
    dfx["date_depart"] = _to_date(dfx["date_depart"])

    # -------- Pré-arrivée --------
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = dfx.dropna(subset=["telephone", "nom_client", "date_arrivee"]).copy()
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (~_to_bool_series(pre["sms_envoye"]))]

    if pre.empty:
        st.info("Aucun client à contacter pour la date sélectionnée.")
    else:
        pre = pre.sort_values("date_arrivee").reset_index()
        options = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=options, index=None, key="pre_pick")
        if pick:
            i = int(pick.split(":")[0])
            r = pre.loc[i]
            nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
            arr_txt = r["date_arrivee"].strftime("%d/%m/%Y") if pd.notna(r["date_arrivee"]) else ""
            dep_txt = r["date_depart"].strftime("%d/%m/%Y") if pd.notna(r["date_depart"]) else ""

            msg = (
                f"{apt_name.upper()}\n"
                f"Plateforme : {r.get('plateforme','N/A')}\n"
                f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuitees}\n\n"
                f"Bonjour {r.get('nom_client','')},\n"
                "Bienvenue chez nous ! Merci de remplir la fiche d’arrivée :\n"
                f"{FORM_SHORT_URL}\n\n"
                "Parking disponible sur place.\nCheck-in dès 14h, check-out avant 11h.\n"
                "Nous serons sur place pour vous remettre les clés.\n\n"
                "Bon voyage !\nAnnick & Charley"
            )

            st.text_area("📋 Copier le message", value=msg, height=260, key="pre_msg")
            e164 = _format_phone_e164(r.get("telephone", ""))
            only_digits = "".join(ch for ch in e164 if ch.isdigit())
            enc = quote(msg)

            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}", key="pre_sms_ios")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}", key="pre_sms_android")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits}?text={enc}", key="pre_wa")

            if st.button("✅ Marquer 'SMS envoyé'", key="pre_mark_sent"):
                try:
                    df.loc[r["index"], "sms_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")

    st.markdown("---")

    # -------- Post-départ --------
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = dfx.dropna(subset=["telephone", "nom_client", "date_depart"]).copy()
    post = post[(post["date_depart"] == target_depart) & (~_to_bool_series(post["post_depart_envoye"]))]

    if post.empty:
        st.info("Aucun message post-départ aujourd'hui.")
    else:
        post = post.sort_values("date_depart").reset_index()
        options2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=options2, index=None, key="post_pick")
        if pick2:
            j = int(pick2.split(":")[0])
            r2 = post.loc[j]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\nMerci d'avoir choisi notre appartement. "
                "Nous espérons que vous avez passé un agréable séjour.\n"
                "Au plaisir de vous accueillir à nouveau !\n\n"
                f"Hello {name},\nThank you for choosing us. "
                "We hope you enjoyed your stay. You're always welcome back!\n\n"
                "Annick & Charley"
            )

            st.text_area("📋 Copier le message", value=msg2, height=240, key="post_msg")
            e164b = _format_phone_e164(r2.get("telephone", ""))
            only_digits_b = "".join(ch for ch in e164b if ch.isdigit())
            enc2 = quote(msg2)

            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits_b}?text={enc2}", key="post_wa")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}", key="post_sms_ios")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}", key="post_sms_android")

            if st.button("✅ Marquer 'post-départ envoyé'", key="post_mark_sent"):
                try:
                    df.loc[r2["index"], "post_depart_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erreur : {e}")


# ---------------- INDICATEURS PAYS ----------------

def vue_indicatifs(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🌍 Indicateurs pays — {apt_name}")
    st.caption("Ajoutez/éditez les pays, indicatifs et drapeaux.")

    base = _load_indicatifs_df()
    st.dataframe(base, use_container_width=True)

    edited = st.data_editor(
        base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        key="indicatifs_editor",
    )

    c1, c2 = st.columns([0.5, 0.5])
    if c1.button("💾 Enregistrer", key="btn_save_indicatifs"):
        if _save_indicatifs_df(edited):
            st.success("Indicatifs sauvegardés ✅")

    if c2.button("🔄 Recharger depuis le disque", key="btn_reload_indicatifs"):
        st.cache_data.clear()
        st.rerun()


# ---------------- PARAMÈTRES ----------------

def vue_settings(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header("⚙️ Paramètres")
    st.subheader(apt_name)
    print_buttons()

    st.markdown("### 🧰 Sélecteur d'appartement")
    default_csv = "slug,name\nvilla-tobias,Villa Tobias\nle-turenne,Le Turenne\n"
    txt = st.text_area("Contenu apartments.csv", value=default_csv, height=120, key="force_apts_txt")
    if st.button("🧰 Écraser apartments.csv", key="btn_force_apts"):
        try:
            with open(APARTMENTS_CSV, "w", encoding="utf-8") as f:
                f.write(txt.strip() + "\n")
            st.cache_data.clear()
            st.success("apartments.csv écrasé ✅ — rechargement…")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur écriture : {e}")


# ------------------------------- MAIN ---------------------------------

def main():
    # Clear cache via ?clear=1
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1", "true", "True", "yes"):
        st.cache_data.clear()

    # Sélecteur d’appartement
    _select_apartment_sidebar()

    # Mode sombre / clair
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    # En-tête
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    # Données
    df, palette_loaded = _load_data_for_active_apartment()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    # Pages
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
        "🆔 ID": vue_id,
        "🌍 Indicateurs pays": vue_indicatifs,
        "⚙️ Paramètres": vue_settings,
    }

    choice = st.sidebar.radio("Aller à", list(pages.keys()), key="nav_radio")
    page_func = pages.get(choice)
    if page_func:
        page_func(df, palette)
    else:
        st.error("Page inconnue.")


if __name__ == "__main__":
    main()