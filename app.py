import streamlit as st
import pandas as pd
import os
import io
from datetime import datetime, timedelta

# ==============================
# CONFIGURATION
# ==============================
FICHIER_XLSX = "reservations.xlsx"

MOIS_LABELS = {
    1: "Janvier", 2: "Février", 3: "Mars", 4: "Avril",
    5: "Mai", 6: "Juin", 7: "Juillet", 8: "Août",
    9: "Septembre", 10: "Octobre", 11: "Novembre", 12: "Décembre"
}

# Couleurs par plateforme
PLATFORM_COLORS_DEFAULT = {
    "Booking": "#1E90FF",
    "Airbnb": "#FF5A5F",
    "Abritel": "#32CD32",
    "Autre": "#FFA500"
}

# ==============================
# CHARGEMENT DES DONNÉES
# ==============================
def charger_donnees():
    if os.path.exists(FICHIER_XLSX):
        return pd.read_excel(FICHIER_XLSX)
    else:
        colonnes = [
            "appartement", "plateforme", "nom_client", "sms", "paye",
            "date_arrivee", "date_depart", "nuitees",
            "prix_brut", "commissions", "frais_cb", "prix_net",
            "menage", "taxes_sejour", "base", "%"
        ]
        return pd.DataFrame(columns=colonnes)

def sauvegarder_donnees(df: pd.DataFrame):
    df.to_excel(FICHIER_XLSX, index=False)

# ==============================
# CALCULS
# ==============================
def recalculer(df: pd.DataFrame):
    if "prix_brut" in df and "commissions" in df and "frais_cb" in df:
        df["prix_net"] = df["prix_brut"] - df["commissions"] - df["frais_cb"]

    if "prix_net" in df and "menage" in df and "taxes_sejour" in df:
        df["base"] = df["prix_net"] - df["menage"] - df["taxes_sejour"]

    if "prix_brut" in df and "prix_net" in df:
        df["%"] = ((df["prix_brut"] - df["prix_net"]) / df["prix_brut"] * 100).round(2)

    return df

# ==============================
# AFFICHAGE DES KPI
# ==============================
def afficher_kpis(df: pd.DataFrame):
    if df.empty:
        st.info("Aucune donnée disponible.")
        return

    total_brut = df["prix_brut"].sum()
    total_net = df["prix_net"].sum()
    total_base = df["base"].sum()
    total_nuitees = df["nuitees"].sum()
    total_charges = df["commissions"].sum() + df["frais_cb"].sum()
    prix_moyen_nuitee = total_brut / total_nuitees if total_nuitees else 0
    commission_moy = (total_charges / total_brut * 100) if total_brut else 0

    col1, col2, col3 = st.columns(3)
    col1.metric("💰 Total Brut", f"{total_brut:.2f} €")
    col2.metric("💵 Total Net", f"{total_net:.2f} €")
    col3.metric("📉 Total Base", f"{total_base:.2f} €")

    col4, col5, col6 = st.columns(3)
    col4.metric("📊 Charges", f"{total_charges:.2f} €")
    col5.metric("📉 % Commissions", f"{commission_moy:.2f}%")
    col6.metric("🛌 Prix moyen/nuit", f"{prix_moyen_nuitee:.2f} €")

# ==============================
# VUES
# ==============================
def vue_reservations(df: pd.DataFrame):
    st.subheader("📋 Réservations")
    afficher_kpis(df)

    # Filtre année et mois
    annee = st.selectbox("Année", sorted(df["date_arrivee"].dt.year.unique()) if not df.empty else [datetime.today().year])
    mois = st.selectbox("Mois", ["Tous"] + list(MOIS_LABELS.values()))

    data_filtre = df.copy()
    if mois != "Tous":
        mois_num = [k for k, v in MOIS_LABELS.items() if v == mois][0]
        data_filtre = data_filtre[data_filtre["date_arrivee"].dt.month == mois_num]
    data_filtre = data_filtre[data_filtre["date_arrivee"].dt.year == annee]

    st.dataframe(data_filtre, use_container_width=True)

