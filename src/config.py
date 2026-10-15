"""
Configuración declarativa de las planillas — el "7 macros → 1 motor".

Cada planilla describe SU forma aquí. El motor no conoce coordenadas ni
tiene una rama por hoja: lee esta config y se comporta en consecuencia.
Agregar o cambiar una planilla = editar este diccionario.

Campos:
  etiqueta     Nombre visible para el usuario (voz de la interfaz, no la técnica).
  metrica      "HORAS" o "IMPORTE": qué teclea el usuario (y cómo se rotula).
  columna_destino  Columna de DATOS_ENTRADA donde cae la métrica, si no es la
               misma que `metrica`. Ayudantías teclea horas pero su sp las lee
               de IMPORTE (las multiplica por 4.5).
  dimensiones  Columnas que identifican cada registro.
  tarifa       "server"   → la aplica el procedimiento; el usuario no la ve.
               "catalogo" → se resuelve por TIPO desde el catálogo (server-side);
                            el usuario elige el TIPO, nunca teclea el precio.
               None       → la planilla entrega IMPORTE ya calculado.
  catalogo_key Dimensión contra la que se busca la tarifa (p. ej. "TIPO").
  tarifa_editable  Con tarifa "catalogo": la grilla muestra la columna TARIFA,
               prellenada con la del catálogo según el TIPO, y el usuario puede
               cambiarla. Se guarda en DATOS_ENTRADA.TARIFA.
  precarga     CSV (ruta relativa al repo) con filas que la grilla trae ya
               cargadas; sus columnas son dimensiones o columnas_info.
  columnas_info  Columnas que se muestran en la grilla pero no se guardan.
  opciones     {dimensión: [valores]}: la columna se elige de una lista cerrada
               (los sp reconocen esos textos exactos).
  info_destino {columna_info: columna de DATOS_ENTRADA} para guardar (y volver
               a leer) una columna informativa; p. ej. FOCO va en TIPO_BLOQUE,
               que ningún sp usa.
  usa_roster   Si True, la grilla se pre-puebla con el padrón de docentes del
               departamento para que el usuario solo complete la métrica.
               También activa la ficha por docente (vistas.ficha_docente) en
               vez de la grilla matricial.
  mes_carga    Solo para hojas con usa_roster=True: mes en el que se carga el
               valor único (horas por mes) de la ficha. sp_ValorizarPlanilla_
               Total_2026 lo replica: MARZO (3) → meses 1-7, AGOSTO (8) → 8-12.
  sps          Procedimientos de valorización a ejecutar tras la carga, en orden.
               (nombre, pasa_OrigenEntrada)

MES se escribe en DATOS_ENTRADA como número ("1".."12"): PLANILLA.MES es int y
varios sp (Postgrado, Ayudantías, CargaAcademica) hacen TRY_CAST(MES AS INT).
"""

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
         "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

# Encabezado corto para las columnas de la matriz (más meses visibles a la vez).
MESES_ABBR = {"ENERO": "Ene", "FEBRERO": "Feb", "MARZO": "Mar", "ABRIL": "Abr",
              "MAYO": "May", "JUNIO": "Jun", "JULIO": "Jul", "AGOSTO": "Ago",
              "SEPTIEMBRE": "Set", "OCTUBRE": "Oct", "NOVIEMBRE": "Nov",
              "DICIEMBRE": "Dic"}

# Semestres para el selector de la grilla: reduce el scroll horizontal a 6
# columnas de mes a la vez. El guardado sigue derritiendo los 12 meses
# (repositorio.py deriva los meses de las columnas del DataFrame, que
# conserva los 12 aunque solo se muestren 6).
SEMESTRES = {
    "I semestre (Ene-Jun)": MESES[:6],
    "II semestre (Jul-Dic)": MESES[6:],
}

# Ejercicio presupuestal: va en DATOS_ENTRADA.PRESUPUESTO en cada fila que
# escribe la app, y acota el DELETE previo a la carga (las filas del Excel
# 2026 tienen PRESUPUESTO NULL y no se tocan). Los sp_*_2027 deben leer solo
# las filas de este PRESUPUESTO.
PRESUPUESTO = "PPTO2027"

