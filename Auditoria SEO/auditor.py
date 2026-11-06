"""Motor de la auditoría técnica, SEO y GEO.

Rastrea la web, elige las páginas principales y ejecuta las comprobaciones.
Devuelve un diccionario con todos los resultados, que luego se usa para el PDF.
"""

import json
import re
import socket
import ssl
import time
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone
from urllib import robotparser
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36 AuditoriaSEO/1.0"
)
TIMEOUT = 15
PAUSA = 0.3            # segundos entre peticiones
MAX_PETICIONES = 30    # páginas HTML descargadas como máximo
NUM_URLS = 8           # páginas que aparecen en el informe
MAX_IMAGENES = 60      # imágenes cuyo peso se comprueba
MAX_ENLACES = 40       # enlaces internos que se comprueban
PESO_MAX_IMG = 400 * 1024

BOTS_IA = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot",
           "PerplexityBot", "Google-Extended", "CCBot"]

EXCLUIR = re.compile(
    r"(carrito|cart|checkout|finalizar-compra|mi-cuenta|my-account|cuenta|login|"
    r"wp-login|wp-admin|registro|aviso-legal|legal|privacidad|privacy|cookies|"
    r"terminos|condiciones|terms|feed|/tag/|/etiqueta/|/author/|/autor/|"
    r"\?|#|\.(pdf|jpe?g|png|gif|webp|svg|zip|xml|css|js|mp4|docx?)$)", re.I)

ANCLAS_GENERICAS = {"haz clic aquí", "haz click aquí", "clic aquí", "click aquí",
                    "pincha aquí", "aquí", "leer más", "lee más", "ver más", "más",
                    "más información", "saber más", "click here", "read more",
                    "here", "more", "info"}

CORRECTO, ADVERTENCIA, ERROR, NO_VERIFICADO = "correcto", "advertencia", "error", "no_verificado"


