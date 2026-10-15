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

# Todas las columnas posibles de DATOS_ENTRADA (unión de las 7 macros).
COLS_DESTINO = ["HOJA_ORIGEN", "ORIGEN", "DNI", "NOMBRE", "CENTRO_COSTO",
                "CONCEPTO", "CONCEPTO_2", "TIPO", "MES", "HORAS", "IMPORTE", "TARIFA",
                "PRESUPUESTO"]

# Plan de trabajo TC: las horas se planifican en horas cronológicas.
# El dictado se programa en horas académicas (45 min), así que el usuario
# teclea las académicas y las cronológicas se calculan (× 45/60). Las
# académicas no cuentan para el total, que debe ser exactamente HORAS_PLAN_TC.
CONCEPTO_ACADEMICAS = "Horas Dictado Pregrado (académicas)"
CONCEPTO_CRONOLOGICAS = "Horas Dictado Pregrado (cronológicas)"
FACTOR_CRONOLOGICAS = 45 / 60
HORAS_PLAN_TC = 40
TOLERANCIA_HORAS = 0.01


def es_concepto(valor, concepto: str) -> bool:
    return str(valor).strip().lower() == concepto.lower()


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
        "ayuda": "Registra las horas de cada docente por centro de costo: "
                 "deben sumar 40 horas cronológicas. Las horas académicas de "
                 "dictado se convierten solas a cronológicas (× 45/60). "
                 "El importe se calcula al valorizar.",
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
        "ayuda": "Registra las horas de cada docente por centro de costo: "
                 "deben sumar 40 horas cronológicas. Las horas académicas de "
                 "dictado se convierten solas a cronológicas (× 45/60). "
                 "El importe se calcula al valorizar.",
    },
    "Horas Adicionales": {
        "etiqueta": "Horas adicionales",
        "metrica": "HORAS",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "TIPO", "MES"],
        "tarifa": "catalogo",
        "catalogo_key": "TIPO",
        "usa_roster": False,
        "sps": [("sp_Valorizar_HorasAdicionales_2027", True)],
        "ayuda": "Elige el tipo (Asistente, Jefe de práctica, Titular) y la "
                 "tarifa se aplica sola desde el catálogo.",
    },
    "Postgrado": {
        "etiqueta": "Postgrado",
        "metrica": "IMPORTE",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "TIPO", "MES"],
        "tarifa": None,
        "usa_roster": False,
        "sps": [("sp_Valorizar_Postgrado_2027", True)],
        "ayuda": "Ingresa el importe presupuestado por programa y mes.",
    },
    "Investigacion": {
        "etiqueta": "Investigación",
        "metrica": "IMPORTE",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "MES"],
        "tarifa": None,
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