# Carga académica: la registra la Dirección de Gestión Académica (DGA), no los
# departamentos. Mismo formato que la hoja "Carga academica.xlsx": por semestre
# y centro de costo, horas de titulares, jefes de práctica y asistentes. En
# DATOS_ENTRADA va una fila por concepto con las horas en IMPORTE y el semestre
# en MES; sp_Valorizar_CargaAcademica_2027 lee esos textos exactos (incluido
# "ASITENTES", tal como está en el sp y en la hoja).
CARGA_ACADEMICA = {
    "hoja": "Carga Academica",
    "origen": "DGA",
    "semestres": ["2027-1", "2027-2"],
    "conceptos": {
        "# HORAS TITULARES": "# Horas titulares",
        "# HORAS JEFES DE PRÁCTICA": "# Horas jefes de práctica",
        "# HORAS ASITENTES": "# Horas asistentes",
    },
    "sps": [("sp_Valorizar_CargaAcademica_2027", False)],
}

# Flujo de valorización. Los departamentos guardan borradores las veces que
# quieran y valorizan cuando terminan. Estos tres tienen docentes que dictan
# en centros de costo de otros departamentos: deben valorizar y CERRAR antes
# de que la DGA pueda valorizar la carga académica.
DEPTOS_PRIMERO = ["DHUM", "DMAT", "DCN"]

# Todas las columnas posibles de DATOS_ENTRADA (unión de las 7 macros).
COLS_DESTINO = ["HOJA_ORIGEN", "ORIGEN", "DNI", "NOMBRE", "CENTRO_COSTO",
                "CONCEPTO", "CONCEPTO_2", "TIPO", "MES", "HORAS", "IMPORTE", "TARIFA",
                "PRESUPUESTO", "TIPO_BLOQUE"]

# Plan de trabajo TC: las horas se planifican en horas cronológicas.
# El dictado se programa en horas académicas (45 min), así que el usuario
# teclea las académicas y las cronológicas se calculan (× 45/60). Las
# académicas no cuentan para el total, que debe ser exactamente las horas del
# docente en HORAS_DOCENTES.HORAS (HORAS_META); HORAS_PLAN_TC si no las tiene.
CONCEPTO_ACADEMICAS = "Horas Dictado Pregrado (académicas)"
CONCEPTO_CRONOLOGICAS = "Horas Dictado Pregrado (cronológicas)"
FACTOR_CRONOLOGICAS = 45 / 60
HORAS_PLAN_TC = 40
TOLERANCIA_HORAS = 0.01


def es_concepto(valor, concepto: str) -> bool:
    return str(valor).strip().lower() == concepto.lower()


def meta_horas(valor) -> float:
    """Horas que debe sumar el docente; HORAS_PLAN_TC si no hay dato."""
    try:
        v = float(valor)
    except (TypeError, ValueError):
        return float(HORAS_PLAN_TC)
    return v if v > 0 else float(HORAS_PLAN_TC)


def a_hhmm(horas: float) -> str:
    """3.5 -> '03:30'. La ficha muestra y recibe las horas en este formato;
    en la base se guardan en decimal."""
    minutos = int(round(float(horas) * 60))
    return f"{minutos // 60:02d}:{minutos % 60:02d}"


def de_hhmm(texto) -> float | None:
    """'03:30' -> 3.5; '3' -> 3.0; vacío -> 0.0. None si no es válido
    (minutos fuera de 0-59, negativos o texto)."""
    t = str(texto or "").strip()
    if not t:
        return 0.0
    partes = t.split(":")
    if len(partes) > 2 or not all(p.isdigit() for p in partes):
        return None
    horas = int(partes[0])
    minutos = int(partes[1]) if len(partes) == 2 else 0
    if minutos > 59:
        return None
    return horas + minutos / 60


