"""
Validación y formato — sobre el layout matricial.

La grilla trae los 12 meses como columnas. Aquí se suma por fila, se validan
solo las filas que tienen algún dato (las filas totalmente vacías del editor
dinámico se ignoran) y se estima el monto para el feedback en vivo.
"""

import pandas as pd

from .config import MESES, cfg_de, dims_fila


def formato_soles(valor: float) -> str:
    return f"S/ {valor:,.2f}"


def _meses_presentes(df: pd.DataFrame) -> list[str]:
    return [m for m in MESES if m in df.columns]


def _matriz_valores(df: pd.DataFrame) -> pd.DataFrame:
    """Las 12 columnas de mes como números, con vacíos = 0."""
    meses = _meses_presentes(df)
    return df[meses].apply(pd.to_numeric, errors="coerce").fillna(0.0)


def _filas_con_datos(df: pd.DataFrame) -> pd.Series:
    """Máscara de filas que tienen algún valor mensual > 0."""
    return _matriz_valores(df).sum(axis=1) > 0


def estimar_importe(hoja: str, df: pd.DataFrame, tarifas: dict) -> float:
    """Total presupuestado para el número en vivo."""
    cfg = cfg_de(hoja)
    if df.empty or not _meses_presentes(df):
        return 0.0
    suma_fila = _matriz_valores(df).sum(axis=1)
    if cfg["metrica"] == "IMPORTE":
        return float(suma_fila.sum())
    if cfg["tarifa"] == "catalogo":
        tarifa_fila = df[cfg["catalogo_key"]].map(tarifas).fillna(0.0)
        return float((suma_fila * tarifa_fila).sum())
    return 0.0  # tarifa server: el importe lo calcula el procedimiento en SQL


def total_horas(hoja: str, df: pd.DataFrame) -> float:
    cfg = cfg_de(hoja)
    if cfg["metrica"] != "HORAS" or df.empty or not _meses_presentes(df):
        return 0.0
    return float(_matriz_valores(df).values.sum())


def conteo(df: pd.DataFrame) -> tuple[int, int]:
    """(líneas con datos, registros mensuales que se insertarán)."""
    if df.empty or not _meses_presentes(df):
        return 0, 0
    val = _matriz_valores(df)
    lineas = int((val.sum(axis=1) > 0).sum())
    registros = int((val > 0).values.sum())
    return lineas, registros


def validar(hoja: str, df: pd.DataFrame, ccos_validos: set, tarifas: dict) -> list[str]:
    cfg = cfg_de(hoja)
    dims = dims_fila(cfg)
    errores = []

    if df.empty or not _filas_con_datos(df).any():
        return ["Ingresa horas o importes en al menos un mes antes de guardar."]

    val = _matriz_valores(df)
    if (val < 0).any().any():
        errores.append("Hay valores negativos. Usa cantidades mayores o iguales a cero.")

    sub = df[_filas_con_datos(df)]
    for dim in dims:
        col = sub[dim].astype(str).str.strip()
        if col.eq("").any() or sub[dim].isna().any():
            errores.append(f"Hay filas con datos pero sin {_nombre_dim(dim)}.")

    fuera = set(sub["CENTRO_COSTO"].dropna()) - ccos_validos
    if fuera:
        errores.append("Estos centros de costo no pertenecen a tu departamento: "
                       + ", ".join(sorted(map(str, fuera))))

    if cfg["tarifa"] == "catalogo":
        malos = set(sub[cfg["catalogo_key"]].dropna()) - set(tarifas)
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
    }.get(dim, dim.lower())
