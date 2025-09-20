# ============================== PARTIE 1 — Imports, Constantes, Utilitaires, Style ==============================
import os
import re
import hashlib
import pandas as pd
import numpy as np
from datetime import datetime, date, timedelta
from calendar import monthrange
from urllib.parse import quote
import altair as alt
import streamlit as st

# Constantes globales
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES = "plateformes.csv"
APARTMENTS_CSV = "apartments.csv"

FORM_SHORT_URL = "https://urlr.me/kZuH94"
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1LX3E82w0pHslT6xmm5N8u8HL0oq5S5K1xXY5T4zPq8k/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vSZ0GpCvb4z4CSVqEo6t7oIti7wqgE7DmbEvEkVqN6/ pub?gid=0&single=true&output=csv"

DEFAULT_PALETTE = {
    "Booking": "#1E90FF",
    "Airbnb": "#FF5A5F",
    "Abritel": "#7B68EE",
    "Expedia": "#FFD700",
    "Autre": "#808080",
}

# ========== Utilitaires généraux ==========
def _phone_country(phone: str) -> str:
    """Retourne un pays à partir du numéro de téléphone (simplifié)."""
    if not phone:
        return ""
    phone = str(phone).strip()
    if phone.startswith("+33") or phone.startswith("0033") or re.match(r"^0[1-9]", phone):
        return "France"
    if phone.startswith("+49") or phone.startswith("0049"):
        return "Allemagne"
    if phone.startswith("+34") or phone.startswith("0034"):
        return "Espagne"
    if phone.startswith("+39") or phone.startswith("0039"):
        return "Italie"
    return "Inconnu"

def _format_phone_e164(phone: str) -> str:
    """Format E.164 simplifié pour SMS/WhatsApp."""
    if not phone:
        return ""
    phone = re.sub(r"\D", "", str(phone))
    if phone.startswith("33"):
        return f"+{phone}"
    if phone.startswith("0"):
        return f"+33{phone[1:]}"
    return f"+{phone}"

def _to_date(x):
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return None

def _to_bool_series(s):
    return pd.Series(s).astype(str).str.lower().isin(["1", "true", "vrai", "yes", "oui"])

