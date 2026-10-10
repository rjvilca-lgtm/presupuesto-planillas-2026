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

# Estructura CECO -> conceptos para la ficha por docente (planillas TC).
# Vocabulario de conceptos derivado de las columnas de horas (G-W) de la
# hoja real "Hoja DTC.xlsx" (una fila por docente, un CECO puede repetirse
# en varios conceptos), pero mapeado sobre los CECOs demo de arriba.
# TODO: cuando exista la tabla maestra en SQL (p. ej. CECO_CONCEPTO_TC),
# reemplazar este dict y RepositorioSQL.estructura_tc() por una consulta a
# esa tabla, filtrada por departamento.
_CECO_CONCEPTOS_DEMO = {
    "DAIC": {
        "03.01.07.01.01": ["Gestión Administrativa", "Gestión de Dirección"],
        "03.01.07.02.01": ["Horas Dictado Pregrado", "Otras Actividades Pregrado"],
        "03.01.07.02.02": ["Horas Dictado Pregrado", "Otras Actividades Pregrado"],
        "03.01.07.03.01": ["Gestión Administrativa Postgrado"],
        "03.01.07.04.01": ["Gestión Administrativa Investigación", "Horas de Investigación"],
        "03.01.07.05.01": ["Proyectos Solidarios", "Servicios a Terceros"],
    },
    "DMAT": {
        "03.01.08.01.01": ["Gestión Administrativa", "Gestión de Dirección"],
        "03.01.08.02.01": ["Horas Dictado Pregrado", "Otras Actividades Pregrado"],
        "03.01.08.04.01": ["Gestión Administrativa Investigación", "Horas de Investigación"],
    },
}


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

    def estructura_tc(self, origen: str) -> pd.DataFrame:
        """CECO -> conceptos para la ficha por docente (planillas TC).
        Una fila por par (CODIGO_CECO, CONCEPTO); un mismo CECO puede
        repetirse con varios conceptos, igual que en la hoja real."""
        ccos = dict(_CCOS_DEMO.get(origen, []))
        conceptos = _CECO_CONCEPTOS_DEMO.get(origen, {})
        filas = [
            (ceco, ccos.get(ceco, ceco), concepto)
            for ceco, lista in conceptos.items()
            for concepto in lista
        ]
        return pd.DataFrame(filas, columns=["CODIGO_CECO", "DESCRIPCION_CECO", "CONCEPTO"])

    def guardar(self, hoja: str, origen: str, filas: list[list]) -> int:
        # En demo no se persiste; se confirma como si hubiera cargado.
        return len(filas)


class RepositorioSQL:
    """Producción sobre Azure SQL. Requiere secrets['sql']."""

    modo = "sql"

    def __init__(self, secrets):
        s = secrets["sql"]
        # Driver por defecto: FreeTDS, el único que se puede instalar en
        # Streamlit Community Cloud (vía packages.txt; el "ODBC Driver 18 for
        # SQL Server" de Microsoft requiere su propio repo APT, que ahí no se
        # puede agregar). En un host propio con el driver de Microsoft
        # instalado, basta con fijar `driver = "ODBC Driver 18 for SQL
        # Server"` en secrets.toml para volver a ese camino.
        driver = s.get("driver", "FreeTDS")
        partes = [f"DRIVER={{{driver}}}", f"SERVER={s['server']}",
                  f"DATABASE={s['database']}", f"UID={s['username']}",
                  f"PWD={s['password']}"]
        if driver == "FreeTDS":
            # FreeTDS no reconoce Encrypt/TrustServerCertificate del driver de
            # Microsoft; TDS_Version 8.0 es la que negocia TLS 1.2+ con Azure
            # SQL (Azure exige TLS; versiones de protocolo más viejas fallan).
            partes += [f"PORT={s.get('port', 1433)}",
                       f"TDS_Version={s.get('tds_version', '8.0')}"]
        else:
            partes += ["Encrypt=yes", "TrustServerCertificate=no",
                       "Connection Timeout=30"]
        self._cn = ";".join(partes) + ";"

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

    def estructura_tc(self, origen: str) -> pd.DataFrame:
        # TODO: todavía no existe una tabla maestra CECO -> conceptos en SQL.
        # Cuando se cree (p. ej. CECO_CONCEPTO_TC con columnas CODIGO_CECO,
        # DESCRIPCION_CECO, CONCEPTO, DEPARTAMENTO), reemplazar por algo como:
        #   SELECT CODIGO_CECO, DESCRIPCION_CECO, CONCEPTO
        #   FROM CECO_CONCEPTO_TC WHERE DEPARTAMENTO = ?
        raise NotImplementedError(
            "estructura_tc: falta la tabla maestra CECO->concepto en SQL.")

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
    """Derrite la matriz (meses en columnas) a formato largo para DATOS_ENTRADA:
    un registro por cada celda mensual con valor > 0. Aplica la tarifa desde el
    catálogo (server-side) cuando corresponde; el usuario nunca la teclea."""
    from .config import MESES, dims_fila
    cfg = cfg_de(hoja)
    dims = dims_fila(cfg)
    metrica = cfg["metrica"]
    meses = [m for m in MESES if m in df.columns]

    largo = df.melt(id_vars=dims, value_vars=meses,
                    var_name="MES", value_name=metrica)
    largo[metrica] = pd.to_numeric(largo[metrica], errors="coerce").fillna(0.0)
    largo = largo[largo[metrica] > 0]              # solo celdas con valor

    cols = ["HOJA_ORIGEN", "ORIGEN"] + cfg["dimensiones"] + [metrica]
    tarifas = {}
    if cfg["tarifa"] == "catalogo":
        cols.append("TARIFA")
        tarifas = repo.tarifas(hoja)

    filas = []
    for _, r in largo.iterrows():
        reg = {"HOJA_ORIGEN": hoja, "ORIGEN": origen}
        for dim in cfg["dimensiones"]:               # incluye MES
            reg[dim] = r[dim]
        reg[metrica] = float(r[metrica])
        if cfg["tarifa"] == "catalogo":
            reg["TARIFA"] = float(tarifas[r[cfg["catalogo_key"]]])
        filas.append([reg[c] for c in cols])
    return filas, cols
