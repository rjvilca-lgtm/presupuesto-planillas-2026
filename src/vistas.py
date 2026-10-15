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

import re
from html import escape
from pathlib import Path

import pandas as pd
import streamlit as st

from .repositorio import matriz_desde_entrada
from .config import (CONCEPTO_ACADEMICAS, CONCEPTO_CRONOLOGICAS, FACTOR_CRONOLOGICAS,
                     HORAS_PLAN_TC, MESES, MESES_ABBR, SEMESTRES, TOLERANCIA_HORAS,
                     a_hhmm, cfg_de, de_hhmm, dims_fila, es_concepto, meta_horas)
from .validacion import formato_soles


CSS = """
<style>
  /* menos espacio vacío arriba: la ficha TC entra mejor en pantallas de laptop */
  .block-container, [data-testid="stMainBlockContainer"] { padding-top: 2.5rem; }
  .hero { padding: 1.1rem 1.3rem; border-left: 4px solid #B45309;
          background: #FFFFFF; border-radius: 6px; margin-bottom: .4rem; }
  .hero .monto { font-size: 2.6rem; font-weight: 700; color: #B45309;
                 line-height: 1.05; font-variant-numeric: tabular-nums; }
  .hero .sub { color: #55607A; font-size: .9rem; margin-top: .15rem; }
  .hero .nota { color: #8A93A8; font-size: .82rem; margin-top: .35rem; }

  /* Ficha por docente (planillas TC) — maestro-detalle, estilo de gestión */
  .resumen-tc { background: #FFFFFF; border: 1px solid #E1E5EC; border-radius: 12px;
                padding: 14px 18px; display: flex; align-items: center;
                gap: 28px; margin-bottom: .9rem; flex-wrap: wrap; }
  .resumen-tc .metric .value { font-size: 1.15rem; font-weight: 700; color: #17233B; }
  .resumen-tc .metric .label { color: #667085; font-size: .68rem; margin-top: 2px; }
  .resumen-tc .progress-wrap { min-width: 180px; flex: 1; }
  .resumen-tc .progress-title { font-size: .72rem; color: #667085; margin-bottom: 6px; }
  .progress-track { height: 7px; background: #EDF0F5; border-radius: 20px; overflow: hidden; }
  .progress-track .progress-fill { height: 100%; background: #315B9D; }

  div[class*="st-key-people_card"] { border: 1px solid #E1E5EC; border-radius: 12px;
                                      padding: .3rem .6rem .6rem; }
  .people-header { font-size: .72rem; font-weight: 700; color: #17233B;
                   letter-spacing: .3px; padding: .5rem .2rem .2rem;
                   display: flex; justify-content: space-between; }
  .people-header .pendientes { color: #B45309; font-weight: 600; }

  div[class*="st-key-docitem_"] { margin: 0; }
  div[class*="st-key-docitem_"] button { justify-content: flex-start !important;
                                          text-align: left !important;
                                          font-weight: 400; border-radius: 8px;
                                          padding: .35rem .6rem; min-height: 0;
                                          line-height: 1.25; }
  div[class*="st-key-docitem_"] button > div,
  div[class*="st-key-docitem_"] button p { justify-content: flex-start !important;
                                            text-align: left !important;
                                            width: 100%; font-size: .82rem; }
  div[class*="st-key-docitem_"] button[kind="secondary"] {
      background: transparent; border-color: transparent; }
  div[class*="st-key-docitem_"] button[kind="secondary"]:hover { background: #F7F8FA; }
  div[class*="st-key-docitem_"] button[kind="primary"] {
      background: #F1F5FC; color: #315B9D; border-color: #F1F5FC;
      border-left: 3px solid #315B9D; }

  div[class*="st-key-agregar_docente_"] summary { color: #315B9D; font-size: .78rem;
                                                    font-weight: 600; }

  .detail-head { display: flex; justify-content: space-between; align-items: center;
                gap: 1.2rem; padding-bottom: .9rem; border-bottom: 1px solid #EDF0F4;
                margin-bottom: .9rem; }
  .detail-head .nombre { font-size: 1.05rem; font-weight: 700; color: #17233B; }
  .detail-head .dni { color: #7A8496; font-size: .72rem; margin-top: .2rem; }
  .detail-head .total { text-align: right; background: #F5F7FB; border-radius: 9px;
                        padding: .5rem .85rem; min-width: 100px; }
  .detail-head .total .numero { font-size: 1.2rem; font-weight: 700; color: #17233B; }
  .detail-head .total .etiqueta { font-size: .62rem; color: #7A8496; letter-spacing: .2px; }
  .detail-head .total.completo { background: #ECFDF3; }
  .detail-head .total.completo .numero { color: #067647; }
  .detail-head .total.incompleto { background: #FFF6ED; }
  .detail-head .total.incompleto .numero { color: #B45309; }
  .detail-head .total .falta { font-size: .68rem; color: #B45309; margin-top: .1rem; }

  div[class*="st-key-ceco_"] { padding: .7rem 1rem .4rem; margin-bottom: .2rem; }
  .ceco-card-header { display: flex; justify-content: space-between; align-items: baseline;
                      gap: 1rem; border-bottom: 1px solid #F0F2F6; padding-bottom: .4rem; }
  .ceco-card-header .titulo { font-size: .74rem; font-weight: 800; letter-spacing: .3px;
                              text-transform: uppercase; color: #B35B18; }
  .ceco-card-header .codigo-ceco { color: #9BA3B1; font-weight: 500;
                                   text-transform: none; margin-left: .35rem; }
  .ceco-card-header .subtotal { font-size: .78rem; color: #667085; white-space: nowrap; }
  .ceco-card-header .subtotal b { color: #17233B; }

  div[class*="st-key-ceco_"] div[data-testid="stTextInput"] label p {
      font-size: .8rem; color: #344054; }
  /* etiquetas de 1 o 2 líneas con el mismo alto: los campos quedan alineados */
  div[class*="st-key-ceco_"] div[data-testid="stTextInput"] label {
      min-height: 2.5rem; align-items: flex-end; }
  div[class*="st-key-ceco_"] div[data-testid="stTextInput"] { max-width: 230px; }
  div[class*="st-key-ceco_"] div[data-testid="stTextInput"] input {
      background: #F3F5F8; text-align: right; font-weight: 600; color: #25324A;
      font-variant-numeric: tabular-nums; }
  .hhmm-error { color: #B42318; font-size: .72rem; margin-top: -.6rem; }
  /* sin botones +/-: las horas se teclean, y así el campo ocupa menos */
  div[class*="st-key-ceco_"] button[data-testid="stNumberInputStepUp"],
  div[class*="st-key-ceco_"] button[data-testid="stNumberInputStepDown"] { display: none; }
  div[data-testid="stNumberInputContainer"] { background: #F3F5F8 !important;
                                              border-radius: 8px; border: none !important; }
  div[data-testid="stNumberInputField"] { background: transparent !important;
                                          text-align: center; font-weight: 600;
                                          color: #25324A; }

  /* Barra inferior sticky de guardado (solo ficha TC) */
  div[class*="st-key-barra_guardar"] {
      position: fixed; left: 0; right: 0; bottom: 0; z-index: 999;
      background: rgba(255,255,255,.97); border-top: 1px solid #DFE4EB;
      padding: .55rem 3rem; box-shadow: 0 -2px 10px rgba(0,0,0,.05);
  }
  div[class*="st-key-barra_guardar"] .bottom-info { font-size: .78rem; color: #667085;
                                                    padding-top: .45rem; }
</style>
"""


