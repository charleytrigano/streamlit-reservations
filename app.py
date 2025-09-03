# app.py — Villa Tobias (COMPLET) - Version SQLite
# - Backend de base de données SQLite pour plus de robustesse et de performance.
# - Initialisation automatique de la base de données au premier lancement.
# - Fonctions de lecture/écriture adaptées (sqlite3 + pandas).
# - Sauvegarde/Restauration adaptées au fichier .db.

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
from urllib.parse import quote
import colorsys
import sqlite3 # Nouvelle importation !

DB_FILE = "reservations.db" # Remplacement de FICHIER = "reservations.xlsx"
# Les noms de feuilles ne sont plus nécessaires

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  SESSION KEYS  ==============================
if "uploader_key_restore" not in st.session_state:
    st.session_state.uploader_key_restore = 0
if "did_clear_cache" not in st.session_state:
    st.session_state.did_clear_cache = False

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

# ============================== DATABASE INITIALIZATION =============================
def init_db():
    """Crée les tables de la base de données si elles n'existent pas."""
    with sqlite3.connect(DB_FILE) as con:
        cur = con.cursor()
        # Création de la table des réservations
        cur.execute("""
            CREATE TABLE IF NOT EXISTS reservations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date_reservation TEXT,
                date_arrivee TEXT,
                date_depart TEXT,
                nb_nuits INTEGER,
                plateforme TEXT,
                nom_client TEXT,
                tel_client TEXT,
                nb_adultes INTEGER,
                nb_enfants INTEGER,
                prix_brut REAL,
                charges REAL,
                prix_net REAL,
                paye INTEGER,
                notes TEXT
            )
        """)
        # Création de la table des plateformes/couleurs
        cur.execute("""
            CREATE TABLE IF NOT EXISTS plateformes (
                nom TEXT PRIMARY KEY,
                couleur TEXT
            )
        """)
        # Vérifier si la table des plateformes est vide pour insérer les valeurs par défaut
        cur.execute("SELECT COUNT(*) FROM plateformes")
        if cur.fetchone()[0] == 0:
            cur.executemany("INSERT INTO plateformes (nom, couleur) VALUES (?, ?)", DEFAULT_PALETTE.items())
        con.commit()

# ==============================  CORE DATA FUNCTIONS (SQLite Version) ==============================
@st.cache_data
def charger_donnees():
    """Charge les réservations et la palette depuis la base de données SQLite."""
    if not os.path.exists(DB_FILE):
        return pd.DataFrame(), DEFAULT_PALETTE

    with sqlite3.connect(DB_FILE) as con:
        # Charger les réservations
        df = pd.read_sql_query("SELECT * FROM reservations", con)
        
       # Charger la palette
df_palette = pd.read_sql_query("SELECT * FROM plateformes", con)

# S'assurer que la colonne 'nom' existe (gestion de l'ancien format)
if 'nom' not in df_palette.columns and 'plateforme' in df_palette.columns:
    df_palette.rename(columns={'plateforme': 'nom'}, inplace=True)

# Vérifier que les colonnes requises existent avant de créer le dictionnaire
if 'nom' in df_palette.columns and 'couleur' in df_palette.columns:
    palette = dict(zip(df_palette['nom'], df_palette['couleur']))
else:
    # Utiliser la palette par défaut si la table est vide ou mal formée
    palette = DEFAULT_PALETTE.copy()

    # Conversion des types de données
    for col in ["date_reservation", "date_arrivee", "date_depart"]:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce').dt.date
    if 'paye' in df.columns:
        df['paye'] = df['paye'].astype(bool)

   # Fichier app.py

def charger_donnees():
    # ... code pour charger les données ...

    # Assurez-vous que les lignes suivantes sont bien à l'intérieur de la fonction
    df = ensure_schema(df)
    return df, palette

