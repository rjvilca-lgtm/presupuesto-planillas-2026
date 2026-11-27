"""
Centros de costo 2027 (Presupuesto · administración › Centros de costo).

Para saber qué centros existen en cada facultad y dirección, quién puede
presupuestarlos, y agregarlos o corregirlos sin escribir SQL:

  - Consultar: el catálogo CENTROS_COSTOS_2027 con los departamentos que
    pueden presupuestar cada centro (CECOS_DEPARTAMENTO_2027), los que lo
    tienen en la ficha TC (CECO_CONCEPTO_TC) y las filas guardadas en 2027.
  - Verificar: lo que impide presupuestar o no cuadra.
  - Actualizar: pegar centros desde Excel, asignarlos a departamentos y
    agregarlos a la ficha TC.
  - Focos: cambiar el foco de un centro (foco manual en
    CLASIFICACION_CECOS_2027, requiere sql/crear_foco_por_centro_2027.sql) o
    el nombre de un foco (FOCOS_NOMBRES_2027, sql/crear_nombres_focos_2027.sql).
  - Permisos Power BI: qué centros 2027 ve cada cuenta del informe; dar o
    quitar acceso por foco (USUARIOS_FOCOS_2027) o por código
    (USUARIOS_PREFIJOS_2027). Requiere sql/crear_permisos_powerbi_2027.sql.
  - Cambios: el registro de quién cambió qué (AUDITORIA_CECOS_2027).

Escribir requiere sql/crear_gestion_cecos_2027.sql. Nunca borra centros del
catálogo ni quita un centro en el que un departamento ya tiene datos 2027.
"""

import re

import pandas as pd
import streamlit as st

from .config import CONCEPTO_ACADEMICAS, CONCEPTO_CRONOLOGICAS

CODIGO = re.compile(r"\d{2}(\.\d{2}){4}")
CONCEPTOS_ESCUELA = [CONCEPTO_ACADEMICAS, CONCEPTO_CRONOLOGICAS, "Otras Actividades Pregrado"]
_RES = "_res_cecos"


def _resultado():
    res = st.session_state.pop(_RES, None)
    if res:
        (st.success if res[0] else st.error)(res[1], icon="✅" if res[0] else "🛑")


def _hecho(ok: bool, mensaje: str):
    st.session_state[_RES] = (ok, mensaje)
    st.rerun()


def vista_cecos(repo, deptos: list[tuple], usuario):
    st.caption("Qué centros de costo existen en cada facultad y dirección, quién puede "
               "presupuestarlos y cómo agregarlos. Un centro aparece en las planillas de un "
               "departamento cuando está **asignado** a ese departamento; en la ficha TC, "
               "cuando además está en su **estructura TC**.")
    _resultado()
    try:
        catalogo = repo.catalogo_cecos()
    except Exception as ex:
        st.warning(f"No se pudo leer el catálogo ({type(ex).__name__}: {ex}).", icon="⚠️")
        return
    puede_escribir = repo.gestion_cecos_disponible()
    parte = st.segmented_control(
        "Sección", ["🔎 Consultar", "✅ Verificar", "✏️ Actualizar", "🎯 Focos",
                    "🔐 Permisos Power BI", "🕘 Cambios"],
        default="🔎 Consultar", key="cecos_parte", label_visibility="collapsed")
    if parte == "🎯 Focos":
        _focos(repo, usuario)
    elif parte == "🔐 Permisos Power BI":
        _permisos_bi(repo, usuario)
    elif parte == "✅ Verificar":
        _verificar(repo)
    elif parte == "✏️ Actualizar":
        if not puede_escribir:
            st.warning("Para actualizar desde aquí, ejecuta `sql/crear_gestion_cecos_2027.sql` en "
                       "Azure y pulsa «Actualizar datos ahora» en ⏱ Rendimiento.", icon="⚠️")
            return
        _actualizar(repo, catalogo, deptos, usuario)
    elif parte == "🕘 Cambios":
        if puede_escribir:
            st.dataframe(repo.auditoria_cecos(), hide_index=True, width="stretch",
                         column_config={"FECHA": st.column_config.DatetimeColumn(
                             "Fecha (Lima)", format="DD/MM/YYYY HH:mm"), "EMAIL": "Por",
                             "ACCION": "Acción", "DETALLE": "Detalle"})
        else:
            st.info("El registro de cambios empieza cuando se ejecute "
                    "`sql/crear_gestion_cecos_2027.sql`.", icon="ℹ️")
    else:
        _consultar(catalogo)


