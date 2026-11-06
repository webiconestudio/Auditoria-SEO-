# Auditoría técnica, SEO y GEO

Genera un informe PDF de auditoría a partir de un dominio.

## Instalación (una sola vez)

1. Tener Python 3.10 o superior instalado.
2. Doble clic en `instalar.bat`.

El PDF se genera con Microsoft Edge (o Chrome), que ya viene en Windows. No hace falta WeasyPrint ni GTK.

## Uso

Doble clic en `auditar.bat` y escribir el dominio y el nombre del cliente.

O desde la consola:

```
python auditoria.py laimprentadeinternet.com --cliente "La Imprenta de Internet"
```

El informe se guarda en la carpeta `informes/` como PDF, junto con un `.json` con todos los datos medidos.

## Qué hace

- Elige hasta 8 páginas principales a partir del sitemap (o del menú si no hay sitemap). Deja fuera las páginas `noindex`, legales, carrito y cuenta, e incluye el artículo más reciente del blog si existe.
- Descarga como máximo 30 páginas, con una pausa entre peticiones.
- Comprueba SSL, robots.txt (bots de IA), viewport, canonical, idioma, H1, jerarquía de encabezados, imágenes (alt y peso), longitud del texto, negritas, enlaces rotos y anchors, titles y descriptions, Schema (incluido `@graph`), FAQ, respuestas directas, tablas y autoría.

## Archivos

| Archivo | Contenido |
| --- | --- |
| `auditoria.py` | Programa principal |
| `auditor.py` | Rastreo y mediciones |
| `evaluacion.py` | Reglas: estado, hallazgo y acción de cada fila |
| `informe.py` | Generación del PDF |
| `plantilla/informe.html` | Diseño del informe; se puede cambiar sin tocar el código |

## SE Ranking (opcional)

Si hay una clave de API configurada, el informe incluye una sección con el rastreo completo del sitio
(puntuación de salud, errores y avisos). Se usa la auditoría terminada más reciente del dominio.
Si no hay clave o falla la conexión, el informe se genera igualmente sin esa sección.

Configurar la clave (una de las dos formas):

1. Copiar `.env.example` como `.env` y escribir la clave tras `SERANKING_API_KEY=`.
2. O definir la variable de entorno `SERANKING_API_KEY`.

El archivo `.env` no debe compartirse ni subirse a ningún repositorio.