def sauvegarder_donnees(df_reservations, palette_dict):
    """Sauvegarde le DataFrame des réservations et la palette dans la BDD SQLite."""
    with sqlite3.connect(DB_FILE) as con:
        # Sauvegarder les réservations en remplaçant la table existante
        # C'est la méthode la plus simple pour garantir la cohérence
        df_reservations_db = df_reservations.copy()
        # Convertir les booléens en 0/1 pour SQLite
        if 'paye' in df_reservations_db.columns:
            df_reservations_db['paye'] = df_reservations_db['paye'].astype(int)
        
        # Supprimer la colonne 'id' si elle existe pour éviter les conflits
        if 'id' in df_reservations_db.columns:
             df_reservations_db = df_reservations_db.drop(columns=['id'])

        df_reservations_db.to_sql('reservations', con, if_exists='replace', index=False, index_label='id')

        # Sauvegarder la palette avec une logique d'UPSERT (INSERT OR REPLACE)
        cur = con.cursor()
        cur.executemany("INSERT OR REPLACE INTO plateformes (nom, couleur) VALUES (?, ?)", palette_dict.items())
        con.commit()


# Le reste du code est quasi identique, seules les fonctions ci-dessus changent drastiquement
# ... (toutes les fonctions `ensure_schema`, `get_palette`, `vue_...`, etc., restent les mêmes)


# ==============================  SCHEMA & DATA VALIDATION  ==============================
BASE_COLS = ["date_reservation", "date_arrivee", "date_depart", "nb_nuits", "plateforme", "nom_client", "tel_client", "nb_adultes", "nb_enfants", "prix_brut", "charges", "prix_net", "paye", "notes"]

def ensure_schema(df):
    """Assure que le DataFrame a toutes les colonnes nécessaires et les bons types."""
    df_res = df.copy()
    for col in BASE_COLS:
        if col not in df_res.columns:
            if "date" in col:
                df_res[col] = pd.NaT
            elif col in ["prix_brut", "charges", "prix_net", "nb_nuits", "nb_adultes", "nb_enfants"]:
                df_res[col] = 0
            elif col == "paye":
                df_res[col] = False
            else:
                df_res[col] = ""

    # Conversion des types
    for col in ["date_reservation", "date_arrivee", "date_depart"]:
        df_res[col] = pd.to_datetime(df_res[col], errors='coerce').dt.date
    df_res["paye"] = df_res["paye"].astype(bool)
    
    # Calculs dérivés
    df_res["nb_nuits"] = (pd.to_datetime(df_res["date_depart"]) - pd.to_datetime(df_res["date_arrivee"])).dt.days
    df_res["prix_net"] = df_res["prix_brut"] - df_res["charges"]
    with np.errstate(divide='ignore', invalid='ignore'):
        df_res["%"] = np.where(df_res["prix_brut"] != 0, (df_res["charges"] / df_res["prix_brut"] * 100), 0)
    
    # Nettoyage
    df_res = df_res.fillna({
        'prix_brut': 0, 'charges': 0, 'prix_net': 0, '%': 0,
        'nb_adultes': 0, 'nb_enfants': 0, 'nb_nuits': 0,
        'nom_client': '', 'tel_client': '', 'plateforme': 'Autre', 'notes': ''
    })
    
    return df_res[BASE_COLS + ["%"]]


# ==============================  PALETTE HELPERS ==============================
def get_palette():
    if 'palette' in st.session_state:
        return st.session_state.palette
    _, pal = charger_donnees()
    st.session_state.palette = pal
    return pal

def hex_to_rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

def is_dark_color(hex_color):
    rgb = hex_to_rgb(hex_color)
    # Formule de luminosité (YIQ)
    luminance = (rgb[0] * 299 + rgb[1] * 587 + rgb[2] * 114) / 1000
    return luminance < 128

# ==============================  UTILITIES  ==============================
def to_date_only(dt):
    if isinstance(dt, datetime):
        return dt.date()
    return dt

