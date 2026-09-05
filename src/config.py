"""
Configuración declarativa de las planillas — el "7 macros → 1 motor".

Cada planilla describe SU forma aquí. El motor no conoce coordenadas ni
tiene una rama por hoja: lee esta config y se comporta en consecuencia.
Agregar o cambiar una planilla = editar este diccionario.

Campos:
  etiqueta     Nombre visible para el usuario (voz de la interfaz, no la técnica).
  metrica      "HORAS" o "IMPORTE": qué teclea el usuario y en qué columna
               de DATOS_ENTRADA cae. Resuelve que Ayudantías hoy meta horas
               dentro de IMPORTE.
  dimensiones  Columnas que identifican cada registro.
  tarifa       "server"   → la aplica el procedimiento; el usuario no la ve.
               "catalogo" → se resuelve por TIPO desde el catálogo (server-side);
                            el usuario elige el TIPO, nunca teclea el precio.
               None       → la planilla entrega IMPORTE ya calculado.
  catalogo_key Dimensión contra la que se busca la tarifa (p. ej. "TIPO").
  usa_roster   Si True, la grilla se pre-puebla con el padrón de docentes del
               departamento para que el usuario solo complete la métrica.
  sps          Procedimientos de valorización a ejecutar tras la carga, en orden.
               (nombre, pasa_OrigenEntrada)
  ayuda        Una línea que orienta al usuario en la interfaz.
"""

MESES = ["ENERO", "FEBRERO", "MARZO", "ABRIL", "MAYO", "JUNIO",
         "JULIO", "AGOSTO", "SEPTIEMBRE", "OCTUBRE", "NOVIEMBRE", "DICIEMBRE"]

# Todas las columnas posibles de DATOS_ENTRADA (unión de las 7 macros).
COLS_DESTINO = ["HOJA_ORIGEN", "ORIGEN", "DNI", "NOMBRE", "CENTRO_COSTO",
                "CONCEPTO", "CONCEPTO_2", "TIPO", "MES", "HORAS", "IMPORTE", "TARIFA"]

PLANILLAS = {
    "1. Plan TC-I": {
        "etiqueta": "Plan de trabajo TC · I semestre",
        "metrica": "HORAS",
        "dimensiones": ["DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "MES"],
        "tarifa": "server",
        "usa_roster": True,
        "sps": [("sp_ValorizarPlanilla_Total_2026", True),
                ("sp_Valorizar_CargaAcademica_2026", False)],
        "ayuda": "Registra las horas de cada docente por centro de costo. "
                 "El importe se calcula al valorizar.",
    },
    "Plan TC-II": {
        "etiqueta": "Plan de trabajo TC · II semestre",
        "metrica": "HORAS",
        "dimensiones": ["DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "MES"],
        "tarifa": "server",
        "usa_roster": True,
        "sps": [("sp_ValorizarPlanilla_Total_2026", True),
                ("sp_Valorizar_CargaAcademica_2026", False)],
        "ayuda": "Registra las horas de cada docente por centro de costo. "
                 "El importe se calcula al valorizar.",
    },
    "Horas Adicionales": {
        "etiqueta": "Horas adicionales",
        "metrica": "HORAS",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "TIPO", "MES"],
        "tarifa": "catalogo",
        "catalogo_key": "TIPO",
        "usa_roster": False,
        "sps": [("sp_Valorizar_HorasAdicionales_2026", True)],
        "ayuda": "Elige el tipo (Asistente, Jefe de práctica, Titular) y la "
                 "tarifa se aplica sola desde el catálogo.",
    },
    "Postgrado": {
        "etiqueta": "Postgrado",
        "metrica": "IMPORTE",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "TIPO", "MES"],
        "tarifa": None,
        "usa_roster": False,
        "sps": [("sp_Valorizar_Postgrado_2026", True)],
        "ayuda": "Ingresa el importe presupuestado por programa y mes.",
    },
    "Investigacion": {
        "etiqueta": "Investigación",
        "metrica": "IMPORTE",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "MES"],
        "tarifa": None,
        "usa_roster": False,
        "sps": [("sp_Valorizar_Investigacion_2026", True)],
        "ayuda": "Ingresa el importe presupuestado por línea y mes.",
    },
    "Ayudantias": {
        "etiqueta": "Ayudantías",
        "metrica": "HORAS",
        "dimensiones": ["CONCEPTO", "CONCEPTO_2", "CENTRO_COSTO", "TIPO", "MES"],
        "tarifa": "catalogo",
        "catalogo_key": "TIPO",
        "usa_roster": False,
        "sps": [("sp_Valorizar_Ayudantias_2026", True)],
        "ayuda": "Registra las horas de ayudantía. El costo por hora se aplica "
                 "desde el catálogo.",
    },
}


def cfg_de(hoja: str) -> dict:
    """Devuelve la config de una planilla con su clave incluida."""
    c = dict(PLANILLAS[hoja])
    c["_hoja"] = hoja
    return c