# ========== Gestion des couleurs ==========
def apply_style(light=False):
    st.markdown(
        f"""
        <style>
        body {{
            background-color: {"white" if light else "#0E1117"};
            color: {"black" if light else "white"};
        }}
        .chip {{
            display: inline-block;
            padding: 8px 12px;
            margin: 4px;
            border-radius: 12px;
            background: #333;
            color: white;
            font-size: 0.9em;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

def print_buttons():
    col1, col2 = st.columns(2)
    col1.button("🖨️ Imprimer", on_click=lambda: st.write("<script>window.print()</script>"), key=f"print_{datetime.now().timestamp()}")

# ============================== PARTIE 2 — Données & Appartements ==============================
from io import StringIO, BytesIO

# --- Colonnes standard du fichier réservations ---
BASE_COLS = [
    "paye", "nom_client", "email", "sms_envoye", "post_depart_envoye",
    "plateforme", "telephone", "pays",
    "date_arrivee", "date_depart", "nuitees",
    "prix_brut", "commissions", "frais_cb", "prix_net", "menage",
    "taxes_sejour", "base", "charges", "%",
    "res_id", "ical_uid",
]

# ---------- Helpers lecture/écriture ----------
@st.cache_data(show_spinner=False)
def _load_file_bytes(path: str):
    try:
        with open(path, "rb") as f:
            return f.read()
    except Exception:
        return None

def _detect_delimiter_and_read(raw: bytes) -> pd.DataFrame:
    """Essaye ; , \t | puis fallback pandas par défaut."""
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

def _to_num(s: pd.Series) -> pd.Series:
    s = pd.Series(s)
    s = (
        s.astype(str)
         .str.replace("€", "", regex=False)
         .str.replace(" ", "", regex=False)
         .str.replace(",", ".", regex=False)
         .str.strip()
    )
    return pd.to_numeric(s, errors="coerce")

def _series_or_default(df: pd.DataFrame, col: str, default=None):
    if col in df.columns:
        return df[col]
    return pd.Series([default] * len(df), index=df.index)

def _safe_date_series(s: pd.Series) -> pd.Series:
    ss = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if ss.isna().mean() > 0.5:
        ss2 = pd.to_datetime(s, errors="coerce", format="%Y-%m-%d")
        ss = ss.fillna(ss2)
    return ss.dt.date

def _df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Reservations"):
    buf = BytesIO()
    try:
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_name)
        return buf.getvalue(), None
    except Exception as e:
        st.warning(f"Impossible de générer le fichier Excel (openpyxl requis) : {e}")
        return None, e

# ---------- Schéma, normalisation & sauvegarde ----------
def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Normalise le DataFrame dans le schéma attendu, calcule dérivés, renseigne pays si absent."""
    if df_in is None or len(df_in) == 0:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Quelques renommages courants
    rename = {
        "Payé": "paye",
        "Client": "nom_client",
        "Plateforme": "plateforme",
        "Arrivée": "date_arrivee",
        "Départ": "date_depart",
        "Nuits": "nuitees",
        "Brut (€)": "prix_brut",
    }
    df.rename(columns=rename, inplace=True)

    # Ajoute colonnes manquantes
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = None

    # Types & nettoyages
    for b in ["paye", "sms_envoye", "post_depart_envoye"]:
        df[b] = _to_bool_series(df[b]) if b in df.columns else False

    for n in ["prix_brut", "commissions", "frais_cb", "menage", "taxes_sejour", "nuitees", "charges", "%", "base"]:
        df[n] = _to_num(_series_or_default(df, n, 0.0)).fillna(0.0)

    # Dates
    df["date_arrivee"] = _safe_date_series(df["date_arrivee"])
    df["date_depart"]  = _safe_date_series(df["date_depart"])

    # Nuits si manquantes
    mask_ok = pd.notna(df["date_arrivee"]) & pd.notna(df["date_depart"])
    if mask_ok.any():
        da = pd.to_datetime(df.loc[mask_ok, "date_arrivee"])
        dd = pd.to_datetime(df.loc[mask_ok, "date_depart"])
        df.loc[mask_ok, "nuitees"] = (dd - da).dt.days.clip(lower=0).astype(float)

    # Net, charges, base, %
    prix_brut = _to_num(df["prix_brut"])
    commissions = _to_num(df["commissions"])
    frais_cb = _to_num(df["frais_cb"])
    menage = _to_num(df["menage"])
    taxes  = _to_num(df["taxes_sejour"])

    df["prix_net"] = (prix_brut - commissions - frais_cb).fillna(0.0)
    df["charges"]  = (prix_brut - df["prix_net"]).fillna(0.0)
    df["base"]     = (df["prix_net"] - menage - taxes).fillna(0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        df["%"] = np.where(prix_brut > 0, (df["charges"] / prix_brut * 100), 0.0).astype(float)

    # IDs si manquants
    if "res_id" in df.columns:
        miss_res = df["res_id"].isna() | (df["res_id"].astype(str).str.strip() == "")
        if miss_res.any():
            df.loc[miss_res, "res_id"] = [hashlib.sha256(f"res-{i}-{datetime.utcnow()}".encode()).hexdigest()[:16]
                                          for i in range(int(miss_res.sum()))]
    if "ical_uid" in df.columns:
        miss_uid = df["ical_uid"].isna() | (df["ical_uid"].astype(str).str.strip() == "")
        if miss_uid.any():
            df.loc[miss_uid, "ical_uid"] = [
                hashlib.sha1(f"{r}".encode()).hexdigest() + "@villa" for r in range(int(miss_uid.sum()))
            ]

    # Nettoyages texte
    for c in ["nom_client", "plateforme", "telephone", "email", "pays"]:
        df[c] = df[c].astype(str).replace({"nan": "", "None": ""}).str.strip()

    # Pays si vide
    need_pays = df["pays"].eq("") | df["pays"].isna()
    if need_pays.any():
        df.loc[need_pays, "pays"] = df.loc[need_pays, "telephone"].apply(_phone_country)

    return df[BASE_COLS]

def sauvegarder_donnees(df: pd.DataFrame, csv_path: str) -> bool:
    """Sauvegarde un DF au schéma, avec dates DD/MM/YYYY, au chemin fourni."""
    try:
        out = ensure_schema(df).copy()
        for col in ["date_arrivee", "date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        out.to_csv(csv_path, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ---------- Chargement paramétrique (par appartement) ----------
@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations: str, csv_plateformes: str):
    """Crée les fichiers si absents, puis charge df & palette pour les chemins fournis."""
    # Crée au besoin
    for fichier, header in [
        (csv_reservations, "nom_client,email,telephone,plateforme,date_arrivee,date_depart,nuitees,prix_brut\n"),
        (csv_plateformes, "plateforme,couleur\nBooking,#1e90ff\nAirbnb,#e74c3c\n"),
    ]:
        if not os.path.exists(fichier):
            with open(fichier, "w", encoding="utf-8", newline="") as f:
                f.write(header)

    # Charge réservations
    raw = _load_file_bytes(csv_reservations)
    base_df = _detect_delimiter_and_read(raw) if raw is not None else pd.DataFrame()
    df = ensure_schema(base_df)

    # Palette
    palette = DEFAULT_PALETTE.copy()
    rawp = _load_file_bytes(csv_plateformes)
    if rawp is not None:
        try:
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip()
            if {"plateforme", "couleur"}.issubset(pal_df.columns):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception as e:
            st.warning(f"Erreur de chargement de la palette : {e}")

    return df, palette

# ---------- Gestion multi-appartements ----------
def _read_apartments_csv() -> pd.DataFrame:
    """Lit apartments.csv (séparateur ; ou ,) et retourne colonnes normalisées slug/name."""
    try:
        if not os.path.exists(APARTMENTS_CSV):
            return pd.DataFrame(columns=["slug", "name"])
        raw = _load_file_bytes(APARTMENTS_CSV)
        df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame(columns=["slug", "name"])

        # Normalisation
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "slug" not in df.columns:
            df["slug"] = ""
        if "name" not in df.columns:
            df["name"] = ""

        df["slug"] = (
            df["slug"].astype(str)
            .str.replace("\ufeff", "", regex=False)
            .str.strip()
            .str.replace(" ", "-", regex=False)
            .str.replace("_", "-", regex=False)
            .str.lower()
        )
        df["name"] = df["name"].astype(str).str.replace("\ufeff", "", regex=False).str.strip()

        df = df[(df["slug"] != "") & (df["name"] != "")]
        df = df.drop_duplicates(subset=["slug"], keep="first")
        return df[["slug", "name"]]
    except Exception:
        return pd.DataFrame(columns=["slug", "name"])

def _current_apartment() -> dict | None:
    """Retourne l’appartement courant depuis la session."""
    slug = st.session_state.get("apt_slug", "")
    name = st.session_state.get("apt_name", "")
    if slug and name:
        return {"slug": slug, "name": name}
    return None

def _select_apartment_sidebar() -> bool:
    """
    Affiche le sélecteur d'appartement (sidebar).
    Retourne True si la sélection a changé (le caller fera st.rerun()).
    """
    st.sidebar.markdown("### Appartement")
    apts = _read_apartments_csv()
    if apts.empty:
        st.sidebar.warning("Aucun appartement trouvé dans apartments.csv")
        return False

    options = apts["slug"].tolist()
    labels = {r["slug"]: r["name"] for _, r in apts.iterrows()}

    default_idx = 0
    if "apt_slug" in st.session_state and st.session_state["apt_slug"] in options:
        default_idx = options.index(st.session_state["apt_slug"])

    slug = st.sidebar.selectbox(
        "Choisir un appartement",
        options=options,
        index=default_idx,
        format_func=lambda s: labels.get(s, s),
        key="apt_slug_selectbox",
    )
    name = labels.get(slug, slug)

    changed = (slug != st.session_state.get("apt_slug", "") or name != st.session_state.get("apt_name", ""))

    # Mémorise et prépare les fichiers dédiés à l'appartement
    st.session_state["apt_slug"] = slug
    st.session_state["apt_name"] = name
    st.session_state["CSV_RESERVATIONS"] = f"reservations_{slug}.csv"
    st.session_state["CSV_PLATEFORMES"]  = f"plateformes_{slug}.csv"

    # Ajoute un petit bouton d’impression dans la sidebar
    try:
        print_buttons()
    except Exception:
        pass

    return changed

def _paths_for_active_apartment():
    """Retourne les chemins CSV spécifiques à l’appartement actif (ou défaut)."""
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_pal = st.session_state.get("CSV_PLATEFORMES",  CSV_PLATEFORMES)
    return csv_res, csv_pal

def _load_data_for_active_apartment():
    """Charge df/palette pour l’appartement actif via les chemins en session."""
    csv_res, csv_pal = _paths_for_active_apartment()
    try:
        return charger_donnees(csv_res, csv_pal)
    except TypeError:
        # Compat backward si charger_donnees sans args dans d'anciennes versions
        return charger_donnees(CSV_RESERVATIONS, CSV_PLATEFORMES)
    except Exception:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE.copy()

# ============================== PARTIE 3 — Vues principales ==============================
from calendar import monthrange

# ---------- Accueil ----------
    apt = _current_apartment)


# ---------- Réservations (liste + filtres) ----------
def vue_reservations(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")

    years_avail = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1, 12 + 1))
    plats_avail = sorted(
        dfa["plateforme"].dropna().astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist()
    )

    c1, c2, c3, c4 = st.columns(4)
    year = c1.selectbox("Année", ["Toutes"] + years_avail, index=0, key="res_year")
    month = c2.selectbox("Mois", ["Tous"] + months_avail, index=0, key="res_month")
    plat = c3.selectbox("Plateforme", ["Toutes"] + plats_avail, index=0, key="res_plat")
    pay_filter = c4.selectbox("Paiement", ["Tous", "Payé uniquement", "Non payé uniquement"], index=0, key="res_pay")

    data = dfa.copy()
    if year != "Toutes":
        data = data[data["date_arrivee_dt"].dt.year == int(year)]
    if month != "Tous":
        data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]
    if pay_filter == "Payé uniquement":
        data = data[_to_bool_series(data["paye"]) == True]
    elif pay_filter == "Non payé uniquement":
        data = data[_to_bool_series(data["paye"]) == False]

    brut = float(pd.to_numeric(data["prix_brut"], errors="coerce").fillna(0).sum())
    net = float(pd.to_numeric(data["prix_net"], errors="coerce").fillna(0).sum())
    base = float(pd.to_numeric(data["base"], errors="coerce").fillna(0).sum())
    nuits = int(pd.to_numeric(data["nuitees"], errors="coerce").fillna(0).sum())
    adr = (net / nuits) if nuits > 0 else 0.0
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

    order_idx = pd.to_datetime(data["date_arrivee"], errors="coerce").sort_values(ascending=False).index
    data = data.loc[order_idx]
    st.dataframe(
        data.drop(columns=["date_arrivee_dt"]),
        use_container_width=True
    )


