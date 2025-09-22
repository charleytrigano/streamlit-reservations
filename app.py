# ============================== PARTIE 1/5 — IMPORTS, CONFIG, STYLES, HELPERS ==============================
import os, io, re, uuid, hashlib
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange
from urllib.parse import quote

import pandas as pd
import numpy as np
import streamlit as st
import altair as alt

# ------------------------------ CONFIG APP ------------------------------
st.set_page_config(
    page_title="✨ Villa Tobias — Gestion des Réservations",
    page_icon="✨",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------ CONSTANTES ------------------------------
# Chemins par défaut (remplacés ensuite par l’appartement actif)
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"
APARTMENTS_CSV   = "apartments.csv"

DEFAULT_PALETTE = {
    "Booking": "#1b9e77",
    "Airbnb":  "#d95f02",
    "Abritel": "#7570b3",
    "Direct":  "#e7298a",
}

# Google Form & Sheet (adapter si tu changes)
FORM_SHORT_URL = "https://urlr.me/kZuH94"  # lien court public
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1ci-4i8dZWzixt0p5WPdB2D8ePCpNQDD0jjZf41KtYns/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSMie1mawlXGJtqC7KL_gSgeC9e8jwOxcqMzC1HmxxU8FCrOxD0HXl5APTO939__tu7EPh6aiXHnSnF/pub?output=csv"

# ------------------------------ STYLES ÉCRAN ------------------------------
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
          .glass {{
            background:{"rgba(255,255,255,.65)" if light else "rgba(255,255,255,.06)"};
            border:1px solid {border}; border-radius:12px; padding:12px; margin:10px 0;
          }}
          .chip {{
            display:inline-block; padding:6px 10px; border-radius:12px; margin:4px 6px;
            font-size:.86rem; background:{"#eee" if light else "#2a2f3a"}; color:{"#222" if light else "#eee"};
          }}
          .cal-grid {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px; }}
          .cal-cell {{ border:1px solid {border}; border-radius:10px; min-height:110px; padding:8px;
                      position:relative; overflow:hidden; background:{"#fff" if light else "#0b0d12"}; }}
          .cal-cell.outside {{ opacity:.45; }}
          .cal-date {{ position:absolute; top:6px; right:8px; font-weight:700; font-size:.9rem; opacity:.7; }}
          .resa-pill {{ padding:4px 6px; border-radius:6px; font-size:.84rem; margin-top:22px;
                        color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }}
          .cal-header {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:8px;
                         font-weight:700; opacity:.8; margin:6px 0 8px; }}
        </style>
        """,
        unsafe_allow_html=True
    )

def print_buttons(location: str = "main"):
    """Bouton Imprimer (écran) — déclenche window.print()."""
    target = st.sidebar if location == "sidebar" else st
    target.button("🖨️ Imprimer", key=f"print_btn_{location}")
    st.markdown(
        """
        <script>
        (function(){
          try{
            const labels = Array.from(parent.document.querySelectorAll('button span, button p'));
            const btn = labels.find(n => n.textContent && n.textContent.trim() === "🖨️ Imprimer");
            if (btn) { btn.parentElement.onclick = () => window.print(); }
          }catch(e){}
        })();
        </script>
        """,
        unsafe_allow_html=True
    )

# ------------------------------ STYLES IMPRESSION ------------------------------
def add_print_styles():
    """Feuilles de style pour l'impression (A4 portrait par défaut)."""
    st.markdown(
        r"""
        <style>
        /* Écran vs Impression */
        @media screen { .print-only { display: none !important; } }
        @media print  { .print-only { display: block !important; }
                        .screen-only { display: none !important; } }

        /* Règles globales d'impression */
        @media print {
          [data-testid="stSidebar"], header, footer, [data-testid="stToolbar"] { display: none !important; }
          [data-testid="stAppViewContainer"] { margin: 0 !important; padding: 0 !important; }
          .main .block-container { max-width: 100% !important; padding: 0 12mm !important; }

          @page { size: A4 portrait; margin: 12mm; }

          /* Cacher widgets interactifs */
          button, [role="button"], .stSelectbox, .stRadio, .stCheckbox, .stFileUploader,
          .stDownloadButton, .stSlider, .stDateInput { display: none !important; }

          /* En-tête imprimable */
          .print-header {
            display: block !important; font-size: 14px; margin: 0 0 8mm 0; padding: 0 0 6px 0;
            border-bottom: 2px solid #222;
          }
          .print-header .right { float: right; font-weight: 600; opacity: .75; }

          /* Tables HTML propres pour impression */
          table.print-table { width: 100%; border-collapse: collapse; font-size: 12px; }
          table.print-table th, table.print-table td { border: 1px solid #ccc; padding: 4px 6px; }
          table.print-table thead { display: table-header-group; }

          /* Grille calendrier : traits visibles */
          .cal-grid { gap: 6px !important; }
          .cal-cell { border: 1px solid #aaa !important; background: #fff !important; }
          .resa-pill { color: #000 !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }

          .pagebreak { page-break-before: always; }
          .nobreak  { page-break-inside: avoid; }
        }

        /* Paysage — activé dynamiquement sur la page calendrier seulement */
        @media print {
          body.landscape-print .main .block-container { padding: 0 10mm !important; }
          body.landscape-print .cal-grid { gap: 6px !important; }
        }
        </style>
        """,
        unsafe_allow_html=True
    )

def render_print_header():
    """Bandeau qui n'apparaît qu'à l'impression avec le nom de l'appartement et la date."""
    from datetime import datetime as _dt
    st.markdown(
        f"""
        <div class="print-only print-header">
          <div><strong>Gestion des Réservations</strong></div>
          <div class="right">{_dt.now().strftime('%d/%m/%Y %H:%M')}</div>
          <div style="clear:both"></div>
        </div>
        """,
        unsafe_allow_html=True
    )

