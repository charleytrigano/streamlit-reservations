# app.py — Villa Tobias (COMPLET)
# Options d’affichage + colonnes menage/frais_cb/base + calendrier colorisé + SMS + Export ICS
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

# Palette par défaut (peut être enrichie par la suite)
PLATFORM_COLORS_DEFAULT = {
    "Booking": "#2D7FF9",
    "Airbnb": "#FF5A5F",
    "Autre": "#F39C12",
}

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

# ==============================  OPTIONS D’AFFICHAGE  ==============================

def render_display_options():
    with st.sidebar.expander("🎛️ Options d’affichage", expanded=True):
        st.session_state.setdefault("opt_show_search", True)
        st.session_state.setdefault("opt_show_kpi", True)
        st.session_state.setdefault("opt_dense", False)
        st.session_state.setdefault("opt_show_month_list", True)

        st.session_state.opt_show_search = st.checkbox(
            "🔎 Afficher la recherche dans les tableaux",
            value=st.session_state.opt_show_search
        )
        st.session_state.opt_show_kpi = st.checkbox(
            "📊 Afficher les totaux / KPI",
            value=st.session_state.opt_show_kpi
        )
        st.session_state.opt_dense = st.checkbox(
            "🧱 Mode compact (lignes serrées)",
            value=st.session_state.opt_dense
        )
        st.session_state.opt_show_month_list = st.checkbox(
            "📄 Calendrier : afficher la liste du mois",
            value=st.session_state.opt_show_month_list
        )

    # CSS mode compact
    if st.session_state.opt_dense:
        st.markdown("""
        <style>
        .stDataFrame table td, .stDataFrame table th { padding-top: 4px !important; padding-bottom: 4px !important; }
        .stDataFrame [data-testid="stDataFrameResizable"] { font-size: 0.92rem; }
        </style>
        """, unsafe_allow_html=True)

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
    """Forcer lecture téléphone en TEXTE, retirer .0, espaces, garder +."""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip()
    s = s.replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    base_cols = [
        "nom_client","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","prix_net","charges","%",
        "menage","frais_cb","base",
        "AAAA","MM","ical_uid"
    ]
    if df is None or df.empty:
        return pd.DataFrame(columns=base_cols)

    df = df.copy()

    # Dates -> date
    for c in ["date_arrivee", "date_depart"]:
        if c in df.columns:
            df[c] = df[c].apply(to_date_only)

    # Numériques “classiques”
    for c in ["prix_brut", "prix_net", "charges", "%", "menage", "frais_cb", "base"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Calculs charges, %, base
    # - charges: différence entre brut et net (historique)
    # - %: (charges / prix_brut)*100
    # - base: prix_net - menage  (si "taxes_sejour" existe, on la déduit aussi)
    taxes_present = "taxes_sejour" in df.columns
    if taxes_present:
        df["taxes_sejour"] = pd.to_numeric(df["taxes_sejour"], errors="coerce")

    if "prix_brut" in df.columns and "prix_net" in df.columns:
        if "charges" not in df.columns:
            df["charges"] = df["prix_brut"] - df["prix_net"]
        with pd.option_context("mode.use_inf_as_na", True):
            df["%"] = ((df["charges"] / df["prix_brut"]) * 100).fillna(0)

    # menage / frais_cb par défaut à 0
    for c in ["menage", "frais_cb"]:
        if c not in df.columns:
            df[c] = 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)

    # base = prix_net - menage - taxes (si dispo)
    if "prix_net" in df.columns:
        if taxes_present:
            df["base"] = (df["prix_net"].fillna(0.0)
                          - df["menage"].fillna(0.0)
                          - df["taxes_sejour"].fillna(0.0))
        else:
            df["base"] = (df["prix_net"].fillna(0.0)
                          - df["menage"].fillna(0.0))
        df["base"] = df["base"].round(2)

    # Arrondis
    for c in ["prix_brut","prix_net","charges","%","menage","frais_cb"]:
        if c in df.columns:
            df[c] = df[c].round(2)

    # Nuitées
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]

    # AAAA / MM
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")

    # Colonnes minimales
    defaults = {"nom_client":"", "plateforme":"Autre", "telephone":"", "ical_uid":""}
    for k,v in defaults.items():
        if k not in df.columns:
            df[k] = v

    # Téléphone
    if "telephone" in df.columns:
        df["telephone"] = df["telephone"].apply(normalize_tel)

    # Ordre
    cols = base_cols
    return df[[c for c in cols if c in df.columns] + [c for c in df.columns if c not in cols]]