def inyectar_estilos():
    st.markdown(CSS, unsafe_allow_html=True)


# DNI (8 dígitos) o carné de extranjería (9-12 alfanuméricos).
_DOC_IDENTIDAD = re.compile(r"\d{8}|[0-9A-Za-z]{9,12}")

TC_HOJAS = ["1. Plan TC-I", "Plan TC-II"]

# Ficha TC: alto (px) de los paneles con scroll propio y campos por fila
ALTO_PANEL = 470
CAMPOS_POR_FILA = 3


def selector_contexto(repo, permitidos=None):
    """Departamento y planilla. permitidos: los departamentos del usuario
    logueado (None = todos, para Presupuesto).
    Las dos hojas TC (I y II semestre) se presentan como una sola opción
    "Plan de trabajo TC": app.py arma las pestañas por semestre a partir de
    TC_HOJAS. Las demás planillas siguen igual, una por una."""
    from .config import PLANILLAS
    deptos = repo.departamentos()
    if permitidos is not None:
        deptos = [d for d in deptos if d[0] in set(permitidos)]
    opciones = ["TC"] + [h for h in PLANILLAS if h not in TC_HOJAS] + ["RESUMEN"]
    etiquetas = {"TC": "Plan de trabajo TC", "RESUMEN": "✔ Resumen y valorización",
                 **{h: PLANILLAS[h]["etiqueta"] for h in PLANILLAS}}
    col1, col2 = st.columns([1, 2])
    with col1:
        origen = st.selectbox(
            "Departamento",
            [d[0] for d in deptos],
            format_func=lambda c: f"{c} · {dict(deptos)[c]}",
        )
    with col2:
        seleccion = st.selectbox(
            "Planilla", opciones, format_func=lambda h: etiquetas[h])
    return origen, seleccion


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


