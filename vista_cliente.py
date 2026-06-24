import base64
import datetime
import os
import re
import pandas as pd
import streamlit as st
from data_loader import datos_cliente, calcular_vol_cliente, calcular_analytics_cliente, calcular_censo_cliente
from renders_analytics import render_tendencia, render_mix_segmento, render_top_marcas, render_pie_censo
from arbol_cobertura import construir_arbol

# Logo en base64 para overlay de carga
def _logo_b64():
    path = os.path.join(os.path.dirname(__file__), "logo_palco.png")
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

_SPLASH_CSS = """
<style>
#splash-overlay {{
    position: fixed; top: 0; left: 0;
    width: 100vw; height: 100vh;
    background: #0e1117;
    z-index: 99999;
    display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    gap: 20px;
}}
#splash-overlay img {{ width: 180px; }}
#splash-overlay p {{ color: #888; font-size: 1rem; margin: 0; }}
</style>
<div id="splash-overlay">
  <div style="background:white;border-radius:10px;padding:12px;">
    <img src="data:image/png;base64,{logo}">
  </div>
  <p>Cargando...</p>
</div>
"""

# ─── Orden de UNs ────────────────────────────────────────────────────────────
_ORDEN_UN = [
    "CERVEZAS CMQ",
    "UNG",
    "AGUAS ECO",
    "MARKETPLACE ALIMENTOS",
    "VINO",
    "ADYACENCIAS",
]

# ─── Configuración por Unidad de Negocio ────────────────────────────────────
#  mostrar_seg:        ¿Mostrar el nivel Segmento? Si False, pasa directo a Marcas.
#  marcas_todas:       ¿Mostrar marcas no compradas (rojo)? Si False, solo compradas.
#  skus_solo_comprados ya es universal (siempre True) — nivel artículo solo comprados.
_UN_CFG = {
    "CERVEZAS CMQ":         {"mostrar_seg": True,  "marcas_todas": True},
    "UNG":                  {"mostrar_seg": True,  "marcas_todas": True},
    "VINO":                 {"mostrar_seg": False, "marcas_todas": True},
    "ADYACENCIAS":          {"mostrar_seg": False, "marcas_todas": True},
    "AGUAS ECO":            {"mostrar_seg": False, "marcas_todas": True},
    "MARKETPLACE ALIMENTOS":{"mostrar_seg": False, "marcas_todas": False, "skus_directo": True},
}

def _cfg(un_nombre):
    n = str(un_nombre).strip().upper()
    for k, v in _UN_CFG.items():
        if k in n or n in k:
            return v
    return {"mostrar_seg": True, "marcas_todas": True}

# ─── CSS ─────────────────────────────────────────────────────────────────────
_CSS_ARBOL = """
<style>
div[class*="st-key-nivelROOT-"],
div[class*="st-key-nivelUN-"],
div[class*="st-key-nivelSEG-"],
div[class*="st-key-nivelMARCA-"],
div[class*="st-key-nivelART-"] {
    background-color: transparent !important;
    padding: 0.1rem 0 !important;
}
div[class*="st-key-nivelROOT-"] button  { background-color: #111111 !important; color: #f5f5f5 !important; border-radius: 8px !important; border: none !important; font-weight: 600 !important; }
div[class*="st-key-nivelUN-"]   button  { background-color: #2b2b2b !important; color: #eeeeee !important; border-radius: 7px !important; border: none !important; }
div[class*="st-key-nivelSEG-"]  button  { background-color: #454545 !important; color: #e5e5e5 !important; border-radius: 6px !important; border: none !important; }
div[class*="st-key-nivelMARCA-"] button { background-color: #636363 !important; color: #f0f0f0 !important; border-radius: 5px !important; border: none !important; }
</style>
"""

# ─── Helpers ─────────────────────────────────────────────────────────────────
def _slug(texto):
    return re.sub(r"[^a-zA-Z0-9]+", "_", str(texto)).strip("_")

def _icono(compra):
    return "🟢" if compra else "🔴"

def _esta_abierto(key):
    return key in st.session_state.get("arbol_abierto", set())

def _cerrar_con_hijos(key, abiertos):
    """Elimina una clave y todos sus descendientes (claves que empiecen con key|)."""
    abiertos.discard(key)
    prefijo = key + "|"
    abiertos -= {k for k in list(abiertos) if k.startswith(prefijo)}