def is_total_row(row: pd.Series) -> bool:
    name_is_total = str(row.get("nom_client","")).strip().lower() == "total"
    pf_is_total   = str(row.get("plateforme","")).strip().lower() == "total"
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    no_dates = not isinstance(d1, date) and not isinstance(d2, date)
    has_money = any(pd.notna(row.get(c)) and float(row.get(c) or 0) != 0 for c in ["prix_brut","prix_net","charges","menage","frais_cb","base"])
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

def filter_box(df: pd.DataFrame, placeholder: str = "Rechercher…") -> pd.DataFrame:
    q = st.text_input("🔎 Recherche", "", placeholder=placeholder)
    if not q:
        return df
    q = q.lower().strip()
    mask = pd.Series(False, index=df.index)
    for c in df.columns:
        s = df[c]
        try:
            mask |= s.astype(str).str.lower().str.contains(q, na=False)
        except Exception:
            pass
    return df[mask]

# ==============================  EXCEL I/O  ==============================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    # Important: converter pour 'telephone'
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
    """Après to_excel, force le format texte '@' sur 'telephone'."""
    try:
        ws = writer.sheets.get(sheet_name) or writer.sheets.get("Sheet1")
        if ws is None or "telephone" not in df_to_save.columns:
            return
        col_idx = df_to_save.columns.get_loc("telephone") + 1  # 1-based
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

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restauration xlsx", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            df_new = pd.read_excel(up, converters={"telephone": normalize_tel})
            df_new = ensure_schema(df_new)
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    try:
        ensure_schema(df).to_excel(buf, index=False, engine="openpyxl")
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = None
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=data_xlsx if data_xlsx else b"",
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(data_xlsx is None),
    )

# ==============================  ICS EXPORT  ==============================

def _ics_escape(text: str) -> str:
    if text is None:
        return ""
    s = str(text)
    s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    s = s.replace("\n", "\\n")
    return s

def _fmt_date_ics(d: date) -> str:
    return d.strftime("%Y%m%d")

def _dtstamp_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def _stable_uid(nom_client, plateforme, d1, d2, tel, salt="v1"):
    base = f"{nom_client}|{plateforme}|{d1}|{d2}|{tel}|{salt}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return f"vt-{h}@villatobias"

def df_to_ics(df: pd.DataFrame, cal_name: str = "Villa Tobias – Réservations") -> str:
    df = ensure_schema(df)
    if df.empty:
        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PROID:-//Villa Tobias//Reservations//FR\r\n"
            f"X-WR-CALNAME:{_ics_escape(cal_name)}\r\n"
            "CALSCALE:GREGORIAN\r\n"
            "METHOD:PUBLISH\r\n"
            "END:VCALENDAR\r\n"
        )

    core, _ = split_totals(df)
    core = sort_core(core)

    lines = []
    A = lines.append
    A("BEGIN:VCALENDAR")
    A("VERSION:2.0")
    A("PRODID:-//Villa Tobias//Reservations//FR")
    A(f"X-WR-CALNAME:{_ics_escape(cal_name)}")
    A("CALSCALE:GREGORIAN")
    A("METHOD:PUBLISH")

    for _, row in core.iterrows():
        d1 = row.get("date_arrivee")
        d2 = row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue

        plateforme = str(row.get("plateforme") or "").strip()
        nom_client = str(row.get("nom_client") or "").strip()
        tel = str(row.get("telephone") or "").strip()

        summary = " - ".join([x for x in [plateforme, nom_client, tel] if x])
        brut = float(row.get("prix_brut") or 0)
        net  = float(row.get("prix_net") or 0)
        nuitees = int(row.get("nuitees") or ((d2 - d1).days))

        desc = (
            f"Plateforme: {plateforme}\\n"
            f"Client: {nom_client}\\n"
            f"Téléphone: {tel}\\n"
            f"Arrivee: {d1.strftime('%Y/%m/%d')}\\n"
            f"Depart: {d2.strftime('%Y/%m/%d')}\\n"
            f"Nuitees: {nuitees}\\n"
            f"Brut: {brut:.2f} €\\nNet: {net:.2f} €"
        )

        uid_existing = str(row.get("ical_uid") or "").strip()
        uid = uid_existing if uid_existing else _stable_uid(nom_client, plateforme, d1, d2, tel, salt="v1")

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

