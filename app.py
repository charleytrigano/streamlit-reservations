# app.py — Villa Tobias (COMPLET avec ajout / modification / suppression)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os
from urllib.parse import quote
import colorsys

FICHIER = "reservations.xlsx"

# ==============================  PAGE CONFIG  ==============================
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")

# ==============================  PALETTE (PLATEFORMES) ==============================

DEFAULT_PALETTE = {
    "Booking": "#1e90ff",
    "Airbnb":  "#e74c3c",
    "Autre":   "#f59e0b",
}

def get_palette() -> dict:
    if "palette" not in st.session_state:
        st.session_state.palette = DEFAULT_PALETTE.copy()
    return st.session_state.palette

def save_palette(palette: dict):
    st.session_state.palette = palette

def platform_badge(name: str, palette: dict) -> str:
    color = palette.get(name, "#999999")
    return f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{color};border-radius:3px;margin-right:6px;"></span>{name}'

# ==============================  OUTILS  ==============================

def to_date_only(x):
    if pd.isna(x) or x is None:
        return None
    try:
        return pd.to_datetime(x).date()
    except Exception:
        return None

def normalize_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return ""
    s = str(x).strip().replace(" ", "")
    if s.endswith(".0"):
        s = s[:-2]
    return s

BASE_COLS = [
    "paye","nom_client","sms_envoye","plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%","AAAA","MM"
]

