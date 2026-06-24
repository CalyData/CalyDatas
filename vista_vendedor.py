import re
import base64
import os
import datetime
import streamlit as st
from data_loader import (
    cargar_estructura_comercial,
    kpis_vendedor,
    dias_desde_actualizacion_seguimiento,
    calcular_vol_vendedor,
    construir_arbol_vendedor,
    cargar_avance_vendedor,
    calcular_analytics_vendedor,
    calcular_censo_vendedor,
    calcular_censo_empresa,
    calcular_coaching_vendedor,
)
from renders_analytics import (
    render_tendencia, render_mix_segmento, render_top_marcas,
    render_censo_vendedor, render_coaching_vendedor,
)
from vista_cliente import (
    _label_mes, _fmt_hl, _fmt_gmv, _delta_str, _slug,
    _render_tabla_volumen, _MESES_ES, _SPLASH_CSS,
)

_ORDEN_UN = ["CERVEZAS CMQ","UNG","AGUAS ECO","MARKETPLACE ALIMENTOS","VINO","ADYACENCIAS"]

# UNs que muestran nivel segmento
_UN_CON_SEG = {"CERVEZAS CMQ", "UNG"}

_CSS_ARBOL_VND = """
<style>
div[class*="st-key-vnd-ROOT-"] button  { background-color: #111111 !important; color: #f5f5f5 !important; border-radius: 8px !important; border: none !important; font-weight: 600 !important; }
div[class*="st-key-vnd-UN-"]   button  { background-color: #2b2b2b !important; color: #eeeeee !important; border-radius: 7px !important; border: none !important; }
div[class*="st-key-vnd-SEG-"]  button  { background-color: #454545 !important; color: #e5e5e5 !important; border-radius: 6px !important; border: none !important; }
div[class*="st-key-vnd-MRC-"]  button  { background-color: #636363 !important; color: #f0f0f0 !important; border-radius: 5px !important; border: none !important; }
</style>
"""

# ── helpers árbol ─────────────────────────────────────────────────────────────

def _esta_abierto_v(key):
    return key in st.session_state.get("arbol_vnd", set())

def _cerrar_hijos_v(key, abiertos):
    abiertos.discard(key)
    prefijo = key + "|"
    abiertos -= {k for k in list(abiertos) if k.startswith(prefijo)}

def _abrir_exclusivo_v(key, siblings):
    abiertos = st.session_state.setdefault("arbol_vnd", set())
    if key in abiertos:
        _cerrar_hijos_v(key, abiertos)
    else:
        for s in siblings:
            _cerrar_hijos_v(s, abiertos)
        abiertos.add(key)

def _toggle_v(key):
    abiertos = st.session_state.setdefault("arbol_vnd", set())
    if key in abiertos:
        abiertos.clear()
    else:
        abiertos.add(key)

def _lbl_ccc_tbd(ccc, tbd):
    return f"CCC: {ccc} · TBD: {int(tbd)}"

# ── render árbol vendedor ─────────────────────────────────────────────────────

def _render_marcas_v(marcas, key_parent):
    marca_items = sorted(marcas.items(), key=lambda x: -x[1]["tbd"])
    marca_keys  = [f"{key_parent}|m|{m}" for m, _ in marca_items]
    open_key    = next((k for k in marca_keys if _esta_abierto_v(k)), None)

    for marca, datos in marca_items:
        key = f"{key_parent}|m|{marca}"
        if open_key and key != open_key:
            continue
        with st.container(key=f"vnd-MRC-{_slug(key)}"):
            lbl = f"{marca} — {_lbl_ccc_tbd(datos['ccc'], datos['tbd'])}"
            if st.button(lbl, key=key, use_container_width=True):
                _abrir_exclusivo_v(key, marca_keys); st.rerun()


