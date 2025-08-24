# palette_utils.py — lecture/écriture de la palette + éditeur sidebar

import streamlit as st
import pandas as pd
from io import BytesIO
from typing import Dict
import os

# Ces fonctions/constantes doivent déjà exister dans io_utils.py
from io_utils import FICHIER, charger_donnees, ensure_schema, sauvegarder_donnees

DEFAULT_PALETTE: Dict[str, str] = {
    "Booking": "#1e90ff",  # bleu
    "Airbnb":  "#e74c3c",  # rouge
    "Autre":   "#f59e0b",  # orange
}

SHEET_PLAT = "Plateformes"   # onglet Excel des plateformes
COL_NAME    = "nom"
COL_COLOR   = "couleur"

# ---------- Excel I/O ----------

def _read_platform_sheet() -> pd.DataFrame:
    """Retourne la feuille Plateformes si elle existe, sinon DataFrame vide."""
    if not os.path.exists(FICHIER):
        return pd.DataFrame(columns=[COL_NAME, COL_COLOR])
    try:
        xls = pd.ExcelFile(FICHIER, engine="openpyxl")
        if SHEET_PLAT in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=SHEET_PLAT, engine="openpyxl")
            df = df[[COL_NAME, COL_COLOR]].dropna(how="all")
            df[COL_NAME]  = df[COL_NAME].astype(str).str.strip()
            df[COL_COLOR] = df[COL_COLOR].astype(str).str.strip()
            df = df[df[COL_NAME] != ""]
            return df.reset_index(drop=True)
        else:
            return pd.DataFrame(columns=[COL_NAME, COL_COLOR])
    except Exception:
        return pd.DataFrame(columns=[COL_NAME, COL_COLOR])

def _write_platform_sheet(df_plat: pd.DataFrame):
    """Écrit/écrase la feuille Plateformes en préservant la feuille principale."""
    # On lit tout le fichier puis on réécrit toutes les feuilles.
    # La feuille principale (réservations) est gérée via sauvegarder_donnees.
    # Ici on manipule directement le writer pour ne pas casser l’autre feuille.
    try:
        # Charger le fichier existant en mémoire
        xls_bytes = None
        if os.path.exists(FICHIER):
            with open(FICHIER, "rb") as f:
                xls_bytes = f.read()

        with pd.ExcelWriter(FICHIER, engine="openpyxl", mode="w") as writer:
            # Réécrire la feuille des réservations actuelle
            df_resa = charger_donnees()
            df_resa = ensure_schema(df_resa)
            df_resa.to_excel(writer, index=False, sheet_name="Sheet1")

            # Écrire la feuille Plateformes
            out = df_plat.copy()
            out = out[[COL_NAME, COL_COLOR]]
            out.to_excel(writer, index=False, sheet_name=SHEET_PLAT)
    except Exception as e:
        st.error(f"Échec d’écriture de la feuille Plateformes : {e}")

def load_palette_from_excel() -> Dict[str, str]:
    df = _read_platform_sheet()
    if df.empty:
        # Si pas de feuille, on retourne au moins la palette par défaut
        return DEFAULT_PALETTE.copy()
    pal = {}
    for _, r in df.iterrows():
        name  = str(r.get(COL_NAME, "")).strip()
        color = str(r.get(COL_COLOR, "")).strip()
        if name and color.startswith("#"):
            pal[name] = color
    if not pal:
        pal = DEFAULT_PALETTE.copy()
    return pal

def save_palette_to_excel(palette: Dict[str, str]):
    rows = []
    for k, v in palette.items():
        if k and isinstance(k, str) and isinstance(v, str) and v.startswith("#"):
            rows.append({COL_NAME: k, COL_COLOR: v})
    df = pd.DataFrame(rows, columns=[COL_NAME, COL_COLOR])
    _write_platform_sheet(df)

# ---------- Session palette ----------

def get_palette() -> Dict[str, str]:
    if "palette" not in st.session_state:
        st.session_state.palette = load_palette_from_excel()
    # Assainissement minimum
    pal = {}
    for k, v in st.session_state.palette.items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4, 7):
            pal[k] = v
    st.session_state.palette = pal
    return pal

def set_palette(palette: Dict[str, str]):
    st.session_state.palette = {str(k): str(v) for k, v in palette.items() if k and v}

# ---------- Sidebar mini-aperçu (facultatif) ----------

def render_palette_editor_sidebar():
    """Petit éditeur rapide dans la sidebar (utile mais l’onglet principal reste la référence)."""
    st.sidebar.markdown("## 🎨 Plateformes")
    pal = get_palette()
    if pal:
        badges = " &nbsp;&nbsp;".join([
            f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{pal[n]};border-radius:3px;margin-right:6px;"></span>{n}'
            for n in sorted(pal.keys())
        ])
        st.sidebar.markdown(badges, unsafe_allow_html=True)
    with st.sidebar.expander("Ajuster (rapide)"):
        c1, c2 = st.columns([2, 1])
        name  = c1.text_input("Nom", key="sb_pf_name", placeholder="Ex: Expedia")
        color = c2.color_picker("Couleur", key="sb_pf_color", value="#9b59b6")
        cA, cB = st.columns(2)
        if cA.button("Ajouter / MAJ"):
            if name.strip():
                pal[name.strip()] = color
                set_palette(pal)
                save_palette_to_excel(pal)
                st.sidebar.success("Plateforme enregistrée.")
        if cB.button("Réinitialiser défaut"):
            set_palette(DEFAULT_PALETTE.copy())
            save_palette_to_excel(DEFAULT_PALETTE.copy())
            st.sidebar.success("Palette réinitialisée.")