def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    if df is None:
        df = pd.DataFrame()
    for c in BASE_COLS:
        if c not in df.columns:
            df[c] = np.nan
    df["paye"] = df["paye"].fillna(False).astype(bool)
    df["sms_envoye"] = df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee","date_depart"]:
        df[c] = df[c].apply(to_date_only)
    df["telephone"] = df["telephone"].apply(normalize_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    if "date_arrivee" in df and "date_depart" in df:
        df["nuitees"] = [(d2-d1).days if isinstance(d1,date) and isinstance(d2,date) else np.nan for d1,d2 in zip(df["date_arrivee"],df["date_depart"])]
    if "date_arrivee" in df:
        df["AAAA"] = df["date_arrivee"].apply(lambda d: d.year if isinstance(d,date) else np.nan).astype("Int64")
        df["MM"]   = df["date_arrivee"].apply(lambda d: d.month if isinstance(d,date) else np.nan).astype("Int64")
    df["prix_net"] = (df["prix_brut"].fillna(0)-df["commissions"].fillna(0)-df["frais_cb"].fillna(0)).clip(lower=0)
    df["base"]     = (df["prix_net"].fillna(0)-df["menage"].fillna(0)-df["taxes_sejour"].fillna(0)).clip(lower=0)
    df["charges"]  = (df["prix_brut"].fillna(0)-df["prix_net"].fillna(0)).clip(lower=0)
    df["%"]        = (df["charges"]/df["prix_brut"]*100).fillna(0)
    return df

# ==============================  EXCEL I/O  ==============================

def charger_donnees() -> pd.DataFrame:
    if not os.path.exists(FICHIER):
        return ensure_schema(pd.DataFrame())
    return ensure_schema(pd.read_excel(FICHIER, engine="openpyxl", converters={"telephone":normalize_tel}))

def sauvegarder_donnees(df: pd.DataFrame):
    df = ensure_schema(df)
    with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
        df.to_excel(w, index=False, sheet_name="Sheet1")
    st.success("💾 Sauvegarde effectuée")

# ==============================  KPI  ==============================

def kpi_chips(df: pd.DataFrame):
    if df.empty: return
    b = df["prix_brut"].sum()
    n = df["prix_net"].sum()
    base = df["base"].sum()
    ch = df["charges"].sum()
    nuits = df["nuitees"].sum()
    pct = (ch/b*100) if b else 0
    pm_nuit = (b/nuits) if nuits else 0
    st.markdown(f"""
    <div style="display:flex;gap:10px;flex-wrap:wrap">
      <div><b>Total Brut</b><br>{b:,.2f} €</div>
      <div><b>Total Net</b><br>{n:,.2f} €</div>
      <div><b>Total Base</b><br>{base:,.2f} €</div>
      <div><b>Total Charges</b><br>{ch:,.2f} €</div>
      <div><b>Nuitées</b><br>{int(nuits)}</div>
      <div><b>Commission moy.</b><br>{pct:.2f} %</div>
      <div><b>Prix moyen/nuit</b><br>{pm_nuit:,.2f} €</div>
    </div>
    """, unsafe_allow_html=True)


# ==============================  VUES  ==============================

def vue_reservations(df: pd.DataFrame):
    st.title("📋 Réservations")

    show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
    if show_kpi: kpi_chips(df)

    st.subheader("Liste des réservations")
    st.dataframe(df, use_container_width=True)

    st.markdown("### ➕ Ajouter une réservation")
    with st.form("add_resa"):
        nom = st.text_input("Nom du client")
        plateforme = st.selectbox("Plateforme", list(get_palette().keys()))
        tel = st.text_input("Téléphone")
        d1 = st.date_input("Date arrivée", value=date.today())
        d2 = st.date_input("Date départ", value=date.today()+timedelta(days=1))
        brut = st.number_input("Prix brut", 0.0)
        comm = st.number_input("Commission", 0.0)
        cb   = st.number_input("Frais CB", 0.0)
        men  = st.number_input("Ménage", 0.0)
        tax  = st.number_input("Taxes séjour", 0.0)
        ok = st.form_submit_button("Ajouter")
        if ok:
            new_row = {
                "paye":False,"sms_envoye":False,
                "nom_client":nom,"plateforme":plateforme,"telephone":tel,
                "date_arrivee":d1,"date_depart":d2,
                "prix_brut":brut,"commissions":comm,"frais_cb":cb,
                "menage":men,"taxes_sejour":tax
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            sauvegarder_donnees(df)
            st.success("✅ Réservation ajoutée")
            st.rerun()

    st.markdown("### ✏️ Modifier / ❌ Supprimer")
    if not df.empty:
        idx = st.number_input("Numéro de ligne", 0, len(df)-1, 0)
        sel = df.iloc[idx]
        st.write("Sélection :", sel["nom_client"], sel["date_arrivee"], "-", sel["date_depart"])
        c1,c2 = st.columns(2)
        if c1.button("✏️ Modifier"):
            with st.form("edit_resa"):
                nom = st.text_input("Nom", sel["nom_client"])
                plateforme = st.selectbox("Plateforme", list(get_palette().keys()), index=list(get_palette().keys()).index(sel["plateforme"]))
                tel = st.text_input("Téléphone", sel["telephone"])
                d1 = st.date_input("Arrivée", sel["date_arrivee"])
                d2 = st.date_input("Départ", sel["date_depart"])
                brut = st.number_input("Brut", 0.0, value=float(sel["prix_brut"]))
                comm = st.number_input("Commission", 0.0, value=float(sel["commissions"]))
                cb   = st.number_input("Frais CB", 0.0, value=float(sel["frais_cb"]))
                men  = st.number_input("Ménage", 0.0, value=float(sel["menage"]))
                tax  = st.number_input("Taxes", 0.0, value=float(sel["taxes_sejour"]))
                ok = st.form_submit_button("Enregistrer")
                if ok:
                    df.at[idx,"nom_client"]=nom
                    df.at[idx,"plateforme"]=plateforme
                    df.at[idx,"telephone"]=tel
                    df.at[idx,"date_arrivee"]=d1
                    df.at[idx,"date_depart"]=d2
                    df.at[idx,"prix_brut"]=brut
                    df.at[idx,"commissions"]=comm
                    df.at[idx,"frais_cb"]=cb
                    df.at[idx,"menage"]=men
                    df.at[idx,"taxes_sejour"]=tax
                    sauvegarder_donnees(df)
                    st.success("✅ Réservation modifiée")
                    st.rerun()
        if c2.button("🗑 Supprimer"):
            df = df.drop(idx).reset_index(drop=True)
            sauvegarder_donnees(df)
            st.success("✅ Réservation supprimée")
            st.rerun()

# ==============================  CALENDRIER  ==============================

def vue_calendrier(df: pd.DataFrame):
    st.title("📅 Calendrier")
    if df.empty:
        st.info("Aucune réservation")
        return
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()))
    mois = st.selectbox("Mois", list(calendar.month_name)[1:], index=date.today().month-1)
    mois_idx = list(calendar.month_name).index(mois)
    cal = calendar.monthcalendar(int(annee), mois_idx)
    palette = get_palette()
    planning = {}
    for _,r in df.iterrows():
        d1, d2 = r["date_arrivee"], r["date_depart"]
        if isinstance(d1,date) and isinstance(d2,date):
            for j in pd.date_range(d1,d2-timedelta(days=1)):
                planning.setdefault(j.date(), []).append((r["nom_client"],r["plateforme"]))
    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    table = []
    for sem in cal:
        row=[]
        for j in sem:
            if j==0: row.append("")
            else:
                d=date(int(annee),mois_idx,j)
                items=planning.get(d,[])
                if items:
                    pf=items[0][1]; col=palette.get(pf,"#999")
                    content=f"<div style='background:{col};color:white;padding:2px'>{items[0][0]}</div>"
                    row.append(content)
                else: row.append(str(j))
        table.append(row)
    st.markdown("<style>td{min-width:120px;vertical-align:top;}</style>",unsafe_allow_html=True)
    st.write(pd.DataFrame(table,columns=headers).to_html(escape=False), unsafe_allow_html=True)