# ==============================  TEMPLATES SMS (MANUEL) ====================

def sms_message_arrivee(row: pd.Series) -> str:
    d1 = row.get("date_arrivee")
    d2 = row.get("date_depart")
    d1s = d1.strftime("%Y/%m/%d") if isinstance(d1, date) else ""
    d2s = d2.strftime("%Y/%m/%d") if isinstance(d2, date) else ""
    nuitees = int(row.get("nuitees") or ((d2 - d1).days if isinstance(d1, date) and isinstance(d2, date) else 0))
    plateforme = str(row.get("plateforme") or "")
    nom = str(row.get("nom_client") or "")
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

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    msg = (
        f"Bonjour {nom},\n\n"
        "Un grand merci d’avoir choisi notre appartement pour votre séjour ! "
        "Nous espérons que vous avez passé un moment aussi agréable que celui que nous avons eu à vous accueillir.\n\n"
        "Si l’envie vous prend de revenir explorer encore un peu notre ville (ou simplement retrouver le confort de notre petit cocon), "
        "sachez que notre porte vous sera toujours grande ouverte.\n\n"
        "Au plaisir de vous accueillir à nouveau,\n"
        "Annick & Charley"
    )
    return msg

# ==============================  KPI (chips)  ==============================

def _totaux_chips_html(total_brut, total_net, total_chg, total_nuits, pct_moy):
    return f"""
<style>
.chips-wrap {{ display:flex; flex-wrap:wrap; gap:12px; margin:8px 0 16px 0; }}
.chip {{ padding:10px 12px; border-radius:10px; background: rgba(127,127,127,0.12); border: 1px solid rgba(127,127,127,0.25); }}
.chip b {{ display:block; margin-bottom:4px; }}
</style>
<div class="chips-wrap">
  <div class="chip"><b>Total Brut</b><div>{total_brut:,.2f} €</div></div>
  <div class="chip"><b>Total Net</b><div>{total_net:,.2f} €</div></div>
  <div class="chip"><b>Total Charges</b><div>{total_chg:,.2f} €</div></div>
  <div class="chip"><b>Total Nuitées</b><div>{int(total_nuits) if pd.notna(total_nuits) else 0}</div></div>
  <div class="chip"><b>Commission moy.</b><div>{pct_moy:.2f} %</div></div>
</div>
"""

# ==============================  VUES  ==============================

def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")
    core, totals = split_totals(ensure_schema(df))
    core = sort_core(core)

    # Totaux (KPI)
    if st.session_state.get("opt_show_kpi", True) and not core.empty:
        total_brut   = core["prix_brut"].sum(skipna=True)
        total_net    = core["prix_net"].sum(skipna=True)
        total_chg    = core["charges"].sum(skipna=True)
        total_nuits  = core["nuitees"].sum(skipna=True)
        pct_moy = (core["charges"].sum() / core["prix_brut"].sum() * 100) if core["prix_brut"].sum() else 0
        st.markdown(_totaux_chips_html(total_brut, total_net, total_chg, total_nuits, pct_moy), unsafe_allow_html=True)

    show = pd.concat([core, totals], ignore_index=True)
    for c in ["date_arrivee","date_depart"]:
        if c in show.columns:
            show[c] = show[c].apply(format_date_str)

    # Recherche (option)
    show_to_display = filter_box(show, "Rechercher une valeur…") if st.session_state.get("opt_show_search", True) else show
    st.dataframe(show_to_display, use_container_width=True)

