# =============== GESTION DES PLATEFORMES (Excel) =================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def _ensure_palette_df(dfpf: pd.DataFrame) -> pd.DataFrame:
    """Normalise la feuille Plateformes (colonnes/valeurs)."""
    if dfpf is None or dfpf.empty:
        return pd.DataFrame({"plateforme": list(DEFAULT_PALETTE.keys()),
                             "couleur":    list(DEFAULT_PALETTE.values())})
    dfpf = dfpf.copy()
    if "plateforme" not in dfpf.columns: dfpf["plateforme"] = ""
    if "couleur" not in dfpf.columns:    dfpf["couleur"] = ""
    # nettoyage simple
    dfpf["plateforme"] = dfpf["plateforme"].astype(str).str.strip()
    dfpf["couleur"] = dfpf["couleur"].astype(str).str.strip()
    dfpf = dfpf[dfpf["plateforme"] != ""].drop_duplicates(subset=["plateforme"], keep="last")
    # couleurs par défaut si vide / invalide
    dfpf.loc[~dfpf["couleur"].str.match(r"^#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$"), "couleur"] = "#999999"
    return dfpf.reset_index(drop=True)

@st.cache_data(show_spinner=False)
def charger_plateformes(path: str) -> pd.DataFrame:
    """Charge la feuille Plateformes si elle existe, sinon palette par défaut."""
    try:
        if not os.path.exists(path):
            return _ensure_palette_df(None)
        # tente lecture de la feuille Plateformes
        xls = pd.ExcelFile(path, engine="openpyxl")
        if "Plateformes" in xls.sheet_names:
            dfpf = pd.read_excel(path, engine="openpyxl", sheet_name="Plateformes")
            return _ensure_palette_df(dfpf)
        else:
            return _ensure_palette_df(None)
    except Exception as e:
        st.warning(f"Lecture Plateformes: {e}")
        return _ensure_palette_df(None)

def sauvegarder_plateformes(path: str, dfpf: pd.DataFrame):
    """Écrit/Remplace uniquement la feuille Plateformes (préserve le reste)."""
    dfpf = _ensure_palette_df(dfpf)
    try:
        # Si le fichier n’existe pas encore, on crée un classeur avec Plateformes
        if not os.path.exists(path):
            with pd.ExcelWriter(path, engine="openpyxl") as w:
                dfpf.to_excel(w, index=False, sheet_name="Plateformes")
        else:
            # Remplacer la feuille Plateformes sans toucher aux autres
            with pd.ExcelWriter(path, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
                dfpf.to_excel(w, index=False, sheet_name="Plateformes")
        st.cache_data.clear()
        st.success("✅ Plateformes enregistrées dans Excel.")
    except Exception as e:
        st.error(f"Échec sauvegarde Plateformes : {e}")

def get_palette() -> dict:
    """Palette prioritaire depuis Excel; sinon session ; sinon défaut."""
    try:
        dfpf = charger_plateformes(FICHIER)
        pal_xlsx = dict(zip(dfpf["plateforme"], dfpf["couleur"]))
        if pal_xlsx:
            return pal_xlsx
    except Exception:
        pass
    # fallback session / défaut
    if "palette" not in st.session_state:
        st.session_state["palette"] = DEFAULT_PALETTE.copy()
    # nettoyage minimal
    out = {}
    for k, v in st.session_state["palette"].items():
        if isinstance(k, str) and isinstance(v, str) and v.startswith("#") and len(v) in (4,7):
            out[k] = v
    if not out:
        out = DEFAULT_PALETTE.copy()
    return out

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return (
        f'<span style="display:inline-block;width:0.9em;height:0.9em;'
        f'background:{color};border-radius:3px;margin-right:6px;vertical-align:-0.1em;"></span>{name}'
    )

def vue_plateformes():
    """Onglet de gestion Plateformes (ajout / modif / suppression) persistant dans Excel."""
    st.title("🔧 Plateformes (couleurs)")
    dfpf = charger_plateformes(FICHIER).copy()

    st.caption("Ajoutez, modifiez ou supprimez des plateformes. Les couleurs doivent être au format hex (#RRGGBB).")
    edited = st.data_editor(
        dfpf,
        use_container_width=True,
        num_rows="dynamic",
        hide_index=True,
        column_config={
            "plateforme": st.column_config.TextColumn("Plateforme"),
            "couleur": st.column_config.TextColumn("Couleur (#RRGGBB)"),
        }
    )

    c1, c2, c3 = st.columns([1,1,2])
    if c1.button("➕ Ajouter une ligne"):
        edited = pd.concat([edited, pd.DataFrame([{"plateforme": "", "couleur": "#999999"}])], ignore_index=True)
        st.experimental_rerun()

    if c2.button("🗑 Supprimer les lignes vides"):
        edited = edited[edited["plateforme"].astype(str).str.strip() != ""].reset_index(drop=True)
        st.experimental_rerun()

    if st.button("💾 Enregistrer dans Excel"):
        sauvegarder_plateformes(FICHIER, edited)

    # Aperçu pastilles
    st.markdown("### Aperçu")
    pal = dict(zip(edited["plateforme"], edited["couleur"]))
    if pal:
        badges = " &nbsp;&nbsp;".join([platform_badge(pf, pal) for pf in sorted(pal.keys()) if pf])
        st.markdown(badges, unsafe_allow_html=True)