# ==============================
# OUTILS ICS & SMS
# ==============================
from datetime import date
import hashlib

def _ics_escape(text: str) -> str:
    if text is None:
        return ""
    s = str(text).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
    return s

def _fmt_date_ics(d: date) -> str:
    return d.strftime("%Y%m%d")

def _stable_uid(nom_client, plateforme, d1, d2, tel, salt="v1"):
    base = f"{nom_client}|{plateforme}|{d1}|{d2}|{tel}|{salt}"
    h = hashlib.sha1(base.encode("utf-8")).hexdigest()
    return f"vt-{h}@reservations"

def df_to_ics(df: pd.DataFrame, cal_name: str = "Réservations") -> str:
    if df.empty:
        return (
            "BEGIN:VCALENDAR\r\n"
            "VERSION:2.0\r\n"
            "PRODID:-//Reservations//FR\r\n"
            f"X-WR-CALNAME:{_ics_escape(cal_name)}\r\n"
            "CALSCALE:GREGORIAN\r\n"
            "METHOD:PUBLISH\r\n"
            "END:VCALENDAR\r\n"
        )

    lines = []
    A = lines.append
    A("BEGIN:VCALENDAR")
    A("VERSION:2.0")
    A("PRODID:-//Reservations//FR")
    A(f"X-WR-CALNAME:{_ics_escape(cal_name)}")
    A("CALSCALE:GREGORIAN")
    A("METHOD:PUBLISH")

    for _, r in df.iterrows():
        d1 = r.get("date_arrivee"); d2 = r.get("date_depart")
        if pd.isna(d1) or pd.isna(d2):
            continue
        nom = str(r.get("nom_client") or "").strip()
        plateforme = str(r.get("plateforme") or "").strip()
        tel = str(r.get("telephone") or "").strip() if "telephone" in r else ""
        uid = _stable_uid(nom, plateforme, d1, d2, tel)

        summary = " - ".join([x for x in [plateforme, nom, tel] if x])
        brut = float(r.get("prix_brut") or 0)
        net  = float(r.get("prix_net")  or 0)
        nuitees = int(r.get("nuitees") or ((d2 - d1).days))

        desc = (
            f"Plateforme: {plateforme}\\n"
            f"Client: {nom}\\n"
            f"Téléphone: {tel}\\n"
            f"Arrivee: {d1:%Y/%m/%d}\\n"
            f"Depart: {d2:%Y/%m/%d}\\n"
            f"Nuitees: {nuitees}\\n"
            f"Brut: {brut:.2f} €\\nNet: {net:.2f} €"
        )

        A("BEGIN:VEVENT")
        A(f"UID:{_ics_escape(uid)}")
        A(f"DTSTART;VALUE=DATE:{_fmt_date_ics(d1)}")
        A(f"DTEND;VALUE=DATE:{_fmt_date_ics(d2)}")
        A(f"SUMMARY:{_ics_escape(summary)}")
        A(f"DESCRIPTION:{_ics_escape(desc)}")
        A("END:VEVENT")

    A("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

def sms_message_arrivee(row: pd.Series) -> str:
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    d1s = d1.strftime("%Y/%m/%d") if pd.notna(d1) else ""
    d2s = d2.strftime("%Y/%m/%d") if pd.notna(d2) else ""
    nuitees = int(row.get("nuitees") or ((d2 - d1).days if pd.notna(d1) and pd.notna(d2) else 0))
    plateforme = str(row.get("plateforme") or "")
    nom = str(row.get("nom_client") or "")
    tel_aff = str(row.get("telephone") or "").strip() if "telephone" in row else ""

    return (
        "VILLA TOBIAS\n"
        f"Plateforme : {plateforme}\n"
        f"Date d'arrivee : {d1s}  Date depart : {d2s}  Nombre de nuitees : {nuitees}\n\n"
        f"Bonjour {nom}\n"
        f"Telephone : {tel_aff}\n\n"
        "Bienvenue chez nous !\n\n "
        "Merci de nous indiquer votre heure d'arrivée.\n\n "
        "Une place de parking est disponible si besoin.\n\n "
        "Bon voyage !"
    )

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Merci d’avoir choisi notre appartement ! "
        "Au plaisir de vous accueillir à nouveau."
    )