ORIGEN_FOCO = {"manual": "Manual", "heredada": "Heredado del centro antiguo",
               "grupo": "De su grupo de centros"}


def _focos(repo, usuario):
    st.caption("Los focos agrupan los centros 2027 en los informes de Power BI. Los cambios "
               "valen solo para las páginas 2027 (no para 2026) y se ven en Power BI al "
               "actualizar el modelo.")
    if not repo.focos_disponible():
        st.warning("Para cambiar focos, ejecuta `sql/crear_nombres_focos_2027.sql` en Azure.",
                   icon="⚠️")
        return
    try:
        focos = repo.focos_2027()
    except Exception as ex:
        st.warning(f"No se pudieron leer los focos ({type(ex).__name__}: {ex}).", icon="⚠️")
        return
    with st.expander("📍 Cambiar el foco de un centro", expanded=True):
        _foco_centro(repo, usuario, focos)
    with st.expander("✏️ Cambiar el nombre de un foco (todos sus centros)"):
        _nombre_foco(repo, usuario, focos)


def _foco_centro(repo, usuario, focos):
    if not repo.foco_centro_disponible():
        st.warning("Para cambiar el foco de un centro, ejecuta "
                   "`sql/crear_foco_por_centro_2027.sql` en Azure.", icon="⚠️")
        return
    centros = repo.focos_centros_2027()
    info = centros.astype(object).where(centros.notna(), None).set_index("CENTRO_COSTO")
    codigo = st.selectbox(
        "Centro de costo", list(centros["CENTRO_COSTO"]), index=None,
        placeholder="Escribe el código o el nombre", key="foco_centro",
        format_func=lambda c: f"{c} · {info.loc[c, 'DESCRIPCION_CC']} · "
                              f"{info.loc[c, 'FOCO'] or '(sin foco)'}")
    if not codigo:
        st.caption("El foco manual manda sobre el heredado. Los centros nuevos que no vienen "
                   "de un centro antiguo toman el foco de su grupo.")
        return
    actual, origen = info.loc[codigo, "FOCO"], info.loc[codigo, "ORIGEN_FOCO"]
    st.markdown(f"Foco actual: **{actual or '(sin foco)'}** · "
                f"{ORIGEN_FOCO.get(origen, 'sin origen')}")
    ver = st.session_state.get("_ver_foco_centro", 0)
    opciones = [f for f in focos["FOCO"] if f != actual] + ["➕ Otro foco (escribir)"]
    elegido = st.selectbox("Nuevo foco", opciones, index=None, placeholder="Elige el foco",
                           key=f"foco_centro_nuevo_{ver}_{codigo}")
    nuevo = elegido
    if elegido == opciones[-1]:
        nuevo = " ".join(st.text_input("Nombre del foco nuevo", max_chars=150,
                                       key=f"foco_centro_texto_{ver}_{codigo}").split())
        igual = next((f for f in focos["FOCO"] if f.casefold() == nuevo.casefold()), None)
        if igual:
            st.caption(f"Ya existe: se usará «{igual}».")
            nuevo = igual
    # Mover el último centro de un foco deja sin datos a las cuentas que lo ven por foco
    fila_foco = focos[focos["FOCO"] == actual]
    if actual and not fila_foco.empty and int(fila_foco["CENTROS"].iloc[0]) == 1 \
            and int(fila_foco["CUENTAS"].iloc[0]) > 0:
        st.warning(f"{codigo} es el único centro del foco «{actual}», y "
                   f"{int(fila_foco['CUENTAS'].iloc[0])} cuenta(s) de Power BI lo ven por ese "
                   "foco. Si lo mueves, se quedan sin datos: después dales el foco nuevo en "
                   "🔐 Permisos Power BI. Si solo cambió el nombre de la dirección, usa "
                   "«Cambiar el nombre del foco» (abajo): las cuentas pasan solas.", icon="⚠️")
    c1, c2 = st.columns(2)
    if c1.button("Cambiar foco", type="primary", key="btn_foco_centro", width="stretch",
                 disabled=not nuevo or nuevo == actual):
        try:
            repo.cambiar_foco_centro(codigo, nuevo, usuario.email)
            st.session_state["_ver_foco_centro"] = ver + 1
            _hecho(True, f"{codigo}: foco «{actual or '(sin foco)'}» → «{nuevo}». Actualiza el "
                         "modelo de Power BI para verlo.")
        except Exception as ex:
            _hecho(False, f"No se cambió nada; se revirtió la operación. Detalle: {ex}")
    if origen == "manual" and c2.button(
            "Volver al foco heredado", key="btn_foco_centro_heredado", width="stretch",
            help="Quita el foco manual: el centro vuelve a tomar el de su centro antiguo "
                 "o el de su grupo."):
        try:
            repo.cambiar_foco_centro(codigo, None, usuario.email)
            st.session_state["_ver_foco_centro"] = ver + 1
            _hecho(True, f"{codigo}: vuelve al foco heredado. Actualiza el modelo de Power BI "
                         "para verlo.")
        except Exception as ex:
            _hecho(False, f"No se cambió nada; se revirtió la operación. Detalle: {ex}")
    if actual:
        n = int(dict(zip(focos["FOCO"], focos["CENTROS"])).get(actual, 0))
        st.divider()
        st.markdown(f"**✏️ Cambiar el nombre del foco «{actual}»**")
        st.caption(f"Cambia en sus {n} centro(s) 2027, no solo en {codigo}, y en los que se "
                   "agreguen después. Las cuentas con acceso por foco pasan al nombre nuevo. "
                   "Para mover solo este centro, usa «Nuevo foco» arriba.")
        _renombrar(repo, usuario, focos, actual, "foco_c")


