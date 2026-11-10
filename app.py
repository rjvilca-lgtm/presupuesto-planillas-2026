"""
Presupuesto de planillas 2026 — aplicación de entrada.

Reemplaza el formato Excel con macros por un motor único guiado por
configuración (src/config.py). Corre en modo demostración sin base de datos;
al configurar secrets['sql'] pasa a producción sobre Azure SQL sin cambiar
la interfaz.

Flujo (ver src/flujo.py): cada planilla se guarda como borrador las veces que
se quiera; el departamento valoriza todo junto desde "Resumen y valorización".

    streamlit run app.py
"""

import sys
import time
from pathlib import Path

import pandas as pd
import streamlit as st


def _recargar_src_si_cambio():
    """Con fileWatcherType = "none" (.streamlit/config.toml), al hacer push
    Streamlit Cloud vuelve a ejecutar app.py pero deja en memoria los módulos
    de src/ anteriores: el app.py nuevo llamaba funciones que el src/ viejo no
    tenía (AttributeError). Si los archivos de src/ cambiaron desde que se
    importaron, se olvidan para que los imports de abajo carguen los nuevos.
    También se vacía st.cache_resource: guarda objetos de las clases viejas
    (el repositorio de crear_repositorio, sin los métodos nuevos)."""
    huella = tuple(sorted((p.name, p.stat().st_mtime_ns)
                          for p in (Path(__file__).parent / "src").glob("*.py")))
    src = sys.modules.get("src")
    if src is not None and getattr(src, "_huella", None) != huella:
        for nombre in [m for m in sys.modules if m == "src" or m.startswith("src.")]:
            del sys.modules[nombre]
        st.cache_resource.clear()
        print("[app] src/ cambió: se recargan sus módulos", flush=True)
    import src as nuevo
    nuevo._huella = huella


def _recargar_app_si_cambio():
    """Con fileWatcherType = "none", Streamlit guarda compilado el app.py y no
    se entera de que cambió con un push: seguía corriendo el app.py viejo con
    el src/ nuevo (pasó con el rol Postgrado: st.tabs([]) sin pestañas). Si el
    archivo cambió desde la última ejecución, se olvida lo compilado y se
    vuelve a ejecutar con el nuevo. Usa un atributo interno de Streamlit: si
    no existe (otra versión, AppTest), no hace nada."""
    try:
        from streamlit.runtime import Runtime
        rt = Runtime.instance()
        mtime = Path(__file__).stat().st_mtime_ns
        previa = getattr(rt, "_mtime_app_py", None)
        rt._mtime_app_py = mtime
        if previa is None or previa == mtime:
            return
        rt._script_cache.clear()
        print("[app] app.py cambió: se vuelve a compilar", flush=True)
    except Exception:
        return
    st.rerun()


_recargar_app_si_cambio()
_recargar_src_si_cambio()

from src.auth import barra_usuario, exigir_login
from src import borrador
from src.borrador import (aviso_al_salir, autoguardar, firma, marcar_guardado,
                          mostrar_indicador, indicador, pendiente, toca_autoguardar)
from src.diagnostico import iniciar_medicion, iniciar_vigilante, registrar, vista_diagnostico
from src.carga_academica import consulta_carga_academica, registro_carga_academica
from src.config import MESES, PUESTOS_NUEVOS, cfg_de, dims_fila, es_ceco_postgrado
from src.flujo import (aviso_departamento, leer_flujo, marcar, ahora, panel_flujo,
                       vista_admin, vista_resumen)
from src.reporte import vista_reporte
from src import plantilla_tc
from src.rrhh import vista_desarrollo_humano
from src.repositorio import ConflictoGuardado, crear_repositorio, preparar_filas
from src.validacion import conteo, contar_puestos, estimar_importe, total_horas, validar
from src.vistas import (TC_HOJAS, ficha_docente, grilla, hero,
                        inyectar_estilos, selector_contexto)


def main():
    """Mide cuánto tarda el servidor en cada ejecución (ver src/diagnostico.py)."""
    t0 = time.perf_counter()
    iniciar_vigilante()
    iniciar_medicion()
    contexto = {"pantalla": "Login", "email": "—"}
    try:
        _main(contexto)
    finally:
        registrar(contexto["pantalla"], contexto["email"], time.perf_counter() - t0)