def _abrir_exclusivo(key, sibling_keys):
    abiertos = st.session_state.setdefault("arbol_abierto", set())
    if key in abiertos:
        _cerrar_con_hijos(key, abiertos)
    else:
        for sib in sibling_keys:
            _cerrar_con_hijos(sib, abiertos)
        abiertos.add(key)

def _toggle_simple(key):
    abiertos = st.session_state.setdefault("arbol_abierto", set())
    if key in abiertos:
        # Al cerrar el root, limpia TODO lo que estaba abierto abajo
        abiertos.clear()
    else:
        abiertos.add(key)

def _ordenar_uns(arbol):
    def _idx(nombre):
        n = str(nombre).strip().upper()
        for i, ref in enumerate(_ORDEN_UN):
            if n == ref or n in ref or ref in n:
                return i
        return len(_ORDEN_UN)
    return sorted(arbol.items(), key=lambda x: _idx(str(x[0])))

# ─── Renderizado ─────────────────────────────────────────────────────────────

def _render_articulos(datos_marca, key_marca):
    """Nivel SKU: muestra SOLO los artículos comprados (universal)."""
    items_comprados = [
        (nombre, d)
        for nombre, d in sorted(datos_marca["articulos"].items(), key=lambda x: str(x[0]))
        if d["compra"]
    ]
    if not items_comprados:
        return
    with st.container(key=f"nivelART-{_slug(key_marca)}"):
        for art_nombre, datos_art in items_comprados:
            st.markdown(
                f"&nbsp;&nbsp;&nbsp;&nbsp;🟢 "
                f"<span style='color:#2ecc71'>{art_nombre}</span>",
                unsafe_allow_html=True,
            )


def _render_marcas(datos_marcas_dict, key_parent, cfg):
    """
    Renderiza el nivel Marca con acordeón.
    datos_marcas_dict: {marca_nombre: {"compra": bool, "hl": float, "articulos": {...}}}
    cfg: config de la UN (marcas_todas, etc.)
    """
    marca_todas = cfg.get("marcas_todas", True)
    items = sorted(
        datos_marcas_dict.items(),
        key=lambda x: (not x[1]["compra"], str(x[0])),
    )
    if not marca_todas:
        items = [(m, d) for m, d in items if d["compra"]]
    if not items:
        st.caption("Sin compras registradas.")
        return

    marca_keys = [f"{key_parent}|m|{m}" for m, _ in items]
    open_key = next((k for k in marca_keys if _esta_abierto(k)), None)

    for marca_nombre, datos_marca in items:
        key = f"{key_parent}|m|{marca_nombre}"
        if open_key is not None and key != open_key:
            continue
        with st.container(key=f"nivelMARCA-{_slug(key)}"):
            detalle = ""
            if st.button(
                f"{_icono(datos_marca['compra'])} {marca_nombre}{detalle}",
                key=key,
                use_container_width=True,
            ):
                _abrir_exclusivo(key, marca_keys)
                st.rerun()
            if _esta_abierto(key):
                _render_articulos(datos_marca, key)


def _render_segmentos(datos_un, key_un, cfg):
    """Nivel Segmento con acordeón."""
    seg_items = sorted(
        datos_un["segmentos"].items(),
        key=lambda x: (not x[1]["compra"], str(x[0])),
    )
    seg_keys = [f"{key_un}|s|{s}" for s, _ in seg_items]
    open_key = next((k for k in seg_keys if _esta_abierto(k)), None)

    for seg_nombre, datos_seg in seg_items:
        key = f"{key_un}|s|{seg_nombre}"
        if open_key is not None and key != open_key:
            continue
        with st.container(key=f"nivelSEG-{_slug(key)}"):
            if st.button(
                f"{_icono(datos_seg['compra'])} {seg_nombre}",
                key=key,
                use_container_width=True,
            ):
                _abrir_exclusivo(key, seg_keys)
                st.rerun()
            if _esta_abierto(key):
                _render_marcas(datos_seg["marcas"], key, cfg)


def _render_skus_directo(datos_un, key_un):
    """Saltea Segmento y Marca — muestra directamente solo los SKUs comprados (MARKETPLACE)."""
    with st.container(key=f"nivelART-{_slug(key_un)}"):
        items = []
        for datos_seg in datos_un["segmentos"].values():
            for datos_marca in datos_seg["marcas"].values():
                for art_nombre, datos_art in datos_marca["articulos"].items():
                    if datos_art["compra"]:
                        items.append((art_nombre, datos_art["hl"]))
        if not items:
            st.caption("Sin compras registradas.")
            return
        for art_nombre, hl in sorted(items, key=lambda x: x[0]):
            st.markdown(
                f"&nbsp;&nbsp;🟢 <span style='color:#2ecc71'>{art_nombre}</span>",
                unsafe_allow_html=True,
            )