# ---------- Ajouter ----------
def vue_ajouter(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter une réservation — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

    with st.form("form_add_resa", clear_on_submit=True):
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
                csv_res, _ = _paths_for_active_apartment()
                if sauvegarder_donnees(df2, csv_res):
                    st.success(f"Réservation pour {nom} ajoutée.")
                    st.rerun()


# ---------- Modifier / Supprimer ----------
def vue_modifier(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client', '')} ({r.get('date_arrivee', '')})" for i, r in df_sorted.iterrows()]
    sel = st.selectbox("Sélectionnez une réservation", options=options, index=None, key="mod_select")

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
            arrivee = st.date_input("Arrivée", value=row.get("date_arrivee"))
            depart = st.date_input("Départ", value=row.get("date_depart"))
        with c2:
            palette_keys = list(palette.keys()) or ["Booking"]
            try:
                plat_idx = palette_keys.index(row.get("plateforme")) if row.get("plateforme") in palette_keys else 0
            except Exception:
                plat_idx = 0
            plat = st.selectbox("Plateforme", options=palette_keys, index=plat_idx, key=f"plat_{original_idx}")
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))
            brut = float(pd.to_numeric(row.get("prix_brut"), errors="coerce") or 0)
            commissions = float(pd.to_numeric(row.get("commissions"), errors="coerce") or 0)
            frais_cb = float(pd.to_numeric(row.get("frais_cb"), errors="coerce") or 0)
            menage = float(pd.to_numeric(row.get("menage"), errors="coerce") or 0)
            taxes = float(pd.to_numeric(row.get("taxes_sejour"), errors="coerce") or 0)
            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=brut, key=f"brut_{original_idx}")
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=commissions, key=f"com_{original_idx}")
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=frais_cb, key=f"cb_{original_idx}")
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=menage, key=f"men_{original_idx}")
            taxes = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=taxes, key=f"tax_{original_idx}")

        b1, b2 = st.columns([0.7, 0.3])
        if b1.form_submit_button("💾 Enregistrer", key=f"save_{original_idx}"):
            for k, v in {
                "nom_client": nom, "email": email, "telephone": tel, "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye, "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes
            }.items():
                df.loc[original_idx, k] = v
            csv_res, _ = _paths_for_active_apartment()
            if sauvegarder_donnees(df, csv_res):
                st.success("Modifié ✅")
                st.rerun()

        if b2.form_submit_button("🗑️ Supprimer", key=f"del_{original_idx}"):
            df2 = df.drop(index=original_idx)
            csv_res, _ = _paths_for_active_apartment()
            if sauvegarder_donnees(df2, csv_res):
                st.warning("Supprimé.")
                st.rerun()


