# app.py — Villa Tobias (COMPLET, prêt à l’emploi)

import streamlit as st
import pandas as pd
import numpy as np
import calendar
from datetime import date, timedelta, datetime, timezone
from io import BytesIO
import hashlib
import os

# ----------------- Config -----------------
st.set_page_config(page_title="📖 Réservations Villa Tobias", layout="wide")
FICHIER = "reservations.xlsx"
HEAD_RES = "Reservations"
HEAD_PLAT = "Plateformes"

DEFAULT_PLATEFORMES = [
    {"plateforme": "Booking", "couleur": "#1e90ff"},
    {"plateforme": "Airbnb",  "couleur": "#e74c3c"},
    {"plateforme": "Autre",   "couleur": "#f59e0b"},
]

BASE_COLS = [
    "paye","nom_client","sms_envoye","plateforme","telephone",
    "date_arrivee","date_depart","nuitees",
    "prix_brut","commissions","frais_cb","prix_net",
    "menage","taxes_sejour","base","charges","%",
    "AAAA","MM","ical_uid"
]

# ----------------- Utils -----------------
def _to_date(x):
    if pd.isna(x) or x is None: return None
    try: return pd.to_datetime(x).date()
    except: return None

def _fmt(d): return d.strftime("%Y/%m/%d") if isinstance(d, date) else ""

def _norm_tel(x):
    if x is None or (isinstance(x, float) and np.isnan(x)): return ""
    s=str(x).strip().replace(" ","")
    if s.endswith(".0"): s=s[:-2]
    return s

def ensure_schema(df: pd.DataFrame)->pd.DataFrame:
    if df is None: df=pd.DataFrame()
    df=df.copy()
    for c in BASE_COLS:
        if c not in df.columns: df[c]=np.nan
    df["paye"]=df["paye"].fillna(False).astype(bool)
    df["sms_envoye"]=df["sms_envoye"].fillna(False).astype(bool)
    for c in ["date_arrivee","date_depart"]: df[c]=df[c].apply(_to_date)
    df["telephone"]=df["telephone"].apply(_norm_tel)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%","nuitees"]:
        df[c]=pd.to_numeric(df[c],errors="coerce")
    df["nuitees"]=[(d2-d1).days if isinstance(d1,date) and isinstance(d2,date) else np.nan for d1,d2 in zip(df["date_arrivee"],df["date_depart"])]
    df["AAAA"]=df["date_arrivee"].apply(lambda d: d.year if isinstance(d,date) else np.nan).astype("Int64")
    df["MM"]=df["date_arrivee"].apply(lambda d: d.month if isinstance(d,date) else np.nan).astype("Int64")
    for c in ["nom_client","plateforme","ical_uid"]: df[c]=df[c].fillna("")
    for c in ["prix_brut","commissions","frais_cb","menage","taxes_sejour"]: df[c]=df[c].fillna(0.0)
    df["prix_net"]=(df["prix_brut"]-df["commissions"]-df["frais_cb"]).clip(lower=0)
    df["base"]=(df["prix_net"]-df["menage"]-df["taxes_sejour"]).clip(lower=0)
    df["charges"]=(df["prix_brut"]-df["prix_net"]).clip(lower=0)
    with pd.option_context("mode.use_inf_as_na",True): df["%"]=(df["charges"]/df["prix_brut"]*100).fillna(0)
    for c in ["prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour","base","charges","%"]:
        df[c]=df[c].round(2)
    ordered=[c for c in BASE_COLS if c in df.columns]
    rest=[c for c in df.columns if c not in ordered]
    return df[ordered+rest]

def sort_core(df: pd.DataFrame)->pd.DataFrame:
    if df is None or df.empty: return df
    by=[c for c in ["date_arrivee","nom_client"] if c in df.columns]
    return df.sort_values(by=by, na_position="last").reset_index(drop=True)

def palette_to_dict(dfp: pd.DataFrame)->dict:
    if dfp is None or dfp.empty:
        return {r["plateforme"]: r["couleur"] for r in DEFAULT_PLATEFORMES}
    out={}
    for _,r in dfp.iterrows():
        nom=str(r.get("plateforme") or "").strip()
        col=str(r.get("couleur") or "").strip()
        if nom and col.startswith("#"):
            out[nom]=col
    return out