def _nombre_foco(repo, usuario, focos):
    st.caption("Cambia el **nombre** que se ve de un foco en todos sus centros, también los "
               "que se agreguen después. Las cuentas con acceso por foco pasan al nombre nuevo.")
    st.dataframe(focos, hide_index=True, width="stretch", column_config={
        "FOCO": st.column_config.TextColumn("Foco", width="large"),
        "CENTROS": st.column_config.NumberColumn("Centros 2027", format="%d"),
        "CUENTAS": st.column_config.NumberColumn(
            "Cuentas con acceso por foco", format="%d",
            help="Cuentas de Power BI que ven todos los centros de ese foco"),
        "ANTES": "Nombre original"})

    c1, c2 = st.columns(2)
    anterior = c1.selectbox("Foco", list(focos["FOCO"]), index=None,
                            placeholder="Elige un foco", key="foco_anterior")
    _renombrar(repo, usuario, focos, anterior, "foco", c2)


def _renombrar(repo, usuario, focos, anterior, clave, donde=None):
    """Nombre nuevo para el foco «anterior» (todos sus centros). Si el nombre
    ya existe, junta los dos focos con confirmación."""
    lista = list(focos["FOCO"])
    ver = st.session_state.get("_ver_foco", 0)
    nuevo = " ".join((donde or st).text_input(
        "Nombre nuevo del foco", key=f"{clave}_nuevo_{ver}_{anterior}",
        value=anterior or "", max_chars=150).split())
    juntar = next((f for f in lista if f.casefold() == nuevo.casefold() and f != anterior), None)
    confirma = True
    if anterior and juntar:
        centros = dict(zip(focos["FOCO"], focos["CENTROS"]))
        confirma = st.checkbox(f"«{juntar}» ya existe: los dos focos quedarán juntos, con "
                               f"{int(centros.get(juntar, 0) + centros.get(anterior, 0))} "
                               "centros. Confirmo que quiero juntarlos.",
                               key=f"{clave}_juntar_{ver}")
    if st.button("Cambiar nombre", type="primary", key=f"btn_{clave}",
                 disabled=not anterior or not nuevo or nuevo == anterior or not confirma):
        try:
            r = repo.renombrar_foco(anterior, juntar or nuevo, usuario.email)
            st.session_state["_ver_foco"] = ver + 1
            _hecho(True, f"«{anterior}» ahora se llama «{juntar or nuevo}»"
                         + (f"; {r['cuentas']} cuenta(s) con acceso por foco pasaron al nombre "
                            "nuevo" if r["cuentas"] else "")
                         + ". Actualiza el modelo de Power BI para verlo.")
        except Exception as ex:
            _hecho(False, f"No se cambió nada; se revirtió la operación. Detalle: {ex}")


CORREO = re.compile(r"[a-z0-9._%+-]+@ucsp\.edu\.pe")
PREFIJO = re.compile(r"\d{2}(\.\d{2}){0,4}\.?")
_OTRA_CUENTA = "➕ Otra cuenta (escribir)"