def _render_marcas_directo(datos_un, key_un, cfg):
    """Saltea el nivel Segmento y renderiza Marcas directamente (para VINO, ADY, etc.)."""
    # Fusionar todas las marcas de todos los segmentos
    marcas_fusionadas = {}
    for datos_seg in datos_un["segmentos"].values():
        for marca, datos_marca in datos_seg["marcas"].items():
            if marca not in marcas_fusionadas:
                marcas_fusionadas[marca] = {"compra": False, "hl": 0.0, "articulos": {}}
            marcas_fusionadas[marca]["articulos"].update(datos_marca["articulos"])
            marcas_fusionadas[marca]["hl"] = round(marcas_fusionadas[marca]["hl"] + datos_marca["hl"], 2)
            if datos_marca["compra"]:
                marcas_fusionadas[marca]["compra"] = True
    _render_marcas(marcas_fusionadas, key_un, cfg)


_MESES_ES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

def _label_mes(anio_mes):
    return f"{_MESES_ES[anio_mes[1]-1]} {str(anio_mes[0])[2:]}"

def _pct_val(actual, base):
    if not base: return None
    return (actual - base) / base * 100

def _fmt_hl(v):
    return f"{v:.1f}" if v else "—"

def _fmt_gmv(v):
    if not v: return "—"
    if v >= 1_000_000: return f"${v/1_000_000:.1f}M"
    if v >= 1_000: return f"${v/1_000:.0f}K"
    return f"${v:.0f}"

def _delta_str(actual, base):
    p = _pct_val(actual, base)
    if p is None: return None
    return f"{'+' if p>=0 else ''}{p:.0f}%"

_CSS_VOL = """
<style>
.vol-tabla {
    width: 100%;
    border-collapse: collapse;
    font-size: 0.88rem;
}
.vol-tabla th {
    background: rgba(128,128,128,0.15);
    color: var(--text-color);
    opacity: 0.7;
    font-weight: 600;
    padding: 6px 10px;
    text-align: right;
    font-size: 0.78rem;
    border-bottom: 2px solid rgba(128,128,128,0.25);
}
.vol-tabla th:first-child { text-align: left; }
.vol-tabla td {
    padding: 5px 10px;
    text-align: right;
    color: var(--text-color);
    border-top: 1px solid rgba(128,128,128,0.12);
}
.vol-tabla td:first-child { text-align: left; }
.vol-tabla tr.sub td { background: rgba(128,128,128,0.06); font-size: 0.82rem; opacity: 0.85; }
.vol-tabla tr.sub td:first-child { padding-left: 1.6rem; }
.vol-tabla tr.sep td { height: 4px; padding: 0; border: none; background: transparent; }
.vol-tabla .pos { color: #1d9e52; font-size: 0.75rem; }
.vol-tabla .neg { color: #cc2222; font-size: 0.75rem; }
.vol-tabla .bold { font-weight: 700; color: var(--text-color); }
</style>
"""

def _dh(actual, base):
    """Delta HTML inline: ▲12% verde o ▼5% rojo."""
    if not base or actual == 0:
        return ""
    pct = (actual - base) / base * 100
    cls = "pos" if pct >= 0 else "neg"
    sym = "▲" if pct >= 0 else "▼"
    return f'<span class="{cls}"> {sym}{abs(pct):.0f}%</span>'

def _td(v, fmt, base_ma=None, base_mma=None, bold=False):
    """Celda de valor actual con delta opcional."""
    cls = ' class="bold"' if bold else ""
    return f'<td{cls}>{fmt(v)}{_dh(v, base_ma) if base_ma is not None else ""}</td>'

