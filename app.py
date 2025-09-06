# app.py — Villa Tobias (COMPLET) - Checkboxes éditables pour SMS

import streamlit as st
import pandas as pd
import numpy as np
import os
import calendar
from datetime import date, timedelta
from urllib.parse import quote

# --- Configuration des Fichiers ---
CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv" 

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================
DEFAULT_PALETTE = { "Booking": "#1e90ff", "Airbnb":  "#e74c3c", "Autre": "#f59e0b" }

# ============================== CORE DATA FUNCTIONS ==============================
@st.cache_data
def charger_donnees_csv():
    """Charge et nettoie les données directement depuis les fichiers CSV."""
    df = pd.DataFrame()
    palette = DEFAULT_PALETTE.copy()

    try:
        df = pd.read_csv(CSV_RESERVATIONS, delimiter=';')
        df.columns = df.columns.str.strip()
    except FileNotFoundError:
        st.warning(f"Fichier '{CSV_RESERVATIONS}' introuvable.")
    except Exception as e:
        st.error(f"Erreur de lecture de {CSV_RESERVATIONS}: {e}")

    try:
        df_palette = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        palette = dict(zip(df_palette['plateforme'], df_palette['couleur']))
    except:
        pass

    df = ensure_schema(df)
    return df, palette

def sauvegarder_donnees_csv(df, file_path=CSV_RESERVATIONS):
    """Sauvegarde le DataFrame dans le fichier CSV spécifié."""
    try:
        df_to_save = df.copy()
        # Garder uniquement les colonnes du schéma
        colonnes_a_sauvegarder = [col for col in BASE_COLS if col in df_to_save.columns]
        df_to_save = df_to_save[colonnes_a_sauvegarder]

        for col in ['date_arrivee', 'date_depart']:
            if col in df_to_save.columns:
                df_to_save[col] = pd.to_datetime(df_to_save[col]).dt.strftime('%d/%m/%Y')

        df_to_save.to_csv(file_path, sep=';', index=False)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"Erreur de sauvegarde : {e}")
        return False

# ==============================  SCHEMA & DATA VALIDATION  ==============================
BASE_COLS = [
    'paye', 'nom_client', 'sms_envoye', 'plateforme', 'telephone', 'date_arrivee',
    'date_depart', 'nuitees', 'prix_brut', 'commissions', 'frais_cb',
    'prix_net', 'menage', 'taxes_sejour', 'base', 'charges', '%',
    'AAAA', 'MM', 'ical_uid'
]

