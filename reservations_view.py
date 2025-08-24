import streamlit as st
from io_utils import ensure_schema, sauvegarder_donnees

def vue_reservations(df):
    st.title("📋 Réservations")
    df = ensure_schema(df)

    edited = st.data_editor(df, use_container_width=True, hide_index=True)

    if st.button("💾 Sauvegarder"):
        sauvegarder_donnees(edited)
        st.success("✅ Réservations mises à jour.")