def enable_landscape_print():
    """Active A4 paysage uniquement pour la vue calendrier (injection @page)."""
    st.markdown(
        """
        <script>
        try {
          const b = parent.document.querySelector('body') || document.querySelector('body');
          if (b && !b.classList.contains('landscape-print')) {
            b.classList.add('landscape-print');
          }
          const css = document.createElement('style');
          css.innerHTML = '@page { size: A4 landscape; margin: 10mm; }';
          parent.document.head.appendChild(css);
        } catch(e) {}
        </script>
        """,
        unsafe_allow_html=True
    )

# ------------------------------ HELPERS DATA ------------------------------
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
    if isinstance(x, pd.Series):
        return x
    if isinstance(x, (list, tuple, np.ndarray)):
        s = pd.Series(list(x))
        if index is not None and len(index) == len(s):
            s.index = index
        return s
    if index is None:
        return pd.Series([x])
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

def _format_phone_e164(phone: str) -> str:
    s = re.sub(r"\D","", str(phone or ""))
    if not s: return ""
    if s.startswith("33"): return "+"+s
    if s.startswith("0"):  return "+33"+s[1:]
    return "+"+s

PHONE_PREFIX_COUNTRY = {
    "33":"France","34":"Espagne","49":"Allemagne","44":"Royaume-Uni","39":"Italie",
    "41":"Suisse","32":"Belgique","352":"Luxembourg","351":"Portugal",
    "1":"États-Unis/Canada","61":"Australie","64":"Nouvelle-Zélande",
    "420":"Tchéquie","421":"Slovaquie","36":"Hongrie","40":"Roumanie",
    "30":"Grèce","31":"Pays-Bas","353":"Irlande","354":"Islande","358":"Finlande",
    "46":"Suède","47":"Norvège","48":"Pologne","43":"Autriche","45":"Danemark",
    "90":"Turquie","212":"Maroc","216":"Tunisie","971":"Émirats Arabes Unis"
}
def _phone_country(phone: str) -> str:
    p = str(phone or "").strip()
    if not p: return ""
    if p.startswith("+"): p1 = p[1:]
    elif p.startswith("00"): p1 = p[2:]
    elif p.startswith("0"): return "France"
    else: p1 = p
    for k in sorted(PHONE_PREFIX_COUNTRY.keys(), key=lambda x: -len(x)):
        if p1.startswith(k): return PHONE_PREFIX_COUNTRY[k]
    return "Inconnu"

# ------------------------------ NORMALISATION & SAUVEGARDE ------------------------------
def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    rename_map = {
        "Payé":"paye","Client":"nom_client","Plateforme":"plateforme",
        "Arrivée":"date_arrivee","Départ":"date_depart","Nuits":"nuitees",
        "Brut (€)":"prix_brut"
    }
    df.rename(columns=rename_map, inplace=True)

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = pd.Series([None]*len(df), index=df.index)

    for c in df.columns:
        df[c] = _as_series(df[c], index=df.index)

    for b in ["paye","sms_envoye","post_depart_envoye"]:
        df[b] = _to_bool_series(df[b])

    for n in ["prix_brut","commissions","frais_cb","menage","taxes_sejour","nuitees","charges","%","base"]:
        df[n] = _to_num(df[n]).fillna(0.0)

    df["date_arrivee"] = _to_date(df["date_arrivee"])
    df["date_depart"]  = _to_date(df["date_depart"])

    mask_ok = pd.notna(df["date_arrivee"]) & pd.notna(df["date_depart"])
    if mask_ok.any():
        da = pd.to_datetime(df.loc[mask_ok,"date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok,"date_depart"])
        df.loc[mask_ok,"nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)

    prix_brut = _to_num(df["prix_brut"])
    commissions = _to_num(df["commissions"])
    frais_cb = _to_num(df["frais_cb"])
    menage = _to_num(df["menage"])
    taxes  = _to_num(df["taxes_sejour"])

    df["prix_net"] = (prix_brut - commissions - frais_cb).fillna(0.0)
    df["charges"]  = (prix_brut - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - menage - taxes).fillna(0.0)

    with np.errstate(divide="ignore", invalid="ignore"):
        df["%"] = np.where(prix_brut > 0, (df["charges"]/prix_brut*100), 0.0).astype(float)

    miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip()=="")
    if miss_res.any():
        df.loc[miss_res,"res_id"] = [str(uuid.uuid4()) for _ in range(int(miss_res.sum()))]

    miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip()=="")
    if miss_uid.any():
        df.loc[miss_uid,"ical_uid"] = df.loc[miss_uid].apply(build_stable_uid, axis=1)

    for c in ["nom_client","plateforme","telephone","email","pays"]:
        df[c] = df[c].astype(str).replace({"nan":"","None":""}).str.strip()

    need = df["pays"].eq("") | df["pays"].isna()
    if need.any():
        df.loc[need,"pays"] = df.loc[need,"telephone"].apply(_phone_country)

    return df[BASE_COLS]

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee","date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations: str, csv_plateformes: str):
    # crée les fichiers s'ils n'existent pas
    for fichier, header in [
        (csv_reservations, "nom_client,email,telephone,plateforme,date_arrivee,date_depart,nuitees,prix_brut\n"),
        (csv_plateformes,  "plateforme,couleur\nBooking,#1b9e77\nAirbnb,#d95f02\nAbritel,#7570b3\nDirect,#e7298a\n"),
    ]:
        if not os.path.exists(fichier):
            with open(fichier, "w", encoding="utf-8", newline="") as f:
                f.write(header)

    raw = _load_file_bytes(csv_reservations)
    base_df = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base_df)

    rawp = _load_file_bytes(csv_plateformes)
    palette = DEFAULT_PALETTE.copy()
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if {"plateforme","couleur"}.issubset(pal_df.columns):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception as e:
            st.warning(f"Erreur de palette : {e}")
    return df, palette

