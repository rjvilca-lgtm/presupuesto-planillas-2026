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
import threading
import time
from contextlib import contextmanager

import pandas as pd
import streamlit as st

from .config import (CARGA_ACADEMICA, CONCEPTO_ACADEMICAS, MESES, PLANILLAS,
                     PRESUPUESTO, cfg_de, dims_fila)

# Columnas de DATOS_ENTRADA que se leen para retomar lo guardado
COLS_ENTRADA = ["HOJA_ORIGEN", "DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "CONCEPTO_2",
                "TIPO", "TIPO_BLOQUE", "MES", "HORAS", "IMPORTE", "TARIFA"]
# Componentes del salario (Remuneraciones_2027); el sp 2027 suma todos
COLS_REMUNERACION = ["Basico", "Asignacion_Familiar", "Bonificacion_Docente_TC",
                     "Bonificacion_Dedicacion_Exclusiva", "Bono_por_Decano",
                     "Bono_por_Director_de_Escuela", "Bono_por_Departamento", "Bono_al_Cargo",
                     "Bonificacion_Variable_por_Profesor_Extranjero",
                     "Bonificacion_Ordinaria_por_Acuerdo_Rem", "Bonificacion_por_Representacion",
                     "Grado_de_Maestria", "Grado_de_Doctorado", "Asignacion_por_Vivienda",
                     "Asignacion_por_Hijo_Menor", "Vale_por_Alimentos"]
DATOS_REMUNERACION = ["DNI", "Nombre", "Categoria", "DPTO"]
CAMPOS_ESTADO = {"BLOQUEO", "CERRADO", "FECHA_GUARDADO", "FECHA_VALORIZACION",
                 "FECHA_CIERRE"}


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

    # En demo lo guardado y el estado viven en memoria del proceso
    _entrada: dict = {}
    _estados: dict = {}
    _fecha_bloqueo = None

    def guardar_borrador(self, hoja, origen, filas, cols) -> int:
        df = pd.DataFrame(filas, columns=cols)
        self._entrada[(hoja, origen)] = df.reindex(columns=COLS_ENTRADA).assign(HOJA_ORIGEN=hoja)
        return len(filas)

    def entrada(self, origen: str) -> pd.DataFrame:
        partes = [df for (h, o), df in self._entrada.items() if o == origen]
        return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame(columns=COLS_ENTRADA)

    def valorizar(self, origen: str, sps: list[tuple]) -> None:
        pass

    def estado_flujo(self):
        filas = [{"DEPARTAMENTO": d, **e} for d, e in self._estados.items()]
        return pd.DataFrame(filas), self._fecha_bloqueo, True

    def actualizar_estado(self, depto: str, **campos):
        assert set(campos) <= CAMPOS_ESTADO
        self._estados.setdefault(depto, {}).update(campos)

    def fijar_fecha_bloqueo(self, fecha):
        RepositorioDemo._fecha_bloqueo = fecha

    _usuarios: list = []

    def valorizacion(self, anio: int, origenes: list[str]) -> pd.DataFrame:
        return pd.DataFrame(columns=["DEPTO", "ORIGEN", "PARTIDA", "DESCRIPCION",
                                     "CENTRO_COSTO", "MES", "IMPORTE"])

    def parametros(self):
        return None

    def permisos_usuario(self, email: str) -> pd.DataFrame:
        filas = [u for u in self._usuarios if u["EMAIL"] == email and u.get("ACTIVO", True)]
        return pd.DataFrame(filas, columns=["ROL", "DEPARTAMENTO"])

    def listar_usuarios(self) -> pd.DataFrame:
        return pd.DataFrame(self._usuarios, columns=["EMAIL", "ROL", "DEPARTAMENTO", "ACTIVO"])

    def guardar_usuario(self, email, rol, departamento, activo=True):
        self._usuarios = [u for u in self._usuarios if (u["EMAIL"], u["ROL"], u["DEPARTAMENTO"])
                          != (email, rol, departamento)]
        self._usuarios.append({"EMAIL": email, "ROL": rol, "DEPARTAMENTO": departamento,
                               "ACTIVO": activo})


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
            validate_host=True,   # el certificado debe ser de este servidor
        )
        # Comunicación cifrada obligatoria: si la sesión no quedó con TLS, no se usa
        cur = conn.cursor()
        cur.execute("SELECT encrypt_option FROM sys.dm_exec_connections "
                    "WHERE session_id = @@SPID")
        cifrada = str(cur.fetchone()[0]).upper() == "TRUE"
        conn.rollback()
        if not cifrada:
            conn.close()
            raise ConnectionError("La conexión con la base de datos no está cifrada; "
                                  "se rechazó por seguridad.")
        print(f"[sql] conectado (cifrado TLS) en {time.time() - t0:.1f}s", flush=True)
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
@st.cache_resource(show_spinner=False)
def _conexion_lectura(server, port, database, user):
    """Una conexión de lectura compartida por todas las sesiones. Abrir una
    conexión TLS a Azure cuesta ~0.7 s (más desde Streamlit Cloud): con una
    por consulta, la primera carga de la página tardaba 15-20 s. El lock
    serializa las lecturas (pytds no admite uso concurrente de una conexión)."""
    return {"conn": None, "lock": threading.Lock()}


