# app.py — Villa Tobias (COMPLET)
# - Boutons Modifier/Supprimer dans 📋 Réservations (sur les lignes visibles)
# - Palette plateformes stockée dans le .xlsx (feuille "plateformes")
# - Restauration simple (upload .xlsx, BytesIO) + openpyxl partout
# - Calendrier coloré (lisible en thème sombre)
# - KPI, Rapport, SMS, ICS, Maintenance

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
from urllib.parse import quote
import colorsys

FICHIER = "reservations.xlsx"
RES_SHEET = "reservations"
PAL_SHEET = "plateformes"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PAR DEFAUT) ==============================
DEFAULT_PALETTE = {
    "Booking": "#1e90ff",  # bleu
    "Airbnb":  "#e74c3c",  # rouge
    "Autre":   "#f59e0b",  # orange
}

# ==============================  OUTILS DATES/TEL ==============================
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
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

# ==============================  SCHEMA & CALCULS  ==============================
BASE_COLS = [
    "paye", "nom_client", "sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%",
    "AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()

    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan

    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)

    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(to_date_only)

    df["telephone"] = df["telephone"].apply(normalize_tel)

    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Nuitées
    df["nuitees"] = [
        (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
        for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
    ]

    # AAAA / MM
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    # Valeurs par défaut
    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"] = df["ical_uid"].fillna("")

    # NaN -> 0 pour calculs
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    # Calculs
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    # Arrondis
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)

    ordered_cols = [c for c in BASE_COLS if c in df.columns]
    rest_cols = [c for c in df.columns if c not in ordered_cols]
    return df[ordered_cols + rest_cols]

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

# ==============================  EXCEL I/O (reservations + palette) ==============================

@st.cache_data(show_spinner=False)
def _read_workbook_cached(path: str, mtime: float):
    # Retourne (df_reservations, palette_dict)
    xls = pd.ExcelFile(path, engine="openpyxl")
    # Feuille réservations
    if RES_SHEET in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name=RES_SHEET, engine="openpyxl",
                           converters={"telephone": normalize_tel})
    else:
        # Compat ancien: première feuille
        df = pd.read_excel(xls, sheet_name=0, engine="openpyxl",
                           converters={"telephone": normalize_tel})
    # Feuille palette
    palette = DEFAULT_PALETTE.copy()
    if PAL_SHEET in xls.sheet_names:
        try:
            pal_df = pd.read_excel(xls, sheet_name=PAL_SHEET, engine="openpyxl")
            if {"plateforme","couleur"}.issubset(set(pal_df.columns)):
                tmp = {}
                for _, r in pal_df.iterrows():
                    k = str(r.get("plateforme") or "").strip()
                    v = str(r.get("couleur") or "").strip()
                    if k and v.startswith("#"):
                        tmp[k] = v
                if tmp:
                    palette = tmp
        except Exception:
            pass
    return ensure_schema(df), palette

def charger_workbook():
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame()), DEFAULT_PALETTE.copy()
    try:
        mtime = os.path.getmtime(FICHIER)
        df, pal = _read_workbook_cached(FICHIER, mtime)
        return df, pal
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame()), DEFAULT_PALETTE.copy()

