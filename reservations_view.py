def vue_reservations(df: pd.DataFrame):
    try:
        palette = get_palette()
        st.title("📋 Réservations")

        with st.expander("🎛️ Options d’affichage", expanded=True):
            filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
            show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
            enable_search = st.checkbox("Activer la recherche", value=True)

        # Aperçu plateformes
        if palette:
            st.markdown("### Plateformes")
            badges = " &nbsp;&nbsp;".join([platform_badge(pf, palette) for pf in sorted(palette.keys())])
            st.markdown(badges, unsafe_allow_html=True)

        # Toujours normaliser le DF
        df = ensure_schema(df)

        # Filtre payé
        if filtre_paye == "Payé":
            df = df[df["paye"] == True].copy()
        elif filtre_paye == "Non payé":
            df = df[df["paye"] == False].copy()

        if show_kpi:
            # Protège KPI si df est vide
            if df is None or df.empty:
                st.info("Aucune réservation pour calculer les totaux.")
            else:
                kpi_chips(df)

        if enable_search:
            df = search_box(df)

        # Sépare totaux
        core, totals = split_totals(df)
        core = sort_core(core)

        # Si rien à afficher
        if core.empty and totals.empty:
            st.info("Aucune ligne à afficher avec ces filtres.")
            return

        # Prépare l’éditeur (seulement colonnes existantes)
        core_edit = core.copy()
        core_edit["__rowid"] = core_edit.index
        if "date_arrivee" in core_edit.columns:
            core_edit["date_arrivee"] = core_edit["date_arrivee"].apply(format_date_str)
        if "date_depart" in core_edit.columns:
            core_edit["date_depart"]  = core_edit["date_depart"].apply(format_date_str)

        cols_order = [
            "paye","nom_client","sms_envoye","plateforme","telephone",
            "date_arrivee","date_depart","nuitees",
            "prix_brut","commissions","frais_cb","prix_net",
            "menage","taxes_sejour","base","charges","%","AAAA","MM","__rowid"
        ]
        cols_show = [c for c in cols_order if c in core_edit.columns]

        edited = st.data_editor(
            core_edit[cols_show] if cols_show else core_edit,
            use_container_width=True,
            hide_index=True,
            column_config={
                "paye": st.column_config.CheckboxColumn("Payé"),
                "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
                "__rowid": st.column_config.Column("id", help="Interne", disabled=True, width="small"),
                "date_arrivee": st.column_config.TextColumn("date_arrivee", disabled=True),
                "date_depart":  st.column_config.TextColumn("date_depart",  disabled=True),
                "nom_client":   st.column_config.TextColumn("nom_client",   disabled=True),
                "plateforme":   st.column_config.TextColumn("plateforme",   disabled=True),
                "telephone":    st.column_config.TextColumn("telephone",    disabled=True),
                "nuitees":      st.column_config.NumberColumn("nuitees",    disabled=True),
                "prix_brut":    st.column_config.NumberColumn("prix_brut",   disabled=True),
                "commissions":  st.column_config.NumberColumn("commissions", disabled=True),
                "frais_cb":     st.column_config.NumberColumn("frais_cb",    disabled=True),
                "prix_net":     st.column_config.NumberColumn("prix_net",    disabled=True),
                "menage":       st.column_config.NumberColumn("menage",      disabled=True),
                "taxes_sejour": st.column_config.NumberColumn("taxes_sejour",disabled=True),
                "base":         st.column_config.NumberColumn("base",        disabled=True),
                "charges":      st.column_config.NumberColumn("charges",     disabled=True),
                "%":            st.column_config.NumberColumn("%",           disabled=True),
                "AAAA":         st.column_config.NumberColumn("AAAA",        disabled=True),
                "MM":           st.column_config.NumberColumn("MM",          disabled=True),
            }
        )

        c1, _ = st.columns([1,3])
        if c1.button("💾 Enregistrer les cases cochées"):
            if edited is not None and not edited.empty:
                for _, r in edited.iterrows():
                    ridx = int(r["__rowid"])
                    if ridx in core.index:
                        core.at[ridx, "paye"] = bool(r.get("paye", False))
                        core.at[ridx, "sms_envoye"] = bool(r.get("sms_envoye", False))
                new_df = pd.concat([core, totals], ignore_index=False).reset_index(drop=True)
                sauvegarder_donnees(new_df)
                st.success("✅ Stat