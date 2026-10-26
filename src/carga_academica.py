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

from . import borrador
from .borrador import (autoguardar, firma, marcar_guardado, mostrar_indicador, pendiente,
                       toca_autoguardar)
from .config import CARGA_ACADEMICA, PRESUPUESTO
from .flujo import DGA, ahora, marcar, panel_flujo

CA = CARGA_ACADEMICA
CONCEPTOS = list(CA["conceptos"])
TITULARES = "# HORAS TITULARES"
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


def registro_carga_academica(repo, fl, usuario=None):
    st.caption("Para la Dirección de Gestión Académica. Registra, por semestre y "
               "centro de costo, las horas de titulares, jefes de práctica y "
               "asistentes, como en la hoja Carga académica. Puedes guardar las veces "
               "que quieras; la valorización se habilita cuando DHUM, DMAT y DCN cierren.")
    panel_flujo(fl)
    resultado = st.session_state.pop("_resultado_carga_academica", None)
    if resultado:
        ok, mensaje = resultado
        (st.success if ok else st.error)(mensaje, icon="✅" if ok else "🛑")

    bloqueado, motivo = fl.bloqueo(DGA)
    if bloqueado:
        st.warning(f"🔒 La carga académica está {motivo}")

    ccos = repo.todos_centros_costo()
    borrador.mostrar_conflicto(CA["hoja"], DGA, ["_base_carga_academica",
                                                 "_ultimo_carga_academica",
                                                 "_aviso_carga_academica"],
                               ("grilla_carga_academica_",))
    borrador.registrar_version(repo, CA["hoja"], DGA)
    if "_base_carga_academica" not in st.session_state:
        st.session_state["_base_carga_academica"], aviso = _semilla(repo)
        st.session_state["_aviso_carga_academica"] = aviso
    if st.session_state.get("_aviso_carga_academica"):
        st.info(st.session_state["_aviso_carga_academica"], icon="ℹ️")

    widget_key = f"grilla_carga_academica_{st.session_state.get('_ver_carga_academica', 0)}"
    if widget_key not in st.session_state and "_ultimo_carga_academica" in st.session_state:
        # Al volver a la pestaña el editor se crea de nuevo: arranca de lo último editado
        st.session_state["_base_carga_academica"] =             st.session_state["_ultimo_carga_academica"].reset_index(drop=True)
    editado = st.data_editor(
        st.session_state["_base_carga_academica"],
        num_rows="fixed" if bloqueado else "dynamic", disabled=bloqueado,
        hide_index=True, width="stretch", column_order=COLS_GRILLA,
        column_config=_colcfg(ccos, True), key=widget_key)
    st.session_state["_ultimo_carga_academica"] = editado

    clave, f_actual = "carga_academica", firma(editado, ["MES", "CENTRO_COSTO"], CONCEPTOS)
    hay_cambios = pendiente(clave, f_actual)

    def _guardar():
        from .repositorio import ConflictoGuardado
        versiones, clave_v = borrador.versiones(), f"{CA['hoja']}|{DGA}"
        try:
            n, _ = repo.guardar_borrador(
                CA["hoja"], DGA, _filas_destino(editado), COLS_DESTINO,
                email=getattr(usuario, "email", None), version=versiones.get(clave_v),
                al_confirmar=lambda v: versiones.__setitem__(clave_v, v))
            marcar(repo, DGA, FECHA_GUARDADO=ahora())
            return True, f"{n} registro(s) de carga académica guardados."
        except ConflictoGuardado as c:
            from .flujo import fmt
            mensaje = (f"No se guardó la carga académica: {c.email or 'otra persona'} la "
                       f"guardó el {fmt(c.fecha)} mientras la editabas. Recarga con lo último "
                       "guardado y vuelve a hacer tus cambios. El guardado automático queda "
                       "en pausa hasta que recargues.")
            borrador.marcar_conflicto(CA["hoja"], DGA, mensaje)
            return False, mensaje
        except Exception as ex:
            return False, f"No se guardó nada; se revirtió la operación. Detalle: {ex}"

    if hay_cambios and not bloqueado and toca_autoguardar(clave):
        autoguardar(clave, f_actual, _validar(editado, set(ccos["CODIGO_CECO"])), _guardar)
        hay_cambios = pendiente(clave, f_actual)

    st.dataframe(_totales(editado), hide_index=True, width="stretch")

    mostrar_indicador(clave, hay_cambios, bloqueado)
    c_guardar, c_valorizar = st.columns(2)
    if c_guardar.button("Guardar", type="primary", width="stretch", disabled=bloqueado,
                        key="btn_guardar_carga_academica"):
        errores = _validar(editado, set(ccos["CODIGO_CECO"]))
        if errores:
            _dialogo_errores(errores)
        else:
            with st.spinner("Guardando…"):
                res = _guardar()
            if res[0]:
                marcar_guardado(clave, f_actual)
            if res[0] or not borrador.hay_conflicto(CA["hoja"], DGA):
                st.session_state["_resultado_carga_academica"] = res
            st.rerun()

    # Sin las tablas del flujo no hay a quién esperar: se permite valorizar
    pendientes = fl.pendientes_carga() if fl.disponible else []
    if c_valorizar.button("Valorizar carga académica", width="stretch",
                          disabled=bool(pendientes) or bloqueado,
                          key="btn_valorizar_carga_academica"):
        _dialogo_valorizar(repo)
    if pendientes:
        c_valorizar.caption("Para valorizar faltan cerrar: " + ", ".join(pendientes) + ".")
    elif fl.cambios_sin_valorizar(DGA):
        c_valorizar.caption("Hay cambios guardados sin valorizar.")


