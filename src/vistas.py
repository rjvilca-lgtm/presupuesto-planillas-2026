"""
Componentes de interfaz — grilla matricial estilo Excel.

Foco de experiencia:
  - Los 12 meses son columnas: se recupera la navegación horizontal de Excel
    y se reduce ~12 veces el número de filas frente al formato largo.
  - Se puede pegar un bloque de celdas desde Excel directamente en la grilla.
  - La grilla se pre-puebla con el padrón cuando aplica, para que el usuario
    complete solo las horas.
  - Los centros de costo se limitan a los del departamento.
  - El monto presupuestado reacciona mientras se teclea.
"""

import pandas as pd
import streamlit as st

from .config import MESES, MESES_ABBR, cfg_de, dims_fila
from .validacion import formato_soles


CSS = """
<style>
  .hero { padding: 1.1rem 1.3rem; border-left: 4px solid #B45309;
          background: #FFFFFF; border-radius: 6px; margin-bottom: .4rem; }
  .hero .monto { font-size: 2.6rem; font-weight: 700; color: #B45309;
                 line-height: 1.05; font-variant-numeric: tabular-nums; }
  .hero .sub { color: #55607A; font-size: .9rem; margin-top: .15rem; }
  .hero .nota { color: #8A93A8; font-size: .82rem; margin-top: .35rem; }
</style>
"""


def inyectar_estilos():
    st.markdown(CSS, unsafe_allow_html=True)


def selector_contexto(repo):
    """Departamento y planilla. En producción el departamento debe venir del
    usuario autenticado (SSO); aquí es un selector para la demostración."""
    from .config import PLANILLAS
    deptos = repo.departamentos()
    col1, col2 = st.columns([1, 2])
    with col1:
        origen = st.selectbox(
            "Departamento",
            [d[0] for d in deptos],
            format_func=lambda c: f"{c} · {dict(deptos)[c]}",
        )
    with col2:
        hoja = st.selectbox(
            "Planilla",
            list(PLANILLAS),
            format_func=lambda h: PLANILLAS[h]["etiqueta"],
        )
    return origen, hoja


def hero(hoja: str, total_soles: float, horas: float, lineas: int, registros: int):
    cfg = cfg_de(hoja)
    if cfg["tarifa"] == "server":
        monto = f"{horas:,.0f} h"
        nota = "El importe en soles se calcula al valorizar en el sistema."
    else:
        monto = formato_soles(total_soles)
        nota = "Estimado en vivo. El valor final se confirma al valorizar."
    st.markdown(
        f"""<div class="hero">
              <div class="monto">{monto}</div>
              <div class="sub">{lineas} línea(s) · {registros} registro(s) mensual(es)</div>
              <div class="nota">{nota}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def _semilla(cfg: dict, roster: pd.DataFrame) -> pd.DataFrame:
    """Grilla inicial: dimensiones de fila + una columna por mes.
    Con padrón, una fila por docente ya identificada."""
    dims = dims_fila(cfg)
    if cfg["usa_roster"] and not roster.empty:
        base = roster.copy()
        for d in dims:
            if d not in base.columns:
                base[d] = None
        base = base[dims]
    else:
        base = pd.DataFrame(columns=dims)
    for m in MESES:
        base[m] = pd.Series(dtype="float64")
    return base


def grilla(cfg: dict, ccos: pd.DataFrame, roster: pd.DataFrame,
           tarifas: dict) -> pd.DataFrame:
    """data_editor matricial: dimensiones a la izquierda, 12 meses a la derecha."""
    ccos_opts = ccos["CODIGO_CECO"].tolist()
    dims = dims_fila(cfg)
    metrica = cfg["metrica"]
    unidad = "horas" if metrica == "HORAS" else "importe (S/)"

    colcfg = {
        "DNI": st.column_config.TextColumn("DNI", disabled=cfg["usa_roster"]),
        "NOMBRE": st.column_config.TextColumn("Docente", disabled=cfg["usa_roster"],
                                              width="medium"),
        "CENTRO_COSTO": st.column_config.SelectboxColumn(
            "Centro de costo", options=ccos_opts, required=True, width="medium",
            help="Solo aparecen los centros de costo de tu departamento."),
        "CONCEPTO": st.column_config.TextColumn("Concepto"),
        "CONCEPTO_2": st.column_config.TextColumn("Detalle"),
    }
    if cfg["tarifa"] == "catalogo":
        colcfg[cfg["catalogo_key"]] = st.column_config.SelectboxColumn(
            "Tipo", options=list(tarifas), required=True,
            help="La tarifa se aplica sola según el tipo. No se teclea el precio.")

    # columnas de mes (encabezado corto para ver más meses a la vez)
    fmt = "%.1f" if metrica == "HORAS" else "%.2f"
    for m in MESES:
        colcfg[m] = st.column_config.NumberColumn(
            MESES_ABBR[m], min_value=0.0, format=fmt, width="small")

    st.caption(f"Escribe las {unidad} de cada mes en su columna. "
               "Puedes pegar un bloque de celdas copiado desde Excel.")

    df = _semilla(cfg, roster)
    columnas = dims + MESES
    editado = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={k: colcfg[k] for k in columnas if k in colcfg},
        key=f"grilla_{cfg['_hoja']}",
    )

    with st.expander("Ver descripción de los centros de costo"):
        st.dataframe(ccos.rename(columns={"CODIGO_CECO": "Código",
                                          "DESCRIPCION_CECO": "Descripción"}),
                     hide_index=True, use_container_width=True)
    return editado


def resumen_por_ceco(hoja: str, df: pd.DataFrame):
    """Total por centro de costo, sumando los 12 meses."""
    cfg = cfg_de(hoja)
    meses = [m for m in MESES if m in df.columns]
    if df.empty or not meses:
        return
    val = df[meses].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    tmp = df.assign(_total=val.sum(axis=1))
    tmp = tmp[tmp["_total"] > 0]
    resumen = tmp.groupby("CENTRO_COSTO")["_total"].sum().reset_index()
    etiqueta = "Horas" if cfg["metrica"] == "HORAS" else "Importe (S/)"
    resumen.columns = ["Centro de costo", etiqueta]
    st.dataframe(resumen, hide_index=True, use_container_width=True)
