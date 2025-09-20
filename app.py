# ================================================================
# ✨ Villa Tobias — Gestion des Réservations (Streamlit)
# Multi-appartements, SMS, calendrier, rapports, paramètres
# ================================================================

import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
import re
import os
from datetime import datetime, date, timedelta
from urllib.parse import quote
from io import BytesIO
import base64
from calendar import monthrange

# ============================== CONSTANTES ==============================
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES = "plateformes.csv"
CSV_APARTMENTS = "apartments.csv"

FORM_SHORT_URL = "https://urlr.me/kZuH94"  # lien court Google Form
GOOGLE_FORM_VIEW = "https://docs.google.com/forms/d/e/1FAIpQLScLiaqSAY3JYriYZIk9qP75YGUyP0sxF8pzmhbIQqsSEY0jpQ/viewform?embedded=true"
GOOGLE_SHEET_EMBED_URL = "https://docs.google.com/spreadsheets/d/1qzJc0aWUpA1WcD7JgGtuCfEJ4C6J4wElu4LJPo0sMfg/edit?usp=sharing"
GOOGLE_SHEET_PUBLISHED_CSV = "https://docs.google.com/spreadsheets/d/e/2PACX-1vRANDOM/pub?gid=0&single=true&output=csv"

DEFAULT_PALETTE = {
    "Booking": "#1E90FF",
    "Airbnb": "#FF5A5F",
    "Abritel": "#32CD32",
}

# ============================== HELPERS ==============================

def _detect_delimiter_and_read(raw_bytes: bytes) -> pd.DataFrame:
    """Détecte le délimiteur ( ; , tab | ) et lit le CSV"""
    raw_str = raw_bytes.decode("utf-8", errors="ignore")
    for delim in [";", ",", "\t", "|"]:
        try:
            df = pd.read_csv(BytesIO(raw_str.encode("utf-8")), sep=delim, dtype=str)
            if df.shape[1] > 1:
                return df
        except Exception:
            continue
    return pd.DataFrame()

def _to_date(x):
    try:
        return pd.to_datetime(x, errors="coerce").date()
    except Exception:
        return pd.NaT

def _to_bool_series(s):
    return s.astype(str).str.lower().isin(["1", "true", "yes", "oui", "y", "t"])

def _format_phone_e164(phone: str) -> str:
    phone = str(phone).strip()
    if phone.startswith("00"):
        return "+" + phone[2:]
    elif phone.startswith("0"):
        return "+33" + phone[1:]
    return phone

# Mapping d’indicatifs → pays (simplifié Europe + Monde étendu)
PHONE_PREFIX_TO_COUNTRY = {
    "+33": "France",
    "+34": "Espagne",
    "+39": "Italie",
    "+41": "Suisse",
    "+49": "Allemagne",
    "+44": "Royaume-Uni",
    "+32": "Belgique",
    "+352": "Luxembourg",
    "+351": "Portugal",
    "+1": "États-Unis / Canada",
    "+7": "Russie",
    "+90": "Turquie",
    "+212": "Maroc",
    "+216": "Tunisie",
    "+213": "Algérie",
    "+81": "Japon",
    "+82": "Corée du Sud",
    "+86": "Chine",
}

def _phone_country(phone: str) -> str:
    if not phone:
        return "Inconnu"
    phone = str(phone).strip()
    if phone.startswith("00"):
        phone = "+" + phone[2:]
    for prefix, country in PHONE_PREFIX_TO_COUNTRY.items():
        if phone.startswith(prefix):
            return country
    return "Inconnu"

def _df_to_xlsx_bytes(df: pd.DataFrame, sheet_name="Feuille"):
    try:
        from openpyxl import Workbook
        from openpyxl.utils.dataframe import dataframe_to_rows
        wb = Workbook()
        ws = wb.active
        ws.title = sheet_name
        for r in dataframe_to_rows(df, index=False, header=True):
            ws.append(r)
        bio = BytesIO()
        wb.save(bio)
        return bio.getvalue(), None
    except Exception as e:
        return None, e

# ============================== STYLE ==============================

