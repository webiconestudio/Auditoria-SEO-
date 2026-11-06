"""Auditoría técnica, SEO y GEO de un dominio.

Uso:
    python auditoria.py laimprentadeinternet.com
    python auditoria.py laimprentadeinternet.com --cliente "La Imprenta de Internet"
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

from auditor import Auditor
from evaluacion import evaluar
from informe import generar_pdf
import seranking

BASE = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description="Genera un informe PDF de auditoría técnica, SEO y GEO.")
    ap.add_argument("dominio", nargs="?", help="Dominio a auditar, por ejemplo: midominio.com")
    ap.add_argument("--cliente", default="", help="Nombre del cliente para la portada del informe")
    ap.add_argument("--salida", default=str(BASE / "informes"), help="Carpeta donde se guarda el informe")
    ap.add_argument("--audit-id", type=int, default=None,
                    help="ID de la auditoría de SE Ranking (si se omite, se usa la más reciente)")
    a = ap.parse_args()

    dominio = a.dominio or input("Dominio a auditar (ej. midominio.com): ").strip()
    if not dominio:
        print("No se ha indicado ningún dominio.")
        return 1
    cliente = a.cliente
    if not a.dominio and not cliente:
        cliente = input("Nombre del cliente (opcional, Intro para omitir): ").strip()

    audit_id = a.audit_id
    if not a.dominio:  # modo interactivo (doble clic en auditar.bat)
        
        if seranking.leer_clave():
            txt = input("ID de la auditoría de SE Ranking (Intro para usar la más reciente): ").strip()
            if txt.isdigit():
                audit_id = int(txt)
            elif txt:
                print("  · ID no válido; se usará la auditoría más reciente.")

    try:
        datos = Auditor(dominio, log=lambda m: print("  ·", m)).ejecutar()
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return 1

    sr = seranking.obtener(datos["dominio"], log=lambda m: print("  ·", m), audit_id=audit_id)
    if not sr["disponible"]:
        print(f"  · SE Ranking omitido: {sr['motivo']}")
    datos["seranking"] = sr

    informe = evaluar(datos, cliente)
    nombre = re.sub(r"[^a-z0-9]+", "_", datos["dominio"].lower()).strip("_")
    fecha = datos["fecha"].replace("/", "-")
    salida = Path(a.salida)
    salida.mkdir(parents=True, exist_ok=True)
    (salida / f"auditoria_{nombre}_{fecha}.json").write_text(
        json.dumps({"medido": datos, "informe": informe}, ensure_ascii=False, indent=1), encoding="utf-8")

    print("  · Generando el PDF…")
    try:
        pdf = generar_pdf(informe, salida / f"auditoria_{nombre}_{fecha}.pdf")
    except Exception as e:
        print(f"\n[ERROR] {e}")
        return 1
    print(f"\n[OK] Informe generado: {pdf}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
