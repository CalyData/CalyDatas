"""Bloques visuales compartidos: tendencia, mix por segmento, top marcas."""

import streamlit as st

_MESES_ES = ["Ene","Feb","Mar","Abr","May","Jun","Jul","Ago","Sep","Oct","Nov","Dic"]

def _lbl_mes(am):
    return _MESES_ES[am[1] - 1]


# ── Tendencia (SVG inline) ────────────────────────────────────────────────────

def _render_tendencia_chart(meses, principal, secundaria, color_p, color_s, lbl_p, lbl_s):
    """Gráfico de barras de la serie principal HL con línea de la serie secundaria."""
    cerveza   = principal
    abovecore = secundaria

    if not any(cerveza):
        st.caption("Sin datos de tendencia.")
        return

    W, H       = 320, 160
    pad_l, pad_r, pad_t, pad_b = 12, 12, 28, 28
    inner_w    = W - pad_l - pad_r
    inner_h    = H - pad_t - pad_b
    n          = len(meses)
    cw         = inner_w / n
    bar_w      = cw * 0.52
    max_val    = max(max(cerveza), 0.1)

    def _y(v):
        return pad_t + inner_h * (1 - v / max_val)

    bars = []
    ac_pts = []

    for i, (am, cz, ac) in enumerate(zip(meses, cerveza, abovecore)):
        cx  = pad_l + cw * i + cw / 2
        bx  = cx - bar_w / 2
        y_cz = _y(cz)
        h_cz = H - pad_b - y_cz

        # Barra principal
        bars.append(
            f'<rect x="{bx:.1f}" y="{y_cz:.1f}" width="{bar_w:.1f}" height="{h_cz:.1f}" '
            f'rx="3" fill="{color_p}" opacity="0.82"/>'
        )
        # Barra secundaria encima
        if ac > 0:
            y_ac = _y(ac)
            h_ac = H - pad_b - y_ac
            bars.append(
                f'<rect x="{bx:.1f}" y="{y_ac:.1f}" width="{bar_w:.1f}" height="{h_ac:.1f}" '
                f'rx="3" fill="{color_s}" opacity="0.9"/>'
            )

        # Valor principal encima de la barra — más grande y visible
        if cz > 0:
            bars.append(
                f'<text x="{cx:.1f}" y="{y_cz - 6:.1f}" text-anchor="middle" '
                f'font-size="11" font-weight="700" fill="#a8c8ff">{cz:.1f}</text>'
            )
        # Valor secundario (pequeño, encima de su barra)
        if ac > 0:
            y_ac = _y(ac)
            bars.append(
                f'<text x="{cx + bar_w/2 + 2:.1f}" y="{y_ac - 3:.1f}" text-anchor="start" '
                f'font-size="9" fill="{color_s}">{ac:.1f}</text>'
            )

        # Etiqueta mes en el fondo
        bars.append(
            f'<text x="{cx:.1f}" y="{H - pad_b + 14}" text-anchor="middle" '
            f'font-size="11" fill="rgba(180,180,180,0.85)">{_lbl_mes(am)}</text>'
        )

        ac_pts.append((cx, _y(ac) if ac > 0 else H - pad_b))

    # Línea secundaria
    if len(ac_pts) >= 2 and any(ac > 0 for ac in abovecore):
        pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in ac_pts)
        bars.append(f'<polyline points="{pts}" fill="none" stroke="{color_s}" stroke-width="1.5" stroke-dasharray="5,3" opacity="0.7"/>')

    # Leyenda arriba
    legend = (
        f'<rect x="{pad_l}" y="6" width="11" height="10" rx="2" fill="{color_p}" opacity="0.82"/>'
        f'<text x="{pad_l+14}" y="15" font-size="10" fill="rgba(180,180,180,0.85)">{lbl_p}</text>'
        f'<rect x="{pad_l+72}" y="6" width="11" height="10" rx="2" fill="{color_s}" opacity="0.9"/>'
        f'<text x="{pad_l+86}" y="15" font-size="10" fill="rgba(180,180,180,0.85)">{lbl_s}</text>'
    )

    svg = (
        f'<svg viewBox="0 0 {W} {H}" xmlns="http://www.w3.org/2000/svg" '
        f'style="width:100%;max-width:{W}px;height:auto;display:block;">'
        + legend
        + "".join(bars)
        + "</svg>"
    )
    st.markdown(svg, unsafe_allow_html=True)


