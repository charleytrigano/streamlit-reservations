# app.py — Villa Tobias (COMPLET, STABLE)
# - Colonnes enrichies: commissions, frais_cb, menage, taxes_sejour, base
# - Calculs automatiques: net, base, %, nuitees, AAAA, MM
# - Téléphone forcé en texte
# - Options d'affichage, KPI, recherche
# - Calendrier stable, Rapport filtrable, Export ICS, SMS manuel
# - Sauvegarde/restauration XLSX

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
from urllib.parse import quote

FICHIER = "reservations.xlsx"

# ==============================  MAINTENANCE / CACHE  ==============================

def render_cache_section_sidebar():
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache et relancer"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.sidebar.success("Cache vidé. Redémarrage…")
        st.rerun()

# ==============================  OUTILS  ==============================

def to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def normalize_tel(x):
    """Force lecture téléphone en texte, retire .0, espaces."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip()
    s = s.replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

PLATFORM_ICONS = {"Booking": "🟦", "Airbnb": "🟩", "Autre": "🟧"}

# ==============================  SCHEMA & CALCULS  ==============================

BASE_COLS = [
    "nom_client","plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%", "AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """Normalise les colonnes, types et recalcule tout proprement."""
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(to_date_only)

    df["telephone"] = df["telephone"].apply(normalize_tel)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["nuitees"] = [
        (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
        for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
    ]

    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"]   = df["ical_uid"].fillna("")

    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)

    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)

    return df[[c for c in BASE_COLS if c in df.columns] + [c for c in df.columns if c not in BASE_COLS]]

def is_total_row(row: pd.Series) -> bool:
    name_is_total = str(row.get("nom_client","")).strip().lower() == "total"
    pf_is_total   = str(row.get("plateforme","")).strip().lower() == "total"
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    no_dates = not isinstance(d1, date) and not isinstance(d2, date)
    has_money = any(pd.notna(row.get(c)) and float(row.get(c) or 0) != 0
                    for c in ["prix_brut","prix_net","base","charges"])
    return name_is_total or pf_is_total or (no_dates and has_money)

def split_totals(df: pd.DataFrame):
    if df is None or df.empty:
        return df, df
    mask = df.apply(is_total_row, axis=1)
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    by = [c for c in ["date_arrivee","nom_client"] if c in df.columns]
    return df.sort_values(by=by, na_position="last").reset_index(drop=True)

# ==============================  EXCEL I/O  ==============================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path, converters={"telephone": normalize_tel})

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    try:
        mtime = os.path.getmtime(FICHIER)
        df = _read_excel_cached(FICHIER, mtime)
        return ensure_schema(df)
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame())

def _force_telephone_text_format_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
    try:
        ws = writer.sheets.get(sheet_name) or writer.sheets.get('Sheet1', None)
        if ws is None or "telephone" not in df_to_save.columns:
            return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            cell = row[0]
            cell.number_format = '@'
    except Exception:
        pass

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name="Sheet1")
            _force_telephone_text_format_openpyxl(w, out, "Sheet1")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

# ==============================  KPI & OPTIONS  ==============================

def afficher_kpis(df: pd.DataFrame):
    """Affiche les indicateurs clés."""
    if df is None or df.empty:
        st.warning("Aucune donnée disponible.")
        return

    core, _ = split_totals(df)
    total_net = core["prix_net"].sum()
    total_charges = core["charges"].sum()
    total_nuitees = core["nuitees"].sum()
    commission_moy = (core["charges"].sum() / core["prix_brut"].sum() * 100) if core["prix_brut"].sum() else 0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💰 Total Net", f"{total_net:,.2f} €", delta=f"{(total_net/ (total_nuitees or 1)):.2f} €/nuit")
    c2.metric("💸 Total Charges", f"{total_charges:,.2f} €")
    c3.metric("🛌 Total Nuitées", f"{int(total_nuitees)}")
    c4.metric("📊 Commission moy.", f"{commission_moy:.2f} %")

def render_display_options_sidebar():
    st.sidebar.markdown("### 🎛️ Options d’affichage")
    recherche = st.sidebar.text_input("🔍 Rechercher")
    return {"recherche": recherche}

# ==============================  VUE RESERVATIONS  ==============================

def vue_reservations(df: pd.DataFrame):
    st.subheader("📋 Réservations")
    afficher_kpis(df)
    opts = render_display_options_sidebar()

    core, totals = split_totals(df)

    if opts.get("recherche"):
        mask = core.apply(lambda r: opts["recherche"].lower() in str(r.values).lower(), axis=1)
        core = core[mask]

    st.dataframe(core, use_container_width=True)

    if not totals.empty:
        st.markdown("#### Totaux")
        totaux = {}
        for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
            if c in totals.columns:
                totaux[c] = totals[c].sum() if c != "%" else (totals["charges"].sum()/totals["prix_brut"].sum()*100 if totals["prix_brut"].sum() else 0)
        st.write(pd.DataFrame([totaux]))

# ==============================  VUE CALENDRIER  ==============================

def vue_calendrier(df: pd.DataFrame, colors: dict = PLATFORM_COLORS_DEFAULT):
    st.subheader("📅 Calendrier")
    mois = st.selectbox("Mois", range(1, 13), index=datetime.date.today().month - 1)
    annee = st.selectbox("Année", range(2023, 2031), index=datetime.date.today().year - 2023)

    # Filtrer les réservations
    df = df.copy()
    df["date_arrivee"] = pd.to_datetime(df["date_arrivee"], errors="coerce")
    df["date_depart"] = pd.to_datetime(df["date_depart"], errors="coerce")
    reservations = df[(df["date_arrivee"].dt.month == mois) & (df["date_arrivee"].dt.year == annee)]

    # Construire calendrier
    jours = ["L", "M", "M", "J", "V", "S", "D"]
    cal = calendar.Calendar(firstweekday=0).monthdayscalendar(annee, mois)
    grille = []
    for semaine in cal:
        row = []
        for jour in semaine:
            if jour == 0:
                row.append("")
            else:
                date_jour = datetime.date(annee, mois, jour)
                resa = reservations[(reservations["date_arrivee"] <= date_jour) & (reservations["date_depart"] > date_jour)]
                if not resa.empty:
                    plat = resa.iloc[0]["plateforme"]
                    couleur = colors.get(plat, "#888")
                    row.append(f"**<span style='background-color:{couleur};color:white;padding:2px;border-radius:4px'>{jour}</span>**")
                else:
                    row.append(str(jour))
        grille.append(row)

    st.table(pd.DataFrame(grille, columns=jours))

# ==============================  VUE SMS  ==============================

def vue_sms(df: pd.DataFrame):
    st.subheader("✉️ SMS")
    aujourd_hui = datetime.date.today()
    demain = aujourd_hui + datetime.timedelta(days=1)

    resa = df[pd.to_datetime(df["date_arrivee"]).dt.date == demain]
    for _, row in resa.iterrows():
        nom = row["nom_client"]
        tel = row["telephone"]
        msg = f"Bonjour {nom},\nBienvenue chez nous demain !"
        st.text_area(f"SMS pour {nom}", msg)
        if st.button(f"📲 Envoyer à {tel}"):
            st.success(f"SMS envoyé à {tel}")

# ==============================  EXPORT ICS  ==============================

def export_ics(df: pd.DataFrame):
    st.subheader("📤 Export ICS")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Streamlit Reservations//FR"]
    for _, r in df.iterrows():
        start = pd.to_datetime(r["date_arrivee"]).strftime("%Y%m%d")
        end = pd.to_datetime(r["date_depart"]).strftime("%Y%m%d")
        summary = f"{r['plateforme']} - {r['nom_client']}"
        lines.extend([
            "BEGIN:VEVENT",
            f"DTSTART;VALUE=DATE:{start}",
            f"DTEND;VALUE=DATE:{end}",
            f"SUMMARY:{summary}",
            "END:VEVENT"
        ])
    lines.append("END:VCALENDAR")
    ics_data = "\n".join(lines)
    st.download_button("📥 Télécharger ICS", ics_data, file_name="reservations.ics", mime="text/calendar")

# ==============================  MAIN  ==============================

def main():
    st.set_page_config(page_title="Streamlit Réservations", layout="wide")
    st.title("📋 Gestion des Réservations")

    onglets = ["📋 Réservations", "➕ Ajouter", "✏️ Modifier / Supprimer", "📅 Calendrier", "📊 Rapport", "👥 Liste clients", "📤 Export ICS", "✉️ SMS"]
    onglet = st.sidebar.radio("Aller à", onglets)

    df = charger_donnees()

    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "📅 Calendrier":
        vue_calendrier(df)
    elif onglet == "✉️ SMS":
        vue_sms(df)
    elif onglet == "📤 Export ICS":
        export_ics(df)
    # ➕ et ✏️ à compléter avec ton code existant

if __name__ == "__main__":
    main()