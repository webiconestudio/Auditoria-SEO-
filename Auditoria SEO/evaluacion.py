"""Convierte los datos medidos en filas del informe: estado, hallazgo y acción."""

import re
from collections import Counter
from urllib.parse import urlparse

from auditor import ADVERTENCIA, CORRECTO, ERROR, NO_VERIFICADO

ORDEN = {CORRECTO: 0, NO_VERIFICADO: 0, ADVERTENCIA: 1, ERROR: 2}


def fila(elemento, estado, hallazgo, accion):
    return {"elemento": elemento, "estado": estado, "hallazgo": hallazgo, "accion": accion}


def pl(n, singular, plural):
    return f"{n} {singular if n == 1 else plural}"


CORTO = {"Certificado SSL & HTTPS": "certificado SSL", "Archivo robots.txt & Rastreadores IA": "robots.txt",
         "Diseño Adaptativo (Responsive)": "responsive", "Metadatos Técnicos & Canonical": "canonical",
         "Etiquetas de Idioma y Charset": "idioma y charset", "Encabezado Principal (H1)": "H1",
         "Estructura Jerárquica (H2 - H6)": "jerarquía de encabezados", "Optimización de Imágenes": "imágenes",
         "Longitud y Profundidad del Texto": "longitud del texto", "Uso de Negritas y Escaneabilidad": "negritas",
         "Enlazado Interno y Externo": "enlazado", "Metatags (Title & Meta Description)": "title y description",
         "Datos Estructurados (Schema.org)": "Schema", "Módulo de Preguntas Frecuentes (FAQ)": "FAQ",
         "Formato de Respuesta Directa (AEO)": "respuestas directas", "Tablas de Datos y Comparativas": "tablas de datos",
         "Claridad de Autoría y E-E-A-T": "autoría"}


def lista(rutas, n=3):
    rutas = list(rutas)
    txt = ", ".join(rutas[:n])
    return txt + (f" y {len(rutas) - n} más" if len(rutas) > n else "")


def misma_url(a, b):
    def n(u):
        p = urlparse(u)
        return (p.hostname or "").replace("www.", ""), (p.path or "/").rstrip("/") or "/"
    return n(a) == n(b)


