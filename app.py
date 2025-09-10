# ============================== 3) DATA & UTILS ==============================

@st.cache_data
def load_reservations_data():
    return _detect_delimiter_and_read(CSV_RESERVATIONS)

def _detect_delimiter_and_read(file_path):
    """
    Tente de lire un fichier CSV en détectant le délimiteur.
    """
    # Lire le fichier en tant que chaîne de caractères pour la détection
    try:
        content = file_path.getvalue().decode("utf-8")
    except AttributeError:
        # Gère le cas où file_path est un chemin de fichier (ex: pour les tests)
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

    # Détecter le délimiteur
    # Si le délimiteur est le point-virgule
    if ';' in content.splitlines()[0]:
        delimiter = ';'
    else:
        delimiter = ','
    
    # Lecture du fichier avec le délimiteur détecté
    try:
        # Ajout de l'argument 'sep' (séparateur)
        df = pd.read_csv(StringIO(content), sep=delimiter)
        # Supprime les lignes vides
        df.dropna(how='all', inplace=True)
        # Réinitialise les index
        df.reset_index(drop=True, inplace=True)
        print(f"Fichier lu avec le délimiteur '{delimiter}'. Nombre de colonnes: {df.shape[1]}") # Ajout d'un journal de débogage
        return df
    except Exception as e:
        st.error(f"Erreur lors de la lecture du fichier : {e}")
        return pd.DataFrame()

def _series(s: any, dtype: str = "num"):
    """
    Transforme l'entrée en une série Pandas pour le traitement.
    """
    if isinstance(s, pd.Series):
        ser = s
    elif isinstance(s, np.ndarray):
        ser = pd.Series(s)
    elif isinstance(s, (list, tuple)):
        ser = pd.Series(s)
    else:
        ser = pd.Series([s])

    if dtype == "num":
        return pd.to_numeric(ser, errors='coerce').fillna(0)
    return ser


def _to_bool_series(s) -> pd.Series:
    ser = _series(s)
    return ser.fillna(False).astype(bool)


def _to_num(s) -> pd.Series:
    ser = _series(s, "string")
    return pd.to_numeric(ser, errors='coerce').fillna(0)


def _to_date(s) -> pd.Series:
    ser = _series(s, "string")
    return pd.to_datetime(ser, errors='coerce').dt.date

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    """
    Vérifie et assure que les colonnes nécessaires sont présentes et ont le bon type de données.
    """
    df = df.copy()

    # Nettoyer les noms des colonnes
    df.columns = df.columns.astype(str).str.strip()

    # Définir le schéma attendu avec les types de données
    schema = {
        'paye': 'bool',
        'nom_client': 'string',
        'email': 'string',
        'sms_envoye': 'bool',
        'post_depart_envoye': 'bool',
        'plateforme': 'string',
        'telephone': 'string',
        'date_arrivee': 'date',
        'date_depart': 'date',
        'nuitees': 'num',
        'prix_brut': 'num',
        'commissions': 'num',
        'frais_cb': 'num',
        'prix_net': 'num',
        'menage': 'num',
        'taxes_sejour': 'num',
        'base': 'num',
        'charges': 'num',
        '%': 'num',
        'res_id': 'string',
        'ical_uid': 'string',
        'AAAA': 'num',
        'MM': 'num',
    }

    # Vérifier et convertir les colonnes
    for col, dtype in schema.items():
        if col not in df.columns:
            df[col] = None  # Ajouter la colonne manquante
        else:
            try:
                if dtype == 'bool':
                    df[col] = _to_bool_series(df[col])
                elif dtype == 'num':
                    df[col] = _to_num(df[col])
                elif dtype == 'date':
                    df[col] = _to_date(df[col])
            except Exception as e:
                # Gérer les erreurs de conversion
                print(f"Erreur de conversion de type pour la colonne '{col}': {e}")
                # Le code ci-dessous ajoute un journal de débogage pour voir la cause de l'erreur
                print(f"Premières valeurs de la colonne '{col}' avant conversion :")
                print(df[col].head())
                st.error(f"Erreur de conversion de type pour la colonne '{col}'. "
                         f"Vérifiez que les données de cette colonne sont du bon format.")

    return df


def load_plateformes_data():
    """
    Charge les données des plateformes à partir du CSV.
    """
    try:
        df_plateformes = pd.read_csv(CSV_PLATEFORMES)
        return df_plateformes
    except FileNotFoundError:
        st.error("Le fichier 'plateformes.csv' est introuvable.")
        return pd.DataFrame(columns=['plateforme', 'couleur'])

def get_palette_from_df(df_plateformes):
    """
    Génère une palette de couleurs à partir des données des plateformes.
    """
    if not df_plateformes.empty:
        return dict(zip(df_plateformes['plateforme'], df_plateformes['couleur']))
    return DEFAULT_PALETTE
