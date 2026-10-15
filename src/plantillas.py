"""
Plantillas Excel de Desarrollo Humano y lectura de los archivos que suben.

Docentes y salarios se actualizan SOLO con estos Excel: cada archivo es la
lista completa (quien no está en el archivo se da de baja). La app muestra
las diferencias antes de guardar.

La plantilla de salarios se descarga sin montos (solo DNI, nombre, categoría
y departamento): así el archivo que circula no lleva sueldos hasta que
Desarrollo Humano los completa.
"""

import io
import re
import unicodedata

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .repositorio import COLS_REMUNERACION

# DNI (8 dígitos), carné de extranjería (9-12) o plaza nueva sin docente aún (NUEVO1, NUEVO2...)
DOC_IDENTIDAD = re.compile(r"\d{8}|[0-9A-Za-z]{9,12}|NUEVO\d+", re.IGNORECASE)

# Columna interna -> encabezado en el Excel
CABECERAS_DOCENTES = {"DPTO": "DEPARTAMENTO", "DNI": "DNI", "NOMBRE": "DOCENTE",
                      "HORAS": "HORAS"}
ETIQUETAS_SALARIO = {
    "Basico": "BÁSICO", "Asignacion_Familiar": "ASIGNACIÓN FAMILIAR",
    "Bonificacion_Docente_TC": "BONIF. DOCENTE TC",
    "Bonificacion_Dedicacion_Exclusiva": "BONIF. DEDICACIÓN EXCLUSIVA",
    "Bono_por_Decano": "BONO POR DECANO",
    "Bono_por_Director_de_Escuela": "BONO POR DIRECTOR DE ESCUELA",
    "Bono_por_Departamento": "BONO POR DEPARTAMENTO", "Bono_al_Cargo": "BONO AL CARGO",
    "Bonificacion_Variable_por_Profesor_Extranjero": "BONIF. VARIABLE PROF. EXTRANJERO",
    "Bonificacion_Ordinaria_por_Acuerdo_Rem": "BONIF. ORDINARIA POR ACUERDO REM.",
    "Bonificacion_por_Representacion": "BONIF. POR REPRESENTACIÓN",
    "Grado_de_Maestria": "GRADO DE MAESTRÍA", "Grado_de_Doctorado": "GRADO DE DOCTORADO",
    "Asignacion_por_Vivienda": "ASIGNACIÓN POR VIVIENDA",
    "Asignacion_por_Hijo_Menor": "ASIGNACIÓN POR HIJO MENOR",
    "Vale_por_Alimentos": "VALE POR ALIMENTOS",
}
CABECERAS_SALARIOS = {"DNI": "DNI", "Nombre": "DOCENTE", "Categoria": "CATEGORÍA",
                      "DPTO": "DEPARTAMENTO", **ETIQUETAS_SALARIO}

_AZUL = PatternFill("solid", fgColor="17233B")
_GRIS = PatternFill("solid", fgColor="EEF1F6")


def _norm(texto) -> str:
    """Encabezado comparable: sin tildes, mayúsculas, solo letras y números."""
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode()
    return re.sub(r"[^A-Z0-9]", "", t.upper())


# ------------------------------------------------------------ plantillas

def _hoja_datos(wb, titulo, cabeceras, filas, anchos):
    ws = wb.active
    ws.title = titulo
    ws.append(list(cabeceras.values()))
    for celda in ws[1]:
        celda.font = Font(bold=True, color="FFFFFF")
        celda.fill = _AZUL
        celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    ws.row_dimensions[1].height = 32
    for fila in filas:
        ws.append(fila)
    for i, ancho in enumerate(anchos, start=1):
        ws.column_dimensions[get_column_letter(i)].width = ancho
    ws.freeze_panes = "A2"
    # DNI como texto: Excel no debe quitar ceros a la izquierda
    col_dni = list(cabeceras).index("DNI") + 1
    for (celda,) in ws.iter_rows(min_row=2, max_row=2000, min_col=col_dni, max_col=col_dni):
        celda.number_format = "@"
    return ws