def _permisos_bi(repo, usuario):
    st.caption("Qué centros 2027 ve cada cuenta en las páginas 2027 del informe de Power BI. "
               "Aquí se da o se quita acceso por **foco** (todos los centros de un foco) o por "
               "**código** (todos los centros cuyo código empieza así; un código completo = un "
               "centro). El acceso base por centro o departamento (tabla USUARIOS, también "
               "2026) se ve pero no se cambia aquí. Los cambios se ven al actualizar el modelo.")
    if not repo.permisos_bi_disponible():
        st.warning("Para cambiar permisos, ejecuta `sql/crear_permisos_powerbi_2027.sql` en "
                   "Azure.", icon="⚠️")
        return
    try:
        cuentas = repo.cuentas_bi_2027()
        centros = repo.focos_centros_2027()
    except Exception as ex:
        st.warning(f"No se pudieron leer los permisos ({type(ex).__name__}: {ex}).", icon="⚠️")
        return
    with st.expander(f"👥 Cuentas con acceso 2027 ({len(cuentas)})"):
        st.dataframe(cuentas, hide_index=True, width="stretch", column_config={
            "CORREO": "Cuenta",
            "DEPTO": st.column_config.NumberColumn(
                "Centros (rol Usuarios)", format="%d",
                help="Centros 2027 que ve con el rol Usuarios del informe"),
            "CENTRO": st.column_config.NumberColumn(
                "Centros (rol Usuario_centro)", format="%d",
                help="Centros 2027 que ve con el rol Usuario_centro (páginas de requerimientos)"),
            "FOCOS": "Focos dados", "PREFIJOS": "Códigos dados"})

    ver = st.session_state.get("_ver_bi", 0)
    elegida = st.selectbox("Cuenta", list(cuentas["CORREO"]) + [_OTRA_CUENTA], index=None,
                           placeholder="Escribe la cuenta", key="bi_cuenta")
    correo = elegida
    if elegida == _OTRA_CUENTA:
        correo = st.text_input("Correo de la cuenta", key="bi_cuenta_texto",
                               placeholder="cuenta-bi@ucsp.edu.pe").strip().lower()
        if correo and not CORREO.fullmatch(correo):
            st.error("Escribe un correo @ucsp.edu.pe.", icon="🛑")
            return
    if not correo:
        return

    p = repo.permisos_bi_cuenta(correo)
    vistos = p["centros"]
    c1, c2 = st.columns(2)
    c1.metric("Centros 2027 · rol Usuarios", int(vistos["USUARIOS"].sum()) if len(vistos) else 0)
    c2.metric("Centros 2027 · rol Usuario_centro",
              int(vistos["USUARIO_CENTRO"].sum()) if len(vistos) else 0)
    base = p["base"]
    if len(base):
        st.caption("Acceso base (USUARIOS, no se cambia aquí): " + "; ".join(
            x for x in (base["CENTRO_COSTO"].dropna().tolist()
                        + base["DEPARTAMENTO"].dropna().tolist())))
    else:
        st.caption("Sin acceso base en USUARIOS: en el servicio de Power BI agrega la cuenta al "
                   "rol Usuarios o Usuario_centro (con foco o código vale cualquiera de los dos).")

    for tipo, df, col, nombre in (("FOCO", p["focos"], "FOCO", "Foco"),
                                  ("PREFIJO", p["prefijos"], "PREFIJO", "Código")):
        for i, valor in enumerate(df[col]):
            extra = ""
            if tipo == "PREFIJO":
                n = int(centros["CENTRO_COSTO"].str.startswith(valor).sum())
                motivo = df["MOTIVO"].iloc[i]
                extra = f" · {n} centro(s)" + (f" · {motivo}" if pd.notna(motivo) and motivo
                                               else "")
            else:
                extra = f" · {int((centros['FOCO'] == valor).sum())} centro(s)"
            a, b = st.columns([4, 1], vertical_alignment="center")
            a.markdown(f"{nombre}: **{valor}**{extra}")
            if b.button("Quitar", key=f"bi_quitar_{tipo}_{i}", width="stretch"):
                try:
                    repo.quitar_permiso_bi(correo, tipo, valor, usuario.email)
                    _hecho(True, f"{correo}: se quitó el {nombre.lower()} «{valor}». Actualiza "
                                 "el modelo de Power BI para verlo.")
                except Exception as ex:
                    _hecho(False, f"No se cambió nada; se revirtió la operación. Detalle: {ex}")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**🎯 Dar un foco**")
        dados = set(p["focos"]["FOCO"])
        lista = sorted(f for f in centros["FOCO"].dropna().unique() if f not in dados)
        foco = st.selectbox("Foco", lista, index=None, placeholder="Elige el foco",
                            key=f"bi_foco_{ver}_{correo}")
        if foco:
            st.caption(f"Verá sus {int((centros['FOCO'] == foco).sum())} centro(s) 2027 y los "
                       "que tengan ese foco después.")
        if st.button("Dar foco", type="primary", key="btn_bi_foco", disabled=not foco,
                     width="stretch"):
            _dar_bi(repo, usuario, correo, "FOCO", foco, None, ver)
    with c2:
        st.markdown("**🔢 Dar centros por código**")
        texto = "".join(st.text_input("Código o inicio del código", max_chars=20,
                                      key=f"bi_prefijo_{ver}_{correo}",
                                      placeholder="01.01.04. o 01.01.04.06.01").split())
        prefijo, n = None, 0
        if texto:
            if not PREFIJO.fullmatch(texto):
                st.error("Usa el formato de los códigos: 01, 01.01, … 01.01.04.06.01.", icon="🛑")
            else:
                base_cod = texto.rstrip(".")   # código completo: un solo centro
                prefijo = base_cod if len(base_cod) == 14 else base_cod + "."
                n =int(centros["CENTRO_COSTO"].str.startswith(prefijo).sum())
                st.caption(f"`{prefijo}` → {n} centro(s) 2027 hoy"
                           + (" y los que se creen después con ese inicio."
                              if n and prefijo.endswith(".") else "."))
        motivo = " ".join(st.text_input("Motivo (opcional)", max_chars=200,
                                        key=f"bi_motivo_{ver}_{correo}").split())
        if st.button("Dar centros", type="primary", key="btn_bi_prefijo",
                     disabled=not prefijo or not n, width="stretch"):
            _dar_bi(repo, usuario, correo, "PREFIJO", prefijo, motivo or None, ver)

    with st.expander(f"📋 Centros 2027 que ve ({len(vistos)})"):
        st.dataframe(vistos, hide_index=True, width="stretch", column_config={
            "CENTRO_COSTO": "Centro", "DESCRIPCION_CC": "Descripción", "FOCO": "Foco",
            "USUARIOS": st.column_config.CheckboxColumn("Rol Usuarios"),
            "USUARIO_CENTRO": st.column_config.CheckboxColumn("Rol Usuario_centro")})


