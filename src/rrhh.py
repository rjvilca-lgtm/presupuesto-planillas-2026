"""
Desarrollo Humano: padrón de docentes TC, sus horas, salarios 2027 y tarifas.

Docentes, horas y salarios se actualizan SOLO importando la plantilla única
(src/plantillas.py), una fila por persona. La pantalla no muestra datos: solo
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

from .plantillas import contar_movimientos, filas_txt, leer, plantilla, unificar_dni
from .repositorio import COLS_REMUNERACION

XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def vista_desarrollo_humano(repo, usuario, deptos):
    t_imp, t_tar, t_aud = st.tabs(["Importar docentes y salarios", "Tarifas",
                                   "Registro de cambios"], on_change="rerun", key="tabs_rrhh")
    if t_imp.open:
        with t_imp:
            _importar(repo, usuario, deptos)
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


# ------------------------------------------------------------- tarifas

def _tarifas(repo, usuario):
    st.caption("Tarifas por hora 2027. Las usan Horas adicionales (como valor por defecto "
               "de la tarifa), Ayudantías y la Carga académica. Un cambio se aplica a "
               "partir de la próxima valorización.")
    _mostrar_resultado("_res_tarifas")
    base = repo.tarifas_todas()
    editado = st.data_editor(
        base, hide_index=True, width="stretch", num_rows="fixed",
        key=f"ed_tarifas_{st.session_state.get('_ver_tarifas', 0)}",
        column_config={
            "HOJA_ORIGEN": st.column_config.TextColumn("Planilla", disabled=True),
            "TIPO": st.column_config.TextColumn("Tipo", disabled=True),
            "TARIFA": st.column_config.NumberColumn("Tarifa (S/)", min_value=0.01,
                                                    format="%.2f", required=True),
        })
    cambios = [(b.HOJA_ORIGEN, b.TIPO, b.TARIFA, e.TARIFA)
               for b, e in zip(base.itertuples(), editado.itertuples())
               if pd.notna(e.TARIFA) and abs(float(e.TARIFA) - float(b.TARIFA)) > 1e-9]
    if st.button("Guardar tarifas", type="primary", disabled=not cambios,
                 key="btn_guardar_tarifas"):
        try:
            repo.guardar_tarifas(cambios, usuario.email)
            st.session_state["_res_tarifas"] = (True, f"{len(cambios)} tarifa(s) actualizadas.")
            st.session_state["_ver_tarifas"] = st.session_state.get("_ver_tarifas", 0) + 1
        except Exception as ex:
            st.session_state["_res_tarifas"] = (False, f"No se guardó nada. Detalle: {ex}")
        st.rerun()