def sauvegarder_workbook(df: pd.DataFrame, palette: dict = None):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core = sort_core(core)
    out = pd.concat([core, totals], ignore_index=True)

    if palette is None:
        palette = get_palette()

    pal_df = pd.DataFrame(
        [{"plateforme": k, "couleur": v} for k, v in palette.items()]
    )

    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name=RES_SHEET)
            pal_df.to_excel(w, index=False, sheet_name=PAL_SHEET)
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration .xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            xls = pd.ExcelFile(bio, engine="openpyxl")
            # reservations
            if RES_SHEET in xls.sheet_names:
                df_new = pd.read_excel(xls, sheet_name=RES_SHEET, engine="openpyxl",
                                       converters={"telephone": normalize_tel})
            else:
                df_new = pd.read_excel(xls, sheet_name=0, engine="openpyxl",
                                       converters={"telephone": normalize_tel})
            df_new = ensure_schema(df_new)
            # palette
            pal = DEFAULT_PALETTE.copy()
            if PAL_SHEET in xls.sheet_names:
                pal_df = pd.read_excel(xls, sheet_name=PAL_SHEET, engine="openpyxl")
                if {"plateforme","couleur"}.issubset(set(pal_df.columns)):
                    tmp = {}
                    for _, r in pal_df.iterrows():
                        k = str(r.get("plateforme") or "").strip()
                        v = str(r.get("couleur") or "").strip()
                        if k and v.startswith("#"):
                            tmp[k] = v
                    if tmp:
                        pal = tmp
            # Sauvegarde complète (2 feuilles)
            sauvegarder_workbook(df_new, pal)
            # Init palette session
            st.session_state.palette = pal
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    # Télécharge le classeur complet (2 feuilles)
    df = ensure_schema(df)
    core, totals = split_totals(df)
    core


