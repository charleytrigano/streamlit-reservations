# plateformes_view.py — Onglet complet pour gérer les plateformes (CRUD)

import streamlit as st
import pandas as pd
from palette_utils import (
    get_palette, set_palette,
    load_palette_from_excel, save_palette_to_excel,
    SHEET_PLAT, COL_NAME, COL_COLOR
)

def vue_plateformes():
    st.title("🎛️ Plateformes (couleurs & gestion)")
    st.caption("Ici vous pouvez **ajouter, renommer, supprimer** des plateformes et définir leur **couleur**. Les changements sont enregistrés dans la feuille Excel « Plateformes ».")

    pal = load_palette_from_excel()
    st.session_state.palette = pal  # sync

    # Tableau éditable
    rows = [{"nom": k, "couleur": v} for k, v in pal.items()]
    df = pd.DataFrame(rows, columns=[COL_NAME, COL_COLOR])

    edited = st.data_editor(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            COL_NAME:  st.column_config.TextColumn("Nom de la plateforme"),
            COL_COLOR: st.column_config.ColorPickerColumn("Couleur"),
        },
        num_rows="dynamic",
    )

    c1, c2, c3 = st.columns([1,1,2])
    if c1.button("💾 Enregistrer"):
        # Validation basique
        new_pal = {}
        for _, r in edited.iterrows():
            name  = str(r.get(COL_NAME, "")).strip()
            color = str(r.get(COL_COLOR, "")).strip()
            if name and color.startswith("#"):
                new_pal[name] = color
        if not new_pal:
            st.error("Aucune plateforme valide (nom + couleur).")
            return
        set_palette(new_pal)
        save_palette_to_excel(new_pal)
        st.success("✅ Plateformes enregistrées dans Excel.")
        st.experimental_rerun()

    if c2.button("➕ Ajouter une ligne"):
        edited.loc[len(edited)] = {COL_NAME: "", COL_COLOR: "#9b59b6"}
        st.experimental_rerun()

    st.markdown("---")
    if pal:
        st.subheader("Aperçu")
        badges = " &nbsp;&nbsp;".join([
            f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{pal[n]};border-radius:3px;margin-right:6px;"></span>{n}'
            for n in sorted(pal.keys())
        ])
        st.markdown(badges, unsafe_allow_html=True)
