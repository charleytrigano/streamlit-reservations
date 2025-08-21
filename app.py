import streamlit as st
import pandas as pd
import numpy as np
import os
from datetime import datetime, timedelta
import calendar
import json

FICHIER = "reservations.xlsx"
CONFIG_FILE = "plateformes.json"
LOGO_FILE = "logo.png"

# =========================
# Gestion des plateformes
# =========================
def charger_palette():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    # palette par défaut
    return {
        "Booking": "#1e90ff",
        "Airbnb": "#ff5a5f",
        "Abritel": "#00a699",
        "Autre": "#f59e0b",
    }

def sauvegarder_palette(palette):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(palette, f, ensure_ascii=False, indent=2)

PALETTE = charger_palette()

def platform_badge(pf):
    color = PALETTE.get(pf, "#999999")
    return f'<span style="color:{color}">{pf}</span>'

# =========================
# Gestion des données
# =========================
def ensure_schema(df: pd.DataFrame):
    colonnes = [
        "paye", "nom_client", "sms_envoye", "plateforme", "telephone",
        "date_arrivee", "date_depart", "prix_brut", "commissions",
        "frais_cb", "prix_net", "menage", "taxes_sejour",
        "base", "charges", "%", "nuitees", "AAAA", "MM", "ical_uid"
    ]
    for col in colonnes:
        if col not in df.columns:
            if col in ["paye", "sms_envoye"]:
                df[col] = False
            elif col in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
                df[col] = 0.0
            elif col in ["AAAA","MM","nuitees"]:
                df[col] = 0
            else:
                df[col] = ""
    return df[colonnes]

def charger_donnees():
    if os.path.exists(FICHIER):
        try:
            df = pd.read_excel(FICHIER)
            df = ensure_schema(df)
            for c in ["date_arrivee","date_depart"]:
                df[c] = pd.to_datetime(df[c], errors="coerce")
            return df
        except Exception as e:
            st.error(f"Erreur lecture {FICHIER} : {e}")
    return ensure_schema(pd.DataFrame())

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    df.to_excel(FICHIER, index=False)

# =========================
# Utils
# =========================
def normalize_tel(tel: str):
    if not tel: return ""
    return "".join([c for c in str(tel) if c.isdigit()])

# =========================
# Vue AJOUTER
# =========================
def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    df = ensure_schema(df)

    col1,col2 = st.columns(2)
    with col1:
        nom = st.text_input("Nom du client")
        tel = st.text_input("Téléphone")
        arrivee = st.date_input("Date d’arrivée", value=datetime.today())
        brut = st.number_input("Prix brut (€)", 0.0, 10000.0, 100.0, 10.0)
        menage = st.number_input("Frais ménage (€)", 0.0, 500.0, 50.0, 5.0)
    with col2:
        plateforme = st.selectbox("Plateforme", list(PALETTE.keys()))
        depart = st.date_input("Date de départ", value=datetime.today()+timedelta(days=1))
        commissions = st.number_input("Commission (€)", 0.0, 5000.0, 0.0, 5.0)
        frais_cb = st.number_input("Frais CB (€)", 0.0, 500.0, 0.0, 1.0)

    paye = st.checkbox("Réservation payée ?", value=False)
    sms_envoye = st.checkbox("SMS envoyé ?", value=False)

    nuitees = (depart - arrivee).days
    taxes = round(nuitees * 2.01, 2)
    net_calc = brut - commissions - frais_cb - menage - taxes
    base_calc = brut - commissions
    charges_calc = commissions + frais_cb + menage + taxes
    pct_calc = round(100*net_calc/base_calc,2) if base_calc!=0 else 0

    st.markdown(f"""
    **Résumé :**
    - Nuitées : {nuitees}  
    - Taxes de séjour : {taxes} €  
    - Net : {net_calc:.2f} €  
    - % marge : {pct_calc} %
    """)

    if st.button("Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        ligne = {
            "paye": bool(paye),
            "nom_client": (nom or "").strip(),
            "sms_envoye": bool(sms_envoye),
            "plateforme": plateforme,
            "telephone": normalize_tel(tel),
            "date_arrivee": arrivee,
            "date_depart": depart,
            "prix_brut": float(brut),
            "commissions": float(commissions),
            "frais_cb": float(frais_cb),
            "prix_net": round(net_calc, 2),
            "menage": float(menage),
            "taxes_sejour": float(taxes),
            "base": round(base_calc, 2),
            "charges": round(charges_calc, 2),
            "%": round(pct_calc, 2),
            "nuitees": (depart - arrivee).days,
            "AAAA": arrivee.year,
            "MM": arrivee.month,
            "ical_uid": ""
        }
        df2 = pd.concat([df, pd.DataFrame([ligne])], ignore_index=True)
        sauvegarder_donnees(df2)
        st.success("✅ Réservation enregistrée")
        st.experimental_rerun()