# ==============================  VUE : AJOUTER ==============================
def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    st.caption("Saisie compacte (libellés à gauche)")
    palette = get_palette()

    def inline_input(label, widget_fn, key=None, **widget_kwargs):
        col1, col2 = st.columns([1,2])
        with col1: st.markdown(f"**{label}**")
        with col2: return widget_fn(label, key=key, label_visibility="collapsed", **widget_kwargs)

    paye = inline_input("Payé", st.checkbox, key="add_paye", value=False)
    nom = inline_input("Nom", st.text_input, key="add_nom", value="")
    sms_envoye = inline_input("SMS envoyé", st.checkbox, key="add_sms", value=False)

    tel = inline_input("Téléphone (+33...)", st.text_input, key="add_tel", value="")
    pf_options = sorted(palette.keys())
    pf_index = pf_options.index("Booking") if "Booking" in pf_options else 0
    plateforme = inline_input("Plateforme", st.selectbox, key="add_pf",
                              options=pf_options, index=pf_index)

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

    base_calc = max(net_calc - float(menage) - float(taxes), 0.0)
    charges_calc = max(float(brut) - net_calc, 0.0)
    pct_calc = (charges_calc / float(brut) * 100) if float(brut) > 0 else 0.0

    inline_input("Base (calculée)", st.number_input, key="add_base",
                 value=round(base_calc,2), step=0.01, format="%.2f", disabled=True)
    inline_input("Commission (%)", st.number_input, key="add_pct",
                 value=round(pct_calc,2), step=0.01, format="%.2f", disabled=True)

    if st.button("💾 Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        ligne = {
            "paye": bool(paye),
            "nom_client": (nom or "").strip(),
            "sms_envoye": bool(sms_envoye),
            "plateforme": plateforme,
            "telephone": normalize_tel(tel),
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
            "%": round(pct_calc, 2),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month,
            "ical_uid": ""
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        sauvegarder_workbook(df2)  # palette conservée
        st.success("✅ Réservation enregistrée")
        st.rerun()

# ==============================  VUE : CALENDRIER ==============================
def vue_calendrier(df: pd.DataFrame):
    palette = get_palette()
    st.title("📅 Calendrier mensuel (coloré par plateforme)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

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

    core, _ = split_totals(df)
    planning = {j: [] for j in jours}
    for _, row in core.iterrows():
        d1 = row["date_arrivee"]; d2 = row["date_depart"]
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        pf = str(row["plateforme"] or "Autre")
        nom = str(row["nom_client"] or "")
        for j in jours:
            if d1 <= j < d2:
                planning[j].append((pf, nom))

    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    monthcal = calendar.monthcalendar(annee, mois_index)

    table = []
    bg_table = []
    fg_table = []

    for semaine in monthcal:
        row_text, row_bg, row_fg = [], [], []
        for jour in semaine:
            if jour == 0:
                row_text.append("")
                row_bg.append("transparent")
                row_fg.append(None)
            else:
                d = date(annee, mois_index, jour)
                items = planning.get(d, [])
                # 1re ligne: numéro du jour; ensuite un nom client par ligne (max 4 pour lisibilité)
                max_lines = 4
                content = [str(jour)] + [nom for _, nom in items[:max_lines]]
                if len(items) > max_lines:
                    content.append(f"... (+{len(items)-max_lines})")
                row_text.append("\n".join(content))

                if items:
                    base = palette.get(items[0][0], "#777777")
                    bg = lighten_color(base, 0.70)  # un peu plus soutenu pour thème sombre
                    fg = ideal_text_color(bg)
                else:
                    bg = "transparent"
                    fg = None
                row_bg.append(bg)
                row_fg.append(fg)
        table.append(row_text)
        bg_table.append(row_bg)
        fg_table.append(row_fg)

    df_table = pd.DataFrame(table, columns=headers)

    def style_row(vals, row_idx):
        css = []
        for col_idx, _ in enumerate(vals):
            bg = bg_table[row_idx][col_idx]
            fg = fg_table[row_idx][col_idx] or "inherit"
            css.append(
                f"background-color:{bg};color:{fg};white-space:pre-wrap;"
                f"border:1px solid rgba(127,127,127,0.25);"
            )
        return css

    styler = df_table.style
    for r in range(df_table.shape[0]):
        styler = styler.apply(lambda v, r=r: style_row(v, r), axis=1)

    st.caption("Légende :")
    leg = " • ".join([
        f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{get_palette()[p]};margin-right:6px;border-radius:3px;"></span>{p}'
        for p in sorted(get_palette().keys())
    ])
    st.markdown(leg, unsafe_allow_html=True)

    st.dataframe(styler, use_container_width=True, height=460)

# ==============================  VUE : RAPPORT ==============================
def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport (détaillé)")
    df = ensure_schema(df)
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
        detail[c] = detail[c].apply(format_date_str)
    by = [c for c in ["date_arrivee","nom_client"] if c in detail.columns]
    if by:
        detail = detail.sort_values(by=by, na_position="last").reset_index(drop=True)

    cols_detail = [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"
    ]
    cols_detail = [c for c in cols_detail if c in detail.columns]
    st.dataframe(detail[cols_detail], use_container_width=True)

    core, _ = split_totals(data)
    kpi_chips(core)

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
        if stats.empty:
            return
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

# ==============================  VUE : CLIENTS ==============================
def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste des clients")
    df = ensure_schema(df)
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
        show[c] = show[c].apply(format_date_str)

    cols = ["paye","nom_client","sms_envoye","plateforme","telephone","date_arrivee","date_depart",
            "nuitees","prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","prix_brut/nuit","prix_net/nuit"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Télécharger (CSV)",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

# ==============================  VUE : EXPORT ICS ==============================
def vue_export_ics(df: pd.DataFrame):
    st.title("📤 Export ICS (Google Agenda – Import manuel)")
    df = ensure_schema(df)
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

# ==============================  VUE : SMS ==============================
def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS (envoi manuel)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    today = date.today()
    demain = today + timedelta(days=1)
    hier = today - timedelta(days=1)

    colA, colB = st.columns(2)

    with colA:
        st.subheader("📆 Arrivées demain")
        arrives = df[df["date_arrivee"] == demain].copy()
        if arrives.empty:
            st.info("Aucune arrivée demain.")
        else:
            for idx, r in arrives.reset_index(drop=True).iterrows():
                body = sms_message_arrivee(r)
                tel = normalize_tel(r.get("telephone"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                st.markdown(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}")
                st.markdown(f"Arrivée: {format_date_str(r.get('date_arrivee'))} • "
                            f"Départ: {format_date_str(r.get('date_depart'))} • "
                            f"Nuitées: {r.get('nuitees','')}")
                st.code(body)
                c1, c2 = st.columns(2)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                st.divider()

    with colB:
        st.subheader("🕒 Relance +24h après départ")
        dep_24h = df[df["date_depart"] == hier].copy()
        if dep_24h.empty:
            st.info("Aucun départ hier.")
        else:
            for idx, r in dep_24h.reset_index(drop=True).iterrows():
                body = sms_message_depart(r)
                tel = normalize_tel(r.get("telephone"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                st.markdown(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}")
                st.code(body)
                c1, c2 = st.columns(2)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                st.divider()

    st.subheader("✍️ Composer un SMS manuel")
    df_pick = df.copy()
    df_pick["id_aff"] = df_pick["nom_client"].astype(str) + " | " + df_pick["plateforme"].astype(str) + " | " + df_pick["date_arrivee"].apply(format_date_str)
    if df_pick.empty:
        st.info("Aucune réservation.")
        return
    choix = st.selectbox("Choisir une réservation", df_pick["id_aff"])
    r = df_pick.loc[df_pick["id_aff"] == choix].iloc[0]
    tel = normalize_tel(r.get("telephone"))

    choix_type = st.radio("Modèle de message",
                          ["Arrivée (demande d’heure)","Relance après départ","Message libre"],
                          horizontal=True)
    if choix_type == "Arrivée (demande d’heure)":
        body = sms_message_arrivee(r)
    elif choix_type == "Relance après départ":
        body = sms_message_depart(r)
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

# ==============================  VUE : PLATEFORMES (onglet dédié) ==============================
def vue_plateformes(df: pd.DataFrame):
    st.title("⚙️ Plateformes")
    st.caption("Ces couleurs sont sauvegardées dans la feuille Excel « plateformes ».")

    pal = get_palette()

    st.markdown("### Ajouter / modifier")
    c1, c2, c3 = st.columns([2,1,1])
    with c1:
        name = st.text_input("Nom de la plateforme", key="pal_edit_name", placeholder="Ex: Expedia")
    with c2:
        color = st.color_picker("Couleur", key="pal_edit_color", value="#9b59b6")
    with c3:
        st.write("")
        if st.button("💾 Enregistrer / Mettre à jour"):
            nm = (name or "").strip()
            if not nm:
                st.warning("Entrez un nom de plateforme.")
            else:
                pal[nm] = color
                save_palette(pal)
                # Persister dans le classeur
                sauvegarder_workbook(df, pal)
                st.success(f"✅ Palette mise à jour pour « {nm} ».")

    st.markdown("### Plateformes existantes")
    for pf in sorted(pal.keys()):
        colA, colB, colC = st.columns([4,1,1])
        with colA:
            st.markdown(
                f'<span style="display:inline-block;width:1.1em;height:1.1em;background:{pal[pf]};border-radius:3px;margin-right:6px"></span>{pf}',
                unsafe_allow_html=True
            )
        with colB:
            if st.button("🎨 Changer", key=f"chg_{pf}"):
                st.session_state["pal_edit_name"] = pf
                st.session_state["pal_edit_color"] = pal[pf]
        with colC:
            if st.button("🗑 Supprimer", key=f"delpf_{pf}"):
                del pal[pf]
                save_palette(pal)
                sauvegarder_workbook(df, pal)
                st.warning(f"Supprimé: {pf}")
                st.rerun()

# ==============================  MAIN / NAVIGATION ==============================
def main():
    # Charger classeur (réservations + palette)
    df, pal = charger_workbook()
    # Initialiser la palette en session depuis le fichier
    st.session_state.palette = pal

    # Sidebar : Fichier & Maintenance
    st.sidebar.title("📁 Fichier")
    bouton_telecharger(df)
    bouton_restaurer()
    render_cache_section_sidebar()

    # Navigation
    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS","⚙️ Plateformes"]
    )

    # Router
    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "➕ Ajouter":
        vue_ajouter(df)
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
    elif onglet == "⚙️ Plateformes":
        vue_plateformes(df)

if __name__ == "__main__":
    main()