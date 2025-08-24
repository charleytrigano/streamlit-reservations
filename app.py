# app.py — Shell principal (multi-fichiers)
# ------------------------------------------------------------
# N'affiche QUE la navigation et délègue aux modules :
# - reservations_view.py : vue_reservations / vue_ajouter / vue_modifier
# - calendar_view.py     : vue_calendrier
# - rapport_view.py      : vue_rapport
# - clients_view.py      : vue_clients
# - sms_view.py          : vue_sms
# - plateformes_view.py  : vue_plateformes  (nouvel onglet demandé)
# - io_utils.py          : Excel I/O (charger/sauvegarder/restaurer…)
# - palette_utils.py     : gestion palette (utilisée par calendrier & plateformes)
#
# NOTE : si ton fichier s'appelle "palette_utis.py" (sans 'l'),
# le code gère automatiquement ce fallback.

import streamlit as st

# ---------- Imports utilitaires (Excel, cache, etc.) ----------
from io_utils import (
    charger_donnees,
    bouton_telecharger,
    bouton_restaurer,
    render_cache_section_sidebar,
)

# ---------- Vues cœur (réservations / ajout / modifs) ----------
from reservations_view import (
    vue_reservations,
    vue_ajouter,
    vue_modifier,
)

# ---------- Vues secondaires (rapport, clients, SMS) ----------
from rapport_view import vue_rapport
from clients_view import vue_clients
from sms_view import vue_sms

# ---------- Calendrier (cases colorées + noms clients) ----------
from calendar_view import vue_calendrier

# ---------- Plateformes (onglet dédié CRUD) ----------
try:
    # nom correct
    from plateformes_view import vue_plateformes
except Exception:
    vue_plateformes = None  # si absent, on masquera l’onglet

# ---------- Palette (aperçu/éditeur rapide facultatif) ----------
try:
    # nom correct
    from palette_utils import render_palette_editor_sidebar
except Exception:
    # fallback si tu as un fichier mal orthographié "palette_utis.py"
    try:
        from palette_utis import render_palette_editor_sidebar  # type: ignore
    except Exception:
        render_palette_editor_sidebar = None  # on fera sans

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  SIDEBAR (Fichier & Maintenance) ==========
st.sidebar.title("📁 Fichier")
# On charge une fois pour activer le bouton de téléchargement (aperçu actuel)
_df_for_download = charger_donnees()
bouton_telecharger(_df_for_download)
bouton_restaurer()
render_cache_section_sidebar()

# (Facultatif) mini éditeur de palette dans la sidebar.
# Tu trouves ça envahissant ? Laisse commenté :
if render_palette_editor_sidebar is not None:
    with st.sidebar.expander("🎨 Aperçu palette (facultatif)"):
        render_palette_editor_sidebar()

# ==============================  NAVIGATION  ===============================
st.sidebar.title("🧭 Navigation")

# Construire la liste des onglets (on masque Plateformes si la vue n'est pas dispo)
onglets = [
    "📋 Réservations",
    "➕ Ajouter",
    "✏️ Modifier / Supprimer",
]
if vue_plateformes is not None:
    onglets.append("🎛️ Plateformes")  # << demandé
onglets += [
    "📅 Calendrier",
    "📊 Rapport",
    "👥 Liste clients",
    "✉️ SMS",
]

onglet = st.sidebar.radio("Aller à", onglets, index=0)

# ==============================  ROUTAGE  =================================
# On recharge le DataFrame propre avant chaque vue qui en a besoin
df = charger_donnees()

if onglet == "📋 Réservations":
    vue_reservations(df)

elif onglet == "➕ Ajouter":
    vue_ajouter(df)

elif onglet == "✏️ Modifier / Supprimer":
    vue_modifier(df)

elif onglet == "🎛️ Plateformes" and vue_plateformes is not None:
    # Vue dédiée pour ajouter / renommer / supprimer plateformes + couleurs (sauvegarde Excel)
    vue_plateformes()

elif onglet == "📅 Calendrier":
    # Grille mensuelle : cases colorées par plateforme + noms clients
    vue_calendrier(df)

elif onglet == "📊 Rapport":
    vue_rapport(df)

elif onglet == "👥 Liste clients":
    vue_clients(df)

elif onglet == "✉️ SMS":
    vue_sms(df)

# Fin