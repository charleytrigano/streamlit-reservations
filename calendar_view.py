def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier")
    palette = get_palette()
    df = ensure_schema(df)

    # Si pas de données, on affiche un message plutôt que planter
    if df is None or df.empty:
        st.info("Aucune réservation à afficher.")
        return

    # Sélection année/mois – protection si aucune année dispo
    annees_series = df["AAAA"].dropna() if "AAAA" in df.columns else pd.Series(dtype="Int64")
    if annees_series.empty:
        st.info("Aucune année disponible (colonne AAAA vide). Ajoute au moins une réservation avec une date d’arrivée.")
        return

    annees = sorted(int(a) for a in annees_series.unique() if pd.notna(a))
    today = date.today()
    annee = st.selectbox("Année", annees, index=max(0, len(annees)-1))
    mois = st.selectbox("Mois", list(range(1, 13)), index=today.month - 1)

    cal = calendar.Calendar(firstweekday=0)  # 0 = lundi
    days = list(cal.itermonthdates(int(annee), int(mois)))

    # Prépare les réservations par jour
    rows = []
    core, _ = split_totals(df)
    for week in range(0, len(days), 7):
        tds = []
        for d in days[week:week+7]:
            # Jour hors mois = case grisée
            if d.month != mois:
                tds.append(
                    "<td style='vertical-align:top;width:14%;height:88px;border:1px solid #333;"
                    "background:rgba(127,127,127,0.08);color:rgba(255,255,255,0.5);padding:6px;'>"
                    f"{d.day}</td>"
                )
                continue

            # Trouve les séjours couvrant ce jour
            resa = core[(core["date_arrivee"] <= d) & (core["date_depart"] > d)]
            chips = []
            for _, r in resa.iterrows():
                pf = str(r.get("plateforme") or "Autre")
                nom = str(r.get("nom_client") or "")
                color = palette.get(pf, "#666666")
                chips.append(
                    f"<div style='margin-top:4px;padding:2px 6px;border-radius:4px;"
                    f"background:{color};color:white;font-size:0.82rem;overflow:hidden;text-overflow:ellipsis;'>"
                    f"{nom}</div>"
                )
            cell_html = "".join(chips)
            tds.append(
                "<td style='vertical-align:top;width:14%;height:88px;border:1px solid #333;"
                "background:transparent;color:inherit;padding:6px;'>"
                f"<div style='font-weight:600;opacity:0.9'>{d.day}</div>{cell_html}</td>"
            )
        rows.append("<tr>" + "".join(tds) + "</tr>")

    # Titre semaine
    head = "".join([f"<th style='padding:6px;border:1px solid #333'>{j}</th>"
                    for j in ['Lun','Mar','Mer','Jeu','Ven','Sam','Dim']])

    html = (
        "<div style='overflow-x:auto'>"
        "<table style='border-collapse:collapse;width:100%;font-size:0.95rem;'>"
        f"<tr>{head}</tr>"
        f"{''.join(rows)}"
        "</table>"
        "</div>"
    )
    st.markdown(html, unsafe_allow_html=True)

    # Légende
    if palette:
        leg = " • ".join(
            f"<span style='display:inline-block;width:0.9em;height:0.9em;background:{palette[p]};"
            f"margin-right:6px;border-radius:3px;vertical-align:-0.1em;'></span>{p}"
            for p in sorted(palette.keys())
        )
        st.caption("Légende :")
        st.markdown(leg, unsafe_allow_html=True)