# ---------- Helpers impression & CSS global (à coller une seule fois) ----------

def _apply_custom_css():
    """CSS global : mise en page impression A4 paysage, masquage de la sidebar, etc."""
    st.markdown(
        """
        <style>
        /* ---- Écran ---- */
        .print-only { display: none !important; }

        /* ---- Impression ---- */
        @page { size: A4 landscape; margin: 10mm; }

        @media print {
          /* Plein écran pour le contenu */
          [data-testid="stSidebar"], header, footer { display: none !important; }
          [data-testid="stAppViewContainer"] { padding: 0 !important; }
          .main .block-container { padding: 0 !important; }

          /* Masquer boutons, inputs, radios, etc. */
          button, [role="radiogroup"], [data-baseweb="select"], input, textarea, label { 
            visibility: hidden !important; height: 0 !important; overflow: hidden !important;
          }

          /* Montrer l’en-tête d’impression si présent */
          .print-only { display: block !important; }

          /* Resserre les tableaux pour tenir en largeur */
          [data-testid="stDataFrame"] table { font-size: 11px !important; }
          [data-testid="stDataFrame"] th, 
          [data-testid="stDataFrame"] td { padding: 4px 6px !important; }

          /* Option: masquer quelques colonnes techniques par nom courant (si visibles)
             -> selon tes besoins, dé-commente et adapte.
          */
          /* th:contains("res_id"), td:contains("@villa-tobias") { display:none !important; } */
        }
        </style>
        """,
        unsafe_allow_html=True
    )

def render_print_header(title: str | None = None):
    """Petit en-tête qui n’apparaît qu’à l’impression (A4 paysage)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    titre = title or f"Résumé — {apt_name}"
    today = date.today().strftime("%d/%m/%Y")
    st.markdown(
        f"""
        <div class="print-only" style="margin-bottom:10px;">
          <h2 style="margin:0;padding:0;">{titre}</h2>
          <div style="opacity:.75;">Imprimé le {today}</div>
          <hr style="margin:8px 0 12px 0;">
        </div>
        """,
        unsafe_allow_html=True
    )

# ============================== PARTIE 2/5 — APARTMENTS, CHARGEMENT ACTIF, VUES ACCUEIL & RÉSERVATIONS ==============================

# --------- APARTMENTS (sélecteur sans mot de passe) ---------
def _read_apartments_csv() -> pd.DataFrame:
    try:
        if not os.path.exists(APARTMENTS_CSV):
            return pd.DataFrame(columns=["slug","name"])
        raw = _load_file_bytes(APARTMENTS_CSV)
        df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame(columns=["slug","name"])
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "slug" not in df.columns: df["slug"] = ""
        if "name" not in df.columns: df["name"] = ""
        df["slug"] = (df["slug"].astype(str).str.replace("\ufeff","",regex=False)
                      .str.strip().str.replace(" ","-",regex=False).str.replace("_","-",regex=False).str.lower())
        df["name"] = df["name"].astype(str).str.replace("\ufeff","",regex=False).str.strip()
        df = df[(df["slug"]!="") & (df["name"]!="")].drop_duplicates(subset=["slug"], keep="first")
        return df[["slug","name"]]
    except Exception:
        return pd.DataFrame(columns=["slug","name"])

def _current_apartment() -> dict | None:
    slug = st.session_state.get("apt_slug","")
    name = st.session_state.get("apt_name","")
    if slug and name:
        return {"slug": slug, "name": name}
    return None

def _select_apartment_sidebar() -> bool:
    """Affiche le sélecteur dans la sidebar et met à jour les chemins CSV pour l'appartement actif.
    Retourne True si la sélection a changé (pour éventuellement recharger)."""
    st.sidebar.markdown("### Appartement")
    df_apts = _read_apartments_csv()
    if df_apts.empty:
        st.sidebar.warning("Aucun appartement trouvé dans apartments.csv")
        return False

    options = df_apts["slug"].tolist()
    labels = {r["slug"]: r["name"] for _, r in df_apts.iterrows()}

    cur_slug = st.session_state.get("apt_slug", options[0] if options else "")
    if cur_slug not in options and options:
        cur_slug = options[0]
    default_idx = options.index(cur_slug)

    slug = st.sidebar.selectbox(
        "Choisir un appartement",
        options=options,
        index=default_idx,
        format_func=lambda s: labels.get(s, s),
        key="apt_slug_selectbox",
    )
    name = labels.get(slug, slug)

    changed = (slug != st.session_state.get("apt_slug","") or name != st.session_state.get("apt_name",""))

    # synchronise session et variables globales de chemins
    st.session_state["apt_slug"] = slug
    st.session_state["apt_name"] = name
    st.session_state["CSV_RESERVATIONS"] = f"reservations_{slug}.csv"
    st.session_state["CSV_PLATEFORMES"]  = f"plateformes_{slug}.csv"

    global CSV_RESERVATIONS, CSV_PLATEFORMES
    CSV_RESERVATIONS = st.session_state["CSV_RESERVATIONS"]
    CSV_PLATEFORMES  = st.session_state["CSV_PLATEFORMES"]

    st.sidebar.success(f"Connecté : {name}")
    try:
        print_buttons(location="sidebar")
    except Exception:
        pass

    return changed

def _load_data_for_active_apartment():
    """Retourne (df, palette) pour l'appartement actif."""
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_pal = st.session_state.get("CSV_PLATEFORMES",  CSV_PLATEFORMES)
    try:
        return charger_donnees(csv_res, csv_pal)
    except TypeError:
        # compat ancienne signature
        return charger_donnees(CSV_RESERVATIONS, CSV_PLATEFORMES)
    except Exception:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE.copy()

