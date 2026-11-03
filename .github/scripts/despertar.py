"""Abre la app con un navegador sin pantalla para que Streamlit Community
Cloud no la duerma (se duerme tras 12 h sin visitas). Si ya está dormida,
pulsa "Yes, get this app back up!". Solo abre la pantalla de login: no usa
credenciales. Lo corre .github/workflows/mantener_despierta.yml."""

import os
import re
import sys

from playwright.sync_api import sync_playwright

URL = os.environ.get("APP_URL",
                     "https://presupuesto-planillas-2026-uju9fwbb26t9awktyu79fa.streamlit.app/")
TEXTO_APP = "Presupuesto de planillas"


def app_cargada(page) -> bool:
    """La app corre dentro de un iframe: se busca su título en todos los frames."""
    for frame in page.frames:
        try:
            if frame.get_by_text(TEXTO_APP).count():
                return True
        except Exception:
            pass
    return False


with sync_playwright() as p:
    navegador = p.chromium.launch()
    page = navegador.new_page()
    page.goto(URL, wait_until="domcontentloaded", timeout=90_000)
    page.wait_for_timeout(10_000)

    boton = page.get_by_role("button", name=re.compile("get this app back up", re.I))
    if boton.count():
        print("La app estaba dormida: despertándola…")
        boton.first.click()
    else:
        print("La app estaba despierta.")

    # Esperar a que cargue: al despertar, o cuando la app está ocupada con
    # otros usuarios, puede tardar varios minutos. Si a los 4 minutos no cargó,
    # se recarga la página una vez y se espera otros 4.
    def esperar(intentos: int) -> bool:
        for _ in range(intentos):
            if app_cargada(page):
                return True
            page.wait_for_timeout(10_000)
        return app_cargada(page)

    ok = esperar(24)
    if not ok:
        print("No cargó en 4 minutos: recargando la página…")
        page.reload(wait_until="domcontentloaded", timeout=90_000)
        ok = esperar(24)
    # Quedarse un rato para que cuente como visita
    page.wait_for_timeout(15_000)
    navegador.close()

print("App en línea." if ok else "No se pudo confirmar que la app cargó.")
sys.exit(0 if ok else 1)