def _dar_bi(repo, usuario, correo, tipo, valor, motivo, ver):
    nombre = {"FOCO": "el foco", "PREFIJO": "los centros"}[tipo]
    try:
        n = repo.dar_permiso_bi(correo, tipo, valor, usuario.email, motivo)
        st.session_state["_ver_bi"] = ver + 1
        _hecho(True, f"{correo}: ya tenía {nombre} «{valor}»." if not n else
                     f"{correo}: ahora ve {nombre} «{valor}». Actualiza el modelo de Power BI "
                     "para verlo.")
    except Exception as ex:
        _hecho(False, f"No se cambió nada; se revirtió la operación. Detalle: {ex}")


def _direcciones(catalogo) -> list[str]:
    dirs = sorted(d for d in catalogo["DIRECCION"].dropna().unique())
    return [d for d in dirs if d.upper().startswith("FACULTAD")] + \
           [d for d in dirs if not d.upper().startswith("FACULTAD")]


def _consultar(catalogo):
    c1, c2, c3 = st.columns([3, 3, 2], vertical_alignment="bottom")
    direccion = c1.selectbox("Facultad o dirección", ["Todas"] + _direcciones(catalogo),
                             key="cecos_dir")
    texto = c2.text_input("Buscar", placeholder="Código o descripción", key="cecos_buscar")
    solo = c3.toggle("Solo sin departamento", key="cecos_solo_sin")
    df = catalogo
    if direccion != "Todas":
        df = df[df["DIRECCION"] == direccion]
    if texto.strip():
        t = texto.strip().lower()
        df = df[df["CENTRO_COSTO"].str.lower().str.contains(t, regex=False)
                | df["DESCRIPCION_CC"].fillna("").str.lower().str.contains(t, regex=False)]
    if solo:
        df = df[df["DEPARTAMENTOS"].isna()]
    m = st.columns(4)
    m[0].metric("Centros", len(df))
    m[1].metric("Con departamento", int(df["DEPARTAMENTOS"].notna().sum()))
    m[2].metric("En alguna ficha TC", int(df["FICHA_TC"].notna().sum()))
    m[3].metric("Con datos 2027", int((pd.to_numeric(df["FILAS_2027"]) > 0).sum()))
    st.dataframe(
        df, hide_index=True, width="stretch",
        column_config={
            "CENTRO_COSTO": "Código", "DESCRIPCION_CC": st.column_config.TextColumn(
                "Descripción", width="large"), "DIRECCION": "Facultad o dirección",
            "DEPARTAMENTOS": "Pueden presupuestarlo", "FICHA_TC": "En la ficha TC de",
            "FILAS_2027": st.column_config.NumberColumn("Filas 2027", format="%d")})
    st.caption("Sin departamento: nadie puede presupuestarlo todavía. Asígnalo en "
               "✏️ Actualizar.")