# --------- VUE : ACCUEIL ---------
def vue_accueil(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()
    render_print_header()  # bandeau impression

    today = date.today()
    tomorrow = today + timedelta(days=1)
    st.write(f"**Aujourd'hui : {today.strftime('%d/%m/%Y')}**")

    dfv = df.copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    arr = dfv[dfv["date_arrivee"] == today][["nom_client","telephone","plateforme","pays"]]
    dep = dfv[dfv["date_depart"]  == today][["nom_client","telephone","plateforme","pays"]]
    arr_plus1 = dfv[dfv["date_arrivee"] == tomorrow][["nom_client","telephone","plateforme","pays"]]

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("🟢 Arrivées du jour")
        st.dataframe(arr if not arr.empty else pd.DataFrame({"info":["Aucune arrivée."]}), use_container_width=True)
    with c2:
        st.subheader("🔴 Départs du jour")
        st.dataframe(dep if not dep.empty else pd.DataFrame({"info":["Aucun départ."]}), use_container_width=True)
    with c3:
        st.subheader("🟠 Arrivées J+1 (demain)")
        st.dataframe(arr_plus1 if not arr_plus1.empty else pd.DataFrame({"info":["Aucune arrivée demain."]}), use_container_width=True)

# --------- VUE : RÉSERVATIONS (colonnes techniques masquées) ---------
_TECH_COLS_TO_HIDE = {
    "email","sms_envoye","post_depart_envoye","%","charges","base",
    "commissions","frais_cb","menage","taxes_sejour","ical_uid","res_id"
}

def vue_reservations(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()
    render_print_header()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")

    years_avail  = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1,13))
    plats_avail  = sorted(dfa["plateforme"].astype(str).str.strip().replace({"":np.nan}).dropna().unique().tolist())

    c1,c2,c3,c4 = st.columns(4)
    year  = c1.selectbox("Année", ["Toutes"]+years_avail, index=0)
    month = c2.selectbox("Mois",  ["Tous"]+months_avail, index=0)
    plat  = c3.selectbox("Plateforme", ["Toutes"]+plats_avail, index=0)
    payf  = c4.selectbox("Paiement", ["Tous","Payé uniquement","Non payé uniquement"], index=0)

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

    brut = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net  = float(pd.to_numeric(data["prix_net"],  errors="coerce").fillna(0).sum())
    base = float(pd.to_numeric(data["base"],     errors="coerce").fillna(0).sum())
    nuits= int(pd.to_numeric(data["nuitees"],   errors="coerce").fillna(0).sum())
    adr  = (net/nuits) if nuits>0 else 0.0
    charges = float(pd.to_numeric(data["charges"], errors="coerce").fillna(0).sum())

    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
          <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
          <span class='chip'><small>Charges</small><br><strong>{charges:,.2f} €</strong></span>
          <span class='chip'><small>Base</small><br><strong>{base:,.2f} €</strong></span>
          <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
          <span class='chip'><small>ADR (net)</small><br><strong>{adr:,.2f} €</strong></span>
        </div>
        """.replace(",", " "),
        unsafe_allow_html=True
    )
    st.markdown("---")

    # Masquer colonnes techniques à l’affichage
    display_cols = [c for c in data.columns if c not in _TECH_COLS_TO_HIDE and not c.endswith("_dt")]
    order_idx = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order_idx, display_cols]
    st.dataframe(data, use_container_width=True)

# ============================== PARTIE 3/5 — VUES AJOUTER / MODIFIER / PLATEFORMES ==============================

def vue_ajouter(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter une réservation — {apt_name}")
    print_buttons()
    render_print_header()

    with st.form("form_add", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom  = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel  = st.text_input("Téléphone")
            arr  = st.date_input("Arrivée", date.today())
            dep  = st.date_input("Départ",  date.today() + timedelta(days=1))
        with c2:
            plat = st.selectbox("Plateforme", list(palette.keys()) or list(DEFAULT_PALETTE.keys()))
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage  = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes   = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye    = st.checkbox("Payé", value=False)

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
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()
    render_print_header()

    if df.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
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
            nom  = st.text_input("Nom", value=row.get("nom_client", "") or "")
            email = st.text_input("Email", value=row.get("email", "") or "")
            tel  = st.text_input("Téléphone", value=row.get("telephone", "") or "")
            arrivee = st.date_input("Arrivée", value=row.get("date_arrivee"))
            depart  = st.date_input("Départ",  value=row.get("date_depart"))
        with c2:
            palette_keys = list(palette.keys()) or list(DEFAULT_PALETTE.keys())
            try:
                plat_idx = palette_keys.index(row.get("plateforme"))
            except Exception:
                plat_idx = 0
            plat = st.selectbox("Plateforme", options=palette_keys, index=plat_idx)
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut = float(pd.to_numeric(row.get("prix_brut"), errors="coerce") or 0)
            commissions = float(pd.to_numeric(row.get("commissions"), errors="coerce") or 0)
            frais_cb = float(pd.to_numeric(row.get("frais_cb"), errors="coerce") or 0)
            menage  = float(pd.to_numeric(row.get("menage"), errors="coerce") or 0)
            taxes   = float(pd.to_numeric(row.get("taxes_sejour"), errors="coerce") or 0)

            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=brut)
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=commissions)
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=frais_cb)
            menage  = st.number_input("Ménage", min_value=0.0, step=0.01, value=menage)
            taxes   = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=taxes)

        b1, b2 = st.columns([0.7, 0.3])
        if b1.form_submit_button("💾 Enregistrer"):
            updates = {
                "nom_client": nom, "email": email, "telephone": tel, "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye, "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes
            }
            for k, v in updates.items():
                df.loc[original_idx, k] = v
            if sauvegarder_donnees(df):
                st.success("Modifié ✅")
                st.rerun()

        if b2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=original_idx)
            if sauvegarder_donnees(df2):
                st.warning("Supprimé.")
                st.rerun()


def vue_plateformes(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes & couleurs — {apt_name}")
    print_buttons()
    render_print_header()

    HAS_COLORCOL = hasattr(getattr(st, "column_config", object), "ColorColumn")

    plats_df = sorted(
        df.get("plateforme", pd.Series([], dtype=str))
        .astype(str).str.strip()
        .replace({"nan": ""})
        .dropna().unique().tolist()
    )
    all_plats = sorted(set(list(palette.keys()) + plats_df))
    base = pd.DataFrame({
        "plateforme": all_plats,
        "couleur": [palette.get(p, "#666666") for p in all_plats],
    })

    if HAS_COLORCOL:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorColumn("Couleur (hex)"),
        }
    else:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn(
                "Couleur (hex)",
                help="Ex: #1b9e77",
                validate=r"^#([0-9A-Fa-f]{6})$",
                width="small",
            ),
        }

    edited = st.data_editor(
        base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
        key="palette_editor",
    )

    # Aperçu couleurs si pas de ColorColumn
    if not HAS_COLORCOL and not edited.empty:
        chips = []
        for _, r in edited.iterrows():
            plat = str(r["plateforme"]).strip()
            col = str(r["couleur"]).strip()
            if not plat:
                continue
            ok = bool(re.match(r"^#([0-9A-Fa-f]{6})$", col or ""))
            chips.append(
                "<span style='display:inline-block;margin:4px 6px;padding:6px 10px;"
                f"border-radius:12px;background:{col if ok else '#666'};color:#fff;'>{plat} {col}</span>"
            )
        if chips:
            st.markdown("".join(chips), unsafe_allow_html=True)

    c1, c2, c3 = st.columns([0.5, 0.3, 0.2])
    if c1.button("💾 Enregistrer la palette", key="save_palette_btn"):
        try:
            to_save = edited.copy()
            to_save["plateforme"] = to_save["plateforme"].astype(str).str.strip()
            to_save["couleur"]    = to_save["couleur"].astype(str).str.strip()
            to_save = to_save[to_save["plateforme"] != ""].drop_duplicates(subset=["plateforme"])
            if not HAS_COLORCOL:
                ok = to_save["couleur"].str.match(r"^#([0-9A-Fa-f]{6})$")
                to_save.loc[~ok, "couleur"] = "#666666"
            to_save.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("↩️ Palette par défaut", key="restore_palette_btn"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme", "couleur"]).to_csv(
                CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8", lineterminator="\n"
            )
            st.success("Palette restaurée.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c3.button("🔄 Recharger", key="reload_palette_btn"):
        st.cache_data.clear()
        st.rerun()

# ============================== PARTIE 4/5 — VUES CALENDRIER & RAPPORT ==============================

def vue_calendrier(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier (grille mensuelle) — {apt_name}")
    print_buttons()
    render_print_header()

    dfv = df.dropna(subset=["date_arrivee", "date_depart"]).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois  = st.selectbox("Mois",  options=list(range(1, 13)), index=today.month - 1)

    # En-têtes de jours
    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div>"
        "<div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True
    )

    def day_resas(d):
        mask = (dfv["date_arrivee"] <= d) & (dfv["date_depart"] > d)
        return dfv[mask]

    cal = Calendar(firstweekday=0)  # Lundi
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
                        color = palette.get(r.get("plateforme"), "#888")
                        name  = str(r.get("nom_client") or "")[:22]
                        cell += (
                            f"<div class='resa-pill' style='background:{color}' "
                            f"title='{r.get('nom_client','')}'>{name}</div>"
                        )
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)
    st.markdown("---")

    # Détail du mois
    st.subheader("Détail du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    from calendar import monthrange as _mr
    fin_mois   = date(annee, mois, _mr(annee, mois)[1])
    rows = dfv[(dfv["date_arrivee"] <= fin_mois) & (dfv["date_depart"] > debut_mois)].copy()

    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
        return

    plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
    plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
    if plat != "Toutes":
        rows = rows[rows["plateforme"] == plat]

    brut  = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
    net   = float(pd.to_numeric(rows["prix_net"],  errors="coerce").fillna(0).sum())
    nuits = int(pd.to_numeric(rows["nuitees"],    errors="coerce").fillna(0).sum())

    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
          <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
          <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
        </div>
        """.replace(",", " "),
        unsafe_allow_html=True
    )
    st.dataframe(
        rows[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "paye", "pays"]],
        use_container_width=True
    )