def render_tendencia(datos: dict, key_prefix: str = "tend"):
    """Toggle Cerveza/UNG + gráfico de barras HL con línea de sub-segmento.
    datos = {"meses","cerveza","above_core","ung","ung_top"}
    """
    tab_key = f"{key_prefix}_tend_un"
    if tab_key not in st.session_state:
        st.session_state[tab_key] = "cerveza"

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🍺 Cerveza", key=f"{key_prefix}_tend_btn_cz",
                     use_container_width=True,
                     type="primary" if st.session_state[tab_key] == "cerveza" else "secondary"):
            st.session_state[tab_key] = "cerveza"
            st.rerun()
    with c2:
        if st.button("🥤 UNG", key=f"{key_prefix}_tend_btn_ung",
                     use_container_width=True,
                     type="primary" if st.session_state[tab_key] == "ung" else "secondary"):
            st.session_state[tab_key] = "ung"
            st.rerun()

    meses = datos["meses"]
    if st.session_state[tab_key] == "cerveza":
        _render_tendencia_chart(
            meses, datos["cerveza"], datos["above_core"],
            "#1a6eb5", "#f4c542", "Cerveza", "Above Core",
        )
    else:
        _render_tendencia_chart(
            meses, datos.get("ung", []), datos.get("ung_top", []),
            "#c0392b", "#f4c542", "UNG", "UNG Top",
        )


# ── Mix por segmento ──────────────────────────────────────────────────────────

_CSS_MIX = """
<style>
.mix-bar-outer { background:rgba(128,128,128,0.12); border-radius:6px; height:14px; margin:3px 0; overflow:hidden; }
.mix-bar-inner { height:14px; border-radius:6px; }
.mix-row { display:flex; align-items:center; gap:8px; margin:4px 0; font-size:0.82rem; }
.mix-lbl { min-width:110px; color:var(--text-color); opacity:0.85; }
.mix-pct { min-width:42px; text-align:right; font-weight:600; color:var(--text-color); }
.mix-hl  { min-width:52px; text-align:right; font-size:0.75rem; color:var(--text-color); opacity:0.6; }
.mix-title { font-size:0.78rem; font-weight:700; color:var(--text-color); opacity:0.6;
             text-transform:uppercase; letter-spacing:.05em; margin:8px 0 4px; }
</style>
"""

def _barra(pct, color):
    w = min(max(pct, 0), 100)
    return (
        f'<div class="mix-bar-outer">'
        f'<div class="mix-bar-inner" style="width:{w:.1f}%;background:{color};"></div>'
        f'</div>'
    )

def _fila_mix(lbl, hl_seg, hl_total, color):
    pct = (hl_seg / hl_total * 100) if hl_total > 0 else 0
    return (
        f'<div class="mix-row">'
        f'<span class="mix-lbl">{lbl}</span>'
        f'<div style="flex:1">{_barra(pct, color)}</div>'
        f'<span class="mix-pct">{pct:.1f}%</span>'
        f'<span class="mix-hl">{hl_seg:.1f} HL</span>'
        f'</div>'
    )

def render_mix_segmento(datos: dict, key_prefix: str = "mix"):
    """Toggle Cerveza / UNG con barras de segmento."""
    st.markdown(_CSS_MIX, unsafe_allow_html=True)

    tab_key = f"{key_prefix}_tab_mix"
    if tab_key not in st.session_state:
        st.session_state[tab_key] = "cerveza"

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🍺 Cerveza", key=f"{key_prefix}_btn_cz",
                     use_container_width=True,
                     type="primary" if st.session_state[tab_key] == "cerveza" else "secondary"):
            st.session_state[tab_key] = "cerveza"
            st.rerun()
    with c2:
        if st.button("🥤 UNG", key=f"{key_prefix}_btn_ung",
                     use_container_width=True,
                     type="primary" if st.session_state[tab_key] == "ung" else "secondary"):
            st.session_state[tab_key] = "ung"
            st.rerun()

    sel = st.session_state[tab_key]
    if sel == "cerveza":
        d = datos["cerveza"]
        if d["total_hl"] == 0:
            st.caption("Sin ventas de Cerveza en el año.")
            return
        base = d["core_value"] + d["above_core"]
        html = (
            f'<div class="mix-title">MIX Cerveza YTD · {d["total_hl"]:.1f} HL total</div>'
            + _fila_mix("Core-Value", d["core_value"], base, "#1a6eb5")
            + _fila_mix("Above Core", d["above_core"], base, "#0a3d78")
        )
    else:
        d = datos["ung"]
        if d["total_hl"] == 0:
            st.caption("Sin ventas de UNG en el año.")
            return
        dv = d.get("del_valle", 0)
        base = d["ung_top"] + d["resto_ung"] + dv
        html = (
            f'<div class="mix-title">MIX UNG YTD · {d["total_hl"]:.1f} HL total</div>'
            + _fila_mix("UNG Top",    d["ung_top"],  base, "#c0392b")
            + _fila_mix("Resto UNG",  d["resto_ung"], base, "#e67e22")
            + (_fila_mix("Del Valle", dv, base, "#8e44ad") if dv > 0 else "")
        )
    st.markdown(html, unsafe_allow_html=True)