def _main(contexto):
    st.set_page_config(page_title="Presupuesto de planillas 2026",
                       page_icon="📋", layout="wide")
    inyectar_estilos()

    repo = crear_repositorio()
    usuario = exigir_login(repo)
    contexto["email"] = usuario.email
    fl = leer_flujo(repo)

    barra_usuario(usuario)
    st.title("Presupuesto de planillas 2026")
    if repo.modo == "demo":
        st.info("Modo demostración: los datos son de ejemplo y no se guardan en "
                "ninguna base. Para conectar Azure SQL, configura los secrets.",
                icon="🧪")

    # Cada rol ve solo sus pestañas; la consulta de carga académica, todos
    pestañas = []
    if (usuario.presupuesto or usuario.departamentos or usuario.investigacion
            or usuario.postgrado):
        pestañas.append(("Presupuesto por departamento",
                         lambda: vista_departamentos(repo, fl, usuario)))
    if usuario.presupuesto or usuario.areas:
        pestañas.append(("Ayudantías · áreas", lambda: vista_areas(repo, fl, usuario)))
    if usuario.presupuesto or usuario.puestos:
        pestañas.append(("Puestos nuevos", lambda: vista_puestos(repo, fl, usuario)))
    if usuario.presupuesto or usuario.dga:
        pestañas.append(("Carga académica · registro (DGA)",
                         lambda: registro_carga_academica(repo, fl, usuario)))
    if usuario.rrhh:
        pestañas.append(("Desarrollo Humano",
                         lambda: vista_desarrollo_humano(repo, usuario, repo.departamentos())))
    if not usuario.solo_investigacion:   # el gestor de investigación solo registra
        pestañas.append(("Carga académica · consulta",
                         lambda: consulta_carga_academica(repo, fl)))
        pestañas.append(("Resumen de valorización",
                         lambda: vista_reporte(repo, fl, usuario, repo.departamentos())))
    if usuario.presupuesto:
        pestañas.append(("Presupuesto · administración",
                         lambda: vista_admin(repo, fl, repo.departamentos(), usuario,
                                             lambda: vista_diagnostico(repo))))
    # Solo se ejecuta la pestaña abierta: las demás no consultan la base ni
    # dibujan nada hasta que se abren (lo editado y no guardado sigue en la sesión)
    if not pestañas:   # un rol que esta versión no conoce: avisar, no romper
        st.warning("Tu acceso no tiene pantallas en esta versión de la app. Recarga la "
                   "página; si sigue igual, avisa a la Oficina de Presupuesto.", icon="⚠️")
        return
    tabs = st.tabs([t for t, _ in pestañas], on_change="rerun", key="nav_principal")
    for tab, (titulo, vista) in zip(tabs, pestañas):
        if tab.open:
            contexto["pantalla"] = titulo
            st.session_state.pop("_pantalla_detalle", None)
            with tab:
                vista()
            if st.session_state.get("_pantalla_detalle"):
                contexto["pantalla"] = f"{titulo} › {st.session_state['_pantalla_detalle']}"
    aviso_al_salir()


