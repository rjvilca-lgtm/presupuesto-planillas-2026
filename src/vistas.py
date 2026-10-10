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

from .config import MESES, MESES_ABBR, SEMESTRES, cfg_de, dims_fila
from .validacion import formato_soles


CSS = """
<style>
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
                   letter-spacing: .3px; padding: .5rem .2rem .4rem; }

  div[class*="st-key-docitem_"] { margin: 0; border-bottom: 1px solid #F0F2F6; }
  div[class*="st-key-docitem_"] button { justify-content: flex-start !important;
                                          text-align: left !important;
                                          font-weight: 400; border-radius: 8px; }
  div[class*="st-key-docitem_"] button[kind="secondary"] {
      background: transparent; border-color: transparent; }
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

  div[class*="st-key-ceco_"] { padding: 0; margin-bottom: .8rem; }
  .ceco-card-header { font-size: .68rem; font-weight: 800; letter-spacing: .3px;
                      text-transform: uppercase; color: #B35B18; margin-bottom: .3rem; }
  .ceco-card-header .codigo-ceco { color: #9BA3B1; font-weight: 500;
                                   text-transform: none; margin-left: .35rem; }

  .actividad-label { font-size: .82rem; color: #344054; padding-top: .5rem; }

  div[data-testid="stNumberInput"] { max-width: 150px; }
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


TC_HOJAS = ["1. Plan TC-I", "Plan TC-II"]


def selector_contexto(repo):
    """Departamento y planilla. En producción el departamento debe venir del
    usuario autenticado (SSO); aquí es un selector para la demostración.
    Las dos hojas TC (I y II semestre) se presentan como una sola opción
    "Plan de trabajo TC": app.py arma las pestañas por semestre a partir de
    TC_HOJAS. Las demás planillas siguen igual, una por una."""
    from .config import PLANILLAS
    deptos = repo.departamentos()
    opciones = ["TC"] + [h for h in PLANILLAS if h not in TC_HOJAS]
    etiquetas = {"TC": "Plan de trabajo TC",
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


def _semestre_activo(hoja: str) -> str:
    """Selector de semestre: reduce a 6 las columnas de mes visibles.
    Los 6 meses del semestre oculto se conservan aparte (ver grilla())
    para que el guardado siga derritiendo los 12 meses."""
    opciones = list(SEMESTRES)
    key = f"semestre_{hoja}"
    if hasattr(st, "segmented_control"):
        return st.segmented_control(
            "Semestre", opciones, default=opciones[0], key=key) or opciones[0]
    return st.radio("Semestre", opciones, horizontal=True, key=key)


def _fusionar_semestre(dims: list[str], meses_ocultos: list[str],
                        estado_previo: pd.DataFrame,
                        editado_vista: pd.DataFrame) -> pd.DataFrame:
    """Recompone el DataFrame de 12 meses tras editar solo 6.
    Empareja filas por sus dimensiones (identifican el registro, ver
    config.py) para recuperar los meses del semestre oculto; filas nuevas
    quedan en NaN en el semestre oculto (nada que perder todavía) y filas
    eliminadas en la vista se eliminan también del otro semestre."""
    otros = estado_previo[dims + meses_ocultos] if not estado_previo.empty \
        else pd.DataFrame(columns=dims + meses_ocultos)
    fusion = editado_vista.merge(otros, on=dims, how="left")
    for m in meses_ocultos:
        if m not in fusion.columns:
            fusion[m] = pd.Series(dtype="float64")
    return fusion[dims + MESES]


def grilla(cfg: dict, ccos: pd.DataFrame, roster: pd.DataFrame,
           tarifas: dict, origen: str) -> pd.DataFrame:
    """data_editor matricial: dimensiones a la izquierda, 12 meses a la derecha
    (solo se muestran los 6 del semestre elegido para reducir el scroll).
    El DataFrame completo de 12 meses se mantiene en session_state, así que
    cambiar de semestre no descarta lo tecleado en el otro."""
    ccos_opts = ccos["CODIGO_CECO"].tolist()
    dims = dims_fila(cfg)
    metrica = cfg["metrica"]
    unidad = "horas" if metrica == "HORAS" else "importe (S/)"
    semestre = _semestre_activo(cfg["_hoja"])
    meses_visibles = SEMESTRES[semestre]
    meses_ocultos = [m for m in MESES if m not in meses_visibles]

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
               "Puedes pegar un bloque de celdas copiado desde Excel. "
               "Los datos del otro semestre no se pierden al cambiar de vista.")

    estado_key = f"_estado_{cfg['_hoja']}_{origen}"
    if estado_key not in st.session_state:
        st.session_state[estado_key] = _semilla(cfg, roster)
    estado_previo = st.session_state[estado_key]

    vista_cols = dims + meses_visibles
    vista = estado_previo[vista_cols].copy()
    editado_vista = st.data_editor(
        vista, num_rows="dynamic", use_container_width=True, hide_index=True,
        column_config={k: colcfg[k] for k in vista_cols if k in colcfg},
        key=f"grilla_{cfg['_hoja']}_{semestre}",
    )

    editado = _fusionar_semestre(dims, meses_ocultos, estado_previo, editado_vista)
    st.session_state[estado_key] = editado

    with st.expander("Ver descripción de los centros de costo"):
        st.dataframe(ccos.rename(columns={"CODIGO_CECO": "Código",
                                          "DESCRIPCION_CECO": "Descripción"}),
                     hide_index=True, use_container_width=True)
    return editado


def _semilla_ficha(roster: pd.DataFrame, estructura: pd.DataFrame) -> pd.DataFrame:
    """Ledger inicial de la ficha: una fila por (docente, CECO, concepto),
    con HORAS=0. Cruce del padrón con la estructura CECO->concepto."""
    if roster.empty or estructura.empty:
        return pd.DataFrame(columns=["DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "HORAS"])
    cruce = roster.merge(estructura, how="cross")
    cruce = cruce.rename(columns={"CODIGO_CECO": "CENTRO_COSTO"})
    cruce["HORAS"] = 0.0
    return cruce[["DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "HORAS"]]


def ficha_docente(cfg: dict, ccos: pd.DataFrame, estructura: pd.DataFrame,
                   roster: pd.DataFrame, origen: str) -> pd.DataFrame:
    """Ficha por docente para las planillas TC: un valor de horas por
    (CECO, concepto), por semestre (no por mes). Devuelve un DataFrame con
    la misma forma que grilla() (dims_fila(cfg) + MESES) para que
    preparar_filas() no cambie: el valor único se replica en los 6 meses
    del semestre de cfg["semestre"] y queda en 0 en el otro semestre.

    Layout maestro-detalle: lista de docentes a la izquierda, ficha del
    docente activo (centros de costo en grilla de 2 columnas) a la derecha.
    El docente activo se guarda en session_state para sobrevivir el rerun
    que dispara cada clic de la lista. El resumen superior y el total por
    docente se llenan al final mediante placeholders (st.empty), para
    reflejar lo recién tecleado en este mismo rerun."""
    dims = dims_fila(cfg)
    desc_ceco = dict(zip(ccos["CODIGO_CECO"], ccos["DESCRIPCION_CECO"]))

    estado_key = f"_ficha_{cfg['_hoja']}_{origen}"
    if estado_key not in st.session_state:
        st.session_state[estado_key] = _semilla_ficha(roster, estructura)
    ledger = st.session_state[estado_key]

    if ledger.empty:
        st.warning("No hay padrón de docentes ni estructura de CECO/conceptos "
                   "para este departamento.", icon="⚠️")
        return pd.DataFrame(columns=dims + MESES)

    docentes = ledger[["DNI", "NOMBRE"]].drop_duplicates().reset_index(drop=True)
    resumen_slot = st.empty()

    activo_key = f"_docente_activo_{estado_key}"
    if st.session_state.get(activo_key) not in set(docentes["DNI"]):
        st.session_state[activo_key] = docentes["DNI"].iloc[0]
    dni_sel = st.session_state[activo_key]

    col_lista, col_detalle = st.columns([1, 2], gap="medium")

    with col_lista:
        with st.container(key=f"people_card_{estado_key}"):
            st.markdown('<div class="people-header">DOCENTES</div>',
                       unsafe_allow_html=True)
            # Placeholder: las horas por docente de esta lista solo reflejan lo
            # recién tecleado si se llenan después de recorrer los number_input
            # del docente activo más abajo (mismo motivo que resumen_slot).
            lista_slot = st.empty()

            with st.expander("➕ Agregar docente fuera del padrón"):
                st.caption("Usa esto solo si el docente no aparece en el padrón "
                           "del departamento; es una excepción, no el flujo normal.")
                c1, c2 = st.columns(2)
                nuevo_dni = c1.text_input("DNI", key=f"nuevo_dni_{estado_key}")
                nuevo_nombre = c2.text_input("Nombre completo",
                                             key=f"nuevo_nombre_{estado_key}")
                if st.button("Agregar docente", key=f"btn_agregar_{estado_key}"):
                    dni_limpio = nuevo_dni.strip()
                    if not dni_limpio or not nuevo_nombre.strip():
                        st.error("Ingresa DNI y nombre para agregar al docente.",
                                icon="⚠️")
                    elif dni_limpio in set(ledger["DNI"]):
                        st.error("Ese DNI ya está en la ficha.", icon="⚠️")
                    else:
                        nuevo = estructura.copy()
                        nuevo = nuevo.rename(columns={"CODIGO_CECO": "CENTRO_COSTO"})
                        nuevo["DNI"] = dni_limpio
                        nuevo["NOMBRE"] = nuevo_nombre.strip()
                        nuevo["HORAS"] = 0.0
                        nuevo = nuevo[["DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "HORAS"]]
                        st.session_state[estado_key] = pd.concat(
                            [ledger, nuevo], ignore_index=True)
                        st.rerun()

    def _pintar_lista(horas_por_docente):
        for _, fila_doc in docentes.iterrows():
            dni_d, nombre_d = fila_doc["DNI"], fila_doc["NOMBRE"]
            h = horas_por_docente.get(dni_d, 0.0)
            activo = dni_d == st.session_state[activo_key]
            with st.container(key=f"docitem_{estado_key}_{dni_d}"):
                if st.button(f"{nombre_d}  \nDNI {dni_d} · {h:,.1f} h",
                            key=f"docsel_{estado_key}_{dni_d}",
                            use_container_width=True,
                            type="primary" if activo else "secondary"):
                    st.session_state[activo_key] = dni_d
                    st.rerun()

    with col_detalle:
        # Placeholder: nombre + total de horas se pintan juntos al final,
        # cuando ya se conoce el total tras recorrer los number_input.
        detalle_head_slot = st.empty()

        sub = ledger[ledger["DNI"] == dni_sel]
        total_docente = 0.0
        cecos_docente = list(sub.groupby("CENTRO_COSTO", sort=False))

        def _tarjeta_ceco(ceco, grupo):
            nonlocal total_docente
            with st.container(border=True, key=f"ceco_{estado_key}_{dni_sel}_{ceco}"):
                st.markdown(
                    f'<div class="ceco-card-header">{desc_ceco.get(ceco, ceco)}'
                    f'<span class="codigo-ceco">{ceco}</span></div>',
                    unsafe_allow_html=True,
                )
                for idx, fila in grupo.iterrows():
                    c_label, c_input = st.columns([3, 2])
                    c_label.markdown(
                        f'<div class="actividad-label">{fila["CONCEPTO"]}</div>',
                        unsafe_allow_html=True)
                    key = f"h_{estado_key}_{dni_sel}_{ceco}_{fila['CONCEPTO']}"
                    valor = c_input.number_input(
                        fila["CONCEPTO"], min_value=0.0, value=float(fila["HORAS"]),
                        step=0.5, format="%.1f", key=key, label_visibility="collapsed")
                    ledger.loc[idx, "HORAS"] = valor
                    total_docente += valor

        for i in range(0, len(cecos_docente), 2):
            par = cecos_docente[i:i + 2]
            if len(par) == 2:
                cols = st.columns(2, gap="small")
                for col, (ceco, grupo) in zip(cols, par):
                    with col:
                        _tarjeta_ceco(ceco, grupo)
            else:
                ceco, grupo = par[0]
                _tarjeta_ceco(ceco, grupo)

        nombre_sel = docentes.loc[docentes["DNI"] == dni_sel, "NOMBRE"].iloc[0]
        with detalle_head_slot.container():
            st.markdown(
                f"""<div class="detail-head">
                      <div>
                        <div class="nombre">{nombre_sel}</div>
                        <div class="dni">DNI {dni_sel}</div>
                      </div>
                      <div class="total">
                        <div class="numero">{total_docente:,.1f}</div>
                        <div class="etiqueta">HORAS TOTALES</div>
                      </div>
                    </div>""",
                unsafe_allow_html=True,
            )

    with lista_slot.container():
        _pintar_lista(ledger.groupby("DNI")["HORAS"].sum())

    st.session_state[estado_key] = ledger

    horas_por_docente = ledger.groupby("DNI")["HORAS"].sum()
    con_horas = int((horas_por_docente > 0).sum())
    horas_total = float(ledger["HORAS"].sum())
    pct = (con_horas / len(docentes)) if len(docentes) else 0.0
    with resumen_slot.container():
        st.markdown(
            f"""<div class="resumen-tc">
                  <div class="metric">
                    <div class="value">{con_horas} / {len(docentes)}</div>
                    <div class="label">Docentes cargados</div>
                  </div>
                  <div class="metric">
                    <div class="value">{horas_total:,.1f} h</div>
                    <div class="label">Horas asignadas</div>
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

    meses_semestre = SEMESTRES[cfg["semestre"]]
    salida = ledger.copy()
    for m in MESES:
        salida[m] = salida["HORAS"] if m in meses_semestre else 0.0
    return salida[dims + MESES]


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