def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    st.caption("Saisie rapide (libellés inline)")

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
    net  = inline_input("Prix net (€)",  st.number_input, key="add_net",
                        min_value=0.0, step=1.0, format="%.2f")
    menage = inline_input("Ménage (€)", st.number_input, key="add_menage", min_value=0.0, step=1.0, format="%.2f")
    frais_cb = inline_input("Frais CB (€)", st.number_input, key="add_cb", min_value=0.0, step=1.0, format="%.2f")

    charges_calc = max(float(brut) - float(net), 0.0)  # historique
    pct_calc = (charges_calc / float(brut) * 100) if float(brut) > 0 else 0.0
    base_calc = float(net) - float(menage)  # si taxes_sejour présent, il sera intégré par ensure_schema

    inline_input("Charges (€)", st.number_input, key="add_ch",
                 value=round(charges_calc,2), step=0.01, format="%.2f", disabled=True)
    inline_input("Commission (%)", st.number_input, key="add_pct",
                 value=round(pct_calc,2), step=0.01, format="%.2f", disabled=True)
    inline_input("Base (€)", st.number_input, key="add_base",
                 value=round(base_calc,2), step=0.01, format="%.2f", disabled=True)

    c1, c2 = st.columns(2)
    with c1:
        if st.button("Enregistrer"):
            if net > brut:
                st.error("Le prix net ne peut pas être supérieur au prix brut.")
                return
            if depart < arrivee + timedelta(days=1):
                st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
                return

            ligne = {
                "nom_client": (nom or "").strip(),
                "plateforme": plateforme,
                "telephone": normalize_tel(tel),
                "date_arrivee": arrivee,
                "date_depart": depart,
                "prix_brut": float(brut),
                "prix_net": float(net),
                "charges": round(charges_calc, 2),
                "%": round(pct_calc, 2),
                "menage": float(menage),
                "frais_cb": float(frais_cb),
                # base sera recalculée dans ensure_schema, mais on persist la valeur calculée ici aussi:
                "base": round(base_calc, 2),
                "nuitees": (depart - arrivee).days,
                "AAAA": arrivee.year,
                "MM": arrivee.month,
                "ical_uid": ""
            }
            df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            df2 = ensure_schema(df2)
            sauvegarder_donnees(df2)
            st.success("✅ Réservation enregistrée")
            st.rerun()
    with c2:
        st.info("Astuce : le départ est proposé au lendemain automatiquement.")