def _hoja_instrucciones(wb, lineas):
    ws = wb.create_sheet("Instrucciones")
    ws.column_dimensions["A"].width = 110
    for i, linea in enumerate(lineas, start=1):
        c = ws.cell(row=i, column=1, value=linea)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if i == 1:
            c.font = Font(bold=True, size=13)


def _a_bytes(wb) -> bytes:
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def plantilla_docentes(docentes: pd.DataFrame, codigos: list[str]) -> bytes:
    """Lista actual de docentes TC (no es confidencial), lista para editar."""
    wb = Workbook()
    filas = [[r.DPTO, str(r.DNI), r.NOMBRE, float(r.HORAS)]
             for r in docentes.itertuples(index=False)]
    ws = _hoja_datos(wb, "Docentes", CABECERAS_DOCENTES, filas, [16, 14, 46, 10])
    listas = wb.create_sheet("Listas")
    for i, c in enumerate(codigos, start=1):
        listas.cell(row=i, column=1, value=c)
    listas.sheet_state = "hidden"
    dv = DataValidation(type="list", formula1=f"=Listas!$A$1:$A${len(codigos)}",
                        allow_blank=False, showErrorMessage=True,
                        errorTitle="Departamento", error="Elige un departamento de la lista.")
    dv.add("A2:A2000")
    horas = DataValidation(type="decimal", operator="between", formula1="1", formula2="40",
                           showErrorMessage=True, errorTitle="Horas",
                           error="Las horas deben estar entre 1 y 40.")
    horas.add("D2:D2000")
    ws.add_data_validation(dv)
    ws.add_data_validation(horas)
    _hoja_instrucciones(wb, [
        "Docentes a tiempo completo y sus horas — presupuesto 2027",
        "1. Este archivo es la LISTA COMPLETA: quien no esté aquí se dará de baja al subirlo.",
        "2. DEPARTAMENTO: código de la lista (DAIC, DHUM, ...). DNI: 8 dígitos, o 9 a 12 "
        "caracteres si es carné de extranjería; para una plaza nueva sin docente asignado "
        "usa NUEVO1, NUEVO2, ... HORAS: horas cronológicas del plan de trabajo (40, o "
        "menos si tiene carga parcial).",
        "3. No cambies los nombres de las columnas ni el nombre de la hoja «Docentes».",
        "4. Sube el archivo en la app: Desarrollo Humano › Docentes y horas. Antes de guardar "
        "verás qué docentes se agregan, se quitan o cambian.",
    ])
    return _a_bytes(wb)


def plantilla_salarios(identidad: pd.DataFrame) -> bytes:
    """DNI, nombre, categoría y departamento de quienes ya tienen salario 2027,
    con los montos VACÍOS para completar."""
    wb = Workbook()
    filas = [[str(r.DNI), r.Nombre, r.Categoria, r.DPTO] + [None] * len(COLS_REMUNERACION)
             for r in identidad.itertuples(index=False)]
    ws = _hoja_datos(wb, "Salarios", CABECERAS_SALARIOS, filas,
                     [14, 40, 18, 16] + [16] * len(COLS_REMUNERACION))
    ultima = get_column_letter(4 + len(COLS_REMUNERACION))
    montos = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0",
                            allow_blank=True, showErrorMessage=True, errorTitle="Monto",
                            error="Ingresa un monto mayor o igual a 0 (sin texto).")
    montos.add(f"E2:{ultima}2000")
    ws.add_data_validation(montos)
    for fila in ws.iter_rows(min_row=2, max_row=2000, min_col=5, max_col=4 + len(COLS_REMUNERACION)):
        for celda in fila:
            celda.number_format = "#,##0.00"
    for celda in ws[1][4:]:
        celda.fill = PatternFill("solid", fgColor="7A1F2B")
    _hoja_instrucciones(wb, [
        "Salarios 2027 — CONFIDENCIAL",
        "1. Completa los montos MENSUALES en soles de cada docente. Un componente que no "
        "aplica va en 0 o vacío. Cada docente debe tener un total mayor que 0.",
        "2. Este archivo es la LISTA COMPLETA: quien no esté aquí perderá su salario 2027 "
        "al subirlo. Para agregar a alguien, añade una fila con su DNI.",
        "3. No cambies los nombres de las columnas ni el nombre de la hoja «Salarios».",
        "4. Sube el archivo en la app: Desarrollo Humano › Salarios. Antes de guardar verás "
        "las altas, bajas y qué campos cambian.",
        "5. Contiene información confidencial: no lo envíes por correo ni lo dejes en "
        "carpetas compartidas, y bórralo después de subirlo.",
    ])
    return _a_bytes(wb)


