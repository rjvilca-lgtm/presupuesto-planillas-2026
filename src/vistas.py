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
    del semestre de cfg["semestre"] y queda en 0 en el otro semestre."""
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
    # Placeholder: se llena al final, después de aplicar los number_input de
    # esta misma ejecución (si se calculara aquí, mostraría el avance de la
    # ejecución anterior en vez de reflejar lo recién tecleado).
    progreso_slot = st.empty()

    with st.expander("➕ Agregar docente fuera del padrón"):
        st.caption("Usa esto solo si el docente no aparece en el padrón del "
                   "departamento; es una excepción, no el flujo normal.")
        c1, c2 = st.columns(2)
        nuevo_dni = c1.text_input("DNI", key=f"nuevo_dni_{estado_key}")
        nuevo_nombre = c2.text_input("Nombre completo", key=f"nuevo_nombre_{estado_key}")
        if st.button("Agregar docente", key=f"btn_agregar_{estado_key}"):
            dni_limpio = nuevo_dni.strip()
            if not dni_limpio or not nuevo_nombre.strip():
                st.error("Ingresa DNI y nombre para agregar al docente.", icon="⚠️")
            elif dni_limpio in set(ledger["DNI"]):
                st.error("Ese DNI ya está en la ficha.", icon="⚠️")
            else:
                nuevo = estructura.copy()
                nuevo = nuevo.rename(columns={"CODIGO_CECO": "CENTRO_COSTO"})
                nuevo["DNI"] = dni_limpio
                nuevo["NOMBRE"] = nuevo_nombre.strip()
                nuevo["HORAS"] = 0.0
                nuevo = nuevo[["DNI", "NOMBRE", "CENTRO_COSTO", "CONCEPTO", "HORAS"]]
                st.session_state[estado_key] = pd.concat([ledger, nuevo], ignore_index=True)
                st.rerun()

    opciones = list(docentes["DNI"])
    etiquetas = dict(zip(docentes["DNI"], docentes["NOMBRE"]))
    dni_sel = st.selectbox("Docente", opciones,
                           format_func=lambda d: f"{d} · {etiquetas[d]}",
                           key=f"docente_sel_{estado_key}")

    sub = ledger[ledger["DNI"] == dni_sel]
    total_docente = 0.0
    for ceco, grupo in sub.groupby("CENTRO_COSTO", sort=False):
        st.markdown(f"**{ceco} · {desc_ceco.get(ceco, ceco)}**")
        for idx, fila in grupo.iterrows():
            key = f"h_{estado_key}_{dni_sel}_{ceco}_{fila['CONCEPTO']}"
            valor = st.number_input(fila["CONCEPTO"], min_value=0.0,
                                    value=float(fila["HORAS"]), step=0.5,
                                    format="%.1f", key=key)
            ledger.loc[idx, "HORAS"] = valor
            total_docente += valor

    st.metric("Total horas · semana (este docente)", f"{total_docente:,.1f}")
    st.session_state[estado_key] = ledger

    horas_por_docente = ledger.groupby("DNI")["HORAS"].sum()
    con_horas = int((horas_por_docente > 0).sum())
    progreso_slot.progress(
        con_horas / len(docentes) if len(docentes) else 0.0,
        text=f"{con_horas} de {len(docentes)} docentes con horas cargadas")

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
