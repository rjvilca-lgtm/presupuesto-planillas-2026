"""
Reporte de horas de los docentes TC 2027 para Desarrollo Humano.

Sale de lo que los departamentos guardaron en los planes de trabajo TC
(DATOS_ENTRADA, PRESUPUESTO 2027, hojas TC-I y TC-II). Lo principal es la
Gestión de Dirección (centro de costo '0'): esas horas no las valoriza la app,
las valoriza Desarrollo Humano, y para eso necesita cuántas horas de cada
docente son de dirección y qué proporción son de su plan (el sp reparte la
remuneración por proporción de horas).

Las horas se expresan en horas cronológicas semanales, en decimal (3.5 = 3 h
30 min). Las horas académicas de dictado son informativas: no suman al plan
(lo que suma es su equivalente cronológico), así que el detalle las marca y
los totales no las cuentan. No incluye remuneraciones.
"""

import io

import pandas as pd

from .config import CONCEPTO_ACADEMICAS, es_concepto
from .vistas import es_direccion

HOJAS_TC = {"1. Plan TC-I": "I", "Plan TC-II": "II"}
SEMESTRES = {"I": "I semestre (TC-I)", "II": "II semestre (TC-II)"}


def _base(horas: pd.DataFrame) -> pd.DataFrame:
    h = horas.copy()
    h["HORAS"] = pd.to_numeric(h["HORAS"], errors="coerce").fillna(0.0)
    h = h[h["HOJA_ORIGEN"].isin(HOJAS_TC) & (h["HORAS"] != 0)].copy()
    h["DNI"] = h["DNI"].astype(str).str.strip()
    h["CENTRO_COSTO"] = h["CENTRO_COSTO"].fillna("").astype(str).str.strip()
    h["CONCEPTO"] = h["CONCEPTO"].fillna("").astype(str).str.strip()
    h["SEM"] = h["HOJA_ORIGEN"].map(HOJAS_TC)
    # astype(bool): vacías quedan como object y h[serie] seleccionaría columnas
    h["ACAD"] = h["CONCEPTO"].map(lambda c: es_concepto(c, CONCEPTO_ACADEMICAS)).astype(bool)
    h["DIR"] = pd.Series([es_direccion(c, k) for c, k in zip(h["CENTRO_COSTO"], h["CONCEPTO"])],
                         index=h.index, dtype=bool)
    return h


