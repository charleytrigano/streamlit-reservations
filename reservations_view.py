# reservations_view.py — Réservations (liste + ajouter + modifier/supprimer)

import streamlit as st
import pandas as pd
from datetime import date, timedelta
from io_utils import (
    ensure_schema, split_totals, sort_core, format_date_str, normalize_tel,
    sauvegarder_donnees, charger_donnees
)
from palette_utils import get_palette_dict, platform_badge

# ------- KPI -------
def kpi_chips(df: pd.DataFrame):
    core, _ = split_totals(df)
    if core.empty:
        return
    b = core["prix_brut"].sum()
    total_comm = core["commissions"].sum()
    total_cb   = core["frais_cb"].sum()
    ch = total_comm + total_cb
    n = core["prix_net"].sum()
    base = core["base"].sum()
    nuits = core["nuitees"].sum()
    pct = (ch / b * 100) if b else 0
    pm_nuit = (b / nuits) if nuits else 0
    html = f"""
    <style>.chips-wrap {{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 10px 0;}}
    .chip{{padding:8px 10px;border-radius:10px;background:rgba(127,127,127,.12);border:1px solid rgba(127,127,127,.25)}}
    .chip b{{display:block;margin-bottom:3px;font-size:.85rem;opacity:.8}}</style>
    <div class="chips-wrap">
      <div class="chip"><b>Total Brut</b>{b:,.2f} €</div>
      <div class="chip"><b>Total Net</b>{n:,.2f} €</div>
      <div class="chip"><b>Total Base</b>{base:,.2f} €</div>
      <div class="chip"><b>Total Charges</b>{ch:,.2f} €</div>
      <div class="chip"><b>Nuitées</b>{int(nuits) if pd.notna(nuits) else 0}</div>
      <div class="chip"><b>Commission moy.</b>{pct:.2f} %</div>
      <div class="chip"><b>Prix moyen/nuit</b>{pm_nuit:,.2f} €</div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

def search_box(df: pd.DataFrame) -> pd.DataFrame:
    q = st.text_input("🔎 Recherche (nom, plateforme, téléphone…)", "")
    if not q:
        return df
    ql = q.strip().lower()
    def _m(v): s = "" if pd.isna(v) else str(v); return ql in s.lower()
    mask = (df["nom_client"].apply(_m) | df["plateforme"].apply(_m) | df["telephone"].apply(_m))
    return df[mask].copy()

# ------- VUE LISTE -------
def vue_reservations(df: pd.DataFrame):
    palette = get_palette_dict()
    st.title("📋 Réservations")
    with st.expander("🎛️ Options d’affichage", expanded=True):
        filtre_paye = st.selectbox("Filtrer payé", ["Tous", "Payé", "Non payé"])
        show_kpi = st.checkbox("Afficher les totaux (KPI)", value=True)
        enable_search = st.checkbox("Activer la recherche", value=True)

    # badges plateforme
    st.markdown("### Plateformes")
    st.markdown(
        " &nbsp;&nbsp;".join([platform_badge(pf, palette) for pf in sorted(palette.keys())]),
        unsafe_allow_html=True
    )

    df = ensure_schema(df)
    if filtre_paye == "Payé":
        df = df[df["paye"] == True].copy()
    elif filtre_paye == "Non payé":
        df = df[df["paye"] == False].copy()

    if show_kpi: kpi_chips(df)
    if enable_search: df = search_box(df)

    core, totals = split_totals(df)
    core = sort_core(core)

    core_edit = core.copy()
    core_edit["__rowid"] = core_edit.index
    core_edit["date_arrivee"] = core_edit["date_arrivee"].apply(format_date_str)
    core_edit["date_depart"]  = core_edit["date_depart"].apply(format_date_str)

    cols_order = [
        "paye","nom_client","sms_envoye","plateforme","telephone",
        "date_arrivee","date_depart","nuitees",
        "prix_brut","commissions","frais_cb","prix_net",
        "menage","taxes_sejour","base","charges","%","AAAA","MM","__rowid"
    ]
    cols_show = [c for c in cols_order if c in core_edit.columns]

    edited = st.data_editor(
        core_edit[cols_show],
        use_container_width=True, hide_index=True,
        column_config={
            "paye": st.column_config.CheckboxColumn("Payé"),
            "sms_envoye": st.column_config.CheckboxColumn("SMS envoyé"),
            "__rowid": st.column_config.Column("id", disabled=True, width="small"),
        }
    )

    if st.button("💾 Enregistrer les cases cochées"):
        for _, r in edited.iterrows():
            ridx = int(r["__rowid"])
            core.at[ridx, "paye"] = bool(r.get("paye", False))
            core.at[ridx, "sms_envoye"] = bool(r.get("sms_envoye", False))
        new_df = pd.concat([core, totals], ignore_index=False).reset_index(drop=True)
        sauvegarder_donnees(new_df)
        st.success("✅ Statuts mis à jour.")
        st.rerun()

    if not totals.empty:
        show_tot = totals.copy()
        for c in ["date_arrivee","date_depart"]:
            show_tot[c] = show_tot[c].apply(format_date_str)
        st.caption("Lignes de totaux (non éditables) :")
        st.dataframe(show_tot, use_container_width=True, hide_index=True)

# ------- VUE AJOUT -------
def vue_ajouter(df: pd.DataFrame):
    st.title("➕ Ajouter une réservation")
    pal = get_palette_dict()
    def inline(label, widget, key=None, **kw):
        c1, c2 = st.columns([1,2]); c1.markdown(f"**{label}**"); return c2.__getattribute__(widget)(label, key=key, label_visibility="collapsed", **kw)

    paye = inline("Payé", "checkbox", key="add_paye", value=False)
    nom = inline("Nom", "text_input", key="add_nom", value="")
    sms_envoye = inline("SMS envoyé", "checkbox", key="add_sms", value=False)
    tel = inline("Téléphone (+33...)", "text_input", key="add_tel", value="")
    pf_opts = sorted(pal.keys())
    pf_idx = pf_opts.index("Booking") if "Booking" in pf_opts else 0
    plateforme = inline("Plateforme", "selectbox", key="add_pf", options=pf_opts, index=pf_idx)
    arrivee = inline("Arrivée", "date_input", key="add_arrivee", value=date.today())
    min_dep = arrivee + timedelta(days=1)
    depart  = inline("Départ", "date_input", key="add_depart", value=min_dep, min_value=min_dep)
    brut = inline("Prix brut (€)", "number_input", key="add_brut", min_value=0.0, step=1.0, format="%.2f")
    commissions = inline("Commissions (€)", "number_input", key="add_comm", min_value=0.0, step=1.0, format="%.2f")
    frais_cb = inline("Frais CB (€)", "number_input", key="add_cb", min_value=0.0, step=1.0, format="%.2f")
    menage = inline("Ménage (€)", "number_input", key="add_menage", min_value=0.0, step=1.0, format="%.2f")
    taxes  = inline("Taxes séjour (€)", "number_input", key="add_taxes", min_value=0.0, step=1.0, format="%.2f")

    net_calc = max(float(brut) - float(commissions) - float(frais_cb), 0.0)
    base_calc = max(net_calc - float(menage) - float(taxes), 0.0)
    charges_calc = max(float(brut) - net_calc, 0.0)
    pct_calc = (charges_calc / float(brut) * 100) if float(brut) > 0 else 0.0
    st.info(f"Prix net: {net_calc:.2f} € • Base: {base_calc:.2f} € • %: {pct_calc:.2f}")

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
        st.rerun()

# ------- VUE MODIFIER / SUPPRIMER -------
def vue_modifier(df: pd.DataFrame):
    st.title("✏️ Modifier / Supprimer")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune réservation.")
        return
    df["identifiant"] = df["nom_client"].astype(str) + " | " + df["date_arrivee"].apply(format_date_str)
    choix = st.selectbox("Choisir une réservation", df["identifiant"])
    idx = df.index[df["identifiant"] == choix]
    if len(idx) == 0:
        st.warning("Sélection invalide.")
        return
    i = idx[0]

    t0, t1, t2 = st.columns(3)
    paye = t0.checkbox("Payé", value=bool(df.at[i, "paye"]))
    nom = t1.text_input("Nom", df.at[i, "nom_client"])
    sms_envoye = t2.checkbox("SMS envoyé", value=bool(df.at[i, "sms_envoye"]))

    col = st.columns(2)
    tel = col[0].text_input("Téléphone", normalize_tel(df.at[i, "telephone"]))
    pf_opts = sorted(get_palette_dict().keys())
    cur_pf = df.at[i,"plateforme"]
    pf_index = pf_opts.index(cur_pf) if cur_pf in pf_opts else 0
    plateforme = col[1].selectbox("Plateforme", pf_opts, index=pf_index)

    arrivee = st.date_input("Arrivée", df.at[i,"date_arrivee"] or date.today())
    depart  = st.date_input("Départ",  df.at[i,"date_depart"] or (arrivee + timedelta(days=1)), min_value=arrivee+timedelta(days=1))

    c1, c2, c3 = st.columns(3)
    brut = c1.number_input("Prix brut (€)", min_value=0.0, value=float(df.at[i,"prix_brut"]) if pd.notna(df.at[i,"prix_brut"]) else 0.0, step=1.0, format="%.2f")
    commissions = c2.number_input("Commissions (€)", min_value=0.0, value=float(df.at[i,"commissions"]) if pd.notna(df.at[i,"commissions"]) else 0.0, step=1.0, format="%.2f")
    frais_cb = c3.number_input("Frais CB (€)", min_value=0.0, value=float(df.at[i,"frais_cb"]) if pd.notna(df.at[i,"frais_cb"]) else 0.0, step=1.0, format="%.2f")

    d1, d2, d3 = st.columns(3)
    menage = d1.number_input("Ménage (€)", min_value=0.0, value=float(df.at[i,"menage"]) if pd.notna(df.at[i,"menage"]) else 0.0, step=1.0, format="%.2f")
    taxes  = d2.number_input("Taxes séjour (€)", min_value=0.0, value=float(df.at[i,"taxes_sejour"]) if pd.notna(df.at[i,"taxes_sejour"]) else 0.0, step=1.0, format="%.2f")

    net_calc = max(brut - commissions - frais_cb, 0.0)
    base_calc = max(net_calc - menage - taxes, 0.0)
    charges_calc = max(brut - net_calc, 0.0)
    pct_calc = (charges_calc / brut * 100) if brut > 0 else 0.0
    d3.markdown(f"**Prix net**: {net_calc:.2f} €  \n**Base**: {base_calc:.2f} €  \n**%**: {pct_calc:.2f}")

    c_save, c_del = st.columns(2)
    if c_save.button("💾 Enregistrer"):
        if depart < arrivee + timedelta(days=1):
            st.error("La date de départ doit être au moins le lendemain de l’arrivée.")
            return
        df.at[i,"paye"] = bool(paye)
        df.at[i,"nom_client"] = nom.strip()
        df.at[i,"sms_envoye"] = bool(sms_envoye)
        df.at[i,"plateforme"] = plateforme
        df.at[i,"telephone"]  = normalize_tel(tel)
        df.at[i,"date_arrivee"] = arrivee
        df.at[i,"date_depart"]  = depart
        df.at[i,"prix_brut"] = float(brut)
        df.at[i,"commissions"] = float(commissions)
        df.at[i,"frais_cb"] = float(frais_cb)
        df.at[i,"prix_net"]  = round(net_calc, 2)
        df.at[i,"menage"] = float(menage)
        df.at[i,"taxes_sejour"] = float(taxes)
        df.at[i,"base"] = round(base_calc, 2)
        df.at[i,"charges"] = round(charges_calc, 2)
        df.at[i,"%"] = round(pct_calc, 2)
        df.at[i,"nuitees"]   = (depart - arrivee).days
        df.at[i,"AAAA"]      = arrivee.year
        df.at[i,"MM"]        = arrivee.month
        df.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df)
        st.success("✅ Modifié")
        st.rerun()

    if c_del.button("🗑 Supprimer"):
        df2 = df.drop(index=i)
        df2.drop(columns=["identifiant"], inplace=True, errors="ignore")
        sauvegarder_donnees(df2)
        st.warning("Supprimé.")
        st.rerun()