def _consultar(server, port, database, user, password,
               sql: str, params: tuple) -> pd.DataFrame:
    compartida = _conexion_lectura(server, port, database, user)
    with compartida["lock"]:
        for intento in (1, 2):
            if compartida["conn"] is None:
                compartida["conn"] = _conectar_con_timeout(server, port, database,
                                                           user, password)
            conn = compartida["conn"]
            try:
                cur = conn.cursor()
                cur.execute(sql, list(params))
                columnas = [d[0] for d in cur.description]
                filas = cur.fetchall()
                conn.rollback()   # cierra la transacción implícita de la lectura
                return pd.DataFrame(filas, columns=columnas)
            except Exception as e:
                # Conexión caída (Azure cierra las inactivas): se reabre una vez
                print(f"[sql] lectura falló ({e!r}); reconectando", flush=True)
                try:
                    conn.close()
                except Exception:
                    pass
                compartida["conn"] = None
                if intento == 2:
                    raise


@st.cache_data(ttl=600, show_spinner=False)
def _leer_cacheado(server, port, database, user, password,
                   sql: str, params: tuple) -> pd.DataFrame:
    return _consultar(server, port, database, user, password, sql, params)


# Años cerrados (2026): no cambian, así que se guardan medio día y no se
# borran al guardar. La consulta del resumen 2026 tarda ~10 s en el nivel
# Basic de Azure; así solo la paga el primer usuario.
@st.cache_data(ttl=12 * 3600, show_spinner=False)
def _leer_historico(server, port, database, user, password,
                    sql: str, params: tuple) -> pd.DataFrame:
    return _consultar(server, port, database, user, password, sql, params)