# ----------------- Excel I/O -----------------
def _create_if_missing():
    if os.path.exists(FICHIER): return
    dfp = pd.DataFrame(DEFAULT_PLATEFORMES)
    dfr = ensure_schema(pd.DataFrame(columns=BASE_COLS))
    with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
        dfr.to_excel(w, index=False, sheet_name=HEAD_RES)
        dfp.to_excel(w, index=False, sheet_name=HEAD_PLAT)

@st.cache_data(show_spinner=False)
def _read_workbook_cached(path:str, mtime:float):
    xl = pd.ExcelFile(path, engine="openpyxl")
    dfr = xl.parse(HEAD_RES) if HEAD_RES in xl.sheet_names else pd.DataFrame(columns=BASE_COLS)
    dfp = xl.parse(HEAD_PLAT) if HEAD_PLAT in xl.sheet_names else pd.DataFrame(DEFAULT_PLATEFORMES)
    return ensure_schema(dfr), dfp[["plateforme","couleur"]]

def charger_donnees():
    _create_if_missing()
    try:
        m=os.path.getmtime(FICHIER)
        dfr, dfp = _read_workbook_cached(FICHIER, m)
        return dfr, dfp
    except Exception as e:
        st.error(f"Erreur de lecture Excel : {e}")
        return ensure_schema(pd.DataFrame()), pd.DataFrame(DEFAULT_PLATEFORMES)

def sauvegarder(dfr: pd.DataFrame, dfp: pd.DataFrame):
    try:
        with pd.ExcelWriter(FICHIER, engine="openpyxl") as w:
            ensure_schema(dfr).to_excel(w, index=False, sheet_name=HEAD_RES)
            dfp[["plateforme","couleur"]].to_excel(w, index=False, sheet_name=HEAD_PLAT)
        st.cache_data.clear()
        st.success("💾 Sauvegarde effectuée.")
    except Exception as e:
        st.error(f"Échec de sauvegarde : {e}")