def normalize_tel(tel):
    if not isinstance(tel, str): return ""
    return "".join(filter(str.isdigit, tel))

def ics_escape(text):
    if text is None: return ""
    return str(text).replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')

def generate_ics(row):
    start_time = datetime.combine(row['date_arrivee'], datetime.min.time()).astimezone(timezone.utc)
    end_time = datetime.combine(row['date_depart'], datetime.min.time()).astimezone(timezone.utc)
    
    uid_base = f"{start_time.strftime('%Y%m%d')}-{end_time.strftime('%Y%m%d')}-{row['nom_client']}"
    uid = hashlib.sha1(uid_base.encode()).hexdigest() + "@villatobias"

    return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Streamlit//VillaTobias//FR
BEGIN:VEVENT
UID:{uid}
DTSTAMP:{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}
DTSTART;VALUE=DATE:{start_time.strftime('%Y%m%d')}
DTEND;VALUE=DATE:{end_time.strftime('%Y%m%d')}
SUMMARY:Réservation {ics_escape(row['nom_client'])}
DESCRIPTION:Nb Adultes: {row['nb_adultes']}\\nNb Enfants: {row['nb_enfants']}\\nPlateforme: {ics_escape(row['plateforme'])}
END:VEVENT
END:VCALENDAR"""

# ==============================  BACKUP & RESTORE (SQLite Version)  ==============================
def bouton_telecharger():
    if os.path.exists(DB_FILE):
        with open(DB_FILE, "rb") as fp:
            st.sidebar.download_button(
                label="📥 Télécharger la sauvegarde (.db)",
                data=fp,
                file_name="backup_reservations.db",
                mime="application/x-sqlite3"
            )

def bouton_restaurer():
    uploaded_file = st.sidebar.file_uploader(
        "📤 Restaurer une sauvegarde (.db)",
        type=['db'],
        key=f"uploader_key_restore_{st.session_state.uploader_key_restore}"
    )
    if uploaded_file is not None:
        if st.sidebar.button("⚠️ Confirmer la restauration"):
            try:
                with open(DB_FILE, "wb") as f:
                    f.write(uploaded_file.getvalue())
                st.cache_data.clear()
                st.session_state.uploader_key_restore += 1
                st.sidebar.success("✅ Restauration réussie ! L'application va se recharger.")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur lors de la restauration: {e}")

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation pour le moment. Ajoutez-en une via l'onglet '➕ Ajouter'.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False)
    
    # Calcul des totaux
    df_core = df_sorted[BASE_COLS + ["%"]]
    total_row = pd.DataFrame({
        'nom_client': ['-- TOTAL --'],
        'prix_brut': [df_core['prix_brut'].sum()],
        'charges': [df_core['charges'].sum()],
        'prix_net': [df_core['prix_net'].sum()]
    })
    
    show_tot = pd.concat([total_row, df_core], ignore_index=True)
    
    # Colonnes à afficher
    cols_to_show = ["paye", "nom_client", "date_arrivee", "date_depart", "nb_nuits", "plateforme", "prix_brut", "charges", "prix_net", "%"]
    
    # Configuration des colonnes pour le data_editor
    config = {
        "paye": st.column_config.CheckboxColumn("Payé", width="small"),
        "nom_client": st.column_config.TextColumn("Client", width="medium"),
        "date_arrivee": st.column_config.DateColumn("Arrivée", format="DD/MM/YYYY"),
        "date_depart": st.column_config.DateColumn("Départ", format="DD/MM/YYYY"),
        "nb_nuits": st.column_config.NumberColumn("Nuits", width="small"),
        "plateforme": st.column_config.TextColumn("Plateforme"),
        "prix_brut": st.column_config.NumberColumn("Brut (€)", format="%.2f €"),
        "charges": st.column_config.NumberColumn("Charges (€)", format="%.2f €"),
        "prix_net": st.column_config.NumberColumn("Net (€)", format="%.2f €"),
        "%": st.column_config.NumberColumn("Charges (%)", format="%.1f%%", width="small"),
    }

    edited_df = st.data_editor(
        show_tot[cols_to_show],
        key="editor_reservations",
        hide_index=True,
        column_config=config,
        disabled=True # Affichage seul
    )

def vue_ajouter(df):
    st.header("➕ Ajouter une Réservation")
    palette = get_palette()
    
    with st.form("form_ajout", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        with c1:
            nom_client = st.text_input("**Nom du Client**", placeholder="ex: Jean Dupont")
            date_arrivee = st.date_input("**Date d'arrivée**", value=date.today())
            nb_adultes = st.number_input("Nb Adultes", min_value=1, value=2, step=1)
            prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, step=10.0, format="%.2f")
        with c2:
            tel_client = st.text_input("Téléphone", placeholder="ex: 0612345678")
            date_depart = st.date_input("**Date de départ**", value=date.today() + timedelta(days=7))
            nb_enfants = st.number_input("Nb Enfants", min_value=0, value=0, step=1)
            charges = st.number_input("Charges (€) (commission, ménage...)", min_value=0.0, step=5.0, format="%.2f")
        with c3:
            plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()))
            date_reservation = st.date_input("Date de réservation", value=date.today())
            paye = st.checkbox("La réservation est payée", value=False)
        
        notes = st.text_area("Notes", placeholder="Code d'accès, heure d'arrivée, demandes spéciales...")

        submitted = st.form_submit_button("✅ Ajouter la réservation")

        if submitted:
            if not nom_client or not date_arrivee or not date_depart:
                st.error("❌ Veuillez remplir au moins le nom du client et les dates.")
            elif date_depart <= date_arrivee:
                st.error("❌ La date de départ doit être après la date d'arrivée.")
            else:
                nouvelle_ligne = {
                    "date_reservation": date_reservation, "date_arrivee": date_arrivee, "date_depart": date_depart,
                    "plateforme": plateforme, "nom_client": nom_client, "tel_client": normalize_tel(tel_client),
                    "nb_adultes": nb_adultes, "nb_enfants": nb_enfants, "prix_brut": prix_brut, "charges": charges,
                    "paye": paye, "notes": notes, "nb_nuits": 0, "prix_net": 0, "%": 0 # Valeurs calculées
                }
                
                df_a_jour = pd.concat([df, pd.DataFrame([nouvelle_ligne])], ignore_index=True)
                df_a_jour = ensure_schema(df_a_jour) # Recalculer les champs dérivés
                
                sauvegarder_donnees(df_a_jour, get_palette())
                st.cache_data.clear()
                st.success(f"✅ Réservation pour **{nom_client}** ajoutée !")
                st.rerun()

def vue_modifier(df):
    st.header("✏️ Modifier / Supprimer une Réservation")
    if df.empty:
        st.warning("Aucune réservation à modifier.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index(drop=True)
    
    options_resa = [f"{idx}: {row['nom_client']} | {row['date_arrivee'].strftime('%d/%m/%Y')}" for idx, row in df_sorted.iterrows()]
    
    selection = st.selectbox("Sélectionnez une réservation à modifier", options=options_resa, index=None, placeholder="Choisissez une réservation...")
    
    if selection:
        idx_selection = int(selection.split(":")[0])
        resa_selectionnee = df_sorted.loc[idx_selection].copy()
        
        with st.form("form_modif"):
            palette = get_palette()
            c1, c2, c3 = st.columns(3)
            with c1:
                nom_client = st.text_input("**Nom du Client**", value=resa_selectionnee['nom_client'])
                date_arrivee = st.date_input("**Date d'arrivée**", value=to_date_only(resa_selectionnee['date_arrivee']))
                nb_adultes = st.number_input("Nb Adultes", min_value=0, value=int(resa_selectionnee['nb_adultes']), step=1)
                prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, value=float(resa_selectionnee['prix_brut']), step=10.0, format="%.2f")
            with c2:
                tel_client = st.text_input("Téléphone", value=resa_selectionnee['tel_client'])
                date_depart = st.date_input("**Date de départ**", value=to_date_only(resa_selectionnee['date_depart']))
                nb_enfants = st.number_input("Nb Enfants", min_value=0, value=int(resa_selectionnee['nb_enfants']), step=1)
                charges = st.number_input("Charges (€)", min_value=0.0, value=float(resa_selectionnee['charges']), step=5.0, format="%.2f")
            with c3:
                plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()), index=list(palette.keys()).index(resa_selectionnee['plateforme']) if resa_selectionnee['plateforme'] in palette else 0)
                date_reservation = st.date_input("Date de réservation", value=to_date_only(resa_selectionnee['date_reservation']))
                paye = st.checkbox("La réservation est payée", value=bool(resa_selectionnee['paye']))
            
            notes = st.text_area("Notes", value=resa_selectionnee['notes'])

            btn_enregistrer, btn_supprimer = st.columns([.8, .2])
            
            if btn_enregistrer.form_submit_button("💾 Enregistrer les modifications"):
                if date_depart <= date_arrivee:
                    st.error("❌ La date de départ doit être après la date d'arrivée.")
                else:
                    df_sorted.loc[idx_selection, 'nom_client'] = nom_client
                    df_sorted.loc[idx_selection, 'date_arrivee'] = date_arrivee
                    df_sorted.loc[idx_selection, 'date_depart'] = date_depart
                    df_sorted.loc[idx_selection, 'tel_client'] = normalize_tel(tel_client)
                    df_sorted.loc[idx_selection, 'nb_adultes'] = nb_adultes
                    df_sorted.loc[idx_selection, 'nb_enfants'] = nb_enfants
                    df_sorted.loc[idx_selection, 'prix_brut'] = prix_brut
                    df_sorted.loc[idx_selection, 'charges'] = charges
                    df_sorted.loc[idx_selection, 'plateforme'] = plateforme
                    df_sorted.loc[idx_selection, 'date_reservation'] = date_reservation
                    df_sorted.loc[idx_selection, 'paye'] = paye
                    df_sorted.loc[idx_selection, 'notes'] = notes
                    
                    df_final = ensure_schema(df_sorted)
                    sauvegarder_donnees(df_final, palette)
                    st.cache_data.clear()
                    st.success("✅ Modifications enregistrées !")
                    st.rerun()

            if btn_supprimer.form_submit_button("❌ Supprimer"):
                df_sorted = df_sorted.drop(index=idx_selection)
                sauvegarder_donnees(df_sorted, palette)
                st.cache_data.clear()
                st.warning("🗑️ Réservation supprimée.")
                st.rerun()

def vue_calendrier(df):
    st.header("📅 Calendrier des Réservations")
    palette = get_palette()

    # Sélecteur de mois/année
    today = date.today()
    c1, c2 = st.columns(2)
    selected_month = c1.selectbox("Mois", options=range(1, 13), format_func=lambda m: calendar.month_name[m], index=today.month - 1)
    selected_year = c2.selectbox("Année", options=range(today.year - 2, today.year + 3), index=2)

    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(selected_year, selected_month)

    # Préparer les données
    df_filtered = df[(df['date_arrivee'] <= date(selected_year, selected_month, calendar.monthrange(selected_year, selected_month)[1])) & 
                     (df['date_depart'] > date(selected_year, selected_month, 1))].copy()

    # Style CSS pour le calendrier
    st.markdown("""
    <style>
        .calendar-day { border: 1px solid #444; min-height: 120px; padding: 5px; }
        .calendar-day.outside-month { background-color: #222; }
        .calendar-date { font-weight: bold; font-size: 1.1em; margin-bottom: 5px; }
        .reservation-bar { 
            padding: 3px 6px; 
            margin-bottom: 3px; 
            border-radius: 5px; 
            font-size: 0.9em; 
            overflow: hidden;
            white-space: nowrap;
            text-overflow: ellipsis;
        }
    </style>
    """, unsafe_allow_html=True)
    
    header_cols = st.columns(7)
    for i, day_name in enumerate(["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]):
        header_cols[i].markdown(f"**{day_name}**")
        
    for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                day_class = "outside-month" if day.month != selected_month else ""
                day_html = f"<div class='calendar-day {day_class}'><div class='calendar-date'>{day.day}</div>"
                
                # Itérer sur les réservations qui couvrent ce jour
                for _, resa in df_filtered.iterrows():
                    if resa['date_arrivee'] <= day < resa['date_depart']:
                        color = palette.get(resa['plateforme'], '#888888')
                        text_color = "#FFFFFF" if is_dark_color(color) else "#000000"
                        day_html += f"<div class='reservation-bar' style='background-color:{color}; color:{text_color};' title='{resa['nom_client']} - {resa['plateforme']}'>{resa['nom_client']}</div>"
                
                day_html += "</div>"
                st.markdown(day_html, unsafe_allow_html=True)

def vue_rapport(df):
    st.header("📊 Rapport de Performance")
    if df.empty:
        st.info("Aucune donnée à analyser.")
        return
        
    # Filtres
    years = sorted(df['date_arrivee'].dt.year.unique(), reverse=True)
    selected_year = st.selectbox("Sélectionner une année", options=years, index=0)
    
    df_year = df[df['date_arrivee'].dt.year == selected_year]
    
    # KPIs
    kpi1, kpi2, kpi3, kpi4 = st.columns(4)
    total_brut = df_year['prix_brut'].sum()
    total_net = df_year['prix_net'].sum()
    nb_resa = len(df_year)
    nb_nuits = df_year['nb_nuits'].sum()

    kpi1.metric("Chiffre d'Affaires Brut", f"{total_brut:,.2f} €")
    kpi2.metric("Revenu Net", f"{total_net:,.2f} €")
    kpi3.metric("Nombre de Réservations", nb_resa)
    kpi4.metric("Nuits Réservées", nb_nuits)
    
    st.markdown("---")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("CA Brut par Mois")
        ca_mois = df_year.groupby(df_year['date_arrivee'].dt.month)['prix_brut'].sum()
        ca_mois = ca_mois.reindex(range(1, 13), fill_value=0)
        ca_mois.index = [calendar.month_abbr[i] for i in ca_mois.index]
        st.bar_chart(ca_mois)
        
    with c2:
        st.subheader("Répartition par Plateforme")
        platform_dist = df_year['plateforme'].value_counts()
        st.bar_chart(platform_dist)

def vue_liste_clients(df):
    st.header("👥 Liste des Clients")
    if df.empty:
        st.info("Aucun client enregistré.")
        return

    clients = df.drop_duplicates(subset=['nom_client', 'tel_client']).sort_values('nom_client')
    st.dataframe(clients[['nom_client', 'tel_client']], use_container_width=True, hide_index=True)

def vue_export_ics(df):
    st.header("📤 Export ICS (iCalendar)")
    st.info("Téléchargez un fichier .ics pour une réservation spécifique, compatible avec la plupart des agendas (Google Calendar, Outlook, etc.).")
    
    if df.empty:
        st.warning("Aucune réservation à exporter.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index(drop=True)
    options_resa = [f"{idx}: {row['nom_client']} | {row['date_arrivee'].strftime('%d/%m/%Y')}" for idx, row in df_sorted.iterrows()]
    selection = st.selectbox("Sélectionnez une réservation", options=options_resa, index=None)

    if selection:
        idx = int(selection.split(":")[0])
        resa = df_sorted.loc[idx]
        ics_content = generate_ics(resa)
        st.download_button(
            label="📥 Télécharger le fichier .ics",
            data=ics_content,
            file_name=f"reservation_{resa['nom_client']}.ics",
            mime="text/calendar"
        )

def vue_sms(df):
    st.header("✉️ Générateur de SMS")
    st.info("Générez un lien pour envoyer un SMS pré-rempli au client.")

    if df.empty:
        st.warning("Aucune réservation pour envoyer un SMS.")
        return

    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index(drop=True)
    options_resa = [f"{idx}: {row['nom_client']} | {row['date_arrivee'].strftime('%d/%m/%Y')}" for idx, row in df_sorted.iterrows()]
    selection = st.selectbox("Sélectionnez un client", options=options_resa, index=None)

    if selection:
        idx = int(selection.split(":")[0])
        resa = df_sorted.loc[idx]
        
        if resa['tel_client']:
            message_template = f"Bonjour {resa['nom_client']}, bienvenue à la Villa Tobias ! Votre arrivée est prévue le {resa['date_arrivee'].strftime('%d/%m/%Y')}. Voici quelques informations utiles : ..."
            message_body = st.text_area("Message à envoyer", value=message_template, height=150)
            
            encoded_message = quote(message_body)
            sms_link = f"sms:{resa['tel_client']}?body={encoded_message}"
            
            st.markdown(f"[📲 **Cliquez ici pour ouvrir l'application SMS**]({sms_link})")
        else:
            st.error("Ce client n'a pas de numéro de téléphone enregistré.")

def vue_plateformes(df):
    st.header("🎨 Gestion des Plateformes")
    palette = get_palette().copy()

    for p, c in palette.items():
        cols = st.columns([0.4, 0.4, 0.2])
        new_color = cols[0].color_picker(f"Couleur pour **{p}**", value=c)
        if new_color != c:
            palette[p] = new_color
        
        if cols[2].button(f"🗑️", key=f"del_{p}"):
            del palette[p]
            st.rerun()

    st.markdown("---")
    st.subheader("Ajouter une nouvelle plateforme")
    with st.form("new_platform_form", clear_on_submit=True):
        new_name = st.text_input("Nom de la nouvelle plateforme")
        submitted = st.form_submit_button("Ajouter")
        if submitted and new_name:
            if new_name not in palette:
                palette[new_name] = "#ffffff"
            else:
                st.warning(f"La plateforme '{new_name}' existe déjà.")
    
    if st.button("💾 Enregistrer les changements de couleurs"):
        sauvegarder_donnees(df, palette) # Sauvegarde le df original et la nouvelle palette
        st.session_state.palette = palette
        st.cache_data.clear()
        st.success("Palette de couleurs mise à jour !")
        st.rerun()


# ==============================  MAIN APP  ==============================
def main():
    # Initialise la base de données au premier lancement
    init_db()

    st.title("📖 Gestion des Réservations - Villa Tobias")
    
    st.sidebar.markdown("## ⚙️ Administration")
    bouton_telecharger()
    bouton_restaurer()

    st.sidebar.markdown("---")
    st.sidebar.markdown("## 🧰 Maintenance")
    if st.sidebar.button("♻️ Vider le cache"):
        st.cache_data.clear()
        st.sidebar.success("Cache vidé.")
        st.rerun()

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
         "📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS","🎨 Plateformes"]
    )

    df, _ = charger_donnees()

    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "➕ Ajouter":
        vue_ajouter(df)
    elif onglet == "✏️ Modifier / Supprimer":
        vue_modifier(df)
    elif onglet == "📅 Calendrier":
        vue_calendrier(df)
    elif onglet == "📊 Rapport":
        vue_rapport(df)
    elif onglet == "👥 Liste clients":
        vue_liste_clients(df)
    elif onglet == "📤 Export ICS":
        vue_export_ics(df)
    elif onglet == "✉️ SMS":
        vue_sms(df)
    elif onglet == "🎨 Plateformes":
        vue_plateformes(df)

if __name__ == "__main__":
    main()
