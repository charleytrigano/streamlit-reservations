# app.py — Étape 1 (testable) : Fichier, Réservations, Plateformes

import streamlit as st
from utils import (
    FICHIER, bouton_restaurer, bouton_telecharger,
    get_palette_session, set_palette_session, charger_palette_excel
)
from reservations import vue_reservations
from plateformes import vue_plateformes

st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

def sidebar_fichier():
    st.sidebar.title("📁 Fichier")
    bouton_restaurer()
    # Télécharger l'état actuel (réservations + plateformes)
    from utils import charger_donnees
    bouton_telecharger(charger_donnees())

    st.sidebar.markdown("---")
    st.sidebar.caption(f"Fichier courant : **{FICHIER}**")

    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider cache & relancer"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        st.success("Cache vidé.")
        st.rerun()

def main():
    # Charger palette au démarrage (Excel -> session), si possible
    pal = charger_palette_excel()
    if pal:
        set_palette_session(pal)
    else:
        get_palette_session()  # initialise défaut si besoin

    sidebar_fichier()

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio("Aller à", ["📋 Réservations","🔧 Plateformes (couleurs)"])

    if onglet == "📋 Réservations":
        vue_reservations()
    else:
        vue_plateformes()

if __name__ == "__main__":
    main()