def apply_style(light: bool = False):
    css = """
    <style>
    body { font-family: Arial, sans-serif; }
    .glass { background: rgba(255,255,255,0.05); padding: 1rem; border-radius: 10px; margin: 1rem 0; }
    .chip { display:inline-block; padding:0.5rem 1rem; margin:0.2rem;
            border-radius:20px; background:#eee; font-size:0.9rem; }
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)

def print_buttons():
    c1, c2 = st.columns([0.15, 0.85])
    with c1:
        st.button("🖨️ Imprimer", key=f"print_{datetime.now().timestamp()}")

# ============================== SCHEMA & CHARGEMENT ==============================

BASE_COLS = [
    "res_id", "nom_client", "telephone", "email", "plateforme", "pays",
    "date_arrivee", "date_depart", "nuitees",
    "prix_brut", "commissions", "frais_cb", "menage", "taxes_sejour",
    "prix_net", "charges", "base", "%",
    "paye", "sms_envoye", "post_depart_envoye", "ical_uid"
]

def ensure_schema(df_in: pd.DataFrame) -> pd.DataFrame:
    """Forcer toutes les colonnes et calculer valeurs dérivées"""
    if df_in is None or df_in.empty:
        return pd.DataFrame(columns=BASE_COLS)

    df = df_in.copy()
    df.columns = df.columns.astype(str).str.strip()

    # Normalisation noms
    rename_map = {
        "Payé": "paye",
        "Client": "nom_client",
        "Plateforme": "plateforme",
        "Arrivée": "date_arrivee",
        "Départ": "date_depart",
        "Nuits": "nuitees",
        "Brut (€)": "prix_brut",
    }
    df.rename(columns=rename_map, inplace=True)

    # Colonnes manquantes
    for col in BASE_COLS:
        if col not in df.columns:
            df[col] = None

    # Nettoyage types
    df["paye"] = _to_bool_series(df["paye"])
    num_cols = ["prix_brut", "commissions", "frais_cb", "menage", "taxes_sejour", "nuitees", "charges", "base", "%"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.date
    df["date_depart"] = pd.to_datetime(df["date_depart"], errors="coerce").dt.date

    # Calcul nuitées
    mask = df["date_arrivee"].notna() & df["date_depart"].notna()
    df.loc[mask, "nuitees"] = (pd.to_datetime(df.loc[mask, "date_depart"]) -
                               pd.to_datetime(df.loc[mask, "date_arrivee"])).dt.days

    # Calcul prix net et charges
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).fillna(0.0)
    df["charges"] = (df["prix_brut"] - df["prix_net"]).fillna(0.0)
    df["base"] = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).fillna(0.0)
    df["%"] = np.where(df["prix_brut"] > 0, df["charges"] / df["prix_brut"] * 100, 0)

    # Compléter pays
    need = df["pays"].isna() | df["pays"].eq("")
    if need.any():
        df.loc[need, "pays"] = df.loc[need, "telephone"].apply(_phone_country)

    return df[BASE_COLS]

def sauvegarder_donnees(df: pd.DataFrame, path: str):
    """Sauvegarde CSV avec schéma garanti"""
    try:
        out = ensure_schema(df)
        out.to_csv(path, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

@st.cache_data(show_spinner=False)
def charger_donnees(csv_reservations=CSV_RESERVATIONS, csv_plateformes=CSV_PLATEFORMES):
    """Chargement CSV + palettes"""
    if not os.path.exists(csv_reservations):
        with open(csv_reservations, "w", encoding="utf-8") as f:
            f.write("nom_client,email,telephone,plateforme,date_arrivee,date_depart,nuitees,prix_brut\n")

    raw = open(csv_reservations, "rb").read()
    df = _detect_delimiter_and_read(raw)
    df = ensure_schema(df)

    palette = DEFAULT_PALETTE.copy()
    if os.path.exists(csv_plateformes):
        try:
            pal_df = pd.read_csv(csv_plateformes, sep=";", dtype=str)
            if {"plateforme", "couleur"}.issubset(pal_df.columns):
                palette = dict(zip(pal_df["plateforme"], pal_df["couleur"]))
        except Exception:
            pass

    return df, palette

# ============================== TABLEAUX & AFFICHAGE ==============================

def print_buttons():
    """Bouton impression universel"""
    js = """
    <script>
    function printPage(){window.print();}
    </script>
    <button onclick="printPage()">🖨️ Imprimer</button>
    """
    st.markdown(js, unsafe_allow_html=True)


def vue_accueil(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    today = date.today()
    tomorrow = today + timedelta(days=1)

    df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce").dt.date
    df["date_depart"] = pd.to_datetime(df["date_depart"], errors="coerce").dt.date

    arr_today = df[df["date_arrivee"] == today]
    dep_today = df[df["date_depart"] == today]
    arr_tmr = df[df["date_arrivee"] == tomorrow]

    col1, col2, col3 = st.columns(3)
    col1.metric("Arrivées aujourd'hui", len(arr_today))
    col2.metric("Départs aujourd'hui", len(dep_today))
    col3.metric("Arrivées demain", len(arr_tmr))

    with st.expander("📥 Arrivées aujourd'hui"):
        st.dataframe(arr_today[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees"]])

    with st.expander("📤 Départs aujourd'hui"):
        st.dataframe(dep_today[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees"]])

    with st.expander("📥 Arrivées demain"):
        st.dataframe(arr_tmr[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees"]])


def vue_reservations(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    # Filtres
    plats = ["Toutes"] + sorted(df["plateforme"].dropna().unique())
    plat = st.selectbox("Plateforme", plats, index=0)

    years = sorted(pd.to_datetime(df["date_arrivee"], errors="coerce").dt.year.dropna().unique())
    year = st.selectbox("Année", ["Toutes"] + [int(y) for y in years], index=0)

    paye_opts = ["Tous", "Payé", "Non payé"]
    paye_f = st.selectbox("Filtrer par paiement", paye_opts, index=0)

    data = df.copy()
    if plat != "Toutes":
        data = data[data["plateforme"] == plat]
    if year != "Toutes":
        data = data[pd.to_datetime(data["date_arrivee"], errors="coerce").dt.year == int(year)]
    if paye_f != "Tous":
        val = (paye_f == "Payé")
        data = data[data["paye"] == val]

    st.dataframe(data, use_container_width=True)

    st.download_button(
        "⬇️ Exporter CSV filtré",
        data=data.to_csv(index=False, sep=";").encode("utf-8"),
        file_name="reservations_filtrees.csv",
        mime="text/csv"
    )

# ============================== AJOUT / MODIF / PALETTE / CALENDRIER ==============================

def vue_ajouter(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter une réservation — {apt_name}")
    print_buttons()

    with st.form("form_add_resa", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom du client")
            email = st.text_input("Email", value="")
            tel = st.text_input("Téléphone")
            arr = st.date_input("Arrivée", date.today())
            dep = st.date_input("Départ", date.today() + timedelta(days=1))
        with c2:
            plat = st.selectbox("Plateforme", list(palette.keys()) or ["Autre"])
            brut = st.number_input("Prix brut (€)", min_value=0.0, step=0.01)
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01)
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01)
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01)
            taxes = st.number_input("Taxes séjour (€)", min_value=0.0, step=0.01)
            paye = st.checkbox("Payé", value=False)

        ok = st.form_submit_button("✅ Ajouter")
        if ok:
            if not nom or dep <= arr:
                st.error("Veuillez saisir un nom et des dates valides (départ > arrivée).")
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
                    st.success(f"Réservation pour {nom} ajoutée ✅")
                    st.rerun()


def vue_modifier(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options = [f"{i}: {r.get('nom_client','')} — arrivée {r.get('date_arrivee','')}" for i, r in df_sorted.iterrows()]
    pick = st.selectbox("Choisissez une réservation", options=options, index=None)

    if not pick:
        return

    idx = int(pick.split(":")[0])
    real_idx = df_sorted.loc[idx, "index"]
    row = df.loc[real_idx]

    with st.form(f"form_edit_{real_idx}"):
        c1, c2 = st.columns(2)
        with c1:
            nom = st.text_input("Nom", value=str(row.get("nom_client") or ""))
            email = st.text_input("Email", value=str(row.get("email") or ""))
            tel = st.text_input("Téléphone", value=str(row.get("telephone") or ""))
            arrivee = st.date_input("Arrivée", value=_to_date(pd.Series([row.get("date_arrivee")]))[0] or date.today())
            depart = st.date_input("Départ", value=_to_date(pd.Series([row.get("date_depart")]))[0] or (date.today()+timedelta(days=1)))
        with c2:
            keys = list(palette.keys()) or ["Autre"]
            try:
                idx_plat = keys.index(row.get("plateforme")) if row.get("plateforme") in keys else 0
            except Exception:
                idx_plat = 0
            plat = st.selectbox("Plateforme", keys, index=idx_plat)
            paye = st.checkbox("Payé", value=bool(row.get("paye", False)))

            brut = float(pd.to_numeric(row.get("prix_brut"), errors="coerce") or 0)
            commissions = float(pd.to_numeric(row.get("commissions"), errors="coerce") or 0)
            frais_cb = float(pd.to_numeric(row.get("frais_cb"), errors="coerce") or 0)
            menage = float(pd.to_numeric(row.get("menage"), errors="coerce") or 0)
            taxes = float(pd.to_numeric(row.get("taxes_sejour"), errors="coerce") or 0)

            brut = st.number_input("Prix brut", min_value=0.0, step=0.01, value=brut)
            commissions = st.number_input("Commissions", min_value=0.0, step=0.01, value=commissions)
            frais_cb = st.number_input("Frais CB", min_value=0.0, step=0.01, value=frais_cb)
            menage = st.number_input("Ménage", min_value=0.0, step=0.01, value=menage)
            taxes = st.number_input("Taxes séjour", min_value=0.0, step=0.01, value=taxes)

        colb1, colb2 = st.columns([0.7, 0.3])
        if colb1.form_submit_button("💾 Enregistrer"):
            updates = {
                "nom_client": nom, "email": email, "telephone": tel,
                "date_arrivee": arrivee, "date_depart": depart,
                "plateforme": plat, "paye": paye,
                "prix_brut": brut, "commissions": commissions, "frais_cb": frais_cb,
                "menage": menage, "taxes_sejour": taxes
            }
            for k, v in updates.items():
                df.loc[real_idx, k] = v
            if sauvegarder_donnees(df):
                st.success("Réservation mise à jour ✅")
                st.rerun()

        if colb2.form_submit_button("🗑️ Supprimer"):
            df2 = df.drop(index=real_idx)
            if sauvegarder_donnees(df2):
                st.warning("Réservation supprimée.")
                st.rerun()


def vue_plateformes(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes & couleurs — {apt_name}")
    print_buttons()

    # Base d’édition (toutes plateformes connues + celles déjà en base)
    known = list(palette.keys())
    seen = sorted(df["plateforme"].dropna().astype(str).str.strip().replace({"nan": ""}).unique().tolist())
    all_plats = sorted(set(known + seen))

    base = pd.DataFrame({
        "plateforme": all_plats,
        "couleur": [palette.get(p, "#666666") for p in all_plats],
    })

    HAS_COLORCOL = hasattr(getattr(st, "column_config", object), "ColorColumn")
    if HAS_COLORCOL:
        cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorColumn("Couleur"),
        }
    else:
        cfg = {
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn("Couleur (hex)", validate=r"^#([0-9A-Fa-f]{6})$", width="small"),
        }
        st.caption("Ta version de Streamlit ne supporte peut-être pas le picker couleur — saisis un hex (#e74c3c).")

    edited = st.data_editor(
        base, use_container_width=True, num_rows="dynamic", hide_index=True, column_config=cfg, key="palette_editor"
    )

    c1, c2, c3 = st.columns([0.6, 0.25, 0.15])
    if c1.button("💾 Enregistrer la palette", key="btn_save_palette"):
        try:
            to_save = edited.copy()
            to_save["plateforme"] = to_save["plateforme"].astype(str).str.strip()
            to_save["couleur"] = to_save["couleur"].astype(str).str.strip()
            to_save = to_save[to_save["plateforme"] != ""].drop_duplicates(subset=["plateforme"])
            if not HAS_COLORCOL:
                ok = to_save["couleur"].str.match(r"^#([0-9A-Fa-f]{6})$")
                to_save.loc[~ok, "couleur"] = "#666666"
            to_save.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8", lineterminator="\n")
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur lors de l'enregistrement : {e}")

    if c2.button("↩️ Palette par défaut", key="btn_reset_palette"):
        try:
            pd.DataFrame(list(DEFAULT_PALETTE.items()), columns=["plateforme", "couleur"]).to_csv(
                CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8", lineterminator="\n"
            )
            st.success("Palette par défaut restaurée.")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Erreur : {e}")

    if c3.button("🔄 Reload", key="btn_reload_palette"):
        st.cache_data.clear()
        st.rerun()


def vue_calendrier(df, palette):
    """Grille mensuelle (mise en page conservée)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier (grille mensuelle) — {apt_name}")
    print_buttons()

    dfv = df.dropna(subset=["date_arrivee", "date_depart"]).copy()
    if dfv.empty:
        st.info("Aucune réservation à afficher.")
        return

    today = date.today()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"] = _to_date(dfv["date_depart"])

    years = sorted(pd.to_datetime(dfv["date_arrivee"], errors="coerce").dt.year.dropna().astype(int).unique(), reverse=True)
    annee = st.selectbox("Année", options=years if years else [today.year], index=0)
    mois = st.selectbox("Mois", options=list(range(1, 13)), index=today.month - 1)

    # En-tête jours
    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div>"
        "<div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True
    )

    def day_resas(d):
        mask = (dfv['date_arrivee'] <= d) & (dfv['date_depart'] > d)
        return dfv[mask]

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
                        name = str(r.get('nom_client') or '')[:22]
                        cell += (
                            f"<div class='resa-pill' style='background:{color}' "
                            f"title='{r.get('nom_client','')}'>{name}</div>"
                        )
            cell += "</div>"
            html.append(cell)
    html.append("</div>")
    st.markdown("".join(html), unsafe_allow_html=True)

    # Détail mois sélectionné + KPI
    st.markdown("---")
    st.subheader("Détail du mois sélectionné")
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfv[(dfv['date_arrivee'] <= fin_mois) & (dfv['date_depart'] > debut_mois)].copy()

    if rows.empty:
        st.info("Aucune réservation sur ce mois.")
        return

    plats = ["Toutes"] + sorted(rows["plateforme"].dropna().unique().tolist())
    plat = st.selectbox("Filtrer par plateforme", plats, index=0, key="cal_plat")
    if plat != "Toutes":
        rows = rows[rows["plateforme"] == plat]

    brut = float(pd.to_numeric(rows["prix_brut"], errors="coerce").fillna(0).sum())
    net = float(pd.to_numeric(rows["prix_net"], errors="coerce").fillna(0).sum())
    nuits = int(pd.to_numeric(rows["nuitees"], errors="coerce").fillna(0).sum())

    kpi_html = f"""
    <div class='glass kpi-line'>
      <span class='chip'><small>Total brut</small><br><strong>{brut:,.2f} €</strong></span>
      <span class='chip'><small>Total net</small><br><strong>{net:,.2f} €</strong></span>
      <span class='chip'><small>Nuitées</small><br><strong>{nuits}</strong></span>
    </div>
    """.replace(",", " ")
    st.markdown(kpi_html, unsafe_allow_html=True)

    st.dataframe(
        rows[["nom_client", "plateforme", "date_arrivee", "date_depart", "nuitees", "paye", "pays"]],
        use_container_width=True
    )