# ==============================
# VUES (suite)
# ==============================
def vue_ajouter(df: pd.DataFrame):
    st.subheader("➕ Ajouter une réservation")

    c1, c2 = st.columns(2)
    appartement = c1.text_input("Appartement", value=(df["appartement"].iloc[-1] if not df.empty else "Général") )
    plateforme = c2.selectbox("Plateforme", sorted(PLATFORM_COLORS_DEFAULT.keys()))

    c3, c4 = st.columns(2)
    nom_client = c3.text_input("Nom client")
    paye = c4.checkbox("Payé ?", value=False)

    c5, c6 = st.columns(2)
    date_arrivee = c5.date_input("Date d'arrivée", value=datetime.today().date())
    date_depart = c6.date_input("Date de départ", value=(datetime.today() + timedelta(days=2)).date(), min_value=date_arrivee + timedelta(days=1))

    nuitees = (date_depart - date_arrivee).days

    c7, c8 = st.columns(2)
    prix_brut = c7.number_input("Prix brut (€)", min_value=0.0, step=1.0)
    commissions = c8.number_input("Commissions (€)", min_value=0.0, step=1.0)

    c9, c10 = st.columns(2)
    frais_cb = c9.number_input("Frais CB (€)", min_value=0.0, step=1.0)
    menage = c10.number_input("Ménage (€)", min_value=0.0, step=1.0)

    c11, c12 = st.columns(2)
    taxes_sejour = c11.number_input("Taxes séjour (€)", min_value=0.0, step=1.0)
    telephone = c12.text_input("Téléphone (+33...)", value="")

    # Recalcul live
    temp = pd.DataFrame([{
        "prix_brut": prix_brut, "commissions": commissions, "frais_cb": frais_cb,
        "menage": menage, "taxes_sejour": taxes_sejour
    }])
    temp = recalculer(temp)
    prix_net = float(temp["prix_net"].iloc[0]) if not temp.empty else 0.0
    base = float(temp["base"].iloc[0]) if not temp.empty else 0.0
    pct = float(temp["%"].iloc[0]) if not temp.empty else 0.0

    st.info(f"Net (calculé): **{prix_net:.2f} €** • Base (calculée): **{base:.2f} €** • %: **{pct:.2f}**")

    if st.button("Enregistrer"):
        new_row = {
            "appartement": appartement,
            "plateforme": plateforme,
            "nom_client": nom_client,
            "paye": paye,
            "date_arrivee": pd.to_datetime(date_arrivee),
            "date_depart": pd.to_datetime(date_depart),
            "nuitees": nuitees,
            "prix_brut": prix_brut,
            "commissions": commissions,
            "frais_cb": frais_cb,
            "prix_net": prix_net,
            "menage": menage,
            "taxes_sejour": taxes_sejour,
            "base": base,
            "%": pct,
            "telephone": telephone
        }
        df2 = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
        df2 = recalculer(df2)
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée.")
        st.experimental_rerun()

