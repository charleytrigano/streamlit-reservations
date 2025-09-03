import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import openpyxl

# ==================== CONFIGURATION ====================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

FICHIER = "reservations.xlsx"
PALETTE_SHEET = "Plateformes"
DATA_SHEET = "Sheet1"
DEFAULT_PALETTE = {"Booking": "#1e90ff", "Airbnb": "#e74c3c", "Autre": "#f59e0b"}
BASE_COLS = [
    "paye", "nom_client", "sms_envoye", "plateforme", "telephone", "date_arrivee",
    "date_depart", "nuitees", "prix_brut", "commissions", "frais_cb", "prix_net",
    "menage", "taxes_sejour", "base", "charges", "%", "AAAA", "MM", "ical_uid"
]

# ==================== OUTILS ====================
def _clean_hex(c: str) -> str:
    if not isinstance(c, str): return "#999999"
    c = c.strip()
    if not c.startswith("#"): c = "#" + c
    if len(c) in (4,7): return c
    return "#999999"

def to_date_only(x):
    if pd.isna(x) or x is None: return None
    try: return pd.to_datetime(x).date()
    except Exception: return None

def normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)): return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"): s = s[:-2]
    return s

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy() if df is not None else pd.DataFrame()
    for c in BASE_COLS:
        if c not in df.columns: df[c] = np.nan
    if "paye" in df.columns: df["paye"] = df["paye"].fillna(False).astype(bool)
    if "sms_envoye" in df.columns: df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee", "date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    if "date_arrivee" in df.columns and "date_depart" in df.columns:
        df["nuitees"] = [
            (d2 - d1).days if (isinstance(d1, date) and isinstance(d2, date)) else np.nan
            for d1, d2 in zip(df["date_arrivee"], df["date_depart"])
        ]
    if "date_arrivee" in df.columns:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d, date) else np.nan).astype("Int64")
        df["MM"] = df["date_arrivee"].apply(lambda d: d.month if isinstance(d, date) else np.nan).astype("Int64")
    df["nom_client"] = df["nom_client"].fillna("")
    df["plateforme"] = df["plateforme"].fillna("Autre")
    df["ical_uid"] = df["ical_uid"].fillna("")
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]:
        df[c] = df[c].fillna(0.0)
    df["prix_net"] = (df["prix_brut"] - df["commissions"] - df["frais_cb"]).clip(lower=0)
    df["base"] = (df["prix_net"] - df["menage"] - df["taxes_sejour"]).clip(lower=0)
    df["charges"] = (df["prix_brut"] - df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na", True):
        df["%"] = (df["charges"] / df["prix_brut"] * 100).fillna(0)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c] = df[c].round(2)
    ordered_cols = [c for c in BASE_COLS if c in df.columns]
    rest_cols = [c for c in df.columns if c not in ordered_cols]
    return df[ordered_cols + rest_cols]

def get_palette():
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    # nettoyage minimal
    pal = {}
    for k, v in st.session_state.palette.items():
        if isinstance(k, str) and isinstance(v, str):
            pal[k.strip()] = _clean_hex(v)
    st.session_state.palette = pal
    return st.session_state.palette

def set_palette(pal: dict):
    st.session_state.palette = { str(k).strip(): _clean_hex(str(v)) for k, v in pal.items() if k and v }

def save_xlsx(df: pd.DataFrame, palette: dict = None):
    df = ensure_schema(df)
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            df.to_excel(w, index=False, sheet_name=DATA_SHEET)
            if palette:
                p = pd.DataFrame([{"plateforme": k, "couleur": v} for k, v in sorted(palette.items())])
                p.to_excel(w, index=False, sheet_name=PALETTE_SHEET)
        st.success("Sauvegarde Excel réussie.")
    except Exception as e:
        st.error(f"Erreur lors de la sauvegarde : {e}")

def load_xlsx():
    if not os.path.exists(FICHIER):
        df, pal = ensure_schema(pd.DataFrame()), DEFAULT_PALETTE
        set_palette(pal)
        return df, pal
    try:
        with pd.ExcelFile(FICHIER, engine="openpyxl") as xf:
            if DATA_SHEET in xf.sheet_names:
                df = pd.read_excel(xf, sheet_name=DATA_SHEET, engine="openpyxl", converters={"telephone": normalize_tel})
            else:
                first = xf.sheet_names
                df = pd.read_excel(xf, sheet_name=first, engine="openpyxl", converters={"telephone": normalize_tel})
            df = ensure_schema(df)
            pal = DEFAULT_PALETTE.copy()
            if PALETTE_SHEET in xf.sheet_names:
                pf_df = pd.read_excel(xf, sheet_name=PALETTE_SHEET, engine="openpyxl")
                if {"plateforme","couleur"}.issubset(set(pf_df.columns)):
                    for _, r in pf_df.iterrows():
                        name = str(r["plateforme"]).strip()
                        color = _clean_hex(str(r["couleur"]))
                        if name: pal[name] = color
            set_palette(pal)
            return df, pal
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame()), DEFAULT_PALETTE

def backup_file():
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    if os.path.exists(FICHIER):
        os.rename(FICHIER, f"{FICHIER}.backup_{ts}")