def _verificar(repo):
    try:
        v = repo.verificacion_cecos()
    except Exception as ex:
        st.warning(f"No se pudo verificar ({type(ex).__name__}: {ex}).", icon="⚠️")
        return
    revisiones = [
        ("sin_departamento", "Centros de facultad sin departamento",
         "Nadie puede presupuestarlos. Si deben usarse en 2027, asígnalos en ✏️ Actualizar."),
        ("deptos_sin_cecos", "Departamentos sin centros asignados",
         "Sus planillas no tienen centros para elegir."),
        ("asignados_inexistentes", "Asignaciones a centros que no están en el catálogo",
         "Agrega el centro al catálogo (✏️ Actualizar › pegar desde Excel) o quita la asignación."),
        ("ficha_inexistentes", "Ficha TC con centros que no están en el catálogo",
         "Aparecen en la ficha sin descripción. Agrega el centro al catálogo o quítalo de la ficha."),
        ("datos_fuera", "Datos 2027 guardados con centros que el departamento no tiene",
         "Lo guardado no coincide con sus centros: asigna el centro al departamento o pide que "
         "corrijan la planilla."),
        ("otra_facultad", "Centros de otra facultad asignados a un departamento",
         "Su facultad es la que tiene más centros suyos; no cuentan las escuelas y programas de "
         "pregrado (ahí dictan departamentos de otras facultades). Suele pasar tras una "
         "recodificación: si no es un programa compartido, quítale el centro en ✏️ Actualizar."),
        ("ficha_nombre_facultad", "Ficha TC con nombres de facultad que no coinciden con el centro",
         "El concepto lleva el nombre de otra facultad o el anterior a una recodificación. "
         "Las horas guardadas con ese nombre se ven como una línea aparte."),
        ("permisos_bi_vacios", "Permisos de Power BI que no dan acceso a ningún centro",
         "Esas cuentas no ven nada en el informe 2027: el foco se quedó sin centros o el prefijo "
         "ya no coincide con ningún código. Cámbialos en 🔐 Permisos Power BI."),
    ]
    problemas = sum(1 for k, _, _ in revisiones if not v[k].empty)
    if not problemas:
        st.success("Todo cuadra: catálogo, asignaciones, ficha TC y datos 2027.", icon="✅")
    for clave, titulo, ayuda in revisiones:
        df = v[clave]
        if df.empty:
            st.markdown(f"✅ **{titulo}:** ninguno.")
            continue
        with st.expander(f"⚠️ {titulo}: {len(df)}", expanded=True):
            st.caption(ayuda)
            st.dataframe(df, hide_index=True, width="stretch")


def leer_pegado(texto: str) -> list[list[str]]:
    """Filas pegadas desde Excel (columnas separadas por tabulador, o por «;»):
    código, descripción y, opcional, facultad o dirección. Se salta una fila de
    encabezados."""
    filas = []
    for linea in (texto or "").splitlines():
        if not linea.strip():
            continue
        partes = [p.strip() for p in (linea.split("\t") if "\t" in linea else linea.split(";"))]
        if not filas and not any(ch.isdigit() for ch in partes[0]):
            continue   # encabezados
        filas.append((partes + ["", "", ""])[:3])
    return filas