def vue_modifier(df: pd.DataFrame):
    st.subheader("✏️ Modifier / Supprimer")

    if df.empty:
        st.info("Aucune réservation.")
        return

    df = df.copy()
    df["ident"] = df.apply(lambda r: f"{r.get('nom_client','')} | {r.get('date_arrivee').date() if pd.notna(r.get('date_arrivee')) else ''}", axis=1)
    choix = st.selectbox("Choisir une réservation", df["ident"])
    i = df.index[df["ident"] == choix][0]

    c1, c2 = st.columns(2)
    df.at[i, "appartement"] = c1.text_input("Appartement", value=str(df.at[i, "appartement"]))
    df.at[i, "plateforme"]  = c2.selectbox("Plateforme", sorted(PLATFORM_COLORS_DEFAULT.keys()), index=sorted(PLATFORM_COLORS_DEFAULT.keys()).index(df.at[i, "plateforme"]) if df.at[i, "plateforme"] in PLATFORM_COLORS_DEFAULT else 0)

    c3, c4 = st.columns(2)
    df.at[i, "nom_client"] = c3.text_input("Nom client", value=str(df.at[i, "nom_client"]))
    df.at[i, "paye"] = c4.checkbox("Payé ?", value=bool(df.at[i, "paye"]))

    c5, c6 = st.columns(2)
    d1 = pd.to_datetime(df.at[i, "date_arrivee"]).date() if pd.notna(df.at[i, "date_arrivee"]) else datetime.today().date()
    d2 = pd.to_datetime(df.at[i, "date_depart"]).date() if pd.notna(df.at[i, "date_depart"]) else (datetime.today() + timedelta(days=2)).date()
    new_d1 = c5.date_input("Date d'arrivée", value=d1)
    new_d2 = c6.date_input("Date de départ", value=d2, min_value=new_d1 + timedelta(days=1))
    df.at[i, "date_arrivee"] = pd.to_datetime(new_d1)
    df.at[i, "date_depart"]  = pd.to_datetime(new_d2)
    df.at[i, "nuitees"] = (new_d2 - new_d1).days

    c7, c8 = st.columns(2)
    df.at[i, "prix_brut"] = c7.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i, "prix_brut"]), step=1.0)
    df.at[i, "commissions"] = c8.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i, "commissions"]), step=1.0)

    c9, c10 = st.columns(2)
    df.at[i, "frais_cb"] = c9.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i, "frais_cb"]), step=1.0)
    df.at[i, "menage"]   = c10.number_input("Ménage (€)", min_value=0.0, value=float(df.at[i, "menage"]), step=1.0)

    c11, c12 = st.columns(2)
    df.at[i, "taxes_sejour"] = c11.number_input("Taxes séjour (€)", min_value=0.0, value=float(df.at[i, "taxes_sejour"]), step=1.0)
    df.at[i, "telephone"] = c12.text_input("Téléphone (+33...)", value=str(df.at[i, "telephone"]) if "telephone" in df.columns else "")

    # Preview des calculs
    prev = recalculer(df.loc[[i]].copy())
    st.info(f"Net (calculé): **{float(prev['prix_net'].iloc[0]):.2f} €** • Base (calculée): **{float(prev['base'].iloc[0]):.2f} €** • %: **{float(prev['%'].iloc[0]):.2f}**")

    cA, cB = st.columns(2)
    if cA.button("💾 Enregistrer"):
        df = recalculer(df)
        sauvegarder_donnees(df.drop(columns=["ident"]))
        st.success("✅ Modifié.")
        st.experimental_rerun()

    if cB.button("🗑 Supprimer"):
        df2 = df.drop(index=i).drop(columns=["ident"])
        sauvegarder_donnees(df2)
        st.warning("Supprimé.")
        st.experimental_rerun()