# =========================
# Vue MODIFIER / SUPPRIMER
# =========================
def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune réservation.")
        return

    # Sélecteur d'une ligne
    df["__id"] = df.index
    df["__lib"] = (
        df["nom_client"].astype(str)
        + " | "
        + pd.to_datetime(df["date_arrivee"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
        + " → "
        + pd.to_datetime(df["date_depart"], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    )
    row_label = st.selectbox("Choisir une réservation", df["__lib"])
    rid = int(df.loc[df["__lib"] == row_label, "__id"].iloc[0])

    c0, c1, c2 = st.columns(3)
    with c0:
        paye = st.checkbox("Payé", value=bool(df.at[rid, "paye"]))
    with c1:
        sms_envoye = st.checkbox("SMS envoyé", value=bool(df.at[rid, "sms_envoye"]))
    with c2:
        plateforme = st.selectbox("Plateforme", list(PALETTE.keys()), index=max(0, list(PALETTE.keys()).index(df.at[rid, "plateforme"])) if df.at[rid, "plateforme"] in PALETTE else 0)

    nom = st.text_input("Nom du client", df.at[rid, "nom_client"])
    tel = st.text_input("Téléphone", str(df.at[rid, "telephone"]))
    arrivee = st.date_input("Arrivée", pd.to_datetime(df.at[rid, "date_arrivee"]).date() if pd.notna(df.at[rid, "date_arrivee"]) else datetime.today().date())
    depart_min = arrivee + timedelta(days=1)
    depart = st.date_input("Départ", pd.to_datetime(df.at[rid, "date_depart"]).date() if pd.notna(df.at[rid, "date_depart"]) else depart_min, min_value=depart_min)

    c3, c4, c5 = st.columns(3)
    with c3:
        brut = st.number_input("Prix brut (€)", value=float(df.at[rid, "prix_brut"]), min_value=0.0, step=1.0, format="%.2f")
    with c4:
        commissions = st.number_input("Commission (€)", value=float(df.at[rid, "commissions"]), min_value=0.0, step=1.0, format="%.2f")
    with c5:
        frais_cb = st.number_input("Frais CB (€)", value=float(df.at[rid, "frais_cb"]), min_value=0.0, step=1.0, format="%.2f")

    d1, d2 = st.columns(2)
    with d1:
        menage = st.number_input("Frais ménage (€)", value=float(df.at[rid, "menage"]), min_value=0.0, step=1.0, format="%.2f")
    with d2:
        taxes = st.number_input("Taxes de séjour (€)", value=float(df.at[rid, "taxes_sejour"]), min_value=0.0, step=0.5, format="%.2f")

    # Recalcule
    nuitees = (depart - arrivee).days
    prix_net = max(brut - commissions - frais_cb, 0.0)
    base = max(prix_net - menage - taxes, 0.0)
    charges = max(brut - prix_net, 0.0)
    pct = round((charges / brut * 100), 2) if brut else 0.0

    st.markdown(
        f"**Résumé** — Nuitées: {nuitees}, Net: {prix_net:.2f}€, Base: {base:.2f}€, Charges: {charges:.2f}€, %: {pct:.2f}"
    )

    b1, b2 = st.columns(2)
    if b1.button("💾 Enregistrer la modification"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        df.at[rid, "paye"] = bool(paye)
        df.at[rid, "sms_envoye"] = bool(sms_envoye)
        df.at[rid, "plateforme"] = plateforme
        df.at[rid, "nom_client"] = (nom or "").strip()
        df.at[rid, "telephone"] = normalize_tel(tel)
        df.at[rid, "date_arrivee"] = arrivee
        df.at[rid, "date_depart"] = depart
        df.at[rid, "prix_brut"] = float(brut)
        df.at[rid, "commissions"] = float(commissions)
        df.at[rid, "frais_cb"] = float(frais_cb)
        df.at[rid, "prix_net"] = round(prix_net, 2)
        df.at[rid, "menage"] = float(menage)
        df.at[rid, "taxes_sejour"] = float(taxes)
        df.at[rid, "base"] = round(base, 2)
        df.at[rid, "charges"] = round(charges, 2)
        df.at[rid, "%"] = round(pct, 2)
        df.at[rid, "nuitees"] = nuitees
        df.at[rid, "AAAA"] = arrivee.year
        df.at[rid, "MM"] = arrivee.month
        df.drop(columns=["__id", "__lib"], inplace=True, errors="ignore")
        sauvegarder_donnees(df)
        st.success("✅ Modifié")
        st.experimental_rerun()

    if b2.button("🗑 Supprimer cette réservation"):
        df2 = df.drop(index=rid)
        df2.drop(columns=["__id", "__lib"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2)
        st.warning("Supprimé.")
        st.experimental_rerun()


# =========================
# Vue RÉSERVATIONS (liste + filtres)
# =========================
def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")
    df = ensure_schema(df)

    c1, c2 = st.columns([1, 3])
    with c1:
        filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"], index=0)
    with c2:
        q = st.text_input("🔎 Recherche (nom / tel / plateforme)")

    if filtre_paye == "Payé":
        df = df[df["paye"] == True]
    elif filtre_paye == "Non payé":
        df = df[df["paye"] == False]

    if q:
        ql = q.strip().lower()
        def match(v):
            s = "" if pd.isna(v) else str(v)
            return ql in s.lower()
        mask = df["nom_client"].apply(match) | df["telephone"].apply(match) | df["plateforme"].apply(match)
        df = df[mask]

    # Affiche la palette (légende)
    st.caption("Plateformes :")
    st.markdown(" • ".join([platform_badge(p) for p in PALETTE.keys()]), unsafe_allow_html=True)

    show = df.copy()
    for c in ["date_arrivee", "date_depart"]:
        show[c] = pd.to_datetime(show[c], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    cols = [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net",
        "menage","taxes_sejour","base","charges","%","AAAA","MM"
    ]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)

    # Bouton sauvegarde (écrit tout le df)
    if st.button("💾 Sauvegarder le fichier Excel"):
        try:
            sauvegarder_donnees(df)
            st.success("Fichier Excel sauvegardé.")
        except Exception as e:
            st.error(f"Erreur de sauvegarde : {e}")


# =========================
# Calendrier coloré
# =========================
def _lighten(hex_color: str, factor: float = 0.75) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    # éclaircissement simple
    r2 = int(r + (255 - r) * factor)
    g2 = int(g + (255 - g) * factor)
    b2 = int(b + (255 - b) * factor)
    return f"#{r2:02x}{g2:02x}{b2:02x}"

def _ideal_fg(bg_hex: str) -> str:
    bg_hex = bg_hex.lstrip("#")
    r = int(bg_hex[0:2], 16); g = int(bg_hex[2:4], 16); b = int(bg_hex[4:6], 16)
    luminance = (0.299*r + 0.587*g + 0.114*b)/255
    return "#000000" if luminance > 0.6 else "#ffffff"

def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier mensuel (coloré)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    c1, c2 = st.columns(2)
    mois = c1.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, datetime.today().month-1))
    annees = sorted([int(a) for a in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = c2.selectbox("Année", annees, index=len(annees)-1)

    m_idx = list(calendar.month_name).index(mois)
    nb_jours = calendar.monthrange(annee, m_idx)[1]
    jours = [datetime(annee, m_idx, j).date() for j in range(1, nb_jours+1)]

    # planning
    plan = {j: [] for j in jours}
    for _, r in df.iterrows():
        d1 = pd.to_datetime(r["date_arrivee"], errors="coerce")
        d2 = pd.to_datetime(r["date_depart"], errors="coerce")
        if pd.isna(d1) or pd.isna(d2):
            continue
        d1 = d1.date(); d2 = d2.date()
        pf = str(r["plateforme"] or "Autre")
        nom = str(r["nom_client"] or "")
        for j in jours:
            if d1 <= j < d2:
                plan[j].append((pf, nom))

    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    monthcal = calendar.monthcalendar(annee, m_idx)

    grid_text = []
    grid_bg = []
    grid_fg = []

    for week in monthcal:
        row_text, row_bg, row_fg = [], [], []
        for day in week:
            if day == 0:
                row_text.append("")
                row_bg.append("transparent")
                row_fg.append(None)
            else:
                d = datetime(annee, m_idx, day).date()
                items = plan.get(d, [])
                # Texte
                if len(items) > 5:
                    txt_lines = [str(day)] + [f"{pf} · {nom}" for pf,nom in items[:5]] + [f"... (+{len(items)-5})"]
                else:
                    txt_lines = [str(day)] + [f"{pf} · {nom}" for pf,nom in items]
                row_text.append("\n".join(txt_lines))
                # Couleurs
                if items:
                    base = PALETTE.get(items[0][0], "#999999")
                    bg = _lighten(base, 0.75)
                    fg = _ideal_fg(bg)
                else:
                    bg = "transparent"
                    fg = None
                row_bg.append(bg)
                row_fg.append(fg)
        grid_text.append(row_text)
        grid_bg.append(row_bg)
        grid_fg.append(row_fg)

    df_table = pd.DataFrame(grid_text, columns=headers)

    def style_row(vals, r):
        css = []
        for c_idx, _ in enumerate(vals):
            bg = grid_bg[r][c_idx]
            fg = grid_fg[r][c_idx] or "inherit"
            css.append(
                f"background-color:{bg};color:{fg};white-space:pre-wrap;"
                f"border:1px solid rgba(127,127,127,0.25);"
            )
        return css

    styler = df_table.style
    for r in range(df_table.shape[0]):
        styler = styler.apply(lambda v, rr=r: style_row(v, rr), axis=1)

    st.caption("Légende :")
    legend = " • ".join([f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{PALETTE[p]};border-radius:3px;margin-right:6px;"></span>{p}' for p in sorted(PALETTE.keys())])
    st.markdown(legend, unsafe_allow_html=True)

    st.dataframe(styler, use_container_width=True, height=480)


# =========================
# Rapport
# =========================
def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(a) for a in df["AAAA"].dropna().unique()])
    if not annees:
        st.info("Aucune année disponible.")
        return

    col1, col2, col3 = st.columns(3)
    annee = col1.selectbox("Année", annees, index=len(annees)-1)
    pf_opt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = col2.selectbox("Plateforme", pf_opt)
    mois_opt = ["Tous"] + [f"{i:02d}" for i in range(1,13)]
    mois = col3.selectbox("Mois", mois_opt)

    data = df[df["AAAA"] == int(annee)].copy()
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]

    if data.empty:
        st.info("Aucune donnée pour ces filtres.")
        return

    detail = data.copy()
    for c in ["date_arrivee","date_depart"]:
        detail[c] = pd.to_datetime(detail[c], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")
    st.dataframe(
        detail[[
            "paye","nom_client","sms_envoye","plateforme","telephone",
            "date_arrivee","date_depart","nuitees",
            "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"
        ]],
        use_container_width=True
    )

    # totaux
    tot_brut = data["prix_brut"].sum()
    tot_net  = data["prix_net"].sum()
    tot_base = data["base"].sum()
    tot_ch   = data["charges"].sum()
    nuits    = data["nuitees"].sum()
    pm_nuit  = (tot_brut/nuits) if nuits else 0
    pct      = (tot_ch/tot_brut*100) if tot_brut else 0

    st.markdown(
        f"**Totaux** — Brut: {tot_brut:.2f}€, Net: {tot_net:.2f}€, Base: {tot_base:.2f}€, Charges: {tot_ch:.2f}€, Nuitées: {int(nuits)}, Prix moyen/nuit: {pm_nuit:.2f}€, Commission moy: {pct:.2f}%"
    )


# =========================
# Clients (liste export)
# =========================
def vue_clients(df: pd.DataFrame):
    st.title("👥 Liste des clients")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    annees = sorted([int(a) for a in df["AAAA"].dropna().unique()])
    col1, col2 = st.columns(2)
    annee = col1.selectbox("Année", annees, index=len(annees)-1) if annees else None
    mois = col2.selectbox("Mois", ["Tous"] + [f"{i:02d}" for i in range(1,13)])

    data = df.copy()
    if annee:
        data = data[data["AAAA"] == int(annee)]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]

    if data.empty:
        st.info("Aucune donnée pour cette période.")
        return

    data["prix_brut/nuit"] = data.apply(lambda r: round((r["prix_brut"]/r["nuitees"]) if r["nuitees"] else 0,2), axis=1)
    data["prix_net/nuit"]  = data.apply(lambda r: round((r["prix_net"]/r["nuitees"])  if r["nuitees"] else 0,2), axis=1)

    show = data.copy()
    for c in ["date_arrivee","date_depart"]:
        show[c] = pd.to_datetime(show[c], errors="coerce").dt.strftime("%Y-%m-%d").fillna("")

    cols = ["paye","nom_client","sms_envoye","plateforme","telephone","date_arrivee","date_depart",
            "nuitees","prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","prix_brut/nuit","prix_net/nuit"]
    cols = [c for c in cols if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)
    st.download_button(
        "📥 Export CSV",
        data=show[cols].to_csv(index=False).encode("utf-8"),
        file_name="clients.csv",
        mime="text/csv"
    )


# =========================
# Export ICS
# =========================
def df_to_ics(df: pd.DataFrame, cal_name: str = "Villa Tobias – Réservations") -> str:
    def esc(s: str) -> str:
        if s is None:
            return ""
        s = str(s)
        s = s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")
        return s

    def fmt_date(d):
        return pd.to_datetime(d).strftime("%Y%m%d")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Villa Tobias//Reservations//FR",
        f"X-WR-CALNAME:{esc(cal_name)}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]
    for _, r in df.iterrows():
        if pd.isna(r["date_arrivee"]) or pd.isna(r["date_depart"]):
            continue
        nom = str(r["nom_client"] or "")
        pf  = str(r["plateforme"] or "")
        tel = str(r["telephone"] or "")
        summary = " - ".join([x for x in [pf, nom, tel] if x])
        desc = (
            f"Plateforme: {pf}\\n"
            f"Client: {nom}\\n"
            f"Téléphone: {tel}\\n"
        )
        lines += [
            "BEGIN:VEVENT",
            f"DTSTART;VALUE=DATE:{fmt_date(r['date_arrivee'])}",
            f"DTEND;VALUE=DATE:{fmt_date(r['date_depart'])}",
            f"SUMMARY:{esc(summary)}",
            f"DESCRIPTION:{esc(desc)}",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"

def vue_export_ics(df: pd.DataFrame):
    st.title("📤 Export ICS")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    c1, c2, c3 = st.columns(3)
    annees = sorted([int(a) for a in df["AAAA"].dropna().unique()])
    annee = c1.selectbox("Année", ["Toutes"] + annees, index=len(annees)) if annees else "Toutes"
    mois  = c2.selectbox("Mois", ["Tous"] + list(range(1,13)))
    pfopt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf    = c3.selectbox("Plateforme", pfopt)

    data = df.copy()
    if annee != "Toutes":
        data = data[data["AAAA"] == int(annee)]
    if mois != "Tous":
        data = data[data["MM"] == int(mois)]
    if pf != "Toutes":
        data = data[data["plateforme"] == pf]

    if data.empty:
        st.info("Aucune réservation pour ces filtres.")
        return

    ics = df_to_ics(data)
    st.download_button(
        "⬇️ Télécharger reservations.ics",
        data=ics.encode("utf-8"),
        file_name="reservations.ics",
        mime="text/calendar"
    )


# =========================
# SMS (simple affichage de modèles)
# =========================
from urllib.parse import quote

def sms_message_arrivee(row: pd.Series) -> str:
    d1 = pd.to_datetime(row["date_arrivee"], errors="coerce")
    d2 = pd.to_datetime(row["date_depart"], errors="coerce")
    d1s = d1.strftime("%Y/%m/%d") if not pd.isna(d1) else ""
    d2s = d2.strftime("%Y/%m/%d") if not pd.isna(d2) else ""
    nuitees = int((d2 - d1).days) if (not pd.isna(d1) and not pd.isna(d2)) else 0
    pf = str(row.get("plateforme") or "")
    nom = str(row.get("nom_client") or "")
    tel = str(row.get("telephone") or "")
    return (
        "VILLA TOBIAS\n"
        f"Plateforme : {pf}\n"
        f"Date d'arrivee : {d1s}  Date depart : {d2s}  Nombre de nuitees : {nuitees}\n\n"
        f"Bonjour {nom}\n"
        f"Telephone : {tel}\n\n"
        "Bienvenue chez nous !\n"
        "Pouvez-vous nous indiquer votre heure d'arrivée ?\n"
        "Check-in à partir de 14:00, check-out avant 11:00.\n"
        "Bonne route !\n"
        "Annick & Charley"
    )

def sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Merci pour votre séjour ! Nous espérons vous revoir bientôt à Nice.\n"
        "Annick & Charley"
    )

def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS (modèles)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    today = datetime.today().date()
    demain = today + timedelta(days=1)
    hier = today - timedelta(days=1)

    colA, colB = st.columns(2)

    with colA:
        st.subheader("📆 Arrivées demain")
        arrives = df[pd.to_datetime(df["date_arrivee"], errors="coerce").dt.date == demain]
        if arrives.empty:
            st.info("Aucune arrivée demain.")
        else:
            for _, r in arrives.iterrows():
                body = sms_message_arrivee(r)
                tel = normalize_tel(r.get("telephone"))
                st.markdown(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}")
                st.code(body)
                if tel and body:
                    st.link_button(f"📩 SMS à {tel}", f"sms:{tel}?&body={quote(body)}")

    with colB:
        st.subheader("🕒 Relance +24h après départ")
        dep_24h = df[pd.to_datetime(df["date_depart"], errors="coerce").dt.date == hier]
        if dep_24h.empty:
            st.info("Aucun départ hier.")
        else:
            for _, r in dep_24h.iterrows():
                body = sms_message_depart(r)
                tel = normalize_tel(r.get("telephone"))
                st.markdown(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}")
                st.code(body)
                if tel and body:
                    st.link_button(f"📩 SMS à {tel}", f"sms:{tel}?&body={quote(body)}")


# =========================
# Sidebar : gestion palette (ajout/suppression)
# =========================
def sidebar_palette():
    st.sidebar.markdown("---")
    st.sidebar.subheader("🎨 Plateformes")
    with st.sidebar.form("palette_form"):
        nom = st.text_input("Nom nouvelle plateforme")
        colp = st.color_picker("Couleur", "#9b59b6")
        add = st.form_submit_button("Ajouter / Mettre à jour")
        if add and nom.strip():
            PALETTE[nom.strip()] = colp
            try:
                sauvegarder_palette(PALETTE)
                st.sidebar.success(f"Plateforme « {nom.strip()} » enregistrée.")
            except Exception as e:
                st.sidebar.error(f"Erreur sauvegarde palette : {e}")

    # liste & suppression
    for pf in sorted(PALETTE.keys()):
        c1, c2 = st.sidebar.columns([4,1])
        c1.markdown(f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{PALETTE[pf]};border-radius:3px;margin-right:6px;"></span>{pf}', unsafe_allow_html=True)
        if c2.button("🗑", key=f"del_pf_{pf}"):
            try:
                del PALETTE[pf]
                sauvegarder_palette(PALETTE)
                st.sidebar.success(f"Supprimé: {pf}")
                st.experimental_rerun()
            except Exception as e:
                st.sidebar.error(f"Erreur : {e}")


# =========================
# Main
# =========================
def main():
    st.sidebar.title("📁 Fichier")
    df = charger_donnees()
    # Téléchargement rapide du fichier actuel
    st.sidebar.download_button(
        "💾 Télécharger Excel courant",
        data=df.to_excel(index=False, engine="openpyxl") if False else b"",  # désactivé (Streamlit n'aime pas to_excel direct)
        file_name="reservations.xlsx",
        disabled=True,
        help="Utilisez plutôt le bouton « 💾 Sauvegarder le fichier Excel » dans l’onglet Réservations."
    )

    sidebar_palette()

    st.sidebar.title("🧭 Navigation")
    onglet = st.sidebar.radio(
        "Aller à",
        ["📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer","📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS"]
    )

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
    elif onglet == "✉️ SMS":
        vue_sms(df)


if __name__ == "__main__":
    main()