# ------------------------------------------------------------ lectura

def _leer(archivo, hoja: str, cabeceras: dict) -> tuple[pd.DataFrame | None, list[str]]:
    try:
        libro = pd.read_excel(archivo, sheet_name=None, dtype=object)
    except Exception as ex:
        return None, [f"No se pudo leer el archivo como Excel ({type(ex).__name__})."]
    df = libro.get(hoja)
    if df is None:
        df = next(iter(libro.values()))
    esperadas = {_norm(v): k for k, v in cabeceras.items()}
    df = df.rename(columns={c: esperadas.get(_norm(c), c) for c in df.columns})
    faltan = [cabeceras[k] for k in cabeceras if k not in df.columns]
    if faltan:
        return None, ["Faltan columnas en el archivo: " + ", ".join(faltan)
                      + ". Usa la plantilla sin cambiar los encabezados."]
    df = df[list(cabeceras)].dropna(how="all").reset_index(drop=True)
    df.index = df.index + 2   # número de fila en Excel (la 1 es el encabezado)
    return df, []


def _dni(valor) -> str:
    """Excel convierte el DNI en número y quita ceros a la izquierda."""
    if valor is None or (isinstance(valor, float) and pd.isna(valor)):
        return ""
    if isinstance(valor, (int, float)):
        t = str(int(valor))
        return t.zfill(8) if 6 <= len(t) < 8 else t
    t = str(valor).strip()
    if t.upper().startswith("NUEVO"):
        return t.upper()
    # Solo se completan los ceros que Excel suele quitar (DNI de 6 o 7 cifras)
    return t.zfill(8) if t.isdigit() and 6 <= len(t) < 8 else t