# ----------------- Widgets communs -----------------
def bouton_telecharger(dfr):
    buf=BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as w:
        ensure_schema(dfr).to_excel(w, index=False, sheet_name=HEAD_RES)
        pd.DataFrame(DEFAULT_PLATEFORMES).to_excel(w, index=False, sheet_name=HEAD_PLAT)
    st.sidebar.download_button("💾 Télécharger un modèle", data=buf.getvalue(),
        file_name="reservations_modele.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

def bouton_restaurer():
    up = st.sidebar.file_uploader("📤 Restaurer (XLSX)", type=["xlsx"])
    if up is not None and st.sidebar.button("Restaurer maintenant"):
        try:
            raw = up.read()
            if not raw: raise ValueError("Fichier vide")
            dfr, dfp = None, None
            xl = pd.ExcelFile(BytesIO(raw), engine="openpyxl")
            dfr = xl.parse(HEAD_RES) if HEAD_RES in xl.sheet_names else pd.DataFrame(columns=BASE_COLS)
            dfp = xl.parse(HEAD_PLAT) if HEAD_PLAT in xl.sheet_names else pd.DataFrame(DEFAULT_PLATEFORMES)
            sauvegarder(dfr, dfp)
            st.experimental_rerun()
        except Exception as e:
            st.sidebar.error(f"Erreur import : {e}")

def kpi(df):
    core=df.copy()
    b=core["prix_brut"].sum()
    ch=(core["commissions"].sum()+core["frais_cb"].sum())
    n=core["prix_net"].sum()
    base=core["base"].sum()
    nuits=int(core["nuitees"].sum() or 0)
    pct=(ch/b*100) if b else 0
    pm=(b/nuits) if nuits else 0
    st.markdown(
        f"""
        <div style="display:flex;gap:8px;flex-wrap:wrap">
        <div style="padding:8px 10px;border:1px solid #777;border-radius:8px;background:rgba(127,127,127,.1)"><b>Total Brut</b><div>{b:,.2f} €</div></div>
        <div style="padding:8px 10px;border:1px solid #777;border-radius:8px;background:rgba(127,127,127,.1)"><b>Total Net</b><div>{n:,.2f} €</div></div>
        <div style="padding:8px 10px;border:1px solid #777;border-radius:8px;background:rgba(127,127,127,.1)"><b>Total Base</b><div>{base:,.2f} €</div></div>
        <div style="padding:8px 10px;border:1px solid #777;border-radius:8px;background:rgba(127,127,127,.1)"><b>Total Charges</b><div>{ch:,.2f} €</div></div>
        <div style="padding:8px 10px;border:1px solid #777;border-radius:8px;background:rgba(127,127,127,.1)"><b>Nuitées</b><div>{nuits}</div></div>
        <div style="padding:8px 10px;border:1px solid #777;border-radius:8px;background:rgba(127,127,127,.1)"><b>Commission moy.</b><div>{pct:.2f} %</div></div>
        <div style="padding:8px 10px;border:1px solid #777;border-radius:8px;background:rgba(127,127,127,.1)"><b>Prix moyen/nuit</b><div>{pm:,.2f} €</div></div>
        </div>
        """, unsafe_allow_html=True
    )

# ----------------- Vues -----------------
def vue_plateformes(dfp):
    st.title("🎨 Plateformes")
    st.caption("Ajouter / modifier / supprimer, puis **Enregistrer**.")
    grid = st.data_editor(
        dfp.rename(columns={"plateforme":"Plateforme","couleur":"Couleur"}),
        use_container_width=True, num_rows="dynamic",
        column_config={
            "Plateforme": st.column_config.TextColumn(required=True),
            "Couleur": st.column_config.TextColumn(help="Hex (#RRGGBB)", required=True),
        }
    )
    c1,c2=st.columns(2)
    if c1.button("💾 Enregistrer plateformes"):
        clean=grid.rename(columns={"Plateforme":"plateforme","Couleur":"couleur"})
        sauvegarder(charger_donnees()[0], clean)
        st.experimental_rerun()
    if c2.button("↩️ Réinitialiser palette par défaut"):
        sauvegarder(charger_donnees()[0], pd.DataFrame(DEFAULT_PLATEFORMES))
        st.experimental_rerun()

def vue_reservations(dfr, dfp):
    st.title("📋 Réservations")
    pal = palette_to_dict(dfp)

    with st.expander("🎛️ Options", expanded=True):
        filtre = st.selectbox("Filtrer payé", ["Tous","Payé","Non payé"])
        show_k = st.checkbox("Afficher les KPI", True)
        do_search = st.checkbox("Activer la recherche", True)

    st.markdown("### Plateformes")
    st.markdown(" &nbsp;&nbsp;".join([
        f"<span style='display:inline-block;width:0.9em;height:0.9em;background:{pal[p]};border-radius:3px;margin-right:6px;vertical-align:-0.1em'></span>{p}"
        for p in sorted(pal.keys())
    ]), unsafe_allow_html=True)

    df = ensure_schema(dfr)
    if filtre=="Payé": df=df[df["paye"]==True]
    elif filtre=="Non payé": df=df[df["paye"]==False]

    if show_k: kpi(df)

    if do_search:
        q = st.text_input("🔎 Recherche (nom, plateforme, téléphone…)", "")
        if q:
            ql=q.lower().strip()
            def _m(v): 
                s="" if pd.isna(v) else str(v)
                return ql in s.lower()
            mask = df["nom_client"].apply(_m) | df["plateforme"].apply(_m) | df["telephone"].apply(_m)
            df = df[mask]

    core = sort_core(df)
    core_edit = core.copy()
    core_edit["__id"]=core_edit.index
    for c in ["date_arrivee","date_depart"]: core_edit[c]=core_edit[c].apply(_fmt)

    show_cols = [c for c in [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net","menage","taxes_sejour",
        "base","charges","%","AAAA","MM","__id"
    ] if c in core_edit.columns]

    edited = st.data_editor(
        core_edit[show_cols], use_container_width=True, hide_index=True,
        column_config={
            "paye": st.column_config.CheckboxColumn("Payé"),
            "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
            "__id": st.column_config.Column("id", disabled=True, width="small"),
        }
    )
    if st.button("💾 Enregistrer les cases cochées"):
        for _,r in edited.iterrows():
            rid=int(r["__id"])
            dfr.at[rid,"paye"]=bool(r.get("paye",False))
            dfr.at[rid,"sms_envoye"]=bool(r.get("sms_envoye",False))
        sauvegarder(dfr, dfp)
        st.success("✅ Statuts mis à jour.")
        st.experimental_rerun()

def vue_ajouter(dfr, dfp):
    st.title("➕ Ajouter une réservation")
    pal = palette_to_dict(dfp)
    def inline(label, widget, **kw):
        c1,c2=st.columns([1,2])
        with c1: st.markdown(f"**{label}**")
        with c2: return widget(label, label_visibility="collapsed", **kw)

    paye = inline("Payé", st.checkbox, value=False)
    nom  = inline("Nom", st.text_input, value="")
    sms  = inline("SMS envoyé", st.checkbox, value=False)
    tel  = inline("Téléphone (+33…)", st.text_input, value="")
    pf   = inline("Plateforme", st.selectbox, options=sorted(pal.keys()), index=0)
    arr  = inline("Arrivée", st.date_input, value=date.today())
    dep  = inline("Départ", st.date_input, value=arr+timedelta(days=2), min_value=arr+timedelta(days=1))
    brut = inline("Prix brut (€)", st.number_input, min_value=0.0, step=1.0, format="%.2f")
    comm = inline("Commissions (€)", st.number_input, min_value=0.0, step=1.0, format="%.2f")
    cb   = inline("Frais CB (€)", st.number_input, min_value=0.0, step=1.0, format="%.2f")
    net  = max(brut-comm-cb, 0.0)
    men  = inline("Ménage (€)", st.number_input, min_value=0.0, step=1.0, format="%.2f")
    tax  = inline("Taxes séjour (€)", st.number_input, min_value=0.0, step=1.0, format="%.2f")
    base = max(net-men-tax, 0.0); ch=max(brut-net,0.0); pct=(ch/brut*100) if brut>0 else 0.0

    st.info(f"Net: {net:.2f} € • Base: {base:.2f} € • %: {pct:.2f}")

    if st.button("Enregistrer"):
        if dep < arr+timedelta(days=1):
            st.error("Départ au moins le lendemain.")
            return
        row = {
            "paye": bool(paye), "nom_client": nom.strip(), "sms_envoye": bool(sms),
            "plateforme": pf, "telephone": _norm_tel(tel),
            "date_arrivee": arr, "date_depart": dep, "nuitees": (dep-arr).days,
            "prix_brut": float(brut), "commissions": float(comm), "frais_cb": float(cb),
            "prix_net": round(net,2), "menage": float(men), "taxes_sejour": float(tax),
            "base": round(base,2), "charges": round(ch,2), "%": round(pct,2),
            "AAAA": arr.year, "MM": arr.month, "ical_uid": ""
        }
        dfr2 = pd.concat([dfr, pd.DataFrame([row])], ignore_index=True)
        sauvegarder(dfr2, dfp)
        st.success("✅ Ajouté.")
        st.experimental_rerun()

def vue_modifier(dfr, dfp):
    st.title("✏️ Modifier / Supprimer")
    if dfr.empty:
        st.info("Aucune réservation."); return
    df = ensure_schema(dfr)
    df["ident"] = df["nom_client"].astype(str)+" | "+df["date_arrivee"].apply(_fmt)
    choix = st.selectbox("Choisir une réservation", df["ident"])
    i = df.index[df["ident"]==choix][0]

    pal = palette_to_dict(dfp)
    c0,c1,c2 = st.columns(3)
    paye = c0.checkbox("Payé", value=bool(df.at[i,"paye"]))
    nom = c1.text_input("Nom", value=df.at[i,"nom_client"])
    sms = c2.checkbox("SMS envoyé", value=bool(df.at[i,"sms_envoye"]))
    c3,c4 = st.columns(2)
    tel = c3.text_input("Téléphone", _norm_tel(df.at[i,"telephone"]))
    pf = c4.selectbox("Plateforme", options=sorted(pal.keys()), index=list(sorted(pal.keys())).index(df.at[i,"plateforme"]) if df.at[i,"plateforme"] in pal else 0)
    arr = st.date_input("Arrivée", value=df.at[i,"date_arrivee"] or date.today())
    dep = st.date_input("Départ", value=df.at[i,"date_depart"] or (arr+timedelta(days=1)), min_value=arr+timedelta(days=1))
    d1,d2,d3 = st.columns(3)
    brut = d1.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i,"prix_brut"] or 0), step=1.0, format="%.2f")
    comm = d2.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i,"commissions"] or 0), step=1.0, format="%.2f")
    cb   = d3.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i,"frais_cb"] or 0), step=1.0, format="%.2f")
    net = max(brut-comm-cb,0.0)
    e1,e2 = st.columns(2)
    men = e1.number_input("Ménage (€)", min_value=0.0, value=float(df.at[i,"menage"] or 0), step=1.0, format="%.2f")
    tax = e2.number_input("Taxes séjour (€)", min_value=0.0, value=float(df.at[i,"taxes_sejour"] or 0), step=1.0, format="%.2f")
    base=max(net-men-tax,0.0); ch=max(brut-net,0.0); pct=(ch/brut*100) if brut>0 else 0.0
    st.caption(f"Net {net:.2f} • Base {base:.2f} • % {pct:.2f}")

    b1,b2 = st.columns(2)
    if b1.button("💾 Enregistrer"):
        df.at[i,"paye"]=bool(paye); df.at[i,"nom_client"]=nom.strip(); df.at[i,"sms_envoye"]=bool(sms)
        df.at[i,"plateforme"]=pf; df.at[i,"telephone"]=_norm_tel(tel)
        df.at[i,"date_arrivee"]=arr; df.at[i,"date_depart"]=dep; df.at[i,"nuitees"]=(dep-arr).days
        df.at[i,"prix_brut"]=float(brut); df.at[i,"commissions"]=float(comm); df.at[i,"frais_cb"]=float(cb)
        df.at[i,"prix_net"]=round(net,2); df.at[i,"menage"]=float(men); df.at[i,"taxes_sejour"]=float(tax)
        df.at[i,"base"]=round(base,2); df.at[i,"charges"]=round(ch,2); df.at[i,"%"]=round(pct,2)
        sauvegarder(df.drop(columns=["ident"]), dfp)
        st.success("✅ Modifié.")
        st.experimental_rerun()
    if b2.button("🗑 Supprimer"):
        df2 = df.drop(index=i).drop(columns=["ident"])
        sauvegarder(df2, dfp); st.warning("Supprimé."); st.experimental_rerun()

