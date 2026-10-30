"""
Seguimiento del presupuesto 2027 para la Oficina de Presupuesto, e historial
de guardados.

El panel junta en una tabla lo que antes había que revisar departamento por
departamento: docentes TC con sus horas completas por semestre, planillas
guardadas, estado del flujo (sin empezar, en carga, cambios sin valorizar,
valorizado, cerrado) y monto valorizado 2027. Solo conteos y totales.

El historial sale de BITACORA_GUARDADOS_2027 (sql/crear_bitacora_guardados_2027.sql):
una fila por cada guardado, con quién, cuándo y cuántas filas.
"""

import pandas as pd
import streamlit as st

from .config import PLANILLAS
from .flujo import DGA, Flujo, fmt

TC_I, TC_II = "1. Plan TC-I", "Plan TC-II"
_CORTO = {TC_I: "TC I", TC_II: "TC II", "Carga Academica": "Carga académica"}


def _corto(hoja: str) -> str:
    return _CORTO.get(hoja) or (PLANILLAS[hoja]["etiqueta"] if hoja in PLANILLAS else hoja)


def _estado(fl: Flujo, depto: str, guardadas: int) -> str:
    if fl.cerrado(depto):
        return "🔒 Cerrado"
    if fl.cambios_sin_valorizar(depto):
        return "🟠 Cambios sin valorizar"
    if fl.estado(depto).get("FECHA_VALORIZACION"):
        return "✅ Valorizado"
    return "✏️ En carga" if guardadas else "⚪ Sin empezar"


def vista_seguimiento(repo, fl: Flujo, deptos: list[tuple], areas: list[tuple]):
    st.caption("Avance de todos los departamentos en una sola tabla. Se actualiza solo "
               "(los datos tienen como máximo 20 segundos). «Completos»: docentes del padrón "
               "cuyas horas suman lo que les corresponde.")
    try:
        datos = repo.seguimiento()
    except Exception as ex:
        st.warning(f"No se pudo leer el avance ({type(ex).__name__}: {ex}).", icon="⚠️")
        return
    planillas, docentes, montos = datos["planillas"], datos["docentes"], datos["montos"]
    por_depto = planillas.groupby("ORIGEN")["HOJA_ORIGEN"].apply(list).to_dict()
    monto = dict(zip(montos["DEPTO"], montos["IMPORTE"]))
    tc = {(r.DPTO, r.HOJA): r for r in docentes.itertuples(index=False)}

    filas = []
    for d, nombre in deptos:
        hojas = por_depto.get(d, [])
        fila = {"Departamento": f"{d} · {nombre}", "_codigo": d}
        padron = 0
        for hoja, col in ((TC_I, "TC I"), (TC_II, "TC II")):
            r = tc.get((d, hoja))
            padron = max(padron, int(r.PADRON) if r is not None else 0)
            completos = int(r.COMPLETOS) if r is not None else 0
            fila[f"{col} completos"] = f"{completos} / {int(r.PADRON)}" if r is not None else "—"
            fila[f"{col} %"] = (100 * completos / r.PADRON) if r is not None and r.PADRON else None
        fila["Docentes TC"] = padron
        fila["Planillas guardadas"] = ", ".join(sorted(_corto(h) for h in hojas)) or "—"
        fila["Estado"] = _estado(fl, d, len(hojas))
        fila["Último guardado"] = fmt(fl.estado(d).get("FECHA_GUARDADO"))
        fila["Valorizado 2027 (S/)"] = monto.get(d)
        filas.append(fila)
    otros = [(DGA, "Carga académica (DGA)")] + [(a, f"{n} (ayudantías)") for a, n in areas]
    for d, nombre in otros:
        hojas = por_depto.get(d, [])
        filas.append({"Departamento": f"{d} · {nombre}", "_codigo": d,
                      "Planillas guardadas": ", ".join(sorted(_corto(h) for h in hojas)) or "—",
                      "Estado": _estado(fl, d, len(hojas)),
                      "Último guardado": fmt(fl.estado(d).get("FECHA_GUARDADO")),
                      "Valorizado 2027 (S/)": monto.get(d)})
    tabla = pd.DataFrame(filas)

    solo_deptos = tabla[tabla["_codigo"].isin([d for d, _ in deptos])]
    n = len(solo_deptos)
    contar = lambda texto: int(solo_deptos["Estado"].str.contains(texto).sum())
    padron_total = sum(int(r.PADRON) for r in docentes.itertuples() if r.HOJA == TC_I)
    completos_i = sum(int(r.COMPLETOS) for r in docentes.itertuples() if r.HOJA == TC_I)
    completos_ii = sum(int(r.COMPLETOS) for r in docentes.itertuples() if r.HOJA == TC_II)
    m = st.columns(5)
    m[0].metric("Cerrados", f"{contar('Cerrado')} / {n}")
    m[1].metric("Valorizados al día", f"{contar('Valorizado')} / {n}")
    m[2].metric("Con cambios sin valorizar", contar("sin valorizar"))
    m[3].metric("Sin empezar", contar("Sin empezar"))
    m[4].metric("Docentes TC completos (I · II)",
                f"{completos_i} · {completos_ii}",
                help=f"De {padron_total} docentes en el padrón, en cada semestre.")

    filtro = st.segmented_control(
        "Mostrar", ["Todos", "Pendientes", "Cerrados"], default="Todos",
        key="seguimiento_filtro",
        help="Pendientes: sin empezar, en carga o con cambios sin valorizar.")
    if filtro == "Pendientes":
        tabla = tabla[~tabla["Estado"].str.contains("Cerrado|Valorizado")]
    elif filtro == "Cerrados":
        tabla = tabla[tabla["Estado"].str.contains("Cerrado")]
    st.dataframe(
        tabla.drop(columns="_codigo"), hide_index=True, width="stretch",
        column_order=["Departamento", "Estado", "Docentes TC", "TC I completos", "TC I %",
                      "TC II completos", "TC II %", "Planillas guardadas", "Último guardado",
                      "Valorizado 2027 (S/)"],
        column_config={
            "TC I %": st.column_config.ProgressColumn("TC I", min_value=0, max_value=100,
                                                      format="%.0f%%"),
            "TC II %": st.column_config.ProgressColumn("TC II", min_value=0, max_value=100,
                                                       format="%.0f%%"),
            "Docentes TC": st.column_config.NumberColumn(format="%d"),
            "Valorizado 2027 (S/)": st.column_config.NumberColumn(format="%,.2f"),
        })
    st.caption("Para ver el detalle de un departamento, ábrelo en «Presupuesto por "
               "departamento» › Resumen y valorización. Para bloquear, desbloquear o reabrir, "
               "usa «Plazos y bloqueos».")


