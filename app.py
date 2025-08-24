# app.py — Base stable (Réservations OK + erreurs visibles + Excel openpyxl)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os

# ---------- Fichier de travail ----------
FICHIER = "reservations.xlsx"

# ---------- Page ----------
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ---------- Session flags ----------
if "did_clear_cache" not in st.session_state:
    st.session_state.did_clear_cache = False

# ---------- Palette plateformes ----------
DEFAULT_PALETTE = {"Booking": "#1e90ff", "Airbnb": "#e74c3c", "Autre": "#f59e0b"}

def get_palette() -> dict:
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    pal = {}
    for k, v in st.session_state.palette.items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4, 7):
            pal[k] = v
    st.session_state.palette = pal
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = {str(k): str(v) for k, v in palette.items() if k and v}

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
            new_name = st.text_input("Nom", key="pal_new_name")
        with c2:
            new_color = st.color_picker("Couleur", key="pal_new_color", value="#9b59b6")
        colA, colB = st.columns(2)
        if colA.button("Ajouter / MAJ"):
            name = (new_name or "").strip()
            if not name:
                st.warning("Entrez un nom de plateforme.")
            else:
                palette[name] = new_color
                save_palette(palette)
                st.success(f"✅ « {name} » enregistrée.")
        if colB.button("Réinitialiser"):
            save_palette(DEFAULT_PALETTE.copy())
            st.success("✅ Palette réinitialisée.")
    if palette:
        st.sidebar.markdown("**Plateformes :**")
        for pf in sorted(palette.keys()):
            cols = st.sidebar.columns([1, 3, 1])
            with cols[0]:
                st.markdown(
                    f'<span style="display:inline-block;width:1.1em;height:1.1em;background:{palette[pf]};border-radius:3px;"></span>',
                    unsafe_allow_html=True,
                )
            cols[1].markdown(pf)

# ---------- Utils ----------
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

BASE_COLS = [
    "paye","nom_client","sms_envoye","plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%","AAAA","MM","ical_uid"
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
    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
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
    ordered = [c for c in BASE_COLS if c in df.columns]
    rest = [c for c in df.columns if c not in ordered]
    return df[ordered + rest]

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

# ---------- Excel I/O ----------
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

def _force_telephone_text_format_openpyxl(writer, df_to_save: pd.DataFrame, sheet_name: str):
    try:
        ws = writer.sheets.get(sheet_name) or writer.sheets.get('Sheet1', None)
        if ws is None or "telephone" not in df_to_save.columns:
            return
        col_idx = df_to_save.columns.get_loc("telephone") + 1
        for row in ws.iter_rows(min_row=2, max_row=ws.max_row, min_col=col_idx, max_col=col_idx):
            row[0].number_format = '@'
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
    if up is not None and st.sidebar.button("Restaurer maintenant"):
        try:
            raw = up.read()
            if not raw:
                raise ValueError("Fichier vide.")
            df_new = pd.read_excel(BytesIO(raw), engine="openpyxl", converters={"telephone": normalize_tel})
            df_new = ensure_schema(df_new)
            sauvegarder_donnees(df_new)
            st.sidebar.success("✅ Fichier restauré.")
            st.experimental_rerun()
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
    )

# ---------- KPI + recherche ----------
def kpi_chips(df: pd.DataFrame):
    core, _ = split_totals(df)
    if core.empty:
        return
    b = core["prix_brut"].sum()
    total_comm = core["commissions"].sum()
    total_cb   = core["frais_cb"].sum()
    ch = total_comm + total_cb
    n = core["prix_net"].sum()
    base = core["base"].sum()
    nuits = core["nuitees"].sum()
    pct = (ch / b * 100) if b else 0
    pm_nuit = (b / nuits) if nuits else 0
    html = f"""
    <style>.chips-wrap{{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 10px 0}}
    .chip{{padding:8px 10px;border-radius:10px;background:rgba(127,127,127,0.12);
    border:1px solid rgba(127,127,127,0.25);font-size:0.9rem}}</style>
    <div class="chips-wrap">
      <div class="chip"><b>Total Brut</b> {b:,.2f} €</div>
      <div class="chip"><b>Total Net</b> {n:,.2f} €</div>
      <div class="chip"><b>Base</b> {base:,.2f} €</div>
      <div class="chip"><b>Charges</b> {ch:,.2f} €</div>
      <div class="chip"><b>Nuitées</b> {int(nuits) if pd.notna(nuits) else 0}</div>
      <div class="chip"><b>Comm. moy.</b> {pct:.2f} %</div>
      <div class="chip"><b>€/nuit (brut)</b> {pm_nuit:,.2f} €</div>
    </div>"""
    st.markdown(html, unsafe_allow_html=True)

def search_box(df: pd.DataFrame) -> pd.DataFrame:
    q = st.text_input("🔎 Recherche (nom, plateforme, téléphone…)", "")
    if not q:
        return df
    ql = q.strip().lower()
    def _m(v): s = "" if pd.isna(v) else str(v); return ql in s.lower()
    mask = df["nom_client"].apply(_m) | df["plateforme"].apply(_m) | df["telephone"].apply(_m)
    return df[mask].copy()

