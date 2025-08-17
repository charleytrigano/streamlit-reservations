import streamlit as st
import pandas as pd
import numpy as np
import io
import os
from datetime import datetime, timedelta
import calendar

# ==============================
# Configuration
# ==============================
FICHIER_EXCEL = "reservations.xlsx"

PLATFORM_COLORS_DEFAULT = {
    "Booking": "#1E90FF",
    "Airbnb": "#FF5A5F",
    "Abritel": "#8A2BE2",
    "Autre": "#2E8B57"
}

# ==============================
# Fonctions utilitaires
# ==============================
def charger_donnees():
    if os.path.exists(FICHIER_EXCEL):
        df = pd.read_excel(FICHIER_EXCEL)
        return df
    else:
        colonnes = [
            "appartement", "plateforme", "nom", "telephone",
            "date_arrivee", "date_depart", "nuitees",
            "prix_brut", "commissions", "frais_cb",
            "prix_net", "menage", "taxes_sejour",
            "base", "pct"
        ]
        return pd.DataFrame(columns=colonnes)

def sauvegarder_donnees(df: pd.DataFrame):
    df.to_excel(FICHIER_EXCEL, index=False)

def calculs(df: pd.DataFrame) -> pd.DataFrame:
    if "prix_brut" in df.columns and "commissions" in df.columns and "frais_cb" in df.columns:
        df["prix_net"] = df["prix_brut"] - df["commissions"] - df["frais_cb"]
    if "prix_net" in df.columns and "menage" in df.columns and "taxes_sejour" in df.columns:
        df["base"] = df["prix_net"] - df["menage"] - df["taxes_sejour"]
    if "prix_brut" in df.columns and "prix_net" in df.columns:
        df["pct"] = ((df["prix_brut"] - df["prix_net"]) / df["prix_brut"] * 100).round(2)
    return df

# ==============================
# Vues
# ==============================
def vue_reservations(df: pd.DataFrame):
    st.subheader("📋 Réservations")
    st.dataframe(df, use_container_width=True)

def vue_rapport(df: pd.DataFrame):
    st.subheader("📊 Rapport")
    total_brut = df["prix_brut"].sum()
    total_net = df["prix_net"].sum()
    total_base = df["base"].sum()
    total_charges = (df["commissions"] + df["frais_cb"]).sum()
    total_nuitees = df["nuitees"].sum()
    prix_moyen_nuit = round(total_brut / total_nuitees, 2) if total_nuitees > 0 else 0
    pct_comm_moy = round((total_charges / total_brut * 100), 2) if total_brut > 0 else 0

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric("💰 Total Brut", f"{total_brut:,.2f} €")
    c2.metric("💶 Total Net", f"{total_net:,.2f} €")
    c3.metric("📉 Total Base", f"{total_base:,.2f} €")
    c4.metric("💸 Charges", f"{total_charges:,.2f} €")
    c5.metric("🛌 Nuitées", f"{total_nuitees}")
    c6.metric("💤 Prix/nuit", f"{prix_moyen_nuit:,.2f} €")

    st.metric("📊 Commission Moy.", f"{pct_comm_moy} %")

def vue_calendrier(df: pd.DataFrame, colors: dict = PLATFORM_COLORS_DEFAULT):
    st.subheader("📅 Calendrier mensuel")
    mois = st.selectbox("Mois", list(calendar.month_name)[1:], index=datetime.now().month - 1)
    annee = st.number_input("Année", value=datetime.now().year, step=1)
    mois_num = list(calendar.month_name).index(mois)
    jours_dans_mois = calendar.monthrange(annee, mois_num)[1]

    # Création du calendrier
    grille = []
    headers = ["L", "M", "M", "J", "V", "S", "D"]
    cal = calendar.Calendar(firstweekday=0)
    for semaine in cal.monthdatescalendar(annee, mois_num):
        row = []
        for jour in semaine:
            if jour.month == mois_num:
                resa = df[(df["date_arrivee"] <= jour.strftime("%Y-%m-%d")) &
                          (df["date_depart"] > jour.strftime("%Y-%m-%d"))]
                if not resa.empty:
                    plateforme = resa.iloc[0]["plateforme"]
                    couleur = colors.get(plateforme, "#CCCCCC")
                    row.append(f"{jour.day} ({plateforme})")
                else:
                    row.append(str(jour.day))
            else:
                row.append("")
        grille.append(row)

    st.table(pd.DataFrame(grille, columns=headers))

