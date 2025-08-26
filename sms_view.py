# sms_view.py — vue SMS (arrivées demain, relance après départ, composeur)
import streamlit as st
import pandas as pd
from datetime import date, timedelta
from urllib.parse import quote

# utilitaires fournis par io_utils.py
from io_utils import ensure_schema, normalize_tel, format_date_str

def _sms_message_arrivee(row: pd.Series) -> str:
    d1 = row.get("date_arrivee"); d2 = row.get("date_depart")
    d1s = d1.strftime("%Y/%m/%d") if isinstance(d1, date) else ""
    d2s = d2.strftime("%Y/%m/%d") if isinstance(d2, date) else ""
    nuitees = int(row.get("nuitees") or ((d2 - d1).days if d1 and d2 else 0))
    plateforme = str(row.get("plateforme") or "")
    nom = str(row.get("nom_client") or "")
    tel_aff = str(row.get("telephone") or "").strip()
    return (
        "VILLA TOBIAS\n"
        f"Plateforme : {plateforme}\n"
        f"Date d'arrivee : {d1s}  Date depart : {d2s}  Nombre de nuitees : {nuitees}\n\n"
        f"Bonjour {nom}\n"
        f"Telephone : {tel_aff}\n\n"

        "Bienvenue chez nous !\n\n"
        "Nous sommes ravis de vous accueillir à Nice. \n\n"
        "Afin d'organiser au mieux votre reception, merci de nous indiquervotre heure d'arrivée.\n\n"
        "Une Place de parking vous est allouée en cas de besoin. \n\n"
        "Le check-in se fait à partir de 14:00 h et le check-out au plus tard à 11;00 h.\n\n"
        "Vous trouverez des consignes a bagages dans chaque quartier de Nice.\n\n"
        "Nous vous souhaitons un excellent voyage et nous nous rejouissons de vous rencontrer tres bientot.\n\n"
        "Annick & Charley"

        “Welcome to our home!\n\n”
        “We are delighted to welcome you to Nice. \n\n”
        “In order to organize your reception as best as possible, please let us know your arrival time.\n\n”
        “A parking space is available if needed. \n\n”
        “Check-in is from 2:00 p.m. and check-out is by 11:00 a.m. at the latest.\n\n”
        “You will find luggage storage facilities in every district of Nice.\n\n”
        "We wish you a wonderful trip and look forward to meeting you very soon. \n\n"
        “Annick & Charley”
    )

def _sms_message_depart(row: pd.Series) -> str:
    nom = str(row.get("nom_client") or "")
    return (
        f"Bonjour {nom},\n\n"
        "Merci d’avoir choisi notre appartement ! "
        "Nous espérons que vous avez passé un agréable séjour.\n\n"
        "Si vous souhaitez revenir, notre porte vous sera toujours ouverte.\n\n"
        "Annick & Charley"
    )

def vue_sms(df: pd.DataFrame):
    st.title("✉️ SMS (envoi manuel)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    today = date.today()
    demain = today + timedelta(days=1)
    hier = today - timedelta(days=1)

    colA, colB = st.columns(2)

    # Arrivées demain
    with colA:
        st.subheader("📆 Arrivées demain")
        arrives = df[df["date_arrivee"] == demain].copy()
        if arrives.empty:
            st.info("Aucune arrivée demain.")
        else:
            for _, r in arrives.reset_index(drop=True).iterrows():
                body = _sms_message_arrivee(r)
                tel = normalize_tel(r.get("telephone"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                st.markdown(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}")
                st.markdown(
                    f"Arrivée: {format_date_str(r.get('date_arrivee'))} • "
                    f"Départ: {format_date_str(r.get('date_depart'))} • "
                    f"Nuitées: {r.get('nuitees','')}"
                )
                st.code(body)
                c1, c2 = st.columns(2)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                st.divider()

    # Relance +24h après départ
    with colB:
        st.subheader("🕒 Relance +24h après départ")
        dep_24h = df[df["date_depart"] == hier].copy()
        if dep_24h.empty:
            st.info("Aucun départ hier.")
        else:
            for _, r in dep_24h.reset_index(drop=True).iterrows():
                body = _sms_message_depart(r)
                tel = normalize_tel(r.get("telephone"))
                tel_link = f"tel:{tel}" if tel else ""
                sms_link = f"sms:{tel}?&body={quote(body)}" if tel and body else ""
                st.markdown(f"**{r.get('nom_client','')}** — {r.get('plateforme','')}")
                st.code(body)
                c1, c2 = st.columns(2)
                if tel_link: c1.link_button(f"📞 Appeler {tel}", tel_link)
                if sms_link: c2.link_button("📩 Envoyer SMS", sms_link)
                st.divider()

    # Composeur manuel
    st.subheader("✍️ Composer un SMS manuel")
    df_pick = df.copy()
    df_pick["id_aff"] = (
        df_pick["nom_client"].astype(str)
        + " | "
        + df_pick["plateforme"].astype(str)
        + " | "
        + df_pick["date_arrivee"].apply(format_date_str)
    )
    if df_pick["id_aff"].empty:
        st.info("Aucune réservation sélectionnable.")
        return

    choix = st.selectbox("Choisir une réservation", df_pick["id_aff"])
    r = df_pick.loc[df_pick["id_aff"] == choix].iloc[0]
    tel = normalize_tel(r.get("telephone"))

    choix_type = st.radio(
        "Modèle de message",
        ["Arrivée (demande d’heure)", "Relance après départ", "Message libre"],
        horizontal=True,
    )
    if choix_type == "Arrivée (demande d’heure)":
        body = _sms_message_arrivee(r)
    elif choix_type == "Relance après départ":
        body = _sms_message_depart(r)
    else:
        body = st.text_area("Votre message", value="", height=160, placeholder="Tapez votre SMS ici…")

    c1, c2 = st.columns(2)
    with c1:
        st.code(body or "—")
    if tel and body:
        c1, c2 = st.columns(2)
        c1.link_button(f"📞 Appeler {tel}", f"tel:{tel}")
        c2.link_button("📩 Envoyer SMS", f"sms:{tel}?&body={quote(body)}")
    else:
        st.info("Renseignez un téléphone et un message.")
