"""
Presupuesto de planillas 2026 — aplicación de entrada.

Reemplaza el formato Excel con macros por un motor único guiado por
configuración (src/config.py). Corre en modo demostración sin base de datos;
al configurar secrets['sql'] pasa a producción sobre Azure SQL sin cambiar
la interfaz.

    streamlit run app.py
"""

import streamlit as st

from src.carga_academica import consulta_carga_academica, registro_carga_academica
from src.config import cfg_de
from src.repositorio import crear_repositorio, preparar_filas
from src.validacion import conteo, estimar_importe, total_horas, validar
from src.vistas import (TC_HOJAS, ficha_docente, grilla, hero,
                        inyectar_estilos, resumen_por_ceco, selector_contexto)


def main():
    st.set_page_config(page_title="Presupuesto de planillas 2026",
                       page_icon="📋", layout="wide")
    inyectar_estilos()

    repo = crear_repositorio()

    st.title("Presupuesto de planillas 2026")
    if repo.modo == "demo":
        st.info("Modo demostración: los datos son de ejemplo y no se guardan en "
                "ninguna base. Para conectar Azure SQL, configura los secrets.",
                icon="🧪")

    tab_deptos, tab_registro, tab_consulta = st.tabs([
        "Presupuesto por departamento",
        "Carga académica · registro (DGA)",
        "Carga académica · consulta",
    ])
    with tab_deptos:
        vista_departamentos(repo)
    with tab_registro:
        registro_carga_academica(repo)
    with tab_consulta:
        consulta_carga_academica(repo)


def vista_departamentos(repo):
    origen, seleccion = selector_contexto(repo)
    ccos = repo.centros_costo(origen)
    if ccos.empty:
        st.warning(f"El departamento {origen} no tiene centros de costo cargados. "
                   "Cárgalos en el catálogo antes de presupuestar.", icon="⚠️")
        return

    if seleccion == "TC":
        st.caption(cfg_de(TC_HOJAS[0])["ayuda"])
        roster = repo.roster(origen)
        estructura = repo.estructura_tc(origen)
        pestañas = st.tabs(["I semestre (Ene-Jun)", "II semestre (Jul-Dic)"])
        for hoja, tab in zip(TC_HOJAS, pestañas):
            with tab:
                renderizar_planilla(repo, hoja, ccos, roster, estructura, {}, origen)
        return

    cfg = cfg_de(seleccion)
    st.caption(cfg["ayuda"])
    roster = repo.roster(origen) if cfg["usa_roster"] else roster_vacio()
    tarifas = repo.tarifas(seleccion) if cfg["tarifa"] == "catalogo" else {}
    renderizar_planilla(repo, seleccion, ccos, roster, None, tarifas, origen)


def renderizar_planilla(repo, hoja, ccos, roster, estructura, tarifas, origen):
    """Ficha o grilla + feedback en vivo + guardado con confirmación, para
    una sola hoja. Aislado en una función porque la vista TC lo invoca una
    vez por pestaña de semestre; las claves de session_state y de widgets
    usan `hoja` para no chocar entre pestañas que corren en el mismo rerun."""
    cfg = cfg_de(hoja)
    if cfg["usa_roster"]:
        _renderizar_ficha_tc(repo, hoja, cfg, ccos, roster, estructura, tarifas, origen)
    else:
        _renderizar_grilla(repo, hoja, cfg, ccos, roster, tarifas, origen)


def _renderizar_ficha_tc(repo, hoja, cfg, ccos, roster, estructura, tarifas, origen):
    """Vista maestro-detalle de la ficha TC: resumen de docentes/horas arriba
    (lo pinta ficha_docente con un placeholder propio), y guardado con
    confirmación en una barra inferior sticky."""
    # Resultado del último guardado (el diálogo se cierra con un rerun)
    resultado = st.session_state.pop(f"_resultado_{hoja}", None)
    if resultado:
        ok, mensaje = resultado
        (st.success if ok else st.error)(mensaje, icon="✅" if ok else "🛑")

    editado = ficha_docente(cfg, ccos, estructura, roster, origen)

    # La estructura TC puede traer CECOs de otros departamentos (docentes
    # transversales); son válidos porque vienen del catálogo, no del usuario.
    ccos_validos = set(ccos["CODIGO_CECO"]) | set(estructura["CODIGO_CECO"])
    st.markdown('<div style="height:60px"></div>', unsafe_allow_html=True)
    with st.container(key=f"barra_guardar_{hoja}"):
        c_info, c_btn = st.columns([3, 1])
        con_horas = editado.loc[editado[cfg["mes_carga"]] > 0, "DNI"].nunique()
        c_info.markdown(
            f'<div class="bottom-info">{cfg["etiqueta"]} · '
            f'{con_horas} de {editado["DNI"].nunique()} docente(s) con horas</div>',
            unsafe_allow_html=True)
        clic_guardar = c_btn.button("Guardar cambios", type="primary",
                                    width="stretch", key=f"btn_guardar_{hoja}")
    if clic_guardar:
        # Diálogo emergente para errores y confirmación: quedan a la vista,
        # no al final de la página detrás de la barra fija.
        errores = validar(hoja, editado, ccos_validos, tarifas)
        invalidos = st.session_state.get(f"_invalidos_{hoja}") or []
        if invalidos:
            errores.insert(0, "Hay horas mal escritas (usa hh:mm, por ejemplo 03:30) en: "
                           + ", ".join(invalidos) + ".")
        if errores:
            _dialogo_errores(errores)
        else:
            _dialogo_confirmar(repo, hoja, origen, editado)


