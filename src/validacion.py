"""
Validación y formato.

La validación se deriva de la config de la planilla, no se escribe una por
hoja. Los mensajes van en la voz de la interfaz: dicen qué corregir, no
piden disculpas.
"""

import pandas as pd

from .config import MESES, cfg_de


def formato_soles(valor: float) -> str:
    return f"S/ {valor:,.2f}"


def estimar_importe(hoja: str, df: pd.DataFrame, tarifas: dict) -> float:
    """Total presupuestado para el feedback en vivo.
      - IMPORTE directo → suma la columna IMPORTE.
      - HORAS con tarifa de catálogo → horas × tarifa por tipo.
      - HORAS con tarifa server → no se puede estimar en el cliente; se
        informa aparte que el importe se calcula al valorizar.
    """
    cfg = cfg_de(hoja)
    if df.empty:
        return 0.0
    if cfg["metrica"] == "IMPORTE":
        return float(pd.to_numeric(df["IMPORTE"], errors="coerce").fillna(0).sum())
    if cfg["tarifa"] == "catalogo":
        horas = pd.to_numeric(df["HORAS"], errors="coerce").fillna(0)
        tarifa_fila = df[cfg["catalogo_key"]].map(tarifas).fillna(0)
        return float((horas * tarifa_fila).sum())
    return 0.0  # tarifa server: se valoriza en SQL


def total_horas(df: pd.DataFrame) -> float:
    if "HORAS" not in df.columns or df.empty:
        return 0.0
    return float(pd.to_numeric(df["HORAS"], errors="coerce").fillna(0).sum())


def validar(hoja: str, df: pd.DataFrame, ccos_validos: set, tarifas: dict) -> list[str]:
    cfg = cfg_de(hoja)
    metrica = cfg["metrica"]
    errores = []

    if df.empty:
        return ["Agrega al menos una fila antes de guardar."]

    metrica_num = pd.to_numeric(df[metrica], errors="coerce")
    if metrica_num.isna().any() or (metrica_num <= 0).any():
        errores.append(f"Hay filas con {metrica.lower()} vacío o en cero. "
                       f"Completa un valor mayor que cero o elimina la fila.")

    for dim in cfg["dimensiones"]:
        col = df[dim].astype(str).str.strip()
        if col.eq("").any() or df[dim].isna().any():
            errores.append(f"Hay filas sin {_nombre_dim(dim)}.")

    fuera = set(df["CENTRO_COSTO"].dropna()) - ccos_validos
    if fuera:
        errores.append("Estos centros de costo no pertenecen a tu departamento: "
                       + ", ".join(sorted(map(str, fuera))))

    if "MES" in df.columns and not df["MES"].isin(MESES).all():
        errores.append("Hay meses inválidos. Elige un mes de la lista.")

    if cfg["tarifa"] == "catalogo":
        malos = set(df[cfg["catalogo_key"]].dropna()) - set(tarifas)
        if malos:
            errores.append("Estos tipos no tienen tarifa en el catálogo: "
                           + ", ".join(sorted(map(str, malos))))

    return errores


def _nombre_dim(dim: str) -> str:
    return {
        "DNI": "DNI",
        "NOMBRE": "nombre",
        "CENTRO_COSTO": "centro de costo",
        "CONCEPTO": "concepto",
        "CONCEPTO_2": "detalle del concepto",
        "TIPO": "tipo",
        "MES": "mes",
    }.get(dim, dim.lower())
