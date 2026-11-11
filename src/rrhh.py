"""
Desarrollo Humano: padrón de docentes TC, sus horas, salarios 2027 y tarifas.

Docentes, horas y salarios se actualizan SOLO importando la plantilla única
(src/plantillas.py), una fila por persona. La valorización DDH 2027 se importa
con su propia plantilla (src/carga_ddh.py). La pantalla no muestra datos: solo
valida el archivo e informa errores, inconsistencias (por número de fila y DNI)
y conteos de altas, bajas y cambios. Las tarifas (4 valores) se editan aquí.

Salarios (Remuneraciones_2027) son confidenciales: solo este rol importa; se
leen sin caché compartida y solo para comparar; nunca se muestran ni se
imprimen; el archivo subido no se guarda; la auditoría registra quién, cuándo
y conteos, nunca montos. La comunicación con la base de datos va cifrada
(TLS obligatorio, ver repositorio._conectar_con_timeout). Opcional: [sql_rrhh]
en los secrets para una cuenta de base de datos propia para salarios.
"""

import pandas as pd
import streamlit as st

from . import carga_ddh, reporte_tc
from .plantillas import contar_movimientos, filas_txt, leer, plantilla, unificar_dni
from .repositorio import COLS_REMUNERACION, _hora_lima

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def vista_desarrollo_humano(repo, usuario, deptos):
    t_imp, t_hrs, t_ddh, t_tar, t_aud = st.tabs(
        ["Importar docentes y salarios", "Horas docentes TC", "Valorización DDH", "Tarifas",
         "Registro de cambios"], on_change="rerun", key="tabs_rrhh")
    if t_imp.open:
        with t_imp:
            _importar(repo, usuario, deptos)
    if t_hrs.open:
        with t_hrs:
            _horas_tc(repo, deptos)
    if t_ddh.open:
        with t_ddh:
            _valorizacion_ddh(repo, usuario)
    if t_tar.open:
        with t_tar:
            _tarifas(repo, usuario)
    if t_aud.open:
        with t_aud:
            st.caption("Importaciones y cambios de tarifas. Las importaciones registran solo "
                       "conteos, nunca datos de personas ni montos.")
            st.dataframe(repo.auditoria_dh(), hide_index=True, width="stretch")


def _mostrar_resultado(clave):
    res = st.session_state.pop(clave, None)
    if res:
        (st.success if res[0] else st.error)(res[1], icon="✅" if res[0] else "🛑")


# ------------------------------------------------------------ importar

def _avisos_planes(repo, tc: pd.DataFrame, pad_actual: pd.DataFrame) -> list[str]:
    """Docentes con plan TC 2027 ya guardado a los que la importación afecta.
    Solo DNI y departamento, sin nombres."""
    planes = repo.dni_con_plan_tc()
    if planes.empty:
        return []
    planes = planes.assign(DNI=planes["DNI"].map(lambda d: str(d).strip()))
    nuevos = tc.set_index("DNI")
    avisos = []
    fuera = planes[~planes["DNI"].isin(nuevos.index)]
    if not fuera.empty:
        avisos.append("Docentes con plan TC 2027 ya guardado que dejan de ser docentes TC "
                      "(su departamento deberá corregir el plan): "
                      + ", ".join(f"{r.DNI} ({r.ORIGEN})" for r in fuera.itertuples()))
    siguen = planes[planes["DNI"].isin(nuevos.index)]
    movidos = [(r.DNI, r.ORIGEN, nuevos.at[r.DNI, "DPTO"]) for r in siguen.itertuples()
               if nuevos.at[r.DNI, "DPTO"] != r.ORIGEN]
    if movidos:
        avisos.append("Docentes con plan TC guardado que cambian de departamento: "
                      + ", ".join(f"{d} ({a} → {b})" for d, a, b in movidos))
    horas_ant = pad_actual.set_index("DNI")["HORAS"]
    cambian = sorted(d for d in siguen["DNI"].unique() if d in horas_ant.index
                     and abs(float(nuevos.at[d, "HORAS"]) - float(horas_ant[d])) > 0.005)
    if cambian:
        avisos.append("Docentes con plan TC guardado a los que les cambian las horas (su "
                      "plan deberá sumar las nuevas horas): " + ", ".join(cambian))
    return avisos