def vue_calendrier(df: pd.DataFrame):
    st.subheader("📅 Calendrier")

    if df.empty:
        st.info("Aucune donnée.")
        return

    # Filtres
    annee = st.selectbox("Année", sorted(df["date_arrivee"].dt.year.unique()))
    mois = st.selectbox("Mois", list(MOIS_LABELS.values()), index=datetime.today().month-1)
    mois_num = [k for k, v in MOIS_LABELS.items() if v == mois][0]

    data = df[(df["date_arrivee"].dt.year == annee) &
              (df["date_arrivee"].dt.month == mois_num)].copy()

    # Construction grille
    import calendar as cal
    nb_jours = cal.monthrange(annee, mois_num)[1]
    jours = [datetime(annee, mois_num, j+1).date() for j in range(nb_jours)]
    planning = {j: [] for j in jours}

    for _, r in data.iterrows():
        d1 = r["date_arrivee"].date(); d2 = r["date_depart"].date()
        nom = str(r["nom_client"])
        pf = str(r["plateforme"])
        ic = "⬤"  # puce simple
        for j in jours:
            if d1 <= j < d2:
                planning[j].append(f"{ic} {nom} ({pf})")

    # semainier
    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    table = []
    first_week = datetime(annee, mois_num, 1).weekday()  # 0=Mon
    week = [""] * first_week

    for day in jours:
        cell = f"{day.day}\n" + "\n".join(planning[day])
        week.append(cell)
        if len(week) == 7:
            table.append(week)
            week = []
    if week:
        week += [""] * (7 - len(week))
        table.append(week)

    st.table(pd.DataFrame(table, columns=headers))

