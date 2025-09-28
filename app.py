# ============================== PARTIE 1/5 — IMPORTS, CONSTANTES, STYLES, HELPERS ==============================

from __future__ import annotations

import os
import io
import re
import csv
from datetime import date, datetime, timedelta
from calendar import Calendar, monthrange

import pandas as pd
import numpy as np

import streamlit as st
import matplotlib.pyplot as plt

from urllib.parse import quote

# ---------- Constantes globales ----------
APP_TITLE = "Gestion des Reservations"

# Fichiers racine
APARTMENTS_CSV = "apartments.csv"              # liste des appartements: slug,name
INDICATIFS_CSV = "indicatifs_pays.csv"         # code,country,dial,flag

# Fichiers dependants de l'appartement (mis a jour en session)
CSV_RESERVATIONS = "reservations.csv"
CSV_PLATEFORMES  = "plateformes.csv"

# Lien court de formulaire (utilise dans les SMS)
FORM_SHORT_URL = "https://urlr.me/kZuH94"

# Palette par defaut si aucune palette specifique
DEFAULT_PALETTE = {
    "Airbnb": "#FF5A5F",
    "Booking": "#003580",
    "Abritel": "#00A4BD",
    "Direct": "#22A699",
    "Autre": "#8E8E93",
}

# ---------- CSS / style ----------
def apply_style(light: bool = False) -> None:
    """Applique un petit style global + mode clair optionnel sur Desktop."""
    bg = "#0E1117" if not light else "#FFFFFF"
    fg = "#FAFAFA" if not light else "#111111"
    muted = "#64748b" if not light else "#334155"

    css = f"""
    <style>
      :root {{
        --app-bg: {bg};
        --app-fg: {fg};
        --app-muted: {muted};
      }}
      .print-header {{ display: none; }}
      @media print {{
        .print-header {{ display: block; font-size: 14px; margin-bottom: 10px; }}
        .stAppViewMain, .stApp {{ background: white !important; color: black !important; }}
      }}
      div.block-container {{ padding-top: 1rem; }}
      .chip {{
        display:inline-flex; align-items:center; gap:.5rem;
        padding:.2rem .6rem; border-radius:999px; font-size:.85rem;
        background:#1f2937; color:#e5e7eb;
      }}
    </style>
    """
    st.markdown(css, unsafe_allow_html=True)


# ---------- Utils donnees ----------
NEEDED_COLS = [
    "id", "numero_reservation", "plateforme",
    "date_arrivee", "date_depart", "nuitees",
    "nom_client", "telephone", "pays",
    "tarif", "sms_envoye", "post_depart_envoye",
]

def ensure_schema(df: pd.DataFrame | None) -> pd.DataFrame:
    """Garanti la presence des colonnes attendues."""
    if df is None:
        df = pd.DataFrame(columns=NEEDED_COLS)
    for c in NEEDED_COLS:
        if c not in df.columns:
            df[c] = ""
    return df[NEEDED_COLS].copy()