# ── Top marcas por Unidad de Negocio ─────────────────────────────────────────

_CSS_TOP = """
<style>
.top-row { display:flex; align-items:center; gap:8px; margin:4px 0; font-size:0.82rem; }
.top-lbl { min-width:130px; color:var(--text-color); opacity:0.9;
           white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.top-bar-outer { flex:1; background:rgba(128,128,128,0.12); border-radius:5px; height:12px; overflow:hidden; }
.top-bar-inner { height:12px; border-radius:5px; }
.top-hl  { min-width:52px; text-align:right; font-size:0.75rem; font-weight:600;
           color:var(--text-color); opacity:0.75; }
.top-title { font-size:0.78rem; font-weight:700; color:var(--text-color); opacity:0.6;
             text-transform:uppercase; letter-spacing:.05em; margin:4px 0 8px; }
</style>
"""

_UN_LABELS = {
    "CERVEZAS CMQ":         "🍺 Cerveza",
    "UNG":                  "🥤 UNG",
    "AGUAS ECO":            "💧 Aguas",
    "MARKETPLACE ALIMENTOS":"🛒 Mkpl",
    "VINO":                 "🍷 Vino",
    "ADYACENCIAS":          "➕ Adyac.",
}
_UN_COLORS = {
    "CERVEZAS CMQ":          ["#1a6eb5","#2980b9","#3498db","#5dade2","#85c1e9","#aed6f1"],
    "UNG":                   ["#c0392b","#e74c3c","#ec7063","#f1948a","#f5b7b1","#fadbd8"],
    "AGUAS ECO":             ["#1abc9c","#2ecc71","#58d68d","#82e0aa","#a9dfbf","#d5f5e3"],
    "MARKETPLACE ALIMENTOS": ["#8e44ad","#9b59b6","#af7ac5","#c39bd3","#d7bde2","#e8daef"],
    "VINO":                  ["#922b21","#a93226","#c0392b","#e74c3c","#ec7063","#f1948a"],
    "ADYACENCIAS":           ["#d35400","#e67e22","#f39c12","#f8c471","#fad7a0","#fef9e7"],
}

def render_top_marcas(top_por_un: dict, key_prefix: str = "top"):
    """Ranking de marcas por UN con toggle entre UNs disponibles."""
    if not top_por_un:
        st.caption("Sin datos de marcas.")
        return

    st.markdown(_CSS_TOP, unsafe_allow_html=True)

    uns_disponibles = list(top_por_un.keys())
    tab_key = f"{key_prefix}_top_un"
    if tab_key not in st.session_state or st.session_state[tab_key] not in uns_disponibles:
        st.session_state[tab_key] = uns_disponibles[0]

    # Botones de UN (en columnas)
    n_cols = min(len(uns_disponibles), 4)
    cols = st.columns(n_cols)
    for i, un in enumerate(uns_disponibles):
        lbl = _UN_LABELS.get(un, un.split()[0])
        tipo = "primary" if st.session_state[tab_key] == un else "secondary"
        with cols[i % n_cols]:
            if st.button(lbl, key=f"{key_prefix}_top_btn_{un}", use_container_width=True, type=tipo):
                st.session_state[tab_key] = un
                st.rerun()

    sel_un  = st.session_state[tab_key]
    entrada = top_por_un.get(sel_un)
    if not entrada:
        st.caption("Sin ventas en esta UN.")
        return

    lista    = entrada["items"]
    unidad   = entrada["unidad"]
    colors   = _UN_COLORS.get(sel_un, ["#1a6eb5"] * 6)
    max_val  = lista[0]["valor"] if lista else 1
    un_label = _UN_LABELS.get(sel_un, sel_un)
    total_un = sum(x["valor"] for x in lista)
    fmt_total = f"{total_un:.0f}" if unidad == "Blt" else f"{total_un:.1f}"

    html = f'<div class="top-title">{un_label} — Top marcas YTD · {fmt_total} {unidad}</div>'
    for i, item in enumerate(lista):
        w     = (item["valor"] / max_val * 100) if max_val > 0 else 0
        color = colors[min(i, len(colors) - 1)]
        fmt_v = f"{item['valor']:.0f}" if unidad == "Blt" else f"{item['valor']:.1f}"
        html += (
            f'<div class="top-row">'
            f'<span class="top-lbl">{item["marca"]}</span>'
            f'<div class="top-bar-outer">'
            f'<div class="top-bar-inner" style="width:{w:.1f}%;background:{color};"></div>'
            f'</div>'
            f'<span class="top-hl">{fmt_v} {unidad}</span>'
            f'</div>'
        )
    st.markdown(html, unsafe_allow_html=True)


