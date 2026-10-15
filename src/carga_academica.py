"""
Carga académica: la registra la Dirección de Gestión Académica (DGA).

Dos pestañas:
  - registro: grilla editable con el formato de la hoja "Carga academica.xlsx"
    (semestre, centro de costo y horas de titulares, jefes de práctica y
    asistentes). Guarda en DATOS_ENTRADA y ejecuta sp_Valorizar_CargaAcademica_2027.
  - consulta: lo mismo, solo lectura, para los departamentos.

En DATOS_ENTRADA cada fila de la grilla se guarda como una fila por concepto
(horas en IMPORTE, semestre en MES), que es lo que lee el sp.
"""

import pandas as pd
import streamlit as st

from .config import CARGA_ACADEMICA, PRESUPUESTO

CA = CARGA_ACADEMICA
CONCEPTOS = list(CA["conceptos"])
COLS_GRILLA = ["MES", "CENTRO_COSTO"] + CONCEPTOS
COLS_DESTINO = ["PRESUPUESTO", "HOJA_ORIGEN", "ORIGEN", "CENTRO_COSTO", "CONCEPTO",
                "MES", "IMPORTE"]


def _a_ancho(largo: pd.DataFrame) -> pd.DataFrame:
    """Formato largo de DATOS_ENTRADA -> una fila por (semestre, CECO)."""
    if largo.empty:
        return pd.DataFrame(columns=COLS_GRILLA)
    ancho = largo.pivot_table(index=["MES", "CENTRO_COSTO"], columns="CONCEPTO",
                              values="IMPORTE", aggfunc="sum").reset_index()
    for c in CONCEPTOS:
        if c not in ancho:
            ancho[c] = float("nan")
    ancho = ancho[COLS_GRILLA].sort_values(["MES", "CENTRO_COSTO"])
    ancho.columns.name = None
    return ancho.reset_index(drop=True)


def _semilla(repo) -> tuple[pd.DataFrame, str]:
    """Lo ya guardado para 2027; si no hay nada, los mismos semestres y
    centros de costo de 2026 con las horas vacías, como punto de partida."""
    actual = _a_ancho(repo.carga_academica(actual=True))
    if not actual.empty:
        return actual, "Se muestra la carga académica 2027 guardada."
    previa = _a_ancho(repo.carga_academica(actual=False))
    if previa.empty:
        return pd.DataFrame(columns=COLS_GRILLA).astype(
            {c: "float64" for c in CONCEPTOS}), ""
    previa["MES"] = previa["MES"].str.replace("2026-", "2027-", regex=False)
    previa[CONCEPTOS] = float("nan")
    return previa, ("Aún no hay carga 2027: se precargaron los centros de costo de "
                    "2026 con las horas vacías.")


def _colcfg(ccos: pd.DataFrame, editable: bool) -> dict:
    cfg = {
        "MES": st.column_config.SelectboxColumn(
            "Semestre", options=CA["semestres"], required=True, disabled=not editable),
        "CENTRO_COSTO": st.column_config.SelectboxColumn(
            "Centro de costo", options=ccos["CODIGO_CECO"].tolist(), required=True,
            width="medium", disabled=not editable),
        "DESCRIPCION_CECO": st.column_config.TextColumn("Descripción", width="large"),
    }
    for c, etiqueta in CA["conceptos"].items():
        cfg[c] = st.column_config.NumberColumn(
            etiqueta, min_value=0.0, format="%.0f", disabled=not editable)
    return cfg


def _validar(df: pd.DataFrame, ccos_validos: set) -> list[str]:
    errores = []
    valores = df[CONCEPTOS].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    con_datos = df[valores.sum(axis=1) > 0]
    if con_datos.empty:
        return ["Ingresa horas en al menos un centro de costo antes de guardar."]
    if (valores < 0).any().any():
        errores.append("Hay horas negativas.")
    if con_datos["MES"].isna().any() or not con_datos["MES"].isin(CA["semestres"]).all():
        errores.append("Hay filas con horas sin semestre válido (2027-1 o 2027-2).")
    if con_datos["CENTRO_COSTO"].isna().any():
        errores.append("Hay filas con horas sin centro de costo.")
    fuera = set(con_datos["CENTRO_COSTO"].dropna()) - ccos_validos
    if fuera:
        errores.append("Centros de costo que no están en el catálogo: "
                       + ", ".join(sorted(fuera)))
    dup = con_datos[con_datos.duplicated(["MES", "CENTRO_COSTO"], keep=False)]
    if not dup.empty:
        pares = sorted({f"{m} · {c}" for m, c in zip(dup["MES"], dup["CENTRO_COSTO"])})
        errores.append("Centro de costo repetido en el mismo semestre: " + ", ".join(pares))
    return errores


def _filas_destino(df: pd.DataFrame) -> list[list]:
    largo = df.melt(id_vars=["MES", "CENTRO_COSTO"], value_vars=CONCEPTOS,
                    var_name="CONCEPTO", value_name="IMPORTE")
    largo["IMPORTE"] = pd.to_numeric(largo["IMPORTE"], errors="coerce").fillna(0.0)
    largo = largo[largo["IMPORTE"] > 0]
    return [[PRESUPUESTO, CA["hoja"], CA["origen"], r.CENTRO_COSTO, r.CONCEPTO,
             r.MES, float(r.IMPORTE)] for r in largo.itertuples(index=False)]