def _to_date(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce").dt.date

def _to_bool_series(s: pd.Series) -> pd.Series:
    if s is None:
        return pd.Series(False, index=pd.RangeIndex(0))
    return s.astype(str).str.lower().isin(["1", "true", "yes", "y", "t", "vrai", "oui"])

def _detect_delimiter_and_read(raw_bytes: bytes) -> pd.DataFrame:
    sample = raw_bytes.decode("utf-8", errors="ignore")
    delim = ";"
    if sample.count(",") > sample.count(";"):
        delim = ","
    return pd.read_csv(io.BytesIO(raw_bytes), sep=delim, dtype=str)

def _df_to_xlsx_bytes(df: pd.DataFrame, sheet_name: str = "Sheet1") -> tuple[bytes, str]:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        df.to_excel(xw, sheet_name=sheet_name, index=False)
    return buf.getvalue(), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


# ---------- Indicatifs pays ----------
def _ensure_indicatifs_exists() -> None:
    """Cree un petit CSV si absent pour eviter les erreurs la premiere fois."""
    if os.path.exists(INDICATIFS_CSV):
        return
    base = pd.DataFrame(
        [
            {"code": "FR", "country": "France", "dial": "+33", "flag": "🇫🇷"},
            {"code": "GB", "country": "United Kingdom", "dial": "+44", "flag": "🇬🇧"},
            {"code": "ES", "country": "Spain", "dial": "+34", "flag": "🇪🇸"},
            {"code": "IT", "country": "Italy", "dial": "+39", "flag": "🇮🇹"},
            {"code": "DE", "country": "Germany", "dial": "+49", "flag": "🇩🇪"},
        ]
    )
    try:
        base.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8")
    except Exception:
        pass

@st.cache_data(show_spinner=False)
def _load_indicatifs_df_cached() -> pd.DataFrame:
    _ensure_indicatifs_exists()
    try:
        df = pd.read_csv(INDICATIFS_CSV, dtype=str).fillna("")
        for col in ["code", "country", "dial", "flag"]:
            if col not in df.columns:
                df[col] = ""
        # normalisation
        df["code"] = df["code"].str.strip().str.upper()
        df["country"] = df["country"].str.strip()
        df["dial"] = df["dial"].astype(str).str.strip()
        df.loc[~df["dial"].str.startswith("+") & df["dial"].ne(""), "dial"] = "+" + df["dial"].str.lstrip("+").str.strip()
        df["flag"] = df["flag"].astype(str).str.strip()
        return df[["code", "country", "dial", "flag"]]
    except Exception:
        return pd.DataFrame(columns=["code", "country", "dial", "flag"])

def _format_phone_e164(phone: str) -> str:
    """Normalise un numero: garde chiffres, prefixe + si manquant."""
    s = re.sub(r"\D", "", str(phone or ""))
    if not s:
        return ""
    if s.startswith("00"):
        s = s[2:]
    if not s.startswith("+"):
        s = "+" + s
    return s

def _phone_country(phone: str) -> str:
    """Renvoie un libelle de pays a partir de l'indicatif. Utilise INDICATIFS_CSV."""
    phone = _format_phone_e164(phone)
    if not phone:
        return "Inconnu"
    idx = _load_indicatifs_df_cached()
    # trie par longueur d'indicatif decroissante pour matcher le plus specifique
    idx = idx.assign(len_dial=idx["dial"].str.len()).sort_values("len_dial", ascending=False)
    for _, r in idx.iterrows():
        d = r.get("dial", "")
        if d and phone.startswith(d):
            flag = r.get("flag", "")
            name = r.get("country", "")
            return f"{name}" if not flag else f"{name} {flag}"
    return "Inconnu"


# ---------- Lecture / ecriture des donnees ----------
def _active_paths_from_session() -> tuple[str, str]:
    """Retourne (csv_reservations, csv_plateformes) en fonction de l'appartement active."""
    csv_res = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
    csv_plat = st.session_state.get("CSV_PLATEFORMES", CSV_PLATEFORMES)
    return csv_res, csv_plat

def sauvegarder_donnees(df: pd.DataFrame) -> bool:
    """Sauvegarde le CSV de reservations actif."""
    csv_res, _ = _active_paths_from_session()
    try:
        ensure_schema(df).to_csv(csv_res, sep=";", index=False, encoding="utf-8", lineterminator="\n")
        return True
    except Exception as e:
        st.error(f"Ecriture impossible: {e}")
        return False

def _load_palette(csv_plateformes: str) -> dict:
    """Lit la palette couleur par plateforme depuis CSV_PLATEFORMES (colonnes: plateforme,couleur)."""
    if not os.path.exists(csv_plateformes):
        return DEFAULT_PALETTE.copy()
    try:
        df = pd.read_csv(csv_plateformes, dtype=str).fillna("")
        out = {}
        for _, r in df.iterrows():
            p = r.get("plateforme", "").strip()
            c = r.get("couleur", "").strip()
            if p:
                out[p] = c if c else DEFAULT_PALETTE.get(p, "#888888")
        return {**DEFAULT_PALETTE, **out}
    except Exception:
        return DEFAULT_PALETTE.copy()

@st.cache_data(show_spinner=False)
def _read_reservations(csv_res: str) -> pd.DataFrame:
    if not os.path.exists(csv_res):
        return ensure_schema(pd.DataFrame())
    try:
        df = pd.read_csv(csv_res, sep=";", dtype=str).fillna("")
    except Exception:
        df = pd.read_csv(csv_res, dtype=str).fillna("")
    return ensure_schema(df)

def _current_apartment() -> dict | None:
    """Retourne l'appartement actif depuis apartments.csv selon st.session_state.apartment_slug."""
    if not os.path.exists(APARTMENTS_CSV):
        return None
    try:
        df = pd.read_csv(APARTMENTS_CSV, dtype=str).fillna("")
        slug = st.session_state.get("apartment_slug", "")
        if slug and (df["slug"] == slug).any():
            r = df[df["slug"] == slug].iloc[0]
            return {"slug": r["slug"], "name": r.get("name", r["slug"])}
        # fallback premier
        if not df.empty:
            r = df.iloc[0]
            st.session_state["apartment_slug"] = r["slug"]
            return {"slug": r["slug"], "name": r.get("name", r["slug"])}
    except Exception:
        pass
    return None

def _select_apartment_sidebar() -> bool:
    """Widget sidebar pour choisir l'appartement et mettre a jour les chemins actifs.
       Retourne True si changement."""
    st.sidebar.markdown("### Appartement")
    # charge liste
    if os.path.exists(APARTMENTS_CSV):
        apts = pd.read_csv(APARTMENTS_CSV, dtype=str).fillna("")
    else:
        apts = pd.DataFrame(columns=["slug", "name"])

    if apts.empty:
        st.sidebar.warning("Aucun appartement trouve dans apartments.csv")
        return False

    options = {f"{r['name']} ({r['slug']})": r["slug"] for _, r in apts.iterrows()}
    current_slug = st.session_state.get("apartment_slug", list(options.values())[0])
    label_default = [k for k, v in options.items() if v == current_slug]
    chosen = st.sidebar.selectbox("Choisir un appartement", list(options.keys()),
                                  index=0 if not label_default else list(options.keys()).index(label_default[0]))

    new_slug = options[chosen]
    changed = new_slug != current_slug
    if changed:
        st.session_state["apartment_slug"] = new_slug

    # chemins dependants de l'appartement
    csv_res = f"data/{new_slug}_reservations.csv"
    csv_plat = f"data/{new_slug}_plateformes.csv"
    os.makedirs("data", exist_ok=True)
    # si fichiers inexistants, creer squelette
    if not os.path.exists(csv_res):
        ensure_schema(pd.DataFrame()).to_csv(csv_res, sep=";", index=False, encoding="utf-8", lineterminator="\n")
    if not os.path.exists(csv_plat):
        pd.DataFrame({"plateforme": list(DEFAULT_PALETTE.keys()), "couleur": list(DEFAULT_PALETTE.values())}).to_csv(
            csv_plat, index=False, encoding="utf-8"
        )

    st.session_state["CSV_RESERVATIONS"] = csv_res
    st.session_state["CSV_PLATEFORMES"]  = csv_plat

    # petit indicateur
    apt = _current_apartment()
    if apt:
        st.sidebar.caption(f"Connecte : **{apt['name']}**")
    return changed

def _load_data_for_active_apartment() -> tuple[pd.DataFrame, dict]:
    """Charge df reservations + palette pour l'appartement courant."""
    csv_res, csv_plat = _active_paths_from_session()
    df = _read_reservations(csv_res)
    palette = _load_palette(csv_plat)
    return df, palette

def print_buttons():
    """Bandeau utilitaire discret sous les titres."""
    st.write("")  # spacing


# ============================== FIN PARTIE 1/5 ==============================



# ============================== PARTIE 2/5 — ACCUEIL, RESERVATIONS, AJOUTER, MODIFIER ==============================

# ---------------- ACCUEIL ----------------
def vue_accueil(df: pd.DataFrame, palette: dict):
    """Page d'accueil avec recap rapide (arrivees/departs)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🏠 Accueil — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune donnée disponible.")
        return

    dfx = ensure_schema(df).copy()
    dfx["date_arrivee"] = _to_date(dfx["date_arrivee"])
    dfx["date_depart"] = _to_date(dfx["date_depart"])

    today = date.today()
    tomorrow = today + timedelta(days=1)

    arrivals_today = dfx[dfx["date_arrivee"] == today]
    departures_today = dfx[dfx["date_depart"] == today]
    arrivals_tomorrow = dfx[dfx["date_arrivee"] == tomorrow]

    c1, c2, c3 = st.columns(3)
    c1.metric("Arrivées aujourd'hui", len(arrivals_today))
    c2.metric("Départs aujourd'hui", len(departures_today))
    c3.metric("Arrivées demain", len(arrivals_tomorrow))

    st.subheader("📋 Arrivées aujourd'hui")
    st.dataframe(arrivals_today[["numero_reservation", "nom_client", "plateforme", "telephone"]], use_container_width=True)

    st.subheader("📤 Départs aujourd'hui")
    st.dataframe(departures_today[["numero_reservation", "nom_client", "plateforme", "telephone"]], use_container_width=True)

    st.subheader("🛬 Arrivées demain")
    st.dataframe(arrivals_tomorrow[["numero_reservation", "nom_client", "plateforme", "telephone"]], use_container_width=True)


# ---------------- RÉSERVATIONS ----------------
def vue_reservations(df: pd.DataFrame, palette: dict):
    """Affiche la liste des réservations."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📋 Réservations — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    st.dataframe(df, use_container_width=True)


# ---------------- AJOUTER ----------------
def vue_ajouter(df: pd.DataFrame, palette: dict):
    """Ajout manuel d'une réservation."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"➕ Ajouter — {apt_name}")
    print_buttons()

    with st.form("ajouter_form", clear_on_submit=True):
        numero_resa = st.text_input("Numéro de réservation")
        plateforme = st.selectbox("Plateforme", options=list(palette.keys()))
        date_arrivee = st.date_input("Date arrivée", value=date.today())
        date_depart = st.date_input("Date départ", value=date.today() + timedelta(days=1))
        nom_client = st.text_input("Nom du client")
        telephone = st.text_input("Téléphone")
        tarif = st.number_input("Tarif (€)", min_value=0.0, step=10.0)

        submitted = st.form_submit_button("Ajouter")
        if submitted:
            try:
                new = {
                    "id": str(int(df["id"].max()) + 1 if not df.empty else 1),
                    "numero_reservation": numero_resa,
                    "plateforme": plateforme,
                    "date_arrivee": date_arrivee.strftime("%Y-%m-%d"),
                    "date_depart": date_depart.strftime("%Y-%m-%d"),
                    "nuitees": (date_depart - date_arrivee).days,
                    "nom_client": nom_client,
                    "telephone": telephone,
                    "pays": _phone_country(telephone),
                    "tarif": tarif,
                    "sms_envoye": False,
                    "post_depart_envoye": False,
                }
                df = pd.concat([df, pd.DataFrame([new])], ignore_index=True)
                if sauvegarder_donnees(df):
                    st.success("Réservation ajoutée ✅")
                    st.rerun()
            except Exception as e:
                st.error(f"Erreur lors de l'ajout: {e}")


# ---------------- MODIFIER / SUPPRIMER ----------------
def vue_modifier(df: pd.DataFrame, palette: dict):
    """Modifier ou supprimer une réservation."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✏️ Modifier / Supprimer — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    dfx = df.copy()
    options = [f"{i}: {r['nom_client']} ({r['date_arrivee']})" for i, r in dfx.iterrows()]
    choice = st.selectbox("Choisir une réservation", options, index=None)

    if choice:
        idx = int(choice.split(":")[0])
        row = dfx.loc[idx]

        with st.form("edit_form"):
            numero_resa = st.text_input("Numéro de réservation", value=row["numero_reservation"])
            plateforme = st.selectbox("Plateforme", options=list(palette.keys()), index=list(palette.keys()).index(row["plateforme"]) if row["plateforme"] in palette else 0)
            date_arrivee = st.date_input("Date arrivée", value=pd.to_datetime(row["date_arrivee"], errors="coerce"))
            date_depart = st.date_input("Date départ", value=pd.to_datetime(row["date_depart"], errors="coerce"))
            nom_client = st.text_input("Nom du client", value=row["nom_client"])
            telephone = st.text_input("Téléphone", value=row["telephone"])
            tarif = st.number_input("Tarif (€)", min_value=0.0, step=10.0, value=float(row["tarif"]) if str(row["tarif"]).replace('.', '', 1).isdigit() else 0.0)

            c1, c2 = st.columns(2)
            if c1.form_submit_button("💾 Sauvegarder"):
                try:
                    df.loc[idx, "numero_reservation"] = numero_resa
                    df.loc[idx, "plateforme"] = plateforme
                    df.loc[idx, "date_arrivee"] = date_arrivee.strftime("%Y-%m-%d")
                    df.loc[idx, "date_depart"] = date_depart.strftime("%Y-%m-%d")
                    df.loc[idx, "nuitees"] = (date_depart - date_arrivee).days
                    df.loc[idx, "nom_client"] = nom_client
                    df.loc[idx, "telephone"] = telephone
                    df.loc[idx, "pays"] = _phone_country(telephone)
                    df.loc[idx, "tarif"] = tarif
                    if sauvegarder_donnees(df):
                        st.success("Réservation modifiée ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la modification: {e}")

            if c2.form_submit_button("🗑️ Supprimer"):
                try:
                    df = df.drop(idx).reset_index(drop=True)
                    if sauvegarder_donnees(df):
                        st.success("Réservation supprimée ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Erreur lors de la suppression: {e}")


# ============================== FIN PARTIE 2/5 ==============================



# ============================== PARTIE 3/5 — PLATEFORMES & CALENDRIER ==============================

from calendar import Calendar, monthrange
from html import escape

# ---------------- PLATEFORMES (palette/couleurs) ----------------
def vue_plateformes(df: pd.DataFrame, palette: dict):
    """Gérer la liste des plateformes et leurs couleurs (palette)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🎨 Plateformes — {apt_name}")
    print_buttons()

    # Plateformes détectées dans les données + palette par défaut
    if df is None or df.empty:
        detected = []
    else:
        detected = sorted([p for p in df["plateforme"].dropna().unique().tolist() if str(p).strip() != ""])

    # Fusion: toutes plateformes connues (palette) + détectées
    all_plats = sorted(set(list(palette.keys()) + detected))
    data = []
    for p in all_plats:
        data.append({
            "plateforme": p,
            "couleur": palette.get(p, "#666666"),
        })
    plat_df = pd.DataFrame(data)

    st.caption("Ajoutez/éditez les couleurs. Le choix influe sur les pastilles du calendrier et les tableaux.")
    edited = st.data_editor(
        plat_df,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.ColorPickerColumn("Couleur"),
        },
        key="palette_editor",
    )

    c1, c2 = st.columns([0.5, 0.5])
    if c1.button("💾 Enregistrer la palette", key="btn_save_palette"):
        # Sauvegarde JSON à côté du CSV de résa de l'appartement courant
        try:
            pal = {}
            for _, r in edited.iterrows():
                name = str(r.get("plateforme") or "").strip()
                col = str(r.get("couleur") or "").strip()
                if name:
                    pal[name] = col if col else "#666666"
            # Persistance par appartement
            apt = _current_apartment()
            if apt:
                pal_path = os.path.join(DATA_DIR, f"{apt['slug']}_palette.json")
            else:
                pal_path = PALETTE_JSON
            with open(pal_path, "w", encoding="utf-8") as f:
                json.dump(pal, f, ensure_ascii=False, indent=2)
            st.success("Palette enregistrée ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Échec de l'enregistrement : {e}")

    if c2.button("↩️ Restaurer la palette par défaut", key="btn_reset_palette"):
        try:
            apt = _current_apartment()
            if apt:
                pal_path = os.path.join(DATA_DIR, f"{apt['slug']}_palette.json")
            else:
                pal_path = PALETTE_JSON
            if os.path.exists(pal_path):
                os.remove(pal_path)
            st.success("Palette restaurée (par défaut) ✅")
            st.cache_data.clear()
            st.rerun()
        except Exception as e:
            st.error(f"Impossible de restaurer : {e}")


# ---------------- CALENDRIER (vue mensuelle) ----------------
def vue_calendrier(df: pd.DataFrame, palette: dict):
    """Calendrier mensuel avec pastilles de séjours (arrivée/départ)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📅 Calendrier — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation.")
        return

    # Préparation des données
    dfv = ensure_schema(df).copy()
    dfv["date_arrivee"] = _to_date(dfv["date_arrivee"])
    dfv["date_depart"]  = _to_date(dfv["date_depart"])

    # Sélection période
    today = date.today()
    col_a, col_b = st.columns(2)
    annee = col_a.selectbox("Année", list(range(today.year - 2, today.year + 3)), index=2)
    mois_names = ["Jan", "Fév", "Mar", "Avr", "Mai", "Juin", "Juil", "Août", "Sep", "Oct", "Nov", "Déc"]
    mois = col_b.selectbox("Mois", list(range(1, 13)), index=today.month - 1, format_func=lambda m: mois_names[m-1])

    # Styles
    st.markdown("""
    <style>
    .cal-grid{
        display:grid;
        grid-template-columns: repeat(7, minmax(120px,1fr));
        gap:8px;
    }
    .cal-header{
        display:grid; grid-template-columns: repeat(7, minmax(120px,1fr));
        gap:8px; font-weight:600; margin-bottom:6px;
    }
    .cal-cell{
        border:1px solid rgba(255,255,255,0.1);
        border-radius:10px; padding:6px; min-height:92px; position:relative;
    }
    .cal-cell.outside{ opacity:.45 }
    .cal-date{ position:absolute; top:6px; right:8px; font-size:0.9rem; opacity:.8 }
    .resa-pill{
        display:block; margin-top:22px; margin-bottom:4px;
        padding:4px 6px; border-radius:999px; font-size:.85rem; white-space:nowrap;
        overflow:hidden; text-overflow:ellipsis; color:#111; background:#ddd;
    }
    </style>
    """, unsafe_allow_html=True)

    # En-têtes jours
    st.markdown(
        "<div class='cal-header'><div>Lun</div><div>Mar</div><div>Mer</div>"
        "<div>Jeu</div><div>Ven</div><div>Sam</div><div>Dim</div></div>",
        unsafe_allow_html=True
    )

    # Helper pour réservations couvrant un jour d
    def day_resas(d):
        mask = (dfv["date_arrivee"] <= d) & (dfv["date_depart"] > d)
        return dfv[mask]

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
                        color = palette.get(str(r.get("plateforme")), "#a3a3a3")
                        name = str(r.get("nom_client") or "")
                        name = escape(name)[:28]
                        title_txt = escape(str(r.get("numero_reservation") or ""), quote=True)
                        cell += (
                            "<span class='resa-pill' "
                            f"style='background:{color}'>"
                            f"{name}</span>"
                        )
            cell += "</div>"
            html_parts.append(cell)
    html_parts.append("</div>")
    st.markdown("".join(html_parts), unsafe_allow_html=True)

    st.markdown("---")
    # Détail du mois sélectionné
    debut_mois = date(annee, mois, 1)
    fin_mois = date(annee, mois, monthrange(annee, mois)[1])
    rows = dfv[(dfv["date_arrivee"] <= fin_mois) & (dfv["date_depart"] > debut_mois)].copy()
    rows = rows.sort_values(["date_arrivee", "nom_client"])
    st.subheader("Détail du mois sélectionné")
    st.dataframe(
        rows[[
            "numero_reservation", "nom_client", "plateforme",
            "date_arrivee", "date_depart", "nuitees", "telephone", "pays", "tarif"
        ]],
        use_container_width=True
    )

# ============================== FIN PARTIE 3/5 ==============================


# ============================== PARTIE 4/5 — RAPPORT, GOOGLE SHEET, CLIENTS, ID ==============================

# ---------------- RAPPORT / KPIs ----------------
def vue_rapport(df: pd.DataFrame, palette: dict):
    """Tableaux de bord et KPIs par plateforme et par pays (graphiques Streamlit)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"📊 Rapport — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune donnée disponible.")
        return

    dfr = ensure_schema(df).copy()
    dfr["date_arrivee"] = _to_date(dfr["date_arrivee"])
    dfr["date_depart"]  = _to_date(dfr["date_depart"])
    dfr["nuitees"]      = pd.to_numeric(dfr["nuitees"], errors="coerce").fillna(0).astype(int)
    dfr["revenu"]       = pd.to_numeric(dfr["tarif"],   errors="coerce").fillna(0.0)

    # KPIs
    total_resa    = int(len(dfr))
    total_nuitees = int(dfr["nuitees"].sum())
    total_revenu  = float(dfr["revenu"].sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Réservations", f"{total_resa}")
    c2.metric("Nuitées", f"{total_nuitees}")
    c3.metric("Revenu total", f"{total_revenu:,.0f} €".replace(",", " "))

    st.markdown("---")

    # Par plateforme
    agg = (
        dfr.groupby("plateforme", dropna=True)
           .agg(reservations=("plateforme", "count"),
                nuitees=("nuitees", "sum"),
                revenu_total=("revenu", "sum"))
           .reset_index()
           .sort_values("revenu_total", ascending=False)
    )
    if total_revenu > 0:
        agg["part_revenu_%"] = (agg["revenu_total"] / total_revenu * 100).round(1)
    else:
        agg["part_revenu_%"] = 0.0

    st.subheader("Par plateforme")
    st.dataframe(agg, use_container_width=True)

    # Graph: revenus par plateforme
    if not agg.empty:
        chart_df = agg.set_index("plateforme")[["revenu_total"]]
        st.bar_chart(chart_df, height=260)

    st.markdown("---")

    # Par pays (si présent)
    if "pays" in dfr.columns:
        agg_pays = (
            dfr.groupby("pays", dropna=True)
               .agg(reservations=("pays", "count"),
                    nuitees=("nuitees", "sum"),
                    revenu_total=("revenu", "sum"))
               .reset_index()
               .sort_values("revenu_total", ascending=False)
        )
        if total_revenu > 0:
            agg_pays["part_revenu_%"] = (agg_pays["revenu_total"] / total_revenu * 100).round(1)
        else:
            agg_pays["part_revenu_%"] = 0.0

        top = agg_pays.head(20)
        st.subheader("Top 20 pays (par CA net)")
        st.dataframe(top, use_container_width=True)

        if not top.empty:
            st.bar_chart(top.set_index("pays")[["revenu_total"]], height=300)


# ---------------- GOOGLE SHEET (placeholder) ----------------
def vue_google_sheet(df: pd.DataFrame, palette: dict):
    """Placeholder Google Sheet : export manuel en attendant l'intégration API."""
    st.header("📝 Google Sheet (bientôt)")
    st.info("Export automatique vers Google Sheets à venir. En attendant, vous pouvez exporter le CSV/XLSX depuis l’onglet **Paramètres** puis l’importer dans Google Sheets.")


# ---------------- CLIENTS ----------------
def vue_clients(df: pd.DataFrame, palette: dict):
    """Liste des clients + recalcul des pays à partir des téléphones."""
    st.header("👥 Clients")
    if df is None or df.empty:
        st.info("Aucun client.")
        return

    dfx = ensure_schema(df).copy()
    # Affichage
    st.dataframe(
        dfx[["nom_client", "telephone", "pays"]].fillna(""),
        use_container_width=True
    )

    st.markdown("### Outils")
    col1, col2 = st.columns([0.5, 0.5])
    if col1.button("🗺️ Recalculer tous les pays à partir des téléphones"):
        try:
            dfx["pays"] = dfx["telephone"].apply(_phone_country)
            if sauvegarder_donnees(dfx):
                st.success("Pays recalculés et enregistrés ✅")
                st.rerun()
        except Exception as e:
            st.error(f"Échec du recalcul : {e}")

    # Import d’un mapping (optionnel) : code, country, dial, flag
    up = col2.file_uploader("Importer un fichier indicatifs (CSV)", type=["csv"], key="clients_import_indicatifs")
    if up is not None:
        try:
            mapping = pd.read_csv(up, dtype=str).fillna("")
            # Normalisation minimale
            for c in ["code", "country", "dial", "flag"]:
                if c not in mapping.columns:
                    mapping[c] = ""
            mapping["dial"] = mapping["dial"].astype(str).str.strip()
            mapping.loc[~mapping["dial"].str.startswith("+") & mapping["dial"].ne(""), "dial"] = "+" + mapping["dial"].str.lstrip("+").str.strip()

            # On peut sauvegarder ce mapping comme fichier global d'indicatifs
            mapping.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8")
            st.success("Fichier indicatifs importé et enregistré ✅")
        except Exception as e:
            st.error(f"Import impossible : {e}")


# ---------------- ID ----------------
def vue_id(df: pd.DataFrame, palette: dict):
    """Affiche les numéros de réservation et identifiants uniques."""
    st.header("🆔 Identifiants")
    if df is None or df.empty:
        st.info("Aucun enregistrement.")
        return
    cols = [c for c in ["id", "numero_reservation", "plateforme"] if c in df.columns]
    st.dataframe(df[cols], use_container_width=True)

# ============================== FIN PARTIE 4/5 ==============================



# ============================== PARTIE 5/5 — SMS, INDICATEURS PAYS, PARAMETRES, MAIN ==============================

# ---------------- SMS ----------------
def vue_sms(df: pd.DataFrame, palette: dict):
    """SMS pré-arrivée (J+1) et post-départ — copier/coller + liens SMS/WhatsApp."""
    from urllib.parse import quote

    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"✉️ SMS — {apt_name}")
    print_buttons()

    if df is None or df.empty:
        st.info("Aucune réservation disponible.")
        return

    dfx = ensure_schema(df).copy()
    dfx["date_arrivee"] = _to_date(dfx["date_arrivee"])
    dfx["date_depart"]  = _to_date(dfx["date_depart"])

    # -------- Pré-arrivée (J+1) --------
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
            link_form = FORM_SHORT_URL
            nuitees = int(pd.to_numeric(r.get("nuitees"), errors="coerce") or 0)
            arr_txt = r["date_arrivee"].strftime("%d/%m/%Y") if pd.notna(r["date_arrivee"]) else ""
            dep_txt = r["date_depart"].strftime("%d/%m/%Y") if pd.notna(r["date_depart"]) else ""

            msg = (
                f"{apt_name.upper()}\n"
                f"Plateforme : {r.get('plateforme', 'N/A')}\n"
                f"Arrivée : {arr_txt}  Départ : {dep_txt}  Nuitées : {nuitees}\n\n"
                f"Bonjour {r.get('nom_client','')}\n"
                "Bienvenue chez nous !\n\n"
                "Nous sommes ravis de vous accueillir bientôt à Nice. Afin d'organiser au mieux votre réception, "
                "nous vous demandons de bien vouloir remplir la fiche en cliquant sur le lien suivant :\n"
                f"{link_form}\n\n"
                "Un parking est à votre disposition sur place.\n\n"
                "Le check-in se fait à partir de 14:00 et le check-out avant 11:00. Nous serons sur place lors de "
                "votre arrivée pour vous remettre les clés.\n\n"
                "Vous trouverez des consignes à bagages dans chaque quartier, à Nice.\n\n"
                "Nous vous souhaitons un excellent voyage et nous nous réjouissons de vous rencontrer très bientôt.\n\n"
                "Annick & Charley\n\n"
                "******\n\n"
                "Welcome to our establishment!\n\n"
                "We are delighted to welcome you soon to Nice. In order to organize your reception as efficiently as possible, "
                "we kindly ask you to fill out the form at the following link:\n"
                f"{link_form}\n\n"
                "Parking is available on site.\n\n"
                "Check-in is from 2:00 p.m. and check-out is before 11:00 a.m. We will be there when you arrive to give you the keys.\n\n"
                "You will find luggage storage facilities in every district of Nice.\n\n"
                "We wish you a pleasant journey and look forward to meeting you very soon.\n\n"
                "Annick & Charley"
            )

            st.text_area("📋 Copier le message", value=msg, height=360, key="pre_msg")
            e164 = _format_phone_e164(r.get("telephone", ""))
            only_digits = "".join(ch for ch in e164 if ch.isdigit())
            enc = quote(msg, safe="")
            c1, c2, c3 = st.columns(3)
            c1.link_button("📲 iPhone SMS", f"sms:&body={enc}", key="pre_sms_ios")
            c2.link_button("🤖 Android SMS", f"sms:{e164}?body={enc}", key="pre_sms_android")
            c3.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits}?text={enc}", key="pre_wa")

            if st.button("✅ Marquer 'SMS envoyé' pour ce client", key="pre_mark_sent"):
                try:
                    df.loc[r["index"], "sms_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")

    st.markdown("---")

    # -------- Post-départ (J0) --------
    st.subheader("📤 Post-départ (départs du jour)")
    target_depart = st.date_input("Départs du", date.today(), key="post_date")
    post = dfx.dropna(subset=["telephone", "nom_client", "date_depart"]).copy()
    post = post[(post["date_depart"] == target_depart) & (~_to_bool_series(post["post_depart_envoye"]))]

    if post.empty:
        st.info("Aucun message post-départ à envoyer aujourd’hui.")
    else:
        post = post.sort_values("date_depart").reset_index()
        options2 = [f"{i}: {r['nom_client']} — départ {r['date_depart']}" for i, r in post.iterrows()]
        pick2 = st.selectbox("Client (post-départ)", options=options2, index=None, key="post_pick")
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
                "Annick & Charley\n\n"
                f"Hello {name},\n\n"
                "Thank you very much for choosing our apartment for your stay.\n"
                "We hope you had a great time — our door is always open if you want to come back.\n\n"
                "Annick & Charley"
            )
            st.text_area("📋 Copier le message", value=msg2, height=280, key="post_msg")
            e164b = _format_phone_e164(r2.get("telephone", ""))
            only_digits_b = "".join(ch for ch in e164b if ch.isdigit())
            enc2 = quote(msg2, safe="")
            c1, c2, c3 = st.columns(3)
            c1.link_button("🟢 WhatsApp", f"https://wa.me/{only_digits_b}?text={enc2}", key="post_wa")
            c2.link_button("📲 iPhone SMS", f"sms:&body={enc2}", key="post_sms_ios")
            c3.link_button("🤖 Android SMS", f"sms:{e164b}?body={enc2}", key="post_sms_android")

            if st.button("✅ Marquer 'post-départ envoyé' pour ce client", key="post_mark_sent"):
                try:
                    df.loc[r2["index"], "post_depart_envoye"] = True
                    if sauvegarder_donnees(df):
                        st.success("Marqué ✅")
                        st.rerun()
                except Exception as e:
                    st.error(f"Impossible de marquer : {e}")


