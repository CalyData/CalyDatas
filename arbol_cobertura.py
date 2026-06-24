"""Construye el árbol Unidad de Negocio -> Segmento (ARBOL) -> Marca -> Artículo,
marcando cada rama como "compra" (verde) o "no compra" (rojo) - estilo semáforo.
Una rama superior se pinta de verde si compra AL MENOS UNO de sus elementos hijos."""
import pandas as pd
from data_loader import cargar_maestro_arbol


def construir_arbol(compras_cliente: pd.DataFrame):
    """
    compras_cliente: DataFrame con columnas articulo, hl (filtrado a un cliente).
    Devuelve estructura anidada de 4 niveles:
      {UN: {"compra": bool, "segmentos": {Seg: {"compra": bool, "marcas": {Marca: {"compra": bool, "hl": float, "articulos": {Art: {"compra": bool, "hl": float}}}}}}}}
    """
    maestro = cargar_maestro_arbol()  # articulo, articulo_desc, unidad_negocio, marca, calibre, arbol
    maestro = maestro.dropna(subset=["unidad_negocio", "arbol", "marca", "articulo_desc"])
    # "NO APLICABLE" no es un segmento real de cobertura: se descarta de la vista
    maestro = maestro[maestro["arbol"].astype(str).str.strip().str.upper() != "NO APLICABLE"]
    # Corregir cruces UN vs Segmento:
    # CERVEZAS CMQ + MKPL → MARKETPLACE ALIMENTOS
    # UNG + MKPL sin ser Del Valle Jugos → MARKETPLACE ALIMENTOS (actualmente no ocurre pero se deja por robustez)
    maestro = maestro.copy()
    mask_cmq_mkpl = (
        maestro["unidad_negocio"].str.strip().str.upper() == "CERVEZAS CMQ"
    ) & maestro["arbol"].str.strip().str.upper().str.contains("MKPL")
    mask_ung_mkpl = (
        (maestro["unidad_negocio"].str.strip().str.upper() == "UNG")
        & (maestro["arbol"].str.strip().str.upper() == "MKPL")
        & ~maestro["marca"].str.strip().str.upper().str.contains("DEL VALLE")
    )
    maestro.loc[mask_cmq_mkpl | mask_ung_mkpl, "unidad_negocio"] = "MARKETPLACE ALIMENTOS"

    # Solo considerar compras de artículos activos en el maestro actual
    articulos_activos = set(maestro["articulo"])
    hl_por_articulo = {
        cod: hl
        for cod, hl in compras_cliente.groupby("articulo", dropna=False)["hl"].sum().items()
        if cod in articulos_activos
    }

    arbol = {}
    for _, fila in maestro.iterrows():
        un = fila["unidad_negocio"]
        seg = fila["arbol"]
        marca = fila["marca"]
        art_cod = fila["articulo"]
        art_nombre = fila["articulo_desc"]

        hl = float(hl_por_articulo.get(art_cod, 0.0))
        compra_art = hl > 0

        nodo_un = arbol.setdefault(un, {"compra": False, "segmentos": {}})
        nodo_seg = nodo_un["segmentos"].setdefault(seg, {"compra": False, "marcas": {}})
        nodo_marca = nodo_seg["marcas"].setdefault(marca, {"compra": False, "hl": 0.0, "articulos": {}})

        nodo_marca["articulos"][f"{art_cod} - {art_nombre}"] = {"compra": compra_art, "hl": round(hl, 2)}

        if compra_art:
            nodo_marca["compra"] = True
            nodo_marca["hl"] = round(nodo_marca["hl"] + hl, 2)
            nodo_seg["compra"] = True
            nodo_un["compra"] = True

    return arbol
