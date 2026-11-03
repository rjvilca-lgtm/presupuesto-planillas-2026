"""
Diagnóstico de lentitud: cuánto tarda el SERVIDOR en armar cada pantalla.

Cada ejecución de la app (cada clic) se mide en app.py y se guarda aquí, en
memoria compartida por todas las sesiones (se reinicia con la app), y en los
logs de Streamlit Cloud ("[tiempo] ..."). Si el servidor responde rápido y el
usuario lo siente lento, la demora está en su red, no en la app.

Para encontrar la causa de una ejecución lenta, los logs también dicen:
  - en cada [tiempo] LENTO: cuánto fue SQL (y cuánto de eso fue esperar una
    conexión libre del grupo compartido) y la memoria del proceso;
  - [sql lento]: cada consulta que esperó o tardó mucho (solo el texto SQL,
    nunca los parámetros);
  - [guardar] … total: en qué etapa del guardado se fue el tiempo;
  - [pausa]: el proceso entero estuvo detenido (todos los usuarios esperan):
    lo detecta un hilo que despierta cada segundo y mide cuánto se atrasó;
  - [memoria]: cada 15 minutos, la memoria usada y el límite del contenedor.
"""

import collections
import os
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

LIMA = timezone(timedelta(hours=-5))
LENTO_SEG = 3.0   # se marca en los logs
SQL_LENTO_SEG = 3.0    # consulta que se anota sola
ESPERA_LENTA_SEG = 1.0  # espera por una conexión libre que se anota
PAUSA_SEG = 3.0        # atraso del vigilante que cuenta como pausa del proceso
MEMORIA_CADA_SEG = 15 * 60


@st.cache_resource(show_spinner=False)
def _registro():
    return {"lock": threading.Lock(), "filas": collections.deque(maxlen=2000)}


# Lo que hizo la ejecución actual (cada ejecución corre en su propio hilo)
_actual = threading.local()


def iniciar_medicion():
    _actual.sql = 0.0
    _actual.espera = 0.0
    _actual.consultas = 0


def anotar_sql(espera: float, consulta: float, sql: str, filas: int | None):
    if hasattr(_actual, "sql"):
        _actual.sql += espera + consulta
        _actual.espera += espera
        _actual.consultas += 1
    if consulta >= SQL_LENTO_SEG or espera >= ESPERA_LENTA_SEG:
        texto = " ".join(sql.split())[:90]
        print(f"[sql lento] espera de conexión {espera:.1f}s · consulta {consulta:.1f}s · "
              f"{filas if filas is not None else '?'} fila(s) · {texto}", flush=True)


def _leer_entero(ruta: str) -> int | None:
    try:
        with open(ruta) as f:
            valor = f.read().strip()
        return None if valor == "max" else int(valor)
    except (OSError, ValueError):
        return None


def memoria() -> str:
    """Memoria del proceso y límite del contenedor (Linux); vacío en Windows."""
    usada = None
    try:
        with open("/proc/self/status") as f:
            for linea in f:
                if linea.startswith("VmRSS:"):
                    usada = int(linea.split()[1]) * 1024
                    break
    except OSError:
        return ""
    if usada is None:
        return ""
    limite = (_leer_entero("/sys/fs/cgroup/memory.max")
              or _leer_entero("/sys/fs/cgroup/memory/memory.limit_in_bytes"))
    contenedor = (_leer_entero("/sys/fs/cgroup/memory.current")
                  or _leer_entero("/sys/fs/cgroup/memory/memory.usage_in_bytes"))
    mb = lambda b: f"{b / 2**20:,.0f}"
    texto = f"mem {mb(usada)} MB"
    if contenedor and limite and limite < 2**50:
        texto += f" (contenedor {mb(contenedor)} de {mb(limite)} MB, {contenedor / limite:.0%})"
    return texto


def _vigilar():
    """Despierta cada segundo: si se atrasa mucho, el proceso estuvo detenido
    (sin CPU, sin memoria o con el intérprete acaparado por otro hilo)."""
    ultimo_mem = 0.0
    while True:
        antes = time.monotonic()
        time.sleep(1)
        atraso = time.monotonic() - antes - 1
        if atraso >= PAUSA_SEG:
            print(f"[pausa] el proceso estuvo detenido {atraso:.1f}s · {memoria()}", flush=True)
        if time.monotonic() - ultimo_mem >= MEMORIA_CADA_SEG:
            ultimo_mem = time.monotonic()
            texto = memoria()
            if texto:
                print(f"[memoria] {texto} · hilos {threading.active_count()}", flush=True)


_NOMBRE_VIGILANTE = "vigilante-diagnostico"
_lanzando = threading.Lock()


def iniciar_vigilante():
    """Un solo hilo por proceso. Se busca por nombre (no con cache_resource):
    al recargar src/ tras un push se vacía esa caché y se lanzaría otro."""
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    with _lanzando:
        if any(h.name == _NOMBRE_VIGILANTE for h in threading.enumerate()):
            return
        threading.Thread(target=_vigilar, name=_NOMBRE_VIGILANTE, daemon=True).start()


def registrar(pantalla: str, email: str, segundos: float):
    reg = _registro()
    with reg["lock"]:
        reg["filas"].append((datetime.now(LIMA).replace(tzinfo=None, microsecond=0),
                             pantalla, email, round(segundos, 2)))
    marca = ""
    if segundos >= LENTO_SEG:
        marca = " LENTO"
        if hasattr(_actual, "sql"):
            marca += (f" · sql {_actual.sql:.1f}s en {_actual.consultas} consulta(s)"
                      f" (espera de conexión {_actual.espera:.1f}s)")
        mem = memoria()
        if mem:
            marca += f" · {mem}"
    print(f"[tiempo] {segundos:5.2f}s · {pantalla} · {email}{marca}", flush=True)


def vista_diagnostico(repo):
    st.subheader("Tiempos de respuesta del servidor")
    st.caption("Cuánto tarda la app en armar cada pantalla, sin contar la red del usuario. "
               "Si aquí los tiempos son bajos y alguien siente la app lenta, la demora está en "
               "su conexión. Se cuenta desde el último reinicio de la app.")
    with _registro()["lock"]:
        filas = list(_registro()["filas"])
    if not filas:
        st.info("Aún no hay mediciones.", icon="ℹ️")
    else:
        df = pd.DataFrame(filas, columns=["Hora", "Pantalla", "Usuario", "Segundos"])
        resumen = (df.groupby("Pantalla")["Segundos"]
                     .agg(Veces="count", Mediana="median",
                          **{"9 de cada 10 en menos de": lambda s: s.quantile(0.9)},
                          Máximo="max")
                     .round(2).sort_values("Máximo", ascending=False).reset_index())
        c1, c2, c3 = st.columns(3)
        c1.metric("Mediciones", f"{len(df):,}")
        c2.metric("Mediana", f"{df['Segundos'].median():.2f} s")
        c3.metric(f"Más de {LENTO_SEG:.0f} s", f"{int((df['Segundos'] >= LENTO_SEG).sum())}")
        st.dataframe(resumen, hide_index=True, width="stretch")
        with st.expander("Últimas 50 mediciones"):
            st.dataframe(df.iloc[::-1].head(50), hide_index=True, width="stretch")
    if st.button("Actualizar datos ahora (vaciar la caché)", key="btn_vaciar_cache",
                 help="Los catálogos se guardan en memoria hasta 1 hora y se renuevan solos "
                      "al guardar desde la app. Úsalo si se cambió algo directamente en Azure."):
        repo.limpiar_cache()
        st.toast("Caché vaciada: los datos se vuelven a leer de la base.", icon="🔄")
