"""Conexión con la API de SE Ranking (Website Audit).

Busca la auditoría más reciente y terminada del dominio y descarga su informe.
Si algo falla (sin clave, sin auditoría, error de red), NO detiene la auditoría
principal: devuelve {"disponible": False, "motivo": "..."} y el informe sigue.

La clave se lee de la variable de entorno SERANKING_API_KEY o de un archivo
.env junto a este programa (línea: SERANKING_API_KEY=tu_clave). Nunca va en el código.
"""

import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import requests

BASE_URL = "https://api.seranking.com/v1/site-audit/audits"
TIMEOUT = 30
BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def leer_clave():
    clave = os.environ.get("SERANKING_API_KEY", "").strip()
    if clave:
        return clave
    env = BASE / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8-sig").splitlines():
            linea = linea.strip()
            if not linea or linea.startswith("#") or "=" not in linea:
                continue
            nombre, _, valor = linea.partition("=")
            if nombre.strip() == "SERANKING_API_KEY":
                return valor.strip().strip('"').strip("'")
    return ""


def _host(texto):
    """'https://www.Ejemplo.com/ruta' -> 'ejemplo.com'."""
    texto = (texto or "").strip().lower()
    if "//" not in texto:
        texto = "//" + texto
    host = urlparse(texto).hostname or ""
    return host[4:] if host.startswith("www.") else host


def _buscar_auditoria(dominio, cabeceras):
    """Devuelve (auditoría más reciente terminada | None, nº de auditorías del dominio)."""
    host = _host(dominio)
    r = requests.get(BASE_URL, headers=cabeceras, params={"search": host, "limit": 50}, timeout=TIMEOUT)
    r.raise_for_status()
    propias = [a for a in r.json().get("items", []) if _host(a.get("url", "")) == host]
    terminadas = [a for a in propias if a.get("status") == "finished"]
    if not terminadas:
        return None, len(propias)
    elegida = max(terminadas, key=lambda a: (a.get("last_update") or "", a.get("id") or 0))
    return elegida, len(propias)


def _problemas(informe):
    """Extrae del informe los errores y avisos que tienen casos reales."""
    salida = []
    for seccion in informe.get("sections", []):
        for codigo, prop in seccion.get("props", {}).items():
            if prop.get("status") in ("error", "warning") and prop.get("value"):
                salida.append({"codigo": codigo, "nombre": prop.get("name", codigo),
                               "estado": prop["status"], "valor": prop["value"],
                               "seccion": seccion.get("name", "")})
    return salida


def _auditoria_por_id(audit_id, dominio, cabeceras):
    """Busca en el listado los datos de una auditoría concreta (puede no aparecer)."""
    r = requests.get(BASE_URL, headers=cabeceras, params={"search": _host(dominio), "limit": 50}, timeout=TIMEOUT)
    r.raise_for_status()
    for a in r.json().get("items", []):
        if a.get("id") == audit_id:
            return a
    return None


def obtener(dominio, log=print, audit_id=None):
    """Datos de SE Ranking para el dominio. Con audit_id usa esa auditoría; sin él, la más reciente."""
    clave = leer_clave()
    if not clave:
        return {"disponible": False, "motivo": "No hay clave de SE Ranking (SERANKING_API_KEY)."}
    cabeceras = {"Authorization": f"Token {clave}"}
    try:
        log("Consultando la auditoría de SE Ranking…")
        total = 1
        if audit_id:
            auditoria = _auditoria_por_id(audit_id, dominio, cabeceras)
        else:
            auditoria, total = _buscar_auditoria(dominio, cabeceras)
            if not auditoria:
                return {"disponible": False,
                        "motivo": f"SE Ranking no tiene ninguna auditoría terminada de {dominio}."}
            audit_id = auditoria["id"]
        r = requests.get(f"{BASE_URL}/report", headers=cabeceras,
                         params={"audit_id": audit_id}, timeout=TIMEOUT)
        r.raise_for_status()
        informe = r.json()
        stats = (auditoria or {}).get("stats") or {}
        url = (auditoria or {}).get("url") or informe.get("domain_props", {}).get("domain", "")
        if _host(url) and _host(url) != _host(dominio):
            log(f"Aviso: la auditoría {audit_id} es de {url}, no de {dominio}.")
        return {
            "disponible": True,
            "audit_id": audit_id,
            "url": url,
            "fecha": (auditoria or {}).get("last_update") or (informe.get("updated") or "")[:10],
            "otras_auditorias": max(total - 1, 0),
            "puntuacion": stats.get("score"),
            "errores": informe.get("total_errors", stats.get("errors", 0)),
            "avisos": informe.get("total_warnings", stats.get("warnings", 0)),
            "info": informe.get("total_notices", stats.get("notices", 0)),
            "paginas": informe.get("total_pages", stats.get("crawled", 0)),
            "problemas": _problemas(informe),
        }
    except requests.HTTPError as e:
        codigo = e.response.status_code if e.response is not None else "?"
        return {"disponible": False, "motivo": f"SE Ranking respondió con error HTTP {codigo}."}
    except (requests.RequestException, ValueError, KeyError) as e:
        return {"disponible": False, "motivo": f"No se pudo consultar SE Ranking ({type(e).__name__})."}
