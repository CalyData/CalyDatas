"""Carga y normalización de datos — v2: lee de Supabase (PostgreSQL) en vez de
Excel/Dropbox local para cartera, estructura comercial, artículos, personalización
de visitas y ventas. Avance de vendedores, censo Thomas y coaching siguen leyendo
Excel/Dropbox por ahora (pendiente de migrar en una etapa siguiente)."""
import os
import re as _re
import unicodedata
import datetime

import pandas as pd
import streamlit as st
from sqlalchemy import create_engine
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv(override=True)

# ── Fuentes que TODAVÍA no se migraron a Supabase (Excel/Dropbox local) ───────
BASE = r"C:\Users\palco\Dropbox\ANALISIS COMERCIAL\01_FUENTES"
SEGUIMIENTOS = r"C:\Users\palco\Dropbox\ANALISIS COMERCIAL\03_SEGUIMIENTOS"
REPORTES = r"C:\Users\palco\Dropbox\ANALISIS COMERCIAL\04_REPORTES"
MODELO = r"C:\Users\palco\Dropbox\ANALISIS COMERCIAL\02_MODELO"
CENSO_THOMAS_PATH = MODELO + r"\analisis_resultados_censo_thomas_abr_26.xlsx"

CACHE_DIR = os.path.join(os.path.dirname(__file__), "_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


# ── Conexión a Supabase ────────────────────────────────────────────────────────

@st.cache_resource
def _config(clave: str) -> str:
    """Lee credenciales de st.secrets (Streamlit Cloud) si están disponibles,
    si no cae a variables de entorno / .env (uso local en esta PC)."""
    try:
        if clave in st.secrets:
            return st.secrets[clave]
    except Exception:
        pass
    return os.getenv(clave)


def _engine():
    """Usa sqlalchemy.engine.URL.create en vez de armar el string a mano — evita
    tener que pre-codificar caracteres especiales del password (%, !, ^) nosotros
    mismos, que generaba doble-codificación y fallos de autenticación intermitentes."""
    from sqlalchemy.engine import URL
    url = URL.create(
        "postgresql+psycopg2",
        username=_config("SUPABASE_DB_USER"),
        password=_config("SUPABASE_DB_PASSWORD"),
        host=_config("SUPABASE_DB_HOST"),
        port=int(_config("SUPABASE_DB_PORT")),
        database=_config("SUPABASE_DB_NAME"),
    )
    return create_engine(url, pool_pre_ping=True)


def _query(sql, params=None):
    return pd.read_sql(sql, _engine(), params=params)


# ── Catálogos (desde Supabase) ─────────────────────────────────────────────────

# Vendedores ficticios (no son personas reales que visitan clientes) — sus clientes
# asignados no deben contarse en la cartera/cobertura de NINGÚN vendedor/supervisor/
# jefe/Grupo Palco. Confirmado por el usuario: 98 "INDICADOR ESPECIAL".
VENDEDORES_FICTICIOS = {98}


@st.cache_data(ttl=21600)
def cargar_cartera():
    df = _query("SELECT * FROM clientes")
    df["cliente"] = pd.to_numeric(df["cliente"], errors="coerce")
    df["vendedor_cod"] = pd.to_numeric(df["vendedor_cod"], errors="coerce")
    df = df.dropna(subset=["cliente"])
    if "anulado" in df.columns:
        df = df[df["anulado"].astype(str).str.strip().str.upper() == "NO"]
    if "fv1_anulado" in df.columns:
        df = df[df["fv1_anulado"].astype(str).str.strip().str.upper() == "NO"]
    df = df[~df["vendedor_cod"].isin(VENDEDORES_FICTICIOS)]
    return df


@st.cache_data(ttl=21600)
def cargar_estructura_comercial():
    return _query("SELECT * FROM estructura_comercial")


# Supervisor con vendedores "mayoristas/cadenitas/BDR" — el Jefe de Venta (cod 100)
# se calcula como TODOS los vendedores EXCEPTO los de este supervisor (regla confirmada
# por el usuario); ese supervisor tiene su propio nivel "Ficha Gerencial" aparte.
SUPERVISOR_EXCLUIDO_JEFE = 24


def resolver_grupo_vendedores(codigo: str) -> dict | None:
    """Dado el código ingresado en el login de Ficha Gerencial, devuelve:
    {tipo, nombre, vendedores (lista de vendedor_cod), incluir_lucky, incluir_pana}.
    - Supervisor (21,22,24,26,27,29,...): sus vendedores, CON Lucky y CON PANA (igual
      que la ficha de un vendedor individual).
    - Jefe de Venta ('100'): todos los vendedores MENOS los del supervisor 24, CON
      Lucky y CON PANA.
    - Grupo Palco ('palco'): TODOS los vendedores, SIN Lucky y SIN PANA (venta real
      de proveedor, sin ajustes ni genéricos de canje)."""
    codigo_norm = str(codigo).strip().lower()
    estructura = cargar_estructura_comercial()

    if codigo_norm == "palco":
        vendedores = estructura["vendedor_cod"].dropna().astype(int).tolist()
        return {
            "tipo": "palco", "nombre": "Grupo Palco", "codigo": "palco",
            "vendedores": vendedores, "incluir_lucky": False, "incluir_pana": False,
        }

    try:
        cod_num = int(codigo_norm)
    except ValueError:
        return None

    if cod_num == 100:
        vendedores = (
            estructura[estructura["supervisor_cod"] != SUPERVISOR_EXCLUIDO_JEFE]
            ["vendedor_cod"].dropna().astype(int).tolist()
        )
        return {
            "tipo": "jefe", "nombre": "Jefe de Venta", "codigo": 100,
            "vendedores": vendedores, "incluir_lucky": True, "incluir_pana": True,
        }

    sup_filas = estructura[estructura["supervisor_cod"] == cod_num]
    if sup_filas.empty:
        return None
    vendedores = sup_filas["vendedor_cod"].dropna().astype(int).tolist()
    nombre_sup = sup_filas.iloc[0].get("supervisor_nombre") or f"Supervisor {cod_num}"
    return {
        "tipo": "supervisor", "nombre": nombre_sup, "codigo": cod_num,
        "vendedores": vendedores, "incluir_lucky": True, "incluir_pana": True,
    }


@st.cache_data(ttl=21600)
def cargar_personalizacion_visitas():
    df = _query("SELECT * FROM personalizacion_visitas")
    df["cliente"] = pd.to_numeric(df["cliente"], errors="coerce")
    df["vendedor_cod"] = pd.to_numeric(df["vendedor_cod"], errors="coerce")
    df["eficiencia"] = (
        df["eficiencia_str"].astype(str)
          .str.replace(",", ".", regex=False)
          .pipe(pd.to_numeric, errors="coerce")
    )
    return df.dropna(subset=["cliente"])


@st.cache_data(ttl=21600)
def cargar_articulos():
    """Maestro de artículos — ya viene filtrado a activos/no-anulados desde la migración."""
    return _query("SELECT * FROM articulos")


@st.cache_data(ttl=21600)
def cargar_arbol_segmentos():
    """Compatibilidad: ya no hace falta — 'arbol' viene resuelto directo en cargar_articulos()."""
    return _query("SELECT articulo, arbol FROM articulos")


@st.cache_data(ttl=21600)
def cargar_maestro_arbol():
    """En v1 hacía merge articulos+arbol; en v2 ya viene unido en la tabla 'articulos'."""
    df = _query("SELECT * FROM articulos")
    df["arbol"] = df["arbol"].fillna("SIN SEGMENTO")
    return df


# ── Ventas (desde Supabase — ya unificado histórico + mes actual + API) ───────

_HIST_COLS = ["fecha", "cliente", "articulo", "unidad_negocio", "marca", "calibre", "hl", "bultos", "importe_neto", "fuente"]


@st.cache_data(ttl=900)  # 15 min — la tabla ventas se actualiza por sync incremental
def cargar_historico_compras(anios=("2025", "2026")):
    """En v2 no hace falta concatenar archivos anuales + mes actual — todo está
    unificado en la tabla 'ventas' de Supabase, ya con sync incremental diario.
    Incluye 'fuente' para poder excluir los ajustes Lucky de cálculos que dependen
    de un día real de compra (eficiencia de visita, última compra, etc.) — Lucky
    corrige volumen, no representa una visita/venta real en una fecha específica."""
    anio_min = min(int(a) for a in anios)
    df = _query(
        "SELECT fecha, cliente, articulo, unidad_negocio, marca, calibre, hl, bultos, importe_neto, fuente "
        "FROM ventas WHERE date_part('year', fecha) >= %(anio_min)s",
        params={"anio_min": anio_min},
    )
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    for c in ["hl", "bultos", "importe_neto"]:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df[_HIST_COLS]


# ── Fuentes pendientes de migrar (siguen en Excel/Dropbox) ────────────────────

@st.cache_data(ttl=21600)
def cargar_por_vendedor_semanas():
    """Visitas planificadas por día/semana, desde Supabase (antes leía
    reporte_visitas_vendedor.xlsx hoja 'Por Vendedor' directo)."""
    return _query("SELECT * FROM por_vendedor_semanas")


@st.cache_data(ttl=21600)
def cargar_calendario_laboral() -> set:
    """Fechas del mes en curso que NO son laborables (domingos/feriados) — AVANCE
    DE VENTAS.xlsm hoja 'Planilla', fila 3. Se usa para no contar como 'visita
    perdida' un día que en realidad nadie trabajó."""
    df = _query("SELECT fecha FROM calendario_laboral WHERE NOT laborable")
    return set(pd.to_datetime(df["fecha"]).dt.date)


def semana_actual() -> int:
    """Calcula la 'ourWeek' (1-4) de hoy según la lógica del sistema Palco."""
    hoy = datetime.date.today()
    day_of_year = hoy.timetuple().tm_yday
    week_of_year = (day_of_year - 1) // 7 + 1
    return ((week_of_year - 1) % 4) + 1


@st.cache_data(ttl=21600)
def cargar_seguimiento_visitas():
    """KPIs de visita/efectividad por cliente, desde Supabase (antes leía
    reporte_visitas_vendedor.xlsx hoja 'Listado Clientes' directo)."""
    df = _query("SELECT * FROM seguimiento_visitas")
    df["cliente"] = pd.to_numeric(df["cliente"], errors="coerce")
    return df.dropna(subset=["cliente"])


@st.cache_data(ttl=900)
def dias_desde_actualizacion_seguimiento() -> int | None:
    """reporte_visitas_vendedor.xlsx se actualiza con un .bat que el usuario corre
    MANUALMENTE — devuelve cuántos días pasaron desde la última vez que el archivo
    fuente cambió de verdad (no desde el último sync), para poder alertar si quedó
    desactualizado."""
    df = _query(
        "SELECT ultima_fecha_sync FROM sync_control WHERE tabla = 'reporte_visitas_vendedor_archivo'"
    )
    if df.empty or pd.isna(df.iloc[0]["ultima_fecha_sync"]):
        return None
    mtime = pd.to_datetime(df.iloc[0]["ultima_fecha_sync"])
    if mtime.tzinfo is not None:
        mtime = mtime.tz_localize(None)
    return (datetime.datetime.now() - mtime).days


# ── helpers de eficiencia de visita ──────────────────────────────────────────

def _sem_sistema(fecha):
    return (fecha.isocalendar()[1] - 1) % 4 + 1

def _es_semana_visita_fn(fecha, per, pasa):
    s = _sem_sistema(fecha)
    if per == 1: return True
    if per == 2 and pasa == 1: return s in (1, 3)
    if per == 2 and pasa == 2: return s in (2, 4)
    if per == 4: return s == pasa
    return False

_MAP_DIAS_WD = {"lun":0,"mar":1,"mie":2,"jue":3,"vie":4,"sab":5,"dom":6}
_DIAS_COLS   = list(_MAP_DIAS_WD.keys())

def _calcular_eficiencia(pr_row, fechas_compra_set, hoy, dias_no_laborables=frozenset()):
    """Calcula eficiencia para un cliente dado su row de personalización.
    fechas_compra_set: set de datetime.date con días que tuvo compra en el mes.
    dias_no_laborables: fechas del mes que no se trabajan de verdad (domingos/
    feriados, ver cargar_calendario_laboral) — no cuentan como visita planificada.
    Retorna (visitas_plan, visitas_efectivas).
    Una visita es efectiva si hubo al menos una compra entre esa visita
    y la próxima visita planificada (o fin del período). El día de hoy nunca
    se cuenta como visita planificada: todavía no tuvo tiempo de derivar en venta."""
    per  = int(pr_row["periodicidad"]) if pd.notna(pr_row.get("periodicidad")) else 1
    pasa = int(pr_row["pasa_en"])      if pd.notna(pr_row.get("pasa_en"))      else 1
    dias_wd = {
        _MAP_DIAS_WD[col] for col in _DIAS_COLS
        if col in pr_row.index and str(pr_row[col]).strip().upper() == "X"
    }
    if not dias_wd:
        return 0, 0

    primer_dia = hoy.replace(day=1)
    visitas = []
    d = primer_dia
    while d < hoy:
        if (d.weekday() in dias_wd and _es_semana_visita_fn(d, per, pasa)
                and d not in dias_no_laborables):
            visitas.append(d)
        d += datetime.timedelta(days=1)

    if not visitas:
        return 0, 0

    fin_periodo = hoy
    efectivas = 0
    for i, v in enumerate(visitas):
        fin_window = (visitas[i+1] - datetime.timedelta(days=1)) if i+1 < len(visitas) else fin_periodo
        if any(v <= c <= fin_window for c in fechas_compra_set):
            efectivas += 1

    return len(visitas), efectivas


def datos_cliente(cliente_num):
    """Devuelve dict con toda la info disponible de un cliente puntual."""
    cartera = cargar_cartera()
    fila = cartera[cartera["cliente"] == cliente_num]
    if fila.empty:
        return None
    info = fila.iloc[0].to_dict()

    hoy = datetime.date.today()
    historico = cargar_historico_compras()
    hist_cli = historico[historico["cliente"] == cliente_num].copy()
    hist_cli["fecha"] = pd.to_datetime(hist_cli["fecha"], errors="coerce")
    # Lucky corrige volumen, no representa una visita/venta real en una fecha específica —
    # se excluye de cálculos que dependen del día exacto (última compra, días con compra, eficiencia)
    hist_cli_real = hist_cli[hist_cli["fuente"] != "lucky"]

    ult_ts = hist_cli_real["fecha"].max()
    if pd.notna(ult_ts):
        ult_fmt        = ult_ts.strftime("%d/%m/%y")
        dias_sin_compra = (hoy - ult_ts.date()).days
    else:
        ult_fmt        = "—"
        dias_sin_compra = None

    dias_cc_mes = int(hist_cli_real[
        (hist_cli_real["fecha"].dt.year  == hoy.year) &
        (hist_cli_real["fecha"].dt.month == hoy.month)
    ]["fecha"].dt.date.nunique())

    primer_dia_mes_actual = hoy.replace(day=1)
    hace_3m = (primer_dia_mes_actual - pd.DateOffset(months=3)).date()
    dias_cc_u3m = int(hist_cli_real[
        (hist_cli_real["fecha"].dt.date >= hace_3m) &
        (hist_cli_real["fecha"].dt.date <  primer_dia_mes_actual)
    ]["fecha"].dt.date.nunique())

    pers = cargar_personalizacion_visitas()
    p_row = pers[pers["cliente"] == cliente_num]

    if not p_row.empty:
        pr = p_row.iloc[0]
        per    = int(pr["periodicidad"]) if pd.notna(pr.get("periodicidad")) else 1
        pasa   = int(pr["pasa_en"])      if pd.notna(pr.get("pasa_en"))      else 1
        _dias_cols = ["lun","mar","mie","jue","vie","sab","dom"]
        n_dias_asig = sum(
            1 for col in _dias_cols
            if col in pr.index and str(pr[col]).strip().lower() not in ("", "nan", "none", "0")
        )
        if per == 1 and n_dias_asig >= 2:
            per_desc  = "Bi-semanal"
            sem_visita = "Todas"
            frecuencia = 2.0
        elif per == 1 and n_dias_asig == 1:
            col_do = str(pr.get("dom","")).strip().lower()
            if col_do not in ("", "nan", "none", "0"):
                per_desc  = "Domingo"
                sem_visita = "Todas"
                frecuencia = 1.0
            else:
                per_desc  = "Semanal"
                sem_visita = "Todas"
                frecuencia = 1.0
        elif per == 2:
            per_desc  = "Quincenal"
            sem_visita = "Sem 1 y 3" if pasa == 1 else "Sem 2 y 4"
            frecuencia = 0.5
        elif per == 4:
            per_desc  = "Mensual"
            sem_visita = f"Sem {pasa}"
            frecuencia = 0.25
        else:
            per_desc  = f"Per.{per}"
            sem_visita = f"Sem {pasa}"
            frecuencia = round(1 / per, 2)

        fechas_compra_mes = set(
            hist_cli_real[
                (hist_cli_real["fecha"].dt.year  == hoy.year) &
                (hist_cli_real["fecha"].dt.month == hoy.month)
            ]["fecha"].dt.date
        )
        vp, ve = _calcular_eficiencia(pr, fechas_compra_mes, hoy, cargar_calendario_laboral())
        eficiencia = f"{ve / vp * 100:.0f}%" if vp > 0 else "—"

        dias_marcados = {
            col for col in _dias_cols
            if col in pr.index and str(pr[col]).strip().lower() not in ("", "nan", "none", "0")
        }
        if dias_marcados == {"lun", "jue"}:
            zona_visita = "LU-JU"
        elif dias_marcados == {"mar", "vie"}:
            zona_visita = "MA-VI"
        elif dias_marcados == {"mie", "sab"}:
            zona_visita = "MI-SA"
        elif dias_marcados == {"dom"}:
            zona_visita = "DO"
        else:
            zona_visita = "—"
    else:
        per_desc   = "—"
        sem_visita = "—"
        frecuencia = None
        eficiencia = "—"
        zona_visita = "—"

    semana_iso_actual  = hoy.isocalendar()[1]
    semana_sist_actual = (semana_iso_actual - 1) % 4 + 1

    info["visitas"] = {
        "ult_compra":        ult_fmt,
        "dias_sin_compra":   dias_sin_compra,
        "dias_cc_mes":       dias_cc_mes,
        "periodicidad_desc": per_desc,
        "sem_visita":        sem_visita,
        "frecuencia":        frecuencia,
        "eficiencia":        eficiencia,
        "semana_sistema":    semana_sist_actual,
        "zona_visita":       zona_visita,
    }

    info["compras"] = hist_cli
    return info


def calcular_vol_cliente(cliente_num: int) -> dict:
    hoy = datetime.date.today()
    p_actual = (hoy.year, hoy.month)
    if hoy.month == 1:
        p_mes_ant = (hoy.year - 1, 12)
    else:
        p_mes_ant = (hoy.year, hoy.month - 1)
    p_anio_ant = (hoy.year - 1, hoy.month)

    hist = cargar_historico_compras()
    hist = hist[hist["cliente"] == cliente_num].copy()
    hist["fecha"] = pd.to_datetime(hist["fecha"], errors="coerce")
    hist["_anio"] = hist["fecha"].dt.year
    hist["_mes"] = hist["fecha"].dt.month

    maestro = cargar_maestro_arbol()[["articulo", "arbol"]].drop_duplicates("articulo")
    hist = hist.merge(maestro, on="articulo", how="left")

    _FILTROS = {
        "hl_total":       lambda h, u, a, m: pd.Series([True] * len(h), index=h.index),
        "cerveza_total":  lambda h, u, a, m: u.str.contains("CERVEZAS CMQ", na=False),
        "core_value":     lambda h, u, a, m: u.str.contains("CERVEZAS CMQ", na=False) & a.str.contains("CORE.VALUE", regex=True, na=False),
        "above_core":     lambda h, u, a, m: u.str.contains("CERVEZAS CMQ", na=False) & (a == "ABOVE CORE"),
        "ung_total":      lambda h, u, a, m: u == "UNG",
        "ung_top":        lambda h, u, a, m: (u == "UNG") & (a == "UNG TOP"),
        "agua":           lambda h, u, a, m: u.str.contains("AGUAS ECO", na=False),
        "gmv":            lambda h, u, a, m: (
                              u.isin(["MARKETPLACE ALIMENTOS", "VINO", "ADYACENCIAS"]) |
                              u.str.contains("AGUAS ECO", na=False) |
                              m.str.contains("RED BULL", na=False)
                          ),
    }

    def _visitas_mes(periodo):
        anio, mes = periodo
        sub = hist[(hist["_anio"] == anio) & (hist["_mes"] == mes)]
        return sub["fecha"].dt.date.nunique() if not sub.empty else 0

    def _suma(periodo, mask_fn, col):
        anio, mes = periodo
        sub = hist[(hist["_anio"] == anio) & (hist["_mes"] == mes)]
        if sub.empty:
            return 0.0
        u_ = sub["unidad_negocio"].str.strip().str.upper()
        a_ = sub["arbol"].fillna("").str.strip().str.upper()
        m_ = sub["marca"].fillna("").str.strip().str.upper()
        mask = mask_fn(sub, u_, a_, m_)
        return round(float(sub.loc[mask, col].sum()), 2)

    ult_fecha = hist["fecha"].max() if not hist.empty else None

    def _suma_fecha(fecha, mask_fn, col):
        if fecha is None or pd.isna(fecha):
            return 0.0
        sub = hist[hist["fecha"].dt.date == fecha.date()]
        if sub.empty:
            return 0.0
        u_ = sub["unidad_negocio"].str.strip().str.upper()
        a_ = sub["arbol"].fillna("").str.strip().str.upper()
        m_ = sub["marca"].fillna("").str.strip().str.upper()
        mask = mask_fn(sub, u_, a_, m_)
        return round(float(sub.loc[mask, col].sum()), 2)

    metricas = {}
    for nombre, fn in _FILTROS.items():
        col = "importe_neto" if nombre == "gmv" else "hl"
        metricas[nombre] = {
            "actual":     _suma(p_actual,   fn, col),
            "mes_ant":    _suma(p_mes_ant,  fn, col),
            "anio_ant":   _suma(p_anio_ant, fn, col),
            "ult_visita": _suma_fecha(ult_fecha, fn, col),
        }

    for periodo, key in [(p_actual, "actual"), (p_mes_ant, "mes_ant"), (p_anio_ant, "anio_ant")]:
        vis = _visitas_mes(periodo)
        hl = metricas["hl_total"][key]
        metricas["hl_total"][f"prom_{key}"] = round(hl / vis, 2) if vis else 0.0
    metricas["hl_total"]["prom_ult_visita"] = metricas["hl_total"]["ult_visita"]

    ult_fecha_str = ult_fecha.strftime("%d/%m/%y") if ult_fecha is not None and not pd.isna(ult_fecha) else "—"

    return {
        "periodos": {"actual": p_actual, "mes_ant": p_mes_ant, "anio_ant": p_anio_ant},
        "ult_visita_fecha": ult_fecha_str,
        "metricas": metricas,
    }


def _filtro_vendedor(serie_vendedor_cod, vendedor_cod):
    """vendedor_cod puede ser un int (ficha individual) o una lista/set (ficha gerencial:
    supervisor/jefe/grupo palco) — en ese caso filtra por pertenencia, no igualdad."""
    if isinstance(vendedor_cod, (list, set, tuple)):
        return serie_vendedor_cod.isin(vendedor_cod)
    return serie_vendedor_cod == vendedor_cod


def calcular_vol_vendedor(vendedor_cod, incluir_lucky: bool = True, incluir_pana: bool = True) -> dict:
    hoy = datetime.date.today()
    p_actual   = (hoy.year, hoy.month)
    p_mes_ant  = (hoy.year, hoy.month - 1) if hoy.month > 1 else (hoy.year - 1, 12)
    p_anio_ant = (hoy.year - 1, hoy.month)

    cartera = cargar_cartera()
    clientes = set(cartera[_filtro_vendedor(cartera["vendedor_cod"], vendedor_cod)]["cliente"].dropna().astype(int).tolist())

    hist = cargar_historico_compras()
    hist = hist[hist["cliente"].isin(clientes)].copy()
    if not incluir_lucky:
        hist = hist[hist["fuente"] != "lucky"]
    hist["fecha"] = pd.to_datetime(hist["fecha"], errors="coerce")
    hist["_anio"] = hist["fecha"].dt.year
    hist["_mes"]  = hist["fecha"].dt.month

    cols_maestro = ["articulo", "arbol"] + (["es_pana"] if not incluir_pana else [])
    maestro = cargar_maestro_arbol()[cols_maestro].drop_duplicates("articulo")
    hist = hist.merge(maestro, on="articulo", how="left")
    if not incluir_pana:
        hist = hist[hist["es_pana"] != True]

    _FILTROS = {
        "hl_total":      lambda h, u, a, m: pd.Series([True] * len(h), index=h.index),
        "cerveza_total": lambda h, u, a, m: u.str.contains("CERVEZAS CMQ", na=False),
        "core_value":    lambda h, u, a, m: u.str.contains("CERVEZAS CMQ", na=False) & a.str.contains("CORE.VALUE", regex=True, na=False),
        "above_core":    lambda h, u, a, m: u.str.contains("CERVEZAS CMQ", na=False) & (a == "ABOVE CORE"),
        "ung_total":     lambda h, u, a, m: u == "UNG",
        "ung_top":       lambda h, u, a, m: (u == "UNG") & (a == "UNG TOP"),
        "agua":          lambda h, u, a, m: u.str.contains("AGUAS ECO", na=False),
        "gmv":           lambda h, u, a, m: (
                             u.isin(["MARKETPLACE ALIMENTOS", "VINO", "ADYACENCIAS"]) |
                             u.str.contains("AGUAS ECO", na=False) |
                             m.str.contains("RED BULL", na=False)
                         ),
    }

    def _suma(periodo, mask_fn, col):
        anio, mes = periodo
        sub = hist[(hist["_anio"] == anio) & (hist["_mes"] == mes)]
        if sub.empty: return 0.0
        u_ = sub["unidad_negocio"].str.strip().str.upper()
        a_ = sub["arbol"].fillna("").str.strip().str.upper()
        m_ = sub["marca"].fillna("").str.strip().str.upper()
        return round(float(sub.loc[mask_fn(sub, u_, a_, m_), col].sum()), 2)

    def _visitas_mes(periodo):
        anio, mes = periodo
        sub = hist[(hist["_anio"] == anio) & (hist["_mes"] == mes)]
        return sub["cliente"].nunique() if not sub.empty else 0

    metricas = {}
    for nombre, fn in _FILTROS.items():
        col = "importe_neto" if nombre == "gmv" else "hl"
        metricas[nombre] = {
            "actual":   _suma(p_actual,   fn, col),
            "mes_ant":  _suma(p_mes_ant,  fn, col),
            "anio_ant": _suma(p_anio_ant, fn, col),
        }

    for periodo, key in [(p_actual, "actual"), (p_mes_ant, "mes_ant"), (p_anio_ant, "anio_ant")]:
        vis = _visitas_mes(periodo)
        hl  = metricas["hl_total"][key]
        metricas["hl_total"][f"prom_{key}"] = round(hl / vis, 2) if vis else 0.0

    return {
        "periodos": {"actual": p_actual, "mes_ant": p_mes_ant, "anio_ant": p_anio_ant},
        "metricas": metricas,
    }


def _meses_ultimos_4() -> list:
    hoy = datetime.date.today()
    meses = []
    for i in range(3, -1, -1):
        m = hoy.month - i
        a = hoy.year
        if m <= 0:
            m += 12
            a -= 1
        meses.append((a, m))
    return meses


def _prep_hist_ytd(hist_filtrado):
    hoy = datetime.date.today()
    df = hist_filtrado.copy()
    df["fecha"] = pd.to_datetime(df["fecha"], errors="coerce")
    df = df[df["fecha"].dt.year == hoy.year]
    maestro = cargar_maestro_arbol()[["articulo","arbol"]].drop_duplicates("articulo")
    df = df.merge(maestro, on="articulo", how="left")
    df["_mes"]  = df["fecha"].dt.month
    df["_un"]   = df["unidad_negocio"].str.strip().str.upper()
    df["_arb"]  = df["arbol"].fillna("").str.strip().str.upper()
    return df, hoy


_ORDEN_UN_TOP = ["CERVEZAS CMQ", "UNG", "AGUAS ECO", "MARKETPLACE ALIMENTOS", "VINO", "ADYACENCIAS"]
_TOP_N = 6


@st.cache_data(ttl=900)
def calcular_analytics_cliente(cliente_num: int) -> dict:
    hist_all = cargar_historico_compras()
    hist_cli = hist_all[hist_all["cliente"] == cliente_num]

    df, hoy = _prep_hist_ytd(hist_cli)

    meses = _meses_ultimos_4()

    df_t = hist_cli.copy()
    df_t["fecha"] = pd.to_datetime(df_t["fecha"], errors="coerce")
    maestro = cargar_maestro_arbol()[["articulo","arbol"]].drop_duplicates("articulo")
    df_t = df_t.merge(maestro, on="articulo", how="left")
    df_t["_anio"] = df_t["fecha"].dt.year
    df_t["_mes"]  = df_t["fecha"].dt.month
    df_t["_un"]   = df_t["unidad_negocio"].str.strip().str.upper()
    df_t["_arb"]  = df_t["arbol"].fillna("").str.strip().str.upper()

    def _suma_tend(anio, mes, u_mask_fn, a_mask_fn=None):
        sub = df_t[(df_t["_anio"] == anio) & (df_t["_mes"] == mes)]
        if sub.empty: return 0.0
        mask = u_mask_fn(sub["_un"])
        if a_mask_fn:
            mask = mask & a_mask_fn(sub["_arb"])
        return round(float(sub.loc[mask, "hl"].sum()), 2)

    is_czas = lambda u: u.str.contains("CERVEZAS CMQ", na=False)
    is_ac   = lambda a: a.isin(["ABOVE CORE","ABOVE CORE-MKPL"])
    is_ung  = lambda u: u == "UNG"
    is_top  = lambda a: a == "UNG TOP"

    tendencia = {
        "meses":      meses,
        "cerveza":    [_suma_tend(a, m, is_czas) for a, m in meses],
        "above_core": [_suma_tend(a, m, is_czas, is_ac) for a, m in meses],
        "ung":        [_suma_tend(a, m, is_ung) for a, m in meses],
        "ung_top":    [_suma_tend(a, m, is_ung, is_top) for a, m in meses],
    }

    if df.empty:
        mix = {
            "cerveza": {"total_hl": 0, "core_value": 0, "above_core": 0},
            "ung":     {"total_hl": 0, "ung_top": 0, "resto_ung": 0},
        }
    else:
        un, arb = df["_un"], df["_arb"]
        marc = df["marca"].str.strip().str.upper()
        czas = un.str.contains("CERVEZAS CMQ", na=False)
        del_valle = marc.str.contains("DEL VALLE", na=False)
        ung = (un == "UNG") | del_valle
        def _hl(mask): return round(float(df.loc[mask, "hl"].sum()), 2)
        mix = {
            "cerveza": {
                "total_hl":   _hl(czas),
                "core_value": _hl(czas & arb.isin(["CORE-VALUE","CORE-VALUE-MKPL"])),
                "above_core": _hl(czas & arb.isin(["ABOVE CORE","ABOVE CORE-MKPL"])),
            },
            "ung": {
                "total_hl":  _hl(ung),
                "ung_top":   _hl((un == "UNG") & (arb == "UNG TOP")),
                "resto_ung": _hl((un == "UNG") & (arb == "RESTO UNG")),
                "del_valle": _hl(del_valle),
            },
        }

    top_por_un = {}
    if not df.empty:
        for un_val in _ORDEN_UN_TOP:
            sub = df[df["_un"].str.contains(un_val.replace(" ",".*"), regex=True, na=False)]
            if sub.empty: continue
            es_mkpl = "MARKETPLACE" in un_val
            col = "bultos" if es_mkpl else "hl"
            unidad = "Blt" if es_mkpl else "HL"
            by_m = (sub.groupby("marca", as_index=False)[col].sum()
                       .sort_values(col, ascending=False).head(_TOP_N))
            if not by_m.empty:
                top_por_un[un_val] = {
                    "unidad": unidad,
                    "items": [{"marca": r["marca"], "valor": round(float(r[col]),2)} for _, r in by_m.iterrows()]
                }

    return {"tendencia": tendencia, "mix": mix, "top_por_un": top_por_un}


@st.cache_data(ttl=900)
def calcular_analytics_vendedor(vendedor_cod, incluir_lucky: bool = True, incluir_pana: bool = True) -> dict:
    cartera  = cargar_cartera()
    clientes = set(cartera[_filtro_vendedor(cartera["vendedor_cod"], vendedor_cod)]["cliente"].dropna().astype(int))

    hist_all = cargar_historico_compras()
    hist_vnd = hist_all[hist_all["cliente"].isin(clientes)]
    if not incluir_lucky:
        hist_vnd = hist_vnd[hist_vnd["fuente"] != "lucky"]
    if not incluir_pana:
        _pana_arts = set(cargar_maestro_arbol().loc[lambda d: d.get("es_pana") == True, "articulo"]) \
            if "es_pana" in cargar_maestro_arbol().columns else set()
        hist_vnd = hist_vnd[~hist_vnd["articulo"].isin(_pana_arts)]

    df, hoy = _prep_hist_ytd(hist_vnd)

    meses = _meses_ultimos_4()

    df_t = hist_vnd.copy()
    df_t["fecha"] = pd.to_datetime(df_t["fecha"], errors="coerce")
    maestro = cargar_maestro_arbol()[["articulo","arbol"]].drop_duplicates("articulo")
    df_t = df_t.merge(maestro, on="articulo", how="left")
    df_t["_anio"] = df_t["fecha"].dt.year
    df_t["_mes"]  = df_t["fecha"].dt.month
    df_t["_un"]   = df_t["unidad_negocio"].str.strip().str.upper()
    df_t["_arb"]  = df_t["arbol"].fillna("").str.strip().str.upper()

    is_czas = lambda u: u.str.contains("CERVEZAS CMQ", na=False)
    is_ac   = lambda a: a.isin(["ABOVE CORE","ABOVE CORE-MKPL"])
    is_ung  = lambda u: u == "UNG"
    is_top  = lambda a: a == "UNG TOP"

    def _suma_tend(anio, mes, u_fn, a_fn=None):
        sub = df_t[(df_t["_anio"] == anio) & (df_t["_mes"] == mes)]
        if sub.empty: return 0.0
        mask = u_fn(sub["_un"])
        if a_fn: mask = mask & a_fn(sub["_arb"])
        return round(float(sub.loc[mask, "hl"].sum()), 2)

    tendencia = {
        "meses":      meses,
        "cerveza":    [_suma_tend(a, m, is_czas) for a, m in meses],
        "above_core": [_suma_tend(a, m, is_czas, is_ac) for a, m in meses],
        "ung":        [_suma_tend(a, m, is_ung) for a, m in meses],
        "ung_top":    [_suma_tend(a, m, is_ung, is_top) for a, m in meses],
    }

    if df.empty:
        mix = {
            "cerveza": {"total_hl": 0, "core_value": 0, "above_core": 0},
            "ung":     {"total_hl": 0, "ung_top": 0, "resto_ung": 0},
        }
    else:
        un, arb = df["_un"], df["_arb"]
        marc = df["marca"].str.strip().str.upper()
        czas = un.str.contains("CERVEZAS CMQ", na=False)
        del_valle = marc.str.contains("DEL VALLE", na=False)
        ung = (un == "UNG") | del_valle
        def _hl(mask): return round(float(df.loc[mask, "hl"].sum()), 2)
        mix = {
            "cerveza": {
                "total_hl":   _hl(czas),
                "core_value": _hl(czas & arb.isin(["CORE-VALUE","CORE-VALUE-MKPL"])),
                "above_core": _hl(czas & arb.isin(["ABOVE CORE","ABOVE CORE-MKPL"])),
            },
            "ung": {
                "total_hl":  _hl(ung),
                "ung_top":   _hl((un == "UNG") & (arb == "UNG TOP")),
                "resto_ung": _hl((un == "UNG") & (arb == "RESTO UNG")),
                "del_valle": _hl(del_valle),
            },
        }

    top_por_un = {}
    if not df.empty:
        for un_val in _ORDEN_UN_TOP:
            sub = df[df["_un"].str.contains(un_val.replace(" ",".*"), regex=True, na=False)]
            if sub.empty: continue
            es_mkpl = "MARKETPLACE" in un_val
            col = "bultos" if es_mkpl else "hl"
            unidad = "Blt" if es_mkpl else "HL"
            by_m = (sub.groupby("marca", as_index=False)[col].sum()
                       .sort_values(col, ascending=False).head(_TOP_N))
            if not by_m.empty:
                top_por_un[un_val] = {
                    "unidad": unidad,
                    "items": [{"marca": r["marca"], "valor": round(float(r[col]),2)} for _, r in by_m.iterrows()]
                }

    return {"tendencia": tendencia, "mix": mix, "top_por_un": top_por_un}


def _calc_tbd(group: pd.DataFrame, es_cerveza: bool) -> int:
    if group.empty:
        return 0
    if es_cerveza:
        return int(
            group.groupby("cliente")
                 .apply(lambda x: x[["marca", "calibre"]].drop_duplicates().shape[0])
                 .sum()
        )
    else:
        return int(
            group.groupby("cliente")
                 .apply(lambda x: x["articulo"].nunique())
                 .sum()
        )


def construir_arbol_vendedor(vendedor_cod, incluir_lucky: bool = True) -> dict:
    hoy = datetime.date.today()

    cartera  = cargar_cartera()
    clientes = set(cartera[_filtro_vendedor(cartera["vendedor_cod"], vendedor_cod)]["cliente"].dropna().astype(int).tolist())

    hist = cargar_historico_compras()
    hist["fecha"] = pd.to_datetime(hist["fecha"], errors="coerce")
    hist_mes = hist[
        (hist["cliente"].isin(clientes)) &
        (hist["fecha"].dt.year  == hoy.year) &
        (hist["fecha"].dt.month == hoy.month)
    ].copy()
    if not incluir_lucky:
        hist_mes = hist_mes[hist_mes["fuente"] != "lucky"]

    maestro = cargar_maestro_arbol()
    maestro = maestro.dropna(subset=["unidad_negocio", "arbol", "marca"])
    maestro = maestro[maestro["arbol"].str.strip().str.upper() != "NO APLICABLE"]
    # PANA (genéricos sin marca real) no cuentan para cobertura TBD/CCC — sí suman a volumen
    # (eso se calcula aparte en calcular_vol_vendedor, que no pasa por este filtro)
    if "es_pana" in maestro.columns:
        maestro = maestro[maestro["es_pana"] != True]
    maestro = maestro.copy()

    mask_cmq = (maestro["unidad_negocio"].str.strip().str.upper() == "CERVEZAS CMQ") & \
                maestro["arbol"].str.strip().str.upper().str.contains("MKPL")
    mask_ung = (maestro["unidad_negocio"].str.strip().str.upper() == "UNG") & \
               (maestro["arbol"].str.strip().str.upper() == "MKPL") & \
               ~maestro["marca"].str.strip().str.upper().str.contains("DEL VALLE")
    maestro.loc[mask_cmq | mask_ung, "unidad_negocio"] = "MARKETPLACE ALIMENTOS"

    if hist_mes.empty:
        return {"ccc": 0, "tbd": 0, "uns": {}}

    hist_clean = hist_mes.drop(columns=["unidad_negocio","marca"], errors="ignore")
    merged = hist_clean.merge(
        maestro[["articulo","unidad_negocio","arbol","marca"]].drop_duplicates("articulo"),
        on="articulo", how="inner"
    )
    if "calibre" not in merged.columns:
        merged["calibre"] = ""

    _ORDEN_UN = ["CERVEZAS CMQ","UNG","AGUAS ECO","MARKETPLACE ALIMENTOS","VINO","ADYACENCIAS"]

    def _idx_un(nombre):
        n = str(nombre).strip().upper()
        for i, ref in enumerate(_ORDEN_UN):
            if n == ref or n in ref or ref in n: return i
        return len(_ORDEN_UN)

    uns = {}
    for un, g_un in merged.groupby("unidad_negocio"):
        es_cmq = "CERVEZAS CMQ" in str(un).upper()
        segs = {}
        for seg, g_seg in g_un.groupby("arbol"):
            marcas = {}
            for marca, g_marca in g_seg.groupby("marca"):
                marcas[marca] = {
                    "ccc": int(g_marca["cliente"].nunique()),
                    "tbd": _calc_tbd(g_marca, es_cmq),
                }
            segs[seg] = {
                "ccc":    int(g_seg["cliente"].nunique()),
                "tbd":    _calc_tbd(g_seg, es_cmq),
                "marcas": marcas,
            }
        uns[un] = {
            "ccc":      int(g_un["cliente"].nunique()),
            "tbd":      _calc_tbd(g_un, es_cmq),
            "segmentos": segs,
        }

    uns_sorted = dict(sorted(uns.items(), key=lambda x: _idx_un(x[0])))
    tbd_total = sum(v["tbd"] for v in uns_sorted.values())

    return {
        "ccc": int(merged["cliente"].nunique()),
        "tbd": tbd_total,
        "uns": uns_sorted,
    }


def kpis_vendedor(vendedor_cod) -> dict:
    hoy = datetime.date.today()
    _DIAS_COL = {0:"lun", 1:"mar", 2:"mie", 3:"jue", 4:"vie", 5:"sab", 6:"dom"}
    _DIAS_NOM = ["Lun","Mar","Mié","Jue","Vie","Sáb","Dom"]

    cartera    = cargar_cartera()
    estructura = cargar_estructura_comercial()
    pers       = cargar_personalizacion_visitas()

    es_grupo = isinstance(vendedor_cod, (list, set, tuple))

    mi_cartera = cartera[_filtro_vendedor(cartera["vendedor_cod"], vendedor_cod)]
    clientes   = set(mi_cartera["cliente"].dropna().astype(int).tolist())

    total = len(clientes)

    mi_pers = pers[_filtro_vendedor(pers["vendedor_cod"], vendedor_cod)]

    cartera_alcohol = int(
        mi_cartera["licencia_alcohol"].astype(str).str.strip().str.upper().eq("SI").sum()
    )

    col_hoy = _DIAS_COL.get(hoy.weekday())
    if col_hoy and col_hoy in mi_pers.columns:
        clientes_hoy = int((mi_pers[col_hoy].astype(str).str.strip().str.upper() == "X").sum())
    else:
        clientes_hoy = 0

    por_vnd = cargar_por_vendedor_semanas()
    sem = semana_actual()
    fila_vnd = por_vnd[_filtro_vendedor(por_vnd["vendedor_cod"], vendedor_cod)]
    if not fila_vnd.empty:
        if es_grupo:
            visitas_semana   = int(pd.to_numeric(fila_vnd.get(f"s{sem}_total"), errors="coerce").fillna(0).sum())
            visitas_hoy_plan = int(pd.to_numeric(fila_vnd.get(f"s{sem}_d{hoy.weekday()}"), errors="coerce").fillna(0).sum())
        else:
            visitas_semana = int(fila_vnd.iloc[0].get(f"s{sem}_total", 0) or 0)
            visitas_hoy_plan = int(fila_vnd.iloc[0].get(f"s{sem}_d{hoy.weekday()}", 0) or 0)
    else:
        visitas_semana   = 0
        visitas_hoy_plan = 0

    historico = cargar_historico_compras()
    hist_mes = historico[
        (historico["fecha"].dt.year  == hoy.year) &
        (historico["fecha"].dt.month == hoy.month) &
        (historico["fuente"] != "lucky")  # Lucky no representa una visita real
    ].copy()
    hist_mes["fecha_d"] = hist_mes["fecha"].dt.date

    dias_no_laborables = cargar_calendario_laboral()

    total_visitas_plan = 0
    total_efectivas    = 0

    for _, pr in mi_pers.iterrows():
        cli = pr.get("cliente")
        if pd.isna(cli): continue
        cli = int(cli)
        if cli not in clientes: continue

        fechas_cli = set(hist_mes[hist_mes["cliente"] == cli]["fecha_d"])
        vp, ve = _calcular_eficiencia(pr, fechas_cli, hoy, dias_no_laborables)
        total_visitas_plan += vp
        total_efectivas    += ve

    if total_visitas_plan > 0:
        eficiencia_vnd = f"{total_efectivas / total_visitas_plan * 100:.0f}%"
    else:
        eficiencia_vnd = "—"

    if es_grupo:
        info_estructura_dict = None
    else:
        info_estructura = estructura[estructura["vendedor_cod"] == vendedor_cod]
        info_estructura_dict = info_estructura.iloc[0].to_dict() if not info_estructura.empty else None

    return {
        "cartera_total":     total,
        "cartera_alcohol":   cartera_alcohol,
        "clientes_hoy":      clientes_hoy,
        "visitas_hoy_plan":  visitas_hoy_plan,
        "visitas_semana":    visitas_semana,
        "semana_actual":     sem,
        "dia_semana":        _DIAS_NOM[hoy.weekday()],
        "eficiencia_venta":  eficiencia_vnd,
        "estructura":        info_estructura_dict,
    }


def datos_vendedor(vendedor_cod):
    cartera = cargar_cartera()
    estructura = cargar_estructura_comercial()
    seguimiento = cargar_seguimiento_visitas()

    mi_cartera = cartera[cartera["vendedor_cod"] == vendedor_cod].copy()
    mi_seguimiento = seguimiento[seguimiento["vendedor_cod"] == vendedor_cod].copy()
    info_estructura = estructura[estructura["vendedor_cod"] == vendedor_cod]

    return {
        "cartera": mi_cartera,
        "seguimiento": mi_seguimiento,
        "estructura": info_estructura.iloc[0].to_dict() if not info_estructura.empty else None,
    }


@st.cache_data(ttl=1800)
def cargar_avance_vendedor(vendedor_cod: int) -> dict | None:
    """Lee el último snapshot de avance del vendedor desde Supabase (tabla avance_vendedor,
    actualizada por sync diario). Antes leía directo AVANCES VENDEDORES.xlsx."""
    df = _query(
        "SELECT datos FROM avance_vendedor WHERE vendedor_cod = %(cod)s "
        "ORDER BY fecha_snapshot DESC LIMIT 1",
        params={"cod": vendedor_cod},
    )
    if df.empty:
        return None
    datos = df.iloc[0]["datos"]
    if isinstance(datos, str):
        import json
        datos = json.loads(datos)
    datos.setdefault("metricas_hl", {m["label"]: m for m in datos.get("metricas_hl_lista", [])})
    return datos


@st.cache_data(ttl=1800)
def cargar_avance_grupo(codigo_grupo: str) -> dict | None:
    """Avance de Ficha Gerencial (supervisor/jefe/Grupo Palco) — tabla avance_grupo,
    formato más simple que el de vendedor (sin tareas/GMV/tiempos/escalas, solo volumen)."""
    df = _query(
        "SELECT datos FROM avance_grupo WHERE codigo_grupo = %(cod)s "
        "ORDER BY fecha_snapshot DESC LIMIT 1",
        params={"cod": str(codigo_grupo)},
    )
    if df.empty:
        return None
    datos = df.iloc[0]["datos"]
    if isinstance(datos, str):
        import json
        datos = json.loads(datos)
    return datos




# ── Censo Thomas (desde Supabase) ──────────────────────────────────────────────

@st.cache_data(ttl=21600)
def cargar_censo_base() -> pd.DataFrame:
    df = _query("SELECT cliente, vol_cmq, vol_ccu, vol_otros FROM censo_base")
    df["cliente"] = pd.to_numeric(df["cliente"], errors="coerce")
    return df.dropna(subset=["cliente"])


@st.cache_data(ttl=21600)
def cargar_censo_som_prev() -> pd.DataFrame:
    df = _query(
        "SELECT vendedor_cod, nombre, t_cmq, t_ccu, t_otros, sp_cmq, pr_cmq, pr_ccu, "
        "cp_cmq, cp_ccu, co_cmq, co_ccu, va_cmq, va_ccu, va_otros FROM censo_som_prev"
    )
    df["vendedor_cod"] = pd.to_numeric(df["vendedor_cod"], errors="coerce")
    return df.dropna(subset=["vendedor_cod"])


def _pct_3(cmq, ccu, otros=0.0):
    total = cmq + ccu + otros
    if total <= 0:
        return {"hl_cmq": 0.0, "hl_ccu": 0.0, "hl_otros": 0.0, "pct_cmq": 0, "pct_ccu": 0, "pct_otros": 0}
    return {
        "hl_cmq": round(cmq, 2), "hl_ccu": round(ccu, 2), "hl_otros": round(otros, 2),
        "pct_cmq": round(cmq / total * 100, 1),
        "pct_ccu": round(ccu / total * 100, 1),
        "pct_otros": round(otros / total * 100, 1),
    }


def _pct_3_desde_fracciones(frac_cmq, frac_ccu, frac_otros=None):
    frac_cmq = max(frac_cmq, 0.0)
    frac_ccu = max(frac_ccu, 0.0)
    if frac_otros is None:
        frac_otros = max(1.0 - frac_cmq - frac_ccu, 0.0)
    else:
        frac_otros = max(frac_otros, 0.0)
    if frac_cmq + frac_ccu + frac_otros == 0:
        return {"hl_cmq": 0.0, "hl_ccu": 0.0, "hl_otros": 0.0, "pct_cmq": 0, "pct_ccu": 0, "pct_otros": 0}
    return {
        "hl_cmq": 0.0, "hl_ccu": 0.0, "hl_otros": 0.0,
        "pct_cmq": round(frac_cmq * 100, 1),
        "pct_ccu": round(frac_ccu * 100, 1),
        "pct_otros": round(frac_otros * 100, 1),
    }


def calcular_censo_cliente(cliente_num: int) -> dict | None:
    base = cargar_censo_base()
    fila = base[base["cliente"] == cliente_num]
    if fila.empty:
        return None
    r = fila.iloc[0]
    return _pct_3(float(r["vol_cmq"]), float(r["vol_ccu"]), float(r["vol_otros"]))


def _segmentos_desde_fila_som(r) -> dict:
    return {
        "Total":          _pct_3_desde_fracciones(float(r["t_cmq"]),  float(r["t_ccu"]),  float(r["t_otros"])),
        "Super Premium":  _pct_3_desde_fracciones(float(r["sp_cmq"]), 0.0),
        "Premium":        _pct_3_desde_fracciones(float(r["pr_cmq"]), float(r["pr_ccu"])),
        "Core Plus":      _pct_3_desde_fracciones(float(r["cp_cmq"]), float(r["cp_ccu"])),
        "Core":           _pct_3_desde_fracciones(float(r["co_cmq"]), float(r["co_ccu"])),
        "Value":          _pct_3_desde_fracciones(float(r["va_cmq"]), float(r["va_ccu"]), float(r["va_otros"])),
    }


def calcular_censo_vendedor(vendedor_cod: int) -> dict | None:
    som = cargar_censo_som_prev()
    fila = som[som["vendedor_cod"] == vendedor_cod]
    if fila.empty:
        return None
    return _segmentos_desde_fila_som(fila.iloc[0])


@st.cache_data(ttl=21600)
def calcular_censo_empresa() -> dict | None:
    """Referencia 'Grupo Palco' (fila de totales JDV), guardada con vendedor_cod=-1
    en censo_som_prev (ver migrar_avance_censo_coaching.migrar_censo)."""
    som = cargar_censo_som_prev()
    fila = som[som["vendedor_cod"] == -1]
    if fila.empty:
        return None
    return _segmentos_desde_fila_som(fila.iloc[0])


# ── Coaching (pendiente migrar — sigue en Excel/Dropbox) ──────────────────────

def _normalizar_nombre(s):
    s = str(s).strip().upper()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return s


@st.cache_data(ttl=21600)
def cargar_coaching_todos() -> list:
    """Lee la tabla 'coaching' de Supabase — pilares y total_pct ya vienen calculados
    desde la migración (ver migrar_avance_censo_coaching.py)."""
    df = _query(
        "SELECT archivo_origen, coaching_num, activador, supervisor, timestamp_coaching, "
        "plan_logrado, comentario, pilares, total_pct FROM coaching"
    )
    registros = []
    for _, r in df.iterrows():
        pilares = r["pilares"]
        if isinstance(pilares, str):
            import json
            pilares = json.loads(pilares)
        registros.append({
            "archivo_origen": r["archivo_origen"],
            "coaching_num": r["coaching_num"],
            "activador": r["activador"],
            "supervisor": r["supervisor"],
            "timestamp": r["timestamp_coaching"],
            "plan_logrado": r["plan_logrado"],
            "comentario": r["comentario"] or "",
            "pilares_pct": pilares,
            "total_pct": float(r["total_pct"]) if pd.notna(r["total_pct"]) else 0.0,
        })
    return registros


def calcular_coaching_vendedor(vendedor_cod: int) -> dict | None:
    estructura = cargar_estructura_comercial()
    fila = estructura[estructura["vendedor_cod"] == vendedor_cod]
    if fila.empty:
        return None
    nombre_obj = _normalizar_nombre(fila.iloc[0].get("vendedor_nombre", ""))
    if not nombre_obj:
        return None

    registros = cargar_coaching_todos()
    encontrados = [r for r in registros if _normalizar_nombre(r["activador"]) == nombre_obj]
    if not encontrados:
        return None

    resultado = {}
    for r in encontrados:
        ts = r["timestamp"]
        fecha = ts.strftime("%d/%m/%y") if hasattr(ts, "strftime") and not pd.isna(ts) else str(ts)
        resultado[r["coaching_num"]] = {
            "pilares":      r["pilares_pct"],
            "comentario":   r.get("comentario", ""),
            "total_pct":    r["total_pct"],
            "supervisor":   r["supervisor"],
            "fecha":        fecha,
            "plan_logrado": r["plan_logrado"],
        }
    return resultado


def calcular_coaching_supervisor(supervisor_cod: int) -> dict | None:
    """Coachings que el Jefe de Venta le hizo a este supervisor (archivo Coaching SPV
    2026.xlsm) — análogo a calcular_coaching_vendedor pero filtrando por archivo_origen
    'SPV' y por el nombre del supervisor en vez del vendedor."""
    estructura = cargar_estructura_comercial()
    fila = estructura[estructura["supervisor_cod"] == supervisor_cod]
    if fila.empty:
        return None
    nombre_obj = _normalizar_nombre(fila.iloc[0].get("supervisor_nombre", ""))
    if not nombre_obj:
        return None

    registros = cargar_coaching_todos()
    encontrados = [
        r for r in registros
        if r.get("archivo_origen") == "SPV" and _normalizar_nombre(r["activador"]) == nombre_obj
    ]
    if not encontrados:
        return None

    resultado = {}
    for r in encontrados:
        ts = r["timestamp"]
        fecha = ts.strftime("%d/%m/%y") if hasattr(ts, "strftime") and not pd.isna(ts) else str(ts)
        resultado[r["coaching_num"]] = {
            "pilares":      r["pilares_pct"],
            "comentario":   r.get("comentario", ""),
            "total_pct":    r["total_pct"],
            "supervisor":   r["supervisor"],
            "fecha":        fecha,
            "plan_logrado": r["plan_logrado"],
        }
    return resultado