# ----------------------------------------------------------------------
# 1. Infraestructura
# ----------------------------------------------------------------------
def seccion_infraestructura(r):
    P = r["paginas"]
    filas = []

    s = r["ssl"]
    mixto = [p["path"] for p in P if p["mixto"]]
    if not s["valido"]:
        filas.append(fila("Certificado SSL & HTTPS", ERROR,
                          f"El certificado no es válido o el puerto 443 no responde ({s['error']}).",
                          "Instalar un certificado válido (por ejemplo, Let's Encrypt) y forzar HTTPS."))
    else:
        partes = [f"Certificado válido (caduca en {s['dias']} días)."]
        acciones, estado = [], CORRECTO
        if s["redirige_https"] is False:
            partes.append("La versión http no redirige a https.")
            acciones.append("Redirigir con 301 todo el tráfico http a https.")
            estado = ADVERTENCIA
        if mixto:
            partes.append(f"Contenido mixto (recursos http) en {lista(mixto)}.")
            acciones.append("Cargar todos los recursos por https.")
            estado = ADVERTENCIA
        if s["dias"] is not None and s["dias"] < 15:
            partes.append("Caduca en menos de 15 días.")
            acciones.append("Renovar el certificado cuanto antes.")
            estado = ADVERTENCIA
        if estado == CORRECTO:
            partes.append("HTTPS activo en todo el dominio y sin contenido mixto.")
        partes.append("HSTS activo." if s["hsts"] else "Sin cabecera HSTS.")
        if not acciones:
            acciones.append("Mantener la renovación automática" +
                            ("." if s["hsts"] else " y activar HSTS."))
        filas.append(fila("Certificado SSL & HTTPS", estado, " ".join(partes), " ".join(acciones)))

    rb = r["robots"]
    if not rb["existe"]:
        filas.append(fila("Archivo robots.txt & Rastreadores IA", ADVERTENCIA,
                          "No hay archivo robots.txt; todos los rastreadores tienen acceso libre.",
                          "Crear un robots.txt que declare el sitemap y las reglas para bots de IA."))
    elif rb["google_ok"] is False:
        filas.append(fila("Archivo robots.txt & Rastreadores IA", ERROR,
                          "robots.txt bloquea a Googlebot en la portada.",
                          "Eliminar el bloqueo a Googlebot de inmediato."))
    elif rb["bloqueados"]:
        filas.append(fila("Archivo robots.txt & Rastreadores IA", ADVERTENCIA,
                          f"Permite Googlebot pero bloquea {', '.join(rb['bloqueados'])}.",
                          "Abrir el acceso a los rastreadores de motores generativos que interesen (GEO)."))
    else:
        filas.append(fila("Archivo robots.txt & Rastreadores IA", CORRECTO,
                          "Permite Googlebot y los principales bots de IA (GPTBot, ClaudeBot, PerplexityBot, Google-Extended).",
                          "Revisar el archivo tras cambios de plugins o de servidor."))

    sin_vp = [p["path"] for p in P if "width=device-width" not in p["viewport"].replace(" ", "")]
    if len(sin_vp) == len(P):
        filas.append(fila("Diseño Adaptativo (Responsive)", ERROR,
                          "Ninguna página declara la etiqueta viewport para móviles.",
                          'Añadir <meta name="viewport" content="width=device-width, initial-scale=1">.'))
    elif sin_vp:
        filas.append(fila("Diseño Adaptativo (Responsive)", ADVERTENCIA,
                          f"Falta la etiqueta viewport en {lista(sin_vp)}.",
                          "Añadir la etiqueta viewport en esas plantillas."))
    else:
        filas.append(fila("Diseño Adaptativo (Responsive)", CORRECTO,
                          "Viewport correctamente declarado en todas las páginas analizadas.",
                          "Revisar periódicamente la experiencia en móvil y la velocidad de carga."))

    sin_can = [p["path"] for p in P if not p["canonical"]]
    otra = [p["path"] for p in P if p["canonical"] and not misma_url(p["canonical"], p["url"])]
    if sin_can or otra:
        partes = []
        if sin_can:
            partes.append(f"Sin etiqueta canonical en {lista(sin_can)}.")
        if otra:
            partes.append(f"Canonical apuntando a otra URL en {lista(otra)}.")
        filas.append(fila("Metadatos Técnicos & Canonical", ADVERTENCIA, " ".join(partes),
                          "Añadir canonical autorreferenciada y revisar las que apuntan a otra URL."))
    else:
        filas.append(fila("Metadatos Técnicos & Canonical", CORRECTO,
                          "Etiquetas canonical autorreferenciadas en todas las URL principales.",
                          "Verificar la coherencia tras futuras migraciones o cambios de URL."))

    sin_lang = [p["path"] for p in P if not p["lang"]]
    sin_charset = [p["path"] for p in P if not p["charset"]]
    langs = sorted({p["lang"] for p in P if p["lang"]})
    if sin_lang or sin_charset:
        partes = []
        if sin_lang:
            partes.append(f"Falta el atributo lang en {lista(sin_lang)}.")
        if sin_charset:
            partes.append(f"Charset no declarado en {lista(sin_charset)}.")
        filas.append(fila("Etiquetas de Idioma y Charset", ADVERTENCIA, " ".join(partes),
                          'Configurar <html lang="es"> y <meta charset="UTF-8"> en todas las plantillas.'))
    else:
        filas.append(fila("Etiquetas de Idioma y Charset", CORRECTO,
                          f"Idioma declarado ({', '.join(langs)}) y charset presente en todas las páginas.",
                          "Mantener la configuración en nuevas plantillas."))
    return filas