def _render_segmentos_v(segmentos, key_un):
    seg_items = sorted(segmentos.items(), key=lambda x: -x[1]["tbd"])
    seg_keys  = [f"{key_un}|s|{s}" for s, _ in seg_items]
    open_key  = next((k for k in seg_keys if _esta_abierto_v(k)), None)

    for seg, datos in seg_items:
        key = f"{key_un}|s|{seg}"
        if open_key and key != open_key:
            continue
        with st.container(key=f"vnd-SEG-{_slug(key)}"):
            lbl = f"{seg} — {_lbl_ccc_tbd(datos['ccc'], datos['tbd'])}"
            if st.button(lbl, key=key, use_container_width=True):
                _abrir_exclusivo_v(key, seg_keys); st.rerun()
            if _esta_abierto_v(key):
                _render_marcas_v(datos["marcas"], key)


def _render_marcas_directo_v(segmentos, key_un):
    """Fusiona marcas de todos los segmentos (para UNs sin nivel segmento)."""
    fusionadas = {}
    for datos_seg in segmentos.values():
        for marca, dm in datos_seg["marcas"].items():
            if marca not in fusionadas:
                fusionadas[marca] = {"ccc": 0, "tbd": 0.0, "_clientes": set()}
            fusionadas[marca]["tbd"] = round(fusionadas[marca]["tbd"] + dm["tbd"], 2)
            fusionadas[marca]["ccc"] = max(fusionadas[marca]["ccc"], dm["ccc"])
    _render_marcas_v(fusionadas, key_un)


def _render_arbol_vendedor(arbol, key_prefix):
    st.markdown(_CSS_ARBOL_VND, unsafe_allow_html=True)
    st.caption("CCC = clientes compradores · TBD = Total Brand Distribution. Tocá para expandir.")

    root_key = f"{key_prefix}|root"
    lbl_root = f"Comprador — {_lbl_ccc_tbd(arbol['ccc'], arbol['tbd'])}"

    with st.container(key=f"vnd-ROOT-{_slug(key_prefix)}"):
        if st.button(lbl_root, key=root_key, use_container_width=True):
            _toggle_v(root_key); st.rerun()

        if not _esta_abierto_v(root_key):
            return

        un_items  = list(arbol["uns"].items())
        un_keys   = [f"{key_prefix}|u|{u}" for u, _ in un_items]
        open_un   = next((k for k in un_keys if _esta_abierto_v(k)), None)

        for un, datos_un in un_items:
            key_un = f"{key_prefix}|u|{un}"
            if open_un and key_un != open_un:
                continue
            with st.container(key=f"vnd-UN-{_slug(key_un)}"):
                lbl_un = f"{un} — {_lbl_ccc_tbd(datos_un['ccc'], datos_un['tbd'])}"
                if st.button(lbl_un, key=key_un, use_container_width=True):
                    _abrir_exclusivo_v(key_un, un_keys); st.rerun()
                if _esta_abierto_v(key_un):
                    n = str(un).strip().upper()
                    if any(ref in n or n in ref for ref in _UN_CON_SEG):
                        _render_segmentos_v(datos_un["segmentos"], key_un)
                    else:
                        _render_marcas_directo_v(datos_un["segmentos"], key_un)


# ── render volumen vendedor ───────────────────────────────────────────────────

def _render_volumen_vendedor(vendedor_cod):
    st.markdown("#### Volumen de la cartera")
    datos = calcular_vol_vendedor(vendedor_cod)
    for m in datos["metricas"].values():
        m.setdefault("ult_visita", 0)
    _render_tabla_volumen(
        datos["metricas"],
        lbl_ac=_label_mes(datos["periodos"]["actual"]),
        con_ult=False,
    )


# ── render avance de ventas ──────────────────────────────────────────────────