def unificar_dni(df: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """DNI normalizado (8 dígitos con sus ceros) y sin duplicados. Remuneraciones
    tiene docentes repetidos con y sin el cero inicial; se queda la versión de 8
    dígitos, que es la que usan HORAS_DOCENTES y los planes TC."""
    df = df.copy()
    largo = df["DNI"].astype(str).str.strip().str.len()
    df["DNI"] = df["DNI"].map(_dni)
    df = df.assign(_l=largo).sort_values("_l", ascending=False)
    antes = len(df)
    df = df.drop_duplicates("DNI").drop(columns="_l").sort_index()
    return df, antes - len(df)


def _filas(indices) -> str:
    indices = sorted(indices)
    return ", ".join(map(str, indices[:10])) + (f" y {len(indices) - 10} más" if len(indices) > 10 else "")


def leer_docentes(archivo, codigos: set) -> tuple[pd.DataFrame | None, list[str]]:
    df, errores = _leer(archivo, "Docentes", CABECERAS_DOCENTES)
    if errores:
        return None, errores
    df["DNI"] = df["DNI"].map(_dni)
    df["DPTO"] = df["DPTO"].map(lambda v: str(v).strip().upper() if pd.notna(v) else "")
    df["NOMBRE"] = df["NOMBRE"].map(lambda v: " ".join(str(v).split()) if pd.notna(v) else "")
    df["HORAS"] = pd.to_numeric(df["HORAS"], errors="coerce")
    vacias = df.index[(df["DNI"] == "") | (df["NOMBRE"] == "") | (df["DPTO"] == "")]
    if len(vacias):
        errores.append(f"Filas incompletas (DNI, docente o departamento): {_filas(vacias)}.")
    malos = df.index[(df["DNI"] != "") & ~df["DNI"].map(lambda d: bool(DOC_IDENTIDAD.fullmatch(d)))]
    if len(malos):
        errores.append(f"DNI inválido en las filas {_filas(malos)}.")
    rep = df.index[df["DNI"].duplicated(keep=False) & (df["DNI"] != "")]
    if len(rep):
        errores.append(f"DNI repetido en las filas {_filas(rep)}.")
    fuera = df.index[(df["DPTO"] != "") & ~df["DPTO"].isin(codigos)]
    if len(fuera):
        errores.append(f"Departamento que no existe en las filas {_filas(fuera)}.")
    horas = df.index[df["HORAS"].isna() | (df["HORAS"] < 1) | (df["HORAS"] > 40)]
    if len(horas):
        errores.append(f"Horas vacías o fuera de 1 a 40 en las filas {_filas(horas)}.")
    return (None if errores else df.reset_index(drop=True)), errores


def leer_salarios(archivo) -> tuple[pd.DataFrame | None, list[str]]:
    df, errores = _leer(archivo, "Salarios", CABECERAS_SALARIOS)
    if errores:
        return None, errores
    df["DNI"] = df["DNI"].map(_dni)
    for c in ("Nombre", "Categoria", "DPTO"):
        df[c] = df[c].map(lambda v: " ".join(str(v).split()) if pd.notna(v) else None)
    texto = []
    for c in COLS_REMUNERACION:
        num = pd.to_numeric(df[c], errors="coerce")
        texto += list(df.index[df[c].notna() & num.isna()])
        df[c] = num.fillna(0.0).round(2)
    if texto:
        errores.append(f"Montos con texto (deben ser números) en las filas {_filas(set(texto))}.")
    neg = df.index[(df[COLS_REMUNERACION] < 0).any(axis=1)]
    if len(neg):
        errores.append(f"Montos negativos en las filas {_filas(neg)}.")
    sin_dni = df.index[df["DNI"] == ""]
    if len(sin_dni):
        errores.append(f"Filas sin DNI: {_filas(sin_dni)}.")
    malos = df.index[(df["DNI"] != "") & ~df["DNI"].map(lambda d: bool(DOC_IDENTIDAD.fullmatch(d)))]
    if len(malos):
        errores.append(f"DNI inválido en las filas {_filas(malos)}.")
    rep = df.index[df["DNI"].duplicated(keep=False) & (df["DNI"] != "")]
    if len(rep):
        errores.append(f"DNI repetido en las filas {_filas(rep)}.")
    sin_nombre = df.index[df["Nombre"].isna()]
    if len(sin_nombre):
        errores.append(f"Filas sin nombre del docente: {_filas(sin_nombre)}.")
    cero = df.index[df[COLS_REMUNERACION].sum(axis=1) <= 0]
    if len(cero):
        errores.append(f"Docentes con salario total 0 en las filas {_filas(cero)} "
                       "(¿se subió la plantilla sin completar los montos?).")
    return (None if errores else df.reset_index(drop=True)), errores


# ------------------------------------------------------------ diferencias

def _texto(v):
    """Texto comparable: sin espacios de más; vacío = None."""
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    return " ".join(str(v).split()) or None


def diferencias(actual: pd.DataFrame, nuevo: pd.DataFrame, campos: list[str],
                nombre: str) -> pd.DataFrame:
    """Una fila por DNI: Alta, Baja, Cambio (con los campos que cambian) o Sin cambios."""
    a = actual.set_index("DNI")
    n = nuevo.set_index("DNI")
    filas = []
    for dni in sorted(set(a.index) | set(n.index)):
        if dni not in a.index:
            filas.append((dni, n.at[dni, nombre], "Alta", ""))
        elif dni not in n.index:
            filas.append((dni, a.at[dni, nombre], "Baja", ""))
        else:
            cambian = []
            for c in campos:
                va, vn = a.at[dni, c], n.at[dni, c]
                if isinstance(vn, float) or isinstance(va, float):
                    va = 0.0 if va is None or pd.isna(va) else float(va)
                    vn = 0.0 if vn is None or pd.isna(vn) else float(vn)
                    if abs(va - vn) > 0.005:
                        cambian.append(c)
                elif _texto(va) != _texto(vn):
                    cambian.append(c)
            filas.append((dni, n.at[dni, nombre], "Cambio" if cambian else "Sin cambios",
                          ", ".join(cambian)))
    return pd.DataFrame(filas, columns=["DNI", "Docente", "Movimiento", "Campos que cambian"])