def vue_calendrier(dfr, dfp):
    st.title("📅 Calendrier (barres style Agenda)")
    df = ensure_schema(dfr)
    pal = palette_to_dict(dfp)
    if df.empty: st.info("Aucune donnée."); return

    c1,c2 = st.columns(2)
    mois_nom = c1.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annee = c2.number_input("Année", min_value=2020, max_value=2100, value=date.today().year)
    month = list(calendar.month_name).index(mois_nom)

    cal = calendar.Calendar(firstweekday=0)  # Lundi=0
    days = list(cal.itermonthdates(int(annee), month))
    weeks = [days[i:i+7] for i in range(0, len(days), 7)]

    # Map jour -> [(nom, pf)]
    events_by_day = {}
    for _, r in df.iterrows():
        d1, d2 = r.get("date_arrivee"), r.get("date_depart")
        if not (isinstance(d1,date) and isinstance(d2,date)): continue
        cur = d1
        while cur < d2:
            if cur.month==month and cur.year==annee:
                events_by_day.setdefault(cur, []).append((str(r.get("nom_client") or ""), str(r.get("plateforme") or "")))
            cur += timedelta(days=1)

    st.markdown("""
        <style>
        .cal {border-collapse:collapse; width:100%}
        .cal th,.cal td{border:1px solid #555; vertical-align:top; height:90px; width:14%}
        .daynum{font-size:.8rem; color:#999; text-align:right}
        .bar{margin-top:2px; padding:1px 4px; font-size:.72rem; border-radius:3px;
             color:#fff; white-space:nowrap; overflow:hidden; text-overflow:ellipsis}
        </style>
    """, unsafe_allow_html=True)

    html = "<table class='cal'>"
    html += "<tr>" + "".join(f"<th>{d}</th>" for d in ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]) + "</tr>"
    for week in weeks:
        html += "<tr>"
        for d in week:
            daynum = f"<div class='daynum'>{d.day}</div>" if d.month==month else ""
            bars = ""
            for nom, pf in events_by_day.get(d, []):
                color = pal.get(pf, "#666")
                bars += f"<div class='bar' style='background:{color}'>{nom}</div>"
            html += f"<td>{daynum}{bars}</td>"
        html += "</tr>"
    html += "</table>"
    st.markdown(html, unsafe_allow_html=True)

