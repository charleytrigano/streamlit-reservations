# palette_utils.py — accès palette (dict) + éditeur rapide optionnel

import streamlit as st
import pandas as pd
from io_utils import read_palette_from_excel, write_palette_to_excel, charger_donnees

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def get_palette_dict() -> dict:
    pal_df = read_palette_from_excel()
    if pal_df is None or pal_df.empty:
        return DEFAULT_PALETTE.copy()
    d = {}
    for _, r in pal_df.iterrows():
        name = str(r.get("plateforme","")).strip()
        col  = str(r.get("couleur","#999999")).strip()
        if name:
            d[name] = col
    return d

def save_palette_dict(d: dict):
    pal_df = pd.DataFrame({"plateforme": list(d.keys()), "couleur": list(d.values())})
    write_palette_to_excel(pal_df)

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

def render_palette_editor_sidebar():
    pal_dict = get_palette_dict()
    st.markdown("**Aperçu de la palette**")
    if pal_dict:
        st.markdown(
            " &nbsp;&nbsp;".join([platform_badge(k, pal_dict) for k in sorted(pal_dict.keys())]),
            unsafe_allow_html=True
        )
    with st.expander("Modifier rapidement (palette)"):
        for k in sorted(pal_dict.keys()):
            new = st.color_picker(k, pal_dict[k], key=f"pal_col_{k}")
            pal_dict[k] = new
        if st.button("Enregistrer la palette"):
            save_palette_dict(pal_dict)
            st.success("Palette enregistrée.")
            st.rerun()