def vista_departamentos(repo, fl, usuario):
    # Presupuesto ve todos los departamentos; los demás, solo los suyos (el
    # gestor de investigación, solo la planilla de Investigación; el rol
    # Postgrado, la de Postgrado de todos, en solo lectura)
    permitidos = None if usuario.presupuesto or usuario.postgrado else list(
        dict.fromkeys(usuario.departamentos + usuario.investigacion))
    origen, seleccion = selector_contexto(repo, permitidos, usuario.planillas_de)
    st.session_state["_pantalla_detalle"] = f"{origen} · {seleccion}"
    if usuario.solo_ver(origen, seleccion):
        que = ("el Plan de trabajo TC (solo los centros de postgrado y los docentes con "
               "horas en ellos)" if seleccion == "TC" else "la planilla de Postgrado")
        st.info(f"Consultas {que} de {origen} en solo lectura. Lo registra y valoriza el "
                "departamento.", icon="🎓")
        solo_lectura = True
    else:
        panel_flujo(fl)
        solo_lectura = aviso_departamento(fl, origen)

    ccos = repo.centros_costo(origen)
    if ccos.empty:
        st.warning(f"El departamento {origen} no tiene centros de costo cargados. "
                   "Cárgalos en el catálogo antes de presupuestar.", icon="⚠️")
        return

    # Lo ya guardado del departamento: las planillas arrancan desde ahí
    entrada = repo.entrada(origen)

    if seleccion == "RESUMEN":
        vista_resumen(repo, fl, origen, ccos, repo.roster(origen), repo.estructura_tc(origen))
        return

    if seleccion == "TC":
        st.caption(cfg_de(TC_HOJAS[0])["ayuda"])
        roster = repo.roster(origen)
        estructura = repo.estructura_tc(origen)
        prelim = repo.horas_dictado_prelim(origen)
        if usuario.solo_ver(origen, "TC"):
            ccos, estructura, entrada, roster, prelim = _solo_postgrado(
                ccos, estructura, entrada, roster, prelim)
            if entrada[entrada["HOJA_ORIGEN"].isin(TC_HOJAS)].empty:
                st.info(f"{origen} aún no tiene horas del plan TC en centros de postgrado.",
                        icon="🎓")
                return
        pestañas = st.tabs(["I semestre (Ene-Jun)", "II semestre (Jul-Dic)"],
                           on_change="rerun", key=f"tabs_tc_{origen}")
        for hoja, tab in zip(TC_HOJAS, pestañas):
            if not tab.open:
                continue
            borrador.registrar_version(repo, hoja, origen)
            with tab:
                _renderizar_ficha_tc(repo, fl, hoja, ccos, roster, estructura, origen,
                                     entrada[entrada["HOJA_ORIGEN"] == hoja], solo_lectura,
                                     usuario, prelim[prelim["HOJA_ORIGEN"] == hoja])
        return

    cfg = cfg_de(seleccion)
    st.caption(cfg["ayuda"])
    if seleccion == INVESTIGACION:
        solo_lectura = _aviso_investigacion(repo, usuario, origen) or solo_lectura
    roster = repo.roster(origen) if cfg["usa_roster"] else roster_vacio()
    tarifas = repo.tarifas(seleccion) if cfg["tarifa"] == "catalogo" else {}
    borrador.registrar_version(repo, seleccion, origen)
    _renderizar_grilla(repo, fl, seleccion, cfg, ccos, roster, tarifas, origen,
                       entrada[entrada["HOJA_ORIGEN"] == seleccion], solo_lectura, usuario)


AYUDANTIAS = "Ayudantias"
INVESTIGACION = "Investigacion"


def _solo_postgrado(ccos, estructura, entrada, roster, prelim):
    """Plan TC para el rol Postgrado: solo los centros de postgrado y los
    docentes con horas guardadas en ellos (siempre en solo lectura)."""
    ccos = ccos[ccos["CODIGO_CECO"].map(es_ceco_postgrado)]
    estructura = estructura[estructura["CODIGO_CECO"].map(es_ceco_postgrado)]
    # Solo filas con horas: las de 0 harían aparecer docentes sin postgrado
    entrada = entrada[entrada["CENTRO_COSTO"].map(es_ceco_postgrado)
                      & (pd.to_numeric(entrada["HORAS"], errors="coerce").fillna(0) > 0)]
    con_horas = set(entrada["DNI"].astype(str).str.strip())
    roster = roster[roster["DNI"].astype(str).str.strip().isin(con_horas)]
    return ccos, estructura, entrada, roster, prelim.iloc[0:0]


def _aviso_investigacion(repo, usuario, origen) -> bool:
    """Planilla de Investigación (sql/crear_rol_investigacion.sql): la
    registran el gestor de investigación y el departamento (los dos pueden
    modificarla; el control de versiones evita pisarse). El departamento la
    valoriza desde Resumen. Devuelve si queda en solo lectura (hoy nunca)."""
    gestores = repo.gestores_investigacion(origen)
    ultimo = repo.ultimo_guardado(INVESTIGACION, origen)
    from src.flujo import fmt
    quien = (f" Último guardado: {ultimo[0] or '—'}, {fmt(ultimo[1])}." if ultimo else
             " Aún no la ha guardado.")
    if origen in usuario.investigacion and not usuario.presupuesto:
        st.info("Registras la planilla de Investigación de este departamento. Guarda las "
                "veces que quieras; el departamento la revisa y la valoriza." + quien,
                icon="🔬")
        return False
    if gestores:   # el departamento (y Presupuesto) también pueden modificarla
        st.info(f"La planilla de Investigación de {origen} también la registra el gestor "
                f"de investigación ({', '.join(gestores)}). Puedes revisarla y modificarla; "
                "si los dos la editan a la vez, el segundo en guardar recibe un aviso para "
                "recargar y no se pierde nada. Para valorizarla ve a «Resumen y "
                "valorización»." + quien, icon="🔬")
    return False