def vue_rapport(dfr):
    st.title("📊 Rapport")
    df = ensure_schema(dfr)
    if df.empty: st.info("Aucune donnée."); return
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    a = st.selectbox("Année", annees, index=len(annees)-1) if annees else date.today().year
    pfopt = ["Toutes"] + sorted(df["plateforme"].dropna().unique().tolist())
    pf = st.selectbox("Plateforme", pfopt)
    mois = st.selectbox("Mois", ["Tous"]+[f"{i:02d}" for i in range(1,13)])

    dat = df[df["AAAA"]==int(a)].copy()
    if pf!="Toutes": dat=dat[dat["plateforme"]==pf]
    if mois!="Tous": dat=dat[dat["MM"]==int(mois)]
    if dat.empty: st.info("Aucune donnée pour ces filtres."); return

    show=dat.copy()
    for c in ["date_arrivee","date_depart"]: show[c]=show[c].apply(_fmt)
    cols=[c for c in ["nom_client","plateforme","date_arrivee","date_depart","nuitees","prix_brut","prix_net","base"] if c in show.columns]
    st.dataframe(show[cols], use_container_width=True)

    st.bar_chart(dat.groupby("MM")["prix_brut"].sum())

def _ics_escape(s:str)->str:
    return (s or "").replace("\\","\\\\").replace(";","\\;").replace(",","\\,").replace("\n","\\n")
