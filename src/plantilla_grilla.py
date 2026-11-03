"""
Plantilla Excel para cualquier grilla de ingreso (Horas adicionales,
Postgrado, Investigación, Ayudantías, Puestos nuevos, Carga académica):
descargar lo que hay en pantalla, llenarlo fuera de la app y volver a
cargarlo.

La grilla se describe con una lista de columnas (Columna): título, tipo
(texto, número o lista cerrada) y, para las listas, sus opciones. El Excel
trae:
  - hoja Datos: una fila por línea de la grilla, con listas desplegables en
    las columnas de lista y, junto al centro de costo, su descripción
    (fórmula: se ve al elegir el código);
  - hoja Centros de costo: los códigos que el usuario puede usar, con su
    descripción (son centros nuevos 2027 y no todos los conocen);
  - hoja Listas: las opciones de las demás listas.

Al cargarlo se valida todo y, si hay un error, no se carga nada. Cargar
reemplaza las líneas de la grilla por las del archivo; no guarda: se revisa
y se pulsa Guardar, con las validaciones de siempre.
"""

import io
from dataclasses import dataclass, field

import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .plantillas import _norm

HOJA_DATOS = "Datos"
HOJA_CECOS = "Centros de costo"
HOJA_LISTAS = "Listas"
FILA_CABECERA = 4
FILAS_VACIAS = 40          # filas extra con listas desplegables para agregar líneas
_AZUL, _EDITABLE, _GRIS = "17233B", "FFF7E0", "F2F4F7"
CENTRO_COSTO = "CENTRO_COSTO"
DESC_CECO = "Descripción del centro de costo"


@dataclass
class Columna:
    col: str                       # nombre en la grilla (DataFrame)
    titulo: str                    # encabezado en el Excel
    tipo: str = "texto"            # texto | numero | lista
    opciones: list = field(default_factory=list)
    ancho: int = 16
    obligatoria: bool = False      # en filas con algún número


def plantilla(columnas: list[Columna], df: pd.DataFrame, desc_ceco: dict,
              titulo: str, instrucciones: str) -> bytes:
    """Excel con las líneas actuales de la grilla (df) y listas desplegables."""
    wb = Workbook()
    ws = wb.active
    ws.title = HOJA_DATOS
    ws_cc = wb.create_sheet(HOJA_CECOS)
    ws_li = wb.create_sheet(HOJA_LISTAS)

    # Centros de costo con descripción
    for i, (t, a) in enumerate([("Código", 18), ("Descripción", 70)], start=1):
        _cabecera(ws_cc.cell(row=1, column=i, value=t))
        ws_cc.column_dimensions[get_column_letter(i)].width = a
    for r, (codigo, desc) in enumerate(sorted(desc_ceco.items()), start=2):
        ws_cc.cell(row=r, column=1, value=str(codigo)).number_format = "@"
        ws_cc.cell(row=r, column=2, value=desc)
    ws_cc.freeze_panes = "A2"
    n_cc = len(desc_ceco) + 1

    # Encabezados de la hoja Datos (la descripción va después del centro)
    visibles = []
    for c in columnas:
        visibles.append(c)
        if c.col == CENTRO_COSTO:
            visibles.append(Columna(DESC_CECO, DESC_CECO, "info", ancho=48))
    ultima_col = get_column_letter(len(visibles))
    ws["A1"] = titulo
    ws["A1"].font = Font(bold=True, size=13)
    ws["A2"] = instrucciones
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(f"A2:{ultima_col}2")
    ws.row_dimensions[2].height = 46
    for i, c in enumerate(visibles, start=1):
        _cabecera(ws.cell(row=FILA_CABECERA, column=i, value=c.titulo))
        ws.column_dimensions[get_column_letter(i)].width = c.ancho
    ws.row_dimensions[FILA_CABECERA].height = 32
    ws.freeze_panes = ws.cell(row=FILA_CABECERA + 1, column=1)

    filas = df.reset_index(drop=True)
    ultima = FILA_CABECERA + len(filas) + FILAS_VACIAS
    for i, c in enumerate(visibles, start=1):
        letra = get_column_letter(i)
        for r in range(FILA_CABECERA + 1, ultima + 1):
            celda = ws.cell(row=r, column=i)
            k = r - FILA_CABECERA - 1
            if c.tipo == "info":
                cc = get_column_letter(i - 1)
                celda.value = (f'=IFERROR(VLOOKUP({cc}{r},\'{HOJA_CECOS}\'!$A$2:$B${n_cc},'
                               f'2,FALSE),"")')
                celda.fill = PatternFill("solid", fgColor=_GRIS)
                continue
            if k < len(filas) and c.col in filas:
                v = filas.at[k, c.col]
                if v is not None and not (isinstance(v, float) and pd.isna(v)) and v != "":
                    celda.value = float(v) if c.tipo == "numero" else str(v)
            if c.tipo == "numero":
                celda.number_format = "#,##0.##"
            else:
                celda.number_format = "@"
            celda.fill = PatternFill("solid", fgColor=_EDITABLE)
        rango = f"{letra}{FILA_CABECERA + 1}:{letra}{ultima}"
        if c.col == CENTRO_COSTO:
            dv = DataValidation(type="list", formula1=f"='{HOJA_CECOS}'!$A$2:$A${n_cc}",
                                allow_blank=True, showErrorMessage=True,
                                errorTitle="Centro de costo",
                                error="Elige un código de la hoja «Centros de costo».")
        elif c.tipo == "lista" and c.opciones:
            j = ws_li.max_column + 1 if ws_li.max_row > 1 or ws_li["A1"].value else 1
            _cabecera(ws_li.cell(row=1, column=j, value=c.titulo))
            ws_li.column_dimensions[get_column_letter(j)].width = max(
                18, min(60, max(len(str(o)) for o in c.opciones) + 2))
            for r, o in enumerate(c.opciones, start=2):
                ws_li.cell(row=r, column=j, value=str(o)).number_format = "@"
            lj = get_column_letter(j)
            dv = DataValidation(type="list",
                                formula1=f"='{HOJA_LISTAS}'!${lj}$2:${lj}${len(c.opciones) + 1}",
                                allow_blank=True, showErrorMessage=True,
                                errorTitle=c.titulo, error="Elige un valor de la lista.")
        elif c.tipo == "numero":
            dv = DataValidation(type="decimal", operator="greaterThanOrEqual", formula1="0",
                                allow_blank=True, showErrorMessage=True,
                                errorTitle=c.titulo, error="Escribe un número mayor o igual a 0.")
        else:
            continue
        dv.add(rango)
        ws.add_data_validation(dv)
    if ws_li.max_row == 1 and ws_li["A1"].value is None:
        wb.remove(ws_li)
    salida = io.BytesIO()
    wb.save(salida)
    return salida.getvalue()


