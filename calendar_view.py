# calendar_view.py — Calendrier mensuel avec cases colorées par plateforme + noms clients

import streamlit as st
import pandas as pd
import calendar
from datetime import date
import colorsys

from palette_utils import get_palette
from io_utils import ensure_schema, split_totals  # split_totals doit exister dans io_utils.py

def _lighten(hex_color: str, factor: float = 0.75) -> str:
    hex_color = hex_color.lstrip("#")
    r = int(hex_color[0:2], 16)
    g = int(hex_color[2:4], 16)
    b = int(hex_color[4:6], 16)
    h, l, s = colorsys.rgb_to_hls(r/255, g/255, b/255)
    l = min(1.0, l + (1.0 - l) * factor)
    r2, g2, b2 = colorsys.hls_to_rgb(h, l, s)
    return f"#{int(r2*255):02x}{int(g2*255):02x}{int(b2*255):02x}"

def _ideal_text(bg_hex: str) -> str:
    bg_hex = bg_hex.lstrip("#")
    r = int(bg_hex[0:2], 16)
    g = int(bg_hex[2:4], 16)
    b = int(bg_hex[4:6], 16)
    lum = (0.299*r + 0.587*g + 0.114*b)/255
    return "#000000" if lum > 0.6 else "#ffffff"

def vue_calendrier(df: pd.DataFrame):
    pal = get_palette()
    st.title("📅 Calendrier (par plateforme)")
    df = ensure_schema(df)
    if df.empty:
        st.info("Aucune réservation.")
        return

    c1, c2 = st.columns(2)
    mois_nom = c1.selectbox("Mois", list(calendar.month_name)[1:], index=max(0, date.today().month-1))
    annees = sorted([int(x) for x in df["AAAA"].dropna().unique()])
    if not annees:
        st.warning("Aucune année trouvée.")
        return
    annee = c2.selectbox("Année", annees, index=len(annees)-1)

    m = list(calendar.month_name).index(mois_nom)
    monthcal = calendar.monthcalendar(annee, m)

    # Construire mapping jour -> [(pf, client), ...]
    jours_du_mois = {
        date(annee, m, j): []
        for j in range(1, calendar.monthrange(annee, m)[1] + 1)
    }
    core, _ = split_totals(df)
    for _, r in core.iterrows():
        d1, d2 = r.get("date_arrivee"), r.get("date_depart")
        if not (isinstance(d1, date) and isinstance(d2, date)):
            continue
        pf = str(r.get("plateforme") or "Autre")
        nom = str(r.get("nom_client") or "")
        cur = d1
        while cur < d2:
            if cur.month == m and cur.year == annee:
                jours_du_mois[cur].append((pf, nom))
            cur = cur.replace(day=cur.day)  # no-op; just clarity
            # avance d'un jour:
            try:
                from datetime import timedelta
                cur = cur + timedelta(days=1)
            except Exception:
                break

    # Construire table + styles
    headers = ["Lun","Mar","Mer","Jeu","Ven","Sam","Dim"]
    table, bg_table, fg_table = [], [], []

    for sem in monthcal:
        row_txt, row_bg, row_fg = [], [], []
        for jour in sem:
            if jour == 0:
                row_txt.append("")
                row_bg.append("transparent")
                row_fg.append("inherit")
            else:
                d = date(annee, m, jour)
                items = jours_du_mois.get(d, [])
                # texte: num du jour + noms (max 5)
                noms = [nm for _, nm in items]
                if len(noms) > 5:
                    content = [str(jour)] + noms[:5] + [f"... (+{len(noms)-5})"]
                else:
                    content = [str(jour)] + noms
                row_txt.append("\n".join(content))

                if items:
                    base = pal.get(items[0][0], "#999999")
                    bg = _lighten(base, 0.75)
                    fg = _ideal_text(bg)
                else:
                    bg, fg = "transparent", "inherit"
                row_bg.append(bg); row_fg.append(fg)
        table.append(row_txt); bg_table.append(row_bg); fg_table.append(row_fg)

    df_tbl = pd.DataFrame(table, columns=headers)

    def _style_row(vals, ridx):
        css = []
        for cidx, _ in enumerate(vals):
            bg = bg_table[ridx][cidx]; fg = fg_table[ridx][cidx]
            css.append(
                f"background-color:{bg};color:{fg};white-space:pre-wrap;"
                f"border:1px solid rgba(127,127,127,0.25);"
            )
        return css

    styler = df_tbl.style
    for r in range(df_tbl.shape[0]):
        styler = styler.apply(lambda v, r=r: _style_row(v, r), axis=1)

    st.caption("Légende :")
    leg = " • ".join([
        f'<span style="display:inline-block;width:0.9em;height:0.9em;background:{pal[p]};border-radius:3px;margin-right:6px;"></span>{p}'
        for p in sorted(pal.keys())
    ])
    st.markdown(leg, unsafe_allow_html=True)

    st.dataframe(styler, use_container_width=True, height=500)