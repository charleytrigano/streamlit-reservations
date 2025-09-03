# migration.py (Version finale, schéma enrichi)
import pandas as pd
import sqlite3
import os

# --- CONFIGURATION ---
CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv"
DB_FILE = "reservations.db"
# --------------------

def migrate_data():
    """Fonction principale pour migrer les données de CSV vers SQLite."""
    print("🚀 Démarrage de la migration...")

    # Vérification des fichiers source
    if not os.path.exists(CSV_RESERVATIONS):
        print(f"❌ ERREUR: Fichier '{CSV_RESERVATIONS}' introuvable.")
        return
    if not os.path.exists(CSV_PLATEFORMES):
        print(f"❌ ERREUR: Fichier '{CSV_PLATEFORMES}' introuvable.")
        return

    # Suppression de l'ancienne base de données
    if os.path.exists(DB_FILE):
        print(f"🗑️ Suppression de l'ancienne base de données '{DB_FILE}'...")
        os.remove(DB_FILE)

    # Lecture des réservations
    print(f"📄 Lecture du fichier de réservations '{CSV_RESERVATIONS}'...")
    try:
        df_reservations = pd.read_csv(CSV_RESERVATIONS, delimiter=';')
        df_reservations.columns = df_reservations.columns.str.strip() # Nettoyer les noms de colonnes
        print("✅ Données des réservations lues.")
    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier de réservations: {e}")
        return

    # Lecture des plateformes
    print(f"🎨 Lecture du fichier des plateformes '{CSV_PLATEFORMES}'...")
    try:
        df_plateformes = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
        df_plateformes.rename(columns={'plateforme': 'nom'}, inplace=True)
        print("✅ Données des plateformes lues.")
    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier des plateformes: {e}")
        return

    # Écriture dans la base de données
    print(f"✍️ Écriture des données dans '{DB_FILE}'...")
    try:
        with sqlite3.connect(DB_FILE) as con:
            df_reservations.to_sql('reservations', con, if_exists='replace', index=False)
            df_plateformes.to_sql('plateformes', con, if_exists='replace', index=False)
        print("🎉 Migration terminée avec succès !")
    except Exception as e:
        print(f"❌ ERREUR lors de l'écriture dans la base de données: {e}")

if __name__ == "__main__":
    migrate_data()