def vue_rapport(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📊 Rapport — {apt_name}")
    print_buttons()
    render_print_header()

    if df is None or df.empty:
        st.info("Aucune donnée.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    dfa["date_depart_dt"]  = pd.to_datetime(dfa["date_depart"],  errors="coerce")

    years_avail  = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1, 13))
    plats_avail  = sorted(dfa["plateforme"].astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())

    # Pays normalisé (sur base du téléphone si vide)
    dfa["_pays"] = dfa["pays"].replace("", np.nan)
    dfa["_pays"] = dfa["_pays"].fillna(dfa["telephone"].apply(_phone_country)).replace("", "Inconnu")
    pays_avail   = sorted(dfa["_pays"].unique().tolist())
    if "France" in pays_avail:
        pays_avail.remove("France"); pays_avail = ["France"] + pays_avail

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1.2, 1.2])
    year   = c1.selectbox("Année",      ["Toutes"] + years_avail, index=0)
    month  = c2.selectbox("Mois",       ["Tous"] + months_avail,  index=0)
    plat   = c3.selectbox("Plateforme", ["Toutes"] + plats_avail, index=0)
    payf   = c4.selectbox("Pays",       ["Tous"] + pays_avail,    index=0)
    metric = c5.selectbox("Métrique",   ["prix_brut", "prix_net", "base", "charges", "menage", "taxes_sejour", "nuitees"], index=1)

    data = dfa.copy()
    data["pays"] = data["_pays"]
    if year  != "Toutes": data = data[data["date_arrivee_dt"].dt.year  == int(year)]
    if month != "Tous":   data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat  != "Toutes": data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]
    if payf  != "Tous":   data = data[data["pays"] == payf]

    if data.empty:
        st.warning("Aucune donnée après filtres.")
        return

    # ===== Taux d'occupation par mois =====
    st.markdown("---")
    st.subheader("📅 Taux d'occupation")

    data["mois"]    = data["date_arrivee_dt"].dt.to_period("M").astype(str)
    data["nuitees"] = (data["date_depart_dt"] - data["date_arrivee_dt"]).dt.days

    occ_mois = data.groupby(["mois", "plateforme"], as_index=False)["nuitees"] \
                   .sum().rename(columns={"nuitees": "nuitees_occupees"})

    def _jours_mois(p):
        an, mo = map(int, p.split("-"))
        return monthrange(an, mo)[1]

    occ_mois["jours_dans_mois"] = occ_mois["mois"].apply(_jours_mois)
    occ_mois["taux_occupation"] = (occ_mois["nuitees_occupees"] / occ_mois["jours_dans_mois"]) * 100

    col_plat, col_export = st.columns([1, 1])
    plat_occ = col_plat.selectbox("Filtrer par plateforme (occupation)", ["Toutes"] + plats_avail, index=0)
    occ_filtered = occ_mois if plat_occ == "Toutes" else occ_mois[occ_mois["plateforme"] == plat_occ]

    filtered_nuitees = pd.to_numeric(occ_filtered["nuitees_occupees"], errors="coerce").fillna(0).sum()
    filtered_jours   = pd.to_numeric(occ_filtered["jours_dans_mois"],   errors="coerce").fillna(0).sum()
    taux_global_filtered = (filtered_nuitees / filtered_jours) * 100 if filtered_jours > 0 else 0

    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'><small>Taux global</small><br><strong>{taux_global_filtered:.1f}%</strong></span>
          <span class='chip'><small>Nuitées occupées</small><br><strong>{int(filtered_nuitees)}</strong></span>
          <span class='chip'><small>Jours dispos</small><br><strong>{int(filtered_jours)}</strong></span>
          <span class='chip'><small>Pays filtré</small><br><strong>{payf if payf!='Tous' else 'Tous'}</strong></span>
        </div>
        """,
        unsafe_allow_html=True
    )

    occ_export = occ_filtered[["mois", "plateforme", "nuitees_occupees", "jours_dans_mois", "taux_occupation"]] \
                           .copy().sort_values(["mois", "plateforme"], ascending=[False, True])
    col_export.download_button(
        "⬇️ Exporter occupation (CSV)",
        data=occ_export.to_csv(index=False).encode("utf-8"),
        file_name="taux_occupation.csv",
        mime="text/csv",
    )
    xlsx_occ, _ = _df_to_xlsx_bytes(occ_export, "Taux d'occupation")
    if xlsx_occ:
        col_export.download_button(
            "⬇️ Exporter occupation (Excel)",
            data=xlsx_occ,
            file_name="taux_occupation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

    st.dataframe(
        occ_export.assign(taux_occupation=lambda x: x["taux_occupation"].round(1)),
        use_container_width=True
    )

    # ===== Comparaison entre années =====
    st.markdown("---")
    st.subheader("📊 Comparaison des taux d'occupation par année")

    data["annee"] = data["date_arrivee_dt"].dt.year
    occ_annee = data.groupby(["annee", "plateforme"])["nuitees"] \
                    .sum().reset_index().rename(columns={"nuitees": "nuitees_occupees"})

    def _jours_annee(an):
        return 366 if (an % 4 == 0 and an % 100 != 0) or (an % 400 == 0) else 365

    occ_annee["jours_dans_annee"] = occ_annee["annee"].apply(_jours_annee)
    occ_annee["taux_occupation"]  = (occ_annee["nuitees_occupees"] / occ_annee["jours_dans_annee"]) * 100

    uniques = sorted(occ_annee["annee"].unique())
    default_years = uniques[-2:] if len(uniques) >= 2 else uniques
    years_pick = st.multiselect(
        "Sélectionner les années à comparer",
        options=uniques,
        default=default_years
    )

    if years_pick:
        occ_comp = occ_annee[occ_annee["annee"].isin(years_pick)].copy()
        try:
            chart_comparaison = alt.Chart(occ_comp).mark_bar().encode(
                x=alt.X("annee:N", title="Année"),
                y=alt.Y("taux_occupation:Q", title="Taux d'occupation (%)", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("plateforme:N", title="Plateforme"),
                tooltip=["annee", "plateforme", alt.Tooltip("taux_occupation:Q", format=".1f")],
            ).properties(height=400)
            st.altair_chart(chart_comparaison, use_container_width=True)
        except Exception as e:
            st.warning(f"Graphique indisponible : {e}")

        st.dataframe(
            occ_comp[["annee", "plateforme", "nuitees_occupees", "taux_occupation"]]
            .sort_values(["annee", "plateforme"])
            .assign(taux_occupation=lambda x: x["taux_occupation"].round(1)),
            use_container_width=True
        )

    # ===== Métriques financières =====
    st.markdown("---")
    st.subheader("💰 Métriques financières")

    data["mois"] = data["date_arrivee_dt"].dt.to_period("M").astype(str)
    total_val = float(pd.to_numeric(data[metric], errors="coerce").fillna(0).sum())
    st.markdown(f"**Total {metric.replace('_', ' ')} : {total_val:,.2f}**".replace(",", " "))

    agg_mois = data.groupby("mois", as_index=False)[metric].sum().sort_values("mois")
    agg_mois_plat = data.groupby(["mois", "plateforme"], as_index=False)[metric].sum().sort_values(["mois", "plateforme"])

    with st.expander("Détail par mois", expanded=True):
        st.dataframe(agg_mois, use_container_width=True)

    with st.expander("Détail par mois et par plateforme", expanded=False):
        st.dataframe(agg_mois_plat, use_container_width=True)

    try:
        chart = alt.Chart(agg_mois_plat).mark_bar().encode(
            x=alt.X("mois:N", sort=None, title="Mois"),
            y=alt.Y(f"{metric}:Q", title=metric.replace("_", " ").title()),
            color=alt.Color("plateforme:N", title="Plateforme"),
            tooltip=["mois", "plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")],
        )
        st.altair_chart(chart.properties(height=420), use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique indisponible : {e}")

    # ===== Analyse par pays (avec filtre Année dédié) =====
    st.markdown("---")
    st.subheader("🌍 Analyse par pays")

    years_pays = years_avail
    year_pays = st.selectbox("Année (analyse pays)", ["Toutes"] + years_pays, index=0, key="year_pays")
    data_p = dfa.copy()
    data_p["pays"] = dfa["_pays"]
    if year_pays != "Toutes":
        data_p = data_p[data_p["date_arrivee_dt"].dt.year == int(year_pays)]
    data_p["nuitees"] = (data_p["date_depart_dt"] - data_p["date_arrivee_dt"]).dt.days

    agg_pays = data_p.groupby("pays", as_index=False).agg(
        reservations=("nom_client", "count"),
        nuitees=("nuitees", "sum"),
        prix_brut=("prix_brut", "sum"),
        prix_net=("prix_net", "sum"),
        menage=("menage", "sum"),
        taxes_sejour=("taxes_sejour", "sum"),
        charges=("charges", "sum"),
        base=("base", "sum"),
    )

    total_net = float(pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0).sum())
    total_res = int(pd.to_numeric(agg_pays["reservations"], errors="coerce").fillna(0).sum())

    agg_pays["part_revenu_%"] = np.where(
        total_net > 0,
        (pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0) / total_net) * 100,
        0.0
    )
    agg_pays["ADR_net"] = np.where(
        pd.to_numeric(agg_pays["nuitees"], errors="coerce").fillna(0) > 0,
        pd.to_numeric(agg_pays["prix_net"], errors="coerce").fillna(0) / pd.to_numeric(agg_pays["nuitees"], errors="coerce").fillna(0),
        0.0
    )

    agg_pays = agg_pays.sort_values(["prix_net", "reservations"], ascending=[False, False])

    nb_pays  = int(agg_pays["pays"].nunique())
    top_pays = agg_pays.iloc[0]["pays"] if not agg_pays.empty else "—"

    st.markdown(
        f"""
        <div class='glass'>
          <span class='chip'><small>Année</small><br><strong>{year_pays}</strong></span>
          <span class='chip'><small>Pays distincts</small><br><strong>{nb_pays}</strong></span>
          <span class='chip'><small>Total réservations</small><br><strong>{total_res}</strong></span>
          <span class='chip'><small>Top pays (CA net)</small><br><strong>{top_pays}</strong></span>
        </div>
        """,
        unsafe_allow_html=True
    )

    disp = agg_pays.copy()
    num_cols = ["reservations", "nuitees", "prix_brut", "prix_net", "menage", "taxes_sejour", "charges", "base", "ADR_net", "part_revenu_%"]
    for c in num_cols:
        disp[c] = pd.to_numeric(disp[c], errors="coerce")
    disp["reservations"]   = disp["reservations"].fillna(0).astype("int64")
    disp["pays"]           = disp["pays"].astype(str).replace({"nan": "Inconnu", "": "Inconnu"})
    disp["prix_brut"]      = disp["prix_brut"].round(2)
    disp["prix_net"]       = disp["prix_net"].round(2)
    disp["ADR_net"]        = disp["ADR_net"].round(2)
    disp["part_revenu_%"]  = disp["part_revenu_%"].round(1)

    order_cols = ["pays", "reservations", "nuitees", "prix_brut", "prix_net", "charges", "menage", "taxes_sejour", "base", "ADR_net", "part_revenu_%"]
    disp = disp[[c for c in order_cols if c in disp.columns]]
    st.dataframe(disp, use_container_width=True)

    try:
        topN = st.slider("Afficher les N premiers pays (par CA net)", min_value=3, max_value=20, value=12, step=1)
        chart_pays = alt.Chart(agg_pays.head(topN)).mark_bar().encode(
            x=alt.X("pays:N", sort="-y", title="Pays"),
            y=alt.Y("prix_net:Q", title="CA net (€)"),
            tooltip=[
                "pays",
                alt.Tooltip("reservations:Q", title="Réservations"),
                alt.Tooltip("nuitees:Q", title="Nuitées"),
                alt.Tooltip("ADR_net:Q", title="ADR net", format=",.2f"),
                alt.Tooltip("part_revenu_%:Q", title="Part (%)", format=".1f"),
            ],
            color=alt.Color("pays:N", legend=None)
        ).properties(height=420)
        st.altair_chart(chart_pays, use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique 'Analyse pays' indisponible : {e}")

    # ===== Évolution du taux d'occupation (ligne) =====
    st.markdown("---")
    st.subheader("📈 Évolution du taux d'occupation")
    try:
        chart_occ = alt.Chart(occ_mois).mark_line(point=True).encode(
            x=alt.X("mois:N", sort=None, title="Mois"),
            y=alt.Y("taux_occupation:Q", title="Taux d'occupation (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("plateforme:N", title="Plateforme"),
            tooltip=["mois", "plateforme", alt.Tooltip("taux_occupation:Q", format=".1f")],
        )
        st.altair_chart(chart_occ.properties(height=420), use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique du taux d'occupation indisponible : {e}")

# ============================== PARTIE 5/5 — GOOGLE SHEET / CLIENTS / ID / PARAMÈTRES ==============================

def vue_google_sheet(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Fiche d'arrivée / Google Sheet — {apt_name}")
    print_buttons()
    render_print_header()
    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")
    st.markdown(f'<iframe src="{GOOGLE_FORM_VIEW}" width="100%" height="900" frameborder="0"></iframe>', unsafe_allow_html=True)
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
            rep_display = rep.drop(columns=mask_cols, errors="ignore")
        else:
            rep_display = rep
        st.dataframe(rep_display, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")


def vue_clients(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Liste des clients — {apt_name}")
    print_buttons()
    render_print_header()
    if df.empty:
        st.info("Aucun client.")
        return

    clients = df[['nom_client', 'telephone', 'email', 'plateforme', 'res_id', 'pays']].copy()
    for c in ["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]:
        clients[c] = clients[c].astype(str).str.strip().replace({"nan": ""})

    need = clients["pays"].eq("") | clients["pays"].isna()
    if need.any():
        clients.loc[need, "pays"] = clients.loc[need, "telephone"].apply(_phone_country)

    cols_order = ["nom_client", "pays", "telephone", "email", "plateforme", "res_id"]
    clients = clients[cols_order]
    clients = clients.loc[clients["nom_client"] != ""].drop_duplicates()
    clients = clients.sort_values(by="nom_client", kind="stable")
    st.dataframe(clients, use_container_width=True)


def vue_id(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🆔 Identifiants des réservations — {apt_name}")
    print_buttons()
    render_print_header()
    if df is None or df.empty:
        st.info("Aucune réservation.")
        return
    tbl = df[["res_id", "nom_client", "telephone", "email", "plateforme", "pays"]].copy()
    for c in ["nom_client", "telephone", "email", "plateforme", "res_id", "pays"]:
        tbl[c] = tbl[c].astype(str).str.strip().replace({"nan": ""})
    need = tbl["pays"].eq("") | tbl["pays"].isna()
    if need.any():
        tbl.loc[need, "pays"] = tbl.loc[need, "telephone"].apply(_phone_country)
    tbl = tbl.dropna(subset=["res_id"])
    tbl = tbl[tbl["res_id"] != ""].drop_duplicates()
    st.dataframe(tbl, use_container_width=True)


# ============================== PARAMÈTRES ==============================
def vue_settings(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"⚙️ Paramètres — {apt_name}")
    print_buttons()
    render_print_header()

    st.subheader("💾 Sauvegarde (exports)")
    st.download_button("⬇️ Exporter réservations (CSV)", df.to_csv(index=False).encode("utf-8"),
                       file_name=CSV_RESERVATIONS, mime="text/csv")
    xlsx_bytes, _ = _df_to_xlsx_bytes(df, "Réservations")
    if xlsx_bytes:
        st.download_button("⬇️ Exporter réservations (Excel)", xlsx_bytes,
                           file_name=CSV_RESERVATIONS.replace(".csv", ".xlsx"),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    st.subheader("♻️ Restauration (remplacer les données)")
    up = st.file_uploader("Restaurer (CSV ou XLSX)", type=["csv", "xlsx"])
    if up is not None:
        _restore_file(up, CSV_RESERVATIONS)
        st.success("Fichier restauré avec succès.")
        st.experimental_rerun()

    st.subheader("🧹 Vider le cache")
    if st.button("Vider le cache"):
        st.cache_data.clear()
        st.success("Cache vidé. Recharger la page.")

    st.subheader("⛑️ Import manuel (remplacement immédiat)")
    up2 = st.file_uploader("Importer un fichier (CSV ou XLSX)", type=["csv", "xlsx"], key="imp2")
    if up2 is not None:
        _restore_file(up2, CSV_RESERVATIONS)
        st.success("Fichier importé immédiatement.")
        st.experimental_rerun()

    st.subheader("🔎 Diagnostics")
    st.text(f"CSV_RESERVATIONS : {CSV_RESERVATIONS}")
    st.text(f"CSV_PLATEFORMES  : {CSV_PLATEFORMES}")


# ============================== MAIN ==============================
def main():
    st.set_page_config(page_title="Villa Tobias — Réservations", layout="wide")
    _apply_custom_css()

    changed = _select_apartment_sidebar()
    df, palette = _load_data_for_active_apartment()

    pages = {
        "🏠 Accueil": vue_accueil,
        "📋 Réservations": vue_reservations,
        "➕ Ajouter": vue_ajouter,
        "✏️ Modifier/Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes,
        "📅 Calendrier": vue_calendrier,
        "📊 Rapport": vue_rapport,
        "✉️ SMS": vue_sms,
        "📝 Google Sheet": vue_google_sheet,
        "👥 Clients": vue_clients,
        "🆔 ID": vue_id,
        "⚙️ Paramètres": vue_settings,
    }

    choice = st.sidebar.radio("Aller à", list(pages.keys()), key="nav_radio")
    pages[choice](df, palette)


if __name__ == "__main__":
    main()