def vista_historial(repo, deptos: list[tuple], areas: list[tuple], origenes=None,
                    limite: int = 500, filtros: bool = True):
    """Historial de guardados. origenes: los departamentos que se muestran
    (None = todos, para Presupuesto)."""
    try:
        df = repo.historial_guardados(origenes, limite)
    except Exception as ex:
        st.warning(f"No se pudo leer el historial ({type(ex).__name__}).", icon="⚠️")
        return
    if df is None:
        st.info("El historial empieza a registrarse cuando se ejecute "
                "`sql/crear_bitacora_guardados_2027.sql` en Azure.", icon="ℹ️")
        return
    if df.empty:
        st.info("Aún no hay guardados registrados.", icon="ℹ️")
        return
    nombres = {**dict(deptos), **dict(areas), DGA: "Carga académica (DGA)"}
    if filtros:
        c1, c2, c3 = st.columns(3)
        sel_d = c1.multiselect("Departamento", sorted(df["ORIGEN"].unique()),
                               format_func=lambda d: f"{d} · {nombres.get(d, d)}",
                               key="hist_deptos", placeholder="Todos")
        sel_h = c2.multiselect("Planilla", sorted(df["HOJA_ORIGEN"].unique()),
                               format_func=_corto, key="hist_hojas", placeholder="Todas")
        sel_e = c3.multiselect("Usuario", sorted(df["EMAIL"].dropna().unique()),
                               key="hist_emails", placeholder="Todos")
        if sel_d:
            df = df[df["ORIGEN"].isin(sel_d)]
        if sel_h:
            df = df[df["HOJA_ORIGEN"].isin(sel_h)]
        if sel_e:
            df = df[df["EMAIL"].isin(sel_e)]
    vista = df.assign(
        ORIGEN=df["ORIGEN"].map(lambda d: f"{d} · {nombres.get(d, d)}"),
        HOJA_ORIGEN=df["HOJA_ORIGEN"].map(_corto),
        VALORIZADO=df["VALORIZADO"].map(lambda v: "Sí" if v else ""))
    st.dataframe(
        vista, hide_index=True, width="stretch",
        column_config={
            "FECHA": st.column_config.DatetimeColumn("Fecha (Lima)", format="DD/MM/YYYY HH:mm"),
            "ORIGEN": "Departamento", "HOJA_ORIGEN": "Planilla", "EMAIL": "Guardó",
            "FILAS": st.column_config.NumberColumn("Filas guardadas", format="%d"),
            "VALORIZADO": "Valorizado al guardar"})
    st.caption(f"Últimos {len(vista)} guardado(s). «Filas guardadas» es cuántas filas quedaron "
               "en la planilla después de ese guardado: si baja de golpe, alguien borró datos.")