@st.cache_data
def _leer_precarga(ruta: str) -> pd.DataFrame:
    return pd.read_csv(Path(__file__).resolve().parent.parent / ruta,
                       dtype=str, encoding="utf-8").fillna("")


def _columnas_fila(cfg: dict) -> list[str]:
    """Columnas de la grilla a la izquierda de los meses: info + dimensiones
    (+ TARIFA si es editable, justo después del TIPO)."""
    cols = list(cfg.get("columnas_info", [])) + dims_fila(cfg)
    if cfg.get("tarifa_editable"):
        cols.insert(cols.index(cfg["catalogo_key"]) + 1, "TARIFA")
    return cols


def _semilla(cfg: dict, roster: pd.DataFrame, guardado=None) -> pd.DataFrame:
    """Grilla inicial: dimensiones de fila + una columna por mes.
    Si hay algo guardado, eso (el usuario retoma donde quedó); con precarga se
    agregan además los conceptos del CSV que aún no usó. Sin nada guardado:
    con padrón, una fila por docente; con precarga, las filas del CSV."""
    cols = _columnas_fila(cfg)
    if guardado is not None and not guardado.empty:
        base = matriz_desde_entrada(cfg["_hoja"], guardado)
        if cfg.get("precarga"):
            precarga = _leer_precarga(cfg["precarga"])
            claves = [c for c in precarga.columns if c in base.columns]
            usados = set(map(tuple, base[claves].fillna("").astype(str).values))
            faltan = precarga[[tuple(f) not in usados
                               for f in precarga[claves].astype(str).values]]
            base = pd.concat([base, faltan], ignore_index=True)
    elif cfg["usa_roster"] and not roster.empty:
        base = roster.copy()
    elif cfg.get("precarga"):
        base = _leer_precarga(cfg["precarga"]).copy()
    else:
        base = pd.DataFrame(columns=cols)
    for d in cols:
        if d not in base.columns:
            base[d] = None
    base = base[cols + [m for m in MESES if m in base.columns]]
    if "TARIFA" in cols:
        base["TARIFA"] = pd.to_numeric(base["TARIFA"], errors="coerce")
    for m in MESES:
        base[m] = (pd.to_numeric(base[m], errors="coerce") if m in base
                   else pd.Series(dtype="float64", index=base.index))
    return base.reset_index(drop=True)


def _semestre_activo(hoja: str) -> str:
    """Selector de semestre: reduce a 6 las columnas de mes visibles.
    Los 12 meses siguen en los datos del editor (ver grilla())."""
    opciones = list(SEMESTRES)
    key = f"semestre_{hoja}"
    if hasattr(st, "segmented_control"):
        return st.segmented_control(
            "Semestre", opciones, default=opciones[0], key=key) or opciones[0]
    return st.radio("Semestre", opciones, horizontal=True, key=key)