# ============================== RAPPORT / SMS / EXPORT ICS / GOOGLE SHEET / CLIENTS / ID / PARAMÈTRES / MAIN ==============================

# --- Petit helper pour copier des messages (utile pour SMS) ---
def _copy_button(label: str, payload: str, key: str):
    st.text_area(label, payload, height=260, key=f"ta_{key}")
    st.caption("Sélectionnez puis copiez (Ctrl/Cmd+C).")


def vue_rapport(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📊 Rapport — {apt_name}")
    print_buttons()

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
    year = c1.selectbox("Année", ["Toutes"] + years_avail, index=0)
    month = c2.selectbox("Mois", ["Tous"] + months_avail, index=0)
    plat = c3.selectbox("Plateforme", ["Toutes"] + plats_avail, index=0)
    payf = c4.selectbox("Pays", ["Tous"] + pays_avail, index=0)
    metric = c5.selectbox(
        "Métrique",
        ["prix_brut", "prix_net", "base", "charges", "menage", "taxes_sejour", "nuitees"],
        index=1
    )

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

    # ===== TAUX D'OCCUPATION =====
    st.markdown("---")
    st.subheader("📅 Taux d'occupation")

    data["mois"] = data["date_arrivee_dt"].dt.to_period("M").astype(str)
    data["nuitees_calc"] = (data["date_depart_dt"] - data["date_arrivee_dt"]).dt.days

    occ_mois = data.groupby(["mois", "plateforme"], as_index=False)["nuitees_calc"].sum()
    occ_mois.rename(columns={"nuitees_calc": "nuitees_occupees"}, inplace=True)

    def jours_dans_mois(periode_str):
        annee, mois = map(int, periode_str.split("-"))
        return monthrange(annee, mois)[1]

    occ_mois["jours_dans_mois"] = occ_mois["mois"].apply(jours_dans_mois)
    occ_mois["taux_occupation"] = (occ_mois["nuitees_occupees"] / occ_mois["jours_dans_mois"]) * 100

    col_plat, col_export = st.columns([1, 1])
    plat_occ = col_plat.selectbox("Filtrer par plateforme (occupation)", ["Toutes"] + plats_avail, index=0)

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
    col_export.download_button(
        "⬇️ Exporter les données d'occupation (CSV)",
        data=csv_occ,
        file_name="taux_occupation.csv",
        mime="text/csv"
    )
    xlsx_occ, _ = _df_to_xlsx_bytes(occ_export, "Taux d'occupation")
    if xlsx_occ:
        col_export.download_button(
            "⬇️ Exporter les données d'occupation (Excel)",
            data=xlsx_occ,
            file_name="taux_occupation.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.dataframe(
        occ_export.assign(taux_occupation=lambda x: x["taux_occupation"].round(1)),
        use_container_width=True
    )

    # ===== COMPARAISON ENTRE ANNÉES =====
    st.markdown("---")
    st.subheader("📊 Comparaison des taux d'occupation par année")

    data["annee"] = data["date_arrivee_dt"].dt.year
    occ_annee = data.groupby(["annee", "plateforme"])["nuitees_calc"].sum().reset_index()
    occ_annee.rename(columns={"nuitees_calc": "nuitees_occupees"}, inplace=True)

    def jours_dans_annee(annee):
        return 366 if (annee % 4 == 0 and annee % 100 != 0) or (annee % 400 == 0) else 365

    occ_annee["jours_dans_annee"] = occ_annee["annee"].apply(jours_dans_annee)
    occ_annee["taux_occupation"] = (occ_annee["nuitees_occupees"] / occ_annee["jours_dans_annee"]) * 100

    annees_comparaison = st.multiselect(
        "Sélectionner les années à comparer",
        options=sorted(occ_annee["annee"].unique()),
        default=sorted(occ_annee["annee"].unique())[-2:] if len(occ_annee["annee"].unique()) >= 2 else sorted(occ_annee["annee"].unique())
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
    else:
        st.warning("Veuillez sélectionner au moins une année.")

    # ===== MÉTRIQUES FINANCIÈRES =====
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

    # ===== 🌍 ANALYSE PAR PAYS =====
    st.markdown("---")
    st.subheader("🌍 Analyse par pays")

    years_pays = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique().tolist(), reverse=True)
    year_pays = st.selectbox("Année (analyse pays)", ["Toutes"] + years_pays, index=0, key="year_pays")

    data_p = dfa.copy()
    data_p["pays"] = dfa["_pays"]
    if year_pays != "Toutes":
        data_p = data_p[data_p["date_arrivee_dt"].dt.year == int(year_pays)]

    data_p["nuitees_calc"] = (data_p["date_depart_dt"] - data_p["date_arrivee_dt"]).dt.days

    agg_pays = data_p.groupby("pays", as_index=False).agg(
        reservations=("nom_client", "count"),
        nuitees=("nuitees_calc", "sum"),
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
    num_cols = ["reservations", "nuitees", "prix_brut", "prix_net", "menage", "taxes_sejour", "charges", "base", "ADR_net", "part_revenu_%"]
    for c in num_cols:
        disp[c] = pd.to_numeric(disp[c], errors="coerce")

    disp["reservations"] = disp["reservations"].fillna(0).astype("int64")
    disp["pays"] = disp["pays"].astype(str).replace({"nan": "Inconnu", "": "Inconnu"})

    disp["prix_brut"] = disp["prix_brut"].round(2)
    disp["prix_net"] = disp["prix_net"].round(2)
    disp["ADR_net"] = disp["ADR_net"].round(2)
    disp["part_revenu_%"] = disp["part_revenu_%"].round(1)

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
                alt.Tooltip("part_revenu_%:Q", title="Part du revenu (%)", format=".1f"),
            ],
        ).properties(height=420)
        st.altair_chart(chart_pays, use_container_width=True)
    except Exception as e:
        st.warning(f"Graphique 'Analyse par pays' indisponible : {e}")

    # ===== ÉVOLUTION DU TAUX D'OCCUPATION =====
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


