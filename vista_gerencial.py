import base64
import os
import datetime
import streamlit as st

import data_loader as dl
from vista_vendedor import (
    _render_avance, _CSS_AVANCE, _pct, _hl, _tend_cls,
    _render_arbol_vendedor, _CSS_ARBOL_VND,
)
from renders_analytics import (
    render_tendencia, render_mix_segmento, render_top_marcas,
    render_censo_vendedor, render_coaching_vendedor,
)
from vista_cliente import _slug, _SPLASH_CSS, _MESES_ES

CLAVE_FICHA_GERENCIAL = "2254"


def _render_avance_simple(datos):
    """Para Sup 24 / Jefe de Venta / Grupo Palco: no tienen montos a cobrar, solo
    se sigue el volumen (Obj/Acu/%Tend), sin tareas/GMV/tiempos/escalas."""
    st.markdown(_CSS_AVANCE, unsafe_allow_html=True)
    lista = datos.get("metricas_hl_lista", [])
    if not lista:
        st.info("Sin datos de avance disponibles.")
        return

    _SEP_ANTES = {"UNG TOP", "AGUAS"}
    rows = ""
    for item in lista:
        if item["label"] in _SEP_ANTES:
            rows += '<tr class="sep"><td colspan="4"></td></tr>'
        ava = item.get("ava_tend")
        rows += (
            f'<tr class="{item.get("tipo","")}">'
            f'<td>{item["label"]}</td>'
            f'<td>{_hl(item.get("obj"))}</td>'
            f'<td><b>{_hl(item.get("acu"))}</b></td>'
            f'<td class="{_tend_cls(ava)}">{_pct(ava)}</td>'
            f"</tr>"
        )
    st.markdown(
        '<table class="av-tabla"><thead><tr>'
        '<th>Volumen HL</th><th>Obj</th><th>Acu</th><th>%Tend</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody></table>',
        unsafe_allow_html=True,
    )


def _render_avance_grupo(grupo):
    codigo = grupo["codigo"]
    datos = dl.cargar_avance_grupo(str(codigo))
    if datos is None:
        st.info("No se encontró avance para este grupo.")
        return None
    if datos.get("cabecera"):
        _render_avance(codigo, datos=datos)
    else:
        _render_avance_simple(datos)
    return datos


def _render_detalle_por_vendedor(detalle, key_prefix, etiqueta_total):
    """Cuadro con el desglose por vendedor (o por supervisor, en el caso del Jefe de
    Venta) de cada categoría de volumen — bloque V:AC (supervisor) / AJ:AQ (JDV) de
    RESUMEN DE REPORTES.xlsx."""
    if not detalle:
        return
    st.markdown(_CSS_AVANCE, unsafe_allow_html=True)
    categorias = [b["categoria"] for b in detalle]
    sel = st.selectbox("Categoría", categorias, key=f"{key_prefix}_detalle_cat")
    bloque = next(b for b in detalle if b["categoria"] == sel)

    rows = ""
    for fila in bloque["filas"]:
        ava = fila.get("ava_tend")
        nombre = etiqueta_total if fila["nombre"] == "<>24" else fila["nombre"]
        cls = "tot" if fila["nombre"] in ("<>24",) or fila is bloque["filas"][0] else ""
        rows += (
            f'<tr class="{cls}">'
            f'<td>{nombre}</td>'
            f'<td>{_hl(fila.get("obj"))}</td>'
            f'<td><b>{_hl(fila.get("acu"))}</b></td>'
            f'<td class="{_tend_cls(ava)}">{_pct(ava)}</td>'
            f'<td>{_hl(fila.get("vta_prom"))}</td>'
            f'<td>{_hl(fila.get("med_nec"))}</td>'
            f"</tr>"
        )
    st.markdown(
        '<table class="av-tabla"><thead><tr>'
        '<th>Vendedor</th><th>Obj</th><th>Acu</th><th>%Tend</th><th>Vta Prom</th><th>Med Nec</th>'
        '</tr></thead>'
        f'<tbody>{rows}</tbody></table>',
        unsafe_allow_html=True,
    )