# ---------------- INDICATEURS / INDICATIFS PAYS ----------------
def _load_indicatifs_df() -> pd.DataFrame:
    """Charge le CSV d'indicatifs pays (crée un squelette si absent)."""
    path = INDICATIFS_CSV if os.path.exists(INDICATIFS_CSV) else "indicatifs_pays.csv"
    if not os.path.exists(path):
        base = pd.DataFrame(
            [
                {"code": "FR", "country": "France", "dial": "+33", "flag": "🇫🇷"},
                {"code": "GB", "country": "United Kingdom", "dial": "+44", "flag": "🇬🇧"},
                {"code": "ES", "country": "Spain", "dial": "+34", "flag": "🇪🇸"},
            ]
        )
        try:
            base.to_csv(path, index=False, encoding="utf-8")
        except Exception:
            return base
    try:
        return pd.read_csv(path, dtype=str).fillna("")
    except Exception:
        return pd.DataFrame(columns=["code", "country", "dial", "flag"])


def _save_indicatifs_df(df_in: pd.DataFrame) -> bool:
    """Valide et sauvegarde le CSV des indicatifs."""
    try:
        df = df_in.copy()
        for c in ["code", "country", "dial", "flag"]:
            if c not in df.columns:
                df[c] = ""
        df = df[["code", "country", "dial", "flag"]]

        df["code"]    = df["code"].astype(str).str.strip().str.upper()
        df["country"] = df["country"].astype(str).str.strip()
        df["dial"]    = df["dial"].astype(str).str.strip()
        df["flag"]    = df["flag"].astype(str).str.strip()

        df = df[df["code"] != ""]
        df = df.drop_duplicates(subset=["code"], keep="first")
        df.loc[~df["dial"].str.startswith("+") & df["dial"].ne(""), "dial"] = "+" + df["dial"].str.lstrip("+").str.strip()

        df.to_csv(INDICATIFS_CSV, index=False, encoding="utf-8")
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde des indicatifs : {e}")
        return False