class Auditor:
    def __init__(self, dominio, log=print):
        dominio = dominio.strip()
        if not re.match(r"^https?://", dominio):
            dominio = "https://" + dominio
        p = urlparse(dominio)
        self.base = f"{p.scheme}://{p.netloc}"
        self.host = p.hostname
        self.dominio = p.netloc
        self.log = log
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": USER_AGENT,
                               "Accept-Language": "es-ES,es;q=0.9"})
        self.peticiones = 0
        self.cache = {}

    # ------------------------------------------------------------------
    # Utilidades de red
    # ------------------------------------------------------------------
    def get(self, url, **kw):
        time.sleep(PAUSA)
        return self.s.get(url, timeout=TIMEOUT, **kw)

    def pagina(self, url):
        """Descarga una página HTML (con caché y límite de peticiones)."""
        if url in self.cache:
            return self.cache[url]
        if self.peticiones >= MAX_PETICIONES:
            return None
        self.peticiones += 1
        try:
            r = self.get(url)
        except requests.RequestException as e:
            self.cache[url] = {"url": url, "error": str(e)}
            return self.cache[url]
        tipo = r.headers.get("Content-Type", "")
        if "charset" not in tipo.lower():
            m = re.search(rb'<meta[^>]+charset=["\']?([\w-]+)', r.content[:4096], re.I)
            r.encoding = m.group(1).decode() if m else "utf-8"
        datos = {"url": url, "final": r.url, "status": r.status_code,
                 "headers": dict(r.headers), "html": r.text if "html" in tipo else ""}
        self.cache[url] = datos
        return datos

    def interna(self, url):
        h = urlparse(url).hostname or ""
        return h.replace("www.", "") == (self.host or "").replace("www.", "")

    @staticmethod
    def normaliza(url):
        p = urlparse(url)
        ruta = p.path or "/"
        return urlunparse((p.scheme, p.netloc, ruta, "", "", ""))

    # ------------------------------------------------------------------
    # 1. Descubrimiento de páginas
    # ------------------------------------------------------------------
    def leer_sitemap(self, url, profundidad=0):
        """Devuelve [(url, lastmod, nombre_del_sitemap)]."""
        if profundidad > 2:
            return []
        try:
            r = self.get(url)
            if r.status_code != 200 or "<" not in r.text[:200]:
                return []
            raiz = ET.fromstring(r.content)
        except Exception:
            return []
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        salida = []
        if raiz.tag.endswith("sitemapindex"):
            for sm in raiz.findall("s:sitemap", ns):
                loc = (sm.findtext("s:loc", default="", namespaces=ns) or "").strip()
                nombre = loc.rsplit("/", 1)[-1].lower()
                # Nos saltamos sitemaps de autores, etiquetas e imágenes
                if re.search(r"author|tag|etiqueta|image|video", nombre):
                    continue
                salida += self.leer_sitemap(loc, profundidad + 1)
        else:
            nombre = url.rsplit("/", 1)[-1].lower()
            for u in raiz.findall("s:url", ns):
                loc = (u.findtext("s:loc", default="", namespaces=ns) or "").strip()
                lastmod = (u.findtext("s:lastmod", default="", namespaces=ns) or "").strip()
                if loc:
                    salida.append((loc, lastmod, nombre))
        return salida

    def enlaces_menu(self, html, url_base):
        soup = BeautifulSoup(html, "html.parser")
        zonas = soup.select("nav, header, [role=navigation], .menu, #menu")
        enlaces = []
        for z in zonas or [soup]:
            for a in z.find_all("a", href=True):
                u = self.normaliza(urljoin(url_base, a["href"]))
                if self.interna(u) and u not in enlaces:
                    enlaces.append(u)
        return enlaces

    def descubrir(self, robots_txt):
        """Elige las páginas principales: portada, menú y sitemap."""
        self.log("Buscando las páginas principales…")
        sitemaps = re.findall(r"(?im)^\s*sitemap:\s*(\S+)", robots_txt or "")
        sitemaps += [self.base + p for p in ("/sitemap_index.xml", "/sitemap.xml", "/wp-sitemap.xml")]
        entradas, fuente = [], "menú de la portada"
        for sm in dict.fromkeys(sitemaps):
            entradas = self.leer_sitemap(sm)
            if entradas:
                fuente = f"sitemap ({sm})"
                break

        portada = self.pagina(self.base + "/")
        menu = self.enlaces_menu(portada["html"], portada.get("final", self.base)) \
            if portada and portada.get("html") else []

        def es_post(nombre):
            return bool(re.search(r"post-sitemap|posts-post|entradas", nombre))

        paginas_sm = [self.normaliza(u) for u, _, n in entradas if not es_post(n)]
        posts = sorted([(lm, self.normaliza(u)) for u, lm, n in entradas if es_post(n)], reverse=True)

        candidatas = [self.normaliza(self.base + "/")]
        # 1º: páginas del menú (que estén en el sitemap si lo hay)
        for u in menu:
            if not paginas_sm or u in paginas_sm:
                candidatas.append(u)
        # 2º: resto del sitemap, de menor a mayor profundidad
        candidatas += sorted(paginas_sm, key=lambda u: urlparse(u).path.count("/"))
        candidatas = [u for u in dict.fromkeys(candidatas)
                      if self.interna(u) and not EXCLUIR.search(u)]

        elegidas = []
        cupo = NUM_URLS - (1 if posts else 0)   # dejamos sitio a un artículo del blog
        for u in candidatas:
            if len(elegidas) >= cupo:
                break
            p = self.pagina(u)
            if self.valida(p):
                elegidas.append(p)
        for _, u in posts[:3]:
            if len(elegidas) >= NUM_URLS:
                break
            p = self.pagina(u)
            if self.valida(p) and p not in elegidas:
                p["es_articulo"] = True
                elegidas.append(p)
                break
        self.log(f"Páginas elegidas: {len(elegidas)} (fuente: {fuente})")
        return elegidas, fuente

    @staticmethod
    def valida(p):
        if not p or p.get("error") or p.get("status") != 200 or not p.get("html"):
            return False
        soup = BeautifulSoup(p["html"], "html.parser")
        rob = soup.find("meta", attrs={"name": re.compile("^robots$", re.I)})
        return not (rob and "noindex" in (rob.get("content") or "").lower())

    # ------------------------------------------------------------------
    # 2. Análisis de cada página
    # ------------------------------------------------------------------
    def analizar_pagina(self, p):
        soup = BeautifulSoup(p["html"], "html.parser")
        url = p["final"]
        d = {"url": url, "path": urlparse(url).path or "/", "es_articulo": p.get("es_articulo", False)}

        t = soup.find("title")
        d["title"] = t.get_text(strip=True) if t else ""
        md = soup.find("meta", attrs={"name": re.compile("^description$", re.I)})
        d["description"] = (md.get("content") or "").strip() if md else ""
        html_tag = soup.find("html")
        d["lang"] = (html_tag.get("lang") or "").strip() if html_tag else ""
        d["charset"] = bool(soup.find("meta", charset=True)) or \
            "charset" in p["headers"].get("Content-Type", "").lower()
        vp = soup.find("meta", attrs={"name": re.compile("^viewport$", re.I)})
        d["viewport"] = (vp.get("content") or "") if vp else ""
        can = soup.find("link", rel=lambda v: v and "canonical" in [x.lower() for x in (v if isinstance(v, list) else [v])])
        d["canonical"] = urljoin(url, can["href"]) if can and can.get("href") else ""

        # Encabezados
        d["h1"] = [h.get_text(" ", strip=True) for h in soup.find_all("h1")]
        niveles = [int(h.name[1]) for h in soup.find_all(re.compile("^h[1-6]$"))]
        saltos = []
        for a, b in zip(niveles, niveles[1:]):
            if b > a + 1:
                saltos.append(f"H{a}→H{b}")
        d["saltos"] = list(dict.fromkeys(saltos))

        # Contenido principal
        principal = soup.find("main") or soup.find("article") or soup.body or soup
        copia = BeautifulSoup(str(principal), "html.parser")
        for tag in copia(["script", "style", "noscript", "nav", "header", "footer", "aside", "form"]):
            tag.decompose()
        texto = copia.get_text(" ", strip=True)
        palabras = re.findall(r"\w+", texto)
        d["palabras"] = len(palabras)
        negrita = " ".join(b.get_text(" ", strip=True) for b in copia.find_all(["strong", "b"]))
        d["pct_negrita"] = round(100 * len(re.findall(r"\w+", negrita)) / max(1, len(palabras)), 1)

        # Respuesta directa: H2 seguido de un párrafo de 15–80 palabras
        h2s = copia.find_all("h2")
        directas = 0
        for h in h2s:
            sig = h.find_next(["p", "h1", "h2", "h3", "h4", "ul", "ol", "table"])
            if sig and sig.name == "p" and 15 <= len(re.findall(r"\w+", sig.get_text(" "))) <= 80:
                directas += 1
        d["h2_total"], d["h2_directas"] = len(h2s), directas

        # Preguntas en el texto
        d["preguntas"] = sum(1 for h in soup.find_all(re.compile("^h[2-6]$|^summary$|^dt$"))
                             if re.search(r"(^¿|\?$)", h.get_text(" ", strip=True)))

        # Tablas de datos
        d["tablas"] = sum(1 for tb in soup.find_all("table") if len(tb.find_all("tr")) >= 2)

        # Imágenes
        imgs = []
        for img in soup.find_all("img"):
            src = ""
            for attr in ("data-lazy-src", "data-src", "data-original", "src"):
                v = img.get(attr) or ""
                if v and not v.startswith("data:"):
                    src = v
                    break
            alt = img.get("alt")
            imgs.append({"src": urljoin(url, src) if src else "",
                         "alt": alt, "sin_alt": alt is None,
                         "decorativa": alt is not None and not alt.strip()})
        d["imagenes"] = imgs

        # Contenido mixto
        if url.startswith("https://"):
            mixto = [t.get("src") or t.get("href") for t in soup.find_all(["img", "script", "iframe", "source"])
                     if (t.get("src") or "").startswith("http://")]
            mixto += [l.get("href") for l in soup.find_all("link", rel=lambda v: v and "stylesheet" in v)
                      if (l.get("href") or "").startswith("http://")]
            d["mixto"] = mixto
        else:
            d["mixto"] = []

        # Enlaces
        internos, externos, genericos = [], [], []
        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            u = urljoin(url, href)
            (internos if self.interna(u) else externos).append(u)
            txt = a.get_text(" ", strip=True).lower().strip(" .:»›→")
            if txt in ANCLAS_GENERICAS:
                genericos.append(a.get_text(" ", strip=True))
        d["enlaces_internos"] = list(dict.fromkeys(self.normaliza(u) for u in internos))
        d["enlaces_externos"] = list(dict.fromkeys(externos))
        d["anclas_genericas"] = genericos

        # Schema JSON-LD (recorriendo @graph y anidados)
        tipos, autores, same_as, errores_ld = [], [], False, 0
        for s in soup.find_all("script", type=re.compile("ld\\+json", re.I)):
            try:
                datos = json.loads(s.string or s.get_text())
            except Exception:
                errores_ld += 1
                continue
            pila = [datos]
            while pila:
                n = pila.pop()
                if isinstance(n, list):
                    pila.extend(n)
                elif isinstance(n, dict):
                    t = n.get("@type")
                    for x in (t if isinstance(t, list) else [t] if t else []):
                        tipos.append(str(x))
                    if n.get("sameAs"):
                        same_as = True
                    if "author" in n:
                        au = n["author"]
                        for a in (au if isinstance(au, list) else [au]):
                            if isinstance(a, dict):
                                autores.append(a.get("name") or a.get("@id") or "")
                            else:
                                autores.append(str(a))
                    pila.extend(n.values())
        d["schema_tipos"] = sorted(set(tipos))
        d["schema_sameas"] = same_as
        d["schema_errores"] = errores_ld
        ma = soup.find("meta", attrs={"name": re.compile("^author$", re.I)})
        if ma and ma.get("content"):
            autores.append(ma["content"])
        visibles = soup.select("[rel~=author], .author, .byline, .entry-author, .post-author")
        autores += [v.get_text(" ", strip=True) for v in visibles if v.get_text(strip=True)]
        d["autores"] = [a for a in dict.fromkeys(a.strip() for a in autores) if a]
        return d

    # ------------------------------------------------------------------
    # 3. Comprobaciones globales
    # ------------------------------------------------------------------
    def check_ssl(self):
        r = {"valido": False, "dias": None, "redirige_https": None, "hsts": False, "error": ""}
        try:
            ctx = ssl.create_default_context()
            with socket.create_connection((self.host, 443), timeout=8) as sock:
                with ctx.wrap_socket(sock, server_hostname=self.host) as s:
                    cert = s.getpeercert()
            caduca = datetime.strptime(cert["notAfter"], "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
            r["valido"] = True
            r["dias"] = (caduca - datetime.now(timezone.utc)).days
        except Exception as e:
            r["error"] = str(e)[:150]
        try:
            h = self.get(f"http://{self.dominio}/", allow_redirects=True)
            r["redirige_https"] = h.url.startswith("https://")
        except requests.RequestException:
            pass
        try:
            h = self.get(f"https://{self.dominio}/")
            r["hsts"] = "strict-transport-security" in {k.lower() for k in h.headers}
        except requests.RequestException:
            pass
        return r

    def check_robots(self):
        try:
            r = self.get(self.base + "/robots.txt")
        except requests.RequestException:
            return {"existe": False, "texto": "", "bloqueados": [], "google_ok": None}
        if r.status_code != 200:
            return {"existe": False, "texto": "", "bloqueados": [], "google_ok": True}
        rp = robotparser.RobotFileParser()
        rp.parse(r.text.splitlines())
        prueba = self.base + "/"
        bloqueados = [b for b in BOTS_IA if not rp.can_fetch(b, prueba)]
        return {"existe": True, "texto": r.text, "bloqueados": bloqueados,
                "google_ok": rp.can_fetch("Googlebot", prueba)}

    def comprobar_imagenes(self, paginas):
        unicas = list(dict.fromkeys(i["src"] for p in paginas for i in p["imagenes"] if i["src"]))
        pesadas, formatos = [], Counter()
        for src in unicas:
            ext = urlparse(src).path.rsplit(".", 1)[-1].lower() if "." in urlparse(src).path else "?"
            formatos[ext] += 1
        for src in unicas[:MAX_IMAGENES]:
            try:
                h = self.s.head(src, timeout=8, allow_redirects=True)
                tam = int(h.headers.get("Content-Length") or 0)
                if tam > PESO_MAX_IMG:
                    pesadas.append((src, tam))
            except (requests.RequestException, ValueError):
                pass
        return {"total": len(unicas), "revisadas": min(len(unicas), MAX_IMAGENES),
                "pesadas": pesadas, "formatos": dict(formatos)}

    def comprobar_enlaces(self, paginas):
        unicos = list(dict.fromkeys(u for p in paginas for u in p["enlaces_internos"]
                                    if not EXCLUIR.search(u)))
        rotos = []
        for u in unicos[:MAX_ENLACES]:
            try:
                h = self.s.head(u, timeout=8, allow_redirects=True)
                if h.status_code == 405:
                    h = self.s.get(u, timeout=8, stream=True)
                if h.status_code >= 400:
                    rotos.append((u, h.status_code))
            except requests.RequestException:
                rotos.append((u, "sin respuesta"))
        return {"revisados": min(len(unicos), MAX_ENLACES), "rotos": rotos}

    # ------------------------------------------------------------------
    # 4. Orquestación
    # ------------------------------------------------------------------
    def ejecutar(self):
        self.log(f"Analizando {self.dominio}…")
        robots = self.check_robots()
        self.log("Comprobando certificado SSL y HTTPS…")
        ssl_info = self.check_ssl()
        elegidas, fuente = self.descubrir(robots["texto"])
        if not elegidas:
            raise RuntimeError(f"No se ha podido descargar ninguna página de {self.dominio}.")
        self.log("Analizando el contenido de cada página…")
        paginas = [self.analizar_pagina(p) for p in elegidas]
        self.log("Revisando el peso de las imágenes…")
        imagenes = self.comprobar_imagenes(paginas)
        self.log("Revisando enlaces internos…")
        enlaces = self.comprobar_enlaces(paginas)
        return {"dominio": self.dominio, "fecha": datetime.now().strftime("%d/%m/%Y"),
                "fuente_urls": fuente, "robots": {k: v for k, v in robots.items() if k != "texto"},
                "ssl": ssl_info, "paginas": paginas, "imagenes": imagenes, "enlaces": enlaces}
