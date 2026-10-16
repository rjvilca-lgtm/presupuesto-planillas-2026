"""
Diagnóstico de lentitud: cuánto tarda el SERVIDOR en armar cada pantalla.

Cada ejecución de la app (cada clic) se mide en app.py y se guarda aquí, en
memoria compartida por todas las sesiones (se reinicia con la app), y en los
logs de Streamlit Cloud ("[tiempo] ..."). Si el servidor responde rápido y el
usuario lo siente lento, la demora está en su red, no en la app.
"""

import collections
import threading
from datetime import datetime, timedelta, timezone

import pandas as pd
import streamlit as st

LIMA = timezone(timedelta(hours=-5))
LENTO_SEG = 3.0   # se marca en los logs


@st.cache_resource(show_spinner=False)
def _registro():
    return {"lock": threading.Lock(), "filas": collections.deque(maxlen=2000)}


def registrar(pantalla: str, email: str, segundos: float):
    reg = _registro()
    with reg["lock"]:
        reg["filas"].append((datetime.now(LIMA).replace(tzinfo=None, microsecond=0),
                             pantalla, email, round(segundos, 2)))
    marca = " LENTO" if segundos >= LENTO_SEG else ""
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
