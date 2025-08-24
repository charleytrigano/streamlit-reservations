# plateformes.py — onglet Plateformes (ajout / modif / suppression) + sauvegarde Excel

import streamlit as st
from utils import get_palette_session, set_palette_session, sauvegarder_donnees, charger_donnees

def vue_plateformes():
    st.title("🔧 Plateformes (couleurs)")

    pal = dict(get_palette_session())

    st.subheader("Ajouter / modifier")
    c1, c2, c3 = st.columns([2,1,1])
    with c1:
        name = st.text_input("Nom de la plateforme", placeholder="Ex: Expedia")
    with c2:
        color = st.color_picker("Couleur", value="#9b59b6")
    with c3:
        if st.button("Ajouter / Mettre à jour"):
            n = (name or "").strip()
            if not n:
                st.warning("Veuillez saisir un nom.")
            else:
                pal[n] = color
                set_palette_session(pal)
                st.success(f"✅ « {n} » enregistré(e).")

    st.subheader("Existantes")
    if not pal:
        st.info("Aucune plateforme.")
    else:
        for k in sorted(pal.keys()):
            colA, colB, colC = st.columns([4,2,1])
            with colA:
                st.markdown(f"- **{k}**")
            with colB:
                st.markdown(
                    f'<span style="display:inline-block;width:1.2em;height:1.2em;background:{pal[k]};border-radius:3px;border:1px solid #777;"></span>',
                    unsafe_allow_html=True
                )
            with colC:
                if st.button("🗑", key=f"del_{k}"):
                    pal.pop(k, None)
                    set_palette_session(pal)
                    st.experimental_rerun()

    st.markdown("---")
    if st.button("💾 Enregistrer la palette dans Excel"):
        df = charger_donnees()  # on sauvegarde les deux feuilles
        sauvegarder_donnees(df, pal)
        st.success("✅ Palette enregistrée dans reservations.xlsx")
