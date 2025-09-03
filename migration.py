# migration.py
# Ce script lit les données des fichiers CSV exportés depuis Excel
# et les importe dans une nouvelle base de données SQLite (reservations.db).

import pandas as pd
import sqlite3
import os

# --- CONFIGURATION ---
# Assure-toi que ces noms de fichiers correspondent exactement à ceux que tu as.
CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv"
DB_FILE = "reservations.db"
# --------------------

# Colonnes attendues par la nouvelle application (app.py version SQLite)
# On ne prend que les colonnes de base, le reste sera recalculé.
BASE_COLS = [
    "date_reservation", "date_arrivee", "date_depart", "plateforme", 
    "nom_client", "tel_client", "nb_adultes", "nb_enfants", 
    "prix_brut", "charges", "paye", "notes"
]

def migrate_data():
    """Fonction principale pour migrer les données de CSV vers SQLite."""
    
    print("🚀 Démarrage de la migration...")

    # --- Étape 1: Vérifier si les fichiers CSV existent ---
    if not os.path.exists(CSV_RESERVATIONS):
        print(f"❌ ERREUR: Le fichier '{CSV_RESERVATIONS}' est introuvable.")
        return
    if not os.path.exists(CSV_PLATEFORMES):
        print(f"❌ ERREUR: Le fichier '{CSV_PLATEFORMES}' est introuvable.")
        return

    # --- Étape 2: Supprimer l'ancienne base de données si elle existe ---
    if os.path.exists(DB_FILE):
        print(f"🗑️ Suppression de l'ancienne base de données '{DB_FILE}'...")
        os.remove(DB_FILE)

    # --- Étape 3: Lire et nettoyer les données des réservations ---
    print(f"📄 Lecture du fichier de réservations '{CSV_RESERVATIONS}'...")
    try:
        df_reservations = pd.read_csv(CSV_RESERVATIONS)
        
        # Renommer les colonnes si nécessaire (ex: 'telephone' -> 'tel_client')
        df_reservations.rename(columns={'telephone': 'tel_client', 'nuitees': 'nb_nuits'}, inplace=True)

        # Assurer que toutes les colonnes de base existent
        for col in BASE_COLS:
            if col not in df_reservations.columns:
                df_reservations[col] = None # Créer la colonne si elle manque

        # Garder uniquement les colonnes utiles
        df_cleaned = df_reservations[BASE_COLS].copy()

        # Nettoyage et conversion des types
        df_cleaned['paye'] = df_cleaned['paye'].fillna(False).astype(bool)
        df_cleaned['date_arrivee'] = pd.to_datetime(df_cleaned['date_arrivee']).dt.date
        df_cleaned['date_depart'] = pd.to_datetime(df_cleaned['date_depart']).dt.date
        df_cleaned['date_reservation'] = pd.to_datetime(df_cleaned['date_reservation']).dt.date
        df_cleaned['tel_client'] = df_cleaned['tel_client'].astype(str).fillna('')
        df_cleaned['notes'] = df_cleaned['notes'].astype(str).fillna('')


        print("✅ Données des réservations nettoyées.")
    
    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier de réservations: {e}")
        return

    # --- Étape 4: Lire les données des plateformes ---
    print(f"🎨 Lecture du fichier des plateformes '{CSV_PLATEFORMES}'...")
    try:
        df_plateformes = pd.read_csv(CSV_PLATEFORMES)
        df_plateformes.rename(columns={'plateforme': 'nom', 'couleur': 'couleur'}, inplace=True)
        print("✅ Données des plateformes lues.")

    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier des plateformes: {e}")
        return

    # --- Étape 5: Écrire les données dans la base de données SQLite ---
    print(f"✍️ Écriture des données dans '{DB_FILE}'...")
    try:
        with sqlite3.connect(DB_FILE) as con:
            # Écrire les réservations
            df_cleaned.to_sql('reservations', con, if_exists='replace', index=False)
            
            # Écrire les plateformes
            df_plateformes.to_sql('plateformes', con, if_exists='replace', index=False)

        print("🎉 Migration terminée avec succès !")
        print(f"Le fichier '{DB_FILE}' est prêt à être utilisé avec votre application.")

    except Exception as e:
        print(f"❌ ERREUR lors de l'écriture dans la base de données: {e}")

# --- Lancement du script ---
if __name__ == "__main__":
    migrate_data()
