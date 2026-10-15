"""
Capa de datos con dos implementaciones intercambiables.

  RepositorioSQL   producción: Azure SQL vía python-tds, con carga transaccional
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

from .config import CARGA_ACADEMICA, CONCEPTO_ACADEMICAS, PRESUPUESTO, cfg_de


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
    "Horas Adicionales": {"Titular": 152.0, "Jefe de practica": 105.0, "Asistente": 100.0},
    "Ayudantias": {"Ayudantía": 4.5},
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
        return pd.DataFrame(filas, columns=["DNI", "NOMBRE"]).assign(HORAS_META=40.0)

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

    def todos_centros_costo(self) -> pd.DataFrame:
        filas = sorted({f for lista in _CCOS_DEMO.values() for f in lista})
        return pd.DataFrame(filas, columns=["CODIGO_CECO", "DESCRIPCION_CECO"])

    def carga_academica(self, actual: bool = True) -> pd.DataFrame:
        return pd.DataFrame(columns=["MES", "CENTRO_COSTO", "CONCEPTO", "IMPORTE"])

    def horas_dtc(self) -> pd.DataFrame:
        return pd.DataFrame(columns=["MES", "CENTRO_COSTO", "ORIGEN", "DNI", "NOMBRE", "HORAS"])

    def limpiar_cache(self):
        pass


# TIMEOUT_CONEXION: segundos que se espera a pytds antes de cortar a la
# fuerza. pytds no siempre respeta su propio login_timeout durante el
# handshake TLS; si la red lo bloquea en silencio (firewall que descarta
# en vez de rechazar), la app se queda colgada sin ningún error visible.
# Se corre pytds.connect() en un hilo aparte para poder darle un límite
# duro, e imprime cada paso a stdout para que quede en los logs de Cloud.
TIMEOUT_CONEXION = 15


def _conectar_con_timeout(server, port, database, user, password):
    import certifi
    import pytds

    def _intentar():
        print(f"[sql] conectando a {server}:{port}/{database}...", flush=True)
        t0 = time.time()
        conn = pytds.connect(
            server=server, port=port, database=database,
            user=user, password=password,
            autocommit=False, login_timeout=TIMEOUT_CONEXION,
            # Azure SQL exige TLS (ENCRYPT_REQ); sin cafile, pytds declara
            # "no soporto encriptación" (ENCRYPT_NOT_SUP) y el servidor
            # corta la conexión. certifi.where() da el bundle de CAs
            # públicas que valida el certificado de *.database.windows.net.
            cafile=certifi.where(),
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


# Los catálogos casi no cambian durante una sesión y Streamlit re-ejecuta el
# script en cada interacción: sin caché, cada tecla abriría varias conexiones
# TLS nuevas a Azure. Se cachean por 10 minutos (por consulta + parámetros).
@st.cache_data(ttl=600, show_spinner=False)
def _leer_cacheado(server, port, database, user, password,
                   sql: str, params: tuple) -> pd.DataFrame:
    conn = _conectar_con_timeout(server, port, database, user, password)
    try:
        cur = conn.cursor()
        cur.execute(sql, list(params))
        columnas = [d[0] for d in cur.description]
        return pd.DataFrame(cur.fetchall(), columns=columnas)
    finally:
        conn.close()


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

    def _leer(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        return _leer_cacheado(self._server, self._port, self._database,
                              self._user, self._password, sql, params)

    def departamentos(self):
        df = self._leer("SELECT CODIGO, DESCRIPCION FROM Departamentos ORDER BY CODIGO")
        return list(df.itertuples(index=False, name=None))

    def centros_costo(self, origen: str) -> pd.DataFrame:
        # CENTROS_COSTOS.DEPARTAMENTO guarda la descripción del departamento,
        # no el código: se cruza vía Departamentos.
        return self._leer(
            "SELECT c.CENTRO_COSTO AS CODIGO_CECO, c.DESCRIPCION_CC AS DESCRIPCION_CECO "
            "FROM CENTROS_COSTOS c JOIN Departamentos d ON d.DESCRIPCION = c.DEPARTAMENTO "
            "WHERE d.CODIGO = %s ORDER BY c.CENTRO_COSTO", (origen,))

    def tarifas(self, hoja: str) -> dict:
        df = self._leer("SELECT TIPO, TARIFA FROM tarifas_2027 WHERE HOJA_ORIGEN = %s",
                        (hoja,))
        return {t: float(v) for t, v in zip(df["TIPO"], df["TARIFA"])}

    def roster(self, origen: str) -> pd.DataFrame:
        """Padrón del departamento. HORAS_META: horas cronológicas que debe
        sumar el plan de trabajo del docente (40, o menos si es carga parcial)."""
        df = self._leer(
            "SELECT DNI, NOMBRE, MAX(HORAS) AS HORAS_META FROM HORAS_DOCENTES "
            "WHERE DPTO = %s GROUP BY DNI, NOMBRE ORDER BY NOMBRE", (origen,))
        df["HORAS_META"] = pd.to_numeric(df["HORAS_META"], errors="coerce")
        return df

    def estructura_tc(self, origen: str) -> pd.DataFrame:
        """CECO -> conceptos de la ficha TC para el departamento.

        Fuente: la tabla maestra CECO_CONCEPTO_TC (sql/crear_ceco_concepto_tc.sql).
        Mientras no exista, se deriva de las cargas TC que ya hay en
        DATOS_ENTRADA (las tres hojas que procesa sp_ValorizarPlanilla_Total_2026),
        con la limitación de que un concepto guardado con 0 horas en todas las
        hojas TC deja de aparecer. Puede incluir CECOs de otros departamentos
        (docentes transversales)."""
        existe = self._leer("SELECT OBJECT_ID('dbo.CECO_CONCEPTO_TC', 'U') AS ID")
        if existe["ID"].iloc[0] is not None:
            return self._leer(
                # CENTRO_COSTO '0' es intencional: horas de Gestión de Dirección
                # que valoriza Desarrollo Humano y se excluyen del reporte. Cuentan
                # en el total de horas del docente (reparto del sueldo en el sp).
                "SELECT t.CENTRO_COSTO AS CODIGO_CECO, "
                "CASE WHEN t.CENTRO_COSTO = '0' THEN N'Gestión de Dirección (sin centro de costo; la valoriza Desarrollo Humano)' "
                "ELSE COALESCE(c.DESCRIPCION_CC, t.CENTRO_COSTO) END AS DESCRIPCION_CECO, "
                "t.CONCEPTO "
                "FROM CECO_CONCEPTO_TC t "
                "LEFT JOIN CENTROS_COSTOS c ON c.CENTRO_COSTO = t.CENTRO_COSTO "
                "WHERE t.DEPARTAMENTO = %s AND t.ACTIVO = 1 "
                "ORDER BY t.CENTRO_COSTO, t.CONCEPTO", (origen,))
        return self._leer(
            "SELECT DISTINCT LTRIM(RTRIM(de.CENTRO_COSTO)) AS CODIGO_CECO, "
            "CASE WHEN LTRIM(RTRIM(de.CENTRO_COSTO)) = '0' THEN N'Gestión de Dirección (sin centro de costo; la valoriza Desarrollo Humano)' "
            "ELSE COALESCE(c.DESCRIPCION_CC, LTRIM(RTRIM(de.CENTRO_COSTO))) END AS DESCRIPCION_CECO, "
            "LTRIM(RTRIM(de.CONCEPTO)) AS CONCEPTO "
            "FROM DATOS_ENTRADA de "
            "LEFT JOIN CENTROS_COSTOS c ON c.CENTRO_COSTO = LTRIM(RTRIM(de.CENTRO_COSTO)) "
            "WHERE de.ORIGEN = %s "
            "AND de.HOJA_ORIGEN IN ('1. Plan TC-I', 'Plan TC-II', 'Plan TC Transversales') "
            "AND NULLIF(LTRIM(RTRIM(de.CONCEPTO)), '') IS NOT NULL "
            "AND LTRIM(RTRIM(de.CONCEPTO)) <> '0' "
            "ORDER BY CODIGO_CECO, CONCEPTO", (origen,))

    def todos_centros_costo(self) -> pd.DataFrame:
        return self._leer(
            "SELECT DISTINCT CENTRO_COSTO AS CODIGO_CECO, DESCRIPCION_CC AS DESCRIPCION_CECO "
            "FROM CENTROS_COSTOS ORDER BY CENTRO_COSTO")

    def carga_academica(self, actual: bool = True) -> pd.DataFrame:
        """Filas de la hoja Carga Academica en DATOS_ENTRADA. actual=True: las
        de PRESUPUESTO (2027); False: las del Excel 2026 (PRESUPUESTO NULL),
        que sirven de punto de partida."""
        filtro = "PRESUPUESTO = %s" if actual else "PRESUPUESTO IS NULL"
        params = (CARGA_ACADEMICA["hoja"], CARGA_ACADEMICA["origen"]) + (
            (PRESUPUESTO,) if actual else ())
        return self._leer(
            "SELECT LTRIM(RTRIM(MES)) AS MES, LTRIM(RTRIM(CENTRO_COSTO)) AS CENTRO_COSTO, "
            "LTRIM(RTRIM(CONCEPTO)) AS CONCEPTO, CAST(IMPORTE AS float) AS IMPORTE "
            "FROM DATOS_ENTRADA WHERE HOJA_ORIGEN = %s AND ORIGEN = %s AND " + filtro,
            params)

    def horas_dtc(self) -> pd.DataFrame:
        """Horas académicas de dictado de los planes TC 2027 por docente, centro
        de costo y semestre: las que sp_Valorizar_CargaAcademica_2027 resta de
        las horas de titulares (mismo filtro y misma regla de semestre: MES
        1-7 -> 2027-1, 8-12 -> 2027-2)."""
        sem1, sem2 = CARGA_ACADEMICA["semestres"]
        return self._leer(
            "SELECT MES, CENTRO_COSTO, ORIGEN, DNI, NOMBRE, "
            "CAST(SUM(HORAS) AS float) AS HORAS FROM ("
            "  SELECT CASE WHEN TRY_CAST(MES AS INT) BETWEEN 1 AND 7 THEN %s "
            "              WHEN TRY_CAST(MES AS INT) BETWEEN 8 AND 12 THEN %s END AS MES, "
            "  LTRIM(RTRIM(CENTRO_COSTO)) AS CENTRO_COSTO, ORIGEN, DNI, NOMBRE, "
            "  ISNULL(HORAS, 0) AS HORAS "
            "  FROM DATOS_ENTRADA "
            "  WHERE LTRIM(RTRIM(HOJA_ORIGEN)) IN ('Plan TC Transversales', '1. Plan TC-I', 'Plan TC-II') "
            "  AND LTRIM(RTRIM(CONCEPTO)) = %s AND PRESUPUESTO = %s"
            ") t GROUP BY MES, CENTRO_COSTO, ORIGEN, DNI, NOMBRE",
            (sem1, sem2, CONCEPTO_ACADEMICAS, PRESUPUESTO))

    def limpiar_cache(self):
        """Tras guardar: la consulta debe ver lo recién cargado, no la copia
        cacheada por 10 minutos."""
        _leer_cacheado.clear()

    def guardar(self, hoja: str, origen: str, filas: list[list], cols: list[str],
                sps: list[tuple]) -> int:
        """DELETE + INSERT parametrizado + EXEC, en una sola transacción.
        El DELETE solo alcanza las filas del PRESUPUESTO de la app.
        Si algo falla, rollback: nunca quedan datos borrados a medio cargar."""
        placeholders = ", ".join(["%s"] * len(cols))
        sql_insert = f"INSERT INTO DATOS_ENTRADA ({', '.join(cols)}) VALUES ({placeholders})"
        sql_delete = ("DELETE FROM DATOS_ENTRADA "
                      "WHERE HOJA_ORIGEN = %s AND ORIGEN = %s AND PRESUPUESTO = %s")
        print(f"[guardar] {PRESUPUESTO} · {hoja} · {origen}: {len(filas)} fila(s)", flush=True)
        with self._conn() as conn:
            cur = conn.cursor()
            try:
                cur.execute(sql_delete, [hoja, origen, PRESUPUESTO])
                print(f"[guardar] DELETE previo: {cur.rowcount} fila(s)", flush=True)
                cur.executemany(sql_insert, filas)
                print("[guardar] INSERT ok", flush=True)
                for sp, lleva_origen in sps:
                    if lleva_origen:
                        cur.execute(f"EXEC {sp} @OrigenEntrada = %s", [origen])
                    else:
                        cur.execute(f"EXEC {sp}")
                    print(f"[guardar] EXEC {sp} ok", flush=True)
                conn.commit()
                print("[guardar] COMMIT", flush=True)
                return len(filas)
            except Exception as e:
                conn.rollback()
                print(f"[guardar] ROLLBACK por error: {e!r}", flush=True)
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
    catálogo (server-side) cuando corresponde; el usuario nunca la teclea.
    MES sale como número ("1".."12") y la métrica cae en cfg["columna_destino"]
    si está definida (ver config.py)."""
    from .config import MESES, dims_fila
    cfg = cfg_de(hoja)
    dims = dims_fila(cfg)
    metrica = cfg["metrica"]
    destino = cfg.get("columna_destino", metrica)
    meses = [m for m in MESES if m in df.columns]

    # La tarifa editable viaja como columna propia de la fila
    ids = dims + (["TARIFA"] if cfg.get("tarifa_editable") and "TARIFA" in df else [])
    largo = df.melt(id_vars=ids, value_vars=meses,
                    var_name="MES", value_name=metrica)
    largo[metrica] = pd.to_numeric(largo[metrica], errors="coerce").fillna(0.0)
    largo = largo[largo[metrica] > 0]              # solo celdas con valor
    largo["MES"] = largo["MES"].map(lambda m: str(MESES.index(m) + 1))

    cols = ["PRESUPUESTO", "HOJA_ORIGEN", "ORIGEN"] + cfg["dimensiones"] + [destino]
    tarifas = {}
    if cfg["tarifa"] == "catalogo":
        cols.append("TARIFA")
        tarifas = repo.tarifas(hoja)

    filas = []
    for _, r in largo.iterrows():
        reg = {"PRESUPUESTO": PRESUPUESTO, "HOJA_ORIGEN": hoja, "ORIGEN": origen}
        for dim in cfg["dimensiones"]:               # incluye MES
            reg[dim] = r[dim]
        reg[destino] = float(r[metrica])
        if cfg["tarifa"] == "catalogo":
            reg["TARIFA"] = float(tarifas[r[cfg["catalogo_key"]]])
            propia = pd.to_numeric(r.get("TARIFA"), errors="coerce") \
                if cfg.get("tarifa_editable") else None
            if propia is not None and pd.notna(propia) and propia > 0:
                reg["TARIFA"] = float(propia)
        filas.append([reg[c] for c in cols])
    return filas, cols