# ----------------------------------------------------------------------
# 2. SEO on-page
# ----------------------------------------------------------------------
def seccion_seo(r):
    P = r["paginas"]
    filas = []

    mal_h1 = [(p["path"], len(p["h1"])) for p in P if len(p["h1"]) != 1]
    if mal_h1:
        varios = [x for x, n in mal_h1 if n > 1]
        ninguno = [x for x, n in mal_h1 if n == 0]
        partes = []
        if varios:
            partes.append(f"Varias etiquetas H1 en {lista(varios)}.")
        if ninguno:
            partes.append(f"Sin H1 en {lista(ninguno)}.")
        filas.append(fila("Encabezado Principal (H1)", ERROR, " ".join(partes),
                          "Dejar un único H1 descriptivo por página con la keyword principal."))
    else:
        filas.append(fila("Encabezado Principal (H1)", CORRECTO,
                          f"Las {len(P)} páginas tienen un único H1.",
                          "Mantener un H1 por página al crear contenido nuevo."))

    saltos = [f"{p['path']} ({', '.join(p['saltos'][:2])})" for p in P if p["saltos"]]
    if saltos:
        filas.append(fila("Estructura Jerárquica (H2 - H6)", ADVERTENCIA,
                          f"Saltos de nivel en {lista(saltos, 2)}.",
                          "Ordenar los encabezados H1 > H2 > H3 sin omitir niveles."))
    else:
        filas.append(fila("Estructura Jerárquica (H2 - H6)", CORRECTO,
                          "Jerarquía de encabezados sin saltos de nivel.",
                          "Mantener la estructura en contenidos nuevos."))

    imgs = [i for p in P for i in p["imagenes"]]
    sin_alt = sum(1 for i in imgs if i["sin_alt"])
    decor = sum(1 for i in imgs if i["decorativa"])
    pesadas = r["imagenes"]["pesadas"]
    fmts = r["imagenes"]["formatos"]
    modernos = fmts.get("webp", 0) + fmts.get("avif", 0)
    total_u = max(1, sum(fmts.values()))
    partes = [f"{pl(len(imgs), 'imagen', 'imágenes')} en {pl(len(P), 'página', 'páginas')}."]
    estado, acciones = CORRECTO, []
    if sin_alt:
        partes.append(f"{sin_alt} sin atributo alt.")
        estado = ADVERTENCIA
        acciones.append("Redactar textos alt descriptivos.")
    if decor:
        partes.append(f"{decor} con alt vacío (correcto si {'es decorativa' if decor == 1 else 'son decorativas'}).")
    if pesadas:
        partes.append(f"{len(pesadas)} {'pesa' if len(pesadas) == 1 else 'pesan'} más de 400 KB.")
        estado = ADVERTENCIA
        acciones.append("Comprimir las imágenes pesadas.")
    partes.append(f"{round(100 * modernos / total_u)}% en WebP/AVIF.")
    if modernos / total_u < 0.5:
        acciones.append("Pasar a WebP o AVIF.")
        estado = ADVERTENCIA if estado == CORRECTO and sum(fmts.values()) > 5 else estado
    filas.append(fila("Optimización de Imágenes", estado, " ".join(partes),
                      " ".join(acciones) or "Mantener alt descriptivos y formatos ligeros."))

    pal = {p["path"]: p["palabras"] for p in P}
    cortas = [x for x, n in pal.items() if n < 300]
    rango = f"Entre {min(pal.values())} y {max(pal.values())} palabras por página."
    if cortas:
        filas.append(fila("Longitud y Profundidad del Texto", ADVERTENCIA,
                          f"{rango} Menos de 300 en {lista(cortas)}.",
                          "Ampliar esas páginas con contenido útil y original."))
    else:
        filas.append(fila("Longitud y Profundidad del Texto", CORRECTO, rango,
                          "Conservar la profundidad y actualizar el contenido periódicamente."))

    pcts = [p["pct_negrita"] for p in P]
    media = round(sum(pcts) / len(pcts), 1)
    excesivas = [p["path"] for p in P if p["pct_negrita"] > 15]
    if max(pcts) == 0:
        filas.append(fila("Uso de Negritas y Escaneabilidad", ADVERTENCIA,
                          "No se usan negritas en el contenido principal.",
                          "Marcar con <strong> los conceptos clave para facilitar la lectura."))
    elif excesivas:
        filas.append(fila("Uso de Negritas y Escaneabilidad", ADVERTENCIA,
                          f"Exceso de negrita (más del 15% del texto) en {lista(excesivas)}.",
                          "Reservar la negrita para conceptos clave, no para frases enteras."))
    else:
        filas.append(fila("Uso de Negritas y Escaneabilidad", CORRECTO,
                          f"Negrita en un {media}% del texto de media.",
                          "Evitar marcar frases enteras en negrita."))

    rotos = r["enlaces"]["rotos"]
    genericos = Counter(a for p in P for a in p["anclas_genericas"])
    externos = sum(len(p["enlaces_externos"]) for p in P)
    partes, acciones, estado = [], [], CORRECTO
    if rotos:
        partes.append(f"{pl(len(rotos), 'enlace interno roto', 'enlaces internos rotos')} ({lista(urlparse(u).path for u, _ in rotos)}).")
        acciones.append("Corregir o redirigir los enlaces rotos.")
        estado = ERROR
    if genericos:
        top = ", ".join(f'"{a}"' for a, _ in genericos.most_common(3))
        partes.append(f"Anchors genéricos: {top}.")
        acciones.append("Usar textos ancla descriptivos.")
        estado = max(estado, ADVERTENCIA, key=ORDEN.get)
    if externos == 0:
        partes.append("Sin enlaces a fuentes externas.")
        acciones.append("Enlazar fuentes externas de autoridad.")
        estado = max(estado, ADVERTENCIA, key=ORDEN.get)
    if not partes:
        partes.append(f"Sin enlaces rotos entre los {r['enlaces']['revisados']} revisados y anchors descriptivos.")
        acciones.append("Revisar los enlaces tras cambios de URL.")
    filas.append(fila("Enlazado Interno y Externo", estado, " ".join(partes), " ".join(acciones)))

    titulos = Counter(p["title"] for p in P if p["title"])
    descs = Counter(p["description"] for p in P if p["description"])
    sin_t = [p["path"] for p in P if not p["title"]]
    sin_d = [p["path"] for p in P if not p["description"]]
    dup_t = [p["path"] for p in P if p["title"] and titulos[p["title"]] > 1]
    dup_d = [p["path"] for p in P if p["description"] and descs[p["description"]] > 1]
    largo_t = [p["path"] for p in P if len(p["title"]) > 60]
    mal_d = [p["path"] for p in P if p["description"] and not 70 <= len(p["description"]) <= 160]
    partes, estado = [], CORRECTO
    if sin_t or sin_d or dup_t or dup_d:
        estado = ERROR
    elif largo_t or mal_d:
        estado = ADVERTENCIA
    if sin_t: partes.append(f"Sin title en {lista(sin_t)}.")
    if sin_d: partes.append(f"Sin meta description en {lista(sin_d)}.")
    if dup_t: partes.append(f"Titles duplicados en {lista(dup_t)}.")
    if dup_d: partes.append(f"Descriptions duplicadas en {lista(dup_d)}.")
    if largo_t: partes.append(f"Title de más de 60 caracteres en {lista(largo_t)}.")
    if mal_d: partes.append(f"Description fuera de 70–160 caracteres en {lista(mal_d)}.")
    if estado == CORRECTO:
        partes.append("Titles y descriptions únicos y con longitud adecuada.")
    filas.append(fila("Metatags (Title & Meta Description)", estado, " ".join(partes),
                      "Redactar titles únicos (<60 car.) y descriptions orientadas al clic (<155 car.)."
                      if estado != CORRECTO else "Mantener titles y descriptions únicos en páginas nuevas."))
    return filas


