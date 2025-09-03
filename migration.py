# migration.py (Version finale, schéma enrichi)
import pandas as pd
import sqlite3
import os

CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv"
DB_FILE = "reservations.db"

def migrate_data():
    print("🚀 Démarrage de la migration...")
    if not os.path.exists(CSV_RESERVATIONS) or not os.path.exists(CSV_PLATEFORMES):
        print(f"❌ ERREUR: Un des fichiers CSV est introuvable.")
        return
    if os.path.exists(DB_FILE):
        print(f"🗑️ Suppression de l'ancienne base de données '{DB_FILE}'...")
        os.remove(DB_FILE)

    try:
        df_reservations = pd.read_csv(CSV_RESERVATIONS, delimiter=';')
        df_reservations.columns = df_reservations.columns.str.strip()
        print("✅ Données des réservations lues.")
    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier de réservations: {e}")
        return

    try:
        df_plateformes = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        df_plateformes.rename(columns={'plateforme': 'nom'}, inplace=True)
        print("✅ Données des plateformes lues.")
    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier des plateformes: {e}")
        return

    print(f"✍️ Écriture des données dans '{DB_FILE}'...")
    try:
        with sqlite3.connect(DB_FILE) as con:
            # Important : on écrit la table avec toutes les colonnes du CSV
            df_reservations.to_sql('reservations', con, if_exists='replace', index=False)
            df_plateformes.to_sql('plateformes', con, if_exists='replace', index=False)
        print("🎉 Migration terminée avec succès !")
    except Exception as e:
        print(f"❌ ERREUR lors de l'écriture dans la base de données: {e}")

if __name__ == "__main__":
    migrate_data()
