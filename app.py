# app.py — Villa Tobias (COMPLET, STABLE)
# - Palette plateformes (ajout/couleurs)
# - Réservations (affichage)
# - Calendrier (grille lisible)
# - Rapport (aperçu)
# - SMS (modèles)
# - Export ICS (séparé des vues)
# - Sauvegarde / Restauration XLSX fiables
# - Maintenance (vider caches)
# - safe_view: affiche les erreurs complètes dans l’UI (pas de traces tronquées)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
import colorsys
import traceback

APP_SIGNATURE = "VillaTobias v2025-08-23a"

FICHIER = "reservations.xlsx"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  SAFE VIEW WRAPPER  ==============================

def safe_view(view_fn, *args, **kwargs):
    """Exécute une vue et affiche un panneau d’erreur complet si ça plante."""
    try:
        return view_fn(*args, **kwargs)
    except Exception as e:
        st.error(f"💥 Erreur dans `{view_fn.__name__}` : {e}")
        st.exception(e)
        st.caption("Trace complète ci-dessous :")
        st.code(traceback.format_exc())
        return None

# ==============================  PALETTE (PLATEFORMES) ==============================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def get_palette() -> dict:
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    # nettoyage minimal
    pal = {}
    for k, v in st.session_state.palette.items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4,7):
            pal[k] = v
    st.session_state.palette = pal
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = dict(palette)

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

def render_palette_editor_sidebar():
    palette = get_palette()
    st.sidebar.markdown("## 🎨 Plateformes")
    with st.sidebar.expander("➕ Ajouter / modifier", expanded=False):
        c1, c2 = st.columns([2,1])
        with c1:
            new_name = st.text_input("Nom de la plateforme", key="pal_new_name", placeholder="Ex: Expedia")
        with c2:
            new_color = st.color_picker("Couleur", key="pal_new_color", value="#9b59b6")
        colA, colB = st.columns(2)
        if colA.button("Ajouter / Mettre à jour"):
            name = (new_name or "").strip()
            if not name:
                st.warning("Entrez un nom.")
            else:
                palette[name] = new_color
                save_palette(palette)
                st.success(f"✅ « {name} » enregistré.")
        if colB.button("Réinitialiser"):
            save_palette(DEFAULT_PALETTE.copy())
            st.success("✅ Palette réinitialisée.")
    if palette:
        st.sidebar.markdown("**Plateformes :**")
        for pf in sorted(palette.keys()):
            st.sidebar.markdown(platform_badge(pf, palette), unsafe_allow_html=True)

# ==============================  MAINTENANCE / CACHE  ==============================

def render_cache_section_sidebar():
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider les caches et relancer"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.sidebar.success("Caches vidés. Redémarrage…")
        st.rerun()

# ==============================  OUTILS  ==============================

def to_date_only(x):
    if pd.isna(x) or x is None: return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def format_date_str(d):
    return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)): return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"): s = s[:-2]
    return s

# ==============================  SCHEMA & CALCULS  ==============================

BASE_COLS = [
    "paye","nom_client","sms_envoye",
    "plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base",
    "charges","%","AAAA","MM","ical_uid"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    df = df.copy()
    # colonnes
    for c in BASE_COLS:
        if c not in df.columns: df[c] = np.nan
    # types / valeurs
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)

    num_cols = ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]
    for c in num_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df["nuitees"] = [
        (d2 - d1).days if (isinstance(d1,date) and isinstance(d2,date)) else np.nan
        for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
    ]
    df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d,date) else np.nan).astype("Int64")
    df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d,date) else np.nan).astype("Int64")

    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)

    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"]     = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"]  = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)

    # arrondis
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)

    # ordre
    ordered_cols = [c for c in BASE_COLS if c in df.columns]
    rest_cols = [c for c in df.columns if c not in ordered_cols]
    return df[ordered_cols + rest_cols]

def split_totals(df: pd.DataFrame):
    if df is None or df.empty: return df, df
    mask = df["nom_client"].astype(str).str.strip().str.lower().eq("total")
    return df[~mask].copy(), df[mask].copy()

def sort_core(df: pd.DataFrame):
    if df is None or df.empty: return df
    return df.sort_values(["date_arrivee","nom_client"], na_position="last").reset_index(drop=True)

# ==============================  EXCEL I/O  ==============================

@st.cache_data(show_spinner=False)
def _read_excel_cached(path: str, mtime: float):
    return pd.read_excel(path, engine="openpyxl", converters={"telephone": normalize_tel})

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

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    core, totals = split_totals(df)
    out = pd.concat([sort_core(core), totals], ignore_index=True)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            out.to_excel(w, index=False, sheet_name="Sheet1")
        st.cache_data.clear()
        st.success("💾 Sauvegarde Excel effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde Excel : {e}")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer fichier Excel", type=["xlsx"], help="Remplace le fichier actuel")
    if up is not None:
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            bio = BytesIO(raw)
            df_new = pd.read_excel(bio, engine="openpyxl", converters={"telephone": normalize_tel})
            df_new = ensure_schema(df_new)
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import: {e}")