# ----------------------------------------------------------------------
# 3. GEO
# ----------------------------------------------------------------------
def seccion_geo(r):
    P = r["paginas"]
    filas = []
    tipos = Counter(t for p in P for t in p["schema_tipos"])
    sin_schema = [p["path"] for p in P if not p["schema_tipos"]]
    org = any(t in tipos for t in ("Organization", "LocalBusiness", "Corporation", "Store", "ProfessionalService"))
    principales = [t for t in ("Organization", "LocalBusiness", "WebSite", "WebPage", "BreadcrumbList",
                               "Product", "Service", "Article", "FAQPage", "Person") if t in tipos]
    if len(sin_schema) == len(P):
        filas.append(fila("Datos Estructurados (Schema.org)", ERROR,
                          "No existe marcado JSON-LD en ninguna de las páginas analizadas.",
                          "Desplegar Schema de Organization y WebSite con sameAs hacia los perfiles corporativos."))
    else:
        partes = [f"JSON-LD detectado: {', '.join(principales or sorted(tipos)[:5])}."]
        acciones, estado = [], CORRECTO
        if sin_schema:
            partes.append(f"Sin Schema en {lista(sin_schema)}.")
            estado = ADVERTENCIA
            acciones.append("Añadir JSON-LD en esas páginas.")
        if not org:
            partes.append("Falta Organization o LocalBusiness.")
            estado = ADVERTENCIA
            acciones.append("Añadir Organization o LocalBusiness con datos de contacto.")
        elif not any(p["schema_sameas"] for p in P):
            partes.append("Sin sameAs hacia perfiles sociales.")
            estado = ADVERTENCIA
            acciones.append("Añadir sameAs con los perfiles corporativos.")
        if "Service" not in tipos and "Product" not in tipos:
            acciones.append("Valorar Schema Service o Product en las páginas comerciales.")
        filas.append(fila("Datos Estructurados (Schema.org)", estado, " ".join(partes),
                          " ".join(acciones) or "Mantener el marcado actualizado."))

    preguntas = sum(p["preguntas"] for p in P)
    if "FAQPage" in tipos:
        filas.append(fila("Módulo de Preguntas Frecuentes (FAQ)", CORRECTO,
                          "Preguntas frecuentes marcadas con Schema FAQPage.",
                          "Ampliar las FAQ con respuestas directas de 40-50 palabras."))
    elif preguntas:
        filas.append(fila("Módulo de Preguntas Frecuentes (FAQ)", ADVERTENCIA,
                          f"{pl(preguntas, 'pregunta', 'preguntas')} en el texto sin marcado FAQPage.",
                          "Implementar Schema FAQPage y redactar respuestas directas de 40-50 palabras."))
    else:
        filas.append(fila("Módulo de Preguntas Frecuentes (FAQ)", ADVERTENCIA,
                          "No hay sección de preguntas frecuentes en las páginas analizadas.",
                          "Crear bloques FAQ en las páginas de servicio con Schema FAQPage."))

    h2 = sum(p["h2_total"] for p in P)
    directas = sum(p["h2_directas"] for p in P)
    if not h2:
        filas.append(fila("Formato de Respuesta Directa (AEO)", ADVERTENCIA,
                          "Las páginas no usan subtítulos H2 (estimación automática).",
                          "Estructurar el contenido en secciones H2 con una respuesta breve al inicio."))
    else:
        pct = round(100 * directas / h2)
        estado = CORRECTO if pct >= 50 else ADVERTENCIA
        filas.append(fila("Formato de Respuesta Directa (AEO)", estado,
                          f"El {pct}% de los H2 empieza con un párrafo breve de respuesta (estimación automática).",
                          "Añadir una definición concisa justo debajo de cada encabezado principal."
                          if estado != CORRECTO else "Mantener el formato en contenidos nuevos."))

    tablas = sum(p["tablas"] for p in P)
    if tablas:
        filas.append(fila("Tablas de Datos y Comparativas", CORRECTO,
                          f"{pl(tablas, 'tabla HTML', 'tablas HTML')} con datos estructurados.",
                          "Usar tablas también en comparativas de precios y especificaciones."))
    else:
        filas.append(fila("Tablas de Datos y Comparativas", ADVERTENCIA,
                          "No hay tablas HTML en las páginas analizadas.",
                          "Presentar precios, formatos y especificaciones en tablas HTML para que los LLMs extraigan los datos."))

    articulos = [p for p in P if p["es_articulo"]]
    persona = "Person" in tipos
    autores = [a for p in (articulos or P) for a in p["autores"]]
    genericos = [a for a in autores if re.fullmatch(r"(?i)\s*(admin|administrador|administrator|redacción|editor|web)\s*", a)]
    if not articulos and not autores and not persona:
        filas.append(fila("Claridad de Autoría y E-E-A-T", NO_VERIFICADO,
                          "No hay artículos con autor entre las páginas analizadas.",
                          "Si hay blog, firmar los artículos con un autor real y su perfil."))
    elif genericos:
        filas.append(fila("Claridad de Autoría y E-E-A-T", ADVERTENCIA,
                          f"Contenido firmado genéricamente como \"{genericos[0]}\".",
                          "Crear perfiles de autor verificables con biografía y enlaces profesionales."))
    elif not autores and not persona:
        filas.append(fila("Claridad de Autoría y E-E-A-T", ADVERTENCIA,
                          "Los artículos no muestran autor.",
                          "Firmar los artículos y añadir Schema Person del autor."))
    else:
        nombre = autores[0] if autores else "autor identificado"
        filas.append(fila("Claridad de Autoría y E-E-A-T", CORRECTO,
                          f"Artículos firmados ({nombre})" + (" con Schema Person." if persona else "."),
                          "Enlazar el perfil del autor a sus credenciales profesionales."))
    return filas