def grilla(cfg: dict, ccos: pd.DataFrame, roster: pd.DataFrame,
           tarifas: dict, origen: str, guardado=None,
           solo_lectura: bool = False) -> pd.DataFrame:
    """data_editor matricial: dimensiones a la izquierda, 12 meses a la derecha
    (solo se muestran los 6 del semestre elegido para reducir el scroll).

    El editor recibe siempre la MISMA base mientras se edita: con
    num_rows="dynamic" la identidad del widget depende de los datos, así que
    devolverle su propia salida lo reinicia y pierde ediciones. La base solo
    se renueva (con lo último editado) cuando el editor se vuelve a crear:
    al cambiar de semestre, de planilla o de pestaña. Los 12 meses
    viajan en los datos y column_order oculta los 6 del otro semestre, así que
    no hace falta emparejar filas entre semestres."""
    hoja = cfg["_hoja"]
    ccos_opts = ccos["CODIGO_CECO"].tolist()
    dims = dims_fila(cfg)
    metrica = cfg["metrica"]
    unidad = "horas" if metrica == "HORAS" else "importe (S/)"
    semestre = _semestre_activo(hoja)
    meses_visibles = SEMESTRES[semestre]

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
    if cfg.get("precarga"):
        precarga = _leer_precarga(cfg["precarga"])
        # Las filas nuevas eligen de la misma lista que viene precargada
        for col, titulo in (("FOCO", "Foco"), ("CONCEPTO", "Concepto")):
            if col in precarga:
                colcfg[col] = st.column_config.SelectboxColumn(
                    titulo, options=sorted(precarga[col].unique()), width="medium")
    if cfg["tarifa"] == "catalogo":
        colcfg[cfg["catalogo_key"]] = st.column_config.SelectboxColumn(
            "Tipo", options=list(tarifas), required=True,
            help="La tarifa se aplica sola según el tipo. No se teclea el precio."
            if not cfg.get("tarifa_editable") else
            "Al elegir el tipo se llena la tarifa 2027; puedes cambiarla.")
    for col, valores in cfg.get("opciones", {}).items():
        colcfg[col] = st.column_config.SelectboxColumn(
            {"CONCEPTO": "Concepto", "TIPO": "Tipo"}.get(col, col.title()),
            options=valores, required=True, width="large" if col == "CONCEPTO" else "medium")
    if cfg.get("tarifa_editable"):
        colcfg["TARIFA"] = st.column_config.NumberColumn(
            "Tarifa (S/ por hora)", min_value=0.0, format="%.2f", width="small",
            help="Se llena con la tarifa 2027 del tipo elegido. Puedes cambiarla.")

    # columnas de mes (encabezado corto para ver más meses a la vez)
    fmt = "%.1f" if metrica == "HORAS" else "%.2f"
    for m in MESES:
        colcfg[m] = st.column_config.NumberColumn(
            MESES_ABBR[m], min_value=0.0, format=fmt, width="small")

    st.caption(f"Escribe las {unidad} de cada mes en su columna. "
               "Puedes pegar un bloque de celdas copiado desde Excel. "
               "Los datos del otro semestre no se pierden al cambiar de vista.")

    cols_fila = _columnas_fila(cfg)
    base_key = f"_base_{hoja}_{origen}"
    ultimo_key = f"_ultimo_{hoja}_{origen}"
    ver_key = f"_ver_{hoja}_{origen}"
    widget_key = f"grilla_{hoja}_{origen}_{semestre}_{st.session_state.get(ver_key, 0)}"
    if base_key not in st.session_state:
        st.session_state[base_key] = _semilla(cfg, roster, guardado)
        st.session_state[ultimo_key] = st.session_state[base_key]
    elif widget_key not in st.session_state:
        # El editor se vuelve a crear (cambio de semestre, de planilla o de
        # pestaña): Streamlit ya olvidó sus ediciones, así que arranca de lo
        # último editado y no de la base anterior.
        st.session_state[base_key] = st.session_state[ultimo_key].reset_index(drop=True)

    editado = st.data_editor(
        st.session_state[base_key], num_rows="fixed" if solo_lectura else "dynamic",
        width="stretch", disabled=solo_lectura,
        hide_index=True, column_order=cols_fila + meses_visibles,
        column_config={k: v for k, v in colcfg.items() if k in cols_fila + MESES},
        key=widget_key,
    )
    if cfg.get("tarifa_editable") and not solo_lectura:
        _prellenar_tarifa(cfg, editado, st.session_state[ultimo_key], tarifas,
                          base_key, ultimo_key, ver_key)
    st.session_state[ultimo_key] = editado

    with st.expander("Ver descripción de los centros de costo"):
        st.dataframe(ccos.rename(columns={"CODIGO_CECO": "Código",
                                          "DESCRIPCION_CECO": "Descripción"}),
                     hide_index=True, width="stretch")
    return editado


_COLS_LEDGER = ["DNI", "NOMBRE", "HORAS_META", "CENTRO_COSTO", "CONCEPTO", "HORAS"]


def _prellenar_tarifa(cfg, editado, previo, tarifas, base_key, ultimo_key, ver_key):
    """Pone la tarifa del catálogo en las filas cuyo TIPO se acaba de elegir
    o cambiar (o que tienen TIPO y no tienen tarifa). Una tarifa tecleada a
    mano se respeta mientras no cambie el TIPO.

    El editor no permite cambiar celdas desde el código: se renueva la base
    con lo editado + la tarifa y se cambia la clave del widget para que no
    vuelva a aplicar sus ediciones sobre la base nueva."""
    tipo = editado[cfg["catalogo_key"]]
    tipo_prev = previo[cfg["catalogo_key"]].reindex(editado.index)
    sugerida = tipo.map(tarifas)
    tarifa = pd.to_numeric(editado["TARIFA"], errors="coerce")
    cambio = tipo.notna() & (tipo != tipo_prev)
    fijar = (cambio | (tipo.notna() & tarifa.isna())) & sugerida.notna() & (tarifa != sugerida)
    if not fijar.any():
        return
    nuevo = editado.copy()
    nuevo.loc[fijar, "TARIFA"] = sugerida[fijar]
    nuevo = nuevo.reset_index(drop=True)
    st.session_state[base_key] = nuevo
    st.session_state[ultimo_key] = nuevo
    st.session_state[ver_key] = st.session_state.get(ver_key, 0) + 1
    st.rerun()