def vue_rapport(df: pd.DataFrame):
    st.subheader("📊 Rapport")

    if df.empty:
        st.info("Aucune donnée.")
        return

    annee = st.selectbox("Année", sorted(df["date_arrivee"].dt.year.unique()), key="rep_annee")
    pf = st.selectbox("Plateforme", ["Toutes"] + sorted(df["plateforme"].dropna().unique()), key="rep_pf")
    mois = st.selectbox("Mois", ["Tous"] + list(MOIS_LABELS.values()), key="rep_mois")

    data = df[df["date_arrivee"].dt.year == annee].copy()
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]
    if mois != "Tous":
        mois_num = [k for k, v in MOIS_LABELS.items() if v == mois][0]
        data = data[data["date_arrivee"].dt.month == mois_num]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    # KPI
    afficher_kpis(data)

    # tableau détaillé
    show_cols = ["appartement","plateforme","nom_client","paye",
                 "date_arrivee","date_depart","nuitees",
                 "prix_brut","commissions","frais_cb","prix_net",
                 "menage","taxes_sejour","base","%"]
    show_cols = [c for c in show_cols if c in data.columns]
    st.dataframe(data[show_cols].sort_values(["date_arrivee","nom_client"]), use_container_width=True)

    # export xlsx
    buf = io.BytesIO()
    data[show_cols].to_excel(buf, index=False)
    st.download_button("⬇️ Télécharger le détail (XLSX)", data=buf.getvalue(),
                       file_name=f"rapport_{annee}{'' if mois=='Tous' else '_'+mois}.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def vue_clients(df: pd.DataFrame):
    st.subheader("👥 Liste clients")

    if df.empty:
        st.info("Aucune donnée.")
        return

    annee = st.selectbox("Année", sorted(df["date_arrivee"].dt.year.unique()), key="cli_annee")
    mois  = st.selectbox("Mois", ["Tous"] + list(MOIS_LABELS.values()), key="cli_mois")

    data = df[df["date_arrivee"].dt.year == annee].copy()
    if mois != "Tous":
        m = [k for k, v in MOIS_LABELS.items() if v == mois][0]
        data = data[data["date_arrivee"].dt.month == m]

    if data.empty:
        st.info("Aucune donnée.")
        return

    data["prix_brut/nuit"] = data.apply(lambda r: round((r["prix_brut"]/r["nuitees"]) if r["nuitees"] else 0,2), axis=1)
    data["prix_net/nuit"]  = data.apply(lambda r: round((r["prix_net"]/r["nuitees"])  if r["nuitees"] else 0,2), axis=1)

    cols = ["appartement","nom_client","plateforme","paye",
            "date_arrivee","date_depart","nuitees",
            "prix_brut","prix_net","base","prix_brut/nuit","prix_net/nuit"]
    cols = [c for c in cols if c in data.columns]
    st.dataframe(data[cols].sort_values(["date_arrivee","nom_client"]), use_container_width=True)

    buf = io.BytesIO()
    data[cols].to_excel(buf, index=False)
    st.download_button("📥 Télécharger (XLSX)", data=buf.getvalue(),
                       file_name="liste_clients.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def vue_export_ics(df: pd.DataFrame):
    st.subheader("📤 Export ICS")

    if df.empty:
        st.info("Aucune donnée.")
        return

    annee = st.selectbox("Année", sorted(df["date_arrivee"].dt.year.unique()), key="ics_annee")
    mois = st.selectbox("Mois", ["Tous"] + list(MOIS_LABELS.values()), key="ics_mois")
    pf = st.selectbox("Plateforme", ["Toutes"] + sorted(df["plateforme"].dropna().unique()), key="ics_pf")

    data = df[df["date_arrivee"].dt.year == annee].copy()
    if mois != "Tous":
        m = [k for k, v in MOIS_LABELS.items() if v == mois][0]
        data = data[data["date_arrivee"].dt.month == m]
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]

    if data.empty:
        st.info("Rien à exporter.")
        return

    ics_text = df_to_ics(data)
    st.download_button("⬇️ Télécharger reservations.ics",
                       data=ics_text.encode("utf-8"),
                       file_name="reservations.ics",
                       mime="text/calendar")

def vue_sms(df: pd.DataFrame):
    st.subheader("✉️ SMS (manuels)")

    if df.empty:
        st.info("Aucune donnée.")
        return

    today = datetime.today().date()
    demain = today + timedelta(days=1)
    hier = today - timedelta(days=1)

    c1, c2 = st.columns(2)

    with c1:
        st.markdown("**Arrivées demain**")
        arrives = df[df["date_arrivee"].dt.date == demain]
        if arrives.empty:
            st.info("Aucune arrivée demain.")
        else:
            for _, r in arrives.iterrows():
                body = sms_message_arrivee(r)
                tel = str(r.get("telephone") or "").strip()
                st.markdown(f"**{r['nom_client']}** — {r['plateforme']}")
                st.code(body)
                if tel:
                    st.link_button(f"📞 Appeler {tel}", f"tel:{tel}")
                    st.link_button("📩 Envoyer SMS", f"sms:{tel}?&body={body}")

    with c2:
        st.markdown("**Relance +24h après départ**")
        dep_24h = df[df["date_depart"].dt.date == hier]
        if dep_24h.empty:
            st.info("Aucun départ hier.")
        else:
            for _, r in dep_24h.iterrows():
                body = sms_message_depart(r)
                tel = str(r.get("telephone") or "").strip()
                st.markdown(f"**{r['nom_client']}** — {r['plateforme']}")
                st.code(body)
                if tel:
                    st.link_button(f"📞 Appeler {tel}", f"tel:{tel}")
                    st.link_button("📩 Envoyer SMS", f"sms:{tel}?&body={body}")

    # Composeur manuel
    st.markdown("---")
    st.markdown("**Composer un SMS manuel**")
    if not df.empty:
        df_pick = df.copy()
        df_pick["id_aff"] = df_pick.apply(
            lambda r: f"{r.get('nom_client','')} | {r.get('plateforme','')} | {r.get('date_arrivee').date() if pd.notna(r.get('date_arrivee')) else ''}",
            axis=1
        )
        choix = st.selectbox("Choisir une réservation", df_pick["id_aff"])
        r = df_pick.loc[df_pick["id_aff"] == choix].iloc[0]
        tel = str(r.get("telephone") or "").strip()
        body = st.text_area("Votre message", height=160, placeholder="Tapez votre SMS ici…")
        if tel and body:
            st.link_button(f"📞 Appeler {tel}", f"tel:{tel}")
            st.link_button("📩 Envoyer SMS", f"sms:{tel}?&body={body}")

def vue_ratios(df: pd.DataFrame):
    st.subheader("📈 Ratios (triables)")

    if df.empty:
        st.info("Aucune donnée.")
        return

    df = df.copy()
    df["annee"] = df["date_arrivee"].dt.year

    c1, c2 = st.columns(2)
    annee = c1.selectbox("Année", ["Toutes"] + sorted(df["annee"].dropna().unique().tolist()))
    pf = c2.selectbox("Plateforme", ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist()))

    data = df
    if annee != "Toutes":
        data = data[data["annee"] == annee]
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    # Agrégats par année x plateforme
    grouped = (data.groupby(["annee","plateforme"], dropna=True)
        .agg(
            total_brut=("prix_brut","sum"),
            total_net=("prix_net","sum"),
            total_base=("base","sum"),
            total_commissions=("commissions","sum"),
            total_frais_cb=("frais_cb","sum"),
            nuitees=("nuitees","sum"),
            sejours=("nom_client","count")
        )
        .reset_index()
    )
    grouped["charges"] = grouped["total_commissions"] + grouped["total_frais_cb"]
    grouped["% commissions"] = (grouped["charges"] / grouped["total_brut"] * 100).round(2)
    grouped["prix moyen/nuit"] = (grouped["total_brut"] / grouped["nuitees"]).replace([pd.NA, pd.NaT], 0).fillna(0)

    order_cols = [
        "annee","plateforme","sejours","nuitees",
        "total_brut","total_net","total_base",
        "charges","% commissions","prix moyen/nuit"
    ]
    order_cols = [c for c in order_cols if c in grouped.columns]
    st.dataframe(grouped[order_cols], use_container_width=True)

    # Export
    buf = io.BytesIO()
    grouped[order_cols].to_excel(buf, index=False)
    st.download_button("⬇️ Exporter ratios (XLSX)", data=buf.getvalue(),
                       file_name="ratios.xlsx",
                       mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ==============================
# NAVIGATION & MAIN
# ==============================
def main():
    st.set_page_config(page_title="📖 Réservations", layout="wide")

    # Chargement & calculs
    df = charger_donnees()
    if not df.empty:
        # conversions types
        date_cols = ["date_arrivee","date_depart"]
        for c in date_cols:
            if c in df.columns:
                df[c] = pd.to_datetime(df[c], errors="coerce")
        bool_cols = ["paye"] if "paye" in df.columns else []
        for c in bool_cols:
            df[c] = df[c].fillna(False).astype(bool)
        num_cols = ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","nuitees","%"]
        for c in num_cols:
            if c in df.columns:
                df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
        df = recalculer(df)

    # Barre latérale
    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio("Aller à", [
        "📋 Réservations",
        "➕ Ajouter",
        "✏️ Modifier / Supprimer",
        "📅 Calendrier",
        "📊 Rapport",
        "👥 Liste clients",
        "📤 Export ICS",
        "📈 Ratios",
        "💾 Sauvegarder"
    ])

    # Rendu onglets
    if onglet == "📋 Réservations":
        vue_reservations(df)
    elif onglet == "➕ Ajouter":
        vue_ajouter(df)
    elif onglet == "✏️ Modifier / Supprimer":
        vue_modifier(df)
    elif onglet == "📅 Calendrier":
        vue_calendrier(df)
    elif onglet == "📊 Rapport":
        vue_rapport(df)
    elif onglet == "👥 Liste clients":
        vue_clients(df)
    elif onglet == "📤 Export ICS":
        vue_export_ics(df)
    elif onglet == "📈 Ratios":
        vue_ratios(df)
    elif onglet == "💾 Sauvegarder":
        if not df.empty:
            sauvegarder_donnees(df)
            st.success("✅ Sauvegardé sur le disque (reservations.xlsx).")
        else:
            st.info("Rien à sauvegarder.")

if __name__ == "__main__":
    main()