# ----------------------------------------------------------------------
# 4. Desglose por URL
# ----------------------------------------------------------------------
def nombre_pagina(p):
    if p["path"] == "/":
        return "Página de Inicio"
    t = re.split(r"\s+[|\-–—]\s+", p["title"])[0].strip() if p["title"] else ""
    return (t[:45] + "…") if len(t) > 46 else t


def seccion_urls(r):
    P = r["paginas"]
    titulos = Counter(p["title"] for p in P if p["title"])
    descs = Counter(p["description"] for p in P if p["description"])
    rotos_por_pagina = {}
    rotos = {u for u, _ in r["enlaces"]["rotos"]}
    for p in P:
        rotos_por_pagina[p["path"]] = [u for u in p["enlaces_internos"] if u in rotos]
    filas = []
    for p in P:
        errores, avisos, acciones = [], [], []
        n = len(p["h1"])
        if n == 0:
            errores.append("Sin etiqueta H1.")
            acciones.append("Añadir un H1 con la keyword principal.")
        elif n > 1:
            errores.append(f"{n} etiquetas H1.")
            acciones.append("Dejar un solo H1.")
        if not p["title"]:
            errores.append("Sin title.")
            acciones.append("Redactar un title único (<60 car.).")
        elif titulos[p["title"]] > 1:
            errores.append("Title duplicado con otra página.")
            acciones.append("Redactar un title exclusivo.")
        elif len(p["title"]) > 60:
            avisos.append(f"Title de {len(p['title'])} caracteres.")
            acciones.append("Acortar el title a menos de 60 caracteres.")
        if not p["description"]:
            errores.append("Meta description vacía.")
            acciones.append("Redactar una description de ~145 caracteres con llamada a la acción.")
        elif descs[p["description"]] > 1:
            errores.append("Description duplicada.")
            acciones.append("Redactar una description exclusiva.")
        elif not 70 <= len(p["description"]) <= 160:
            avisos.append(f"Description de {len(p['description'])} caracteres.")
            acciones.append("Ajustar la description a 70–160 caracteres.")
        if p["saltos"]:
            avisos.append(f"Salto jerárquico ({', '.join(p['saltos'][:2])}).")
            acciones.append("Reestructurar los encabezados sin saltar niveles.")
        sin_alt = sum(1 for i in p["imagenes"] if i["sin_alt"])
        if sin_alt:
            avisos.append(f"{pl(sin_alt, 'imagen', 'imágenes')} sin atributo alt.")
            acciones.append("Añadir alt descriptivo a esas imágenes.")
        if not p["schema_tipos"]:
            errores.append("Sin Schema JSON-LD.")
            acciones.append("Añadir JSON-LD adecuado al tipo de página.")
        if not p["canonical"]:
            avisos.append("Sin canonical.")
            acciones.append("Añadir canonical autorreferenciada.")
        if p["palabras"] < 300:
            avisos.append(f"Solo {p['palabras']} palabras.")
            acciones.append("Ampliar el contenido.")
        if rotos_por_pagina[p["path"]]:
            errores.append(f"{pl(len(rotos_por_pagina[p['path']]), 'enlace interno roto', 'enlaces internos rotos')}.")
            acciones.append("Corregir los enlaces rotos.")
        if p["es_articulo"]:
            gen = [a for a in p["autores"] if re.fullmatch(r"(?i)\s*(admin|administrador|administrator|redacción|editor|web)\s*", a)]
            if gen:
                avisos.append(f'Firmado como "{gen[0]}" sin ficha de autor.')
                acciones.append("Asignar un autor real con foto y biografía.")
            elif not p["autores"]:
                avisos.append("Artículo sin autor visible.")
                acciones.append("Firmar el artículo con un autor real.")
        if p["preguntas"] and "FAQPage" not in p["schema_tipos"]:
            avisos.append("Preguntas sin Schema FAQPage.")
            acciones.append("Marcar las preguntas con FAQPage.")
        estado = "critico" if errores else ("atencion" if avisos else "correcto")
        hallazgos = " ".join(errores + avisos) or f"H1 único, metadatos correctos y Schema presente ({len(p['schema_tipos'])} tipos)."
        filas.append({"path": p["path"], "nombre": nombre_pagina(p), "estado": estado,
                      "hallazgo": hallazgos,
                      "accion": " ".join(dict.fromkeys(acciones)) or "Sin cambios necesarios."})
    return filas


