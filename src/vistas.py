"""
Componentes de interfaz.

Foco de experiencia:
  - El monto presupuestado es el elemento vivo: cambia mientras se teclea,
    y es el dato que hoy el usuario no ve hasta después de valorizar.
  - La grilla se pre-puebla con el padrón cuando aplica, para que el usuario
    complete la métrica en vez de retipear DNIs y nombres.
  - Los centros de costo se limitan a los del departamento: cada quien ve
    solo lo suyo.
  - Los estados vacíos y los errores orientan la acción.
"""

import pandas as pd
import streamlit as st

from .config import MESES, cfg_de
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
    deptos = repo.departamentos()
    col1, col2 = st.columns([1, 2])
    with col1:
        origen = st.selectbox(
            "Departamento",
            [d[0] for d in deptos],
            format_func=lambda c: f"{c} · {dict(deptos)[c]}",
        )
    with col2:
        from .config import PLANILLAS
        hoja = st.selectbox(
            "Planilla",
            list(PLANILLAS),
            format_func=lambda h: PLANILLAS[h]["etiqueta"],
        )
    return origen, hoja


def hero(hoja: str, total_soles: float, horas: float, n: int):
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
              <div class="sub">{n} registro(s) cargado(s) en esta planilla</div>
              <div class="nota">{nota}</div>
            </div>""",
        unsafe_allow_html=True,
    )


def _semilla(cfg: dict, roster: pd.DataFrame) -> pd.DataFrame:
    """Grilla inicial. Con padrón, una fila por docente ya identificada."""
    cols = cfg["dimensiones"] + [cfg["metrica"]]
    if cfg["usa_roster"] and not roster.empty:
        base = roster.copy()
        for c in cols:
            if c not in base.columns:
                base[c] = None
        return base[cols]
    return pd.DataFrame(columns=cols)


def grilla(cfg: dict, ccos: pd.DataFrame, roster: pd.DataFrame,
           tarifas: dict) -> pd.DataFrame:
    """data_editor genérico armado desde la config."""
    ccos_opts = ccos["CODIGO_CECO"].tolist()
    etiqueta_ceco = dict(zip(ccos["CODIGO_CECO"], ccos["DESCRIPCION_CECO"]))

    colcfg = {
        "DNI": st.column_config.TextColumn("DNI", disabled=cfg["usa_roster"]),
        "NOMBRE": st.column_config.TextColumn("Docente", disabled=cfg["usa_roster"],
                                              width="medium"),
        "CENTRO_COSTO": st.column_config.SelectboxColumn(
            "Centro de costo", options=ccos_opts, required=True, width="medium",
            help="Solo aparecen los centros de costo de tu departamento."),
        "CONCEPTO": st.column_config.TextColumn("Concepto"),
        "CONCEPTO_2": st.column_config.TextColumn("Detalle"),
        "MES": st.column_config.SelectboxColumn("Mes", options=MESES, required=True),
    }
    if cfg["tarifa"] == "catalogo":
        colcfg[cfg["catalogo_key"]] = st.column_config.SelectboxColumn(
            "Tipo", options=list(tarifas), required=True,
            help="La tarifa se aplica sola según el tipo. No se teclea el precio.")
    if cfg["metrica"] == "HORAS":
        colcfg["HORAS"] = st.column_config.NumberColumn(
            "Horas", min_value=0.0, step=1.0, required=True, format="%.2f")
    else:
        colcfg["IMPORTE"] = st.column_config.NumberColumn(
            "Importe (S/)", min_value=0.0, step=100.0, required=True, format="%.2f")

    df = _semilla(cfg, roster)
    editado = st.data_editor(
        df, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={k: v for k, v in colcfg.items()
                       if k in cfg["dimensiones"] + [cfg["metrica"]]},
        key=f"grilla_{cfg['_hoja']}",
    )
    if etiqueta_ceco:
        with st.expander("Ver descripción de los centros de costo"):
            st.dataframe(ccos.rename(columns={"CODIGO_CECO": "Código",
                                              "DESCRIPCION_CECO": "Descripción"}),
                         hide_index=True, use_container_width=True)
    return editado


def resumen_por_ceco(hoja: str, df: pd.DataFrame, tarifas: dict):
    cfg = cfg_de(hoja)
    if df.empty:
        return
    metrica = cfg["metrica"]
    val = pd.to_numeric(df[metrica], errors="coerce").fillna(0)
    tmp = df.assign(_val=val)
    resumen = tmp.groupby("CENTRO_COSTO")["_val"].sum().reset_index()
    resumen.columns = ["Centro de costo", metrica.title()]
    st.dataframe(resumen, hide_index=True, use_container_width=True)