# ---------- VUES ----------
def vue_reservations(df: pd.DataFrame):
    try:
        palette = get_palette()
        st.title("📋 Réservations")
        with st.expander("🎛️ Options d’affichage", expanded=True):
            filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
            show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
            enable_search = st.checkbox("Activer la recherche", value=True)

        if palette:
            st.markdown("### Plateformes")
            badges = " &nbsp;&nbsp;".join([platform_badge(pf, palette) for pf in sorted(palette.keys())])
            st.markdown(badges, unsafe_allow_html=True)

        df = ensure_schema(df)

        if filtre_paye == "Payé":
            df = df[df["paye"] == True].copy()
        elif filtre_paye == "Non payé":
            df = df[df["paye"] == False].copy()

        if show_kpi:
            kpi_chips(df)
        if enable_search:
            df = search_box(df)

        core, totals = split_totals(df)
        core = sort_core(core)

        if core.empty and totals.empty:
            st.info("Aucune ligne à afficher.")
            return

        core_edit = core.copy()
        core_edit["__rowid"] = core_edit.index
        core_edit["date_arrivee"] = core_edit["date_arrivee"].apply(format_date_str)
        core_edit["date_depart"]  = core_edit["date_depart"].apply(format_date_str)

        cols_order = [
            "paye","nom_client","sms_envoye","plateforme","telephone",
            "date_arrivee","date_depart","nuitees",
            "prix_brut","commissions","frais_cb","prix_net",
            "menage","taxes_sejour","base","charges","%","AAAA","MM","__rowid"
        ]
        cols_show = [c for c in cols_order if c in core_edit.columns]

        edited = st.data_editor(
            core_edit[cols_show],
            use_container_width=True,
            hide_index=True,
            column_config={
                "paye": st.column_config.CheckboxColumn("Payé"),
                "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
                "__rowid": st.column_config.Column("id", help="Interne", disabled=True, width="small"),
                "date_arrivee": st.column_config.TextColumn("date_arrivee", disabled=True),
                "date_depart":  st.column_config.TextColumn("date_depart", disabled=True),
                "nom_client":   st.column_config.TextColumn("nom_client", disabled=True),
                "plateforme":   st.column_config.TextColumn("plateforme", disabled=True),
                "telephone":    st.column_config.TextColumn("telephone", disabled=True),
                "nuitees":      st.column_config.NumberColumn("nuitees", disabled=True),
                "prix_brut":    st.column_config.NumberColumn("prix_brut", disabled=True),
                "commissions":  st.column_config.NumberColumn("commissions", disabled=True),
                "frais_cb":     st.column_config.NumberColumn("frais_cb", disabled=True),
                "prix_net":     st.column_config.NumberColumn("prix_net", disabled=True),
                "menage":       st.column_config.NumberColumn("menage", disabled=True),
                "taxes_sejour": st.column_config.NumberColumn("taxes_sejour", disabled=True),
                "base":         st.column_config.NumberColumn("base", disabled=True),
                "charges":      st.column_config.NumberColumn("charges", disabled=True),
                "%":            st.column_config.NumberColumn("%", disabled=True),
                "AAAA":         st.column_config.NumberColumn("AAAA", disabled=True),
                "MM":           st.column_config.NumberColumn("MM", disabled=True),
            }
        )

        c1, _ = st.columns([1,3])
        if c1.button("💾 Enregistrer les cases cochées"):
            if edited is not None and not edited.empty:
                for _, r in edited.iterrows():
                    ridx = int(r["__rowid"])
                    if ridx in core.index:
                        core.at[ridx, "paye"] = bool(r.get("paye", False))
                        core.at[ridx, "sms_envoye"] = bool(r.get("sms_envoye", False))
                new_df = pd.concat([core, totals], ignore_index=False).reset_index(drop=True)
                sauvegarder_donnees(new_df)
                st.success("✅ Statuts Payé / SMS mis à jour.")
                st.experimental_rerun()
            else:
                st.info("Rien à enregistrer.")

        if not totals.empty:
            show_tot = totals.copy()
            for c in ["date_arrivee","date_depart"]:
                show_tot[c] = show_tot[c].apply(format_date_str)
            st.caption("Lignes de totaux (non éditables) :")
            cols_tot = [
                "paye","nom_client","sms_envoye","plateforme","telephone",
                "date_arrivee","date_depart","nuitees",
                "prix_brut","commissions","frais_cb","prix_net",
                "menage","taxes_sejour","base","charges","%","AAAA","MM"
            ]
            cols_tot = [c for c in cols_tot if c in show_tot.columns]
            st.dataframe(show_tot[cols_tot], use_container_width=True)

    except Exception as e:
        st.error("Erreur dans l’onglet « Réservations » :")
        st.exception(e)

# ---- Placeholders sûrs pour les autres onglets (pas d’erreur si cliqués) ----
def vue_ajouter(df): st.info("➕ Ajouter : (placeholder)"); st.write("À compléter.")
def vue_modifier(df): st.info("✏️ Modifier / Supprimer : (placeholder)"); st.write("À compléter.")
def vue_calendrier(df): st.info("📅 Calendrier : (placeholder)"); st.write("À compléter.")
def vue_rapport(df): st.info("📊 Rapport : (placeholder)"); st.write("À compléter.")
def vue_clients(df): st.info("👥 Clients : (placeholder)"); st.write("À compléter.")
def vue_export_ics(df): st.info("📤 Export ICS : (placeholder)"); st.write("À compléter.")
def vue_sms(df): st.info("✉️ SMS : (placeholder)"); st.write("À compléter.")

# ---------- Main ----------
def main():
    # Sidebar : Fichier & Palette & Maintenance
    st.sidebar.title("📁 Fichier")
    df_tmp = charger_donnees()
    bouton_telecharger(df_tmp)
    bouton_restaurer()
    render_palette_editor_sidebar()
    st.sidebar.markdown("---")
    if st.sidebar.button("♻️ Vider le cache"):
        try:
            st.cache_data.clear()
            st.cache_resource.clear()
            st.sidebar.success("Cache vidé.")
        except Exception as e:
            st.sidebar.error(f"Erreur: {e}")

    # Navigation
    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS"]
    )

    # Données
    df = charger_donnees()

    # Route
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
    try:
        main()
    except Exception as e:
        st.error("Une erreur globale est survenue :")
        st.exception(e)