def render():
    st.subheader("Ficha Gerencial")

    if "gerencial_autenticado" not in st.session_state:
        st.session_state.gerencial_autenticado = None

    if st.session_state.gerencial_autenticado is None:
        st.caption(
            "Ingresá tu código (número de supervisor, 100 para Jefe de Venta, "
            "o 'palco' para Grupo Palco) y la clave de acceso."
        )
        codigo_in = st.text_input("Código", placeholder="Ej: 21, 100 o palco")
        clave_in = st.text_input("Clave de acceso", type="password")
        if st.button("Ingresar"):
            if clave_in.strip() != CLAVE_FICHA_GERENCIAL:
                st.error("Clave incorrecta.")
                return
            grupo = dl.resolver_grupo_vendedores(codigo_in)
            if grupo is None:
                st.error("Código no encontrado.")
                return
            st.session_state.gerencial_autenticado = grupo
            st.rerun()
        return

    grupo = st.session_state.gerencial_autenticado
    if st.button("↩ Cerrar sesión"):
        st.session_state.gerencial_autenticado = None
        st.session_state.pop("arbol_vnd", None)
        st.rerun()

    vendedores = grupo["vendedores"]
    incluir_lucky = grupo["incluir_lucky"]
    incluir_pana = grupo["incluir_pana"]
    key_prefix = f"ger{grupo['codigo']}"

    _logo_path = os.path.join(os.path.dirname(__file__), "logo_palco.png")
    with open(_logo_path, "rb") as _f:
        _logo = base64.b64encode(_f.read()).decode()
    _splash = st.empty()
    _splash.markdown(_SPLASH_CSS.format(logo=_logo), unsafe_allow_html=True)

    kpis = dl.kpis_vendedor(vendedores)
    arbol = dl.construir_arbol_vendedor(vendedores, incluir_lucky=incluir_lucky)
    _splash.empty()

    st.markdown(f"### {grupo['nombre']}")
    st.caption(f"{len(vendedores)} vendedores en este grupo.")

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cartera total",    kpis["cartera_total"])
    k2.metric("Cartera alcohol",  kpis["cartera_alcohol"])
    k3.metric(f"Visitas {kpis['dia_semana']}", kpis["visitas_hoy_plan"])
    k4.metric("Eficiencia venta", kpis["eficiencia_venta"])

    st.divider()

    st.markdown("#### Avance de ventas")
    datos_avance = _render_avance_grupo(grupo)

    detalle = (datos_avance or {}).get("detalle_por_vendedor")
    if detalle:
        st.markdown(f"#### Detalle por {'supervisor' if grupo['tipo'] == 'jefe' else 'vendedor'}")
        etiqueta_total = grupo["nombre"] if grupo["tipo"] == "jefe" else "(Total)"
        _render_detalle_por_vendedor(detalle, key_prefix, etiqueta_total)

    st.divider()

    analytics = dl.calcular_analytics_vendedor(vendedores, incluir_lucky=incluir_lucky, incluir_pana=incluir_pana)

    st.markdown("#### Tendencia de volumen cartera")
    render_tendencia(analytics["tendencia"], key_prefix=key_prefix)

    st.divider()

    st.markdown("#### Mix por segmento YTD")
    render_mix_segmento(analytics["mix"], key_prefix=key_prefix)

    st.divider()

    st.markdown("#### Top marcas YTD")
    render_top_marcas(analytics["top_por_un"], key_prefix=key_prefix)

    st.divider()

    # Censo: solo cuando hay un dato pre-calculado real (supervisor o Total Palco) —
    # ver _render_avance_grupo / migrar_censo, no se recalcula nada acá.
    censo_codigo = grupo["codigo"] if grupo["tipo"] == "supervisor" else None
    censo = dl.calcular_censo_vendedor(censo_codigo) if censo_codigo is not None else dl.calcular_censo_empresa()
    if censo:
        st.markdown("#### Censo Thomas — Share of Market por segmento")
        censo_empresa = dl.calcular_censo_empresa()
        render_censo_vendedor(censo, key_prefix=key_prefix, empresa=censo_empresa)
        st.divider()

    # Coaching: solo a nivel supervisor (coachings que el JDV le hizo a ese supervisor).
    if grupo["tipo"] == "supervisor":
        coaching = dl.calcular_coaching_supervisor(grupo["codigo"])
        if coaching:
            st.markdown("#### Coaching")
            render_coaching_vendedor(coaching, key_prefix=key_prefix)
            st.divider()

    st.markdown("#### Árbol de cobertura de cartera")
    hoy = datetime.date.today()
    st.caption(f"Mes: {_MESES_ES[hoy.month-1]} {hoy.year}")
    if not arbol["uns"]:
        st.info("Sin compras registradas para este mes en la cartera.")
    else:
        _render_arbol_vendedor(arbol, key_prefix)