def vue_indicatifs(df: pd.DataFrame, palette: dict):
    """Édition et rechargement des indicatifs pays (code, country, dial, flag)."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header(f"🌍 Indicateurs pays — {apt_name}")
    st.caption("Ajoutez/éditez les pays, indicatifs et drapeaux. Le CSV est chargé et sauvegardé sur disque.")

    base = _load_indicatifs_df()
    with st.expander("Aperçu", expanded=True):
        st.dataframe(base, use_container_width=True)

    st.markdown("### Modifier")
    edited = st.data_editor(
        base,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "code": st.column_config.TextColumn("Code (ISO2)"),
            "country": st.column_config.TextColumn("Pays"),
            "dial": st.column_config.TextColumn("Indicatif (+NN)"),
            "flag": st.column_config.TextColumn("Drapeau (emoji)"),
        },
        key="indicatifs_editor",
    )

    c1, c2, c3 = st.columns([0.4, 0.3, 0.3])
    if c1.button("💾 Enregistrer", key="btn_save_indicatifs"):
        if _save_indicatifs_df(edited):
            st.success("Indicatifs sauvegardés ✅")

    if c2.button("🔄 Recharger depuis le disque", key="btn_reload_indicatifs"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    if c3.button("↩️ Restaurer FR/GB/ES (mini)", key="btn_restore_min_indicatifs"):
        mini = pd.DataFrame(
            [
                {"code": "FR", "country": "France", "dial": "+33", "flag": "🇫🇷"},
                {"code": "GB", "country": "United Kingdom", "dial": "+44", "flag": "🇬🇧"},
                {"code": "ES", "country": "Spain", "dial": "+34", "flag": "🇪🇸"},
            ]
        )
        if _save_indicatifs_df(mini):
            st.success("Mini-jeu de données restauré ✅")
            st.rerun()


# ---------------- PARAMÈTRES ----------------
def vue_settings(df: pd.DataFrame, palette: dict):
    """Sauvegarde / restauration des données + maintenance apartments.csv + cache."""
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.header("## ⚙️ Paramètres")
    st.subheader(apt_name)
    print_buttons()
    st.caption("Sauvegarde, restauration, cache et outil secours pour apartments.csv.")

    # Export CSV
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
        file_name=os.path.basename(st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)),
        mime="text/csv",
        key="dl_res_csv",
    )

    # Export XLSX
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
        file_name=(os.path.splitext(os.path.basename(st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)))[0] + ".xlsx"),
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(xlsx_bytes is None),
        key="dl_res_xlsx",
    )

    # Restauration
    st.markdown("### ♻️ Restauration (remplacer les données)")
    up = st.file_uploader("Restaurer (CSV ou XLSX)", type=["csv", "xlsx"], key="restore_uploader_settings")
    if up is not None:
        try:
            if up.name.lower().endswith(".xlsx"):
                xls = pd.ExcelFile(up)
                sheet = st.selectbox("Feuille Excel", xls.sheet_names, index=0, key="restore_sheet_settings")
                tmp = pd.read_excel(xls, sheet_name=sheet, dtype=str)
            else:
                raw = up.read()
                tmp = _detect_delimiter_and_read(raw)

            prev = ensure_schema(tmp)
            st.success(f"Aperçu chargé ({up.name})")
            with st.expander("Aperçu (10 premières lignes)", expanded=False):
                st.dataframe(prev.head(10), use_container_width=True)

            if st.button("✅ Confirmer la restauration", key="confirm_restore_settings"):
                try:
                    save = prev.copy()
                    for col in ["date_arrivee", "date_depart"]:
                        save[col] = pd.to_datetime(save[col], errors="coerce").dt.strftime("%d/%m/%Y")
                    target_csv = st.session_state.get("CSV_RESERVATIONS", CSV_RESERVATIONS)
                    save.to_csv(target_csv, sep=";", index=False, encoding="utf-8", lineterminator="\n")
                    st.cache_data.clear()
                    st.success("Fichier restauré — rechargement…")
                    st.rerun()
                except Exception as e:
                    st.error(f"Erreur écriture : {e}")
        except Exception as e:
            st.error(f"Erreur restauration : {e}")

    # Cache
    st.markdown("### 🧹 Vider le cache")
    if st.button("Vider le cache & recharger", key="clear_cache_btn_settings"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.rerun()

    # Outil secours apartments.csv
    st.markdown("### 🧰 Écraser apartments.csv (outil secours)")
    default_csv = "slug,name\nvilla-tobias,Villa Tobias\nle-turenne,Le Turenne\n"
    txt = st.text_area("Contenu apartments.csv", value=default_csv, height=140, key="force_apts_txt_settings")
    if st.button("🧰 Écraser apartments.csv", key="force_apts_btn_settings"):
        try:
            with open(APARTMENTS_CSV, "w", encoding="utf-8", newline="") as f:
                f.write(txt.strip() + "\n")
            st.cache_data.clear()
            st.success("apartments.csv écrasé ✅ — rechargement…")
            st.rerun()
        except Exception as e:
            st.error(f"Impossible d'écrire apartments.csv : {e}")


# ---------------- MAIN ----------------
def main():
    # Reset cache via URL ?clear=1
    params = st.query_params
    if params.get("clear", ["0"])[0] in ("1", "true", "True", "yes"):
        try:
            st.cache_data.clear()
        except Exception:
            pass

    # Sélecteur d'appartement (actualise chemins actifs)
    changed = _select_apartment_sidebar()
    if changed:
        try:
            st.cache_data.clear()
        except Exception:
            pass

    # Thème (applique CSS et couleurs)
    try:
        mode_clair = st.sidebar.toggle("🌓 Mode clair (PC)", value=False)
    except Exception:
        mode_clair = st.sidebar.checkbox("🌓 Mode clair (PC)", value=False)
    apply_style(light=bool(mode_clair))

    # En-tête
    apt = _current_apartment()
    apt_name = apt["name"] if apt else "—"
    st.title(f"✨ {apt_name} — Gestion des Réservations")

    # Données + palette
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
# ============================== FIN PARTIE 5/5 ==============================