def _importar(repo, usuario, deptos):
    st.caption("Actualiza el padrón de docentes a tiempo completo, sus horas y los salarios "
               "2027 con un solo Excel (una fila por persona). El archivo es la lista "
               "completa. Esta pantalla no muestra datos: solo verifica el archivo.")
    st.info("🔒 Información confidencial. La comunicación con la base de datos va cifrada y "
            "el archivo no se guarda en la app. Bórralo de tu equipo después de importarlo.")
    _mostrar_resultado("_res_importar")
    codigos = [d for d, _ in deptos]

    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    c1.download_button("⬇ Descargar plantilla en blanco", plantilla(codigos),
                       file_name="docentes_horas_salarios_2027.xlsx", mime=XLSX,
                       width="stretch")
    archivo = c2.file_uploader("Subir el Excel completado", type=["xlsx"],
                               key=f"up_rrhh_{st.session_state.get('_ver_rrhh', 0)}")
    if archivo is None:
        return

    nuevo, errores = leer(archivo, set(codigos))
    if errores:
        st.error("El archivo tiene errores. Corrígelos en el Excel y vuelve a subirlo:",
                 icon="⚠️")
        for e in errores:
            st.markdown(f"- {e}")
        return

    try:
        sal_actual = unificar_dni(repo.remuneraciones())
    except Exception as ex:
        st.error("No se pudieron leer los salarios 2027 actuales. ¿Ya se ejecutó "
                 f"`sql/crear_rol_desarrollo_humano.sql`? Detalle: {type(ex).__name__}")
        return
    pad_actual = unificar_dni(repo.horas_docentes_todos())
    tc = nuevo[nuevo["HORAS"].notna()]
    con_salario = nuevo[nuevo["TOTAL"] > 0]

    # Solo conteos: ningún dato de personas ni montos en pantalla
    mov_pad = contar_movimientos(pad_actual, tc[["DPTO", "DNI", "NOMBRE", "HORAS"]],
                                 ["DPTO", "NOMBRE", "HORAS"])
    # El departamento no cuenta como cambio de salario (en Remuneraciones venía vacío)
    mov_sal = contar_movimientos(
        sal_actual, con_salario.rename(columns={"NOMBRE": "Nombre", "CATEGORIA": "Categoria"}),
        ["Nombre", "Categoria"] + COLS_REMUNERACION)

    st.subheader("Verificación del archivo")
    m = st.columns(3)
    m[0].metric("Personas en el archivo", len(nuevo))
    m[1].metric("Docentes TC", len(tc))
    m[2].metric("Con salario", len(con_salario))
    st.markdown(
        f"**Padrón de docentes TC:** {mov_pad['altas']} alta(s) · {mov_pad['bajas']} baja(s) · "
        f"{mov_pad['cambios']} con cambios  \n"
        f"**Salarios 2027:** {mov_sal['altas']} alta(s) · {mov_sal['bajas']} baja(s) · "
        f"{mov_sal['cambios']} con cambios")

    # Inconsistencias que no bloquean, pero conviene revisar
    avisos = []
    solo_salario = nuevo[nuevo["HORAS"].isna()]
    if not solo_salario.empty:
        avisos.append(f"{len(solo_salario)} persona(s) con salario pero sin horas TC: no "
                      "están en el padrón y no se usan al valorizar (filas "
                      f"{filas_txt(solo_salario.index)}).")
    avisos += _avisos_planes(repo, tc, pad_actual)
    for a in avisos:
        st.warning(a, icon="⚠️")
    if not avisos:
        st.success("Sin inconsistencias.", icon="✅")

    acepta = True
    if mov_pad["bajas"] + mov_sal["bajas"]:
        acepta = st.checkbox(f"Confirmo las bajas: {mov_pad['bajas']} del padrón TC y "
                             f"{mov_sal['bajas']} de salarios (no están en el archivo).",
                             key="bajas_rrhh")
    if st.button("Importar", type="primary", disabled=not acepta, key="btn_importar_rrhh"):
        docentes = [[r.DPTO, r.DNI, r.NOMBRE, float(r.HORAS)] for r in tc.itertuples()]
        salarios = [[r.DNI, r.NOMBRE, r.CATEGORIA or None, r.DPTO or None]
                    + [float(getattr(r, c)) for c in COLS_REMUNERACION]
                    for r in con_salario.itertuples()]
        detalle = (f"Padrón TC: {len(docentes)} ({mov_pad['altas']} altas, {mov_pad['bajas']} "
                   f"bajas, {mov_pad['cambios']} cambios). Salarios: {len(salarios)} "
                   f"({mov_sal['altas']} altas, {mov_sal['bajas']} bajas, "
                   f"{mov_sal['cambios']} cambios).")
        try:
            repo.importar_rrhh(docentes, salarios, usuario.email, detalle)
            res = (True, "Importación completa. " + detalle
                   + " Recuerda borrar el archivo de tu equipo.")
        except Exception as ex:
            res = (False, "No se importó nada; se revirtió la operación. Detalle: "
                          f"{type(ex).__name__}")
        st.session_state["_res_importar"] = res
        st.session_state["_ver_rrhh"] = st.session_state.get("_ver_rrhh", 0) + 1
        st.rerun()