def _semilla_ficha(roster: pd.DataFrame, estructura: pd.DataFrame,
                   guardado=None) -> pd.DataFrame:
    """Ledger inicial de la ficha: una fila por (docente, CECO, concepto),
    con HORAS en decimal. Cruce del padrón con la estructura CECO->concepto,
    con las horas guardadas encima (el usuario retoma donde quedó).
    HORAS_META: horas cronológicas que debe sumar el docente.

    Lo guardado que no esté en el padrón o en la estructura (docente agregado
    a mano, concepto que salió de la estructura) también entra, para no
    perder datos."""
    if roster.empty or estructura.empty:
        base = pd.DataFrame(columns=_COLS_LEDGER)
    else:
        base = roster.merge(estructura, how="cross")
        base = base.rename(columns={"CODIGO_CECO": "CENTRO_COSTO"})
        if "HORAS_META" not in base:
            base["HORAS_META"] = None
        base["HORAS"] = 0.0
        base = base[_COLS_LEDGER]
    if guardado is not None and not guardado.empty:
        clave = ["DNI", "CENTRO_COSTO", "CONCEPTO"]
        # Una fila por clave: si hubiera repetidas, son copias de un mismo valor
        g = guardado.groupby(clave, as_index=False).agg(
            NOMBRE=("NOMBRE", "first"), HORAS_G=("HORAS", "max"))
        nuevos = g.loc[~g["DNI"].isin(base["DNI"]), ["DNI", "NOMBRE"]].drop_duplicates("DNI")
        if not nuevos.empty and not estructura.empty:
            extra = nuevos.merge(estructura.rename(columns={"CODIGO_CECO": "CENTRO_COSTO"}),
                                 how="cross").assign(HORAS_META=None, HORAS=0.0)
            base = pd.concat([base, extra[_COLS_LEDGER]], ignore_index=True)
        # left + lo que sobre al final: conserva el orden del padrón
        base = base.merge(g, on=clave, how="left", suffixes=("", "_g"))
        sobrantes = g.merge(base[clave], on=clave, how="left", indicator=True)
        sobrantes = sobrantes[sobrantes["_merge"] == "left_only"].drop(columns="_merge")
        base = pd.concat([base, sobrantes.rename(columns={"NOMBRE": "NOMBRE_g"})],
                         ignore_index=True)
        base["NOMBRE"] = base["NOMBRE"].fillna(base["NOMBRE_g"])
        base["HORAS"] = base["HORAS_G"].fillna(base["HORAS"]).fillna(0.0)
        # Un solo nombre por DNI (el del padrón): la lista agrupa por DNI y nombre
        base["NOMBRE"] = base["DNI"].map(base.groupby("DNI", sort=False)["NOMBRE"].first())
        metas = base.groupby("DNI")["HORAS_META"].first()
        base["HORAS_META"] = base["DNI"].map(metas)
        base = base[_COLS_LEDGER]
    base["HORAS_META"] = base["HORAS_META"].map(meta_horas)
    return base.reset_index(drop=True)


def _horas_plan(ledger: pd.DataFrame) -> pd.Series:
    """Horas cronológicas por docente: todo menos las académicas de dictado
    (ya entran convertidas en las cronológicas)."""
    plan = ledger[~ledger["CONCEPTO"].map(lambda c: es_concepto(c, CONCEPTO_ACADEMICAS))]
    return plan.groupby("DNI")["HORAS"].sum()


def _normalizar_hhmm(key: str):
    """Al salir del campo: '6:30' o '6' se reescribe como '06:30' / '06:00'.
    Lo inválido se deja tal cual para que el usuario vea qué corregir."""
    valor = de_hhmm(st.session_state.get(key))
    if valor is not None:
        st.session_state[key] = a_hhmm(valor)


def _completo(horas: float, meta: float) -> bool:
    return abs(horas - meta) <= TOLERANCIA_HORAS