def construir(horas: pd.DataFrame, padron: pd.DataFrame, deptos: list[tuple],
              cecos: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """Tablas del reporte. horas: ORIGEN, HOJA_ORIGEN, DNI, NOMBRE,
    CENTRO_COSTO, CONCEPTO, HORAS. padron: DPTO, DNI, NOMBRE, HORAS."""
    nombres = dict(deptos)
    h = _base(horas)
    cron = h.loc[~h["ACAD"]]
    clave = ["ORIGEN", "DNI"]

    def por_sem(df):
        return (df.groupby(clave + ["SEM"])["HORAS"].sum().unstack("SEM")
                .reindex(columns=list(SEMESTRES)))

    total, direc = por_sem(cron), por_sem(cron.loc[cron["DIR"]])
    res = total.join(direc, rsuffix="_DIR", how="outer").fillna(0.0).reset_index()
    res["NOMBRE"] = res.set_index(clave).index.map(h.groupby(clave)["NOMBRE"].first())

    # Docentes del padrón sin plan guardado: también van, con horas en 0
    pad = padron.copy()
    pad["DNI"] = pad["DNI"].astype(str).str.strip()
    meta = pad.drop_duplicates("DNI").set_index("DNI")
    sin_plan = meta[~meta.index.isin(res["DNI"])].reset_index()
    if not sin_plan.empty:
        res = pd.concat([res, pd.DataFrame({
            "ORIGEN": sin_plan["DPTO"], "DNI": sin_plan["DNI"], "NOMBRE": sin_plan["NOMBRE"],
            "I": 0.0, "II": 0.0, "I_DIR": 0.0, "II_DIR": 0.0})], ignore_index=True)
    res["META"] = pd.to_numeric(res["DNI"].map(meta["HORAS"]), errors="coerce")
    for s in SEMESTRES:
        res[f"{s}_PCT"] = (res[f"{s}_DIR"] / res[s].where(res[s] > 0)).fillna(0.0)

    def cabecera(df):
        df = df.copy()
        df.insert(0, "Departamento", df["ORIGEN"])
        df.insert(1, "Nombre del departamento", df["ORIGEN"].map(nombres).fillna(""))
        return df

    res = cabecera(res).sort_values(["Departamento", "NOMBRE"], kind="stable")
    resumen = res.rename(columns={
        "DNI": "DNI", "NOMBRE": "Docente", "META": "Horas del padrón",
        "I": "Horas plan I", "I_DIR": "Gestión de Dirección I", "I_PCT": "% Dirección I",
        "II": "Horas plan II", "II_DIR": "Gestión de Dirección II",
        "II_PCT": "% Dirección II"})
    resumen["Plan guardado"] = [
        ", ".join(s for s in SEMESTRES if r[f"Horas plan {s}"] > 0) or "Sin plan"
        for _, r in resumen.iterrows()]
    cols = ["Departamento", "Nombre del departamento", "DNI", "Docente", "Horas del padrón",
            "Plan guardado", "Horas plan I", "Gestión de Dirección I", "% Dirección I",
            "Horas plan II", "Gestión de Dirección II", "% Dirección II"]
    resumen = resumen[cols].reset_index(drop=True)

    direccion = resumen[(resumen["Gestión de Dirección I"] > 0)
                        | (resumen["Gestión de Dirección II"] > 0)].reset_index(drop=True)
    direccion = direccion.drop(columns=["Plan guardado"])

    desc = dict(zip(cecos["CODIGO_CECO"].astype(str).str.strip(), cecos["DESCRIPCION_CECO"]))
    det = cabecera(h)
    det["Semestre"] = det["SEM"].map(SEMESTRES)
    det["Descripción del centro"] = [
        "Gestión de Dirección (la valoriza Desarrollo Humano)" if c == "0" else desc.get(c, "")
        for c in det["CENTRO_COSTO"]]
    det["Tipo de hora"] = det["ACAD"].map(
        {True: "Académicas (informativo, no suma)", False: "Cronológicas"})
    det["Gestión de Dirección"] = det["DIR"].map({True: "Sí", False: ""})
    detalle = (det.rename(columns={"NOMBRE": "Docente", "CENTRO_COSTO": "Centro de costo",
                                   "CONCEPTO": "Concepto", "HORAS": "Horas"})
               .sort_values(["Departamento", "Docente", "Semestre", "Centro de costo"],
                            kind="stable")
               [["Departamento", "Nombre del departamento", "DNI", "Docente", "Semestre",
                 "Centro de costo", "Descripción del centro", "Concepto", "Horas",
                 "Tipo de hora", "Gestión de Dirección"]].reset_index(drop=True))

    g = resumen.groupby(["Departamento", "Nombre del departamento"], dropna=False)
    depto = pd.DataFrame({
        "Docentes": g.size(),
        "Con plan I": g["Horas plan I"].apply(lambda s: int((s > 0).sum())),
        "Con plan II": g["Horas plan II"].apply(lambda s: int((s > 0).sum())),
        "Con Gestión de Dirección": g.apply(
            lambda d: int(((d["Gestión de Dirección I"] > 0)
                           | (d["Gestión de Dirección II"] > 0)).sum()), include_groups=False),
        "Horas plan I": g["Horas plan I"].sum(),
        "Gestión de Dirección I": g["Gestión de Dirección I"].sum(),
        "Horas plan II": g["Horas plan II"].sum(),
        "Gestión de Dirección II": g["Gestión de Dirección II"].sum(),
    }).reset_index()
    return {"Gestión de Dirección": direccion, "Resumen por docente": resumen,
            "Por departamento": depto, "Detalle": detalle}


NOTAS = [
    "Horas docentes TC 2027 · planes de trabajo guardados por los departamentos",
    "",
    "Horas cronológicas semanales en decimal (3.50 = 3 h 30 min).",
    "Gestión de Dirección: centro de costo 0. No la valoriza la app; la valoriza "
    "Desarrollo Humano.",
    "% Dirección = horas de Gestión de Dirección / horas del plan del semestre "
    "(proporción con la que se reparte la remuneración).",
    "Las horas académicas de dictado son informativas: no suman al plan (suma su "
    "equivalente cronológico). En «Detalle» aparecen marcadas.",
    "«Resumen por docente» incluye a los docentes del padrón sin plan guardado (horas en 0).",
    "Son borradores: cambian cada vez que un departamento guarda su plan.",
]


def excel(tablas: dict[str, pd.DataFrame], generado: str) -> bytes:
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        for nombre, df in tablas.items():
            df.to_excel(xw, sheet_name=nombre, index=False)
            ws = xw.sheets[nombre]
            ws.freeze_panes = "A2"
            ws.auto_filter.ref = ws.dimensions
            for celda in ws[1]:
                celda.font = Font(bold=True, color="FFFFFF")
                celda.fill = PatternFill("solid", fgColor="1F4E78")
                celda.alignment = Alignment(wrap_text=True, vertical="center")
            for i, col in enumerate(df.columns, start=1):
                letra = get_column_letter(i)
                largo = max([len(str(col))] + [len(str(v)) for v in df[col].head(300)])
                ws.column_dimensions[letra].width = min(max(10, largo + 2), 45)
                fmt = ("0.0%" if col.startswith("%") else
                       "#,##0.00" if pd.api.types.is_float_dtype(df[col]) else None)
                if col == "DNI":
                    fmt = "@"
                if fmt:
                    for (c,) in ws.iter_rows(min_row=2, min_col=i, max_col=i):
                        c.number_format = fmt
        ws = xw.book.create_sheet("Notas")
        for fila, texto in enumerate(NOTAS + ["", f"Generado: {generado}"], start=1):
            ws.cell(row=fila, column=1, value=texto)
        ws["A1"].font = Font(bold=True, size=12)
        ws.column_dimensions["A"].width = 110
    return buf.getvalue()