# ---------------------------------------------------------- valorización DDH

def _valorizacion_ddh(repo, usuario):
    st.caption("Valorización de Desarrollo Humano 2027 (planilla administrativa y demás "
               "conceptos de DH) por centro de costo, partida, dimensión y mes. Reemplaza "
               "la macro «Subir datos DDH»: mismas columnas. Cada importación reemplaza la "
               "anterior. Esta pantalla no muestra las filas: solo errores y totales.")
    _mostrar_resultado("_res_ddh")
    if not repo.ddh_disponible():
        st.warning("La cuenta de Desarrollo Humano no encuentra el procedimiento de "
                   "importación. Revisa que se haya ejecutado `sql/crear_carga_ddh_2027.sql` y "
                   "que la sección `[sql_rrhh]` de los secrets tenga la cuenta "
                   "`app_planillas_rrhh`.", icon="⚠️")
        return

    totales = repo.totales_ddh().set_index("ANIO")
    m = st.columns(2)
    for col, anio in zip(m, ("2027", "2026")):
        if anio in totales.index:
            col.metric(f"DDH {anio} en PLANILLA", f"S/ {totales.at[anio, 'TOTAL']:,.2f}",
                       help=f"{int(totales.at[anio, 'FILAS']):,} filas")
        else:
            col.metric(f"DDH {anio} en PLANILLA", "Sin datos")

    dimensiones = repo.dimensiones_ddh()
    c1, c2 = st.columns([1, 2], vertical_alignment="bottom")
    c1.download_button("⬇ Descargar plantilla en blanco", carga_ddh.plantilla(dimensiones),
                       file_name="valorizacion_ddh_2027.xlsx", mime=XLSX, width="stretch")
    archivo = c2.file_uploader("Subir el Excel de la valorización DDH", type=["xlsx", "xlsm"],
                               key=f"up_ddh_{st.session_state.get('_ver_ddh', 0)}")
    if archivo is None:
        return

    cecos = set(repo.todos_centros_costo()["CODIGO_CECO"])
    datos, errores, avisos = carga_ddh.leer(
        archivo, cecos, repo.equivalencia_cecos(), set(dimensiones["CODIGO"].astype(str)),
        repo.partidas())
    for a in avisos:
        st.warning(a, icon="⚠️")
    if errores:
        st.error("El archivo tiene errores. Corrígelos en el Excel y vuelve a subirlo:",
                 icon="⚠️")
        for e in errores:
            st.markdown(f"- {e}")
        return

    st.subheader("Verificación del archivo")
    m = st.columns(4)
    m[0].metric("Filas", f"{len(datos):,}")
    m[1].metric("Centros de costo", datos["CENTRO_COSTO"].nunique())
    m[2].metric("Partidas", datos["PARTIDA"].nunique())
    m[3].metric("Total", f"S/ {datos['IMPORTE'].sum():,.2f}")
    por_mes = datos.groupby("MES")["IMPORTE"].sum().reindex(range(1, 13), fill_value=0.0)
    st.caption("Total por mes (S/)")
    st.dataframe(pd.DataFrame([por_mes.values], columns=[
        "Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Set", "Oct", "Nov", "Dic"]),
        hide_index=True, width="stretch",
        column_config={c: st.column_config.NumberColumn(format="localized")
                       for c in ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago",
                                 "Set", "Oct", "Nov", "Dic"]})

    reemplaza = "2027" in totales.index
    acepta = True
    if reemplaza:
        acepta = st.checkbox(
            f"Confirmo que reemplaza la valorización DDH 2027 actual "
            f"({int(totales.at['2027', 'FILAS']):,} filas, S/ {totales.at['2027', 'TOTAL']:,.2f}).",
            key="conf_ddh")
    if st.button("Importar valorización DDH", type="primary", disabled=not acepta,
                 key="btn_importar_ddh"):
        aviso = (" Puede tardar unos 30 s por cada 13 mil filas nuevas o cambiadas."
                 if len(datos) > 2000 else "")
        with st.spinner("Importando…" + aviso):
            try:
                r = repo.importar_ddh(datos, usuario.email)
                res = (True, f"Valorización DDH 2027 importada: {r['filas']:,} filas, "
                             f"S/ {datos['IMPORTE'].sum():,.2f} ({r['insertadas']:,} nuevas, "
                             f"{r['borradas']:,} quitadas, {r['filas'] - r['insertadas']:,} sin "
                             "cambios). Recuerda borrar el archivo de tu equipo.")
            except Exception as ex:
                res = (False, "No se importó nada; se revirtió la operación. Detalle: "
                              f"{type(ex).__name__}: {str(ex)[:200]}")
        st.session_state["_res_ddh"] = res
        st.session_state["_ver_ddh"] = st.session_state.get("_ver_ddh", 0) + 1
        st.rerun()