def vista_areas(repo, fl, usuario):
    """Ayudantías de las áreas no académicas (sql/crear_areas_2027.sql): la
    misma planilla que la de los departamentos, con los centros de costo de la
    dirección del área. Al guardar queda valorizada (es su única planilla)."""
    areas = repo.areas()
    if not usuario.presupuesto:
        areas = [a for a in areas if a[0] in set(usuario.areas)]
    if not areas:
        st.warning("Aún no hay áreas registradas. Ejecuta `sql/crear_areas_2027.sql` en "
                   "Azure.", icon="⚠️")
        return
    nombres = dict(areas)
    origen = st.selectbox("Área", list(nombres), key="area_ayudantias",
                          format_func=lambda a: f"{a} · {nombres[a]}")
    st.session_state["_pantalla_detalle"] = origen
    solo_lectura = aviso_departamento(fl, origen)

    ccos = repo.centros_costo_area(origen)
    if ccos.empty:
        st.warning(f"El área {origen} no tiene centros de costo 2027. Revisa su dirección "
                   "en AREAS_2027.", icon="⚠️")
        return
    cfg = cfg_de(AYUDANTIAS)
    st.caption(cfg["ayuda"] + " Al guardar, las ayudantías quedan valorizadas.")
    entrada = repo.entrada(origen)
    borrador.registrar_version(repo, AYUDANTIAS, origen)
    _renderizar_grilla(repo, fl, AYUDANTIAS, cfg, ccos, roster_vacio(),
                       repo.tarifas(AYUDANTIAS), origen,
                       entrada[entrada["HOJA_ORIGEN"] == AYUDANTIAS], solo_lectura, usuario,
                       sps=tuple(cfg["sps"]))


def vista_puestos(repo, fl, usuario):
    """Puestos nuevos y ascensos (formato de «Puestos nuevos.xlsx»): solo los
    usuarios con rol PUESTOS, por departamento o área (Presupuesto, todos). Usa
    la misma grilla que las demás planillas; el costo mensual de cada puesto
    sale de tarifas_2027 (sql/crear_puestos_nuevos_2027.sql)."""
    cfg = cfg_de(PUESTOS_NUEVOS)
    deptos, areas = dict(repo.departamentos()), dict(repo.areas())
    unidades = {**deptos, **areas}
    if not usuario.presupuesto:
        unidades = {c: n for c, n in unidades.items() if c in set(usuario.puestos)}
    if not unidades:
        st.info("No tienes departamentos ni áreas asignados para puestos nuevos.", icon="🔒")
        return
    origen = st.selectbox("Departamento o área", list(unidades), key="unidad_puestos",
                          format_func=lambda c: f"{c} · {unidades[c]}")
    st.session_state["_pantalla_detalle"] = origen
    st.caption(cfg["ayuda"])
    solo_lectura = aviso_departamento(fl, origen)
    ccos = repo.centros_costo(origen) if origen in deptos else repo.centros_costo_area(origen)
    if ccos.empty:
        st.warning(f"{origen} no tiene centros de costo 2027 asignados. Pídelo a la Oficina "
                   "de Presupuesto.", icon="⚠️")
        return
    tarifas = repo.tarifas(PUESTOS_NUEVOS)
    if not tarifas:
        st.warning("Aún no están cargados los costos de los puestos. La Oficina de "
                   "Presupuesto debe ejecutar `sql/crear_puestos_nuevos_2027.sql` y la "
                   "carga de costos en Azure.", icon="⚠️")
        return
    if usuario.presupuesto or usuario.rrhh:   # los montos son reservados
        _costos_puestos(tarifas)
    entrada = repo.entrada(origen)
    borrador.registrar_version(repo, PUESTOS_NUEVOS, origen)
    _renderizar_grilla(repo, fl, PUESTOS_NUEVOS, cfg, ccos, roster_vacio(), tarifas, origen,
                       entrada[entrada["HOJA_ORIGEN"] == PUESTOS_NUEVOS], solo_lectura, usuario)