def revisar_pegado(filas, catalogo, direccion_defecto) -> pd.DataFrame:
    actual = catalogo.set_index("CENTRO_COSTO")
    vistos, salida = set(), []
    for codigo, desc, direccion in filas:
        direccion = direccion or ""
        if not CODIGO.fullmatch(codigo):
            res = "Error: el código debe ser como 01.01.08.01.02"
        elif codigo in vistos:
            res = "Error: código repetido en lo pegado"
        elif not desc:
            res = "Error: falta la descripción"
        elif codigo not in actual.index:
            direccion = direccion or direccion_defecto or ""
            res = "Nuevo" if direccion else "Error: falta la facultad o dirección"
        else:
            antes = actual.loc[codigo]
            nueva_dir = direccion or antes["DIRECCION"]
            if (antes["DESCRIPCION_CC"], antes["DIRECCION"]) == (desc, nueva_dir):
                res = "Sin cambios"
            else:
                res = f"Cambia (antes: {antes['DESCRIPCION_CC']} · {antes['DIRECCION']})"
        vistos.add(codigo)
        salida.append((codigo, desc, direccion, res))
    return pd.DataFrame(salida, columns=["Código", "Descripción", "Facultad o dirección",
                                         "Resultado"])


def _actualizar(repo, catalogo, deptos, usuario):
    nombres = dict(deptos)
    fmt_depto = lambda d: f"{d} · {nombres.get(d, '')}"
    desc = dict(zip(catalogo["CENTRO_COSTO"], catalogo["DESCRIPCION_CC"]))
    fmt_ceco = lambda c: f"{c} · {desc.get(c, '¿no está en el catálogo?')}"

    with st.expander("📋 Agregar o corregir centros: pegar desde Excel", expanded=True):
        st.caption("Copia en Excel las columnas **código**, **descripción** y, si quieres, "
                   "**facultad o dirección**, y pégalas aquí. Los códigos nuevos se agregan; los "
                   "que ya existen se corrigen. Nunca se borran centros.")
        ver = st.session_state.get("_ver_cecos_pegar", 0)
        texto = st.text_area("Filas copiadas de Excel", key=f"cecos_pegar_{ver}", height=130,
                             placeholder="01.01.08.01.06\tCENTRO NUEVO DE HUMANIDADES\t"
                                         "FACULTAD DE HUMANIDADES, MATEMÁTICA Y CIENCIAS NATURALES")
        c1, c2 = st.columns(2)
        direccion_defecto = c1.selectbox(
            "Facultad o dirección para los nuevos que no la traigan", [None] +
            _direcciones(catalogo), format_func=lambda d: d or "—", key="cecos_dir_defecto")
        asignar_a = c2.multiselect("Asignar todas las filas pegadas a", [d for d, _ in deptos],
                                   format_func=fmt_depto, key=f"cecos_asignar_pegado_{ver}",
                                   help="Para que esos departamentos puedan presupuestarlos ya. "
                                        "Vale para todas las filas, nuevas o corregidas.")
        filas = leer_pegado(texto)
        if filas:
            revision = revisar_pegado(filas, catalogo, direccion_defecto)
            st.dataframe(revision, hide_index=True, width="stretch")
            errores = revision["Resultado"].str.startswith("Error")
            cambios = revision[revision["Resultado"].str.match("Nuevo|Cambia")]
            if errores.any():
                st.error(f"Corrige {int(errores.sum())} fila(s) con error para continuar.",
                         icon="🛑")
            aplicar = [(r["Código"], r["Descripción"], r["Facultad o dirección"] or None)
                       for _, r in revision.iterrows()
                       if r["Resultado"].startswith(("Nuevo", "Cambia")) or asignar_a]
            if st.button(f"Aplicar ({len(cambios)} cambio(s) en el catálogo"
                         + (f", asignar a {len(asignar_a)} departamento(s)" if asignar_a else "")
                         + ")", type="primary", key="btn_cecos_pegar",
                         disabled=bool(errores.any()) or not aplicar):
                try:
                    r = repo.guardar_cecos(aplicar, asignar_a, usuario.email)
                    st.session_state["_ver_cecos_pegar"] = ver + 1
                    _hecho(True, f"Catálogo: {r['nuevos']} nuevo(s), {r['cambiados']} "
                                 f"corregido(s); {r['asignaciones']} asignación(es) nueva(s).")
                except Exception as ex:
                    _hecho(False, f"No se cambió nada; se revirtió la operación. Detalle: {ex}")

    with st.expander("🏢 Asignar o quitar centros a un departamento"):
        depto = st.selectbox("Departamento", [d for d, _ in deptos], format_func=fmt_depto,
                             key="cecos_asig_depto")
        asignados = catalogo[catalogo["DEPARTAMENTOS"].fillna("").str.split(", ")
                             .apply(lambda l: depto in l)]
        st.caption(f"{depto} tiene {len(asignados)} centro(s) asignado(s).")
        # Por defecto se ofrecen los de su facultad (la más común entre sus centros)
        dirs = _direcciones(catalogo)
        comun = asignados["DIRECCION"].mode()
        direccion = st.selectbox("Mostrar centros de", ["Todas"] + dirs, key=f"cecos_asig_dir_{depto}",
                                 index=(dirs.index(comun.iloc[0]) + 1) if len(comun) else 0)
        libres = catalogo[~catalogo["CENTRO_COSTO"].isin(asignados["CENTRO_COSTO"])]
        if direccion != "Todas":
            libres = libres[libres["DIRECCION"] == direccion]
        c1, c2 = st.columns(2)
        poner = c1.multiselect("Centros para asignar", list(libres["CENTRO_COSTO"]),
                               format_func=fmt_ceco, key=f"cecos_poner_{depto}")
        if c1.button("Asignar", type="primary", disabled=not poner, key="btn_cecos_asignar",
                     width="stretch"):
            r = repo.asignar_cecos([depto], poner, False, usuario.email)
            _hecho(True, f"{r['hechos']} centro(s) asignado(s) a {depto}.")
        sacar = c2.multiselect("Centros para quitar", list(asignados["CENTRO_COSTO"]),
                               format_func=fmt_ceco, key=f"cecos_sacar_{depto}")
        if c2.button("Quitar", disabled=not sacar, key="btn_cecos_quitar", width="stretch"):
            r = repo.asignar_cecos([depto], sacar, True, usuario.email)
            msg = f"{r['hechos']} centro(s) quitado(s) de {depto}."
            if r["con_datos"]:
                msg += (" No se quitaron porque ya tienen datos 2027: "
                        + ", ".join(r["con_datos"]) + ".")
            _hecho(not r["con_datos"] or r["hechos"] > 0, msg)

    with st.expander("🧾 Ficha TC: agregar o quitar un centro"):
        st.caption("La ficha TC muestra, por docente, los centros y conceptos de la estructura "
                   "del departamento. Al agregar un centro aquí, también queda asignado al "
                   "departamento.")
        c1, c2 = st.columns(2)
        depto_f = c1.selectbox("Departamento", [d for d, _ in deptos], format_func=fmt_depto,
                               key="cecos_ficha_depto")
        ceco = c2.selectbox("Centro de costo", list(catalogo["CENTRO_COSTO"]),
                            format_func=fmt_ceco, index=None, placeholder="Elige un centro",
                            key="cecos_ficha_ceco")
        plantilla = st.radio(
            "Conceptos", ["Escuela: horas de dictado (académicas y cronológicas) y otras "
                          "actividades", "Un solo concepto de horas (gestión, investigación, "
                          "proyectos, centros…)"], key="cecos_ficha_plantilla")
        concepto = ""
        if plantilla.startswith("Un solo"):
            concepto = st.text_input("Nombre del concepto", key="cecos_ficha_concepto",
                                     value=(desc.get(ceco) or "").capitalize() if ceco else "",
                                     help="Como se verá en la ficha, por ejemplo «Gestión "
                                          "Administrativa Pregrado».")
        conceptos = CONCEPTOS_ESCUELA if plantilla.startswith("Escuela") else (
            [concepto.strip()] if concepto.strip() else [])
        if st.button("Agregar a la ficha TC", type="primary", key="btn_cecos_ficha",
                     disabled=not ceco or not conceptos):
            n = repo.agregar_ceco_ficha(depto_f, ceco, conceptos, usuario.email)
            _hecho(True, f"{ceco} en la ficha TC de {depto_f}: {n} concepto(s) agregado(s). Quien "
                         "tenga la ficha abierta debe recargar la página.")
        en_ficha = catalogo[catalogo["FICHA_TC"].fillna("").str.split(", ")
                            .apply(lambda l: depto_f in l)]["CENTRO_COSTO"]
        quitar = st.selectbox("Quitar de la ficha TC de " + depto_f, list(en_ficha),
                              format_func=fmt_ceco, index=None, placeholder="Elige un centro",
                              key=f"cecos_ficha_quitar_{depto_f}")
        if st.button("Quitar de la ficha", disabled=not quitar, key="btn_cecos_ficha_quitar"):
            n = repo.quitar_ceco_ficha(depto_f, quitar, usuario.email)
            if n < 0:
                _hecho(False, f"No se quitó: el plan TC 2027 de {depto_f} ya tiene horas en "
                              f"{quitar}. Primero que las pasen a otro centro.")
            _hecho(True, f"{quitar} quitado de la ficha TC de {depto_f} ({n} concepto(s)).")
