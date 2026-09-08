"""
Capa de datos con dos implementaciones intercambiables.

  RepositorioSQL   producción: Azure SQL vía pyodbc, con carga transaccional
                   (DELETE + INSERT parametrizado + EXEC, todo o nada).
  RepositorioDemo  demostración: catálogos y padrón de ejemplo en memoria,
                   sin base de datos. Permite desplegar y mostrar la UX sin
                   credenciales.

crear_repositorio() elige según haya o no secrets de SQL configurados.
La interfaz es idéntica, así que la interfaz de usuario no distingue el modo.
"""

from __future__ import annotations

from contextlib import contextmanager

import pandas as pd
import streamlit as st

from .config import cfg_de


# ---------------------------------------------------------------------
# Datos de ejemplo (derivados de las hojas reales del formato 2026)
# ---------------------------------------------------------------------
_CCOS_DEMO = {
    "DAIC": [
        ("03.01.07.01.01", "Gestión administrativa"),
        ("03.01.07.02.01", "Escuela de Ingeniería"),
        ("03.01.07.02.02", "Escuela de Arquitectura"),
        ("03.01.07.03.01", "Postgrado"),
        ("03.01.07.04.01", "Investigación"),
        ("03.01.07.05.01", "Servicio y proyección"),
    ],
    "DMAT": [
        ("03.01.08.01.01", "Gestión administrativa"),
        ("03.01.08.02.01", "Escuela de Matemática"),
        ("03.01.08.04.01", "Investigación"),
    ],
}

# Catálogo de tarifas por tipo (server-side; el usuario nunca lo teclea).
_TARIFAS_DEMO = {
    "Horas Adicionales": {"Asistente": 93.0, "Jefe de práctica": 98.0, "Titular": 140.65},
    "Ayudantias": {"Pregrado": 4.5, "Postgrado": 6.0},
}

_ROSTER_DEMO = {
    "DAIC": [
        ("43931784", "Acero Condori, Roberto"),
        ("41402789", "Almonte Burgos, Juan Carlos"),
        ("42870321", "Calderón Colca, Yaneth"),
        ("40163004", "Cano Valencia, Alejandro"),
        ("70004934", "Carpio Salazar, Yimy"),
    ],
    "DMAT": [
        ("29876543", "Delgado Rivera, Ana"),
        ("31122334", "Fuentes Loayza, Marco"),
    ],
}

_DEPARTAMENTOS = [("DAIC", "Arquitectura e Ingeniería"),
                  ("DMAT", "Matemática y Estadística")]


class RepositorioDemo:
    """Todo en memoria. No escribe en ninguna base."""

    modo = "demo"

    def departamentos(self):
        return _DEPARTAMENTOS

    def centros_costo(self, origen: str) -> pd.DataFrame:
        filas = _CCOS_DEMO.get(origen, [])
        return pd.DataFrame(filas, columns=["CODIGO_CECO", "DESCRIPCION_CECO"])

    def tarifas(self, hoja: str) -> dict:
        return dict(_TARIFAS_DEMO.get(hoja, {}))

    def roster(self, origen: str) -> pd.DataFrame:
        filas = _ROSTER_DEMO.get(origen, [])
        return pd.DataFrame(filas, columns=["DNI", "NOMBRE"])

    def guardar(self, hoja: str, origen: str, filas: list[list]) -> int:
        # En demo no se persiste; se confirma como si hubiera cargado.
        return len(filas)


class RepositorioSQL:
    """Producción sobre Azure SQL. Requiere secrets['sql']."""

    modo = "sql"

    def __init__(self, secrets):
        s = secrets["sql"]
        self._cn = (
            f"DRIVER={{ODBC Driver 18 for SQL Server}};SERVER={s['server']};"
            f"DATABASE={s['database']};UID={s['username']};PWD={s['password']};"
            f"Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30;"
        )

    @contextmanager
    def _conn(self):
        import pyodbc
        conn = pyodbc.connect(self._cn, autocommit=False)  # transacción manual
        try:
            yield conn
        finally:
            conn.close()

    def departamentos(self):
        with self._conn() as conn:
            df = pd.read_sql("SELECT CODIGO, DESCRIPCION FROM direccion", conn)
        return list(df.itertuples(index=False, name=None))

    def centros_costo(self, origen: str) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql(
                "SELECT CODIGO_CECO, DESCRIPCION_CECO FROM cc WHERE DEPARTAMENTO = ?",
                conn, params=[origen])

    def tarifas(self, hoja: str) -> dict:
        with self._conn() as conn:
            df = pd.read_sql(
                "SELECT TIPO, TARIFA FROM tarifas_2026 WHERE HOJA_ORIGEN = ?",
                conn, params=[hoja])
        return dict(zip(df["TIPO"], df["TARIFA"]))

    def roster(self, origen: str) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql(
                "SELECT DNI, NOMBRE FROM padron_docentes WHERE DEPARTAMENTO = ?",
                conn, params=[origen])

    def guardar(self, hoja: str, origen: str, filas: list[list], cols: list[str],
                sps: list[tuple]) -> int:
        """DELETE + INSERT parametrizado + EXEC, en una sola transacción.
        Si algo falla, rollback: nunca quedan datos borrados a medio cargar."""
        placeholders = ", ".join(["?"] * len(cols))
        sql_insert = f"INSERT INTO DATOS_ENTRADA ({', '.join(cols)}) VALUES ({placeholders})"
        sql_delete = "DELETE FROM DATOS_ENTRADA WHERE HOJA_ORIGEN = ? AND ORIGEN = ?"
        with self._conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql_delete, [hoja, origen])
                cur.fast_executemany = True
                cur.executemany(sql_insert, filas)
                for sp, lleva_origen in sps:
                    if lleva_origen:
                        cur.execute(f"EXEC {sp} @OrigenEntrada = ?", [origen])
                    else:
                        cur.execute(f"EXEC {sp}")
                conn.commit()
                return len(filas)
            except Exception:
                conn.rollback()
                raise


@st.cache_resource
def crear_repositorio():
    """Devuelve el repositorio adecuado. Sin secrets de SQL → modo demo."""
    try:
        if "sql" in st.secrets:
            return RepositorioSQL(st.secrets)
    except Exception:
        pass
    return RepositorioDemo()


def preparar_filas(hoja: str, origen: str, df: pd.DataFrame, repo) -> tuple[list, list]:
    """Convierte la grilla del usuario en filas listas para DATOS_ENTRADA.
    Aplica la tarifa desde el catálogo (server-side) cuando corresponde;
    el usuario nunca la teclea."""
    cfg = cfg_de(hoja)
    cols = ["HOJA_ORIGEN", "ORIGEN"] + cfg["dimensiones"] + [cfg["metrica"]]
    tarifas = {}
    if cfg["tarifa"] == "catalogo":
        cols.append("TARIFA")
        tarifas = repo.tarifas(hoja)

    filas = []
    for _, r in df.iterrows():
        reg = {"HOJA_ORIGEN": hoja, "ORIGEN": origen}
        for dim in cfg["dimensiones"]:
            reg[dim] = r[dim]
        reg[cfg["metrica"]] = float(r[cfg["metrica"]])
        if cfg["tarifa"] == "catalogo":
            reg["TARIFA"] = float(tarifas[r[cfg["catalogo_key"]]])
        filas.append([reg[c] for c in cols])
    return filas, cols