def _render_tabla_volumen(met, lbl_ac, con_ult=True, ult_fecha="—"):
    """Renderiza tabla compacta de volumen. con_ult=False para vista vendedor."""
    def fila(label, vals, fmt, indent=False, bold=False, con_ult=con_ult):
        act, ma, mma = vals["actual"], vals["mes_ant"], vals["anio_ant"]
        ulv = vals.get("ult_visita", 0)
        td_lbl = f'<td{"" if not indent else ""}{"" if not bold else ""}>' \
                 f'{"↳ " if indent else ""}{"<b>" if bold else ""}{label}{"</b>" if bold else ""}</td>'
        td_ac  = f'<td class="{"bold" if bold else ""}">{fmt(act)}{_dh(act, ma)}</td>'
        td_ma  = f'<td>{fmt(ma)}{_dh(ma, mma)}</td>'
        td_mma = f'<td>{fmt(mma)}</td>'
        td_ulv = f'<td>{fmt(ulv)}</td>' if con_ult else ""
        row_cls = ' class="sub"' if indent else ""
        return f"<tr{row_cls}>{td_lbl}{td_ac}{td_ma}{td_mma}{td_ulv}</tr>"

    ult_th = f'<th>Últ {ult_fecha}</th>' if con_ult else ""
    hl = met["hl_total"]

    rows = []
    rows.append(fila("HL Total", hl, _fmt_hl, bold=True))
    rows.append(fila("prom/visita", {
        "actual": hl.get("prom_actual", 0), "mes_ant": hl.get("prom_mes_ant", 0),
        "anio_ant": hl.get("prom_anio_ant", 0), "ult_visita": hl.get("prom_ult_visita", 0)
    }, _fmt_hl, indent=True))
    rows.append('<tr class="sep"><td colspan="5"></td></tr>')
    rows.append(fila("Cerveza", met["cerveza_total"], _fmt_hl))
    rows.append(fila("Core-Value", met["core_value"], _fmt_hl, indent=True))
    rows.append(fila("Above Core", met["above_core"], _fmt_hl, indent=True))
    rows.append('<tr class="sep"><td colspan="5"></td></tr>')
    rows.append(fila("UNG", met["ung_total"], _fmt_hl))
    rows.append(fila("UNG Top", met["ung_top"], _fmt_hl, indent=True))
    rows.append('<tr class="sep"><td colspan="5"></td></tr>')
    rows.append(fila("Agua", met["agua"], _fmt_hl))
    rows.append('<tr class="sep"><td colspan="5"></td></tr>')
    rows.append(fila("GMV — Fact. Neta", met["gmv"], _fmt_gmv, bold=True))

    tbody = "".join(rows)
    tabla = (
        '<table class="vol-tabla">'
        '<thead><tr>'
        '<th style="width:38%"></th>'
        f'<th>{lbl_ac}</th><th>MA</th><th>MMAA</th>{ult_th}'
        '</tr></thead>'
        f'<tbody>{tbody}</tbody>'
        '</table>'
    )
    st.markdown(_CSS_VOL, unsafe_allow_html=True)
    st.markdown(tabla, unsafe_allow_html=True)


def _render_card(key, label, vals, fmt, sub_items=None):
    """Mantener compatibilidad — no usado directamente, reemplazado por tabla."""
    pass


def _render_volumen(cliente_num):
    st.markdown("#### Volumen del cliente")
    datos = calcular_vol_cliente(cliente_num)
    _render_tabla_volumen(
        datos["metricas"],
        lbl_ac=_label_mes(datos["periodos"]["actual"]),
        con_ult=True,
        ult_fecha=datos.get("ult_visita_fecha", "—"),
    )


def _render_arbol(arbol, key_prefix):
    st.markdown(_CSS_ARBOL, unsafe_allow_html=True)
    st.caption(
        "🟢 = compró · 🔴 = no compró → oportunidad. "
        "Tocá para expandir. Los SKUs solo muestran lo comprado."
    )

    root_key = f"{key_prefix}|root"
    compra_total = any(d["compra"] for d in arbol.values())

    with st.container(key=f"nivelROOT-{_slug(key_prefix)}"):
        if st.button(
            f"{_icono(compra_total)} Comprador",
            key=root_key,
            use_container_width=True,
        ):
            _toggle_simple(root_key)
            st.rerun()

        if not _esta_abierto(root_key):
            return

        un_items = _ordenar_uns(arbol)
        un_keys = [f"{key_prefix}|u|{u}" for u, _ in un_items]
        open_un = next((k for k in un_keys if _esta_abierto(k)), None)

        for un_nombre, datos_un in un_items:
            key_un = f"{key_prefix}|u|{un_nombre}"
            if open_un is not None and key_un != open_un:
                continue
            cfg = _cfg(un_nombre)
            with st.container(key=f"nivelUN-{_slug(key_un)}"):
                if st.button(
                    f"{_icono(datos_un['compra'])} {un_nombre}",
                    key=key_un,
                    use_container_width=True,
                ):
                    _abrir_exclusivo(key_un, un_keys)
                    st.rerun()
                if _esta_abierto(key_un):
                    if cfg.get("skus_directo"):
                        _render_skus_directo(datos_un, key_un)
                    elif cfg["mostrar_seg"]:
                        _render_segmentos(datos_un, key_un, cfg)
                    else:
                        _render_marcas_directo(datos_un, key_un, cfg)