_CSS_AVANCE = """
<style>
/* ── usa variables de Streamlit para funcionar en tema claro y oscuro ── */
.av-tabla { width:100%; border-collapse:collapse; font-size:0.82rem; }
.av-tabla th {
  background: rgba(128,128,128,0.15);
  color: var(--text-color);
  opacity: 0.7;
  padding:5px 8px; text-align:right; font-weight:600; font-size:0.73rem;
  border-bottom: 2px solid rgba(128,128,128,0.25);
}
.av-tabla th:first-child { text-align:left; }
.av-tabla td {
  padding:5px 8px; text-align:right;
  color: var(--text-color);
  border-top: 1px solid rgba(128,128,128,0.12);
}
.av-tabla td:first-child { text-align:left; }
.av-tabla tr.tot td {
  background: rgba(128,128,200,0.15);
  font-weight:700;
  border-top: 2px solid rgba(128,128,200,0.3);
}
.av-tabla tr.sub td {
  background: rgba(128,128,128,0.06);
  opacity: 0.85;
}
.av-tabla tr.sub td:first-child { padding-left:1.4rem; }
.av-tabla tr.sep td { height:4px; padding:0; border:none; background:transparent; }
.av-tabla tr.stot td {
  background: rgba(100,120,200,0.12);
  font-weight:600; font-style:italic;
  border-top: 1px solid rgba(100,120,200,0.3);
}
.av-pos { color:#1d9e52; font-weight:600; }
.av-neg { color:#cc2222; font-weight:600; }
.av-warn { color:#c07000; font-weight:600; }
.av-card {
  background: var(--secondary-background-color);
  border-radius:10px; padding:12px 16px; margin-bottom:8px;
  border: 1px solid rgba(128,128,128,0.15);
}
.av-univ { display:flex; gap:8px; flex-wrap:wrap; }
.av-chip {
  background: rgba(128,128,128,0.1);
  border-radius:6px; padding:5px 10px; font-size:0.79rem;
  border: 1px solid rgba(128,128,128,0.2);
}
.av-chip .ch-name {
  color: var(--text-color); opacity:0.55;
  font-size:0.68rem; display:block; font-weight:600;
  letter-spacing:.04em; text-transform:uppercase;
}
.av-chip .ch-tot { color: var(--text-color); font-size:1.0rem; font-weight:700; display:block; line-height:1.2; }
.av-chip .ch-sub { font-size:0.70rem; }
.av-chip .ch-alc { color:#1d9e52; }
.av-chip .ch-nalc { color: var(--text-color); opacity:0.5; }
.av-tot-bar {
  background: var(--secondary-background-color);
  border-radius:10px; padding:14px 18px; margin-top:10px;
  display:flex; gap:24px; flex-wrap:wrap; align-items:center;
  border: 1px solid rgba(128,128,128,0.2);
}
.av-tot-lbl { color: var(--text-color); opacity:0.55; font-size:0.78rem; }
.av-tot-val { color: var(--text-color); font-size:1.05rem; font-weight:700; }
.av-tot-val.green { color:#1d9e52; }
.av-tabla td, .av-tabla th { padding:4px 5px; font-size:0.78rem; }
.av-tabla tr.sub td:first-child { padding-left:0.8rem; }
.av-tot-bar { gap:14px; padding:10px 12px; }
.av-chip { padding:4px 7px; }
</style>
"""

def _pct(v):
    if not v: return "—"
    return f"{v*100:.1f}%"

def _hl(v):
    if not v: return "—"
    return f"{v:.2f}"

def _pesos(v):
    if not v: return "—"
    try:
        return f"${int(round(float(v))):,}".replace(",", ".")
    except Exception:
        return "—"

def _tend_cls(ava):
    if not ava: return ""
    if ava >= 0.95: return "av-pos"
    if ava >= 0.80: return "av-warn"
    return "av-neg"