def _costos_puestos(tarifas):
    with st.expander(f"💼 Costo mensual de cada puesto ({len(tarifas)}) · solo lo ven "
                     "Presupuesto y Desarrollo Humano"):
        st.caption("Sueldo, bonos, Edenred y cargas sociales de un mes. En un UPGRADE "
                   "(ascenso) es solo la diferencia de sueldo con el puesto anterior, más "
                   "sus cargas.")
        st.dataframe(pd.DataFrame(list(tarifas.items()), columns=["Puesto", "Costo mensual"]),
                     hide_index=True, width="stretch", column_config={
                         "Costo mensual": st.column_config.NumberColumn(format="S/ %,.2f")})
        st.caption("Desarrollo Humano los modifica en su pestaña › Tarifas.")


def _mostrar_resultado(hoja, flotante=False):
    """flotante: el éxito sale como aviso flotante (st.toast), sin empujar la
    pantalla; así se ve aunque se esté abajo en la ficha. Los errores se quedan
    también arriba, para leerlos con calma."""
    resultado = st.session_state.pop(f"_resultado_{hoja}", None)
    if resultado:
        ok, mensaje = resultado
        if flotante:
            st.toast(mensaje, icon="✅" if ok else "🛑")
            if ok:
                return
        (st.success if ok else st.error)(mensaje, icon="✅" if ok else "🛑")


@st.fragment
def _renderizar_ficha_tc(repo, fl, hoja, ccos, roster, estructura, origen, guardado,
                         solo_lectura, usuario, prelim=None):
    """Mide las ejecuciones solo de la ficha (cada tecla o Guardar), que no
    pasan por main(); en una ejecución completa ya la mide main()."""
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    ctx = get_script_run_ctx()
    if not (ctx and ctx.fragment_ids_this_run):
        return _ficha_tc(repo, fl, hoja, ccos, roster, estructura, origen, guardado,
                         solo_lectura, usuario, prelim)
    t0 = time.perf_counter()
    iniciar_medicion()
    try:
        return _ficha_tc(repo, fl, hoja, ccos, roster, estructura, origen, guardado,
                         solo_lectura, usuario, prelim)
    finally:
        registrar(f"Ficha TC (solo la ficha) › {origen} · {hoja}", usuario.email,
                  time.perf_counter() - t0)


