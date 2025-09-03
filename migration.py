# migration.py (Version finale et robuste)
# Ce script lit les données des fichiers CSV exportés depuis Excel
# en utilisant le point-virgule comme séparateur,
# et les importe dans une nouvelle base de données SQLite (reservations.db).

import pandas as pd
import sqlite3
import os

# --- CONFIGURATION ---
CSV_RESERVATIONS = "reservations.xlsx - Sheet1.csv"
CSV_PLATEFORMES = "reservations.xlsx - Plateformes.csv"
DB_FILE = "reservations.db"
# --------------------

# Colonnes attendues par la nouvelle application (app.py version SQLite)
BASE_COLS = [
    "date_reservation", "date_arrivee", "date_depart", "plateforme",
    "nom_client", "tel_client", "nb_adultes", "nb_enfants",
    "prix_brut", "charges", "paye", "notes"
]

def migrate_data():
    """Fonction principale pour migrer les données de CSV vers SQLite."""

    print("🚀 Démarrage de la migration...")

    if not os.path.exists(CSV_RESERVATIONS) or not os.path.exists(CSV_PLATEFORMES):
        print(f"❌ ERREUR: Un des fichiers CSV est introuvable. Vérifie leur présence.")
        return

    if os.path.exists(DB_FILE):
        print(f"🗑️ Suppression de l'ancienne base de données '{DB_FILE}'...")
        os.remove(DB_FILE)

    print(f"📄 Lecture du fichier de réservations '{CSV_RESERVATIONS}'...")
    try:
        # Lecture du premier CSV avec le délimiteur point-virgule
        df_reservations = pd.read_csv(CSV_RESERVATIONS, delimiter=';')

        # Nettoyage des espaces superflus dans les noms de colonnes
        df_reservations.columns = df_reservations.columns.str.strip()

        df_reservations.rename(columns={'telephone': 'tel_client', 'nuitees': 'nb_nuits'}, inplace=True)

        for col in BASE_COLS:
            if col not in df_reservations.columns:
                df_reservations[col] = None

        df_cleaned = df_reservations[BASE_COLS].copy()

        # Nettoyage et conversion des types
        df_cleaned['paye'] = df_cleaned['paye'].fillna(False).astype(bool)
        for date_col in ['date_arrivee', 'date_depart', 'date_reservation']:
             df_cleaned[date_col] = pd.to_datetime(df_cleaned[date_col], dayfirst=True, errors='coerce').dt.date

        # Convertir les colonnes monétaires en nombres
        for col in ['prix_brut', 'charges']:
            if df_cleaned[col].dtype == 'object':
                 df_cleaned[col] = df_cleaned[col].str.replace('€', '', regex=False).str.replace(',', '.', regex=False).str.strip().astype(float)

        df_cleaned['tel_client'] = df_cleaned['tel_client'].astype(str).fillna('')
        df_cleaned['notes'] = df_cleaned['notes'].astype(str).fillna('')

        print("✅ Données des réservations nettoyées.")

    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier de réservations: {e}")
        return

    print(f"🎨 Lecture du fichier des plateformes '{CSV_PLATEFORMES}'...")
    try:
        # Vérifier si le fichier est vide avant de le lire
        if os.path.exists(CSV_PLATEFORMES) and os.path.getsize(CSV_PLATEFORMES) > 0:
            # Lecture du second CSV avec le délimiteur point-virgule
            df_plateformes = pd.read_csv(CSV_PLATEFORMES, delimiter=';')
            df_plateformes.rename(columns={'plateforme': 'nom', 'couleur': 'couleur'}, inplace=True)
        else:
            # Si le fichier est vide, on crée un DataFrame vide pour éviter une erreur
            print("Le fichier des plateformes est vide, on continue sans.")
            df_plateformes = pd.DataFrame(columns=['nom', 'couleur'])

        print("✅ Données des plateformes lues.")

    except Exception as e:
        print(f"❌ ERREUR lors de la lecture du fichier des plateformes: {e}")
        return

    print(f"✍️ Écriture des données dans '{DB_FILE}'...")
    try:
        with sqlite3.connect(DB_FILE) as con:
            df_cleaned.to_sql('reservations', con, if_exists='replace', index=False)
            df_plateformes.to_sql('plateformes', con, if_exists='replace', index=False)

        print("🎉 Migration terminée avec succès !")
        print(f"Le fichier '{DB_FILE}' est prêt à être utilisé avec votre application.")

    except Exception as e:
        print(f"❌ ERREUR lors de l'écriture dans la base de données: {e}")

if __name__ == "__main__":
    migrate_data()
