# ---- Pages (tolérant : n’inclut que les vues réellement définies) ----
    page_specs = [
        ("🏠 Accueil", "vue_accueil"),
        ("📋 Réservations", "vue_reservations"),
        ("➕ Ajouter", "vue_ajouter"),
        ("✏️ Modifier / Supprimer", "vue_modifier"),
        ("🎨 Plateformes", "vue_plateformes"),
        ("📅 Calendrier", "vue_calendrier"),
        ("📊 Rapport", "vue_rapport"),
        ("✉️ SMS", "vue_sms"),
        ("📆 Export ICS", "vue_export_ics"),          # ← si absente, elle ne cassera plus l'app
        ("📝 Google Sheet", "vue_google_sheet"),
        ("👥 Clients", "vue_clients"),
        ("🆔 ID", "vue_id"),
        ("⚙️ Paramètres", "vue_settings"),
    ]
    pages = {label: globals().get(fn_name) for label, fn_name in page_specs if globals().get(fn_name)}

    if not pages:
        st.error("Aucune page disponible : vérifie que les fonctions de vues sont définies.")
        return

    choice = st.sidebar.radio("Aller à", list(pages.keys()), key="nav_radio")
    page_func = pages.get(choice)
    if page_func:
        page_func(df, palette)
    else:
        st.error("Page inconnue.")


if __name__ == "__main__":
    main()