# ----------------------------------------------------------------------
# 4. Rastreo completo con SE Ranking (opcional)
# ----------------------------------------------------------------------
ACCIONES_SR = [
    ("contenido mixto", "Cargar todos los recursos (imágenes, scripts, CSS) por HTTPS."),
    ("imágenes 4xx", "Restaurar las imágenes o corregir las rutas que apuntan a archivos inexistentes."),
    ("5xx", "Revisar el servidor y los logs: son errores internos que impiden cargar la página."),
    ("4xx", "Corregir o redirigir (301) las URLs rotas y actualizar los enlaces que apuntan a ellas."),
    ("3xx", "Enlazar directamente a la URL final en lugar de a la redirección."),
    ("falta la descripción", "Redactar una meta description única para cada página."),
    ("descripción", "Dejar una meta description única de entre 120 y 155 caracteres."),
    ("title", "Escribir un title único y descriptivo de entre 30 y 60 caracteres."),
    ("título", "Escribir un title único y descriptivo de entre 30 y 60 caracteres."),
    ("h1", "Dejar un único H1 distinto y descriptivo en cada página."),
    ("alt text", "Añadir texto alternativo descriptivo a las imágenes."),
    ("enlaces entrantes", "Enlazar estas páginas desde otras páginas relacionadas del sitio."),
    ("enlace interno entrante", "Reforzar el enlazado interno hacia estas páginas."),
    ("javascript", "Minificar, combinar y cachear los archivos JavaScript (plugin de caché o servidor)."),
    ("css", "Minificar, comprimir y cachear los archivos CSS (plugin de caché o servidor)."),
    ("velocidad", "Optimizar imágenes, caché y recursos para reducir el tiempo de carga."),
    ("texto a html", "Ampliar el contenido textual útil de las páginas."),
    ("www", "Redirigir (301) una de las dos versiones, con o sin www, a la otra."),
    ("layout shift", "Reservar el espacio de imágenes, anuncios y fuentes para que la página no se desplace al cargar."),
    ("certificado", "Revisar y renovar el certificado SSL."),
]