# ==================== UI GESTION PLATEFORMES ====================
def plateformes_ui():
    st.subheader("Gestion des plateformes & couleurs")
    palette = get_palette()
    mod_palette = palette.copy()
    for pf in list(palette.keys()):
        col1, col2, col3 = st.columns([4, 4, 1])
        with col1:
            new_name = st.text_input(f"Nom plateforme", value=pf, key=f"pf_name_{pf}")
        with col2:
            new_color = st.color_picker(f"Couleur", value=palette[pf], key=f"pf_color_{pf}")
        with col3:
            delete = st.button("Suppr.", key=f"pf_del_{pf}")
        if new_name != pf:
            mod_palette[new_name] = mod_palette.pop(pf)
        mod_palette[new_name] = new_color
        if delete:
            mod_palette.pop(new_name, None)
            st.warning(f"Plateforme '{pf}' supprimée temporairement.")
    stale = st.button("Ajouter une plateforme")
    if stale:
        mod_palette[f"Plateforme_{len(mod_palette)+1}"] = "#CCCCCC"
    set_palette(mod_palette)
    if st.button("Enregistrer plateformes"):
        save_xlsx(df, mod_palette)
        st.success("Palette sauvegardée.")

# ==================== UI AJOUT / MODIFICATION ====================
def form_ajout(df, palette):
    st.subheader("Ajouter une Réservation")
    with st.form(key="add_new"):
        nom_client = st.text_input("Nom du client *")
        telephone = st.text_input("Téléphone *")
        plateforme = st.selectbox("Plateforme", list(palette.keys()))
        date_arrivee = st.date_input("Date d'arrivée", min_value=date.today())
        date_depart = st.date_input("Date de départ", min_value=date_arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut (€)", min_value=0.0, value=100.0)
        commissions = st.number_input("Commissions (€)", min_value=0.0, value=0.0)
        frais_cb = st.number_input("Frais CB (€)", min_value=0.0, value=0.0)
        menage = st.number_input("Ménage (€)", min_value=0.0, value=0.0)
        taxes_sejour = st.number_input("Taxes séjour (€)", min_value=0.0, value=0.0)
        submit = st.form_submit_button("Ajouter la réservation")
    if submit:
        # VALIDATION
        if not nom_client or not telephone:
            st.error("Nom et téléphone obligatoires.")
            return df
        if date_depart <= date_arrivee:
            st.error("Date de départ doit être postérieure à arrivée.")
            return df
        existent = ((df['nom_client']==nom_client) &
                    (df['date_arrivee']==date_arrivee) &
                    (df['date_depart']==date_depart))
        if existent.any():
            st.warning("Une réservation identique existe déjà !")
            return df
        # AJOUT
        new_row = {
            "paye": False, "nom_client": nom_client, "sms_envoye": False, "plateforme": plateforme,
            "telephone": telephone, "date_arrivee": date_arrivee, "date_depart": date_depart,
            "prix_brut": prix_brut, "commissions": commissions, "frais_cb": frais_cb,
            "menage": menage, "taxes_sejour": taxes_sejour
        }
        for key in set(BASE_COLS)-set(new_row.keys()):
            new_row[key] = np.nan
        df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        save_xlsx(df, palette)
        st.success("Réservation ajoutée.")
    return df

# ==================== LISTE DES RESERVATIONS ====================
def liste_resa(df, palette):
    st.subheader("Liste des réservations")
    filt_pf = st.multiselect("Plateformes à afficher", list(palette.keys()), default=list(palette.keys()))
    filt_nom = st.text_input("Filtrer par client (optionnel)")
    filt_annee = st.selectbox("Filtre année", options=["Toutes"] + sorted(df['AAAA'].dropna().unique().astype(str).tolist()))
    dfc = df.copy()
    if filt_pf: dfc = dfc[dfc["plateforme"].isin(filt_pf)]
    if filt_nom: dfc = dfc[dfc["nom_client"].str.contains(filt_nom, case=False)]
    if filt_annee != "Toutes": dfc = dfc[dfc["AAAA"]==int(filt_annee)]
    st.dataframe(dfc[["date_arrivee","date_depart","nom_client","plateforme","prix_brut","prix_net","base","charges"]])

# ==================== EXPORTS ====================
def interface_exports(df, palette):
    st.sidebar.markdown("### Export et restauration")
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name=DATA_SHEET)
        pd.DataFrame([{"plateforme": k, "couleur": v} for k, v in palette.items()]).to_excel(w, index=False, sheet_name=PALETTE_SHEET)
    data_xlsx = buf.getvalue()
    st.sidebar.download_button("💾 Télécharger Excel", data=data_xlsx, file_name="reservations.xlsx")

    up = st.sidebar.file_uploader("Restaurer (XLSX)", type=["xlsx"])
    if up and st.sidebar.button("Restaurer maintenant"):
        backup_file()
        try:
            bio = BytesIO(up.read())
            with pd.ExcelFile(bio, engine="openpyxl") as xf:
                df_new = pd.read_excel(xf, sheet_name=DATA_SHEET)
                pal_df = pd.read_excel(xf, sheet_name=PALETTE_SHEET)
                palette_new = {str(r['plateforme']).strip(): _clean_hex(str(r['couleur'])) for _, r in pal_df.iterrows()}
            save_xlsx(ensure_schema(df_new), palette_new)
            st.success("Fichier restauré !")
            st.rerun()
        except Exception as e:
            st.error(f"Erreur import : {e}")

# ==================== MAIN ====================
df, palette = load_xlsx()
interface_exports(df, palette)
platformes_expand = st.sidebar.expander("Plateformes", expanded=False)
with platformes_expand:
    plateformes_ui()

df = form_ajout(df, palette)
liste_resa(df, palette)
