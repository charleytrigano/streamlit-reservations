# migration.py (Version finale basée sur les données réelles)
import pandas as pd
import sqlite3
import os

CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv"
DB_FILE = "reservations.db"

def migrate_data():
    print("🚀 Démarrage de la migration...")
    if not os.path.exists(CSV_RESERVATIONS):
        print(f"❌ ERREUR: Fichier '{CSV_RESERVATIONS}' introuvable.")
        return
    if os.path.exists(DB_FILE):
        print(f"🗑️ Suppression de l'ancienne base de données '{DB_FILE}'...")
        os.remove(DB_FILE)

    try:
        # CORRECTION : Utilisation de la virgule comme délimiteur
        df_reservations = pd.read_csv(CSV_RESERVATIONS, delimiter=',')
        df_reservations.columns = df_reservations.columns.str.strip()
        print("✅ Données des réservations lues.")
    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier de réservations: {e}")
        return
    
    # Pas besoin de nettoyer les nombres, ils sont déjà au bon format.
    # On s'assure juste que les colonnes de dates sont bien gérées.
    for col in ['date_arrivee', 'date_depart']:
        df_reservations[col] = pd.to_datetime(df_reservations[col], format='%m/%d/%Y', errors='coerce')

    print(f"✍️ Écriture des données dans '{DB_FILE}'...")
    try:
        with sqlite3.connect(DB_FILE) as con:
            df_reservations.to_sql('reservations', con, if_exists='replace', index=False)
            
            # On recrée une table plateformes simple par défaut
            if os.path.exists(CSV_PLATEFORMES):
                df_plateformes = pd.read_csv(CSV_PLATEFORMES, delimiter=',')
                df_plateformes.rename(columns={'plateforme': 'nom'}, inplace=True)
                df_plateformes.to_sql('plateformes', con, if_exists='replace', index=False)

        print("🎉 Migration terminée avec succès !")
    except Exception as e:
        print(f"❌ ERREUR lors de l'écriture dans la base de données: {e}")

if __name__ == "__main__":
    migrate_data()