# ------------------------------------------------------- horas docentes TC

def _horas_tc(repo, deptos):
    st.caption("Horas de los docentes TC 2027 según los planes de trabajo que guardaron "
               "los departamentos (horas cronológicas semanales, en decimal). Lo principal "
               "es la **Gestión de Dirección** (centro de costo 0), que la app no valoriza: "
               "la valoriza Desarrollo Humano. Son borradores: cambian cada vez que un "
               "departamento guarda su plan. No incluye remuneraciones.")
    tablas = reporte_tc.construir(repo.horas_tc(), repo.horas_docentes_todos(), deptos,
                                  repo.todos_centros_costo())
    res, direc = tablas["Resumen por docente"], tablas["Gestión de Dirección"]
    m = st.columns(4)
    m[0].metric("Docentes con plan", int((res["Plan guardado"] != "Sin plan").sum()),
                help=f"{len(res):,} en el padrón o con plan")
    m[1].metric("Con Gestión de Dirección", len(direc))
    m[2].metric("Gestión de Dirección · I", f"{direc['Gestión de Dirección I'].sum():,.2f} h")
    m[3].metric("Gestión de Dirección · II", f"{direc['Gestión de Dirección II'].sum():,.2f} h")

    generado = _hora_lima().strftime("%d/%m/%Y %H:%M")
    st.download_button("⬇ Descargar reporte (Excel)", reporte_tc.excel(tablas, generado),
                       file_name="horas_docentes_tc_2027.xlsx", mime=XLSX, type="primary",
                       help="Hojas: Gestión de Dirección, Resumen por docente, Por "
                            "departamento, Detalle (centro de costo y concepto) y Notas.")

    horas = st.column_config.NumberColumn(format="%.2f")
    pct = st.column_config.NumberColumn(format="percent")
    cfg = {c: (pct if c.startswith("%") else horas) for c in direc.columns
           if pd.api.types.is_float_dtype(direc[c])}
    st.subheader("Gestión de Dirección")
    if direc.empty:
        st.info("Ningún plan TC guardado tiene horas de Gestión de Dirección.", icon="ℹ️")
    else:
        st.caption("% Dirección = horas de Gestión de Dirección / horas del plan del semestre.")
        st.dataframe(direc, hide_index=True, width="stretch", column_config=cfg)
    st.subheader("Por departamento")
    dep = tablas["Por departamento"]
    st.dataframe(dep, hide_index=True, width="stretch",
                 column_config={c: horas for c in dep.columns
                                if pd.api.types.is_float_dtype(dep[c])})