# ── Censo Thomas — SOM (Share of Market) en torta ────────────────────────────

_CSS_PIE = """
<style>
.pie-wrap { display:flex; align-items:center; gap:18px; flex-wrap:wrap; justify-content:center; }
.pie-legend { display:flex; flex-direction:column; gap:6px; }
.pie-leg-row { display:flex; align-items:center; gap:8px; font-size:0.85rem; color:var(--text-color); }
.pie-leg-dot { width:11px; height:11px; border-radius:3px; flex-shrink:0; }
.pie-leg-pct { font-weight:700; min-width:42px; }
.pie-leg-hl { opacity:0.55; font-size:0.75rem; }
.pie-title { font-size:0.78rem; font-weight:700; color:var(--text-color); opacity:0.6;
             text-transform:uppercase; letter-spacing:.05em; margin:6px 0; text-align:center; }
</style>
"""

_COLOR_CMQ   = "#1a6eb5"
_COLOR_CCU   = "#c0392b"
_COLOR_OTROS = "#7f8c8d"

def _donut_svg(pct_cmq, pct_ccu, pct_otros, size=140):
    r = size * 0.34
    cx = cy = size / 2
    stroke_w = size * 0.22
    circ = 2 * 3.14159265 * r

    segs = [(pct_cmq, _COLOR_CMQ), (pct_ccu, _COLOR_CCU), (pct_otros, _COLOR_OTROS)]
    parts = []
    offset = 0.0
    for pct, color in segs:
        if pct <= 0:
            continue
        dash = circ * pct / 100
        gap  = circ - dash
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{color}" '
            f'stroke-width="{stroke_w}" stroke-dasharray="{dash:.2f} {gap:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})"/>'
        )
        offset += dash

    r_centro = r - stroke_w / 2 - 2
    return (
        f'<svg viewBox="0 0 {size} {size}" width="{size}" height="{size}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        + "".join(parts) +
        f'<circle cx="{cx}" cy="{cy}" r="{r_centro:.1f}" fill="#1c1c2e"/>'
        f'<text x="{cx}" y="{cy+5}" text-anchor="middle" font-size="{size*0.16:.0f}" '
        f'font-weight="700" fill="#ffffff">{pct_cmq:.0f}%</text>'
        f'</svg>'
    )