def ficha_docente(cfg: dict, ccos: pd.DataFrame, estructura: pd.DataFrame,
                   roster: pd.DataFrame, origen: str, guardado=None,
                   solo_lectura: bool = False) -> pd.DataFrame:
    """Ficha por docente para las planillas TC: un valor de horas por
    (CECO, concepto): horas por mes, iguales todo el semestre. Devuelve un
    DataFrame con la misma forma que grilla() (dims_fila(cfg) + MESES) para
    que preparar_filas() no cambie: el valor va solo en cfg["mes_carga"]
    (MARZO / AGOSTO) y el sp de valorización lo replica al resto del semestre.

    Layout maestro-detalle: lista de docentes (con buscador) a la izquierda,
    ficha del docente activo a la derecha (un CECO por tarjeta). Ambos
    paneles tienen alto fijo y scroll propio.
    El docente activo se guarda en session_state para sobrevivir el rerun
    que dispara cada clic de la lista. El resumen superior y el total por
    docente se llenan al final mediante placeholders (st.empty), para
    reflejar lo recién tecleado en este mismo rerun."""
    dims = dims_fila(cfg)
    desc_ceco = dict(zip(estructura["CODIGO_CECO"], estructura["DESCRIPCION_CECO"]))
    desc_ceco.update(zip(ccos["CODIGO_CECO"], ccos["DESCRIPCION_CECO"]))

    estado_key = f"_ficha_{cfg['_hoja']}_{origen}"
    if estado_key not in st.session_state:
        st.session_state[estado_key] = _semilla_ficha(roster, estructura, guardado)
    ledger = st.session_state[estado_key]

    if ledger.empty:
        st.warning("No hay padrón de docentes ni estructura de CECO/conceptos "
                   "para este departamento.", icon="⚠️")
        return pd.DataFrame(columns=dims + MESES)

    docentes = ledger[["DNI", "NOMBRE"]].drop_duplicates().reset_index(drop=True)
    metas = ledger.drop_duplicates("DNI").set_index("DNI")["HORAS_META"].map(meta_horas)
    resumen_slot = st.empty()

    activo_key = f"_docente_activo_{estado_key}"
    if st.session_state.get(activo_key) not in set(docentes["DNI"]):
        st.session_state[activo_key] = docentes["DNI"].iloc[0]
    dni_sel = st.session_state[activo_key]

    col_lista, col_detalle = st.columns([1, 2], gap="medium")

    with col_lista:
        with st.container(key=f"people_card_{estado_key}"):
            # Placeholders: el encabezado (pendientes) y las horas por docente
            # solo reflejan lo recién tecleado si se llenan después de recorrer
            # los campos del docente activo (mismo motivo que resumen_slot).
            cabecera_slot = st.empty()
            filtro = st.text_input(
                "Buscar docente", key=f"buscar_{estado_key}",
                placeholder="Buscar por nombre o DNI", label_visibility="collapsed")
            # Alto fijo con scroll propio: la lista no empuja la ficha hacia
            # abajo aunque el departamento tenga muchos docentes.
            with st.container(height=ALTO_PANEL - 90, border=False):
                lista_slot = st.empty()

            if not solo_lectura:
                with st.expander("➕ Agregar docente fuera del padrón"):
                    st.caption("Usa esto solo si el docente no aparece en el padrón "
                               "del departamento; es una excepción, no el flujo normal.")
                    c1, c2 = st.columns(2)
                    nuevo_dni = c1.text_input("DNI", key=f"nuevo_dni_{estado_key}")
                    nuevo_nombre = c2.text_input("Nombre completo",
                                                 key=f"nuevo_nombre_{estado_key}")
                    nueva_meta = st.number_input(
                        "Horas cronológicas del docente", min_value=1.0, max_value=40.0,
                        value=float(HORAS_PLAN_TC), step=1.0, format="%.0f",
                        key=f"nueva_meta_{estado_key}")
                    if st.button("Agregar docente", key=f"btn_agregar_{estado_key}"):
                        dni_limpio = nuevo_dni.strip()
                        if not dni_limpio or not nuevo_nombre.strip():
                            st.error("Ingresa DNI y nombre para agregar al docente.",
                                    icon="⚠️")
                        elif not _DOC_IDENTIDAD.fullmatch(dni_limpio):
                            st.error("El DNI debe tener 8 dígitos (o 9 a 12 caracteres "
                                     "alfanuméricos si es carné de extranjería).",
                                     icon="⚠️")
                        elif dni_limpio in set(ledger["DNI"]):
                            st.error("Ese DNI ya está en la ficha.", icon="⚠️")
                        else:
                            nuevo = estructura.copy()
                            nuevo = nuevo.rename(columns={"CODIGO_CECO": "CENTRO_COSTO"})
                            nuevo["DNI"] = dni_limpio
                            nuevo["NOMBRE"] = nuevo_nombre.strip()
                            nuevo["HORAS_META"] = float(nueva_meta)
                            nuevo["HORAS"] = 0.0
                            nuevo = nuevo[_COLS_LEDGER]
                            st.session_state[estado_key] = pd.concat(
                                [ledger, nuevo], ignore_index=True)
                            st.rerun()

    def _elegir(dni_d):
        st.session_state[activo_key] = dni_d

    def _pintar_lista(horas_por_docente):
        texto = (filtro or "").strip().lower()
        visibles = docentes
        if texto:
            visibles = docentes[docentes["NOMBRE"].str.lower().str.contains(texto, regex=False)
                                | docentes["DNI"].astype(str).str.contains(texto, regex=False)]
        if visibles.empty:
            st.caption("Ningún docente coincide con la búsqueda.")
        for _, fila_doc in visibles.iterrows():
            dni_d, nombre_d = fila_doc["DNI"], fila_doc["NOMBRE"]
            h = horas_por_docente.get(dni_d, 0.0)
            meta = metas[dni_d]
            activo = dni_d == st.session_state[activo_key]
            icono = (":material/check_circle:" if _completo(h, meta)
                     else ":material/error:" if h > 0
                     else ":material/radio_button_unchecked:")
            with st.container(key=f"docitem_{estado_key}_{dni_d}"):
                st.button(f"**{nombre_d}**  \nDNI {dni_d} · {a_hhmm(h)} / {a_hhmm(meta)} h",
                          key=f"docsel_{estado_key}_{dni_d}", width="stretch",
                          icon=icono,
                          type="primary" if activo else "secondary",
                          on_click=_elegir, args=(dni_d,))

    with col_detalle:
        # Placeholder: nombre + total de horas se pintan juntos al final,
        # cuando ya se conoce el total tras recorrer los campos.
        detalle_head_slot = st.empty()

        sub = ledger[ledger["DNI"] == dni_sel]
        total_docente = 0.0
        invalidos = []

        def _tarjeta_ceco(ceco, grupo):
            """Un CECO a todo el ancho, con sus conceptos en filas de
            CAMPOS_POR_FILA campos: las tarjetas se alinean sin huecos."""
            nonlocal total_docente
            with st.container(border=True, key=f"ceco_{estado_key}_{dni_sel}_{ceco}"):
                cabecera = st.empty()
                subtotal = 0.0
                # Las académicas primero: las cronológicas se calculan de ellas
                # en esta misma pasada.
                filas = sorted(grupo.iterrows(), key=lambda par: not es_concepto(
                    par[1]["CONCEPTO"], CONCEPTO_ACADEMICAS))
                academicas = 0.0
                for i in range(0, len(filas), CAMPOS_POR_FILA):
                    cols = st.columns(CAMPOS_POR_FILA, gap="medium")
                    for col, (idx, fila) in zip(cols, filas[i:i + CAMPOS_POR_FILA]):
                        concepto = fila["CONCEPTO"]
                        key = f"h_{estado_key}_{dni_sel}_{ceco}_{concepto}"
                        if es_concepto(concepto, CONCEPTO_CRONOLOGICAS):
                            # Calculada, no editable: se fija antes de crear el widget
                            valor = academicas * FACTOR_CRONOLOGICAS
                            st.session_state[key] = a_hhmm(valor)
                            col.text_input(
                                str(concepto), key=key, disabled=True,
                                help="Se calcula sola: horas académicas × 45/60.")
                        else:
                            # hh:mm en pantalla; en el ledger (y en la base) va en
                            # decimal: 03:30 -> 3.5
                            texto = col.text_input(
                                str(concepto), value=a_hhmm(fila["HORAS"]), key=key,
                                disabled=solo_lectura,
                                placeholder="hh:mm", on_change=_normalizar_hhmm, args=(key,),
                                help="Horas académicas de dictado (45 min), en hh:mm. "
                                     "No suman al total: se convierten a cronológicas."
                                if es_concepto(concepto, CONCEPTO_ACADEMICAS) else None)
                            valor = de_hhmm(texto)
                            if valor is None:
                                invalidos.append(str(concepto))
                                col.markdown('<div class="hhmm-error">Usa hh:mm, por '
                                             'ejemplo 03:30</div>', unsafe_allow_html=True)
                                valor = float(fila["HORAS"])
                        ledger.loc[idx, "HORAS"] = valor
                        if es_concepto(concepto, CONCEPTO_ACADEMICAS):
                            academicas = valor
                        else:
                            subtotal += valor
                total_docente += subtotal
                cabecera.markdown(
                    f'<div class="ceco-card-header"><div class="titulo">'
                    f'{escape(str(desc_ceco.get(ceco, ceco)))}'
                    f'<span class="codigo-ceco">{escape(str(ceco))}</span></div>'
                    f'<div class="subtotal"><b>{a_hhmm(subtotal)}</b> h</div></div>',
                    unsafe_allow_html=True)

        # Clave por docente: al cambiar de docente el panel vuelve arriba
        with st.container(height=ALTO_PANEL, border=False,
                          key=f"detalle_{estado_key}_{dni_sel}"):
            for ceco, grupo in sub.groupby("CENTRO_COSTO", sort=False):
                _tarjeta_ceco(ceco, grupo)

        # Pasar al docente vecino sin volver a buscarlo en la lista
        pos = int(docentes.index[docentes["DNI"] == dni_sel][0])
        c_ant, c_pos, c_sig = st.columns([1, 2, 1], vertical_alignment="center")
        c_ant.button("← Anterior", key=f"ant_{estado_key}", width="stretch",
                     disabled=pos == 0, on_click=_elegir,
                     args=(docentes["DNI"].iloc[max(pos - 1, 0)],))
        c_pos.markdown(f'<div style="text-align:center;color:#667085;font-size:.8rem">'
                       f'Docente {pos + 1} de {len(docentes)}</div>',
                       unsafe_allow_html=True)
        c_sig.button("Siguiente →", key=f"sig_{estado_key}", width="stretch",
                     disabled=pos == len(docentes) - 1, on_click=_elegir,
                     args=(docentes["DNI"].iloc[min(pos + 1, len(docentes) - 1)],))

        nombre_sel = docentes.loc[docentes["DNI"] == dni_sel, "NOMBRE"].iloc[0]
        meta_sel = metas[dni_sel]
        diferencia = meta_sel - total_docente
        if _completo(total_docente, meta_sel):
            estado_total, aviso = "completo", ""
        else:
            estado_total = "incompleto"
            aviso = (f'<div class="falta">Faltan {a_hhmm(diferencia)} h</div>' if diferencia > 0
                     else f'<div class="falta">Sobran {a_hhmm(-diferencia)} h</div>')
        with detalle_head_slot.container():
            st.markdown(
                f"""<div class="detail-head">
                      <div>
                        <div class="nombre">{escape(str(nombre_sel))}</div>
                        <div class="dni">DNI {escape(str(dni_sel))}</div>
                      </div>
                      <div class="total {estado_total}">
                        <div class="numero">{a_hhmm(total_docente)} / {a_hhmm(meta_sel)}</div>
                        <div class="etiqueta">HORAS CRONOLÓGICAS</div>{aviso}
                      </div>
                    </div>""",
                unsafe_allow_html=True,
            )

    horas_lista = _horas_plan(ledger).reindex(docentes["DNI"], fill_value=0.0)
    completos = pd.Series([_completo(h, metas[d]) for d, h in horas_lista.items()],
                          index=horas_lista.index, dtype=bool)
    pendientes = int((~completos).sum())
    extra = (f'<span class="pendientes">{pendientes} sin completar sus horas</span>'
             if pendientes else "")
    # Para que el guardado se bloquee si hay un hh:mm mal escrito
    st.session_state[f"_invalidos_{cfg['_hoja']}"] = invalidos
    cabecera_slot.markdown(
        f'<div class="people-header"><span>DOCENTES ({len(docentes)})</span>{extra}</div>',
        unsafe_allow_html=True)
    with lista_slot.container():
        _pintar_lista(horas_lista)

    st.session_state[estado_key] = ledger

    con_horas = int(completos.sum())
    horas_total = float(horas_lista.sum())
    pct = (con_horas / len(docentes)) if len(docentes) else 0.0
    with resumen_slot.container():
        st.markdown(
            f"""<div class="resumen-tc">
                  <div class="metric">
                    <div class="value">{con_horas} / {len(docentes)}</div>
                    <div class="label">Docentes con sus horas completas</div>
                  </div>
                  <div class="metric">
                    <div class="value">{a_hhmm(horas_total)} h</div>
                    <div class="label">Horas cronológicas asignadas</div>
                  </div>
                  <div class="progress-wrap">
                    <div class="progress-title">Progreso de carga · {pct * 100:.0f}%</div>
                    <div class="progress-track">
                      <div class="progress-fill" style="width:{pct * 100:.0f}%"></div>
                    </div>
                  </div>
                </div>""",
            unsafe_allow_html=True,
        )

    salida = ledger.copy()
    for m in MESES:
        salida[m] = salida["HORAS"] if m == cfg["mes_carga"] else 0.0
    # HORAS_META viaja para la validación; preparar_filas() no la usa
    return salida[dims + MESES + ["HORAS_META"]]


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
    st.dataframe(resumen, hide_index=True, width="stretch")
