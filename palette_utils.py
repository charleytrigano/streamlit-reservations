import streamlit as st

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
    return f'<span style="color:{color};font-weight:bold">{name}</span>'

def render_palette_editor_sidebar():
    palette = get_palette()
    st.sidebar.markdown("## 🎨 Plateformes")
    with st.sidebar.expander("➕ Ajouter / modifier des plateformes", expanded=False):
        new_name = st.text_input("Nom plateforme", key="pal_new_name")
        new_color = st.color_picker("Couleur", key="pal_new_color", value="#9b59b6")
        if st.button("Ajouter / Modifier"):
            if new_name:
                palette[new_name] = new_color
                save_palette(palette)
                st.success(f"Plateforme « {new_name} » mise à jour.")
        if st.button("Réinitialiser"):
            save_palette(DEFAULT_PALETTE.copy())
            st.success("Palette réinitialisée.")
    for pf in sorted(palette.keys()):
        st.sidebar.markdown(platform_badge(pf, palette), unsafe_allow_html=True)
