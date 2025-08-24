# plateformes_view.py — CRUD Plateformes (onglet dédié)

import streamlit as st
import pandas as pd
from io_utils import read_palette_from_excel, write_palette_to_excel, charger_donnees
from palette_utils import platform_badge

def vue_plateformes():
    st.title("🎛️ Plateformes")
    pal = read_palette_from_excel().copy()
    if pal.empty:
        pal = pd.DataFrame({"plateforme":["Booking","Airbnb","Autre"],
                            "couleur":["#1e90ff","#e74c3c","#f59e0b"]})
    pal["plateforme"] = pal["plateforme"].astype(str)

    st.markdown("**Aperçu**")
    badges = " &nbsp;&nbsp;".join([platform_badge(n, dict(zip(pal["plateforme"], pal["couleur"]))) for n in pal["plateforme"]])
    st.markdown(badges, unsafe_allow_html=True)

    st.markdown("---")
    st.subheader("Ajouter / Modifier")
    c1, c2, c3 = st.columns([2,1,1])
    with c1:
        name = st.text_input("Nom plateforme", "")
    with c2:
        col = st.color_picker("Couleur", "#9b59b6")
    with c3:
        st.write("")
        if st.button("Ajouter / Mettre à jour"):
            name2 = (name or "").strip()
            if not name2:
                st.warning("Nom requis.")
            else:
                if name2 in pal["plateforme"].values:
                    pal.loc[pal["plateforme"]==name2, "couleur"] = col
                else:
                    pal = pd.concat([pal, pd.DataFrame([{"plateforme":name2,"couleur":col}])], ignore_index=True)
                write_palette_to_excel(pal, df_resa=charger_donnees())
                st.success("Enregistré.")
                st.rerun()

    st.subheader("Liste")
    st.dataframe(pal, use_container_width=True, hide_index=True)

    # suppression
    st.markdown("### Supprimer")
    if len(pal) > 0:
        choix = st.selectbox("Sélection", pal["plateforme"])
        if st.button("🗑 Supprimer la plateforme"):
            pal = pal[pal["plateforme"] != choix].reset_index(drop=True)
            write_palette_to_excel(pal, df_resa=charger_donnees())
            st.warning(f"Supprimé : {choix}")
            st.rerun()