# ==============================
# Application principale
# ==============================
def main():
    st.set_page_config(page_title="🏠 Réservations", layout="wide")

    # ✅ Ajout du logo en haut
    st.image("logo.png", width=180)

    st.sidebar.title("📁 Fichier")
    df = charger_donnees()
    df = calculs(df)

    onglet = st.sidebar.radio("Aller à", ["📋 Réservations", "📊 Rapport", "📅 Calendrier"])

    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "📊 Rapport":
        vue_rapport(df)
    elif onglet == "📅 Calendrier":
        vue_calendrier(df)

if __name__ == "__main__":
    main()

# ==============================
# >>> Partie 2 : version complète des vues & calculs <<<
# (Les fonctions ci-dessous redéfinissent/complètent celles de la partie 1)
# ==============================

from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
from urllib.parse import quote

# ---------- Outils cohérents ----------
def _to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def _format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def _normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

BASE_COLS = [
    "nom", "plateforme", "telephone",
    "date_arrivee", "date_depart", "nuitees",
    "prix_brut", "commissions", "frais_cb", "prix_net",
    "menage", "taxes_sejour", "base",
    "charges", "pct", "AAAA", "MM", "ical_uid"
]

def _ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = pd.NA

    # dates
    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(_to_date_only)

    # téléphone
    df["telephone"] = df["telephone"].apply(_normalize_tel)

    # numériques
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","pct","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # nuitées
    df["nuitees"] = [
        (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else pd.NA
        for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
    ]

    # AAAA/MM
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else pd.NA).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else pd.NA).astype("Int64")

    # défauts
    df["nom"] = df["nom"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"] = df["ical_uid"].fillna("")

    # NaN -> 0 pour calculs de base
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    # Calculs officiels (cohérents avec ta version stable) :
    # prix_net = prix_brut - commissions - frais_cb
    # base     = prix_net - menage - taxes_sejour
    # charges  = commissions + frais_cb
    # pct      = (charges / prix_brut) * 100
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["commissions"] + df["frais_cb"]).clip(lower=0)

    with pd.option_context("mode.use_inf_as_na", True):
        df["pct"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    # arrondis
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","pct"]:
        df[c] = df[c].round(2)

    return df

def _split_totals(df: pd.DataFrame):
    def is_total_row(row: pd.Series) -> bool:
        name_is_total = str(row.get("nom","")).strip().lower() == "total"
        pf_is_total   = str(row.get("plateforme","")).strip().lower() == "total"
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        no_dates = not isinstance(d1, date) and not isinstance(d2, date)
        has_money = any(pd.notna(row.get(c)) and float(row.get(c) or 0) != 0
                        for c in ["prix_brut","prix_net","base","charges"])
        return name_is_total or pf_is_total or (no_dates and has_money)

    if df is None or df.empty:
        return df, df
    mask = df.apply(is_total_row, axis=1)
    return df[~mask].copy(), df[mask].copy()

def _sort_core(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    by = [c for c in ["date_arrivee","nom"] if c in df.columns]
    return df.sort_values(by=by, na_position="last").reset_index(drop=True)

# ---------- Lecture / écriture fichier ----------
def _read_file() -> pd.DataFrame:
    if os.path.exists(FICHIER_EXCEL):
        try:
            df = pd.read_excel(FICHIER_EXCEL, converters={"telephone": _normalize_tel})
        except Exception:
            df = pd.read_excel(FICHIER_EXCEL)
        return _ensure_schema(df)
    return _ensure_schema(pd.DataFrame())

def _save_file(df: pd.DataFrame):
    df = _ensure_schema(df)
    core, totals = _split_totals(df)
    core = _sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)
    out.to_excel(FICHIER_EXCEL, index=False)

# ==============================
# KPI + Recherche
# ==============================
def _kpi_chips(df: pd.DataFrame):
    core, _ = _split_totals(df)
    if core.empty:
        return
    b    = core["prix_brut"].sum()
    n    = core["prix_net"].sum()
    base = core["base"].sum()
    ch   = (core["commissions"].sum() + core["frais_cb"].sum())
    nuits= core["nuitees"].sum()
    pct  = (ch / b * 100) if b else 0
    pm_nuit = (b / nuits) if nuits else 0

    html = f"""
    <style>
    .chips-wrap {{ display:flex; flex-wrap:wrap; gap:8px; margin:6px 0 10px 0; }}
    .chip {{ padding:8px 10px; border-radius:10px; background: rgba(127,127,127,0.12); border: 1px solid rgba(127,127,127,0.25); font-size:0.9rem; }}
    .chip b {{ display:block; margin-bottom:3px; font-size:0.85rem; opacity:0.8; }}
    .chip .v {{ font-weight:600; }}
    </style>
    <div class="chips-wrap">
      <div class="chip"><b>Total Brut</b><div class="v">{b:,.2f} €</div></div>
      <div class="chip"><b>Total Net</b><div class="v">{n:,.2f} €</div></div>
      <div class="chip"><b>Total Base</b><div class="v">{base:,.2f} €</div></div>
      <div class="chip"><b>Total Charges</b><div class="v">{ch:,.2f} €</div></div>
      <div class="chip"><b>Nuitées</b><div class="v">{int(nuits) if pd.notna(nuits) else 0}</div></div>
      <div class="chip"><b>Commission moy.</b><div class="v">{pct:.2f} %</div></div>
      <div class="chip"><b>Prix moyen/nuit</b><div class="v">{pm_nuit:,.2f} €</div></div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def _search_box(df: pd.DataFrame) -> pd.DataFrame:
    q = st.text_input("🔎 Recherche (nom, plateforme, téléphone…)", "")
    if not q:
        return df
    ql = q.strip().lower()
    def _match(v):
        s = "" if pd.isna(v) else str(v)
        return ql in s.lower()
    mask = (
        df["nom"].apply(_match) |
        df["plateforme"].apply(_match) |
        df["telephone"].apply(_match)
    )
    return df[mask].copy()

# ==============================
# ICS export helpers
# ==============================
def _ics_escape(text: str) -> str:
    if text is None:
        return ""
    s = str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    return s

def _fmt_date_ics(d: date) -> str:
    return d.strftime("%Y%m%d")

def _dtstamp_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def _stable_uid(nom, plateforme, d1, d2, tel, salt="v1"):
    base = f"{nom}|{plateforme}|{d1}|{d2}|{tel}|{salt}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return f"vt-{h}@reservations"

def df_to_ics(df: pd.DataFrame, cal_name: str = "Réservations") -> str:
    df = _ensure_schema(df)
    core, _ = _split_totals(df)
    core = _sort_core(core)

    lines = []
    A = lines.append
    A("BEGIN:VCALENDAR")
    A("VERSION:2.0")
    A("PRODID:-//Reservations//FR")
    A(f"X-WR-CALNAME:{_ics_escape(cal_name)}")
    A("CALSCALE:GREGORIAN")
    A("METHOD:PUBLISH")

    for _, row in core.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        plateforme = str(row.get("plateforme") or "").strip()
        nom = str(row.get("nom") or "").strip()
        tel = str(row.get("telephone") or "").strip()
        summary = " - ".join([x for x in [plateforme, nom, tel] if x])
        brut = float(row.get("prix_brut") or 0)
        net  = float(row.get("prix_net")  or 0)
        nuitees = int(row.get("nuitees") or ((d2 - d1).days))

        desc = (
            f"Plateforme: {plateforme}\\n"
            f"Client: {nom}\\n"
            f"Téléphone: {tel}\\n"
            f"Arrivee: {d1.strftime('%Y/%m/%d')}\\n"
            f"Depart: {d2.strftime('%Y/%m/%d')}\\n"
            f"Nuitees: {nuitees}\\n"
            f"Brut: {brut:.2f} €\\nNet: {net:.2f} €"
        )

        uid_existing = str(row.get("ical_uid") or "").strip()
        uid = uid_existing if uid_existing else _stable_uid(nom, plateforme, d1, d2, tel)

        A("BEGIN:VEVENT")
        A(f"UID:{_ics_escape(uid)}")
        A(f"DTSTAMP:{_dtstamp_utc_now()}")
        A(f"DTSTART;VALUE=DATE:{_fmt_date_ics(d1)}")
        A(f"DTEND;VALUE=DATE:{_fmt_date_ics(d2)}")
        A(f"SUMMARY:{_ics_escape(summary)}")
        A(f"DESCRIPTION:{_ics_escape(desc)}")
        A("END:VEVENT")

    A("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

# ==============================
# VUES COMPLETES
# ==============================
def vue_reservations(df: pd.DataFrame):
    st.subheader("📋 Réservations")
    df = _ensure_schema(df)
    with st.expander("🎛️ Options d’affichage", expanded=True):
        show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)
    if show_kpi:
        _kpi_chips(df)
    if enable_search:
        df = _search_box(df)

    core, totals = _split_totals(df)
    core = _sort_core(core)
    show = pd.concat([core, totals], ignore_index=True)
    for c in ["date_arrivee","date_depart"]:
        show[c] = show[c].apply(_format_date_str)

    cols = ["nom","plateforme","telephone","date_arrivee","date_depart","nuitees",
            "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
            "base","charges","pct","AAAA","MM"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.subheader("➕ Ajouter une réservation")
    st.caption("Saisie compacte (libellés inline)")

    def inline_input(label, widget_fn, key=None, **widget_kwargs):
        col1, col2 = st.columns([1,2])
        with col1: st.markdown(f"**{label}**")
        with col2: return widget_fn(label, key=key, label_visibility="collapsed", **widget_kwargs)

    nom = inline_input("Nom", st.text_input, key="add_nom", value="")
    tel = inline_input("Téléphone (+33...)", st.text_input, key="add_tel", value="")
    plateforme = inline_input("Plateforme", st.selectbox, key="add_pf",
                              options=["Booking","Airbnb","Autre"], index=0)

    arrivee = inline_input("Arrivée", st.date_input, key="add_arrivee", value=date.today())
    min_dep = arrivee + timedelta(days=1)
    depart  = inline_input("Départ",  st.date_input, key="add_depart",
                           value=min_dep, min_value=min_dep)

    brut = inline_input("Prix brut (€)", st.number_input, key="add_brut",
                        min_value=0.0, step=1.0, format="%.2f")
    commissions = inline_input("Commissions (€)", st.number_input, key="add_comm",
                               min_value=0.0, step=1.0, format="%.2f")
    frais_cb = inline_input("Frais CB (€)", st.number_input, key="add_cb",
                            min_value=0.0, step=1.0, format="%.2f")

    net_calc = max(float(brut) - float(commissions) - float(frais_cb), 0.0)
    inline_input("Prix net (calculé)", st.number_input, key="add_net",
                 value=round(net_calc,2), step=0.01, format="%.2f", disabled=True)

    menage = inline_input("Ménage (€)", st.number_input, key="add_menage",
                          min_value=0.0, step=1.0, format="%.2f")
    taxes  = inline_input("Taxes séjour (€)", st.number_input, key="add_taxes",
                          min_value=0.0, step=1.0, format="%.2f")

    base_calc    = max(net_calc - float(menage) - float(taxes), 0.0)
    charges_calc = float(commissions) + float(frais_cb)
    pct_calc     = (charges_calc / float(brut) * 100) if float(brut) > 0 else 0.0

    inline_input("Base (calculée)", st.number_input, key="add_base",
                 value=round(base_calc,2), step=0.01, format="%.2f", disabled=True)
    inline_input("Commission (%)", st.number_input, key="add_pct",
                 value=round(pct_calc,2), step=0.01, format="%.2f", disabled=True)

    if st.button("Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        ligne = {
            "nom": (nom or "").strip(),
            "plateforme": plateforme,
            "telephone": _normalize_tel(tel),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": float(brut),
            "commissions": float(commissions),
            "frais_cb": float(frais_cb),
            "prix_net": round(net_calc, 2),
            "menage": float(menage),
            "taxes_sejour": float(taxes),
            "base": round(base_calc, 2),
            "charges": round(charges_calc, 2),
            "pct": round(pct_calc, 2),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month,
            "ical_uid": ""
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        _save_file(df2)
        st.success("✅ Réservation enregistrée")
        st.rerun()

def vue_modifier(df: pd.DataFrame):
    st.subheader("✏️ Modifier / Supprimer")
    df = _ensure_schema(df)
    if df.empty:
        st.info("Aucune réservation.")
        return

    df["identifiant"] = df["nom"].astype(str) + " | " + df["date_arrivee"].apply(_format_date_str)
    choix = st.selectbox("Choisir une réservation", df["identifiant"])
    idx = df.index[df["identifiant"] == choix]
    if len(idx) == 0:
        st.warning("Sélection invalide.")
        return
    i = idx[0]

    col = st.columns(2)
    nom = col[0].text_input("Nom", df.at[i, "nom"])
    tel = col[1].text_input("Téléphone", _normalize_tel(df.at[i, "telephone"]))
    plateforme = st.selectbox("Plateforme", ["Booking","Airbnb","Autre"],
                              index = ["Booking","Airbnb","Autre"].index(df.at[i,"plateforme"]) if df.at[i,"plateforme"] in ["Booking","Airbnb","Autre"] else 2)

    arrivee = st.date_input("Arrivée", df.at[i,"date_arrivee"] if isinstance(df.at[i,"date_arrivee"], date) else date.today())
    depart  = st.date_input("Départ",  df.at[i,"date_depart"] if isinstance(df.at[i,"date_depart"], date) else arrivee + timedelta(days=1), min_value=arrivee+timedelta(days=1))

    c1, c2, c3 = st.columns(3)
    brut = c1.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i,"prix_brut"]) if pd.notna(df.at[i,"prix_brut"]) else 0.0, step=1.0, format="%.2f")
    commissions = c2.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i,"commissions"]) if pd.notna(df.at[i,"commissions"]) else 0.0, step=1.0, format="%.2f")
    frais_cb = c3.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i,"frais_cb"]) if pd.notna(df.at[i,"frais_cb"]) else 0.0, step=1.0, format="%.2f")

    net_calc = max(brut - commissions - frais_cb, 0.0)

    d1, d2, d3 = st.columns(3)
    menage = d1.number_input("Ménage (€)", min_value=0.0, value=float(df.at[i,"menage"]) if pd.notna(df.at[i,"menage"]) else 0.0, step=1.0, format="%.2f")
    taxes  = d2.number_input("Taxes séjour (€)", min_value=0.0, value=float(df.at[i,"taxes_sejour"]) if pd.notna(df.at[i,"taxes_sejour"]) else 0.0, step=1.0, format="%.2f")
    base_calc = max(net_calc - menage - taxes, 0.0)

    charges_calc = float(commissions) + float(frais_cb)
    pct_calc = (charges_calc / brut * 100) if brut > 0 else 0.0
    d3.markdown(f"**Net (calculé)**: {net_calc:.2f} €  \n**Base (calculée)**: {base_calc:.2f} €  \n**%**: {pct_calc:.2f}")

    c_save, c_del = st.columns(2)
    if c_save.button("💾 Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        df.at[i,"nom"] = nom.strip()
        df.at[i,"plateforme"] = plateforme
        df.at[i,"telephone"]  = _normalize_tel(tel)
        df.at[i,"date_arrivee"] = arrivee
        df.at[i,"date_depart"]  = depart
        df.at[i,"prix_brut"] = float(brut)
        df.at[i,"commissions"] = float(commissions)
        df.at[i,"frais_cb"] = float(frais_cb)
        df.at[i,"prix_net"]  = round(net_calc, 2)
        df.at[i,"menage"] = float(menage)
        df.at[i,"taxes_sejour"] = float(taxes)
        df.at[i,"base"] = round(base_calc, 2)
        df.at[i,"charges"] = round(charges_calc, 2)
        df.at[i,"pct"] = round(pct_calc, 2)
        df.at[i,"nuitees"]   = (depart - arrivee).days
        df.at[i,"AAAA"]      = arrivee.year
        df.at[i,"MM"]        = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        _save_file(df)
        st.success("✅ Modifié")
        st.rerun()

    if c_del.button("🗑 Supprimer"):
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        _save_file(df2)
        st.warning("Supprimé.")
        st.rerun()

def vue_calendrier(df: pd.DataFrame, colors: dict = None):
    st.subheader("📅 Calendrier mensuel")
    df = _ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    colors = colors or {
        "Booking": "#1E90FF",
        "Airbnb": "#FF5A5F",
        "Autre": "#2E8B57"
    }

    cols = st.columns(2)
    mois_nom = cols[0].selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = cols[1].selectbox("Année", annees, index=len(annees)-1)

    mois_index = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(annee, mois_index)[1]
    jours = [date(annee, mois_index, j+1) for j in range(nb_jours)]
    planning = {j: [] for j in jours}

    core, _ = _split_totals(df)
    for _, row in core.iterrows():
        d1 = row["date_arrivee"]; d2 = row["date_depart"]
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        tag = row["plateforme"]
        ic = "🟦" if tag == "Booking" else "🟩" if tag == "Airbnb" else "🟧"
        nom = str(row["nom"])
        for j in jours:
            if d1 <= j < d2:
                planning[j].append(f"{ic} {nom}")

    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    grille = []
    for semaine in calendar.monthcalendar(annee, mois_index):
        ligne = []
        for jour in semaine:
            if jour == 0:
                ligne.append("")
            else:
                d = date(annee, mois_index, jour)
                contenu = f"{jour}\n" + "\n".join(planning.get(d, []))
                ligne.append(contenu)
        grille.append(ligne)

    st.table(pd.DataFrame(grille, columns=headers))

def vue_rapport(df: pd.DataFrame):
    st.subheader("📊 Rapport (détaillé)")
    df = _ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.info("Aucune année disponible.")
        return

    c1, c2, c3 = st.columns(3)
    annee = c1.selectbox("Année", annees, index=len(annees)-1, key="rapport_annee")
    pf_opt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = c2.selectbox("Plateforme", pf_opt, key="rapport_pf")
    mois_opt = ["Tous"] + [f"{i:02d}" for i in range(1,13)]
    mois_label = c3.selectbox("Mois", mois_opt, key="rapport_mois")

    data = df[df["AAAA"] == int(annee)].copy()
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]
    if mois_label != "Tous":
        data = data[data["MM"] == int(mois_label)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    detail = data.copy()
    for c in ["date_arrivee","date_depart"]:
        detail[c] = detail[c].apply(_format_date_str)
    by = [c for c in ["date_arrivee","nom"] if c in detail.columns]
    if by:
        detail = detail.sort_values(by=by, na_position="last").reset_index(drop=True)

    cols_detail = [
        "nom","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","pct"
    ]
    cols_detail = [c for c in cols_detail if c in detail.columns]
    st.dataframe(detail[cols_detail], use_container_width=True)

    _kpi_chips(data)

    stats = (
        data.groupby(["MM","plateforme"], dropna=True)
            .agg(prix_brut=("prix_brut","sum"),
                 prix_net=("prix_net","sum"),
                 base=("base","sum"),
                 charges=("charges","sum"),
                 nuitees=("nuitees","sum"))
            .reset_index()
    )
    stats = stats.sort_values(["MM","plateforme"]).reset_index(drop=True)

    def bar_chart_metric(metric_label, metric_col):
        if stats.empty: return
        pvt = stats.pivot(index="MM", columns="plateforme", values=metric_col).fillna(0).sort_index()
        pvt.index = [f"{int(m):02d}" for m in pvt.index]
        st.markdown(f"**{metric_label}**")
        st.bar_chart(pvt)

    bar_chart_metric("Revenus bruts", "prix_brut")
    bar_chart_metric("Revenus nets", "prix_net")
    bar_chart_metric("Base", "base")
    bar_chart_metric("Nuitées", "nuitees")

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        detail[cols_detail].to_excel(writer, index=False)
    st.download_button(
        "⬇️ Télécharger le détail (XLSX)",
        data=buf.getvalue(),
        file_name=f"rapport_detail_{annee}{'' if mois_label=='Tous' else '_'+mois_label}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def vue_clients(df: pd.DataFrame):
    st.subheader("👥 Liste des clients")
    df = _ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    c1, c2 = st.columns(2)
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = c1.selectbox("Année", annees, index=len(annees)-1) if annees else None
    mois  = c2.selectbox("Mois", ["Tous"] + [f"{i:02d}" for i in range(1,13)])

    data = df.copy()
    if annee:
        data = data[data["AAAA"] == int(annee)]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]
    if data.empty:
        st.info("Aucune donnée pour cette période.")
        return

    data["prix_brut/nuit"] = data.apply(lambda r: round((r["prix_brut"]/r["nuitees"]) if r["nuitees"] else 0,2), axis=1)
    data["prix_net/nuit"]  = data.apply(lambda r: round((r["prix_net"]/r["nuitees"])  if r["nuitees"] else 0,2), axis=1)

    show = data.copy()
    for c in ["date_arrivee","date_depart"]:
        show[c] = show[c].apply(_format_date_str)

    cols = ["nom","plateforme","telephone","date_arrivee","date_depart",
            "nuitees","prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","pct","prix_brut/nuit","prix_net/nuit"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Télécharger (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

def vue_export_ics(df: pd.DataFrame):
    st.subheader("📤 Export ICS (Google Agenda – Import manuel)")
    df = _ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée à exporter.")
        return

    c1, c2, c3 = st.columns(3)
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = c1.selectbox("Année", ["Toutes"] + annees, index=len(annees)) if annees else "Toutes"
    mois  = c2.selectbox("Mois", ["Tous"] + list(range(1,13)))
    pfopt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf    = c3.selectbox("Plateforme", pfopt)

    data = df.copy()
    if annee != "Toutes":
        data = data[data["AAAA"] == int(annee)]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]

    if data.empty:
        st.info("Aucune réservation pour ces filtres.")
        return

    ics_text = df_to_ics(data)
    st.download_button(
        "⬇️ Télécharger reservations.ics",
        data=ics_text.encode("utf-8"),
        file_name="reservations.ics",
        mime="text/calendar"
    )
    st.caption("Dans Google Agenda : Paramètres → Importer & exporter → Importer → sélectionnez ce fichier .ics.")

# ---------- SMS ----------
def _sms_message_arrivee(row: pd.Series) -> str:
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    d1s = d1.strftime("%Y/%m/%d") if isinstance(d1, date) else ""
    d2s = d2.strftime("%Y/%m/%d") if isinstance(d2, date) else ""
    nuitees = int(row.get("nuitees") or ((d2 - d1).days if isinstance(d1, date) and isinstance(d2, date) else 0))
    plateforme = str(row.get("plateforme") or "")
    nom = str(row.get("nom") or "")
    tel_aff = str(row.get("telephone") or "").strip()

    return (
        "VILLA TOBIAS\n"
        f"Plateforme : {plateforme}\n"
        f"Date d'arrivee : {d1s}  Date depart : {d2s}  Nombre de nuitees : {nuitees}\n\n"
        f"Bonjour {nom}\n"
        f"Telephone : {tel_aff}\n\n"
        "Bienvenue chez nous !\n\n "
        "Nous sommes ravis de vous accueillir bientot. Pour organiser au mieux votre reception, pourriez-vous nous indiquer "
        "a quelle heure vous pensez arriver.\n\n "
        "Sachez egalement qu'une place de parking est a votre disposition dans l'immeuble, en cas de besoin.\n\n "
        "Nous vous souhaitons un excellent voyage et nous nous rejouissons de vous rencontrer.\n\n "
        "Annick & Charley"
    )

def _sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Un grand merci d’avoir choisi notre appartement pour votre séjour ! "
        "Nous espérons que vous avez passé un moment aussi agréable que celui que nous avons eu à vous accueillir.\n\n"
        "Si l’envie vous prend de revenir explorer encore un peu notre ville (ou simplement retrouver le confort de notre petit cocon), "
        "sachez que notre porte vous sera toujours grande ouverte.\n\n"
        "Au plaisir de vous accueillir à nouveau,\n"
        "Annick & Charley"
    )

def vue_sms(df: pd.DataFrame):
    st.subheader("✉️ SMS (envoi manuel)")
    df = _ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    today = date.today()
    demain = today + timedelta(days=1)
    hier = today - timedelta(days=1)

    colA, colB = st.columns(2)

    with colA:
        st.markdown("### 📆 Arrivées demain")
        arrives = df[df["date_arrivee"] == demain].copy()
        if arrives.empty:
            st.info("Aucune arrivée demain.")
        else:
            for idx, r in arrives.reset_index(drop=True).iterrows():
                body = _sms_message_arrivee(r)
                tel = _normalize_tel(r.get("telephone"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                st.markdown(f"**{r.get('nom','')}** — {r.get('plateforme','')}")
                st.markdown(f"Arrivée: {_format_date_str(r.get('date_arrivee'))} • "
                            f"Départ: {_format_date_str(r.get('date_depart'))} • "
                            f"Nuitées: {r.get('nuitees','')}")
                st.code(body)
                c1, c2 = st.columns(2)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                st.divider()

    with colB:
        st.markdown("### 🕒 Relance +24h après départ")
        dep_24h = df[df["date_depart"] == hier].copy()
        if dep_24h.empty:
            st.info("Aucun départ hier.")
        else:
            for idx, r in dep_24h.reset_index(drop=True).iterrows():
                body = _sms_message_depart(r)
                tel = _normalize_tel(r.get("telephone"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                st.markdown(f"**{r.get('nom','')}** — {r.get('plateforme','')}")
                st.code(body)
                c1, c2 = st.columns(2)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                st.divider()

    st.markdown("### ✍️ Composer un SMS manuel")
    df_pick = df.copy()
    df_pick["id_aff"] = df_pick["nom"].astype(str) + " | " + df_pick["plateforme"].astype(str) + " | " + df_pick["date_arrivee"].apply(_format_date_str)
    choix = st.selectbox("Choisir une réservation", df_pick["id_aff"])
    r = df_pick.loc[df_pick["id_aff"] == choix].iloc[0]
    tel = _normalize_tel(r.get("telephone"))

    choix_type = st.radio("Modèle de message",
                          ["Arrivée (demande d’heure)","Relance après départ","Message libre"],
                          horizontal=True)
    if choix_type == "Arrivée (demande d’heure)":
        body = _sms_message_arrivee(r)
    elif choix_type == "Relance après départ":
        body = _sms_message_depart(r)
    else:
        body = st.text_area("Votre message", value="", height=160, placeholder="Tapez votre SMS ici…")

    c1, c2 = st.columns(2)
    with c1:
        st.code(body or "—")
    if tel and body:
        c1, c2 = st.columns(2)
        c1.link_button(f"📞 Appeler {tel}", f"tel:{tel}")
        c2.link_button("📩 Envoyer SMS", f"sms:{tel}?&body={quote(body)}")
    else:
        st.info("Renseignez un téléphone et un message.")

# ==============================
# MAIN (remplace celui de la partie 1)
# ==============================
def main():
    st.set_page_config(page_title="🏠 Réservations", layout="wide")
    # Logo : déjà présent dans la partie 1 en haut du fichier.
    st.sidebar.title("📁 Fichier")
    df = _read_file()

    # Sauvegarde / Restauration
    # (Téléchargement)
    buf_dl = BytesIO()
    _ensure_schema(df).to_excel(buf_dl, index=False, engine="openpyxl")
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=buf_dl.getvalue(),
        file_name=FICHIER_EXCEL,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
    # (Restauration)
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            df_new = pd.read_excel(up, converters={"telephone": _normalize_tel})
            df_new = _ensure_schema(df_new)
            _save_file(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS"]
    )

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

    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "➕ Ajouter":
        vue_ajouter(df)
    elif onglet == "✏️ Modifier / Supprimer":
        vue_modifier(df)
    elif onglet == "📅 Calendrier":
        vue_calendrier(df)
    elif onglet == "📊 Rapport":
        vue_rapport(df)
    elif onglet == "👥 Liste clients":
        vue_clients(df)
    elif onglet == "📤 Export ICS":
        vue_export_ics(df)
    elif onglet == "✉️ SMS":
        vue_sms(df)

if __name__ == "__main__":
    main()