@st.cache_data(ttl=20, show_spinner=False)
def _leer_corto(server, port, database, user, password,
                sql: str, params: tuple) -> pd.DataFrame:
    return _consultar(server, port, database, user, password, sql, params)


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
        # Opcional: credenciales propias para salarios ([sql_rrhh]), de un login
        # de base de datos que sea el único con acceso a Remuneraciones_2027
        try:
            self._rrhh = dict(secrets["sql_rrhh"]) if "sql_rrhh" in secrets else None
        except Exception:
            self._rrhh = None

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

    def _cecos_2027(self) -> bool:
        """¿Ya existen los centros de costo 2027 (sql/crear_cecos_2027.sql)?
        Mientras no, la app sigue con el catálogo antiguo CENTROS_COSTOS."""
        df = self._leer("SELECT OBJECT_ID('dbo.CECOS_DEPARTAMENTO_2027', 'U') AS ID")
        return df["ID"].iloc[0] is not None

    def centros_costo(self, origen: str) -> pd.DataFrame:
        if self._cecos_2027():
            # Un código 2027 puede ser de varios departamentos (p. ej. proyectos
            # de la facultad): cada uno lo ve en su lista
            return self._leer(
                "SELECT c.CENTRO_COSTO AS CODIGO_CECO, c.DESCRIPCION_CC AS DESCRIPCION_CECO "
                "FROM CECOS_DEPARTAMENTO_2027 d "
                "JOIN CENTROS_COSTOS_2027 c ON c.CENTRO_COSTO = d.CENTRO_COSTO "
                "WHERE d.DEPARTAMENTO = %s ORDER BY c.CENTRO_COSTO", (origen,))
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
        catalogo = "CENTROS_COSTOS_2027" if self._cecos_2027() else "CENTROS_COSTOS"
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
                f"LEFT JOIN {catalogo} c ON c.CENTRO_COSTO = t.CENTRO_COSTO "
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
        tabla = "CENTROS_COSTOS_2027" if self._cecos_2027() else "CENTROS_COSTOS"
        return self._leer(
            "SELECT DISTINCT CENTRO_COSTO AS CODIGO_CECO, DESCRIPCION_CC AS DESCRIPCION_CECO "
            f"FROM {tabla} ORDER BY CENTRO_COSTO")

    def carga_academica(self, actual: bool = True) -> pd.DataFrame:
        """Filas de la hoja Carga Academica en DATOS_ENTRADA. actual=True: las
        de PRESUPUESTO (2027); False: las del Excel 2026 (PRESUPUESTO NULL),
        que sirven de punto de partida."""
        filtro = "PRESUPUESTO = %s" if actual else "PRESUPUESTO IS NULL"
        params = (CARGA_ACADEMICA["hoja"], CARGA_ACADEMICA["origen"]) + (
            (PRESUPUESTO,) if actual else ())
        if not actual and self._cecos_2027():
            # 2026 con los centros de costo pasados a la codificación 2027
            return self._leer(
                "SELECT LTRIM(RTRIM(d.MES)) AS MES, "
                "COALESCE(e.CODIGO_NUEVO, LTRIM(RTRIM(d.CENTRO_COSTO))) AS CENTRO_COSTO, "
                "LTRIM(RTRIM(d.CONCEPTO)) AS CONCEPTO, CAST(SUM(d.IMPORTE) AS float) AS IMPORTE "
                "FROM DATOS_ENTRADA d LEFT JOIN EQUIVALENCIA_CECOS e "
                "ON e.CODIGO_ANTIGUO = LTRIM(RTRIM(d.CENTRO_COSTO)) "
                "WHERE d.HOJA_ORIGEN = %s AND d.ORIGEN = %s AND d." + filtro + " "
                "GROUP BY LTRIM(RTRIM(d.MES)), COALESCE(e.CODIGO_NUEVO, LTRIM(RTRIM(d.CENTRO_COSTO))), "
                "LTRIM(RTRIM(d.CONCEPTO))", params)
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
        _leer_corto.clear()

    def _leer_vivo(self, sql: str, params: tuple = ()) -> pd.DataFrame:
        """Datos que cambian con el trabajo de los usuarios (borradores,
        estados): caché de pocos segundos, que se limpia al escribir."""
        return _leer_corto(self._server, self._port, self._database,
                           self._user, self._password, sql, params)

    def entrada(self, origen: str) -> pd.DataFrame:
        """Todo lo guardado en DATOS_ENTRADA por el departamento para este
        PRESUPUESTO (todas las planillas). Sirve para retomar el trabajo y para
        el resumen antes de valorizar."""
        df = self._leer_vivo(
            f"SELECT {', '.join(COLS_ENTRADA)} FROM DATOS_ENTRADA "
            "WHERE ORIGEN = %s AND PRESUPUESTO = %s", (origen, PRESUPUESTO))
        for c in ("HORAS", "IMPORTE", "TARIFA"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        return df

    def guardar_borrador(self, hoja: str, origen: str, filas: list[list],
                         cols: list[str]) -> int:
        """Reemplaza lo guardado de la planilla sin valorizar."""
        n = self.guardar(hoja, origen, filas, cols, [])
        self.limpiar_cache()
        return n

    def valorizar(self, origen: str, sps: list[tuple]) -> None:
        """Ejecuta los sp en una sola transacción: si uno falla, ninguno queda."""
        print(f"[valorizar] {origen}: {[s for s, _ in sps]}", flush=True)
        with self._conn() as conn:
            cur = conn.cursor()
            try:
                for sp, lleva_origen in sps:
                    if lleva_origen:
                        cur.execute(f"EXEC {sp} @OrigenEntrada = %s", [origen])
                    else:
                        cur.execute(f"EXEC {sp}")
                    print(f"[valorizar] EXEC {sp} ok", flush=True)
                conn.commit()
                print("[valorizar] COMMIT", flush=True)
            except Exception as e:
                conn.rollback()
                print(f"[valorizar] ROLLBACK por error: {e!r}", flush=True)
                raise
        self.limpiar_cache()

    def estado_flujo(self):
        """(estados por departamento, fecha de bloqueo, tablas disponibles).
        Si aún no se ejecutó sql/crear_estado_presupuesto.sql, devuelve
        disponible=False y la app funciona sin bloqueos."""
        existe = self._leer_vivo(
            "SELECT OBJECT_ID('dbo.ESTADO_DEPARTAMENTO', 'U') AS E, "
            "OBJECT_ID('dbo.CONFIG_PRESUPUESTO', 'U') AS C")
        if existe["E"].iloc[0] is None or existe["C"].iloc[0] is None:
            return pd.DataFrame(), None, False
        estados = self._leer_vivo(
            "SELECT DEPARTAMENTO, BLOQUEO, CERRADO, FECHA_GUARDADO, FECHA_VALORIZACION, "
            "FECHA_CIERRE FROM ESTADO_DEPARTAMENTO WHERE PRESUPUESTO = %s", (PRESUPUESTO,))
        cfg = self._leer_vivo(
            "SELECT FECHA_BLOQUEO FROM CONFIG_PRESUPUESTO WHERE PRESUPUESTO = %s",
            (PRESUPUESTO,))
        fecha = cfg["FECHA_BLOQUEO"].iloc[0] if not cfg.empty else None
        return estados, fecha, True

    def _escribir(self, sql: str, params: list):
        with self._conn() as conn:
            cur = conn.cursor()
            cur.execute(sql, params)
            conn.commit()
        _leer_corto.clear()

    def actualizar_estado(self, depto: str, **campos):
        cols = [c for c in campos if c in CAMPOS_ESTADO]
        assert cols and len(cols) == len(campos), campos
        valores = [campos[c] for c in cols]
        sets = ", ".join(f"t.{c} = %s" for c in cols)
        self._escribir(
            "MERGE ESTADO_DEPARTAMENTO AS t "
            "USING (SELECT %s AS PRESUPUESTO, %s AS DEPARTAMENTO) AS s "
            "ON t.PRESUPUESTO = s.PRESUPUESTO AND t.DEPARTAMENTO = s.DEPARTAMENTO "
            f"WHEN MATCHED THEN UPDATE SET {sets}, t.ACTUALIZADO = SYSDATETIME() "
            f"WHEN NOT MATCHED THEN INSERT (PRESUPUESTO, DEPARTAMENTO, {', '.join(cols)}) "
            f"VALUES (s.PRESUPUESTO, s.DEPARTAMENTO, {', '.join(['%s'] * len(cols))});",
            [PRESUPUESTO, depto] + valores + valores)

    # ------------------------------------------------ Desarrollo Humano

    def _auditar(self, cur, email, tabla, accion, dni=None, detalle=None):
        cur.execute("INSERT INTO AUDITORIA_DESARROLLO_HUMANO (EMAIL, TABLA, DNI, ACCION, DETALLE) "
                    "VALUES (%s, %s, %s, %s, %s)", [email, tabla, dni, accion, detalle])

    def _transaccion(self, conn_ctx, trabajo):
        with conn_ctx as conn:
            cur = conn.cursor()
            try:
                trabajo(cur)
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        self.limpiar_cache()

    def horas_docentes_todos(self) -> pd.DataFrame:
        df = self._leer_vivo("SELECT DPTO, DNI, NOMBRE, CAST(HORAS AS float) AS HORAS "
                             "FROM HORAS_DOCENTES ORDER BY DPTO, NOMBRE")
        return df

    def dni_con_plan_tc(self) -> pd.DataFrame:
        """Docentes que ya tienen plan TC 2027 guardado por su departamento."""
        return self._leer_vivo(
            "SELECT DISTINCT ORIGEN, DNI FROM DATOS_ENTRADA WHERE PRESUPUESTO = %s "
            "AND HOJA_ORIGEN IN ('1. Plan TC-I', 'Plan TC-II')", (PRESUPUESTO,))

    def tarifas_todas(self) -> pd.DataFrame:
        return self._leer_vivo("SELECT HOJA_ORIGEN, TIPO, CAST(TARIFA AS float) AS TARIFA "
                               "FROM tarifas_2027 ORDER BY HOJA_ORIGEN, TIPO")

    def guardar_tarifas(self, cambios: list[tuple], email: str):
        """cambios: (hoja, tipo, tarifa_anterior, tarifa_nueva). Las tarifas no
        son confidenciales: la auditoría guarda los valores."""
        def trabajo(cur):
            for hoja, tipo, antes, despues in cambios:
                cur.execute("UPDATE tarifas_2027 SET TARIFA = %s "
                            "WHERE HOJA_ORIGEN = %s AND TIPO = %s", [despues, hoja, tipo])
                self._auditar(cur, email, "tarifas_2027", "CAMBIO",
                              detalle=f"{tipo} ({hoja}): {antes} -> {despues}")
        self._transaccion(self._conn(), trabajo)

    @contextmanager
    def _conn_rrhh(self):
        c = self._rrhh or {}
        conn = _conectar_con_timeout(
            c.get("server", self._server), int(c.get("port", self._port)),
            c.get("database", self._database), c.get("username", self._user),
            c.get("password", self._password))
        try:
            yield conn
        finally:
            conn.close()

    def remuneraciones(self) -> pd.DataFrame:
        """Salarios 2027. Confidencial: lectura directa, SIN caché (la caché de
        Streamlit es memoria compartida del servidor) y nunca se imprime."""
        cols = ", ".join(DATOS_REMUNERACION + [f"CAST({c} AS float) AS {c}"
                                                for c in COLS_REMUNERACION])
        with self._conn_rrhh() as conn:
            cur = conn.cursor()
            cur.execute(f"SELECT {cols} FROM Remuneraciones_2027 ORDER BY Nombre")
            nombres = [d[0] for d in cur.description]
            datos = cur.fetchall()
            conn.rollback()
        return pd.DataFrame(datos, columns=nombres)

    def importar_rrhh(self, docentes: list[list], salarios: list[list], email: str,
                      detalle: str) -> None:
        """Importación de la plantilla única: reemplaza el padrón de docentes TC
        y los salarios 2027. Con una sola cuenta de base de datos va todo en una
        transacción; con [sql_rrhh] (cuenta propia para salarios) son dos, primero
        salarios. La auditoría guarda solo conteos."""
        cols_sal = DATOS_REMUNERACION + COLS_REMUNERACION
        bloqueo = ("DECLARE @r int; EXEC @r = sp_getapplock @Resource = 'IMPORTAR_RRHH', "
                   "@LockMode = 'Exclusive', @LockOwner = 'Transaction', @LockTimeout = 30000; "
                   "IF @r < 0 THROW 50023, 'Otra importación en curso; intenta de nuevo.', 1;")

        def padron(cur):
            cur.execute("DELETE FROM HORAS_DOCENTES")
            cur.executemany("INSERT INTO HORAS_DOCENTES (DPTO, DNI, NOMBRE, HORAS) "
                            "VALUES (%s, %s, %s, %s)", docentes)

        def sueldos(cur):
            cur.execute("DELETE FROM Remuneraciones_2027")
            cur.executemany(f"INSERT INTO Remuneraciones_2027 ({', '.join(cols_sal)}) "
                            f"VALUES ({', '.join(['%s'] * len(cols_sal))})", salarios)

        if self._rrhh is None:
            def todo(cur):
                cur.execute(bloqueo)
                sueldos(cur)
                padron(cur)
                self._auditar(cur, email, "IMPORTACION", "CARGA EXCEL", detalle=detalle)
            self._transaccion(self._conn(), todo)
        else:
            def solo_sueldos(cur):
                cur.execute(bloqueo)
                sueldos(cur)
            def solo_padron(cur):
                cur.execute(bloqueo)
                padron(cur)
                self._auditar(cur, email, "IMPORTACION", "CARGA EXCEL", detalle=detalle)
            self._transaccion(self._conn_rrhh(), solo_sueldos)
            self._transaccion(self._conn(), solo_padron)

    def auditoria_dh(self) -> pd.DataFrame:
        return self._leer_vivo("SELECT TOP 200 FECHA, EMAIL, TABLA, DNI, ACCION, DETALLE "
                               "FROM AUDITORIA_DESARROLLO_HUMANO ORDER BY ID DESC")

    # ------------------------------------------------ Parámetros 2027

    def parametros(self) -> pd.DataFrame | None:
        """Tasas que leen los sp 2027 (sql/crear_parametros_2027.sql).
        None si la tabla aún no existe."""
        existe = self._leer_vivo("SELECT OBJECT_ID('dbo.PARAMETROS_2027', 'U') AS ID")
        if existe["ID"].iloc[0] is None:
            return None
        return self._leer_vivo("SELECT CODIGO, DESCRIPCION, CAST(VALOR AS float) AS VALOR, "
                               "ACTUALIZADO, EMAIL FROM PARAMETROS_2027 ORDER BY ORDEN")

    def guardar_parametros(self, cambios: list[tuple], email: str):
        """cambios: (codigo, valor_anterior, valor_nuevo). No son confidenciales:
        la auditoría guarda los valores."""
        def trabajo(cur):
            for codigo, antes, despues in cambios:
                cur.execute("UPDATE PARAMETROS_2027 SET VALOR = %s, ACTUALIZADO = SYSDATETIME(), "
                            "EMAIL = %s WHERE CODIGO = %s", [despues, email, codigo])
                cur.execute("INSERT INTO AUDITORIA_PARAMETROS (EMAIL, CODIGO, VALOR_ANTERIOR, "
                            "VALOR_NUEVO) VALUES (%s, %s, %s, %s)", [email, codigo, antes, despues])
        self._transaccion(self._conn(), trabajo)

    def auditoria_parametros(self) -> pd.DataFrame:
        return self._leer_vivo(
            "SELECT TOP 100 a.FECHA, a.EMAIL, p.DESCRIPCION, "
            "CAST(a.VALOR_ANTERIOR AS float) AS VALOR_ANTERIOR, "
            "CAST(a.VALOR_NUEVO AS float) AS VALOR_NUEVO "
            "FROM AUDITORIA_PARAMETROS a LEFT JOIN PARAMETROS_2027 p ON p.CODIGO = a.CODIGO "
            "ORDER BY a.ID DESC")

    def valorizacion(self, anio: int, origenes: list[str]) -> pd.DataFrame:
        """Montos de PLANILLA por departamento (ORIGEN_2), planilla, partida,
        centro de costo y mes. 2026 casi no cambia (caché de 10 min); 2027
        cambia con cada valorización (caché corta)."""
        if not origenes:
            return pd.DataFrame(columns=["DEPTO", "ORIGEN", "PARTIDA", "DESCRIPCION",
                                         "CENTRO_COSTO", "MES", "IMPORTE"])
        marcas = ", ".join(["%s"] * len(origenes))
        sql = ("SELECT p.ORIGEN_2 AS DEPTO, p.ORIGEN, p.PARTIDA, pp.Descripcion AS DESCRIPCION, "
               "p.CENTRO_COSTO, p.MES, CAST(SUM(p.IMPORTE) AS float) AS IMPORTE "
               "FROM PLANILLA p LEFT JOIN PartidaPresupuestal pp ON pp.Codigo = p.PARTIDA "
               # AÑO es varchar: compararlo con texto deja usar IX_PLANILLA_ANIO
               # (con un número SQL convierte toda la columna y la recorre entera)
               f"WHERE p.AÑO = CAST(%s AS varchar(20)) AND p.ORIGEN_2 IN ({marcas}) "
               "GROUP BY p.ORIGEN_2, p.ORIGEN, p.PARTIDA, pp.Descripcion, p.CENTRO_COSTO, p.MES")
        if anio < 2027:
            return _leer_historico(self._server, self._port, self._database, self._user,
                                   self._password, sql, (str(anio), *origenes))
        return self._leer_vivo(sql, (str(anio), *origenes))

    def permisos_usuario(self, email: str) -> pd.DataFrame:
        """Roles activos del correo (ver sql/crear_usuarios_planillas.sql)."""
        return self._leer_vivo(
            "SELECT ROL, DEPARTAMENTO FROM USUARIOS_PLANILLAS "
            "WHERE LOWER(EMAIL) = %s AND ACTIVO = 1", (email.lower(),))

    def listar_usuarios(self) -> pd.DataFrame:
        return self._leer_vivo(
            "SELECT EMAIL, ROL, DEPARTAMENTO, ACTIVO FROM USUARIOS_PLANILLAS "
            "ORDER BY EMAIL, ROL, DEPARTAMENTO")

    def guardar_usuario(self, email: str, rol: str, departamento, activo: bool = True):
        """Alta o cambio de un acceso (EMAIL, ROL, DEPARTAMENTO)."""
        self._escribir(
            "MERGE USUARIOS_PLANILLAS AS t "
            "USING (SELECT %s AS EMAIL, %s AS ROL, %s AS DEPARTAMENTO) AS s "
            "ON LOWER(t.EMAIL) = LOWER(s.EMAIL) AND t.ROL = s.ROL "
            "AND ISNULL(t.DEPARTAMENTO, '') = ISNULL(s.DEPARTAMENTO, '') "
            "WHEN MATCHED THEN UPDATE SET t.ACTIVO = %s "
            "WHEN NOT MATCHED THEN INSERT (EMAIL, ROL, DEPARTAMENTO, ACTIVO) "
            "VALUES (s.EMAIL, s.ROL, s.DEPARTAMENTO, %s);",
            [email.lower(), rol, departamento, activo, activo])

    def fijar_fecha_bloqueo(self, fecha):
        self._escribir(
            "UPDATE CONFIG_PRESUPUESTO SET FECHA_BLOQUEO = %s, ACTUALIZADO = SYSDATETIME() "
            "WHERE PRESUPUESTO = %s", [fecha, PRESUPUESTO])

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
                # Los índices únicos filtrados de DATOS_ENTRADA (sql/crear_indices_2027.sql)
                # exigen ARITHABORT ON a quien escribe; pytds lo deja en OFF.
                cur.execute("SET ARITHABORT ON;")
                # Un solo guardado a la vez por planilla y departamento: dos
                # guardados cruzados (doble clic, dos pestañas) hacían DELETE,
                # DELETE, INSERT, INSERT y dejaban las filas duplicadas.
                cur.execute(
                    "DECLARE @r int; EXEC @r = sp_getapplock @Resource = %s, "
                    "@LockMode = 'Exclusive', @LockOwner = 'Transaction', "
                    "@LockTimeout = 30000; IF @r < 0 THROW 50020, "
                    "'Otro guardado de esta planilla está en curso; intenta de nuevo.', 1;",
                    [f"DATOS_ENTRADA|{PRESUPUESTO}|{hoja}|{origen}"])
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


def matriz_desde_entrada(hoja: str, filas: pd.DataFrame) -> pd.DataFrame:
    """Lo inverso de preparar_filas(): filas guardadas de una planilla ->
    matriz con una columna por mes (y las columnas info / TARIFA). Filas con
    las mismas dimensiones se suman en una sola."""
    cfg = cfg_de(hoja)
    dims = dims_fila(cfg)
    destino = cfg.get("columna_destino", cfg["metrica"])
    info = cfg.get("info_destino", {})
    extra = ["TARIFA"] if cfg.get("tarifa_editable") else []
    claves = list(info) + dims + extra
    f = filas.copy()
    for col, origen_col in info.items():
        f[col] = f[origen_col]
    mes = pd.to_numeric(f["MES"], errors="coerce")
    f = f[mes.between(1, 12)]
    if f.empty:
        return pd.DataFrame(columns=claves + MESES)
    f["MES"] = mes[f.index].astype(int).map(lambda m: MESES[m - 1])
    f["_valor"] = pd.to_numeric(f[destino], errors="coerce").fillna(0.0)
    # Ficha TC: una fila por (docente, CECO, concepto); si hubiera repetidas son
    # copias del mismo valor. En las grillas, filas iguales sí se suman.
    agg = "max" if cfg["usa_roster"] else "sum"
    ancho = (f.groupby(claves + ["MES"], dropna=False, sort=False)["_valor"].agg(agg)
              .unstack("MES").reset_index())
    for m in MESES:
        if m not in ancho:
            ancho[m] = float("nan")
    ancho[MESES] = ancho[MESES].where(ancho[MESES] != 0)
    ancho.columns.name = None
    return ancho[claves + MESES]


def sps_departamento() -> list[tuple]:
    """Procedimientos que valorizan un departamento: los de todas sus
    planillas, sin repetir, sin la carga académica (la valoriza la DGA)."""
    vistos, sps = set(), []
    for cfg in PLANILLAS.values():
        for sp, lleva in cfg["sps"]:
            if sp not in vistos and sp not in dict(CARGA_ACADEMICA["sps"]):
                vistos.add(sp)
                sps.append((sp, lleva))
    return sps


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
    ids += [c for c in cfg.get("info_destino", {}) if c in df]
    largo = df.melt(id_vars=ids, value_vars=meses,
                    var_name="MES", value_name=metrica)
    largo[metrica] = pd.to_numeric(largo[metrica], errors="coerce").fillna(0.0)
    largo = largo[largo[metrica] > 0]              # solo celdas con valor
    largo["MES"] = largo["MES"].map(lambda m: str(MESES.index(m) + 1))

    cols = ["PRESUPUESTO", "HOJA_ORIGEN", "ORIGEN"] + cfg["dimensiones"] + [destino]
    info_destino = cfg.get("info_destino", {})
    cols += list(info_destino.values())
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
        for col, col_destino in info_destino.items():
            reg[col_destino] = r[col] if col in largo and pd.notna(r[col]) else None
        if cfg["tarifa"] == "catalogo":
            reg["TARIFA"] = float(tarifas[r[cfg["catalogo_key"]]])
            propia = pd.to_numeric(r.get("TARIFA"), errors="coerce") \
                if cfg.get("tarifa_editable") else None
            if propia is not None and pd.notna(propia) and propia > 0:
                reg["TARIFA"] = float(propia)
        filas.append([reg[c] for c in cols])
    return filas, cols
