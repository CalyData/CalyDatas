import base64
import os
import streamlit as st
import vista_cliente
import vista_vendedor
import vista_gerencial

st.set_page_config(page_title="Ficha Comercial", page_icon="🏪", layout="centered")

CLAVE_ACCESO_APP = "4778"

if "app_autenticada" not in st.session_state:
    st.session_state.app_autenticada = False

if not st.session_state.app_autenticada:
    _LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo_palco.png")
    with open(_LOGO_PATH, "rb") as f:
        _logo_b64_login = base64.b64encode(f.read()).decode()

    st.markdown(
        f'<div style="text-align:center;margin-top:40px;">'
        f'<div style="display:inline-block;background:white;border-radius:12px;padding:12px;">'
        f'<img src="data:image/png;base64,{_logo_b64_login}" style="width:120px;display:block;">'
        f'</div></div>',
        unsafe_allow_html=True,
    )
    st.markdown("<h3 style='text-align:center;'>Ficha Comercial — Grupo Palco</h3>", unsafe_allow_html=True)
    st.caption("Acceso restringido. Ingresá la clave para continuar.")

    clave_ingresada = st.text_input("Clave de acceso", type="password", key="clave_app_input")
    if st.button("Ingresar", use_container_width=True, type="primary"):
        if clave_ingresada.strip() == CLAVE_ACCESO_APP:
            st.session_state.app_autenticada = True
            st.rerun()
        else:
            st.error("Clave incorrecta.")
    st.stop()

st.markdown("""
<style>
div[data-testid="stStatusWidget"] { visibility: hidden !important; }
#MainMenu { visibility: hidden !important; }
header[data-testid="stHeader"] { background: transparent !important; }
</style>
""", unsafe_allow_html=True)

_LOGO_PATH = os.path.join(os.path.dirname(__file__), "logo_palco.png")
with open(_LOGO_PATH, "rb") as f:
    _logo_b64 = base64.b64encode(f.read()).decode()

st.markdown(f"""
<style>
.header-banner {{
    position: relative;
    width: 100%;
    border-radius: 14px;
    overflow: hidden;
    margin-bottom: 0.8rem;
    background: linear-gradient(135deg, #0d0d1e 0%, #1a1a3e 60%, #0d0d1e 100%);
    padding: 22px 28px;
    box-sizing: border-box;
}}
.header-banner-bg {{
    position: absolute;
    right: -20px;
    top: 50%;
    transform: translateY(-50%);
    width: 180px;
    opacity: 0.08;
    pointer-events: none;
}}
.header-banner-content {{
    position: relative;
    z-index: 2;
    display: flex;
    align-items: center;
    gap: 18px;
}}
.header-logo-box {{
    background: white;
    border-radius: 8px;
    padding: 8px 10px;
    flex-shrink: 0;
}}
.header-logo-box img {{ width: 70px; display: block; }}
.header-title {{ color: #ffffff; font-size: 1.7rem; font-weight: 700; margin: 0; line-height: 1.2; }}
.header-sub {{ color: #aaaacc; font-size: 0.85rem; margin: 0; margin-top: 2px; }}
</style>
<div class="header-banner">
  <img class="header-banner-bg" src="data:image/png;base64,{_logo_b64}">
  <div class="header-banner-content">
    <div class="header-logo-box">
      <img src="data:image/png;base64,{_logo_b64}">
    </div>
    <div>
      <p class="header-title">Ficha Comercial</p>
      <p class="header-sub">Grupo Palco</p>
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

st.markdown("""
<style>
div[class*="st-key-sel_cliente"] button,
div[class*="st-key-sel_vendedor"] button,
div[class*="st-key-sel_gerencial"] button {
    height: 80px !important;
    font-size: 1.05rem !important;
    font-weight: 600 !important;
    border-radius: 12px !important;
    border: 2px solid rgba(128,128,128,0.2) !important;
    transition: all 0.15s ease !important;
}
div[class*="st-key-sel_cliente"] button[kind="primary"],
div[class*="st-key-sel_vendedor"] button[kind="primary"],
div[class*="st-key-sel_gerencial"] button[kind="primary"] {
    border: 2px solid #1a6eb5 !important;
}
</style>
""", unsafe_allow_html=True)

if "opcion" not in st.session_state:
    st.session_state.opcion = "Cliente"

c1, c2, c3 = st.columns(3)
with c1:
    if st.button("🏪  Ficha Cliente\nConsultá info de un PDV",
                 key="sel_cliente", use_container_width=True,
                 type="primary" if st.session_state.opcion == "Cliente" else "secondary"):
        st.session_state.opcion = "Cliente"
        st.rerun()
with c2:
    if st.button("👤  Ficha Vendedor\nResumen de cartera y avance",
                 key="sel_vendedor", use_container_width=True,
                 type="primary" if st.session_state.opcion == "Vendedor" else "secondary"):
        st.session_state.opcion = "Vendedor"
        st.rerun()
with c3:
    if st.button("📊  Ficha Gerencial\nSupervisor / Jefe / Grupo Palco",
                 key="sel_gerencial", use_container_width=True,
                 type="primary" if st.session_state.opcion == "Gerencial" else "secondary"):
        st.session_state.opcion = "Gerencial"
        st.rerun()

opcion = st.session_state.opcion

with st.sidebar:
    st.markdown("### ⚙️ Opciones")
    if st.button("🔄 Limpiar cache", use_container_width=True, help="Fuerza la recarga de todos los datos"):
        st.cache_data.clear()
        st.success("Cache limpiado. Recargando...")
        st.rerun()

st.divider()

if opcion == "Cliente":
    vista_cliente.render()
elif opcion == "Vendedor":
    vista_vendedor.render()
else:
    vista_gerencial.render()