def ensure_schema(df):
    if df.empty:
        out = pd.DataFrame(columns=BASE_COLS)
        # valeurs par défaut booleans
        out['paye'] = out.get('paye', False)
        out['sms_envoye'] = out.get('sms_envoye', False)
        return out

    df_res = df.copy()
    rename_map = {
        'Payé': 'paye', 'Client': 'nom_client', 'Plateforme': 'plateforme',
        'Arrivée': 'date_arrivee', 'Départ': 'date_depart', 'Nuits': 'nuitees',
        'Brut (€)': 'prix_brut'
    }
    df_res.rename(columns=rename_map, inplace=True)

    for col in BASE_COLS:
        if col not in df_res.columns:
            df_res[col] = None

    # Dates
    for col in ["date_arrivee", "date_depart"]:
        df_res[col] = pd.to_datetime(df_res[col], dayfirst=True, errors='coerce')

    mask_dates = pd.notna(df_res["date_arrivee"]) & pd.notna(df_res["date_depart"])
    df_res.loc[mask_dates, "nuitees"] = (df_res.loc[mask_dates, "date_depart"] - df_res.loc[mask_dates, "date_arrivee"]).dt.days

    for col in ["date_arrivee", "date_depart"]:
        df_res[col] = df_res[col].dt.date

    # Booléens
    if df_res['paye'].dtype == 'object':
        df_res['paye'] = df_res['paye'].astype(str).str.strip().str.upper().isin(['VRAI','TRUE','OUI','1'])
    df_res['paye'] = df_res['paye'].fillna(False).astype(bool)

    if df_res['sms_envoye'].dtype == 'object':
        df_res['sms_envoye'] = df_res['sms_envoye'].astype(str).str.strip().str.upper().isin(['VRAI','TRUE','OUI','1'])
    df_res['sms_envoye'] = df_res['sms_envoye'].fillna(False).astype(bool)

    # Numériques
    numeric_cols = ['prix_brut','commissions','frais_cb','menage','taxes_sejour']
    for col in numeric_cols:
        if df_res[col].dtype == 'object':
            df_res[col] = (df_res[col].astype(str)
                           .str.replace('€','',regex=False)
                           .str.replace(',','.',regex=False)
                           .str.replace(' ','',regex=False)
                           .str.strip())
        df_res[col] = pd.to_numeric(df_res[col], errors='coerce').fillna(0)

    # Calculs
    df_res['prix_net'] = df_res['prix_brut'].fillna(0) - df_res['commissions'].fillna(0) - df_res['frais_cb'].fillna(0)
    df_res['charges'] = df_res['prix_brut'].fillna(0) - df_res['prix_net'].fillna(0)
    df_res['base'] = df_res['prix_net'].fillna(0) - df_res['menage'].fillna(0) - df_res['taxes_sejour'].fillna(0)

    with np.errstate(divide='ignore', invalid='ignore'):
        df_res['%'] = np.where(df_res['prix_brut'] > 0, (df_res['charges'] / df_res['prix_brut'] * 100), 0)

    # AAAA/MM
    date_arrivee_dt = pd.to_datetime(df_res["date_arrivee"], errors='coerce')
    df_res.loc[pd.notna(date_arrivee_dt), 'AAAA'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.year
    df_res.loc[pd.notna(date_arrivee_dt), 'MM'] = date_arrivee_dt[pd.notna(date_arrivee_dt)].dt.month

    return df_res

# ============================== UTILITIES & HELPERS ==============================
def is_dark_color(hex_color):
    try:
        hex_color = hex_color.lstrip('#')
        rgb = tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
        luminance = (0.299*rgb[0] + 0.587*rgb[1] + 0.114*rgb[2]) / 255
        return luminance < 0.5
    except (ValueError, TypeError):
        return True

def kpi_chips(df, title="Indicateurs Clés"):
    st.subheader(title)
    if df.empty:
        st.warning("Pas de données à afficher pour cette sélection.")
        return
    totals = {
        "Total Brut": df["prix_brut"].sum(),
        "Total Net": df["prix_net"].sum(),
        "Total Commissions": df["commissions"].sum(),
        "Total Frais CB": df["frais_cb"].sum(),
        "Total Ménage": df["menage"].sum(),
        "Total Base": df["base"].sum(),
        "Nuitées": df["nuitees"].sum(),
    }
    html = f"""
    <style>
        .chips-container {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:20px; }}
        .chip {{ background-color:#333; padding:8px 12px; border-radius:16px; font-size:.9rem; text-align:center; }}
        .chip-label {{ display:block; font-size:.8rem; color:#aaa; margin-bottom:4px; }}
        .chip-value {{ font-weight:bold; color:#eee; }}
    </style>
    <div class="chips-container">
        {"".join([f'<div class="chip"><span class="chip-label">{label}</span><span class="chip-value">{value:,.2f} €</span></div>'
                   if "Nuitées" not in label else f'<div class="chip"><span class="chip-label">{label}</span><span class="chip-value">{int(value)}</span></div>'
                   for label, value in totals.items()])}
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# ==============================  VIEWS (ONGLETS) ==============================
def vue_reservations(df):
    st.header("📋 Liste des Réservations")
    if df.empty:
        st.info("Aucune réservation trouvée.")
        return

    df_dates_valides = df.dropna(subset=['AAAA', 'MM'])

    c1, c2, c3 = st.columns(3)
    annees = ["Toutes"] + sorted(df_dates_valides['AAAA'].astype(int).unique(), reverse=True)
    annee_selectionnee = c1.selectbox("Filtrer par Année", annees)
    mois_options = ["Tous"] + list(range(1, 13))
    mois_selectionne = c2.selectbox("Filtrer par Mois", mois_options)
    plateformes_options = ["Toutes"] + sorted(df_dates_valides['plateforme'].dropna().unique())
    plateforme_selectionnee = c3.selectbox("Filtrer par Plateforme", plateformes_options)

    data_filtree = df_dates_valides.copy()
    if annee_selectionnee != "Toutes":
        data_filtree = data_filtree[data_filtree['AAAA'] == annee_selectionnee]
    if mois_selectionne != "Tous":
        data_filtree = data_filtree[data_filtree['MM'] == mois_selectionne]
    if plateforme_selectionnee != "Toutes":
        data_filtree = data_filtree[data_filtree['plateforme'] == plateforme_selectionnee]

    kpi_chips(data_filtree, title="Totaux pour la Sélection")
    st.markdown("---")

    # Garder l'index d'origine pour savoir quelle ligne sauvegarder
    df_sorted = data_filtree.sort_values(by="date_arrivee", ascending=False, na_position='last').copy()
    df_sorted["_rowid"] = df_sorted.index  # identifiant caché

    # Éditeur avec cases à cocher
    column_config = {
        "paye": st.column_config.CheckboxColumn("Payé"),
        "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
        "nuitees": st.column_config.NumberColumn("Nuits", format="%d"),
        "prix_brut": st.column_config.NumberColumn("Prix Brut", format="%.2f €"),
        "commissions": st.column_config.NumberColumn("Commissions", format="%.2f €"),
        "prix_net": st.column_config.NumberColumn("Prix Net", format="%.2f €"),
        "base": st.column_config.NumberColumn("Base", format="%.2f €"),
        "charges": st.column_config.NumberColumn("Charges", format="%.2f €"),
        "%": st.column_config.NumberColumn("% Charges", format="%.2f %%"),
        "AAAA": st.column_config.NumberColumn("Année", format="%d"),
        "MM": st.column_config.NumberColumn("Mois", format="%d"),
        "date_arrivee": st.column_config.DateColumn("Arrivée", format="DD/MM/YYYY"),
        "date_depart": st.column_config.DateColumn("Départ", format="DD/MM/YYYY"),
        "_rowid": st.column_config.TextColumn("_rowid", help="ID interne", disabled=True)
    }

    # On affiche l'éditeur (éditable) — on laisse toutes colonnes visibles,
    # mais on peut masquer _rowid via column_order si tu préfères.
    edited = st.data_editor(
        df_sorted,
        column_config=column_config,
        use_container_width=True,
        num_rows="fixed",
        hide_index=True,
        key="editor_reservations"
    )

    # Bouton de sauvegarde : on pousse seulement paye & sms_envoye vers le DF d'origine
    if st.button("💾 Enregistrer les modifications"):
        try:
            # S'assurer des types
            edited["paye"] = edited["paye"].fillna(False).astype(bool)
            edited["sms_envoye"] = edited["sms_envoye"].fillna(False).astype(bool)

            # Mise à jour ciblée via l'index d'origine
            for _, row in edited.iterrows():
                rid = row["_rowid"]
                if pd.isna(rid):  # sécurité
                    continue
                df.loc[rid, "paye"] = bool(row["paye"])
                df.loc[rid, "sms_envoye"] = bool(row["sms_envoye"])

            df_final = ensure_schema(df)
            if sauvegarder_donnees_csv(df_final):
                st.success("Statuts mis à jour et sauvegardés ✅")
                st.rerun()
        except Exception as e:
            st.error(f"Impossible de sauvegarder : {e}")

def vue_ajouter(df, palette):
    st.header("➕ Ajouter une Réservation")
    with st.form("form_ajout", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            nom_client = st.text_input("**Nom du Client**")
            telephone = st.text_input("Téléphone")
            date_arrivee = st.date_input("**Date d'arrivée**", date.today())
            date_depart = st.date_input("**Date de départ**", date.today() + timedelta(days=1))
        with c2:
            plateforme = st.selectbox("**Plateforme**", options=list(palette.keys()))
            prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, step=0.01, format="%.2f")
            commissions = st.number_input("Commissions (€)", min_value=0.0, step=0.01, format="%.2f")
            frais_cb = st.number_input("Frais CB (€)", min_value=0.0, step=0.01, format="%.2f")
            menage = st.number_input("Ménage (€)", min_value=0.0, step=0.01, format="%.2f")
            taxes_sejour = st.number_input("Taxes Séjour (€)", min_value=0.0, step=0.01, format="%.2f")
        paye = st.checkbox("Payé", False)
        submitted = st.form_submit_button("✅ Ajouter la réservation")
        if submitted:
            if not nom_client or date_depart <= date_arrivee:
                st.error("Veuillez entrer un nom et des dates valides.")
            else:
                nouvelle_ligne = pd.DataFrame([{
                    'nom_client': nom_client, 'telephone': telephone,
                    'date_arrivee': date_arrivee, 'date_depart': date_depart,
                    'plateforme': plateforme, 'prix_brut': prix_brut, 'commissions': commissions,
                    'frais_cb': frais_cb, 'menage': menage, 'taxes_sejour': taxes_sejour,
                    'paye': paye, 'sms_envoye': False
                }])
                df_a_jour = pd.concat([df, nouvelle_ligne], ignore_index=True)
                df_a_jour = ensure_schema(df_a_jour)
                if sauvegarder_donnees_csv(df_a_jour):
                    st.success(f"Réservation pour {nom_client} ajoutée.")
                    st.rerun()

def vue_modifier(df, palette):
    st.header("✏️ Modifier / Supprimer une Réservation")
    if df.empty:
        st.warning("Aucune réservation à modifier.")
        return
    df_sorted = df.sort_values(by="date_arrivee", ascending=False).reset_index()
    options_resa = [f"{idx}: {row['nom_client']} ({row['date_arrivee']})" for idx, row in df_sorted.iterrows() if pd.notna(row['date_arrivee'])]
    selection = st.selectbox("Sélectionnez une réservation", options=options_resa, index=None, placeholder="Choisissez une réservation...")
    if selection:
        idx_selection = int(selection.split(":")[0])
        original_index = df_sorted.loc[idx_selection, 'index']
        resa_selectionnee = df.loc[original_index].copy()
        with st.form(f"form_modif_{original_index}"):
            c1, c2 = st.columns(2)
            with c1:
                nom_client = st.text_input("**Nom du Client**", value=resa_selectionnee.get('nom_client', ''))
                telephone = st.text_input("Téléphone", value=resa_selectionnee.get('telephone', ''))
                date_arrivee = st.date_input("**Date d'arrivée**", value=resa_selectionnee.get('date_arrivee'))
                date_depart = st.date_input("**Date de départ**", value=resa_selectionnee.get('date_depart'))
            with c2:
                plateforme_options = list(palette.keys())
                current_plateforme = resa_selectionnee.get('plateforme')
                plateforme_index = plateforme_options.index(current_plateforme) if current_plateforme in plateforme_options else 0
                plateforme = st.selectbox("**Plateforme**", options=plateforme_options, index=plateforme_index)
                prix_brut = st.number_input("Prix Brut (€)", min_value=0.0, value=resa_selectionnee.get('prix_brut', 0.0), step=0.01, format="%.2f")
                commissions = st.number_input("Commissions (€)", min_value=0.0, value=resa_selectionnee.get('commissions', 0.0), step=0.01, format="%.2f")
                paye = st.checkbox("Payé", value=bool(resa_selectionnee.get('paye', False)))
            btn_enregistrer, btn_supprimer = st.columns([.8, .2])
            if btn_enregistrer.form_submit_button("💾 Enregistrer"):
                updates = {
                    'nom_client': nom_client, 'telephone': telephone,
                    'date_arrivee': date_arrivee, 'date_depart': date_depart,
                    'plateforme': plateforme, 'prix_brut': prix_brut,
                    'commissions': commissions, 'paye': paye
                }
                for key, value in updates.items():
                    df.loc[original_index, key] = value
                df_final = ensure_schema(df)
                if sauvegarder_donnees_csv(df_final):
                    st.success("Modifications enregistrées !")
                    st.rerun()
            if btn_supprimer.form_submit_button("🗑️ Supprimer"):
                df_final = df.drop(index=original_index)
                if sauvegarder_donnees_csv(df_final):
                    st.warning("Réservation supprimée.")
                    st.rerun()

def vue_plateformes(df, palette):
    st.header("🎨 Gestion des Plateformes")
    df_palette = pd.DataFrame(list(palette.items()), columns=['plateforme', 'couleur'])
    edited_df = st.data_editor(
        df_palette, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={ "plateforme": "Plateforme", "couleur": st.column_config.TextColumn("Couleur (code hex)") }
    )
    if st.button("💾 Enregistrer les modifications"):
        nouvelle_palette = dict(zip(edited_df['plateforme'], edited_df['couleur']))
        df_plateformes_save = pd.DataFrame(list(nouvelle_palette.items()), columns=['plateforme', 'couleur'])
        if sauvegarder_donnees_csv(df_plateformes_save, file_path=CSV_PLATEFORMES):
            st.success("Palette de couleurs mise à jour !")
            st.rerun()

def vue_calendrier(df, palette):
    st.header("📅 Calendrier des Réservations")
    df_dates_valides = df.dropna(subset=['date_arrivee', 'date_depart', 'AAAA'])
    if df_dates_valides.empty:
        st.info("Aucune réservation à afficher.")
        return
    c1, c2 = st.columns(2)
    today = date.today()
    noms_mois = [calendar.month_name[i] for i in range(1, 13)]
    selected_month_name = c1.selectbox("Mois", options=noms_mois, index=today.month - 1)
    selected_month = noms_mois.index(selected_month_name) + 1
    available_years = sorted(list(df_dates_valides['AAAA'].dropna().astype(int).unique()))
    if not available_years:
        available_years = [today.year]
    try:
        default_year_index = available_years.index(today.year)
    except ValueError:
        default_year_index = len(available_years) - 1
    selected_year = c2.selectbox("Année", options=available_years, index=default_year_index)
    cal = calendar.Calendar()
    month_days = cal.monthdatescalendar(selected_year, selected_month)
    st.markdown("""<style>.calendar-day{border:1px solid #444;min-height:120px;padding:5px;vertical-align:top}.calendar-day.outside-month{background-color:#2e2e2e}.calendar-date{font-weight:700;font-size:1.1em;margin-bottom:5px;text-align:right}.reservation-bar{padding:3px 6px;margin-bottom:3px;border-radius:5px;font-size:.9em;overflow:hidden;white-space:nowrap;text-overflow:ellipsis}</style>""", unsafe_allow_html=True)
    headers = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
    st.write(f'<div style="display:grid;grid-template-columns:repeat(7,1fr);text-align:center;font-weight:700">{"".join(f"<div>{h}</div>" for h in headers)}</div>', unsafe_allow_html=True)
    for week in month_days:
        cols = st.columns(7)
        for i, day in enumerate(week):
            with cols[i]:
                day_class = "outside-month" if day.month != selected_month else ""
                day_html = f"<div class='calendar-day {day_class}'><div class='calendar-date'>{day.day}</div>"
                for _, resa in df_dates_valides.iterrows():
                    if isinstance(resa['date_arrivee'], date) and isinstance(resa['date_depart'], date):
                        if resa['date_arrivee'] <= day < resa['date_depart']:
                            color = palette.get(resa['plateforme'], '#888')
                            text_color = "#FFF" if is_dark_color(color) else "#000"
                            day_html += f"<div class='reservation-bar' style='background-color:{color};color:{text_color}' title='{resa['nom_client']}'>{resa['nom_client']}</div>"
                day_html += "</div>"
                st.markdown(day_html, unsafe_allow_html=True)
    st.markdown("---")
    st.subheader("Détails des réservations du mois")
    start_of_month = date(selected_year, selected_month, 1)
    end_of_month = date(selected_year, selected_month, calendar.monthrange(selected_year, selected_month)[1])
    reservations_du_mois = df_dates_valides[(df_dates_valides['date_arrivee'] <= end_of_month) & (df_dates_valides['date_depart'] > start_of_month)].sort_values(by="date_arrivee").reset_index()
    if not reservations_du_mois.empty:
        options = {f"{row['nom_client']} ({row['date_arrivee'].strftime('%d/%m')})": idx for idx, row in reservations_du_mois.iterrows()}
        selection_str = st.selectbox("Voir les détails :", options=options.keys(), index=None, placeholder="Choisissez une réservation...")
        if selection_str:
            details = reservations_du_mois.loc[options[selection_str]]
            st.markdown(f"**Détails pour {details.get('nom_client')}**")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"""- **Téléphone :** {details.get('telephone', 'N/A')}
- **Arrivée :** {details.get('date_arrivee').strftime('%d/%m/%Y') if pd.notna(details.get('date_arrivee')) else 'N/A'}
- **Départ :** {details.get('date_depart').strftime('%d/%m/%Y') if pd.notna(details.get('date_depart')) else 'N/A'}
- **Nuits :** {details.get('nuitees', 0):.0f}""")
            with col2:
                st.markdown(f"""- **Prix Net :** {details.get('prix_net', 0):.2f} €
- **Prix Brut :** {details.get('prix_brut', 0):.2f} €
- **Statut :** {"Payé" if details.get('paye', False) else "Non Payé"}""")
    else:
        st.info("Aucune réservation pour ce mois.")

def vue_rapport(df, palette):
    st.header("📊 Rapport de Performance")
    df_dates_valides = df.dropna(subset=['AAAA', 'MM', 'plateforme'])
    if df_dates_valides.empty:
        st.info("Aucune donnée pour générer un rapport.")
        return
    c1, c2, c3 = st.columns(3)
    annees = sorted(df_dates_valides['AAAA'].astype(int).unique(), reverse=True)
    annee_selectionnee = c1.selectbox("Année", annees)
    mois_options = ["Tous"] + list(range(1, 13))
    mois_selectionne = c2.selectbox("Mois", mois_options)
    plateformes_options = ["Toutes"] + sorted(df_dates_valides['plateforme'].dropna().unique())
    plateforme_selectionnee = c3.selectbox("Plateforme", plateformes_options)
    data = df_dates_valides[df_dates_valides['AAAA'] == annee_selectionnee]
    if mois_selectionne != "Tous": data = data[data['MM'] == mois_selectionne]
    if plateforme_selectionnee != "Toutes": data = data[data['plateforme'] == plateforme_selectionnee]
    st.markdown("---")
    if data.empty:
        st.warning("Aucune donnée pour les filtres sélectionnés.")
        return
    kpi_chips(data)
    st.subheader("Revenus bruts par Plateforme")
    chart_data = data.groupby("plateforme")['prix_brut'].sum().sort_values(ascending=False)
    if not chart_data.empty:
        st.bar_chart(chart_data)

def vue_liste_clients(df):
    st.header("👥 Liste des Clients")
    if df.empty:
        st.info("Aucun client.")
        return
    clients = df[['nom_client', 'telephone', 'plateforme']].dropna(subset=['nom_client']).drop_duplicates().sort_values('nom_client')
    st.dataframe(clients, use_container_width=True)

def vue_sms(df):
    st.header("✉️ Générateur de SMS")
    df_tel = df.dropna(subset=['telephone', 'nom_client', 'date_arrivee'])
    df_tel = df_tel[df_tel['telephone'].astype(str).str.replace('+', '').str.isdigit()]
    if df_tel.empty:
        st.warning("Aucune réservation avec un numéro de téléphone valide.")
        return
    df_sorted = df_tel.sort_values(by="date_arrivee", ascending=False).reset_index()
    options_resa = [f"{idx}: {row['nom_client']} ({row['telephone']})" for idx, row in df_sorted.iterrows() if pd.notna(row['date_arrivee'])]
    selection = st.selectbox("Sélectionnez un client", options=options_resa, index=None)
    if selection:
        idx = int(selection.split(":")[0])
        resa = df_sorted.loc[idx]
        message_body = f"""VILLA TOBIAS
Plateforme : {resa.get('plateforme', 'N/A')}
Arrivée : {resa.get('date_arrivee').strftime('%d/%m/%Y')} Départ : {resa.get('date_depart').strftime('%d/%m/%Y')} Nuitées : {resa.get('nuitees', 0):.0f}

Bonjour {resa.get('nom_client')}
Téléphone : {resa.get('telephone')}

Bienvenue chez nous !

Nous sommes ravis de vous acceuillir bientot a Nice. Aussi afin d'organiser au mieux votre receptionmerci de nous indiquer votre heure d'arrivee. 

Sachez qu'une place de parking vous est allouee en cas de besoin. 

Le check-in se fait a partir de 14:00 h et le check-out avant 11:00 h. 

Vous trouverez des consignes a bagages dans chaque quartier a Nice. 

Nous vous souhaitons un excellent voyage et nous nous rejouissons de vous rencontrer tres bientot. 

Welcome to our home ! 

We are delighted to welcome you soon to Nice. In order to organize your reception as best as possibleplease let us know your arrival time. 

Please note that a parking space is available if needed. 

Check-in is from 2:00 p.m. and check-out is before 11:00 a.m. 

You will find luggage storage facilities in every neighborhood in Nice. 

We wish you a wonderful trip and look forward to meeting you very soon. 

Annick & Charley 

Merci de remplir la fiche d'arrivee / Please fill out the arrival form : 

https://urlr.me/Xu7Sq3"""
        message_area = st.text_area("Message à envoyer", value=message_body, height=400)
        encoded_message = quote(message_area)
        sms_link = f"sms:{resa['telephone']}?&body={encoded_message}"
        st.link_button("📲 Envoyer via Smartphone", sms_link)

def admin_sidebar(df):
    st.sidebar.markdown("---")
    st.sidebar.header("⚙️ Administration")
    st.sidebar.download_button(label="Télécharger la sauvegarde (CSV)", data=df.to_csv(sep=';', index=False).encode('utf-8'), file_name=CSV_RESERVATIONS, mime='text/csv')
    uploaded_file = st.sidebar.file_uploader("Restaurer depuis un fichier CSV", type=['csv'])
    if uploaded_file is not None:
        if st.sidebar.button("Confirmer la restauration"):
            try:
                with open(CSV_RESERVATIONS, "wb") as f: f.write(uploaded_file.getvalue())
                st.cache_data.clear()
                st.success("Fichier restauré. L'application va se recharger.")
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur lors de la restauration: {e}")

# ==============================  MAIN APP  ==============================
def main():
    st.title("📖 Gestion des Réservations - Villa Tobias")
    df, palette = charger_donnees_csv()
    st.sidebar.title("🧭 Navigation")
    pages = { 
        "📋 Réservations": vue_reservations, "➕ Ajouter": vue_ajouter, "✏️ Modifier / Supprimer": vue_modifier,
        "🎨 Plateformes": vue_plateformes, "📅 Calendrier": vue_calendrier, "📊 Rapport": vue_rapport,
        "👥 Liste des Clients": vue_liste_clients, "✉️ SMS": vue_sms,
    }
    selection = st.sidebar.radio("Aller à", list(pages.keys()))
    page_function = pages[selection]

    if selection in ["➕ Ajouter", "✏️ Modifier / Supprimer", "🎨 Plateformes", "📅 Calendrier", "📊 Rapport"]:
        page_function(df, palette)
    else:
        page_function(df)
        
    admin_sidebar(df)

if __name__ == "__main__":
    main()