# ─── Vista principal ──────────────────────────────────────────────────────────

def render():
    st.markdown(_CSS_ARBOL, unsafe_allow_html=True)
    st.subheader("📋 Ficha de Cliente")
    cliente_input = st.text_input("Número de cliente", placeholder="Ej: 100123")

    if not cliente_input:
        st.info("Ingresá el número de cliente para ver su ficha.")
        return

    try:
        cliente_num = int(cliente_input.strip())
    except ValueError:
        st.error("Ingresá solo el número de cliente (sin letras ni espacios).")
        return

    _splash = st.empty()
    _splash.markdown(_SPLASH_CSS.format(logo=_logo_b64()), unsafe_allow_html=True)
    info = datos_cliente(cliente_num)
    _splash.empty()
    if info is None:
        st.warning(f"No se encontró el cliente {cliente_num} en la cartera.")
        return

    # Encabezado
    st.markdown(f"### {info.get('razon_social', '—')}")
    col1, col2, col3 = st.columns(3)
    col1.metric("Cliente N°", int(info["cliente"]))
    col1.write(f"**Domicilio:** {info.get('domicilio', '—')}, {info.get('localidad', '—')}")
    col2.write(f"**Subcanal:** {info.get('subcanal_desc', '—')}")
    col2.write(f"**Vendedor:** {info.get('vendedor_nombre', '—')}")

    # KPIs de visita calculados desde el histórico
    vis = info.get("visitas")
    if vis:
        col3.metric("Última compra", vis["ult_compra"])
        col3.metric("Días sin comprar", vis["dias_sin_compra"] if vis["dias_sin_compra"] is not None else "—")
        st.markdown("#### Indicadores de visita")
        st.caption(f"Semana actual: **Sem {vis['semana_sistema']}**")
        c1, c2, c3 = st.columns(3)
        c1.metric("Periodicidad", vis["periodicidad_desc"])
        c2.metric("Semana de visita", vis["sem_visita"])
        frec_val = f"{vis['frecuencia']:.2f}x/sem" if vis["frecuencia"] is not None else "—"
        c3.metric("Frecuencia", frec_val)
        c4, c5, c6 = st.columns(3)
        c4.metric("Días c/compra mes", vis["dias_cc_mes"])
        c5.metric("Eficiencia de venta", vis["eficiencia"])
        c6.metric("Zona de visita", vis.get("zona_visita", "—"))
    else:
        st.caption("Sin datos de visita para este cliente.")

    st.divider()
    _render_volumen(cliente_num)
    st.divider()

    # ── Analytics: tendencia + mix + top marcas (un solo cálculo cacheado) ──
    analytics = calcular_analytics_cliente(cliente_num)

    st.markdown("#### Tendencia de volumen")
    render_tendencia(analytics["tendencia"], key_prefix=f"cli{cliente_num}")

    st.divider()

    st.markdown("#### Mix por segmento YTD")
    render_mix_segmento(analytics["mix"], key_prefix=f"cli{cliente_num}")

    st.divider()

    st.markdown("#### Top marcas YTD")
    render_top_marcas(analytics["top_por_un"], key_prefix=f"cli{cliente_num}")

    st.divider()

    st.markdown("#### Censo Thomas — Share of Market")
    censo_cli = calcular_censo_cliente(cliente_num)
    render_pie_censo(censo_cli)

    st.divider()

    # Árbol de cobertura
    st.markdown("#### Árbol de cobertura")

    hoy = datetime.date.today()
    compras = info["compras"]
    if compras.empty:
        st.warning("Este cliente no registra compras en el histórico cargado.")
        return

    # Filtrar solo compras del mes en curso para el árbol
    compras_mes = compras.copy()
    compras_mes["fecha"] = pd.to_datetime(compras_mes["fecha"], errors="coerce")
    compras_mes = compras_mes[
        (compras_mes["fecha"].dt.year == hoy.year) &
        (compras_mes["fecha"].dt.month == hoy.month)
    ]
    st.caption(f"🗓️ Árbol basado en compras de {hoy.strftime('%B %Y')} ({len(compras_mes)} registros)")

    arbol = construir_arbol(compras_mes)
    _render_arbol(arbol, f"cli{cliente_num}")