def bouton_telecharger(df: pd.DataFrame):
    buf = BytesIO()
    data_xlsx = b""
    try:
        ensure_schema(df).to_excel(buf, index=False, engine="openpyxl")
        data_xlsx = buf.getvalue()
    except Exception as e:
        st.sidebar.error(f"Export XLSX indisponible : {e}")
        data_xlsx = b""
    st.sidebar.download_button(
        "💾 Sauvegarde xlsx",
        data=data_xlsx,
        file_name="reservations.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=(len(data_xlsx) == 0),
        help="Télécharge une copie locale du fichier actuel."
    )

# ==============================  ICS EXPORT  ==============================

def _fmt_date_ics(d: date) -> str: return d.strftime("%Y%m%d")
def _dtstamp_utc_now() -> str: return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

def df_to_ics(df: pd.DataFrame, cal_name: str = "Villa Tobias – Réservations") -> str:
    df = ensure_schema(df)
    core, _ = split_totals(df)
    core = sort_core(core)
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        f"X-WR-CALNAME:{cal_name}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for _, row in core.iterrows():
        d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)): continue
        plateforme = str(row.get("plateforme") or "").strip()
        nom_client = str(row.get("nom_client") or "").strip()
        tel = str(row.get("telephone") or "").strip()
        uid_src = f"{nom_client}|{plateforme}|{d1}|{d2}|{tel}|v1"
        uid = f"vt-{hashlib.sha1(uid_src.encode()).hexdigest()}@villatobias"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{uid}",
            f"DTSTAMP:{_dtstamp_utc_now()}",
            f"DTSTART;VALUE=DATE:{_fmt_date_ics(d1)}",
            f"DTEND;VALUE=DATE:{_fmt_date_ics(d2)}",
            f"SUMMARY:{plateforme} - {nom_client} - {tel}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

# ==============================  SMS (MANUEL) ==============================

def sms_message_arrivee(row: pd.Series) -> str:
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
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
        "Bienvenue chez nous !\n\n"
        "Nous sommes ravis de vous accueillir bientot à Nice. Merci de nous indiquer votre heure d'arrivee.\n\n"
        "Check-in à partir de 14h, check-out au plus tard 11h.\n\n"
        "Annick & Charley"
    )

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Merci d’avoir choisi notre appartement pour votre séjour ! "
        "Au plaisir de vous accueillir à nouveau.\n\n"
        "Annick & Charley"
    )

# ==============================  UI HELPERS (KPI) ==============================

def kpi_chips(df: pd.DataFrame):
    core, _ = split_totals(df)
    if core.empty: return
    b = float(core["prix_brut"].sum() or 0)
    comm = float(core["commissions"].sum() or 0)
    cb   = float(core["frais_cb"].sum() or 0)
    ch = comm + cb
    n = float(core["prix_net"].sum() or 0)
    base = float(core["base"].sum() or 0)
    nuits = int(core["nuitees"].sum() or 0)
    pct = (ch / b * 100) if b else 0
    pm_nuit = (b / nuits) if nuits else 0
    st.markdown(
        f"""
        <div style="display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 10px 0;">
          <div class="chip"><b>Total Brut</b><div class="v">{b:,.2f} €</div></div>
          <div class="chip"><b>Total Net</b><div class="v">{n:,.2f} €</div></div>
          <div class="chip"><b>Total Base</b><div class="v">{base:,.2f} €</div></div>
          <div class="chip"><b>Total Charges</b><div class="v">{ch:,.2f} €</div></div>
          <div class="chip"><b>Nuitées</b><div class="v">{nuits}</div></div>
          <div class="chip"><b>Commission moy.</b><div class="v">{pct:.2f} %</div></div>
          <div class="chip"><b>Prix moyen/nuit</b><div class="v">{pm_nuit:,.2f} €</div></div>
        </div>
        <style>
        .chip {{ padding:8px 10px; border-radius:10px; background: rgba(127,127,127,0.12);
                border: 1px solid rgba(127,127,127,0.25); font-size:0.9rem; }}
        .chip b {{ display:block; margin-bottom:3px; font-size:0.85rem; opacity:0.8; }}
        .chip .v {{ font-weight:600; }}
        </style>
        """,
        unsafe_allow_html=True
    )

# ==============================  VUES  ==============================

