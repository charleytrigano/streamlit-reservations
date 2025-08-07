import streamlit as st
import pandas as pd
import calendar
from datetime import date, timedelta
import os

FICHIER = "reservations.xlsx"

def afficher_reservations(df):
    st.title("📋 Réservations")
    st.dataframe(df)

def ajouter_reservation(df):
    st.subheader("➕ Nouvelle Réservation")
    with st.form("ajout"):
        nom = st.text_input("Nom")
        plateforme = st.selectbox("Plateforme", ["Booking", "Airbnb", "Autre"])
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date arrivée")
        depart = st.date_input("Date départ", min_value=arrivee + timedelta(days=1))
        prix_brut = st.number_input("Prix brut", min_value=0.0)
        prix_net = st.number_input("Prix net", min_value=0.0, max_value=prix_brut)
        submit = st.form_submit_button("Enregistrer")
        if submit:
            ligne = {
                "nom_client": nom,
                "plateforme": plateforme,
                "telephone": tel,
                "date_arrivee": arrivee,
                "date_depart": depart,
                "prix_brut": round(prix_brut, 2),
                "prix_net": round(prix_net, 2),
                "charges": round(prix_brut - prix_net, 2),
                "%": round((prix_brut - prix_net) / prix_brut * 100, 2) if prix_brut else 0,
                "nuitees": (depart - arrivee).days,
                "annee": arrivee.year,
                "mois": arrivee.month
            }
            df = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
            df.to_excel(FICHIER, index=False)
            st.success("✅ Réservation enregistrée")

def modifier_reservation(df):
    st.subheader("✏️ Modifier / Supprimer")
    st.info("Fonction en construction")

def afficher_calendrier(df):
    st.subheader("📅 Calendrier")
    st.info("Fonction en construction")

def afficher_rapport(df):
    st.subheader("📊 Rapport")
    st.info("Fonction en construction")

def liste_clients(df):
    st.subheader("👥 Liste des clients")
    st.dataframe(df)
