# calendar_view.py — Calendrier mensuel (cases colorées + noms clients)

import streamlit as st
import pandas as pd
import calendar
from datetime import date
import colorsys
from io_utils import ensure_schema, split_totals, format_date_str
from palette_utils import get_palette_dict

def _lighten(hex_color: str, factor: float = 0.75) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16); g = int(hex_color[2:4], 16); b = int(hex_color[4:6], 16)
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    l = min(1.0, l + (1.0 - l) * factor)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"

def _ideal_text(bg_hex: str) -> str:
    bg_hex = bg_hex.lstrip("#")
    r = int(bg_hex[0:2], 16); g = int(bg_hex[2:4], 16); b = int(bg_hex[4:6], 16)
    luminance = (0.299*r + 0.587*g + 0.114*b) / 255
    return "#000000" if luminance > 0.6 else "#ffffff"

def vue_calendrier(df: pd.DataFrame):
    pal = get_palette_dict()
    st.title("📅 Calendrier")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune donnée.")
        return

    cols = st.columns(2)
    mois_nom = cols[0].selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année disponible.")
        return
    annee = cols[1].selectbox("Année", annees, index=len(annees)-1)

    mois_index = list(calendar.month_name).index(mois_nom)
    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    monthcal = calendar.monthcalendar(annee, mois_index)

    # planning jour -> [(pf, nom)]
    core, _ = split_totals(df)
    day_map = {}
    for _, r in core.iterrows():
        d1, d2 = r["date_arrivee"], r["date_depart"]
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        j = d1
        while j < d2:
            if j.month == mois_index and j.year == annee:
                day_map.setdefault(j, []).append((str(r["plateforme"]), str(r["nom_client"])))
            j = j + pd.Timedelta(days=1)

    table, bg_table, fg_table = [], [], []
    for semaine in monthcal:
        row_text, row_bg, row_fg = [], [], []
        for j in semaine:
            if j == 0:
                row_text.append(""); row_bg.append("transparent"); row_fg.append(None)
            else:
                d = date(annee, mois_index, j)
                items = day_map.get(d, [])
                lines = [str(j)] + [nm for _, nm in items[:5]] + ([f"... (+{len(items)-5})"] if len(items)>5 else [])
                row_text.append("\n".join(lines))
                if items:
                    base = pal.get(items[0][0], "#888888")
                    bg = _lighten(base, 0.72)
                    fg = _ideal_text(bg)
                else:
                    bg = "transparent"; fg = None
                row_bg.append(bg); row_fg.append(fg)
        table.append(row_text); bg_table.append(row_bg); fg_table.append(row_fg)

    df_table = pd.DataFrame(table, columns=headers)

    def style_row(vals, i):
        css=[]
        for k,_ in enumerate(vals):
            bg = bg_table[i][k]; fg = fg_table[i][k] or "inherit"
            css.append(f"background-color:{bg};color:{fg};white-space:pre-wrap;border:1px solid rgba(127,127,127,0.25