def vue_reservations(df: pd.DataFrame):
    palette = get_palette()
    st.title("📋 Réservations")
    st.caption(APP_SIGNATURE)
    with st.expander("🎛️ Options d’affichage", expanded=True):
        filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
        show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)

    st.markdown("### Plateformes")
    if palette:
        badges = " &nbsp;&nbsp;".join([platform_badge(pf, palette) for pf in sorted(palette.keys())])
        st.markdown(badges, unsafe_allow_html=True)

    df = ensure_schema(df)
    if filtre_paye == "Payé":
        df = df[df["paye"] == True].copy()
    elif filtre_paye == "Non payé":
        df = df[df["paye"] == False].copy()

    if show_kpi: kpi_chips(df)

    if enable_search:
        q = st.text_input("🔎 Recherche (nom, plateau, tel)")
        if q:
            ql = q.strip().lower()
            def _m(v): return ql in ("" if pd.isna(v) else str(v)).lower()
            mask = df["nom_client"].apply(_m) | df["plateforme"].apply(_m) | df["telephone"].apply(_m)
            df = df[mask].copy()

    show = df.copy()
    show["date_arrivee"] = show["date_arrivee"].apply(format_date_str)
    show["date_depart"]  = show["date_depart"].apply(format_date_str)
    st.dataframe(show, use_container_width=True)

def vue_calendrier(df: pd.DataFrame):
    palette = get_palette()
    st.title("📅 Calendrier (simple)")
    df = ensure_schema(df)
    if df.empty:
        return st.info("Aucune donnée.")
    mois = st.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees: return st.warning("Aucune année.")
    annee = st.selectbox("Année", annees, index=len(annees)-1)
    m_idx = list(calendar.month_name).index(mois)
    nbj = calendar.monthrange(annee, m_idx)[1]
    jours = [date(annee, m_idx, j+1) for j in range(nbj)]
    core, _ = split_totals(df)
    planning = {j: [] for j in jours}
    for _, r in core.iterrows():
        d1, d2 = r["date_arrivee"], r["date_depart"]
        if not (isinstance(d1,date) and isinstance(d2,date)): continue
        for j in jours:
            if d1 <= j < d2:
                planning[j].append((str(r["plateforme"]), str(r["nom_client"])))
    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    monthcal = calendar.monthcalendar(annee, m_idx)
    table = []
    for sem in monthcal:
        row = []
        for j in sem:
            if j == 0:
                row.append("")
            else:
                d = date(annee, m_idx, j)
                noms = [nm for _, nm in planning[d]]
                txt = str(j) + ("".join([f"\n{nm}" for nm in noms]) if noms else "")
                row.append(txt)
        table.append(row)
    st.table(pd.DataFrame(table, columns=headers))

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport (aperçu)")
    df = ensure_schema(df)
    if df.empty: return st.info("Aucune donnée.")
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    annee = st.selectbox("Année", annees, index=len(annees)-1)
    st.dataframe(df[df["AAAA"] == annee], use_container_width=True)

def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS (modèles)")
    df = ensure_schema(df)
    if df.empty: return st.info("Aucune donnée.")
    # simple aperçu : on affiche les deux modèles
    st.subheader("Modèle : Arrivée")
    st.code(sms_message_arrivee(df.iloc[0]))
    st.subheader("Modèle : Départ")
    st.code(sms_message_depart(df.iloc[0]))

def vue_export_ics(df: pd.DataFrame):
    st.title("📤 Export ICS")
    df = ensure_schema(df)
    ics_text = df_to_ics(df)
    st.download_button(
        "⬇️ Télécharger reservations.ics",
        data=ics_text.encode("utf-8"),
        file_name="reservations.ics",
        mime="text/calendar"
    )
    st.caption("Import dans Google Agenda → Paramètres → Importer.")

# ==============================  APP  ==============================

def main():
    # Sidebar: Fichier + Palette + Maintenance
    st.sidebar.title("📁 Fichier")
    df_tmp = charger_donnees()
    bouton_telecharger(df_tmp)
    bouton_restaurer()
    render_palette_editor_sidebar()
    render_cache_section_sidebar()

    # Navigation
    st.sidebar.title("🧭 Navigation")
    page = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","📅 Calendrier","📊 Rapport","✉️ SMS","📤 Export ICS"]
    )

    df = charger_donnees()

    if page == "📋 Réservations":
        safe_view(vue_reservations, df)
    elif page == "📅 Calendrier":
        safe_view(vue_calendrier, df)
    elif page == "📊 Rapport":
        safe_view(vue_rapport, df)
    elif page == "✉️ SMS":
        safe_view(vue_sms, df)
    elif page == "📤 Export ICS":
        safe_view(vue_export_ics, df)

if __name__ == "__main__":
    main()