# ==============================  RAPPORT  ==============================

def vue_rapport(df: pd.DataFrame):
    st.title("📊 Rapport")
    if df.empty: st.info("Vide"); return
    annee = st.selectbox("Année", sorted(df["AAAA"].dropna().unique()))
    data = df[df["AAAA"]==annee]
    kpi_chips(data)
    st.dataframe(data, use_container_width=True)

# ==============================  SMS  ==============================

def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS")
    if df.empty: return st.info("Aucune donnée")
    for _,r in df.iterrows():
        st.text_area(f"SMS pour {r['nom_client']}",
        f"Bonjour {r['nom_client']},\nVotre séjour du {r['date_arrivee']} au {r['date_depart']} est confirmé.\nTéléphone: {r['telephone']}",
        height=120)

# ==============================  ICS EXPORT  ==============================

def vue_ics(df: pd.DataFrame):
    st.title("📤 Export ICS")
    if df.empty: return st.info("Aucune donnée")
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//FR"]
    for _,r in df.iterrows():
        if isinstance(r["date_arrivee"],date) and isinstance(r["date_depart"],date):
            lines+=["BEGIN:VEVENT",
                    f"SUMMARY:{r['nom_client']}",
                    f"DTSTART;VALUE=DATE:{r['date_arrivee'].strftime('%Y%m%d')}",
                    f"DTEND;VALUE=DATE:{r['date_depart'].strftime('%Y%m%d')}",
                    "END:VEVENT"]
    lines.append("END:VCALENDAR")
    st.download_button("Télécharger ICS","\n".join(lines),"reservations.ics")

# ==============================  MAIN ==============================

def main():
    df=charger_donnees()
    st.sidebar.title("🧭 Navigation")
    choix=st.sidebar.radio("Aller à",["📋 Réservations","📅 Calendrier","📊 Rapport","✉️ SMS","📤 Export ICS"])
    if choix=="📋 Réservations": vue_reservations(df)
    elif choix=="📅 Calendrier": vue_calendrier(df)
    elif choix=="📊 Rapport": vue_rapport(df)
    elif choix=="✉️ SMS": vue_sms(df)
    elif choix=="📤 Export ICS": vue_ics(df)

if __name__=="__main__":
    main()