def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune réservation.")
        return

    df["identifiant"] = df["nom_client"].astype(str) + " | " + df["date_arrivee"].apply(format_date_str)
    choix = st.selectbox("Choisir une réservation", df["identifiant"])
    idx = df.index[df["identifiant"] == choix]
    if len(idx) == 0:
        st.warning("Sélection invalide.")
        return
    i = idx[0]

    col = st.columns(2)
    nom = col[0].text_input("Nom", df.at[i, "nom_client"])
    tel = col[1].text_input("Téléphone", normalize_tel(df.at[i, "telephone"]))
    plateforme = st.selectbox("Plateforme", ["Booking","Airbnb","Autre"],
                              index = ["Booking","Airbnb","Autre"].index(df.at[i,"plateforme"]) if df.at[i,"plateforme"] in ["Booking","Airbnb","Autre"] else 2)

    arrivee = st.date_input("Arrivée", df.at[i,"date_arrivee"] if isinstance(df.at[i,"date_arrivee"], date) else date.today())
    depart  = st.date_input("Départ",  df.at[i,"date_depart"] if isinstance(df.at[i,"date_depart"], date) else arrivee + timedelta(days=1), min_value=arrivee+timedelta(days=1))

    c = st.columns(5)
    brut = c[0].number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i,"prix_brut"]) if pd.notna(df.at[i,"prix_brut"]) else 0.0, step=1.0, format="%.2f")
    net  = c[1].number_input("Prix net (€)",  min_value=0.0, value=float(df.at[i,"prix_net"])  if pd.notna(df.at[i,"prix_net"])  else 0.0, step=1.0, format="%.2f")
    menage = c[2].number_input("Ménage (€)", min_value=0.0, value=float(df.at[i,"menage"]) if pd.notna(df.at[i,"menage"]) else 0.0, step=1.0, format="%.2f")
    frais_cb = c[3].number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i,"frais_cb"]) if pd.notna(df.at[i,"frais_cb"]) else 0.0, step=1.0, format="%.2f")

    charges_calc = max(brut - net, 0.0)
    pct_calc = (charges_calc / brut * 100) if brut > 0 else 0.0
    base_calc = net - menage
    c[4].markdown(f"**Charges**: {charges_calc:.2f} €  \n**%**: {pct_calc:.2f}  \n**Base**: {base_calc:.2f} €")

    c1, c2 = st.columns(2)
    if c1.button("💾 Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        df.at[i,"nom_client"] = nom.strip()
        df.at[i,"plateforme"] = plateforme
        df.at[i,"telephone"]  = normalize_tel(tel)
        df.at[i,"date_arrivee"] = arrivee
        df.at[i,"date_depart"]  = depart
        df.at[i,"prix_brut"] = float(brut)
        df.at[i,"prix_net"]  = float(net)
        df.at[i,"charges"]   = round(charges_calc, 2)
        df.at[i,"%"]         = round(pct_calc, 2)
        df.at[i,"menage"]    = float(menage)
        df.at[i,"frais_cb"]  = float(frais_cb)
        df.at[i,"base"]      = round(base_calc, 2)
        df.at[i,"nuitees"]   = (depart - arrivee).days
        df.at[i,"AAAA"]      = arrivee.year
        df.at[i,"MM"]        = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        df = ensure_schema(df)
        sauvegarder_donnees(df)
        st.success("✅ Modifié")
        st.rerun()

    if c2.button("🗑 Supprimer"):
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2)
        st.warning("Supprimé.")
        st.rerun()