@st.dialog("Revisa antes de guardar", width="large")
def _dialogo_errores(errores):
    for e in errores:
        st.error(e, icon="⚠️")
    if st.button("Volver", type="primary", width="stretch"):
        st.rerun()


@st.dialog("Valorizar carga académica", width="large")
def _dialogo_valorizar(repo):
    st.write("Se valoriza la carga académica **guardada** (si hiciste cambios, "
             "guárdalos primero). A las horas de titulares se les restan las horas "
             "académicas de dictado de los planes TC de todos los departamentos tal "
             "como están en este momento.")
    c1, c2 = st.columns(2)
    if c1.button("Valorizar", type="primary", width="stretch"):
        with st.spinner("Valorizando…"):
            try:
                repo.valorizar(DGA, CA["sps"])
                marcar(repo, DGA, FECHA_VALORIZACION=ahora())
                res = (True, "Carga académica valorizada.")
            except Exception as ex:
                res = (False, f"No se valorizó nada; se revirtió la operación. Detalle: {ex}")
        st.session_state["_resultado_carga_academica"] = res
        st.rerun()
    if c2.button("Cancelar", width="stretch"):
        st.rerun()


def consulta_carga_academica(repo, fl):
    st.caption("Carga académica 2027 registrada por la Dirección de Gestión "
               "Académica. Solo lectura.")
    panel_flujo(fl)
    datos = _a_ancho(repo.carga_academica(actual=True))
    if datos.empty:
        st.info("La Dirección de Gestión Académica aún no ha registrado la carga "
                "académica 2027.", icon="ℹ️")
        return
    desc = dict(zip(*repo.todos_centros_costo()[["CODIGO_CECO", "DESCRIPCION_CECO"]]
                    .T.values))
    datos.insert(2, "DESCRIPCION_CECO", datos["CENTRO_COSTO"].map(desc))

    # Horas de los docentes a tiempo completo (DTC) que el sp resta de las de
    # titulares: horas académicas de dictado de los planes TC, por CECO y semestre
    dtc = repo.horas_dtc()
    por_ceco = dtc.groupby(["MES", "CENTRO_COSTO"])["HORAS"].sum()
    titulares = pd.to_numeric(datos[TITULARES], errors="coerce").fillna(0.0)
    descuento = pd.Series([por_ceco.get((m, c), 0.0)
                           for m, c in zip(datos["MES"], datos["CENTRO_COSTO"])],
                          index=datos.index)
    datos.insert(datos.columns.get_loc(TITULARES) + 1, "HORAS_DTC", descuento)
    datos.insert(datos.columns.get_loc("HORAS_DTC") + 1, "TITULARES_NETAS",
                 (titulares - descuento).clip(lower=0))

    semestre = st.segmented_control("Semestre", ["Todos"] + CA["semestres"],
                                    default="Todos", key="semestre_consulta_ca") or "Todos"
    if semestre != "Todos":
        datos = datos[datos["MES"] == semestre]
        dtc = dtc[dtc["MES"] == semestre]

    colcfg = _colcfg(repo.todos_centros_costo(), False)
    colcfg["HORAS_DTC"] = st.column_config.NumberColumn(
        "− Horas DTC", format="%.2f",
        help="Horas académicas de dictado que los departamentos registraron en "
             "los planes TC 2027 para este centro de costo y semestre. Se restan "
             "de las horas de titulares al valorizar.")
    colcfg["TITULARES_NETAS"] = st.column_config.NumberColumn(
        "= Titulares a valorizar", format="%.2f",
        help="Horas de titulares menos horas DTC (nunca menor que 0). Es lo que "
             "se valoriza con la tarifa de titular.")
    st.dataframe(datos, hide_index=True, width="stretch", column_config=colcfg)

    resumen = datos.groupby("MES")[[TITULARES, "HORAS_DTC", "TITULARES_NETAS"]
                                   + CONCEPTOS[1:]].sum(numeric_only=True).reset_index()
    st.dataframe(resumen, hide_index=True, width="stretch", column_config={
        "MES": st.column_config.TextColumn("Semestre"),
        **{k: v for k, v in colcfg.items() if k in resumen.columns}})

    with st.expander("Detalle de horas DTC por docente"):
        if dtc.empty:
            st.caption("Aún no hay planes TC 2027 guardados con horas académicas de "
                       "dictado.")
        else:
            st.caption("Horas académicas de dictado de cada docente TC, tal como las "
                       "registró su departamento. Sirve para revisar de dónde sale "
                       "el descuento de cada centro de costo.")
            # Horas DTC en centros de costo que la DGA no registró: no descuentan nada
            sin_carga = set(zip(dtc["MES"], dtc["CENTRO_COSTO"])) - set(
                zip(datos["MES"], datos["CENTRO_COSTO"]))
            if sin_carga:
                st.warning("Hay horas DTC en centros de costo sin carga académica "
                           "registrada (no se descuentan de nada): "
                           + ", ".join(f"{m} · {c}" for m, c in sorted(sin_carga)),
                           icon="⚠️")
            st.dataframe(
                dtc.sort_values(["MES", "CENTRO_COSTO", "NOMBRE"]),
                hide_index=True, width="stretch", column_config={
                    "MES": st.column_config.TextColumn("Semestre"),
                    "CENTRO_COSTO": st.column_config.TextColumn("Centro de costo"),
                    "ORIGEN": st.column_config.TextColumn("Departamento"),
                    "NOMBRE": st.column_config.TextColumn("Docente"),
                    "HORAS": st.column_config.NumberColumn("Horas académicas",
                                                           format="%.2f")})