@st.dialog("Revisa antes de guardar", width="large")
def _dialogo_errores(errores):
    for e in errores:
        st.error(e, icon="⚠️")
    if st.button("Volver a la ficha", type="primary", width="stretch"):
        st.rerun()


@st.dialog("Confirmar carga", width="large")
def _dialogo_confirmar(repo, hoja, origen, editado):
    cfg = cfg_de(hoja)
    st.write(f"Planilla **{cfg['etiqueta']}** · Departamento **{origen}**")
    sin_horas = editado["DNI"].nunique() - editado.loc[
        editado[cfg["mes_carga"]] > 0, "DNI"].nunique()
    if sin_horas:
        st.warning(f"{sin_horas} docente(s) sin horas no se incluirán en la carga.",
                   icon="ℹ️")
    resumen_por_ceco(hoja, editado)
    st.caption("Al confirmar se reemplaza la carga anterior de esta "
               "planilla para este departamento y se ejecuta la valorización.")
    c1, c2 = st.columns(2)
    if c1.button("Confirmar y valorizar", type="primary", width="stretch"):
        with st.spinner("Guardando y valorizando…"):
            st.session_state[f"_resultado_{hoja}"] = guardar(repo, hoja, origen, editado)
        st.rerun()
    if c2.button("Cancelar", width="stretch"):
        st.rerun()


def _renderizar_grilla(repo, hoja, cfg, ccos, roster, tarifas, origen):
    """Flujo original (grilla matricial + feedback + guardado), sin cambios,
    para las planillas que no usan la ficha por docente."""
    editado = grilla(cfg, ccos, roster, tarifas, origen)

    # feedback en vivo
    total = estimar_importe(hoja, editado, tarifas)
    horas = total_horas(hoja, editado)
    lineas, registros = conteo(editado)
    hero(hoja, total, horas, lineas, registros)

    # guardado con confirmación
    st.divider()
    listo_key = f"_listo_{hoja}"
    ccos_validos = set(ccos["CODIGO_CECO"])
    if st.button("Revisar y guardar", type="primary", width="stretch",
                key=f"btn_guardar_{hoja}"):
        errores = validar(hoja, editado, ccos_validos, tarifas)
        if errores:
            for e in errores:
                st.error(e, icon="⚠️")
            return
        st.session_state[listo_key] = True

    if st.session_state.get(listo_key):
        with st.container(border=True):
            st.subheader("Confirmar carga")
            st.write(f"Planilla **{cfg['etiqueta']}** · Departamento **{origen}**")
            resumen_por_ceco(hoja, editado)
            st.caption("Al confirmar se reemplaza la carga anterior de esta "
                       "planilla para este departamento y se ejecuta la valorización.")
            c1, c2 = st.columns(2)
            if c1.button("Confirmar y valorizar", type="primary",
                         width="stretch", key=f"btn_conf_{hoja}"):
                ok, mensaje = guardar(repo, hoja, origen, editado)
                (st.success if ok else st.error)(mensaje, icon="✅" if ok else "🛑")
                st.session_state[listo_key] = False
            if c2.button("Cancelar", width="stretch",
                         key=f"btn_cancel_{hoja}"):
                st.session_state[listo_key] = False
                st.rerun()


def guardar(repo, hoja, origen, editado):
    """Guarda y valoriza. Devuelve (ok, mensaje) para que quien llama decida
    dónde mostrarlo (la ficha TC lo muestra después de cerrar el diálogo)."""
    cfg = cfg_de(hoja)
    filas, cols = preparar_filas(hoja, origen, editado, repo)
    try:
        if repo.modo == "sql":
            n = repo.guardar(hoja, origen, filas, cols, cfg["sps"])
        else:
            n = repo.guardar(hoja, origen, filas)
        # La consulta de carga académica muestra las horas TC recién guardadas
        repo.limpiar_cache()
        return True, (f"{n} registro(s) cargado(s) y valorizado(s) para "
                      f"{cfg['etiqueta']} en {origen}.")
    except Exception as ex:
        return False, f"No se guardó nada; se revirtió la operación. Detalle: {ex}"


def roster_vacio():
    import pandas as pd
    return pd.DataFrame(columns=["DNI", "NOMBRE"])


if __name__ == "__main__":
    main()