def _google_form_prefill(res_id, nom, phone, arr, dep) -> str:
    """
    Tu utilises un lien court public (FORM_SHORT_URL). On le renvoie tel quel pour fiabilité.
    Si tu veux basculer sur le lien 'long' pré-rempli, remplace ici par la construction d'URL.
    """
    return FORM_SHORT_URL


def vue_sms(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS & WhatsApp — {apt_name}")
    print_buttons()

    # ===== Pré-arrivée =====
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
        pick = st.selectbox("Client (pré-arrivée)", options=opts, index=None)

        if pick:
            i = int(pick.split(":")[0])
            r = pre.loc[i]

            link_form = _google_form_prefill(
                r.get("res_id"),
                r.get("nom_client"),
                _format_phone_e164(r.get("telephone")),
                r.get("date_arrivee"),
                r.get("date_depart"),
            )

            msg = (
                f"{apt_name.upper()}\n"
                f"Plateforme : {r.get('plateforme', 'N/A')}\n"
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
                "We are delighted to welcome you soon to Nice. In order to organize your reception as efficiently as possible,we kindly ask you to fill out the form that you will find by clicking on the following link: \n"
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
            _copy_button("📋 Copier le message (pré-arrivée)", msg, key=f"pre_{i}")

            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{wa}?text={enc}")

            if st.button("✅ Marquer 'SMS envoyé'", key=f"pre_mark_{r['_rowid']}"):
                df.loc[r["_rowid"], "sms_envoye"] = True
                if sauvegarder_donnees(df):
                    st.success("Marqué ✅")
                    st.rerun()

    # ===== Post-départ =====
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
        pick2 = st.selectbox("Client (post-départ)", options=opts2, index=None)

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
            _copy_button("📋 Copier le message (post-départ)", msg2, key=f"post_{j}")

            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{wab}?text={enc2}")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}")

            if st.button("✅ Marquer 'post-départ envoyé'", key=f"post_mark_{r2['_rowid']}"):
                df.loc[r2["_rowid"], "post_depart_envoye"] = True
                if sauvegarder_donnees(df):
                    st.success("Marqué ✅")
                    st.rerun()


def vue_export_ics(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📆 Export ICS — {apt_name}")
    print_buttons()

    if df.empty:
        st.info("Aucune réservation.")
        return

    dfa = df.copy()
    dfa["date_arrivee_dt"] = pd.to_datetime(dfa["date_arrivee"], errors="coerce")
    years = sorted(dfa["date_arrivee_dt"].dt.year.dropna().astype(int).unique(), reverse=True)
    year = st.selectbox("Année (arrivées)", years if years else [date.today().year], index=0)
    plats = ["Tous"] + sorted(df["plateforme"].dropna().unique())
    plat = st.selectbox("Plateforme", plats, index=0)

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
        mime="text/calendar"
    )


def vue_google_sheet(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📝 Fiche d'arrivée / Google Sheet — {apt_name}")
    print_buttons()
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
        rep_display = rep if show_email else rep.drop(columns=[c for c in rep.columns if "mail" in c.lower() or "email" in c.lower()], errors="ignore")
        st.dataframe(rep_display, use_container_width=True)
    except Exception as e:
        st.error(f"Impossible de charger la feuille publiée : {e}")


def vue_clients(df, palette):
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"👥 Liste des clients — {apt_name}")
    print_buttons()

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


def vue_settings(df: pd.DataFrame, palette: dict):
    """Paramètres centralisés : export, restauration, cache, import manuel, écrasement apartments.csv."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header("## ⚙️ Paramètres")
    st.subheader(apt_name)
    print_buttons()

    st.caption("Sauvegarde, restauration (réservations & plateformes), cache, import manuel, diagnostic, écrasement `apartments.csv`.")

    # ========== Sauvegarde (exports) ==========
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
    c1.download_button(
        "⬇️ Exporter réservations (CSV)",
        data=csv_bytes,
        file_name=os.path.basename(CSV_RESERVATIONS),
        mime="text/csv",
        key="dl_res_csv",
    )

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
        file_name=os.path.splitext(os.path.basename(CSV_RESERVATIONS))[0] + ".xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(xlsx_bytes is None),
        key="dl_res_xlsx",
    )

    # ========== Restauration ==========
    st.markdown("### ♻️ Restauration (remplacer les données)")
    st.caption("Charge un **CSV** (séparateur auto) ou **XLSX** puis REMPLACE le fichier de l’appartement en cours.")
    up_res = st.file_uploader("Restaurer — réservations", type=["csv", "xlsx"], key="restore_res")
    up_pal = st.file_uploader("Restaurer — plateformes", type=["csv", "xlsx"], key="restore_pal")

    def _read_upload(upl):
        if upl is None:
            return None
        try:
            if upl.name.lower().endswith(".xlsx"):
                return pd.read_excel(upl, dtype=str)
            else:
                raw = upl.read()
                return _detect_delimiter_and_read(raw)
        except Exception as e:
            st.error(f"Erreur de lecture : {e}")
            return None

    if up_res is not None:
        tmp = _read_upload(up_res)
        if tmp is not None:
            prev = ensure_schema(tmp)
            st.success(f"{len(prev)} lignes prêtes à être restaurées vers {os.path.basename(CSV_RESERVATIONS)}")
            with st.expander("Aperçu (10 premières lignes)", expanded=False):
                st.dataframe(prev.head(10), use_container_width=True)
            if st.button("✅ Confirmer restauration réservations", key="btn_apply_res"):
                try:
                    save = prev.copy()
                    for col in ["date_arrivee", "date_depart"]:
                        save[col] = pd.to_datetime(save[col], errors="coerce").dt.strftime("%d/%m/%Y")
                    save.to_csv(CSV_RESERVATIONS, sep=";", index=False, encoding="utf-8", lineterminator="\n")
                    st.cache_data.clear()
                    st.success("Réservations restaurées ✅")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur écriture réservations : {e}")

    if up_pal is not None:
        tmp = _read_upload(up_pal)
        if tmp is not None:
            try:
                tmp.columns = tmp.columns.astype(str).str.strip().str.lower()
                if not {"plateforme", "couleur"}.issubset(tmp.columns):
                    raise ValueError("Fichier plateformes invalide (colonnes attendues : 'plateforme', 'couleur').")
                st.success(f"{len(tmp)} lignes prêtes à être restaurées vers {os.path.basename(CSV_PLATEFORMES)}")
                with st.expander("Aperçu (10 premières lignes)", expanded=False):
                    st.dataframe(tmp.head(10), use_container_width=True)
                if st.button("✅ Confirmer restauration plateformes", key="btn_apply_pal"):
                    tmp.to_csv(CSV_PLATEFORMES, sep=";", index=False, encoding="utf-8", lineterminator="\n")
                    st.cache_data.clear()
                    st.success("Plateformes restaurées ✅")
                    st.rerun()
            except Exception as e:
                st.error(f"Erreur plateformes : {e}")

    # ========== Vider le cache ==========
    st.markdown("### 🧹 Vider le cache")
    if st.button("Vider le cache & recharger", key="clear_cache_btn_settings"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    # ========== Diagnostic ==========
    st.markdown("### 🔎 Diagnostics")
    st.write(f"- Fichier réservations actif : **{CSV_RESERVATIONS}**")
    st.write(f"- Fichier plateformes actif : **{CSV_PLATEFORMES}**")
    st.write(f"- Fichier appartements : **{APARTMENTS_CSV}**")

    # ========== Écraser apartments.csv (secours) ==========
    st.markdown("### 🧰 Écraser `apartments.csv`")
    default_csv = "slug,name\nvilla-tobias,Villa Tobias\nle-turenne,Le Turenne\n"
    txt = st.text_area("Contenu apartments.csv", value=default_csv, height=140, key="force_apts_txt_settings")
    if st.button("🧰 Écraser apartments.csv (outil secours)", key="force_apts_btn_settings"):
        try:
            with open(APARTMENTS_CSV, "w", encoding="utf-8", newline="") as f:
                f.write(txt.strip() + "\n")
            st.cache_data.clear()
            st.success("apartments.csv écrasé ✅ — rechargement…")
            st.rerun()
        except Exception as e:
            st.error(f"Impossible d'écrire apartments.csv : {e}")

# ============================== APARTMENTS (sélecteur sans mot de passe) ==============================
APARTMENTS_CSV = "apartments.csv"

def _read_apartments_csv() -> pd.DataFrame:
    """Charge apartments.csv (séparateur auto) et normalise {slug, name}."""
    try:
        if not os.path.exists(APARTMENTS_CSV):
            return pd.DataFrame(columns=["slug", "name"])
        raw = _load_file_bytes(APARTMENTS_CSV)
        df = _detect_delimiter_and_read(raw) if raw else pd.DataFrame()
        if df is None or df.empty:
            return pd.DataFrame(columns=["slug", "name"])

        # colonnes et nettoyage
        df.columns = [str(c).strip().lower() for c in df.columns]
        if "slug" not in df.columns: df["slug"] = ""
        if "name" not in df.columns: df["name"] = ""
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
    slug = st.session_state.get("apt_slug", "")
    name = st.session_state.get("apt_name", "")
    if slug and name:
        return {"slug": slug, "name": name}
    return None


def _select_apartment_sidebar() -> bool:
    """
    Affiche le sélecteur d'appartement dans la sidebar et met à jour les chemins
    CSV_RESERVATIONS / CSV_PLATEFORMES en session. Retourne True si la sélection a changé.
    """
    st.sidebar.markdown("### Appartement")
    apts = _read_apartments_csv()
    if apts.empty:
        st.sidebar.warning("Aucun appartement trouvé dans apartments.csv")
        return False

    options = apts["slug"].tolist()
    labels = {r["slug"]: r["name"] for _, r in apts.iterrows()}

    # index par défaut robuste
    cur_slug = st.session_state.get("apt_slug", options[0])
    if cur_slug not in options:
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

    changed = (slug != st.session_state.get("apt_slug", "") or name != st.session_state.get("apt_name", ""))

    # mémorise et synchronise les chemins actifs
    st.session_state["apt_slug"] = slug
    st.session_state["apt_name"] = name
    st.session_state["CSV_RESERVATIONS"] = f"reservations_{slug}.csv"
    st.session_state["CSV_PLATEFORMES"]  = f"plateformes_{slug}.csv"

    # met à jour les globales utilisées par les fonctions d’export/restauration
    global CSV_RESERVATIONS, CSV_PLATEFORMES
    CSV_RESERVATIONS = st.session_state["CSV_RESERVATIONS"]
    CSV_PLATEFORMES  = st.session_state["CSV_PLATEFORMES"]

    st.sidebar.success(f"Connecté : {name}")
    try:
        print_buttons(location="sidebar")
    except Exception:
        pass

    return changed

# ============================== MAIN ==============================
def main():
    # Réinit cache via URL ?clear=1
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1", "true", "True", "yes"):
        try:
            st.cache_data.clear()
        except Exception:
            pass

    # Sélecteur d'appartement
    changed = _select_apartment_sidebar()
    if changed:
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    # Thème clair/obscur
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    # En-tête
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    # Chargement des données pour l’appartement actif
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