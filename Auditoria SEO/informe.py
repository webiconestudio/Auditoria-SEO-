"""Genera el PDF a partir de la plantilla HTML usando Edge o Chrome (sin WeasyPrint)."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

CARPETA = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))


def buscar_navegador():
    candidatos = [
        os.environ.get("PDF_BROWSER", ""),
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ]
    for nombre in ("msedge", "google-chrome", "chromium", "chromium-browser", "chrome"):
        candidatos.append(shutil.which(nombre) or "")
    for c in candidatos:
        if c and os.path.exists(c):
            return c
    return None


def html_informe(datos):
    env = Environment(loader=FileSystemLoader(CARPETA / "plantilla"),
                      autoescape=select_autoescape(["html"]))
    return env.get_template("informe.html").render(d=datos)


def generar_pdf(datos, destino):
    navegador = buscar_navegador()
    if not navegador:
        raise RuntimeError("No encuentro Microsoft Edge ni Google Chrome para generar el PDF.")
    destino = Path(destino).resolve()
    destino.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        html = Path(tmp) / "informe.html"
        html.write_text(html_informe(datos), encoding="utf-8")
        if destino.exists():
            destino.unlink()
        base = [navegador, "--headless", "--disable-gpu", "--no-sandbox", "--disable-dev-shm-usage",
                "--disable-extensions", "--no-first-run", "--no-pdf-header-footer",
                f"--print-to-pdf={destino}", html.as_uri()]
        # 1º intento con el perfil por defecto; si el navegador ya está abierto y no
        # genera nada, 2º intento con un perfil temporal propio.
        for extra in ([], [f"--user-data-dir={Path(tmp) / 'perfil'}"]):
            try:
                subprocess.run(base[:1] + extra + base[1:], check=False, timeout=60,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except subprocess.TimeoutExpired:
                pass
            if destino.exists() and destino.stat().st_size > 0:
                return destino
    raise RuntimeError("El navegador no ha generado el PDF.")