def vue_calendrier(df: pd.DataFrame, colors=None):
    st.title("📅 Calendrier mensuel")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return
    colors = (colors or PLATFORM_COLORS_DEFAULT).copy()

    # Sélecteurs sur une ligne
    colA, colB = st.columns(2)
    mois_nom = colA.selectbox("Mois", ["Lundi=1"] + list(calendar.month_name)[1:], index=date.today().month)
    if mois_nom == "Lundi=1":  # clin d’œil (ne sert à rien, juste à garder l’index)
        mois_nom = list(calendar.month_name)[date.today().month]
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = colB.selectbox("Année", annees, index=len(annees)-1)

    mois_index = list(calendar.month_name).index(mois_nom)
    nb_jours = calendar.monthrange(annee, mois_index)[1]
    jours = [date(annee, mois_index, j+1) for j in range(nb_jours)]

    # Matrices texte et couleurs
    weeks = calendar.monthcalendar(annee, mois_index)  # semaines → listes de 7 (0 = vide)
    display_text = pd.DataFrame(
        [["" for _ in range(7)] for __ in range(len(weeks))],
        columns=["L","M","M","J","V","S","D"]
    )
    display_color = pd.DataFrame(
        [["" for _ in range(7)] for __ in range(len(weeks))],
        columns=display_text.columns
    )

    core, _ = split_totals(df)
    # Remplissage couleurs: si un jour est réservé, colorisation selon 1ère plateforme trouvée ce jour
    # (tu peux raffiner en cascade si plusieurs réservations le même jour)
    reservations_du_mois = []
    for _, row in core.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        # Tous les jours couverts par la resa
        day = d1
        while day < d2:
            if day.month == mois_index and day.year == annee:
                reservations_du_mois.append((day, row.get("plateforme","Autre"), row.get("nom_client",""), row))
            day += timedelta(days=1)

    # Index rapide par jour
    res_by_day = {}
    for d, pf, nom, row in reservations_du_mois:
        res_by_day.setdefault(d, []).append((pf, nom, row))

    # Garnir la grille
    for r, week in enumerate(weeks):
        for c, daynum in enumerate(week):
            if daynum == 0:
                display_text.iat[r, c] = ""
                continue
            d = date(annee, mois_index, daynum)
            display_text.iat[r, c] = f"{daynum}"
            items = res_by_day.get(d, [])
            if items:
                pf = items[0][0] or "Autre"
                col = colors.get(pf, "#888")
                display_color.iat[r, c] = f"background-color: {col}; color:white; font-weight:600;"

    # Styler cohérent (matrice même taille)
    def apply_colors(_):
        return display_color

    st.dataframe(
        display_text.style.apply(apply_colors, axis=None),
        use_container_width=True,
        height=320
    )

    # Sélecteur de jour pour voir le détail
    st.markdown("### 📄 Réservations du mois")
    csel1, csel2 = st.columns([1,2])
    sel_jour = csel1.selectbox(
        "Jour",
        options=[f"{annee}-{mois_index:02d}-{j:02d}" for j in range(1, nb_jours+1)],
        index=min(date.today().day-1, nb_jours-1)
    )
    y, m, d = map(int, sel_jour.split("-"))
    dsel = date(y,m,d)
    details = res_by_day.get(dsel, [])

    if not details:
        st.info("Aucune réservation ce jour.")
    else:
        rows = []
        for pf, nom, row in details:
            rows.append({
                "plateforme": pf,
                "nom_client": nom,
                "date_arrivee": format_date_str(row.get("date_arrivee")),
                "date_depart": format_date_str(row.get("date_depart")),
                "nuitees": row.get("nuitees"),
                "telephone": row.get("telephone")
            })
        det = pd.DataFrame(rows)
        det_to_show = filter_box(det, "Rechercher un nom / plateforme…") if st.session_state.get("opt_show_search", True) else det
        st.dataframe(det_to_show, use_container_width=True)

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport (réservations détaillées)")
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
        "nom_client","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","prix_net","charges","%",
        "menage","frais_cb","base"
    ]
    cols_detail = [c for c in cols_detail if c in detail.columns]

    # Recherche optionnelle
    table_to_show = detail[cols_detail]
    if st.session_state.get("opt_show_search", True):
        table_to_show = filter_box(table_to_show, "Rechercher dans le rapport…")
    st.dataframe(table_to_show, use_container_width=True)

    # KPI
    if st.session_state.get("opt_show_kpi", True):
        total_brut   = data["prix_brut"].sum(skipna=True)
        total_net    = data["prix_net"].sum(skipna=True)
        total_chg    = data["charges"].sum(skipna=True)
        total_nuits  = data["nuitees"].sum(skipna=True)
        pct_moy = (data["charges"].sum() / data["prix_brut"].sum() * 100) if data["prix_brut"].sum() else 0
        st.markdown(_totaux_chips_html(total_brut, total_net, total_chg, total_nuits, pct_moy), unsafe_allow_html=True)

    # Graphes : MM 1..12 triés
    stats = (
        data.groupby(["MM","plateforme"], dropna=True)
            .agg(prix_brut=("prix_brut","sum"),
                 prix_net=("prix_net","sum"),
                 charges=("charges","sum"),
                 nuitees=("nuitees","sum"))
            .reset_index()
    )
    stats = stats.sort_values(["MM","plateforme"]).reset_index(drop=True)

    def chart_of(metric_label, metric_col):
        if stats.empty:
            return
        pivot = stats.pivot(index="MM", columns="plateforme", values=metric_col).fillna(0)
        pivot = pivot.sort_index()
        pivot.index = [f"{int(m):02d}" for m in pivot.index]
        st.markdown(f"**{metric_label}**")
        st.bar_chart(pivot)

    chart_of("Revenus bruts", "prix_brut")
    chart_of("Revenus nets", "prix_net")
    chart_of("Nuitées", "nuitees")

    # Export détail XLSX
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        table_to_show.to_excel(writer, index=False)
    st.download_button(
        "⬇️ Télécharger le détail (XLSX)",
        data=buf.getvalue(),
        file_name=f"rapport_detail_{annee}{'' if mois_label=='Tous' else '_'+mois_label}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

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

    cols = ["nom_client","plateforme","telephone","date_arrivee","date_depart",
            "nuitees","prix_brut","prix_net","charges","%","menage","frais_cb","base",
            "prix_brut/nuit","prix_net/nuit"]
    cols = [c for c in cols if c in show.columns]

    table_to_show = show[cols]
    if st.session_state.get("opt_show_search", True):
        table_to_show = filter_box(table_to_show, "Rechercher un client / plateforme…")
    st.dataframe(table_to_show, use_container_width=True)

    st.download_button(
        "📥 Télécharger (CSV)",
        data=table_to_show.to_csv(index=False).encode("utf-8"),
        file_name="liste_clients.csv",
        mime="text/csv"
    )

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

                c1, c2, c3 = st.columns([1,1,2])
                ck_call = c1.checkbox("📞 Appeler", key=f"sms_arr_call_{idx}", value=False)
                ck_sms  = c2.checkbox("📩 SMS", key=f"sms_arr_sms_{idx}", value=True)
                with c3:
                    if ck_call and tel_link:
                        st.link_button(f"Appeler {tel}", tel_link)
                    if ck_sms and sms_link:
                        st.link_button("Envoyer SMS", sms_link)
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

                c1, c2, c3 = st.columns([1,1,2])
                ck_call = c1.checkbox("📞 Appeler", key=f"sms_dep_call_{idx}", value=False)
                ck_sms  = c2.checkbox("📩 SMS", key=f"sms_dep_sms_{idx}", value=True)
                with c3:
                    if ck_call and tel_link:
                        st.link_button(f"Appeler {tel}", tel_link)
                    if ck_sms and sms_link:
                        st.link_button("Envoyer SMS", sms_link)
                st.divider()

    st.subheader("✍️ Composer un SMS manuel")
    df_pick = df.copy()
    df_pick["id_aff"] = df_pick["nom_client"].astype(str) + " | " + df_pick["plateforme"].astype(str) + " | " + df_pick["date_arrivee"].apply(format_date_str)
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

    c1, c2, c3 = st.columns([2,1,1])
    with c1:
        st.code(body or "—")
    ck_call = c2.checkbox("📞 Appeler", key="sms_manual_call", value=False)
    ck_sms  = c3.checkbox("📩 SMS", key="sms_manual_sms", value=True)

    if tel and body:
        if ck_call:
            st.link_button(f"Appeler {tel}", f"tel:{tel}")
        if ck_sms:
            st.link_button("Envoyer SMS", f"sms:{tel}?&body={quote(body)}")
    else:
        st.info("Renseignez un téléphone et un message.")

# ==============================  APP  ==============================

def main():
    st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

    # Barre latérale : Fichier (Sauvegarde / Restauration)
    st.sidebar.title("📁 Fichier")
    df_tmp = charger_donnees()
    bouton_telecharger(df_tmp)
    bouton_restaurer()

    # Navigation
    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS"]
    )

    # Maintenance et Options d’affichage SOUS la navigation
    render_cache_section_sidebar()
    render_display_options()

    # Charger les données après éventuelle restauration
    df = charger_donnees()

    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "➕ Ajouter":
        vue_ajouter(df)
    elif onglet == "✏️ Modifier / Supprimer":
        vue_modifier(df)
    elif onglet == "📅 Calendrier":
        vue_calendrier(df, colors=PLATFORM_COLORS_DEFAULT)
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