def accion_seranking(nombre):
    n = nombre.lower()
    for clave, accion in ACCIONES_SR:
        if clave in n:
            return accion
    return "Revisar en SE Ranking las URLs afectadas y corregirlas."


def seccion_seranking(sr, maximo=8):
    filas = []
    punt = sr.get("puntuacion")
    if punt is not None:
        estado = CORRECTO if punt >= 80 else ADVERTENCIA if punt >= 60 else ERROR
        filas.append(fila("Puntuación de salud del sitio", estado,
                          f"{punt}/100 en el rastreo de {pl(sr['paginas'], 'página', 'páginas')}.",
                          "Mantener la puntuación por encima de 80 corrigiendo primero los errores." if estado != CORRECTO
                          else "Mantener la revisión periódica del sitio."))
    e, a = sr["errores"], sr["avisos"]
    filas.append(fila("Errores del rastreo completo", ERROR if e else ADVERTENCIA if a else CORRECTO,
                      f"{pl(e, 'error', 'errores')} y {pl(a, 'aviso', 'avisos')} detectados.",
                      "Priorizar los errores sobre los avisos." if e or a else "Sin acciones pendientes."))
    problemas = sorted(sr["problemas"], key=lambda p: (p["estado"] != "error", -p["valor"]))
    for pr in problemas[:maximo]:
        filas.append(fila(pr["nombre"], ERROR if pr["estado"] == "error" else ADVERTENCIA,
                          pl(pr["valor"], "caso detectado", "casos detectados") + f" ({pr['seccion']}).",
                          accion_seranking(pr["nombre"])))
    return filas