def _cabecera(celda):
    celda.font = Font(bold=True, color="FFFFFF")
    celda.fill = PatternFill("solid", fgColor=_AZUL)
    celda.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)


def leer(archivo, columnas: list[Columna], cecos_validos: set) -> tuple[pd.DataFrame | None,
                                                                       list[str], str]:
    """(grilla, errores, resumen). Con errores, la grilla es None: no se carga
    nada. Las filas sin ningún número se descartan."""
    try:
        wb = load_workbook(archivo, data_only=True, read_only=True)
    except Exception as ex:
        return None, [f"No se pudo abrir el archivo como Excel ({ex})."], ""
    if HOJA_DATOS not in wb.sheetnames:
        return None, [f"El archivo no tiene la hoja «{HOJA_DATOS}». Descarga la plantilla "
                      "desde esta pantalla y llénala."], ""
    filas = list(wb[HOJA_DATOS].iter_rows(values_only=True))
    if len(filas) < FILA_CABECERA:
        return None, ["La hoja Datos está vacía."], ""
    cab = {_norm(v): i for i, v in enumerate(filas[FILA_CABECERA - 1]) if v is not None}
    faltan = [c.titulo for c in columnas if _norm(c.titulo) not in cab]
    if faltan:
        return None, ["Faltan columnas en la hoja Datos: " + ", ".join(faltan)
                      + ". Usa la plantilla descargada desde esta pantalla sin cambiar "
                        "los encabezados."], ""

    errores, registros = [], []
    numeros = [c for c in columnas if c.tipo == "numero"]
    for n_fila, fila in enumerate(filas[FILA_CABECERA:], start=FILA_CABECERA + 1):
        valor = lambda c: fila[cab[_norm(c.titulo)]] if cab[_norm(c.titulo)] < len(fila) else None
        reg, fila_err = {}, []
        for c in numeros:
            v = valor(c)
            if v is None or (isinstance(v, str) and not v.strip()):
                reg[c.col] = float("nan")
                continue
            try:
                x = float(str(v).replace(",", "")) if isinstance(v, str) else float(v)
            except (TypeError, ValueError):
                fila_err.append(f"{c.titulo}: «{v}» no es un número")
                continue
            if x < 0:
                fila_err.append(f"{c.titulo}: no puede ser negativo")
            reg[c.col] = x if x != 0 else float("nan")
        # Línea sin números: se descarta, igual que al guardar la grilla
        if not any(pd.notna(reg.get(c.col)) for c in numeros) and not fila_err:
            continue
        textos = [c for c in columnas if c.tipo != "numero"]
        for c in textos:
            texto = str(valor(c) if valor(c) is not None else "").strip()
            if c.col == CENTRO_COSTO:
                texto = texto.split("·")[0].strip()
                if texto and texto not in cecos_validos:
                    fila_err.append(f"centro de costo «{texto}» no está en la hoja "
                                    "«Centros de costo»")
            elif c.tipo == "lista" and texto:
                canon = {_norm(o): o for o in c.opciones}
                if _norm(texto) not in canon:
                    fila_err.append(f"{c.titulo}: «{texto}» no está en la lista")
                else:
                    texto = canon[_norm(texto)]
            if not texto and c.obligatoria:
                fila_err.append(f"falta {c.titulo}")
            reg[c.col] = texto or None
        if fila_err:
            errores.append(f"Fila {n_fila}: " + "; ".join(fila_err) + ".")
        else:
            registros.append(reg)
    if errores:
        return None, errores, ""
    df = pd.DataFrame(registros, columns=[c.col for c in columnas])
    for c in numeros:
        df[c.col] = pd.to_numeric(df[c.col], errors="coerce")
    total = float(df[[c.col for c in numeros]].sum().sum()) if numeros else 0.0
    return df, [], f"{len(df)} línea(s) con datos (suma de las celdas: {total:,.2f})."
