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

import concurrent.futures
import time
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


# TIMEOUT_CONEXION: segundos que se espera a pytds antes de cortar a la
# fuerza. pytds no siempre respeta su propio login_timeout durante el
# handshake TLS; si la red lo bloquea en silencio (firewall que descarta
# en vez de rechazar), la app se queda colgada sin ningún error visible.
# Se corre pytds.connect() en un hilo aparte para poder darle un límite
# duro, e imprime cada paso a stdout para que quede en los logs de Cloud.
TIMEOUT_CONEXION = 15


def _conectar_con_timeout(server, port, database, user, password):
    import pytds

    def _intentar():
        print(f"[sql] conectando a {server}:{port}/{database}...", flush=True)
        t0 = time.time()
        conn = pytds.connect(
            server=server, port=port, database=database,
            user=user, password=password,
            autocommit=False, login_timeout=TIMEOUT_CONEXION,
        )
        print(f"[sql] conectado en {time.time() - t0:.1f}s", flush=True)
        return conn

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        futuro = ex.submit(_intentar)
        try:
            return futuro.result(timeout=TIMEOUT_CONEXION + 5)
        except concurrent.futures.TimeoutError:
            print(f"[sql] TIMEOUT forzado tras {TIMEOUT_CONEXION + 5}s: pytds no "
                  "respondió (bloqueo de red a nivel de conexión/TLS, no error "
                  "de login).", flush=True)
            raise TimeoutError(
                f"No se pudo conectar a {server}:{port} en "
                f"{TIMEOUT_CONEXION + 5}s. La conexión se quedó colgada sin "
                "responder (probable bloqueo de red, no credenciales).")


class RepositorioSQL:
    """Producción sobre Azure SQL. Requiere secrets['sql'].

    Usa python-tds (import pytds): driver 100% Python, sin dependencias de
    sistema. En Streamlit Community Cloud no se puede instalar ni el ODBC
    Driver 18 de Microsoft (exige su propio repo APT) ni FreeTDS vía apt
    (tdsodbc choca con el unixODBC que ya trae la imagen); pytds evita el
    problema por completo al no necesitar nada fuera de pip.

    Nota de sintaxis: los parámetros usan %s (paramstyle de pytds), no el
    ? de pyodbc/ODBC."""

    modo = "sql"

    def __init__(self, secrets):
        s = secrets["sql"]
        self._server = s["server"]
        self._port = int(s.get("port", 1433))
        self._database = s["database"]
        self._user = s["username"]
        self._password = s["password"]

    @contextmanager
    def _conn(self):
        conn = _conectar_con_timeout(
            self._server, self._port, self._database,
            self._user, self._password)
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
                "SELECT CODIGO_CECO, DESCRIPCION_CECO FROM cc WHERE DEPARTAMENTO = %s",
                conn, params=[origen])

    def tarifas(self, hoja: str) -> dict:
        with self._conn() as conn:
            df = pd.read_sql(
                "SELECT TIPO, TARIFA FROM tarifas_2026 WHERE HOJA_ORIGEN = %s",
                conn, params=[hoja])
        return dict(zip(df["TIPO"], df["TARIFA"]))

    def roster(self, origen: str) -> pd.DataFrame:
        with self._conn() as conn:
            return pd.read_sql(
                "SELECT DNI, NOMBRE FROM padron_docentes WHERE DEPARTAMENTO = %s",
                conn, params=[origen])

    def estructura_tc(self, origen: str) -> pd.DataFrame:
        # TODO: todavía no existe una tabla maestra CECO -> conceptos en SQL.
        # Cuando se cree (p. ej. CECO_CONCEPTO_TC con columnas CODIGO_CECO,
        # DESCRIPCION_CECO, CONCEPTO, DEPARTAMENTO), reemplazar por algo como:
        #   SELECT CODIGO_CECO, DESCRIPCION_CECO, CONCEPTO
        #   FROM CECO_CONCEPTO_TC WHERE DEPARTAMENTO = %s
        raise NotImplementedError(
            "estructura_tc: falta la tabla maestra CECO->concepto en SQL.")

    def guardar(self, hoja: str, origen: str, filas: list[list], cols: list[str],
                sps: list[tuple]) -> int:
        """DELETE + INSERT parametrizado + EXEC, en una sola transacción.
        Si algo falla, rollback: nunca quedan datos borrados a medio cargar."""
        placeholders = ", ".join(["%s"] * len(cols))
        sql_insert = f"INSERT INTO DATOS_ENTRADA ({', '.join(cols)}) VALUES ({placeholders})"
        sql_delete = "DELETE FROM DATOS_ENTRADA WHERE HOJA_ORIGEN = %s AND ORIGEN = %s"
        with self._conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql_delete, [hoja, origen])
                cur.executemany(sql_insert, filas)
                for sp, lleva_origen in sps:
                    if lleva_origen:
                        cur.execute(f"EXEC {sp} @OrigenEntrada = %s", [origen])
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
            print("[sql] secrets['sql'] encontrado, modo SQL (no conecta todavía; "
                  "la conexión real se abre en el primer query)", flush=True)
            return RepositorioSQL(st.secrets)
    except Exception as e:
        print(f"[sql] error leyendo secrets, cae a modo demo: {e!r}", flush=True)
    print("[sql] sin secrets['sql'], modo demo", flush=True)
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