def intro_seranking(sr):
    txt = (f"Rastreo completo de {sr['url'] or 'el sitio'} realizado por SE Ranking el {sr['fecha']} "
           f"({pl(sr['paginas'], 'página analizada', 'páginas analizadas')}). Se muestran los problemas más numerosos.")
    if sr.get("otras_auditorias"):
        txt += f" Hay {pl(sr['otras_auditorias'], 'otra auditoría', 'otras auditorías')} de este dominio en SE Ranking."
    return txt


# ----------------------------------------------------------------------
# Resumen
# ----------------------------------------------------------------------
def indicador(filas, correcto_txt):
    peor = max((f["estado"] for f in filas), key=ORDEN.get)
    malos = [f["elemento"] for f in filas if f["estado"] == peor and peor != CORRECTO]
    etiqueta = {CORRECTO: "Correcto", NO_VERIFICADO: "Correcto", ADVERTENCIA: "Advertencia", ERROR: "Crítico"}[peor]
    if peor in (CORRECTO, NO_VERIFICADO):
        texto = correcto_txt
    else:
        nombres = [CORTO.get(m, m) for m in malos]
        texto = ("Revisar: " if peor == ADVERTENCIA else "Corregir: ") + ", ".join(nombres[:3]) + "."
    return {"estado": peor, "etiqueta": etiqueta, "texto": texto}


def evaluar(r, cliente=""):
    s1, s2, s3 = seccion_infraestructura(r), seccion_seo(r), seccion_geo(r)
    sr = r.get("seranking")
    sr_ok = bool(sr and sr.get("disponible"))
    s4 = seccion_seranking(sr) if sr_ok else []
    indicadores = [
        {"nombre": "Desarrollo Web", **indicador(s1, "Base técnica sólida, responsive y segura.")},
        {"nombre": "SEO On-Page", **indicador(s2, "Estructura y metadatos bien optimizados.")},
        {"nombre": "Preparación GEO", **indicador(s3, "Contenido preparado para motores de IA.")},
    ]
    secciones = [
        {"titulo": "1. Infraestructura y Desarrollo Web",
         "intro": "Análisis de la base arquitectónica, seguridad, directivas de rastreo e indexabilidad técnica del sitio.",
         "filas": s1},
        {"titulo": "2. Optimización para Motores Tradicionales (SEO On-Page)",
         "intro": "Evaluación de la jerarquía textual, metatags de posicionamiento, enlazado y recursos multimedia.",
         "filas": s2},
        {"titulo": "3. Optimización para Motores Generativos e IA (GEO)",
         "intro": "Comprobación de la citabilidad, datos estructurados y preparación semántica para modelos como ChatGPT, Perplexity y Gemini.",
         "filas": s3},
    ]
    if sr_ok:
        indicadores.append({"nombre": "Rastreo completo", **indicador(s4, "Sin incidencias relevantes en el rastreo completo.")})
        secciones.append({"titulo": "4. Rastreo Completo del Sitio (SE Ranking)",
                          "intro": intro_seranking(sr), "filas": s4})
    return {
        "dominio": r["dominio"], "fecha": r["fecha"], "cliente": cliente or r["dominio"],
        "fuente_urls": r["fuente_urls"],
        "indicadores": indicadores,
        "secciones": secciones,
        "urls": seccion_urls(r),
    }
