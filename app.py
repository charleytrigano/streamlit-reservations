# app.py — Villa Tobias (projet découpé par onglet)
import sys, os
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)






import streamlit as st
from io_utils import (
    charger_donnees, sauvegarder_donnees, bouton_telecharger, bouton_restaurer,
    get_palette_from_excel, save_palette_to_excel, FICHIER
)

# Vues
from views.reservations import vue_reservations, vue_ajouter, vue_modifier
from views.calendrier import vue_calendrier
from views.rapport import vue_rapport
from views.clients import vue_clients
from views.export_ics import vue_export_ics
from views.sms import vue_sms
from views.plateformes import vue_plateformes

st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

def section_fichier_palette():
    st.sidebar.title("📁 Fichier")
    df_tmp = charger_donnees()
    bouton_telecharger(df_tmp)
    bouton_restaurer()
    st.sidebar.caption(f"📄 Fichier actuel : `{FICHIER}`")

    # Info palette chargée depuis Excel
    pal = get_palette_from_excel()
    chips = " ".join(
        [f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{pal[k]};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{k}'
         for k in sorted(pal.keys())]
    )
    st.sidebar.markdown("**Plateformes (palette)**")
    st.sidebar.markdown(chips or "—", unsafe_allow_html=True)

def section_maintenance():
    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache et relancer"):
        try:
            st.cache_data.clear()
        except Exception:
            pass
        try:
            st.cache_resource.clear()
        except Exception:
            pass
        st.sidebar.success("Cache vidé. Redémarrage…")
        st.rerun()

def main():
    section_fichier_palette()
    section_maintenance()

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        [
            "📋 Réservations",
            "➕ Ajouter",
            "✏️ Modifier / Supprimer",
            "📅 Calendrier",
            "📊 Rapport",
            "👥 Liste clients",
            "📤 Export ICS",
            "✉️ SMS",
            "🎨 Plateformes",
        ],
        index=0,
    )

    df = charger_donnees()
    palette = get_palette_from_excel()

    if onglet == "📋 Réservations":
        vue_reservations(df, palette)
    elif onglet == "➕ Ajouter":
        vue_ajouter(df, palette, on_save=sauvegarder_donnees)
    elif onglet == "✏️ Modifier / Supprimer":
        vue_modifier(df, palette, on_save=sauvegarder_donnees)
    elif onglet == "📅 Calendrier":
        vue_calendrier(df, palette)
    elif onglet == "📊 Rapport":
        vue_rapport(df)
    elif onglet == "👥 Liste clients":
        vue_clients(df)
    elif onglet == "📤 Export ICS":
        vue_export_ics(df)
    elif onglet == "✉️ SMS":
        vue_sms(df)
    elif onglet == "🎨 Plateformes":
        # CRUD palette persistant dans Excel
        changed = vue_plateformes(palette)
        if changed is not None:
            save_palette_to_excel(changed)
            st.success("✅ Palette enregistrée dans `reservations.xlsx` (feuille Plateformes).")
            st.rerun()

if __name__ == "__main__":
    main()