def _ficha_tc(repo, fl, hoja, ccos, roster, estructura, origen, guardado,
              solo_lectura, usuario, prelim=None):
    """Ficha TC (maestro-detalle) con guardado de borrador en la barra fija.
    Es un fragmento: cada tecla o clic dentro de la ficha vuelve a dibujar solo
    la ficha, no la página entera (encabezado, flujo, consultas). Guardar
    también rehace solo la ficha: la pantalla se queda donde estaba, en el
    mismo docente. Agregar docente recarga toda la página."""
    cfg = cfg_de(hoja)
    _mostrar_resultado(hoja, flotante=True)
    estado_ficha = f"_ficha_{hoja}_{origen}"   # ver vistas.ficha_docente
    borrador.mostrar_conflicto(hoja, origen, [estado_ficha], (f"h_{estado_ficha}_",))
    zona_excel = st.container()   # arriba de la ficha; se llena cuando la ficha existe
    editado = ficha_docente(cfg, ccos, estructura, roster, origen, guardado, solo_lectura,
                            prelim)
    _excel_tc(zona_excel, hoja, origen, estado_ficha, ccos, estructura, solo_lectura)

    # La estructura TC puede traer CECOs de otros departamentos (docentes
    # transversales); son válidos porque vienen del catálogo, no del usuario.
    ccos_validos = set(ccos["CODIGO_CECO"]) | set(estructura["CODIGO_CECO"])
    clave, f_actual = f"{hoja}|{origen}", firma(editado, dims_fila(cfg), MESES)
    hay_cambios = pendiente(clave, f_actual)

    def _errores():
        errores = validar(hoja, editado, ccos_validos, {}, estricto=False)
        invalidos = st.session_state.get(f"_invalidos_{hoja}") or []
        if invalidos:
            errores.insert(0, "Hay horas mal escritas (usa hh:mm, por ejemplo 03:30) en: "
                           + ", ".join(invalidos) + ".")
        return errores

    if hay_cambios and not solo_lectura and toca_autoguardar(clave):
        autoguardar(clave, f_actual, _errores(),
                    lambda: guardar_borrador(repo, hoja, origen, editado, usuario.email,
                                             firma_actual=f_actual))
        hay_cambios = pendiente(clave, f_actual)
    st.markdown('<div style="height:60px"></div>', unsafe_allow_html=True)
    with st.container(key=f"barra_guardar_{hoja}"):
        c_info, c_btn = st.columns([3, 1])
        con_horas = editado.loc[editado[cfg["mes_carga"]] > 0, "DNI"].nunique()
        # Leído aquí y no de fl: tras guardar solo se rehace el fragmento
        guardado_en = leer_flujo(repo).estado(origen).get("FECHA_GUARDADO")
        from src.flujo import fmt
        c_info.markdown(
            f'<div class="bottom-info">{cfg["etiqueta"]} · '
            f'{con_horas} de {editado["DNI"].nunique()} docente(s) con horas'
            f'{" · último guardado " + fmt(guardado_en) if guardado_en else ""}'
            f'<br><span style="color:{"#B54708" if hay_cambios else "#067647"}">'
            f'{indicador(clave, hay_cambios, solo_lectura)}</span></div>',
            unsafe_allow_html=True)
        clic_guardar = c_btn.button("Guardar", type="primary", width="stretch",
                                    key=f"btn_guardar_{hoja}", disabled=solo_lectura)
    if clic_guardar and borrador.ya_guardado(clave, f_actual):
        # Clic repetido: el guardado anterior ya dejó esto en la base
        marcar_guardado(clave, f_actual)
        st.session_state[f"_resultado_{hoja}"] = (True, YA_GUARDADO)
        _rehacer_ficha()
    elif clic_guardar:
        errores = _errores()
        if errores:
            _dialogo_errores(errores)
        else:
            with st.spinner(GUARDANDO):
                ok, mensaje = guardar_borrador(repo, hoja, origen, editado, usuario.email,
                                               firma_actual=f_actual)
            if ok:
                marcar_guardado(clave, f_actual)
            if ok or not borrador.hay_conflicto(hoja, origen):   # el conflicto se muestra aparte
                st.session_state[f"_resultado_{hoja}"] = (ok, mensaje)
            _rehacer_ficha()
    # Al rehacer solo el fragmento, el aviso al cerrar la pestaña debe enterarse
    # de los cambios sin guardar
    aviso_al_salir()


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _rehacer_ficha():
    """Vuelve a dibujar solo la ficha (la pantalla no salta). scope="fragment"
    solo vale si esta ejecución ya es del fragmento; si no (el clic llegó junto
    con una recarga completa), se recarga todo."""
    from streamlit.runtime.scriptrunner import get_script_run_ctx
    ctx = get_script_run_ctx()
    st.rerun(scope="fragment" if ctx and ctx.fragment_ids_this_run else "app")


@st.cache_data(max_entries=20, show_spinner=False)
def _excel_ficha(ledger, hoja, origen, desc_ceco):
    return plantilla_tc.plantilla(ledger, hoja, origen, desc_ceco)