PLANILLAS = {
    "1. Plan TC-I": {
        "etiqueta": "Plan de trabajo TC · I semestre",
        "metrica": "HORAS",
        "dimensiones": ["DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "MES"],
        "tarifa": "server",
        "usa_roster": True,
        "mes_carga": "MARZO",
        "sps": [("sp_ValorizarPlanilla_Total_2027", True),
                ("sp_Valorizar_CargaAcademica_2027", False)],
        "ayuda": "Registra las horas de cada docente por centro de costo en formato "
                 "hh:mm (por ejemplo 03:30). Deben sumar las horas cronológicas "
                 "del docente (40 h, o las que tenga asignadas). Las horas "
                 "académicas de dictado se convierten solas a cronológicas "
                 "(× 45/60). El importe se calcula al valorizar.",
    },
    "Plan TC-II": {
        "etiqueta": "Plan de trabajo TC · II semestre",
        "metrica": "HORAS",
        "dimensiones": ["DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "MES"],
        "tarifa": "server",
        "usa_roster": True,
        "mes_carga": "AGOSTO",
        "sps": [("sp_ValorizarPlanilla_Total_2027", True),
                ("sp_Valorizar_CargaAcademica_2027", False)],
        "ayuda": "Registra las horas de cada docente por centro de costo en formato "
                 "hh:mm (por ejemplo 03:30). Deben sumar las horas cronológicas "
                 "del docente (40 h, o las que tenga asignadas). Las horas "
                 "académicas de dictado se convierten solas a cronológicas "
                 "(× 45/60). El importe se calcula al valorizar.",
    },
    "Horas Adicionales": {
        "etiqueta": "Horas adicionales",
        "metrica": "HORAS",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "TIPO", "MES"],
        "tarifa": "catalogo",
        "catalogo_key": "TIPO",
        "tarifa_editable": True,
        # Lista de Conceptos-horas-adicionales.xlsx (el .xlsx no se sube al repo)
        "precarga": "data/conceptos_horas_adicionales.csv",
        "columnas_info": ["FOCO"],
        "info_destino": {"FOCO": "TIPO_BLOQUE"},
        "usa_roster": False,
        "sps": [("sp_Valorizar_HorasAdicionales_2027", True)],
        "ayuda": "Los conceptos ya vienen cargados: completa el detalle, el centro "
                 "de costo, el tipo y las horas. La tarifa se llena con la de 2027 "
                 "según el tipo y puedes cambiarla. Las filas sin horas no se guardan.",
    },
    "Postgrado": {
        "etiqueta": "Postgrado",
        "metrica": "IMPORTE",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "TIPO", "MES"],
        "tarifa": None,
        # sp_Valorizar_Postgrado solo valoriza estos dos tipos
        "opciones": {"TIPO": ["Tiempo Parcial", "Tiempo Completo"]},
        "usa_roster": False,
        "sps": [("sp_Valorizar_Postgrado_2027", True)],
        "ayuda": "Ingresa el importe presupuestado por programa y mes.",
    },
    "Investigacion": {
        "etiqueta": "Investigación",
        "metrica": "IMPORTE",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "MES"],
        "tarifa": None,
        "opciones": {"CONCEPTO": [
            "HORAS INVESTIGACION - ADMINISTRATIVO TIEMPO PARCIAL",
            "HORAS INVESTIGACION - ADMINISTRATIVO TIEMPO COMPLETO",
            "HORAS INVESTIGACION - DOCENTE TIEMPO PARCIAL",
            "HORAS INVESTIGACION - DOCENTE TIEMPO COMPLETO",
        ]},
        "usa_roster": False,
        "sps": [("sp_Valorizar_Investigacion_2027", True)],
        "ayuda": "Ingresa el importe presupuestado por línea y mes.",
    },
    "Ayudantias": {
        "etiqueta": "Ayudantías",
        "metrica": "HORAS",
        "columna_destino": "IMPORTE",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "TIPO", "MES"],
        "tarifa": "catalogo",
        "catalogo_key": "TIPO",
        "usa_roster": False,
        "sps": [("sp_Valorizar_Ayudantias_2027", True)],
        "ayuda": "Registra las horas de ayudantía. El costo por hora se aplica "
                 "desde el catálogo.",
    },
}


def cfg_de(hoja: str) -> dict:
    """Devuelve la config de una planilla con su clave incluida."""
    c = dict(PLANILLAS[hoja])
    c["_hoja"] = hoja
    return c


def dims_fila(cfg: dict) -> list[str]:
    """Dimensiones que van en las filas de la matriz: todas menos el MES,
    que pasa a ser el eje de columnas."""
    return [d for d in cfg["dimensiones"] if d != "MES"]
