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

import pandas as pd
import streamlit as st

from .config import MESES, MESES_ABBR, SEMESTRES, cfg_de, dims_fila
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

  div[class*="st-key-ceco_"] { padding: .7rem 1rem .4rem; margin-bottom: .2rem; }
  .ceco-card-header { display: flex; justify-content: space-between; align-items: baseline;
                      gap: 1rem; border-bottom: 1px solid #F0F2F6; padding-bottom: .4rem; }
  .ceco-card-header .titulo { font-size: .74rem; font-weight: 800; letter-spacing: .3px;
                              text-transform: uppercase; color: #B35B18; }
  .ceco-card-header .codigo-ceco { color: #9BA3B1; font-weight: 500;
                                   text-transform: none; margin-left: .35rem; }
  .ceco-card-header .subtotal { font-size: .78rem; color: #667085; white-space: nowrap; }
  .ceco-card-header .subtotal b { color: #17233B; }

  div[class*="st-key-ceco_"] div[data-testid="stNumberInput"] label p {
      font-size: .8rem; color: #344054; }
  div[class*="st-key-ceco_"] div[data-testid="stNumberInput"] { max-width: 230px; }
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
    Los 12 meses siguen en los datos del editor (ver grilla())."""
    opciones = list(SEMESTRES)
    key = f"semestre_{hoja}"
    if hasattr(st, "segmented_control"):
        return st.segmented_control(
            "Semestre", opciones, default=opciones[0], key=key) or opciones[0]
    return st.radio("Semestre", opciones, horizontal=True, key=key)


def grilla(cfg: dict, ccos: pd.DataFrame, roster: pd.DataFrame,
           tarifas: dict, origen: str) -> pd.DataFrame:
    """data_editor matricial: dimensiones a la izquierda, 12 meses a la derecha
    (solo se muestran los 6 del semestre elegido para reducir el scroll).

    El editor recibe siempre la MISMA base mientras se edita: con
    num_rows="dynamic" la identidad del widget depende de los datos, así que
    devolverle su propia salida lo reinicia y pierde ediciones. La base solo
    se renueva (con lo último editado) al cambiar de semestre. Los 12 meses
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

    base_key = f"_base_{hoja}_{origen}"
    ultimo_key = f"_ultimo_{hoja}_{origen}"
    sem_key = f"_sem_base_{hoja}_{origen}"
    if base_key not in st.session_state:
        st.session_state[base_key] = _semilla(cfg, roster)
        st.session_state[ultimo_key] = st.session_state[base_key]
        st.session_state[sem_key] = semestre
    elif st.session_state[sem_key] != semestre:
        st.session_state[base_key] = st.session_state[ultimo_key].reset_index(drop=True)
        st.session_state[sem_key] = semestre

    editado = st.data_editor(
        st.session_state[base_key], num_rows="dynamic", width="stretch",
        hide_index=True, column_order=dims + meses_visibles,
        column_config={k: v for k, v in colcfg.items() if k in dims + MESES},
        key=f"grilla_{hoja}_{origen}_{semestre}",
    )
    st.session_state[ultimo_key] = editado

    with st.expander("Ver descripción de los centros de costo"):
        st.dataframe(ccos.rename(columns={"CODIGO_CECO": "Código",
                                          "DESCRIPCION_CECO": "Descripción"}),
                     hide_index=True, width="stretch")
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
            # Placeholders: el encabezado (pendientes) y las horas por docente
            # solo reflejan lo recién tecleado si se llenan después de recorrer
            # los number_input del docente activo (mismo motivo que resumen_slot).
            cabecera_slot = st.empty()
            filtro = st.text_input(
                "Buscar docente", key=f"buscar_{estado_key}",
                placeholder="Buscar por nombre o DNI", label_visibility="collapsed")
            # Alto fijo con scroll propio: la lista no empuja la ficha hacia
            # abajo aunque el departamento tenga muchos docentes.
            with st.container(height=ALTO_PANEL - 90, border=False):
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
                        nuevo["HORAS"] = 0.0
                        nuevo = nuevo[["DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "HORAS"]]
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
            activo = dni_d == st.session_state[activo_key]
            with st.container(key=f"docitem_{estado_key}_{dni_d}"):
                st.button(f"**{nombre_d}**  \nDNI {dni_d} · {h:,.1f} h/mes",
                          key=f"docsel_{estado_key}_{dni_d}", width="stretch",
                          icon=":material/check_circle:" if h > 0
                          else ":material/radio_button_unchecked:",
                          type="primary" if activo else "secondary",
                          on_click=_elegir, args=(dni_d,))

    with col_detalle:
        # Placeholder: nombre + total de horas se pintan juntos al final,
        # cuando ya se conoce el total tras recorrer los number_input.
        detalle_head_slot = st.empty()

        sub = ledger[ledger["DNI"] == dni_sel]
        total_docente = 0.0

        def _tarjeta_ceco(ceco, grupo):
            """Un CECO a todo el ancho, con sus conceptos en filas de
            CAMPOS_POR_FILA campos: las tarjetas se alinean sin huecos."""
            nonlocal total_docente
            with st.container(border=True, key=f"ceco_{estado_key}_{dni_sel}_{ceco}"):
                cabecera = st.empty()
                subtotal = 0.0
                filas = list(grupo.iterrows())
                for i in range(0, len(filas), CAMPOS_POR_FILA):
                    cols = st.columns(CAMPOS_POR_FILA, gap="medium")
                    for col, (idx, fila) in zip(cols, filas[i:i + CAMPOS_POR_FILA]):
                        key = f"h_{estado_key}_{dni_sel}_{ceco}_{fila['CONCEPTO']}"
                        valor = col.number_input(
                            str(fila["CONCEPTO"]), min_value=0.0,
                            value=float(fila["HORAS"]), step=0.5, format="%.1f", key=key)
                        ledger.loc[idx, "HORAS"] = valor
                        subtotal += valor
                total_docente += subtotal
                cabecera.markdown(
                    f'<div class="ceco-card-header"><div class="titulo">'
                    f'{escape(str(desc_ceco.get(ceco, ceco)))}'
                    f'<span class="codigo-ceco">{escape(str(ceco))}</span></div>'
                    f'<div class="subtotal"><b>{subtotal:,.1f}</b> h/mes</div></div>',
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
        with detalle_head_slot.container():
            st.markdown(
                f"""<div class="detail-head">
                      <div>
                        <div class="nombre">{escape(str(nombre_sel))}</div>
                        <div class="dni">DNI {escape(str(dni_sel))}</div>
                      </div>
                      <div class="total">
                        <div class="numero">{total_docente:,.1f}</div>
                        <div class="etiqueta">HORAS / MES</div>
                      </div>
                    </div>""",
                unsafe_allow_html=True,
            )

    horas_lista = ledger.groupby("DNI")["HORAS"].sum()
    pendientes = int((horas_lista.reindex(docentes["DNI"]).fillna(0) <= 0).sum())
    extra = f'<span class="pendientes">{pendientes} sin horas</span>' if pendientes else ""
    cabecera_slot.markdown(
        f'<div class="people-header"><span>DOCENTES ({len(docentes)})</span>{extra}</div>',
        unsafe_allow_html=True)
    with lista_slot.container():
        _pintar_lista(horas_lista)

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
                    <div class="label">Horas por mes asignadas</div>
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
    st.dataframe(resumen, hide_index=True, width="stretch")