# ------------------------------------------------------------- tarifas

def _tarifas(repo, usuario):
    from .config import PUESTOS_NUEVOS
    _mostrar_resultado("_res_tarifas")
    todas = repo.tarifas_todas()
    es_puesto = todas["HOJA_ORIGEN"] == PUESTOS_NUEVOS

    st.markdown("**Tarifas por hora**")
    st.caption("Las usan Horas adicionales (como valor por defecto de la tarifa), "
               "Ayudantías, la Carga académica y las Prácticas pre-profesionales (Practicas, "
               "S/ por hora de practicante). Un cambio se aplica a partir de la próxima "
               "valorización; en las prácticas, la próxima vez que se guarde cada planilla.")
    _editor_tarifas(repo, usuario, todas[~es_puesto].reset_index(drop=True), "horas",
                    {"HOJA_ORIGEN": st.column_config.TextColumn("Planilla", disabled=True),
                     "TIPO": st.column_config.TextColumn("Tipo", disabled=True),
                     "TARIFA": st.column_config.NumberColumn("Tarifa (S/ por hora)",
                                                             min_value=0.01, format="%.2f",
                                                             required=True)},
                    "Guardar tarifas por hora")

    st.divider()
    st.markdown("**Costo mensual de los puestos nuevos**")
    st.caption("Sueldo, bonos, asignación familiar, bono por hijo, Edenred y cargas sociales "
               "de un mes, por puesto. En un UPGRADE (ascenso) es solo la diferencia de "
               "básico con el puesto anterior, más sus cargas. Los departamentos y áreas que "
               "registran puestos no ven estos montos: solo eligen el puesto. El cambio se ve "
               "en lo ya registrado la próxima vez que se guarde cada planilla de puestos.")
    puestos = todas[es_puesto].reset_index(drop=True)
    if puestos.empty:
        st.info("Aún no hay costos de puestos cargados. La Oficina de Presupuesto debe "
                "ejecutar sql/crear_puestos_nuevos_2027.sql y la carga de costos en Azure.",
                icon="ℹ️")
        return
    _editor_tarifas(repo, usuario, puestos, "puestos",
                    {"TIPO": st.column_config.TextColumn("Puesto", disabled=True,
                                                         width="large"),
                     "TARIFA": st.column_config.NumberColumn("Costo mensual (S/)",
                                                             min_value=0.01, format="%,.2f",
                                                             required=True)},
                    "Guardar costos de puestos", orden=["TIPO", "TARIFA"])


def _editor_tarifas(repo, usuario, base, nombre, columnas, boton, orden=None):
    ver = f"_ver_tarifas_{nombre}"
    editado = st.data_editor(
        base, hide_index=True, width="stretch", num_rows="fixed", column_order=orden,
        key=f"ed_tarifas_{nombre}_{st.session_state.get(ver, 0)}", column_config=columnas)
    cambios = [(b.HOJA_ORIGEN, b.TIPO, b.TARIFA, e.TARIFA)
               for b, e in zip(base.itertuples(), editado.itertuples())
               if pd.notna(e.TARIFA) and abs(float(e.TARIFA) - float(b.TARIFA)) > 1e-9]
    if st.button(boton, type="primary", disabled=not cambios, key=f"btn_guardar_tarifas_{nombre}"):
        try:
            repo.guardar_tarifas(cambios, usuario.email)
            st.session_state["_res_tarifas"] = (True, f"{len(cambios)} valor(es) actualizado(s).")
            st.session_state[ver] = st.session_state.get(ver, 0) + 1
        except Exception as ex:
            st.session_state["_res_tarifas"] = (False, f"No se guardó nada. Detalle: {ex}")
        st.rerun()