def _fmt_ics(d:date)->str: return d.strftime("%Y%m%d")
def _uid(row)->str:
    base=f"{row.get('nom_client')}|{row.get('plateforme')}|{row.get('date_arrivee')}|{row.get('date_depart')}|{row.get('telephone')}"
    h=hashlib.sha1(base.encode()).hexdigest()
    return f"vt-{h}@villatobias"

def vue_export_ics(dfr):
    st.title("📤 Export ICS")
    df = ensure_schema(dfr)
    if df.empty: st.info("Aucune donnée."); return
    an = st.selectbox("Année", ["Toutes"]+sorted([int(x) for x in df["AAAA"].dropna().unique()]))
    mo = st.selectbox("Mois", ["Tous"]+list(range(1,13)))
    pf = st.selectbox("Plateforme", ["Toutes"]+sorted(df["plateforme"].dropna().unique().tolist()))
    data=df.copy()
    if an!="Toutes": data=data[data["AAAA"]==int(an)]
    if mo!="Tous": data=data[data["MM"]==int(mo)]
    if pf!="Toutes": data=data[data["plateforme"]==pf]
    if data.empty: st.info("Aucune réservation pour ces filtres."); return
    lines=["BEGIN:VCALENDAR","VERSION:2.0","PRODID:-//Villa Tobias//Reservations//FR","CALSCALE:GREGORIAN","METHOD:PUBLISH"]
    for _,r in data.iterrows():
        d1=r.get("date_arrivee"); d2=r.get("date_depart")
        if not (isinstance(d1,date) and isinstance(d2,date)): continue
        summary=_ics_escape(" - ".join([x for x in [str(r.get('plateforme') or ''), str(r.get('nom_client') or ''), str(r.get('telephone') or '')] if x]))
        desc=_ics_escape(f"Client: {r.get('nom_client')}\nPlateforme: {r.get('plateforme')}\nTel: {r.get('telephone')}")
        uid=_ics_escape(_uid(r))
        lines += ["BEGIN:VEVENT", f"UID:{uid}", f"DTSTART;VALUE=DATE:{_fmt_ics(d1)}", f"DTEND;VALUE=DATE:{_fmt_ics(d2)}", f"SUMMARY:{summary}", f"DESCRIPTION:{desc}", "END:VEVENT"]
    lines.append("END:VCALENDAR")
    st.download_button("⬇️ reservations.ics", data=("\r\n".join(lines)+"\r\n").encode("utf-8"), file_name="reservations.ics", mime="text/calendar")

