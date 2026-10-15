"""
Resumen de valorización: los montos que dejaron los procedimientos en PLANILLA.

Muestra 2027 (lo valorizado con la app) y lo compara con 2026 en el mismo
alcance. Cada usuario ve solo lo suyo: Presupuesto todo, un departamento lo
suyo, la DGA la carga académica.
"""

import pandas as pd
import streamlit as st

from .flujo import DGA, fmt

# PLANILLA.ORIGEN -> nombre de la planilla en la app. En 2026 los transversales
# iban en su propia hoja; en 2027 van dentro de los planes TC.
PLANILLA = {
    "1. Plan TC-I": "Plan de trabajo TC",
    "Plan TC-II": "Plan de trabajo TC",
    "Plan TC Transversales": "Plan de trabajo TC",
    "Horas Adicionales": "Horas adicionales",
    "Postgrado": "Postgrado",
    "Investigacion": "Investigación",
    "Ayudantias": "Ayudantías",
    "Carga Academica": "Carga académica",
}
MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct",
                "Nov", "Dic"]
SOLES = st.column_config.NumberColumn(format="localized")


def _alcance(usuario, deptos) -> list[str]:
    if usuario.presupuesto:
        return [d for d, _ in deptos] + [DGA]
    return list(usuario.departamentos) + ([DGA] if usuario.dga else [])


def _preparar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["IMPORTE"] = pd.to_numeric(df["IMPORTE"], errors="coerce").fillna(0.0)
    df["PLANILLA"] = df["ORIGEN"].map(PLANILLA).fillna(df["ORIGEN"])
    df["MES"] = pd.to_numeric(df["MES"], errors="coerce")
    df["PARTIDA_DESC"] = (df["PARTIDA"] + " · " + df["DESCRIPCION"].fillna("")).str.strip(" ·")
    return df


def _tabla_soles(df: pd.DataFrame, **kw):
    cfg = {c: SOLES for c in df.columns if pd.api.types.is_numeric_dtype(df[c])}
    st.dataframe(df, hide_index=True, width="stretch", column_config=cfg, **kw)


def vista_reporte(repo, fl, usuario, deptos):
    st.caption("Montos valorizados (PLANILLA) en soles. 2027 incluye solo lo que ya se "
               "valorizó con la app; 2026 es la referencia en el mismo alcance.")
    alcance = _alcance(usuario, deptos)
    nombres = {**dict(deptos), DGA: "Carga académica (DGA)"}
    d27 = _preparar(repo.valorizacion(2027, alcance))
    d26 = _preparar(repo.valorizacion(2026, alcance))

    c1, c2 = st.columns(2)
    sel_deptos = c1.multiselect("Departamento", alcance, default=alcance,
                                format_func=lambda d: f"{d} · {nombres.get(d, d)}")
    planillas = sorted(set(d27["PLANILLA"]) | set(d26["PLANILLA"]))
    sel_planillas = c2.multiselect("Planilla", planillas, default=planillas)
    filtro = lambda d: d[d["DEPTO"].isin(sel_deptos) & d["PLANILLA"].isin(sel_planillas)]
    d27, d26 = filtro(d27), filtro(d26)

    t27, t26 = d27["IMPORTE"].sum(), d26["IMPORTE"].sum()
    m1, m2, m3 = st.columns(3)
    m1.metric("Total 2027", f"S/ {t27:,.2f}")
    m2.metric("Total 2026 (mismo alcance)", f"S/ {t26:,.2f}")
    m3.metric("Diferencia", f"S/ {t27 - t26:,.2f}",
              f"{(t27 / t26 - 1) * 100:+.1f} %" if t26 else None, delta_color="off")

    # Estado de valorización de cada departamento del alcance
    if fl.disponible:
        estado = pd.DataFrame([{
            "Departamento": f"{d} · {nombres.get(d, d)}",
            "Última valorización": fmt(fl.estado(d).get("FECHA_VALORIZACION")),
            "Cambios sin valorizar": "Sí" if fl.cambios_sin_valorizar(d) else "",
            "Cerrado": "🔒" if fl.cerrado(d) else "",
        } for d in sel_deptos])
        with st.expander("Estado de valorización por departamento", expanded=False):
            st.dataframe(estado, hide_index=True, width="stretch")

    if d27.empty:
        st.info("Aún no hay montos 2027 valorizados en este alcance.", icon="ℹ️")
        return

    st.subheader("2027 por departamento y planilla")
    piv = d27.pivot_table(index="DEPTO", columns="PLANILLA", values="IMPORTE",
                          aggfunc="sum", fill_value=0.0)
    piv["Total"] = piv.sum(axis=1)
    piv.loc["Total"] = piv.sum()
    piv = piv.reset_index().rename(columns={"DEPTO": "Departamento"})
    _tabla_soles(piv)

    st.subheader("Comparación con 2026")
    clave = ["DEPTO", "PLANILLA"]
    comp = (d26.groupby(clave)["IMPORTE"].sum().rename("2026").to_frame()
            .join(d27.groupby(clave)["IMPORTE"].sum().rename("2027"), how="outer")
            .fillna(0.0).reset_index())
    comp["Diferencia"] = comp["2027"] - comp["2026"]
    comp["Var. %"] = (comp["Diferencia"] / comp["2026"].where(comp["2026"] != 0) * 100).round(1)
    comp = comp.rename(columns={"DEPTO": "Departamento", "PLANILLA": "Planilla"})
    cfg = {c: SOLES for c in ["2026", "2027", "Diferencia"]}
    cfg["Var. %"] = st.column_config.NumberColumn(format="%.1f %%")
    st.dataframe(comp, hide_index=True, width="stretch", column_config=cfg)

    st.subheader("2027 por mes")
    mensual = (d27.groupby(["MES", "PLANILLA"])["IMPORTE"].sum().reset_index()
               .dropna(subset=["MES"]))
    mensual["Mes"] = mensual["MES"].astype(int).map(
        lambda m: f"{m:02d} {MESES_CORTOS[m - 1]}" if 1 <= m <= 12 else str(m))
    st.bar_chart(mensual, x="Mes", y="IMPORTE", color="PLANILLA",
                 x_label="", y_label="Soles")

    st.subheader("2027 por partida")
    part = d27.groupby("PARTIDA_DESC")["IMPORTE"].sum().reset_index()
    part.columns = ["Partida", "Importe"]
    _tabla_soles(part.sort_values("Partida"))

    with st.expander("Detalle 2027 por centro de costo"):
        det = (d27.groupby(["DEPTO", "PLANILLA", "CENTRO_COSTO", "PARTIDA_DESC"])["IMPORTE"]
               .sum().reset_index())
        det.columns = ["Departamento", "Planilla", "Centro de costo", "Partida", "Importe"]
        _tabla_soles(det)
        st.download_button("Descargar detalle (CSV)",
                           det.to_csv(index=False).encode("utf-8-sig"),
                           file_name="valorizacion_2027.csv", mime="text/csv")