def _excel_tc(zona, hoja, origen, estado_ficha, ccos, estructura, solo_lectura):
    """Descargar la ficha del semestre en Excel y volver a cargarla llenada
    (src/plantilla_tc.py). Cargar solo pasa las horas a la ficha: se guardan
    con el botón Guardar, con sus validaciones."""
    ledger = st.session_state.get(estado_ficha)
    if ledger is None or ledger.empty:
        return
    with zona.expander("📊 Llenar en Excel: descargar la ficha y cargarla llenada"):
        desc = dict(zip(estructura["CODIGO_CECO"], estructura["DESCRIPCION_CECO"]))
        desc.update(zip(ccos["CODIGO_CECO"], ccos["DESCRIPCION_CECO"]))
        semestre = "I" if hoja == TC_HOJAS[0] else "II"
        c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
        c1.download_button("⬇ Descargar la ficha en Excel",
                           _excel_ficha(ledger, hoja, origen, desc),
                           file_name=f"plan_tc_{origen}_{semestre}_semestre_2027.xlsx",
                           mime=XLSX, on_click="ignore", width="stretch",
                           key=f"btn_excel_{estado_ficha}")
        if solo_lectura:
            return
        c1.caption("Sale con las horas que hay ahora en la ficha.")
        ver_key = f"_ver_excel_{estado_ficha}"
        archivo = c2.file_uploader("Cargar el Excel llenado", type=["xlsx"],
                                   key=f"up_tc_{estado_ficha}_{st.session_state.get(ver_key, 0)}")
        if archivo is None:
            return
        nuevo, errores, resumen = plantilla_tc.leer(archivo, ledger, hoja, origen)
        if errores:
            st.error(f"No se cargó nada: el archivo tiene {len(errores)} observación(es).",
                     icon="🛑")
            for e in errores[:15]:
                st.markdown(f"- {e}")
            if len(errores) > 15:
                st.caption(f"… y {len(errores) - 15} más.")
            return
        st.info(f"Archivo correcto: {resumen} Al cargarlo, esas horas reemplazan a las de "
                "la ficha; lo que no esté en el archivo queda igual.", icon="📄")
        if st.button("Cargar en la ficha", type="primary", key=f"btn_cargar_{estado_ficha}"):
            st.session_state[estado_ficha] = nuevo
            # Los campos de horas se vuelven a crear con los valores del Excel
            for k in [k for k in st.session_state if str(k).startswith(f"h_{estado_ficha}_")]:
                del st.session_state[k]
            st.session_state[ver_key] = st.session_state.get(ver_key, 0) + 1
            st.session_state[f"_resultado_{hoja}"] = (
                True, "Horas del Excel cargadas en la ficha. Revísalas y pulsa Guardar.")
            _rehacer_ficha()


@st.dialog("Revisa antes de guardar", width="large")
def _dialogo_errores(errores):
    for e in errores:
        st.error(e, icon="⚠️")
    if st.button("Volver", type="primary", width="stretch"):
        st.rerun()


def _renderizar_grilla(repo, fl, hoja, cfg, ccos, roster, tarifas, origen, guardado,
                       solo_lectura, usuario, sps=()):
    """Grilla matricial + feedback en vivo + guardado de borrador (con sps,
    además valoriza al guardar: las áreas de ayudantías)."""
    gestor = usuario.planillas_de(origen) == [INVESTIGACION]
    _mostrar_resultado(hoja)
    # Claves de sesión de la grilla (ver vistas.grilla)
    borrador.mostrar_conflicto(hoja, origen, [f"_base_{hoja}_{origen}",
                                              f"_ultimo_{hoja}_{origen}"],
                               (f"grilla_{hoja}_{origen}_",))
    editado = grilla(cfg, ccos, roster, tarifas, origen, guardado, solo_lectura)

    total = estimar_importe(hoja, editado, tarifas)
    horas = total_horas(hoja, editado)
    lineas, registros = conteo(editado)
    reservado = cfg.get("montos_reservados") and not (usuario.presupuesto or usuario.rrhh)
    if hoja == PUESTOS_NUEVOS:   # puestos-mes: la suma de las celdas
        registros = int(round(total_horas(hoja, editado)))
    hero(hoja, total, horas, lineas, registros, ocultar_monto=reservado,
         puestos=contar_puestos(editado) if hoja == PUESTOS_NUEVOS else None)

    clave = f"{hoja}|{origen}"
    f_actual = firma(editado, [c for c in editado.columns if c not in MESES], MESES)
    hay_cambios = pendiente(clave, f_actual)
    errores_de = lambda: validar(hoja, editado, set(ccos["CODIGO_CECO"]), tarifas,
                                 estricto=False)
    if hay_cambios and not solo_lectura and toca_autoguardar(clave):
        autoguardar(clave, f_actual, errores_de(),
                    lambda: guardar_borrador(repo, hoja, origen, editado, usuario.email, sps,
                                             gestor, firma_actual=f_actual))
        hay_cambios = pendiente(clave, f_actual)

    st.divider()
    mostrar_indicador(clave, hay_cambios, solo_lectura)
    if st.button("Guardar", type="primary", width="stretch",
                 key=f"btn_guardar_{hoja}", disabled=solo_lectura):
        errores = errores_de()
        if borrador.ya_guardado(clave, f_actual):
            # Clic repetido: el guardado anterior ya dejó esto en la base
            marcar_guardado(clave, f_actual)
            st.session_state[f"_resultado_{hoja}"] = (True, YA_GUARDADO)
            st.rerun()
        elif errores:
            _dialogo_errores(errores)
        else:
            with st.spinner(GUARDANDO):
                resultado = guardar_borrador(repo, hoja, origen, editado, usuario.email,
                                             sps, gestor, firma_actual=f_actual)
            if resultado[0]:
                marcar_guardado(clave, f_actual)
            if resultado[0] or not borrador.hay_conflicto(hoja, origen):
                st.session_state[f"_resultado_{hoja}"] = resultado
            st.rerun()