def sms_arrivee(row):
    d1=row.get("date_arrivee"); d2=row.get("date_depart")
    d1s=_fmt(d1); d2s=_fmt(d2); n=int(row.get("nuitees") or ((d2-d1).days if isinstance(d1,date) and isinstance(d2,date) else 0))
    return (f"VILLA TOBIAS\nPlateforme : {row.get('plateforme','')}\n"
            f"Arrivée : {d1s}  Départ : {d2s}  Nuitées : {n}\n\n"
            f"Bonjour {row.get('nom_client','')}\nTéléphone : {row.get('telephone','')}\n\n"
            "Bienvenue ! Check-in 14h, check-out 11h. Merci de nous communiquer votre heure d'arrivée.\nAnnick & Charley")

def sms_depart(row):
    return (f"Bonjour {row.get('nom_client','')},\n\n"
            "Merci d’avoir choisi notre appartement. Au plaisir de vous revoir !\nAnnick & Charley")

def vue_sms(dfr):
    st.title("✉️ SMS (manuel)")
    df=ensure_schema(dfr)
    if df.empty: st.info("Aucune donnée."); return
    pick=df.copy()
    pick["id_aff"]=pick["nom_client"].astype(str)+" | "+pick["plateforme"].astype(str)+" | "+pick["date_arrivee"].apply(_fmt)
    choix=st.selectbox("Choisir une réservation", pick["id_aff"])
    r=pick.loc[pick["id_aff"]==choix].iloc[0]
    mod=st.radio("Modèle",["Arrivée","Départ","Libre"],horizontal=True)
    if mod=="Arrivée": txt=sms_arrivee(r)
    elif mod=="Départ": txt=sms_depart(r)
    else: txt=st.text_area("Votre message", value="", height=160)
    st.code(txt or "—")

# ----------------- Main -----------------
def main():
    st.sidebar.title("📁 Fichier")
    dfr, dfp = charger_donnees()
    bouton_telecharger(dfr)
    bouton_restaurer()

    st.sidebar.title("🧭 Navigation")
    page = st.sidebar.radio("Aller à", [
        "📋 Réservations","➕ Ajouter","✏️ Modifier / Supprimer",
        "🎨 Plateformes","📅 Calendrier","📊 Rapport","👥 Liste clients","📤 Export ICS","✉️ SMS"
    ])

    if page=="📋 Réservations": vue_reservations(dfr, dfp)
    elif page=="➕ Ajouter":     vue_ajouter(dfr, dfp)
    elif page=="✏️ Modifier / Supprimer": vue_modifier(dfr, dfp)
    elif page=="🎨 Plateformes": vue_plateformes(dfp)
    elif page=="📅 Calendrier":  vue_calendrier(dfr, dfp)
    elif page=="📊 Rapport":     vue_rapport(dfr)
    elif page=="👥 Liste clients":
        st.title("👥 Liste clients")
        show=ensure_schema(dfr).copy()
        for c in ["date_arrivee","date_depart"]: show[c]=show[c].apply(_fmt)
        cols=[c for c in ["paye","nom_client","sms_envoye","plateforme","telephone","date_arrivee","date_depart","nuitees","prix_brut","prix_net","base"] if c in show.columns]
        st.dataframe(show[cols], use_container_width=True)
        st.download_button("📥 CSV", data=show[cols].to_csv(index=False).encode("utf-8"), file_name="clients.csv", mime="text/csv")
    elif page=="📤 Export ICS":  vue_export_ics(dfr)
    elif page=="✉️ SMS":         vue_sms(dfr)

if __name__=="__main__":
    main()