def _totales(df: pd.DataFrame) -> pd.DataFrame:
    tot = df.copy()
    tot[CONCEPTOS] = tot[CONCEPTOS].apply(pd.to_numeric, errors="coerce").fillna(0.0)
    tot = tot.groupby("MES")[CONCEPTOS].sum().reset_index()
    return tot.rename(columns={"MES": "Semestre", **CA["conceptos"]})


def registro_carga_academica(repo):
    st.caption("Para la Dirección de Gestión Académica. Registra, por semestre y "
               "centro de costo, las horas de titulares, jefes de práctica y "
               "asistentes, como en la hoja Carga académica. Al guardar se "
               "reemplaza la carga 2027 anterior y se valoriza.")
    resultado = st.session_state.pop("_resultado_carga_academica", None)
    if resultado:
        ok, mensaje = resultado
        (st.success if ok else st.error)(mensaje, icon="✅" if ok else "🛑")

    ccos = repo.todos_centros_costo()
    if "_base_carga_academica" not in st.session_state:
        st.session_state["_base_carga_academica"], aviso = _semilla(repo)
        st.session_state["_aviso_carga_academica"] = aviso
    if st.session_state.get("_aviso_carga_academica"):
        st.info(st.session_state["_aviso_carga_academica"], icon="ℹ️")

    editado = st.data_editor(
        st.session_state["_base_carga_academica"], num_rows="dynamic", hide_index=True,
        width="stretch", column_order=COLS_GRILLA, column_config=_colcfg(ccos, True),
        key=f"grilla_carga_academica_{st.session_state.get('_ver_carga_academica', 0)}")

    st.dataframe(_totales(editado), hide_index=True, width="stretch")

    if st.button("Guardar carga académica", type="primary", width="stretch",
                 key="btn_guardar_carga_academica"):
        errores = _validar(editado, set(ccos["CODIGO_CECO"]))
        if errores:
            _dialogo_errores(errores)
        else:
            _dialogo_confirmar(repo, editado)


@st.dialog("Revisa antes de guardar", width="large")
def _dialogo_errores(errores):
    for e in errores:
        st.error(e, icon="⚠️")
    if st.button("Volver", type="primary", width="stretch"):
        st.rerun()


@st.dialog("Confirmar carga académica", width="large")
def _dialogo_confirmar(repo, editado):
    filas = _filas_destino(editado)
    st.write(f"Se guardarán **{len(filas)}** registro(s) para la carga académica "
             f"{PRESUPUESTO}.")
    st.dataframe(_totales(editado), hide_index=True, width="stretch")
    st.caption("Se reemplaza la carga académica 2027 anterior y se ejecuta la "
               "valorización. Las horas de dictado de los planes TC se descuentan "
               "de las horas de titulares.")
    c1, c2 = st.columns(2)
    if c1.button("Confirmar y valorizar", type="primary", width="stretch"):
        with st.spinner("Guardando y valorizando…"):
            try:
                if repo.modo == "sql":
                    n = repo.guardar(CA["hoja"], CA["origen"], filas, COLS_DESTINO, CA["sps"])
                else:
                    n = repo.guardar(CA["hoja"], CA["origen"], filas)
                repo.limpiar_cache()
                resultado = (True, f"{n} registro(s) de carga académica cargados y valorizados.")
                # La grilla se vuelve a leer de la base en el próximo render
                st.session_state.pop("_base_carga_academica", None)
                st.session_state["_ver_carga_academica"] = \
                    st.session_state.get("_ver_carga_academica", 0) + 1
            except Exception as ex:
                resultado = (False, "No se guardó nada; se revirtió la operación. "
                                    f"Detalle: {ex}")
        st.session_state["_resultado_carga_academica"] = resultado
        st.rerun()
    if c2.button("Cancelar", width="stretch"):
        st.rerun()


def consulta_carga_academica(repo):
    st.caption("Carga académica 2027 registrada por la Dirección de Gestión "
               "Académica. Solo lectura.")
    datos = _a_ancho(repo.carga_academica(actual=True))
    if datos.empty:
        st.info("La Dirección de Gestión Académica aún no ha registrado la carga "
                "académica 2027.", icon="ℹ️")
        return
    desc = dict(zip(*repo.todos_centros_costo()[["CODIGO_CECO", "DESCRIPCION_CECO"]]
                    .T.values))
    datos.insert(2, "DESCRIPCION_CECO", datos["CENTRO_COSTO"].map(desc))

    semestre = st.segmented_control("Semestre", ["Todos"] + CA["semestres"],
                                    default="Todos", key="semestre_consulta_ca") or "Todos"
    if semestre != "Todos":
        datos = datos[datos["MES"] == semestre]
    st.dataframe(datos, hide_index=True, width="stretch",
                 column_config=_colcfg(repo.todos_centros_costo(), False))
    st.dataframe(_totales(datos), hide_index=True, width="stretch")