# ---------- Plateformes & couleurs ----------
def vue_plateformes(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes & couleurs — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

    # Plateformes existantes (df + palette)
    plats_from_df = sorted(
        df.get("plateforme", pd.Series([], dtype=str))
          .astype(str).str.strip()
          .replace({"nan": ""})
          .dropna().unique().tolist()
    )
    all_plats = sorted(set(list(palette.keys()) + plats_from_df))
    base = pd.DataFrame({
        "plateforme": all_plats,
        "couleur": [palette.get(p, "#666666") for p in all_plats],
    })

    HAS_COLORCOL = hasattr(getattr(st, "column_config", object), "ColorColumn")
    if HAS_COLORCOL:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorColumn("Couleur (hex)"),
        }
        help_txt = None
    else:
        col_cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn(
                "Couleur (hex) — ex: #1e90ff",
                validate=r"^#([0-9A-Fa-f]{6})$",
                width="small",
            ),
        }
        help_txt = "Aperçu ci-dessous. Ta version de Streamlit ne propose pas le sélecteur couleur natif."

    edited = st.data_editor(
        base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config=col_cfg,
        key="palette_editor_main",
    )

    # Aperçu si pas de ColorColumn
    if not HAS_COLORCOL and not edited.empty:
        st.caption(help_txt or "")
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
    if c1.button("💾 Enregistrer la palette", key="save_palette_btn_main"):
        try:
            to_save = edited.copy()
            to_save["plateforme"] = to_save["plateforme"].astype(str).str.strip()
            to_save["couleur"] = to_save["couleur"].astype(str).str.strip()
            to_save = to_save[to_save["plateforme"] != ""].drop_duplicates(subset=["plateforme"])
            if not HAS_COLORCOL:
                ok = to_save["couleur"].str.match(r"^#([0-9A-Fa-f]{6})$")
                to_save.loc[~ok, "couleur"] = "#666666"
            # Chemin palettes de l’appartement actif
            _, csv_pal = _paths_for_active_apartment()
            to_save.to_csv(csv_pal, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c2.button("↩️ Restaurer palette par défaut", key="restore_palette_btn_main"):
        try:
            _, csv_pal = _paths_for_active_apartment()
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme", "couleur"]).to_csv(
                csv_pal, sep=";", index=False, encoding="utf-8", lineterminator="\n"
            )
            st.success("Palette par défaut restaurée.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c3.button("🔄 Recharger", key="reload_palette_btn_main"):
        st.cache_data.clear()
        st.rerun()

# ============================== PARTIE 4 — Vues (calendrier, rapport, SMS, export, etc.) ==============================
# ---------- Calendrier ----------
def vue_calendrier(df: pd.DataFrame, palette: dict):
    from calendar import monthrange, Calendar

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier (grille mensuelle) — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

    dfv = df.dropna(subset=['date_arrivee', 'date_depart']).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    years = sorted(
        pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(),
        reverse=True
    )
    annee = st.selectbox("Année", options=years if len(years) else [today.year], index=0, key="cal_year")
    mois = st.selectbox("Mois", options=list(range(1, 13)), index=today.month - 1, key="cal_month")

    # Header jours
    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div><div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True
    )

    def day_resas(d):
        mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
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
                        color = palette.get(r.get('plateforme'), '#888')
                        name = str(r.get('nom_client') or '')[:22]
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
            rows = rows[rows["plateforme"] == plat]

        brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
        net = float(pd.to_numeric(rows["prix_net"], errors="coerce").fillna(0).sum())
        nuits = int(pd.to_numeric(rows["nuitees"], errors="coerce").fillna(0).sum())

        html = f"""
        <div class='glass kpi-line'>
          <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
          <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
          <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
        </div>
        """.replace(",", " ")
        st.markdown(html, unsafe_allow_html=True)
        st.dataframe(
            rows[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "paye", "pays"]],
            use_container_width=True
        )


