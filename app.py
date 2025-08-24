# app.py — Villa Tobias
# Script principal qui orchestre les vues et appelle io_utils.py pour I/O

import sys, os
import streamlit as st

# S’assurer que le dossier courant est dans le PYTHONPATH
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

# Import des fonctions utilitaires
from io_utils import (
    charger_donnees, sauvegarder_donnees,
    bouton_restaurer, bouton_telecharger,
    get_palette, save_palette, load_plateformes, save_plateformes
)

# Import des vues
from views_reservations import vue_reservations
from views_calendrier import vue_calendrier
from views_rapport import vue_rapport
from views_clients import vue_clients
from views_sms import vue_sms

# ============================== CONFIG ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ============================== MAIN ==============================
def main():
    st.sidebar.title("🧭 Navigation")
    choix = st.sidebar.radio(
        "Aller à",
        [
            "📋 Réservations",
            "📅 Calendrier",
            "📊 Rapport",
            "👥 Liste clients",
            "✉️ SMS",
            "🎨 Plateformes",
        ]
    )

    # Charger les données principales
    df = charger_donnees()

    # Actions globales : sauvegarde/restauration
    bouton_telecharger(df)
    bouton_restaurer()

    # Choix de la vue
    if choix == "📋 Réservations":
        vue_reservations(df)
    elif choix == "📅 Calendrier":
        vue_calendrier(df)
    elif choix == "📊 Rapport":
        vue_rapport(df)
    elif choix == "👥 Liste clients":
        vue_clients(df)
    elif choix == "✉️ SMS":
        vue_sms(df)
    elif choix == "🎨 Plateformes":
        st.title("🎨 Gestion des plateformes")
        plateformes = load_plateformes()
        st.write("Plateformes actuelles :", plateformes)

        with st.form("ajout_plateforme"):
            nom = st.text_input("Nom de la plateforme")
            couleur = st.color_picker("Couleur", value="#cccccc")
            submitted = st.form_submit_button("Ajouter / Modifier")
            if submitted and nom:
                plateformes[nom] = couleur
                save_plateformes(plateformes)
                st.success(f"✅ Plateforme {nom} enregistrée.")

        if plateformes:
            for pf, col in plateformes.items():
                col1, col2 = st.columns([3,1])
                with col1:
                    st.markdown(
                        f'<span style="display:inline-block;width:1em;height:1em;background:{col};margin-right:6px;"></span>{pf}',
                        unsafe_allow_html=True
                    )
                with col2:
                    if st.button(f"🗑 Supprimer {pf}"):
                        plateformes.pop(pf)
                        save_plateformes(plateformes)
                        st.warning(f"❌ Plateforme {pf} supprimée.")
                        st.rerun()


if __name__ == "__main__":
    main()