def _render_avance(vendedor_cod):
    datos = cargar_avance_vendedor(vendedor_cod)
    if datos is None:
        st.info("No se encontró hoja de avance para este vendedor.")
        return

    st.markdown(_CSS_AVANCE, unsafe_allow_html=True)
    cab = datos["cabecera"]

    # ── Cabecera: fecha + universo ─────────────────────────────────────────
    st.markdown(
        f"#### Avance {cab['mes']} — Día {cab['dia']}/{cab['dias_mes']} ({cab['dia_sem']})"
    )

    canales = ["TRAD","KIOS","K+T","AUTO","REFR","MAYO","TOTAL"]
    univ_html = ""
    for c in canales:
        u = int(cab["universo"].get(c, 0))
        cer = int(cab["cer"].get(c, 0))
        no_cer = int(cab["no_cer"].get(c, 0))
        if u == 0 and c != "TOTAL": continue
        univ_html += (
            f'<div class="av-chip">'
            f'<span class="ch-name">{c}</span>'
            f'<span class="ch-tot">{u}</span>'
            f'<span class="ch-sub"><span class="ch-alc">Alc.{cer}</span>'
            f' <span class="ch-nalc">N/Alc.{no_cer}</span></span>'
            f'</div>'
        )
    st.markdown(
        f'<div class="av-card"><div class="av-univ">{univ_html}</div></div>',
        unsafe_allow_html=True,
    )

    # ── Toggle expandir columnas ──────────────────────────────────────────
    exp_key = f"av_expanded_{vendedor_cod}"
    if exp_key not in st.session_state:
        st.session_state[exp_key] = False
    col_btn, _ = st.columns([1, 3])
    with col_btn:
        lbl_btn = "▲ Ver menos" if st.session_state[exp_key] else "▼ Ver todo"
        if st.button(lbl_btn, key=f"btn_avexp_{vendedor_cod}", use_container_width=True):
            st.session_state[exp_key] = not st.session_state[exp_key]
            st.rerun()
    expanded = st.session_state[exp_key]

    # ── Tabla métricas HL ─────────────────────────────────────────────────
    NCols = 10 if expanded else 5

    def _alc(m):
        v = m.get("premio")
        try:
            f = float(v)
            return _pesos(f) if f else "—"
        except Exception:
            return "—"

    def _td_opt(val):
        return f"<td>{val}</td>" if expanded else ""

    def _fila_hl(nombre, m, cls=""):
        ava = m["ava_tend"]
        td_cls = _tend_cls(ava)
        row_class = f' class="{cls}"' if cls else ""
        return (
            f"<tr{row_class}>"
            f"<td>{nombre}</td>"
            f"<td>{_hl(m['obj'])}</td>"
            f"<td><b>{_hl(m['acu'])}</b></td>"
            f'<td class="{td_cls}">{_pct(ava)}</td>'
            f"<td>{_alc(m)}</td>"
            + _td_opt(_hl(m["tend"]))
            + _td_opt(_hl(m["mnec"]))
            + _td_opt(_hl(m["mreal"]))
            + _td_opt(_hl(m["m7"]))
            + _td_opt(_hl(m["m14"]))
            + "</tr>"
        )

    def _sep():
        return f'<tr class="sep"><td colspan="{NCols}"></td></tr>'

    lista = datos["metricas_hl_lista"]
    tot   = datos["total"]

    _SEP_ANTES = {"UNG TOP", "AGUAS"}
    rows_hl = ""
    for item in lista:
        if item["label"] in _SEP_ANTES:
            rows_hl += _sep()
        rows_hl += _fila_hl(item["label"], item, item["tipo"])

    stot_span = str(NCols - 1)
    rows_hl += (
        _sep()
        + f'<tr class="stot"><td colspan="{stot_span}">Subtotal Alcance $ HL</td>'
          f'<td>{_pesos(tot["subtotal_hl"])}</td></tr>'
    )

    th_opt = "<th>Tend</th><th>Mnec</th><th>Mreal</th><th>-7</th><th>-14</th>" if expanded else ""
    st.markdown(
        '<table class="av-tabla"><thead><tr>'
        '<th>Volumen HL</th><th>Obj</th><th>Acu</th><th>%Tend</th><th>Alcance $</th>'
        + th_opt +
        '</tr></thead>'
        f'<tbody>{rows_hl}</tbody></table>',
        unsafe_allow_html=True,
    )

    # ── Tareas + GMV + subtotal IPs ───────────────────────────────────────
    t = datos["tareas"]
    g = datos["gmv"]
    ava_g = g["ava_tend"]

    tar_rows = ""
    for nombre, td in t.items():
        ava = td["ava_tend"]
        alc_t = _pesos(td.get("obj_pesos", 0)) if td.get("obj_pesos") else "—"
        tar_rows += (
            f"<tr><td>{nombre}</td>"
            f"<td>{_pct(td['obj'])}</td>"
            f"<td><b>{_pct(td['acu'])}</b></td>"
            f'<td class="{_tend_cls(ava)}">{_pct(ava)}</td>'
            f"<td>{alc_t}</td>"
            + _td_opt(_pct(td["tend"]))
            + _td_opt("—") + _td_opt("—") + _td_opt("—") + _td_opt("—")
            + "</tr>"
        )

    tar_rows += (
        f'<tr class="tot"><td>GMV MKPL</td>'
        f'<td>{_pesos(g["obj"])}</td><td><b>{_pesos(g["acu"])}</b></td>'
        f'<td class="{_tend_cls(ava_g)}">{_pct(ava_g)}</td>'
        f'<td>{_pesos(g.get("obj_pesos", 0))}</td>'
        + _td_opt(_pesos(g["tend"]))
        + _td_opt(_pesos(g["mnec"]))
        + _td_opt(_pesos(g["mreal"]))
        + _td_opt(_pesos(g["m7"]))
        + _td_opt(_pesos(g["m14"]))
        + f'</tr>'
        + _sep()
        + f'<tr class="stot"><td colspan="{stot_span}">Subtotal Alcance $ IPs / GMV</td>'
          f'<td>{_pesos(tot["subtotal_ips"])}</td></tr>'
    )

    th_tar_opt = "<th>Tend</th><th>Mnec</th><th>Mreal</th><th>-7</th><th>-14</th>" if expanded else ""
    st.markdown(
        '<table class="av-tabla"><thead><tr>'
        '<th>Tareas / GMV</th><th>Obj</th><th>Acu</th><th>%Tend</th><th>Alcance $</th>'
        + th_tar_opt +
        '</tr></thead>'
        f'<tbody>{tar_rows}</tbody></table>',
        unsafe_allow_html=True,
    )

    # ── Tiempo en PDV / Ruta ───────────────────────────────────────────────
    ti = datos["tiempos"]
    tiempo_rows = ""
    for nombre, td in ti.items():
        cumple = td["cumple"]
        cls_c = "av-pos" if str(cumple).strip().upper() == "SI" else "av-neg"
        tiempo_rows += (
            f"<tr><td>Tiempo en {nombre}</td>"
            f"<td>{td['obj']}</td><td><b>{td['acu']}</b></td>"
            f'<td class="{_tend_cls(td["ratio"])}">{_pct(td["ratio"])}</td>'
            f'<td class="{cls_c}">{cumple}</td></tr>'
        )
    st.markdown(
        '<table class="av-tabla"><thead><tr>'
        '<th>Tiempo PDV</th><th>Obj</th><th>Acu</th><th>%</th><th>Cumple</th>'
        '</tr></thead>'
        f'<tbody>{tiempo_rows}</tbody></table>',
        unsafe_allow_html=True,
    )

    # ── Total Alcance $ ───────────────────────────────────────────────────
    st.markdown(
        f'<div class="av-tot-bar">'
        f'<div><span class="av-tot-lbl">Subtotal HL</span><br>'
        f'<span class="av-tot-val">{_pesos(tot["subtotal_hl"])}</span></div>'
        f'<div style="color:#3a3a6a;font-size:1.3rem">+</div>'
        f'<div><span class="av-tot-lbl">Subtotal IPs / GMV</span><br>'
        f'<span class="av-tot-val">{_pesos(tot["subtotal_ips"])}</span></div>'
        f'<div style="color:#3a3a6a;font-size:1.3rem">=</div>'
        f'<div><span class="av-tot-lbl">Total Alcance $</span><br>'
        f'<span class="av-tot-val green">{_pesos(tot["total_alcance"])}</span></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Escalas ────────────────────────────────────────────────────────────
    with st.expander("Escalas de bonificación"):
        esc_rows = ""
        for e in datos["escalas"]:
            esc_rows += f"<tr><td>{e['label']}</td><td>{_pct(e['alcance'])}</td><td>{_pct(e['volumen'])}</td></tr>"
        st.markdown(
            '<table class="av-tabla"><thead><tr><th>Tramo</th><th>Alcance</th><th>Vol</th></tr></thead>'
            f'<tbody>{esc_rows}</tbody></table>',
            unsafe_allow_html=True,
        )


# ── vista principal ───────────────────────────────────────────────────────────

def render():
    st.subheader("Ficha de Vendedor")

    if "vendedor_autenticado" not in st.session_state:
        st.session_state.vendedor_autenticado = None

    if st.session_state.vendedor_autenticado is None:
        st.caption("Ingresá el número de vendedor.")
        numero = st.text_input("Número de vendedor", placeholder="Ej: 221")
        if st.button("Ingresar"):
            try:
                vendedor_cod = int(numero.strip())
            except ValueError:
                st.error("Ingresá un número de vendedor válido.")
                return
            estructura = cargar_estructura_comercial()
            if estructura[estructura["vendedor_cod"] == vendedor_cod].empty:
                st.error(f"No se encontró el vendedor N° {vendedor_cod}.")
            else:
                st.session_state.vendedor_autenticado = vendedor_cod
                st.rerun()
        return

    vendedor_cod = st.session_state.vendedor_autenticado
    if st.button("↩ Cerrar sesión"):
        st.session_state.vendedor_autenticado = None
        st.session_state.pop("arbol_vnd", None)
        st.rerun()

    # ── KPIs ──────────────────────────────────────────────────────────────────
    _logo_path = os.path.join(os.path.dirname(__file__), "logo_palco.png")
    with open(_logo_path, "rb") as _f:
        _logo = base64.b64encode(_f.read()).decode()
    _splash = st.empty()
    _splash.markdown(_SPLASH_CSS.format(logo=_logo), unsafe_allow_html=True)
    kpis  = kpis_vendedor(vendedor_cod)

    arbol = construir_arbol_vendedor(vendedor_cod)
    _splash.empty()

    est = kpis["estructura"]
    if est:
        st.markdown(f"### {est.get('vendedor_nombre','—')}")
        st.caption(f"Supervisor: {est.get('supervisor_nombre','—')} · Zona: {est.get('zona','—')}")
    else:
        st.markdown(f"### Vendedor {vendedor_cod}")

    dias_desact = dias_desde_actualizacion_seguimiento()
    if dias_desact is not None and dias_desact > 3:
        st.warning(
            f"⚠️ Las visitas planificadas y datos de cobertura no se actualizan hace "
            f"**{dias_desact} días** — falta correr el .bat de reporte_visitas_vendedor."
        )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Cartera total",    kpis["cartera_total"])
    k2.metric("Cartera alcohol",  kpis["cartera_alcohol"])
    k3.metric(f"Visitas {kpis['dia_semana']}", kpis["visitas_hoy_plan"])
    k4.metric("Eficiencia venta", kpis["eficiencia_venta"])

    st.divider()

    # ── Avance de ventas ──────────────────────────────────────────────────────
    st.markdown("#### Avance de ventas")
    _render_avance(vendedor_cod)

    st.divider()

    # ── Analytics: tendencia + mix + top marcas (un solo cálculo cacheado) ──
    analytics_vnd = calcular_analytics_vendedor(vendedor_cod)

    st.markdown("#### Tendencia de volumen cartera")
    render_tendencia(analytics_vnd["tendencia"], key_prefix=f"vnd{vendedor_cod}")

    st.divider()

    st.markdown("#### Mix por segmento YTD")
    render_mix_segmento(analytics_vnd["mix"], key_prefix=f"vnd{vendedor_cod}")

    st.divider()

    st.markdown("#### Top marcas YTD")
    render_top_marcas(analytics_vnd["top_por_un"], key_prefix=f"vnd{vendedor_cod}")

    st.divider()

    st.markdown("#### Censo Thomas — Share of Market por segmento")
    censo_vnd = calcular_censo_vendedor(vendedor_cod)
    censo_empresa = calcular_censo_empresa()
    render_censo_vendedor(censo_vnd, key_prefix=f"vnd{vendedor_cod}", empresa=censo_empresa)

    st.divider()

    st.markdown("#### Coaching")
    coaching_vnd = calcular_coaching_vendedor(vendedor_cod)
    render_coaching_vendedor(coaching_vnd, key_prefix=f"vnd{vendedor_cod}")

    st.divider()

    # ── Árbol CCC / TBD ───────────────────────────────────────────────────────
    st.markdown("#### Árbol de cobertura de cartera")
    hoy = datetime.date.today()
    st.caption(f"Mes: {_MESES_ES[hoy.month-1]} {hoy.year}")
    if not arbol["uns"]:
        st.info("Sin compras registradas para este mes en la cartera.")
    else:
        _render_arbol_vendedor(arbol, f"vnd{vendedor_cod}")