# ---------- Rapport ----------
def vue_rapport(df: pd.DataFrame, palette: dict):
    from calendar import monthrange

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📊 Rapport — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

    if df is None or df.empty:
        st.info("Aucune donnée.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    dfa["date_depart_dt"] = pd.to_datetime(dfa["date_depart"], errors="coerce")

    years_avail = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    months_avail = list(range(1, 13))
    plats_avail = sorted(dfa["plateforme"].astype(str).str.strip().replace({"": np.nan}).dropna().unique().tolist())
    dfa["_pays"] = dfa["pays"].replace("", np.nan)
    dfa["_pays"] = dfa["_pays"].fillna(dfa["telephone"].apply(_phone_country)).replace("", "Inconnu")
    pays_avail = sorted(dfa["_pays"].unique().tolist())
    if "France" in pays_avail:
        pays_avail.remove("France")
        pays_avail = ["France"] + pays_avail

    c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1.2, 1.2])
    year = c1.selectbox("Année", ["Toutes"] + years_avail, index=0, key="rep_year")
    month = c2.selectbox("Mois", ["Tous"] + months_avail, index=0, key="rep_month")
    plat = c3.selectbox("Plateforme", ["Toutes"] + plats_avail, index=0, key="rep_plat")
    payf = c4.selectbox("Pays", ["Tous"] + pays_avail, index=0, key="rep_country")
    metric = c5.selectbox("Métrique", ["prix_brut", "prix_net", "base", "charges", "menage", "taxes_sejour", "nuitees"], index=1, key="rep_metric")

    data = dfa.copy()
    data["pays"] = data["_pays"]
    if year != "Toutes":
        data = data[data["date_arrivee_dt"].dt.year == int(year)]
    if month != "Tous":
        data = data[data["date_arrivee_dt"].dt.month == int(month)]
    if plat != "Toutes":
        data = data[data["plateforme"].astype(str).str.strip() == str(plat).strip()]
    if payf != "Tous":
        data = data[data["pays"] == payf]

    if data.empty:
        st.warning("Aucune donnée après filtres.")
        return

    # ===== Occupation par mois =====
    st.markdown("---")
    st.subheader("📅 Taux d'occupation")

    data["mois"] = data["date_arrivee_dt"].dt.to_period("M").astype(str)
    data["nuitees"] = (data["date_depart_dt"] - data["date_arrivee_dt"]).dt.days

    occ_mois = data.groupby(["mois", "plateforme"], as_index=False)["nuitees"].sum()
    occ_mois.rename(columns={"nuitees": "nuitees_occupees"}, inplace=True)

    def jours_dans_mois(periode_str):
        annee, mois = map(int, periode_str.split("-"))
        return monthrange(annee, mois)[1]

    occ_mois["jours_dans_mois"] = occ_mois["mois"].apply(jours_dans_mois)
    occ_mois["taux_occupation"] = (occ_mois["nuitees_occupees"] / occ_mois["jours_dans_mois"]) * 100

    col_plat, col_export = st.columns([1, 1])
    plat_occ = col_plat.selectbox("Filtrer par plateforme (occupation)", ["Toutes"] + plats_avail, index=0, key="occ_plat")

    occ_filtered = occ_mois.copy()
    if plat_occ != "Toutes":
        occ_filtered = occ_filtered[occ_filtered["plateforme"] == plat_occ]

    filtered_nuitees = pd.to_numeric(occ_filtered["nuitees_occupees"], errors="coerce").fillna(0).sum()
    filtered_jours = pd.to_numeric(occ_filtered["jours_dans_mois"], errors="coerce").fillna(0).sum()
    taux_global_filtered = (filtered_nuitees / filtered_jours) * 100 if filtered_jours > 0 else 0

    st.markdown(
        f"""
        <div class='glass kpi-line'>
            <span class='chip'><small>Taux global</small><br><strong>{taux_global_filtered:.1f}%</strong></span>
            <span class='chip'><small>Nuitées occupées</small><br><strong>{int(filtered_nuitees)}</strong></span>
            <span class='chip'><small>Jours disponibles</small><br><strong>{int(filtered_jours)}</strong></span>
            <span class='chip'><small>Pays filtré</small><br><strong>{payf if payf!='Tous' else 'Tous'}</strong></span>
        </div>
        """,
        unsafe_allow_html=True
    )

    occ_export = occ_filtered[["mois", "plateforme", "nuitees_occupees", "jours_dans_mois", "taux_occupation"]].copy()
    occ_export = occ_export.sort_values(["mois", "plateforme"], ascending=[False, True])

    csv_occ = occ_export.to_csv(index=False).encode("utf-8")
    col_export.download_button("⬇️ Exporter occupation (CSV)", data=csv_occ, file_name="taux_occupation.csv", mime="text/csv")
    xlsx_occ, _ = _df_to_xlsx_bytes(occ_export, "Taux d'occupation")
    if xlsx_occ:
        col_export.download_button(
            "⬇️ Exporter occupation (XLSX)",
            data=xlsx_occ,
            file_name="taux_occupation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.dataframe(occ_export.assign(taux_occupation=lambda x: x["taux_occupation"].round(1)), use_container_width=True)

    # ===== Comparaison entre années =====
    st.markdown("---")
    st.subheader("📊 Comparaison des taux d'occupation par année")

    data["annee"] = data["date_arrivee_dt"].dt.year
    occ_annee = data.groupby(["annee", "plateforme"])["nuitees"].sum().reset_index()
    occ_annee.rename(columns={"nuitees": "nuitees_occupees"}, inplace=True)

    def jours_dans_annee(annee):
        return 366 if (annee % 4 == 0 and annee % 100 != 0) or (annee % 400 == 0) else 365

    occ_annee["jours_dans_annee"] = occ_annee["annee"].apply(jours_dans_annee)
    occ_annee["taux_occupation"] = (occ_annee["nuitees_occupees"] / occ_annee["jours_dans_annee"]) * 100

    annees_comparaison = st.multiselect(
        "Sélectionner les années à comparer",
        options=sorted(occ_annee["annee"].unique()),
        default=sorted(occ_annee["annee"].unique())[-2:] if occ_annee["annee"].nunique() >= 2 else sorted(occ_annee["annee"].unique()),
        key="rep_years_compare"
    )

    if annees_comparaison:
        occ_comparaison = occ_annee[occ_annee["annee"].isin(annees_comparaison)].copy()
        try:
            chart_comparaison = alt.Chart(occ_comparaison).mark_bar().encode(
                x=alt.X("annee:N", title="Année"),
                y=alt.Y("taux_occupation:Q", title="Taux d'occupation (%)", scale=alt.Scale(domain=[0, 100])),
                color=alt.Color("plateforme:N", title="Plateforme"),
                tooltip=["annee", "plateforme", alt.Tooltip("taux_occupation:Q", format=".1f")]
            ).properties(height=400)
            st.altair_chart(chart_comparaison, use_container_width=True)
        except Exception as e:
            st.warning(f"Graphique de comparaison indisponible : {e}")

        st.dataframe(
            occ_comparaison[["annee", "plateforme", "nuitees_occupees", "taux_occupation"]]
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
            tooltip=["mois", "plateforme", alt.Tooltip(f"{metric}:Q", format=",.2f")]
        )
        st.altair_chart(chart.properties(height=420), use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique indisponible : {e}")

    # ===== Analyse par pays (avec filtre année dédié) =====
    st.markdown("---")
    st.subheader("🌍 Analyse par pays")

    years_pays = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
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

    nb_pays = int(agg_pays["pays"].nunique())
    top_pays = agg_pays.iloc[0]["pays"] if not agg_pays.empty else "—"
    st.markdown(
        f"""
        <div class='glass kpi-line'>
          <span class='chip'><small>Année filtrée</small><br><strong>{year_pays}</strong></span>
          <span class='chip'><small>Pays distincts</small><br><strong>{nb_pays}</strong></span>
          <span class='chip'><small>Total réservations</small><br><strong>{total_res}</strong></span>
          <span class='chip'><small>Top pays (CA net)</small><br><strong>{top_pays}</strong></span>
        </div>
        """,
        unsafe_allow_html=True
    )

    disp = agg_pays.copy()
    num_cols = [
        "reservations", "nuitees", "prix_brut", "prix_net",
        "menage", "taxes_sejour", "charges", "base",
        "ADR_net", "part_revenu_%"
    ]
    for c in num_cols:
        disp[c] = pd.to_numeric(disp[c], errors="coerce")

    disp["reservations"] = disp["reservations"].fillna(0).astype("int64")
    disp["pays"] = disp["pays"].astype(str).replace({"nan": "Inconnu", "": "Inconnu"})

    disp["prix_brut"] = disp["prix_brut"].round(2)
    disp["prix_net"] = disp["prix_net"].round(2)
    disp["ADR_net"] = disp["ADR_net"].round(2)
    disp["part_revenu_%"] = disp["part_revenu_%"].round(1)

    order_cols = [
        "pays", "reservations", "nuitees", "prix_brut", "prix_net",
        "charges", "menage", "taxes_sejour", "base", "ADR_net", "part_revenu_%"
    ]
    disp = disp[[c for c in order_cols if c in disp.columns]]

    st.dataframe(disp, use_container_width=True)

    try:
        topN = st.slider("Afficher les N premiers pays (par CA net)", min_value=3, max_value=20, value=12, step=1, key="pays_topn")
        chart_pays = alt.Chart(agg_pays.head(topN)).mark_bar().encode(
            x=alt.X("pays:N", sort="-y", title="Pays"),
            y=alt.Y("prix_net:Q", title="CA net (€)"),
            tooltip=[
                "pays",
                alt.Tooltip("reservations:Q", title="Réservations"),
                alt.Tooltip("nuitees:Q", title="Nuitées"),
                alt.Tooltip("ADR_net:Q", title="ADR net", format=",.2f"),
                alt.Tooltip("part_revenu_%:Q", title="Part du revenu (%)", format=".1f"),
            ],
        ).properties(height=420)
        st.altair_chart(chart_pays, use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique 'Analyse par pays' indisponible : {e}")

    # ===== Évolution du taux d'occupation =====
    st.markdown("---")
    st.subheader("📈 Évolution du taux d'occupation")
    try:
        chart_occ = alt.Chart(occ_filtered).mark_line(point=True).encode(
            x=alt.X("mois:N", sort=None, title="Mois"),
            y=alt.Y("taux_occupation:Q", title="Taux d'occupation (%)", scale=alt.Scale(domain=[0, 100])),
            color=alt.Color("plateforme:N", title="Plateforme"),
            tooltip=["mois", "plateforme", alt.Tooltip("taux_occupation:Q", format=".1f")]
        )
        st.altair_chart(chart_occ.properties(height=420), use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique du taux d'occupation indisponible : {e}")


# ---------- Helpers SMS ----------
def _copy_button(label: str, payload: str, key: str):
    st.text_area("Aperçu", payload, height=260, key=f"ta_{key}")
    st.caption("Sélectionnez puis copiez (Ctrl/Cmd+C).")

def _google_form_prefill(res_id, nom, phone, arr, dep):
    # Tu utilises un lien court qui redirige vers le formulaire prérempli.
    # Si tu veux repasser au lien long Google Forms prérempli, remplace ici.
    return FORM_SHORT_URL


# ---------- SMS / WhatsApp ----------
def vue_sms(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS & WhatsApp — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

    # Pré-arrivée
    st.subheader("🛬 Pré-arrivée (arrivées J+1)")
    target_arrivee = st.date_input("Arrivées du", date.today() + timedelta(days=1), key="pre_date")
    pre = df.dropna(subset=["telephone", "nom_client", "date_arrivee"]).copy()
    pre["date_arrivee"] = _to_date(pre["date_arrivee"])
    pre["date_depart"] = _to_date(pre["date_depart"])
    sms_sent = _to_bool_series(pre["sms_envoye"])
    pre = pre[(pre["date_arrivee"] == target_arrivee) & (~sms_sent)]

    if pre.empty:
        st.info("Aucun client à contacter.")
    else:
        pre["_rowid"] = pre.index
        pre = pre.sort_values("date_arrivee").reset_index(drop=True)
        opts = [f"{i}: {r['nom_client']} ({r['telephone']})" for i, r in pre.iterrows()]
        pick = st.selectbox("Client (pré-arrivée)", options=opts, index=None, key="pre_pick")

        if pick:
            i = int(pick.split(":")[0])
            r = pre.loc[i]
            link_form = _google_form_prefill(
                r.get("res_id"), r.get("nom_client"), _format_phone_e164(r.get("telephone")),
                r.get("date_arrivee"), r.get("date_depart")
            )

            # Message FR+EN (nouvelle version fournie)
            msg = (
                f"{apt_name.upper()}\n"
                f"Plateforme : {r.get('plateforme', 'Booking')}\n"
                f"Arrivée : {r['date_arrivee'].strftime('%d/%m/%Y')}  Départ : {(r['date_depart'].strftime('%d/%m/%Y') if pd.notna(r['date_depart']) else '')}  Nuitées : {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}\n\n"
                f"Bonjour {r.get('nom_client')}\n"
                "Bienvenue chez nous ! \n\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre réception, nous vous demandons de bien vouloir remplir la fiche que vous trouverez en cliquant sur le lien suivant : \n"
                f"{link_form}\n\n"
                "Un parking est à votre disposition sur place.\n\n"
                "Le check-in se fait à partir de 14:00 h et le check-out avant 11:00 h. \n\n"
                "Vous trouverez des consignes à bagages dans chaque quartier, à Nice. \n\n"
                "Nous vous souhaitons un excellent voyage et nous nous réjouissons de vous rencontrer très bientôt. \n\n"
                "Annick & Charley \n\n"
                "****** \n\n"
                "Welcome to our establishment! \n\n"
                "We are delighted to welcome you soon to Nice. In order to organize your reception as efficiently as possible, we kindly ask you to fill out the form that you will find by clicking on the following link: \n"
                f"{link_form}\n\n"
                "Parking is available on site.\n\n"
                "Check-in is from 2:00 p.m. and check-out is before 11:00 a.m. \n\n"
                "You will find luggage storage facilities in every district of Nice. \n\n"
                "We wish you a pleasant journey and look forward to meeting you very soon.\n\n"
                "Annick & Charley"
            )
            enc = quote(msg)
            e164 = _format_phone_e164(r["telephone"])
            wa = re.sub(r"\D", "", e164)
            _copy_button("📋 Copier le message", msg, key=f"pre_{i}")

            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")

            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                csv_res, _ = _paths_for_active_apartment()
                if sauvegarder_donnees(df, csv_res):
                    st.success("Marqué ✅")
                    st.rerun()

    # Post-départ
    st.markdown("---")
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = df.dropna(subset=["telephone", "nom_client", "date_depart"]).copy()
    post["date_depart"] = _to_date(post["date_depart"])
    post_sent = _to_bool_series(post["post_depart_envoye"])
    post = post[(post["date_depart"] == target_depart) & (~post_sent)]

    if post.empty:
        st.info("Aucun message à envoyer.")
    else:
        post["_rowid"] = post.index
        post = post.sort_values("date_depart").reset_index(drop=True)
        opts2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=opts2, index=None, key="post_pick")

        if pick2:
            j = int(pick2.split(":")[0])
            r2 = post.loc[j]
            name = str(r2.get("nom_client") or "").strip()
            msg2 = (
                f"Bonjour {name},\n\n"
                "Un grand merci d'avoir choisi notre appartement pour votre séjour.\n"
                "Nous espérons que vous avez passé un moment agréable.\n"
                "Si vous souhaitez revenir explorer encore un peu la ville, notre porte vous sera toujours grande ouverte.\n\n"
                "Au plaisir de vous accueillir à nouveau.\n\n"
                "Annick & Charley\n"
                f"\nHello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n"
                "We hope you had a great time — our door is always open if you want to come back.\n\n"
                "Annick & Charley"
            )
            enc2 = quote(msg2)
            e164b = _format_phone_e164(r2["telephone"])
            wab = re.sub(r"\D", "", e164b)
            _copy_button("📋 Copier le message", msg2, key=f"post_{j}")

            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")

            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                df.loc[r2["_rowid"], "post_depart_envoye"] = True
                csv_res, _ = _paths_for_active_apartment()
                if sauvegarder_donnees(df, csv_res):
                    st.success("Marqué ✅")
                    st.rerun()


# ---------- Export ICS ----------
def vue_export_ics(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📆 Export ICS — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

    if df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    years = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique(), reverse=True)
    year = st.selectbox("Année (arrivées)", years if years else [date.today().year], index=0, key="ics_year")
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat = st.selectbox("Plateforme", plats, index=0, key="ics_plat")

    data = dfa[dfa["date_arrivee_dt"].dt.year == int(year)].copy()
    if plat != "Tous":
        data = data[data["plateforme"] == plat]

    if data.empty:
        st.warning("Rien à exporter.")
        return

    miss = data["ical_uid"].isna() | (data["ical_uid"].astype(str).str.strip() == "")
    if miss.any():
        data.loc[miss, "ical_uid"] = data.loc[miss].apply(build_stable_uid, axis=1)

    nowstamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    def _fmt(d):
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, date):
            return f"{d.year:04d}{d.month:02d}{d.day:02d}"
        try:
            d2 = pd.to_datetime(d, errors="coerce")
            return d2.strftime("%Y%m%d")
        except Exception:
            return ""

    def _esc(s):
        if s is None:
            return ""
        return str(s).replace("\\", "\\\\").replace("\n", "\\n").replace(",", "\\,").replace(";", "\\;")

    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Villa Tobias//Reservations//FR", "CALSCALE:GREGORIAN"]
    for _, r in data.iterrows():
        dt_a = pd.to_datetime(r["date_arrivee"], errors="coerce")
        dt_d = pd.to_datetime(r["date_depart"], errors="coerce")
        if pd.isna(dt_a) or pd.isna(dt_d):
            continue

        summary = f"{apt_name} — {r.get('nom_client', 'Sans nom')}"
        if r.get("plateforme"):
            summary += f" ({r['plateforme']})"

        desc = "\n".join([
            f"Client: {r.get('nom_client', '')}",
            f"Téléphone: {r.get('telephone', '')}",
            f"Nuitées: {int(pd.to_numeric(r.get('nuitees'), errors='coerce') or 0)}",
            f"Prix brut: {float(pd.to_numeric(r.get('prix_brut'), errors='coerce') or 0):.2f} €",
            f"res_id: {r.get('res_id', '')}",
        ])

        lines += [
            "BEGIN:VEVENT",
            f"UID:{r['ical_uid']}",
            f"DTSTAMP:{nowstamp}",
            f"DTSTART;VALUE=DATE:{_fmt(dt_a)}",
            f"DTEND;VALUE=DATE:{_fmt(dt_d)}",
            f"SUMMARY:{_esc(summary)}",
            f"DESCRIPTION:{_esc(desc)}",
            "TRANSP:OPAQUE",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    ics = "\r\n".join(lines) + "\r\n"
    st.download_button(
        "📥 Télécharger .ics",
        data=ics.encode("utf-8"),
        file_name=f"reservations_{year}.ics",
        mime="text/calendar",
        key="dl_ics"
    )


# ---------- Google Form / Sheet ----------
def vue_google_sheet(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Fiche d'arrivée / Google Sheet — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

    st.markdown(f"**Lien court à partager** : {FORM_SHORT_URL}")
    st.markdown(
        f'<iframe src="{GOOGLE_FORM_VIEW}" width="100%" height="900" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )
    st.markdown("---")
    st.subheader("Feuille Google intégrée")
    st.markdown(
        f'<iframe src="{GOOGLE_SHEET_EMBED_URL}" width="100%" height="700" frameborder="0"></iframe>',
        unsafe_allow_html=True
    )
    st.markdown("---")
    st.subheader("Réponses (CSV publié)")
    try:
        rep = pd.read_csv(GOOGLE_SHEET_PUBLISHED_CSV)
        show_email = st.checkbox("Afficher les colonnes d'email (si présentes)", value=False, key="show_email_form")
        if not show_email:
            mask_cols = [c for c in rep.columns if "mail" in c.lower() or "email" in c.lower()]
            rep_display = rep.drop(columns=mask_cols, errors="ignore")
        else:
            rep_display = rep
        st.dataframe(rep_display, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")


# ---------- Clients ----------
def vue_clients(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Liste des clients — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

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


# ---------- ID ----------
def vue_id(df: pd.DataFrame, palette: dict):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🆔 Identifiants des réservations — {apt_name}")
    try:
        print_buttons()
    except Exception:
        pass

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
    st.header("## ⚙️ Paramètres")
    st.subheader(apt_name)
    try:
        print_buttons()
    except Exception:
        pass

    st.caption("Sauvegarde, restauration, cache, import manuel, diagnostic et écrasement apartments.csv.")

    # --- Sauvegarde (exports)
    st.markdown("### 💾 Sauvegarde (exports)")
    try:
        out = ensure_schema(df).copy()
        out["pays"] = out["telephone"].apply(_phone_country)
        for col in ["date_arrivee", "date_depart"]:
            out[col] = pd.to_datetime(out[col], errors="coerce").dt.strftime("%d/%m/%Y")
        csv_bytes = out.to_csv(sep=";", index=False).encode("utf-8")
    except Exception:
        csv_bytes = b""

    c1, c2 = st.columns(2)
    csv_res, csv_pal = _paths_for_active_apartment()
    c1.download_button("⬇️ Exporter réservations (CSV)", data=csv_bytes,
                       file_name=os.path.basename(csv_res), mime="text/csv", key="dl_res_csv_settings")

    try:
        out_xlsx = ensure_schema(df).copy()
        out_xlsx["pays"] = out_xlsx["telephone"].apply(_phone_country)
        for col in ["date_arrivee", "date_depart"]:
            out_xlsx[col] = pd.to_datetime(out_xlsx[col], errors="coerce").dt.strftime("%d/%m/%Y")
        xlsx_bytes, _ = _df_to_xlsx_bytes(out_xlsx, sheet_name="Reservations")
    except Exception:
        xlsx_bytes = None

    c2.download_button(
        "⬇️ Exporter réservations (XLSX)",
        data=xlsx_bytes or b"",
        file_name=os.path.splitext(os.path.basename(csv_res))[0] + ".xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(xlsx_bytes is None),
        key="dl_res_xlsx_settings"
    )

    # --- Restauration (CSV/XLSX) réservations & plateformes
    st.markdown("### ♻️ Restauration (remplacer les données)")

    up_res = st.file_uploader("Restaurer RÉSERVATIONS (CSV ou XLSX)", type=["csv", "xlsx"], key="restore_res_upl")
    if up_res is not None:
        try:
            if up_res.name.lower().endswith(".xlsx"):
                tmp = pd.read_excel(up_res, dtype=str)
            else:
                raw = up_res.read()
                tmp = _detect_delimiter_and_read(raw)
            new_df = ensure_schema(tmp)
            # on écrit le fichier de l'appartement courant
            new_df2 = new_df.copy()
            for col in ["date_arrivee", "date_depart"]:
                new_df2[col] = pd.to_datetime(new_df2[col], errors="coerce").dt.strftime("%d/%m/%Y")
            new_df2.to_csv(csv_res, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success(f"Réservations restaurées → {os.path.basename(csv_res)}")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur restauration réservations : {e}")

    up_pal = st.file_uploader("Restaurer PALETTES (CSV)", type=["csv"], key="restore_pal_upl")
    if up_pal is not None:
        try:
            rawp = up_pal.read()
            pal_df = _detect_delimiter_and_read(rawp)
            pal_df.columns = pal_df.columns.astype(str).str.strip().str.lower()
            if not {"plateforme", "couleur"}.issubset(pal_df.columns):
                raise ValueError("Le fichier doit contenir les colonnes 'plateforme' et 'couleur'.")
            pal_df = pal_df[["plateforme", "couleur"]]
            pal_df.to_csv(csv_pal, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success(f"Palette restaurée → {os.path.basename(csv_pal)}")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur restauration palettes : {e}")

    # --- Vider cache
    st.markdown("### 🧹 Vider le cache")
    if st.button("Vider le cache & recharger", key="clear_cache_btn_settings"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    # --- Import manuel immédiat (réservations) : remplace tout de suite
    st.markdown("### ⛑️ Import manuel (remplacement immédiat)")
    up_man = st.file_uploader("Choisir un fichier (CSV ou XLSX)", type=["csv", "xlsx"], key="import_manual")
    if up_man is not None:
        try:
            if up_man.name.lower().endswith(".xlsx"):
                tmp = pd.read_excel(up_man, dtype=str)
            else:
                raw = up_man.read()
                tmp = _detect_delimiter_and_read(raw)
            new_df = ensure_schema(tmp)
            save_df = new_df.copy()
            for col in ["date_arrivee", "date_depart"]:
                save_df[col] = pd.to_datetime(save_df[col], errors="coerce").dt.strftime("%d/%m/%Y")
            save_df.to_csv(csv_res, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Import manuel effectué — données remplacées.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur import manuel : {e}")

    # --- Diagnostics
    st.markdown("### 🔎 Diagnostics")
    st.write("**Fichiers actifs**")
    st.code(f"reservations : {csv_res}\nplateformes : {csv_pal}", language="text")
    st.write("**Aperçu réservations (5)**")
    st.dataframe(df.head(5), use_container_width=True)

    # --- Écraser apartments.csv (outil secours)
    st.markdown("### 🧰 Écraser apartments.csv")
    default_csv = "slug,name\nvilla-tobias,Villa Tobias\nle-turenne,Le Turenne\n"
    txt = st.text_area("Contenu apartments.csv", value=default_csv, height=140, key="force_apts_area_settings")
    if st.button("🧰 Écraser apartments.csv (outil secours)", key="force_apts_btn_settings"):
        try:
            with open(APARTMENTS_CSV, "w", encoding="utf-8", newline="") as f:
                f.write(txt.strip() + "\n")
            st.cache_data.clear()
            st.success("apartments.csv écrasé ✅ — rechargement…")
            st.rerun()
        except Exception as e:
            st.error(f"Impossible d'écrire apartments.csv : {e}")


# ============================== Chargeur data par appartement ==============================
def _load_data_for_active_apartment():
    """
    Charge (df, palette) pour l'appartement actif.
    Utilise les chemins renvoyés par _paths_for_active_apartment().
    """
    csv_res, csv_pal = _paths_for_active_apartment()
    try:
        return charger_donnees(csv_res, csv_pal)
    except TypeError:
        # fallback signature ancienne
        return charger_donnees()
    except Exception:
        return pd.DataFrame(columns=BASE_COLS), DEFAULT_PALETTE.copy()


# ============================== MAIN ==============================
def main():
    # ?clear=1 pour vider le cache
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1", "true", "True", "yes"):
        try:
            st.cache_data.clear()
        except Exception:
            pass

    # Sélecteur d’appartement
    changed = _select_apartment_sidebar()
    if changed:
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    # Thème
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False, key="light_toggle")
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False, key="light_checkbox")
    apply_style(light=bool(mode_clair))

    # Titre (nom d’appart)
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    # Données
    df, palette_loaded = _load_data_for_active_apartment()
    palette = palette_loaded if palette_loaded else DEFAULT_PALETTE

    # Navigation
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
        "⚙️ Paramètres": vue_settings,
    }

    choice = st.sidebar.radio("Aller à", list(pages.keys()), key="nav_radio")
    pages[choice](df, palette)


if __name__ == "__main__":
    main()