def guardar_borrador(repo, hoja, origen, editado, email, sps=(), gestor=False, firma_actual=None):
    """Guarda la planilla (sin valorizar, o valorizándola en la misma
    transacción si vienen sps). Devuelve (ok, mensaje). Si otra persona la
    guardó desde que esta sesión la abrió, no guarda: deja el aviso de
    conflicto (borrador.mostrar_conflicto) para recargar."""
    cfg = cfg_de(hoja)
    filas, cols = preparar_filas(hoja, origen, editado, repo)
    versiones, clave = borrador.versiones(), f"{hoja}|{origen}"
    confirmados = borrador.confirmados()

    def al_confirmar(v):   # justo tras el COMMIT, sin st.* (ver borrador.confirmados)
        versiones[clave] = v
        if firma_actual is not None:
            confirmados[clave] = firma_actual

    try:
        n, _ = repo.guardar_borrador(hoja, origen, filas, cols, email=email,
                                     version=versiones.get(clave), sps=sps,
                                     al_confirmar=al_confirmar)
        if sps:
            momento = ahora()
            marcar(repo, origen, FECHA_GUARDADO=momento, FECHA_VALORIZACION=momento)
            return True, f"{cfg['etiqueta']}: {n} registro(s) guardado(s) y valorizado(s)."
        if hoja == PUESTOS_NUEVOS:
            return True, (f"{cfg['etiqueta']}: {contar_puestos(editado)} puesto(s) "
                          f"guardado(s) ({int(round(total_horas(hoja, editado)))} "
                          f"{cfg.get('unidad', 'puestos')}-mes).")
        if cfg.get("pestaña_propia"):   # no se valoriza: no marca el flujo del depto
            return True, f"{cfg['etiqueta']}: {n} registro(s) guardado(s)."
        marcar(repo, origen, FECHA_GUARDADO=ahora())
        if gestor:   # el gestor de investigación no valoriza: lo hace el departamento
            return True, (f"{cfg['etiqueta']}: {n} registro(s) guardado(s). El departamento "
                          "ya puede revisarlos y valorizarlos.")
        return True, (f"{cfg['etiqueta']}: {n} registro(s) guardado(s). Cuando termines "
                      "todas tus planillas, valoriza desde «Resumen y valorización».")
    except ConflictoGuardado as c:
        mensaje = mensaje_conflicto(cfg["etiqueta"], c)
        borrador.marcar_conflicto(hoja, origen, mensaje)
        return False, mensaje
    except Exception as ex:
        return False, f"No se guardó nada; se revirtió la operación. Detalle: {ex}"


GUARDANDO = "Guardando… no hace falta volver a pulsar «Guardar»."
YA_GUARDADO = "Ya está guardado: no hay cambios desde el último guardado."


def mensaje_conflicto(etiqueta, c) -> str:
    from src.flujo import fmt
    return (f"No se guardó «{etiqueta}»: {c.email or 'otra persona'} la guardó el "
            f"{fmt(c.fecha)} mientras la editabas. Para no borrar su trabajo, recarga la "
            "planilla con lo último guardado y vuelve a hacer tus cambios. El guardado "
            "automático queda en pausa hasta que recargues.")


def roster_vacio():
    return pd.DataFrame(columns=["DNI", "NOMBRE"])


if __name__ == "__main__":
    main()