def render_pie_censo(datos: dict, titulo: str = ""):
    """Dona con % CMQ / CCU / Otros (Share of Market, censo Thomas).
    datos = {"pct_cmq","pct_ccu","pct_otros","hl_cmq","hl_ccu","hl_otros"}
    """
    if datos is None or (datos["pct_cmq"] + datos["pct_ccu"] + datos["pct_otros"]) == 0:
        st.caption("Sin datos de censo.")
        return

    st.markdown(_CSS_PIE, unsafe_allow_html=True)
    if titulo:
        st.markdown(f'<div class="pie-title">{titulo}</div>', unsafe_allow_html=True)

    svg = _donut_svg(datos["pct_cmq"], datos["pct_ccu"], datos["pct_otros"])

    con_hl = (datos["hl_cmq"] + datos["hl_ccu"] + datos["hl_otros"]) > 0
    def _hl_span(v):
        return f'<span class="pie-leg-hl">{v:.1f} HL</span>' if con_hl else ""

    legend = (
        '<div class="pie-legend">'
        f'<div class="pie-leg-row"><span class="pie-leg-dot" style="background:{_COLOR_CMQ}"></span>'
        f'CMQ <span class="pie-leg-pct">{datos["pct_cmq"]:.0f}%</span>'
        f'{_hl_span(datos["hl_cmq"])}</div>'
        f'<div class="pie-leg-row"><span class="pie-leg-dot" style="background:{_COLOR_CCU}"></span>'
        f'CCU <span class="pie-leg-pct">{datos["pct_ccu"]:.0f}%</span>'
        f'{_hl_span(datos["hl_ccu"])}</div>'
        f'<div class="pie-leg-row"><span class="pie-leg-dot" style="background:{_COLOR_OTROS}"></span>'
        f'Otros <span class="pie-leg-pct">{datos["pct_otros"]:.0f}%</span>'
        f'{_hl_span(datos["hl_otros"])}</div>'
        '</div>'
    )
    st.markdown(f'<div class="pie-wrap">{svg}{legend}</div>', unsafe_allow_html=True)


_CSS_EMPRESA_REF = """
<style>
.censo-empresa {
  display:flex; gap:14px; justify-content:center; flex-wrap:wrap;
  margin-top:10px; padding:8px 14px;
  background: rgba(128,128,128,0.08); border-radius:8px;
  font-size:0.78rem;
}
.censo-empresa-title {
  width:100%; text-align:center; font-weight:700; opacity:0.55;
  text-transform:uppercase; letter-spacing:.05em; font-size:0.68rem;
  color: var(--text-color); margin-bottom:2px;
}
.censo-empresa span { color: var(--text-color); }
.censo-empresa b { font-weight:700; }
</style>
"""

def render_censo_vendedor(segmentos: dict, key_prefix: str = "censo", empresa: dict | None = None):
    """Toggle entre segmentos (Total/Super Premium/Premium/Core Plus/Core/Value) + dona SOM.
    Si se pasa `empresa`, muestra debajo el dato fijo de referencia a nivel compañía."""
    if not segmentos:
        st.caption("Sin datos de censo para este vendedor.")
        return

    tab_key = f"{key_prefix}_censo_seg"
    nombres = list(segmentos.keys())
    if tab_key not in st.session_state or st.session_state[tab_key] not in nombres:
        st.session_state[tab_key] = nombres[0]

    n_cols = 3
    filas = [nombres[i:i + n_cols] for i in range(0, len(nombres), n_cols)]
    for fila_nombres in filas:
        cols = st.columns(n_cols)
        for i, seg in enumerate(fila_nombres):
            tipo = "primary" if st.session_state[tab_key] == seg else "secondary"
            with cols[i]:
                if st.button(seg, key=f"{key_prefix}_censo_btn_{seg}", use_container_width=True, type=tipo):
                    st.session_state[tab_key] = seg
                    st.rerun()

    sel = st.session_state[tab_key]
    render_pie_censo(segmentos[sel], titulo=f"SOM — {sel}")

    if empresa and sel in empresa:
        d = empresa[sel]
        st.markdown(_CSS_EMPRESA_REF, unsafe_allow_html=True)
        st.markdown(
            '<div class="censo-empresa">'
            '<div class="censo-empresa-title">Resultado Grupo Palco</div>'
            f'<span>CMQ <b>{d["pct_cmq"]:.0f}%</b></span>'
            f'<span>CCU <b>{d["pct_ccu"]:.0f}%</b></span>'
            f'<span>Otros <b>{d["pct_otros"]:.0f}%</b></span>'
            '</div>',
            unsafe_allow_html=True,
        )


# ── Coaching ──────────────────────────────────────────────────────────────────

_CSS_COACHING = """
<style>
.coach-card {
  background: var(--secondary-background-color);
  border-radius: 10px; padding: 12px 16px; margin-bottom: 10px;
  border: 1px solid rgba(128,128,128,0.15);
}
.coach-meta { display:flex; gap:16px; flex-wrap:wrap; font-size:0.78rem;
              color: var(--text-color); opacity:0.7; margin-bottom:10px; }
.coach-meta b { opacity:1; }
.coach-row { display:flex; align-items:center; gap:8px; margin:5px 0; font-size:0.85rem; }
.coach-lbl { min-width:170px; color: var(--text-color); }
.coach-bar-outer { flex:1; background:rgba(128,128,128,0.12); border-radius:6px; height:14px; overflow:hidden; }
.coach-bar-inner { height:14px; border-radius:6px; }
.coach-pct { min-width:42px; text-align:right; font-weight:700; color: var(--text-color); }
.coach-total { display:flex; align-items:center; gap:8px; margin-top:10px; padding-top:8px;
               border-top:1px solid rgba(128,128,128,0.2); font-size:0.92rem; font-weight:700; }
.coach-plan-ok  { color:#1d9e52; font-weight:700; }
.coach-plan-no  { color:#cc2222; font-weight:700; }
.coach-devol {
  background: rgba(192,57,43,0.10);
  border-left: 3px solid #c0392b;
  border-radius: 6px; padding: 10px 14px; margin-bottom: 12px;
  font-size: 0.85rem; color: var(--text-color); line-height: 1.4;
}
.coach-q-row { display:flex; justify-content:space-between; gap:10px;
               font-size:0.78rem; padding:4px 0; border-top:1px solid rgba(128,128,128,0.1); }
.coach-q-row:first-child { border-top:none; }
.coach-q-text { color: var(--text-color); opacity:0.85; flex:1; }
.coach-q-score { font-weight:700; color: var(--text-color); opacity:0.7; flex-shrink:0; }
</style>
"""

def _color_pct(pct):
    if pct >= 80: return "#1d9e52"
    if pct >= 60: return "#c07000"
    return "#cc2222"

def render_coaching_vendedor(coachings: dict, key_prefix: str = "coach"):
    """Toggle entre coachings disponibles (Coaching 1, 2, 3...) + detalle por pilar."""
    if not coachings:
        st.caption("Sin coachings registrados para este vendedor.")
        return

    st.markdown(_CSS_COACHING, unsafe_allow_html=True)

    nombres = sorted(coachings.keys())
    tab_key = f"{key_prefix}_coach_sel"
    if tab_key not in st.session_state or st.session_state[tab_key] not in nombres:
        st.session_state[tab_key] = nombres[0]

    cols = st.columns(len(nombres))
    for i, nom in enumerate(nombres):
        tipo = "primary" if st.session_state[tab_key] == nom else "secondary"
        with cols[i]:
            if st.button(nom, key=f"{key_prefix}_coach_btn_{nom}", use_container_width=True, type=tipo):
                st.session_state[tab_key] = nom
                st.rerun()

    sel = coachings[st.session_state[tab_key]]
    plan_cls = "coach-plan-ok" if sel["plan_logrado"].strip().lower() == "logrado" else "coach-plan-no"

    meta = (
        '<div class="coach-card">'
        '<div class="coach-meta">'
        f'<span><b>Fecha:</b> {sel["fecha"]}</span>'
        f'<span><b>Supervisor:</b> {sel["supervisor"]}</span>'
        f'<span><b>Plan de acción:</b> <span class="{plan_cls}">{sel["plan_logrado"]}</span></span>'
        '</div></div>'
    )
    st.markdown(meta, unsafe_allow_html=True)

    if sel.get("comentario"):
        st.markdown(
            f'<div class="coach-devol">📝 <b>Punto a mejorar (devolución del supervisor):</b><br>{sel["comentario"]}</div>',
            unsafe_allow_html=True,
        )

    for p in sel["pilares"]:
        color = _color_pct(p["pct"])
        with st.expander(f"{p['nombre']} — {p['pct']:.0f}%", expanded=False):
            bar_html = (
                f'<div class="coach-bar-outer"><div class="coach-bar-inner" '
                f'style="width:{min(p["pct"],100):.0f}%;background:{color};"></div></div>'
            )
            st.markdown(bar_html, unsafe_allow_html=True)
            preg_html = ""
            for q in p.get("preguntas", []):
                preg_html += (
                    '<div class="coach-q-row">'
                    f'<span class="coach-q-text">{q["pregunta"]}</span>'
                    f'<span class="coach-q-score">{q["score"]:.0f}/4</span>'
                    '</div>'
                )
            st.markdown(preg_html, unsafe_allow_html=True)

    total_color = _color_pct(sel["total_pct"])
    total_row = (
        '<div class="coach-total">'
        f'<span>Total</span>'
        f'<span style="color:{total_color}">{sel["total_pct"]:.0f}%</span>'
        '</div>'
    )
    st.markdown(total_row, unsafe_allow_html=True)
