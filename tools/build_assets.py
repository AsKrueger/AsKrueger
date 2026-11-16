"""Genera los SVG del README del perfil con la identidad visual del portfolio.

Uso:
    python tools/build_assets.py

Descarga las fuentes del portfolio, las recorta a los caracteres que se usan y
las incrusta en cada SVG, para que GitHub los muestre igual en cualquier equipo.
Cada pieza sale en versión oscura y clara (assets/<nombre>-dark.svg / -light.svg).

La actividad (assets/activity-*.svg) necesita un token de GitHub en GITHUB_TOKEN;
sin él se deja como está. La GitHub Action del repositorio la regenera cada día.
Con STATIC=1 los SVG salen sin animaciones (útil para revisarlos en capturas).
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import os
import urllib.request
from html import escape
from pathlib import Path

from fontTools import subset
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets"
FONT_URL = "https://askrueger.github.io/webportfolio/static/fonts/{}.woff2"
USER = "AsKrueger"

# --------------------------------------------------------------------------
# Contenido. Cambia aquí los datos y vuelve a ejecutar el script.
# --------------------------------------------------------------------------

FIRST_NAME = "Alonso"
LAST_NAME = "Amador Sánchez"
ROLE = "Desarrollador Junior"
FOCUS = "Android Kotlin · Backend Java"
STATUS = "Mérida · Remoto · Disponible ya"

# Respuesta del terminal de la cabecera: (texto, color del tema, peso)
REQUEST = "$ http GET :8080/api/v1/alonso"
RESPONSE = [
    ("HTTP/1.1 200 OK", "ok", 700),
    ("{", "muted", 400),
    ('  "rol": "Desarrollador Junior",', "json", 400),
    ('  "stack": ["Java", "Spring", "Kotlin"],', "json", 400),
    ('  "apps_en_google_play": 5,', "json", 400),
    ('  "tests": "200+",', "json", 400),
    ('  "disponible": true', "json", 400),
    ("}", "muted", 400),
]

STATS = [
    ("5", "apps en prueba cerrada", "en Google Play"),
    ("3", "APIs REST con PostgreSQL", "Spring Boot y NestJS"),
    ("200+", "tests automatizados", "unitarios, integración y UI"),
    ("Ya", "incorporación inmediata", "presencial, híbrido o remoto"),
]

STACK = [
    ("Backend", ["Java 21", "Spring Boot 3", "Spring Security", "JPA / Hibernate", "Kafka", "NestJS"]),
    ("Android", ["Kotlin", "Jetpack Compose", "Room", "WorkManager", "Retrofit", "MapLibre"]),
    ("Datos", ["PostgreSQL", "Flyway", "Prisma", "SQLite + FTS"]),
    ("Calidad", ["JUnit 5", "Mockito", "Testcontainers", "Vitest", "Playwright"]),
    ("DevOps", ["Docker", "GitHub Actions", "AWS", "Gradle", "Maven"]),
    ("Arquitectura", ["Hexagonal", "DDD táctico", "MVVM", "Offline-first"]),
]

# Trayectoria: (título, detalle, inicio, fin o None si sigue, tipo)
TIMELINE = [
    ("Grado en Turismo", "Universidad · gestión y atención al cliente", (2018, 9), (2024, 6), "edu"),
    ("Atención al cliente", "Recepción de hotel", (2022, 4), (2023, 8), "work"),
    ("Técnico Superior en DAM", "Java, Kotlin, C#, SQL · TFG: ExplorerSaga", (2023, 10), (2025, 12), "edu"),
    ("Desarrollador de aplicaciones", "Prácticas en remoto · C#, Unity, .NET", (2025, 9), (2026, 1), "work"),
    ("Apps propias", "5 apps en prueba cerrada en Google Play", (2026, 1), None, "build"),
]
TIMELINE_RANGE = ((2018, 1), (2027, 1))

# Proyectos destacados. El primero ocupa todo el ancho.
BANNER_URL = "https://askrueger.github.io/webportfolio/static/img/projects/{}/banner.webp"
PROJECTS = [
    dict(slug="explorersaga", name="ExplorerSaga Extremadura", tag="v2 · Kotlin + Python",
         eyebrow="EMPEZÓ COMO MI TFG",
         pitch="Toda Extremadura en el bolsillo, también sin cobertura.",
         points=["5.700+ lugares de OpenStreetMap, Wikidata y Wikipedia",
                 "Datos generados en Python, reproducibles byte a byte",
                 "Paquetes versionados con sha256; WorkManager los instala",
                 "Mapa vectorial y búsqueda sin tildes, todo offline"],
         chips=["103 tests", "Room + FTS4", "MapLibre"]),
    dict(slug="3d-cost-manager", name="3D Cost Manager", tag="v1.0.0 · Kotlin",
         pitch="El coste real de cada impresión 3D y a cuánto venderla en cada canal.",
         chips=["BigDecimal", "G-code y 3MF", "6 idiomas"]),
    dict(slug="training-arc", name="Training Arc", tag="v1.0.0 · Kotlin",
         pitch="Tu registro de entrenamientos convertido en un RPG de estética anime.",
         chips=["motor RPG puro", "34 tests", "883 ejercicios"]),
    dict(slug="animewatchlist", name="AnimeWatchlist", tag="v1.1.0 · Kotlin",
         pitch="Tu anime organizado y el calendario semanal de estrenos, sin cuenta.",
         chips=["8 versiones", "caché atómica", "AdMob + UMP"]),
    dict(slug="bingogoals", name="BingoGoals", tag="v0.1 · Kotlin + TS",
         pitch="Tus metas convertidas en un cartón de bingo. Con demo web.",
         chips=["84 tests", "tests de capturas", "Playwright"]),
]

PRINCIPLES = [
    ("Dominio primero", "Reglas de negocio en Kotlin o Java puro, separadas del framework y con sus tests."),
    ("Sin conexión primero", "Apps que guardan sus datos en el dispositivo y funcionan sin cobertura."),
    ("Tests de verdad", "JUnit, Mockito y Testcontainers; tests de interfaz y de capturas en Android."),
    ("Como en un equipo", "Issues, ramas, pull requests, versiones por fases, CI y ADRs, aunque sea solo mío."),
]

# --------------------------------------------------------------------------
# Tema (tokens del portfolio: static/css/style.css)
# --------------------------------------------------------------------------

THEMES = {
    "dark": dict(
        bg="#0c0e12", surface="#14181f", surface2="#1b2029", border="#262c37", text="#e8eaef",
        strong="#ffffff", muted="#9aa3b2", dim="#6b7383", accent="#f2a541", accent_rgb="242,165,65",
        teal="#4fd1c5", teal_soft="rgba(79,209,197,0.10)", violet="#c4a7ff", ok="#5ee08f",
        json="#c9d1dc", term="#090b0f",
        glow_a="rgba(242,165,65,0.16)", glow_b="rgba(79,209,197,0.10)", grid="rgba(255,255,255,0.045)",
    ),
    "light": dict(
        bg="#faf8f4", surface="#ffffff", surface2="#f3efe8", border="#e6e0d6", text="#23262d",
        strong="#0f1115", muted="#5a6170", dim="#8a8f9a", accent="#b45f06", accent_rgb="180,95,6",
        teal="#0f7d74", teal_soft="rgba(15,125,116,0.08)", violet="#6d3fd1", ok="#157a3f",
        json="#c9d1dc", term="#11141a",
        glow_a="rgba(242,165,65,0.20)", glow_b="rgba(79,209,197,0.14)", grid="rgba(0,0,0,0.05)",
    ),
}
# El terminal es oscuro en los dos temas: sus colores no cambian.
TERM = dict(ok="#5ee08f", muted="#6b7383", json="#c9d1dc", prompt="#f2a541", text="#e8eaef")

# --------------------------------------------------------------------------
# Fuentes y SVG
# --------------------------------------------------------------------------

FONTS = {
    "Inter": "inter-latin",
    "Bricolage Grotesque": "bricolage-latin",
    "JetBrains Mono": "jetbrains-mono-latin",
}
MONO_ADVANCE = 0.6  # JetBrains Mono: 600/1000 em
_raw: dict[str, bytes] = {}
_instances: dict[tuple[str, int], TTFont] = {}


def raw_font(family: str) -> bytes:
    if family not in _raw:
        with urllib.request.urlopen(FONT_URL.format(FONTS[family])) as r:
            _raw[family] = r.read()
    return _raw[family]


def text_width(text: str, family: str, size: float, weight: int) -> float:
    if family == "JetBrains Mono":
        return len(text) * size * MONO_ADVANCE
    key = (family, weight)
    if key not in _instances:
        font = TTFont(io.BytesIO(raw_font(family)))
        if "fvar" in font:
            axis = next(a for a in font["fvar"].axes if a.axisTag == "wght")
            w = max(axis.minValue, min(axis.maxValue, weight))
            font = instancer.instantiateVariableFont(font, {"wght": w})
        _instances[key] = font
    font = _instances[key]
    cmap, hmtx = font.getBestCmap(), font["hmtx"]
    units = sum(hmtx[cmap.get(ord(c), cmap[ord("?")])][0] for c in text)
    return units * size / font["head"].unitsPerEm



def fit(text: str, family: str, size: float, weight: int, max_w: float) -> str:
    """Recorta con puntos suspensivos si no cabe."""
    if text_width(text, family, size, weight) <= max_w:
        return text
    while text and text_width(text + "…", family, size, weight) > max_w:
        text = text[:-1]
    return text.rstrip() + "…"


def wrap(text: str, family: str, size: float, weight: int, max_w: float, max_lines: int) -> list[str]:
    """Parte en líneas, cortando también palabras que no caben solas (rutas, ramas)."""
    lines, cur = [], ""
    for ch_word in text.split(" "):
        cand = f"{cur} {ch_word}".strip()
        if text_width(cand, family, size, weight) <= max_w:
            cur = cand
            continue
        if cur:
            lines.append(cur)
        cur = ch_word
        while text_width(cur, family, size, weight) > max_w:
            k = len(cur)
            while text_width(cur[:k], family, size, weight) > max_w:
                k -= 1
            lines.append(cur[:k])
            cur = cur[k:]
    lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit(lines[-1] + " …", family, size, weight, max_w - 1)
        if not lines[-1].endswith("…"):
            lines[-1] += "…"
    return lines


def font_face(family: str, chars: str) -> str:
    font = TTFont(io.BytesIO(raw_font(family)))
    opts = subset.Options()
    opts.flavor = "woff2"
    opts.layout_features = ["*"]
    sub = subset.Subsetter(opts)
    sub.populate(text=chars + " ")
    sub.subset(font)
    buf = io.BytesIO()
    font.flavor = "woff2"
    font.save(buf)
    data = base64.b64encode(buf.getvalue()).decode()
    return (
        f'@font-face{{font-family:"{family}";font-weight:100 900;'
        f'src:url(data:font/woff2;base64,{data}) format("woff2");}}'
    )


class Svg:
    """Acumula elementos y el texto que usa cada fuente."""

    def __init__(self, w: int, h: int, title: str):
        self.w, self.h, self.title = w, h, title
        self.parts: list[str] = []
        self.chars: dict[str, set[str]] = {f: set() for f in FONTS}
        self.css: list[str] = [FADE]

    def add(self, s: str) -> None:
        self.parts.append(s)

    def text(self, x, y, s, family, size, weight, fill, anchor="start", cls="", extra="") -> None:
        self.chars[family].update(s)
        c = f' class="{cls}"' if cls else ""
        self.add(
            f'<text x="{x:.1f}" y="{y:.1f}" font-family="{family}" font-size="{size}" '
            f'font-weight="{weight}" fill="{fill}" text-anchor="{anchor}" xml:space="preserve"{c}{extra}>'
            f"{escape(s)}</text>"
        )

    def render(self) -> str:
        faces = "".join(font_face(f, "".join(sorted(c))) for f, c in self.chars.items() if c)
        css = faces + "".join(self.css) + (
            "*{animation:none!important}" if os.environ.get("STATIC")
            else "@media (prefers-reduced-motion: reduce){*{animation:none!important}}"
        )
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{escape(self.title)}">'
            f"<title>{escape(self.title)}</title><style>{css}</style>"
            + "".join(self.parts)
            + "</svg>\n"
        )


# Sin animación todo se ve igual: los estados iniciales solo existen mientras corre.
FADE = (
    "@keyframes up{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}"
    ".f{animation:up .7s cubic-bezier(.2,.7,.2,1) backwards}"
    "@keyframes in{from{opacity:0}to{opacity:1}}"
    + "".join(f".d{i}{{animation-delay:{i * 0.12:.2f}s}}" for i in range(12))
)


def backdrop(s: Svg, t: dict, rx: int = 22, glow: bool = True) -> None:
    w, h = s.w, s.h
    s.add(
        "<defs>"
        f'<clipPath id="clip"><rect width="{w}" height="{h}" rx="{rx}"/></clipPath>'
        f'<radialGradient id="ga" cx="85%" cy="0%" r="65%"><stop offset="0" stop-color="{t["glow_a"]}"/>'
        f'<stop offset="1" stop-color="{t["glow_a"]}" stop-opacity="0"/></radialGradient>'
        f'<radialGradient id="gb" cx="0%" cy="100%" r="55%"><stop offset="0" stop-color="{t["glow_b"]}"/>'
        f'<stop offset="1" stop-color="{t["glow_b"]}" stop-opacity="0"/></radialGradient>'
        f'<pattern id="dots" width="22" height="22" patternUnits="userSpaceOnUse">'
        f'<circle cx="1" cy="1" r="1" fill="{t["grid"]}"/></pattern>'
        "</defs>"
        f'<g clip-path="url(#clip)"><rect width="{w}" height="{h}" fill="{t["bg"]}"/>'
        f'<rect width="{w}" height="{h}" fill="url(#dots)"/>'
        + (
            f'<rect width="{w}" height="{h}" fill="url(#ga)" class="glow"/>'
            f'<rect width="{w}" height="{h}" fill="url(#gb)"/>'
            if glow else ""
        )
        + "</g>"
        f'<rect x=".5" y=".5" width="{w - 1}" height="{h - 1}" rx="{rx}" fill="none" stroke="{t["border"]}"/>'
    )


def chip(s: Svg, x, y, label, t, size=15, pad=12, h=34) -> float:
    w = text_width(label, "JetBrains Mono", size, 500) + pad * 2
    s.add(
        f'<rect x="{x:.1f}" y="{y}" width="{w:.1f}" height="{h}" rx="8" '
        f'fill="{t["teal_soft"]}" stroke="{t["border"]}"/>'
    )
    s.text(x + pad, y + h / 2 + size * 0.36, label, "JetBrains Mono", size, 500, t["teal"])
    return w


def window(s: Svg, x, y, w, h, title="") -> None:
    """Ventana de terminal (siempre oscura)."""
    s.add(
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="14" fill="#0a0c10" stroke="#2b313c"/>'
        + "".join(
            f'<circle cx="{x + 22 + i * 18}" cy="{y + 21}" r="5.5" fill="{c}"/>'
            for i, c in enumerate(["#ff6b6b", "#f2c94c", "#5ee08f"])
        )
        + f'<line x1="{x}" y1="{y + 42}" x2="{x + w}" y2="{y + 42}" stroke="#222731"/>'
    )
    if title:
        s.text(x + w / 2, y + 26, title, "JetBrains Mono", 12.5, 500, "#6b7383", anchor="middle")


# --------------------------------------------------------------------------
# Piezas
# --------------------------------------------------------------------------


def header(t: dict) -> str:
    W, H = 1200, 470
    s = Svg(W, H, f"{FIRST_NAME} {LAST_NAME} · {ROLE} · {FOCUS} · {STATUS}")
    s.css.append(
        "@keyframes pulse{0%,100%{opacity:1}50%{opacity:.35}}"
        ".pulse{animation:pulse 2.2s ease-in-out infinite}"
        "@keyframes ring{0%{r:6;opacity:.6}100%{r:16;opacity:0}}"
        ".ring{animation:ring 2.2s ease-out infinite}"
        "@keyframes blink{0%,49%{opacity:1}50%,100%{opacity:0}}"
        ".cursor{animation:blink 1.1s step-end infinite}"
        "@keyframes drift{0%,100%{transform:translateX(0)}50%{transform:translateX(-40px)}}"
        ".glow{animation:drift 14s ease-in-out infinite}"
    )
    backdrop(s, t)

    # Monograma y estado
    s.add(
        '<defs><linearGradient id="mono" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#f6b65a"/><stop offset="1" stop-color="#e07b1f"/></linearGradient></defs>'
        '<g class="f d0"><rect x="64" y="56" width="56" height="56" rx="14" fill="url(#mono)"/>'
    )
    s.text(92, 92, "AA", "JetBrains Mono", 21, 700, "#1a1206", anchor="middle")
    s.add("</g>")
    pw = text_width(STATUS, "Inter", 16, 500) + 58
    s.add(
        f'<g class="f d1"><rect x="138" y="60" width="{pw:.1f}" height="48" rx="24" '
        f'fill="{t["surface"]}" stroke="{t["border"]}"/>'
        f'<circle cx="162" cy="84" r="6" fill="{t["ok"]}" class="ring"/>'
        f'<circle cx="162" cy="84" r="6" fill="{t["ok"]}" class="pulse"/>'
    )
    s.text(178, 89.5, STATUS, "Inter", 16, 500, t["text"])
    s.add("</g>")

    # Nombre y rol
    s.add('<g class="f d2">')
    s.text(60, 214, FIRST_NAME, "Inter", 84, 800, t["strong"], extra=' letter-spacing="-3"')
    s.text(60, 296, LAST_NAME, "Inter", 64, 800, t["strong"], extra=' letter-spacing="-2"')
    s.add('</g><g class="f d3">')
    s.text(64, 360, ROLE, "Inter", 26, 600, t["muted"])
    s.text(64, 398, FOCUS, "Inter", 26, 700, t["accent"])
    s.add("</g>")

    # Terminal: se escribe la petición y aparece la respuesta línea a línea
    tx, ty, tw, th = 640, 56, 496, 358
    s.add('<g class="f d2">')
    window(s, tx, ty, tw, th, "zsh — alonso@askrueger")
    size, lh = 15, 26.5
    x0, y0 = tx + 24, ty + 80
    s.text(x0, y0, REQUEST[:1], "JetBrains Mono", size, 700, TERM["prompt"])
    s.text(x0 + text_width("$ ", "JetBrains Mono", size, 400), y0, REQUEST[2:], "JetBrains Mono", size, 500,
           TERM["text"])
    # Cortina que se retira por pasos: efecto de tecleo
    n = len(REQUEST) - 2
    req_w = text_width(REQUEST, "JetBrains Mono", size, 400)
    typed = 1.4
    s.css.append(
        f"@keyframes type{{from{{transform:translateX(0)}}to{{transform:translateX({req_w:.0f}px)}}}}"
        f".typing{{transform:translateX({req_w:.0f}px);animation:type {typed}s steps({n}) .5s backwards}}"
    )
    s.add(
        f'<clipPath id="term"><rect x="{tx + 1}" y="{ty + 43}" width="{tw - 2}" height="{th - 44}"/></clipPath>'
        f'<g clip-path="url(#term)"><rect x="{x0 + text_width("$ ", "JetBrains Mono", size, 400):.1f}" y="{y0 - 17}" '
        f'width="{req_w + 20:.0f}" height="24" fill="#0a0c10" class="typing"/></g>'
    )
    start = 0.5 + typed + 0.25
    for i, (line, color, weight) in enumerate(RESPONSE):
        delay = start + i * 0.09
        s.add(f'<g style="animation:in .25s {delay:.2f}s backwards">')
        y = y0 + (i + 1.4) * lh
        if color == "json" and ":" in line:
            key, val = line.split(":", 1)
            s.add(
                f'<text x="{x0}" y="{y:.1f}" font-family="JetBrains Mono" font-size="{size}" '
                f'xml:space="preserve"><tspan fill="#8fb8ff">{escape(key)}</tspan>'
                f'<tspan fill="{TERM["muted"]}">:</tspan><tspan fill="#f6c27a">{escape(val)}</tspan></text>'
            )
            s.chars["JetBrains Mono"].update(line)
        else:
            s.text(x0, y, line, "JetBrains Mono", size, weight, TERM[color])
        s.add("</g>")
    # Prompt final con cursor
    yp = y0 + (len(RESPONSE) + 1.4) * lh
    s.add(f'<g style="animation:in .2s {start + len(RESPONSE) * 0.09:.2f}s backwards">')
    s.text(x0, yp, "$", "JetBrains Mono", size, 700, TERM["prompt"])
    s.add(f'<rect x="{x0 + 16}" y="{yp - 15}" width="9" height="19" fill="{TERM["prompt"]}" class="cursor"/></g>')
    s.add("</g>")
    return s.render()


def stats(t: dict) -> str:
    gap, n = 16, len(STATS)
    cw = (1200 - gap * (n - 1)) / n
    s = Svg(1200, 150, " · ".join(f"{v} {a}" for v, a, _ in STATS))
    for i, (value, label, sub) in enumerate(STATS):
        x = i * (cw + gap)
        s.add(
            f'<g class="f d{i}"><rect x="{x + .5:.1f}" y=".5" width="{cw - 1:.1f}" height="149" rx="16" '
            f'fill="{t["surface"]}" stroke="{t["border"]}"/>'
        )
        s.text(x + 28, 72, value, "Bricolage Grotesque", 50, 800, t["accent"], extra=' letter-spacing="-1"')
        s.text(x + 28, 104, label, "Inter", 17, 600, t["strong"])
        s.text(x + 28, 128, sub, "Inter", 14.5, 400, t["muted"])
        s.add("</g>")
    return s.render()


def stack(t: dict) -> str:
    row_h, label_w = 52, 170
    s = Svg(1200, 32 + row_h * len(STACK), "Stack: " + "; ".join(f"{g}: {', '.join(i)}" for g, i in STACK))
    backdrop(s, t, rx=18)
    for r, (group, items) in enumerate(STACK):
        y = 24 + r * row_h
        s.add(f'<g class="f d{r}">')
        s.text(40, y + 23, group, "Inter", 16, 700, t["muted"])
        x = 40 + label_w
        for item in items:
            x += chip(s, x, y, item, t) + 10
        s.add("</g>")
    return s.render()


def timeline(t: dict, today: dt.date) -> str:
    colors = {"edu": t["teal"], "work": t["violet"], "build": t["accent"]}
    names = {"edu": "Formación", "work": "Trabajo", "build": "Proyectos"}
    W, row_h, top = 1200, 58, 92
    H = top + row_h * len(TIMELINE) + 30
    s = Svg(W, H, "Trayectoria: " + "; ".join(
        f"{a} ({b[0]}–{c[0] if c else 'hoy'})" for a, _, b, c, _ in TIMELINE))
    backdrop(s, t, rx=18, glow=False)
    (y0m, m0), (y1m, m1) = TIMELINE_RANGE
    lx, rx_ = 430, W - 48
    months = (y1m - y0m) * 12 + (m1 - m0)

    def px(ym) -> float:
        return lx + ((ym[0] - y0m) * 12 + (ym[1] - m0)) / months * (rx_ - lx)

    now = (today.year, today.month)
    # Ejes y leyenda
    for year in range(y0m, y1m + 1):
        x = px((year, 1))
        s.add(f'<line x1="{x:.1f}" y1="{top - 22}" x2="{x:.1f}" y2="{H - 24}" stroke="{t["border"]}" '
              f'stroke-dasharray="2 4"/>')
        if year < y1m:
            s.text(x + (px((year + 1, 1)) - x) / 2, top - 32, str(year), "JetBrains Mono", 13, 500, t["dim"],
                   anchor="middle")
    lgx = 40
    for k in ("edu", "work", "build"):
        s.add(f'<rect x="{lgx}" y="34" width="12" height="12" rx="3" fill="{colors[k]}"/>')
        s.text(lgx + 20, 45, names[k], "Inter", 14, 600, t["muted"])
        lgx += 20 + text_width(names[k], "Inter", 14, 600) + 26
    xn = px(now) + (today.day / 31) * (px((now[0], now[1] + 1)) - px(now)) if now[1] < 12 else px(now)
    s.add(f'<line x1="{xn:.1f}" y1="{top - 22}" x2="{xn:.1f}" y2="{H - 24}" stroke="{t["accent"]}" '
          f'stroke-width="1.5"/>')
    s.text(xn, H - 8, "hoy", "JetBrains Mono", 12.5, 700, t["accent"], anchor="middle")

    for i, (title, detail, start, end, kind) in enumerate(TIMELINE):
        y = top + i * row_h
        c = colors[kind]
        s.add(f'<g class="f d{i + 1}">')
        s.text(40, y + 22, title, "Inter", 17, 700, t["strong"])
        s.text(40, y + 43, detail, "Inter", 13.5, 400, t["muted"])
        x1, x2 = px(start), (px(end) if end else xn)
        bar = f'<rect x="{x1:.1f}" y="{y + 16}" width="{max(x2 - x1, 8):.1f}" height="18" rx="9" fill="{c}"'
        if end is None:
            s.add(
                f'<defs><linearGradient id="open{i}" x1="0" x2="1"><stop offset="0" stop-color="{c}"/>'
                f'<stop offset="1" stop-color="{c}" stop-opacity=".35"/></linearGradient></defs>'
                + bar.replace(f'fill="{c}"', f'fill="url(#open{i})"') + "/>"
                + f'<circle cx="{x2:.1f}" cy="{y + 25}" r="6" fill="{c}" class="pulse"/>'
            )
        else:
            s.add(bar + ' fill-opacity=".9"/>')
        span = f"{start[0]}–{end[0] if end else 'hoy'}" if not end or end[0] != start[0] else str(start[0])
        label_x = x1 - 10
        s.text(label_x, y + 30, span, "JetBrains Mono", 12.5, 500, t["dim"], anchor="end")
        s.add("</g>")
    s.css.append("@keyframes pulse{0%,100%{opacity:1}50%{opacity:.3}}.pulse{animation:pulse 2s infinite}")
    return s.render()


# --------------------------------------------------------------------------
# Actividad (datos reales de GitHub)
# --------------------------------------------------------------------------

ACTIVITY_QUERY = """
query($login: String!) {
  user(login: $login) {
    contributionsCollection {
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
    repositories(first: 12, privacy: PUBLIC, ownerAffiliations: OWNER, orderBy: {field: PUSHED_AT, direction: DESC}) {
      nodes {
        name
        isArchived
        refs(refPrefix: "refs/heads/", first: 1, orderBy: {field: TAG_COMMIT_DATE, direction: DESC}) {
          nodes { target { ... on Commit { history(first: 10) {
            nodes { messageHeadline committedDate parents { totalCount } } } } } }
        }
      }
    }
  }
}
"""
# Repos que no salen en "últimos commits" (los de servicio y los que aún no quiero enseñar)
SKIP_REPOS = {USER, f"{USER}.github.io", "Cosplay-Journal"}
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"]


def fetch_activity(token: str) -> dict:
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": ACTIVITY_QUERY, "variables": {"login": USER}}).encode(),
        headers={"Authorization": f"bearer {token}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as r:
        data = json.load(r)
    if "errors" in data:
        raise SystemExit(f"[x] GraphQL: {data['errors']}")
    return data["data"]["user"]


def thousands(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def activity(t: dict, user: dict) -> str:
    cal = user["contributionsCollection"]["contributionCalendar"]
    weeks = cal["weeks"]
    days = [d for w in weeks for d in w["contributionDays"]]
    counts = [d["contributionCount"] for d in days]
    total = cal["totalContributions"]
    active = sum(1 for c in counts if c)
    best = max(counts)
    # Si hoy aún no hay contribuciones, la racha cuenta hasta ayer
    streak = 0
    for c in reversed(counts[:-1] if counts[-1] == 0 else counts):
        if not c:
            break
        streak += 1

    recent = []
    for repo in user["repositories"]["nodes"]:
        if repo["name"] in SKIP_REPOS or repo["isArchived"] or not repo["refs"]["nodes"]:
            continue
        commits = repo["refs"]["nodes"][0]["target"]["history"]["nodes"]
        commit = next((c for c in commits if c["parents"]["totalCount"] == 1), None)
        if not commit:
            continue
        recent.append((repo["name"], commit["messageHeadline"], commit["committedDate"][:10]))
        if len(recent) == 4:
            break

    W = 1200
    cell, gap = 16, 4
    gx, gy = 64, 150
    grid_h = 7 * (cell + gap)
    H = gy + grid_h + 40 + 172
    s = Svg(W, H, f"{thousands(total)} contribuciones en el último año en GitHub. Trabajo reciente: "
            + "; ".join(f"{r}: {m}" for r, m, _ in recent))
    backdrop(s, t, rx=18)

    # Cifras
    facts = [
        (thousands(total), "contribuciones en el último año"),
        (str(active), "días con actividad"),
        (str(streak), "días seguidos ahora mismo"),
        (str(best), "contribuciones en el mejor día"),
    ]
    fx = 64
    for i, (v, label) in enumerate(facts):
        s.add(f'<g class="f d{i}">')
        s.text(fx, 84, v, "Bricolage Grotesque", 42, 800, t["accent"] if i == 0 else t["strong"],
               extra=' letter-spacing="-1"')
        s.text(fx, 112, label, "Inter", 14.5, 500, t["muted"])
        s.add("</g>")
        fx += max(text_width(v, "Bricolage Grotesque", 42, 800), text_width(label, "Inter", 14.5, 500)) + 56

    # Mapa de calor
    def level(c: int) -> str:
        if c == 0:
            return f'fill="{t["surface2"]}"'
        q = [0.28, 0.5, 0.75, 1.0][min(3, (c - 1) * 4 // max(best, 1))]
        return f'fill="rgb({t["accent_rgb"]})" fill-opacity="{q}"'

    last_month = None
    for wi, w in enumerate(weeks):
        x = gx + wi * (cell + gap)
        first = dt.date.fromisoformat(w["contributionDays"][0]["date"])
        if first.month != last_month and first.day <= 7 and wi < len(weeks) - 2:
            s.text(x, gy - 12, MESES[first.month - 1], "Inter", 12.5, 500, t["dim"])
            last_month = first.month
        s.add(f'<g style="animation:in .4s {0.3 + wi * 0.018:.3f}s backwards">')
        for d in w["contributionDays"]:
            wd = (dt.date.fromisoformat(d["date"]).weekday() + 1) % 7  # domingo = 0, como GitHub
            s.add(f'<rect x="{x}" y="{gy + wd * (cell + gap)}" width="{cell}" height="{cell}" rx="4" '
                  f'{level(d["contributionCount"])}/>')
        s.add("</g>")
    for wd, name in ((1, "lun"), (3, "mié"), (5, "vie")):
        s.text(gx - 10, gy + wd * (cell + gap) + 12.5, name, "Inter", 11.5, 500, t["dim"], anchor="end")
    # Leyenda
    lx = gx + len(weeks) * (cell + gap) - 5 * (cell + gap) - 4
    ly = gy + grid_h + 14
    s.text(lx - 10, ly + 12.5, "menos", "Inter", 12, 500, t["dim"], anchor="end")
    for i, c in enumerate([0, 1, best // 3 + 1, best * 2 // 3 + 1, best]):
        s.add(f'<rect x="{lx + i * (cell + gap)}" y="{ly}" width="{cell}" height="{cell}" rx="4" {level(c)}/>')
    s.text(lx + 5 * (cell + gap) + 6, ly + 12.5, "más", "Inter", 12, 500, t["dim"])

    # Trabajo reciente
    ry = gy + grid_h + 56
    s.text(64, ry, "ÚLTIMOS COMMITS", "JetBrains Mono", 12.5, 700, t["dim"], extra=' letter-spacing="1.5"')
    gap_c = 14
    cw = (W - 128 - gap_c * 3) / 4
    for i, (repo, msg, date) in enumerate(recent):
        x = 64 + i * (cw + gap_c)
        d = dt.date.fromisoformat(date)
        inner = cw - 36
        s.add(f'<g class="f d{i + 4}"><rect x="{x:.1f}" y="{ry + 16}" width="{cw:.1f}" height="116" rx="12" '
              f'fill="{t["surface"]}" stroke="{t["border"]}"/>')
        s.text(x + 18, ry + 44, fit(repo, "Inter", 16, 700, inner), "Inter", 16, 700, t["strong"])
        for j, ln in enumerate(wrap(msg, "Inter", 13.5, 400, inner, 2)):
            s.text(x + 18, ry + 68 + j * 19, ln, "Inter", 13.5, 400, t["muted"])
        s.text(x + 18, ry + 118, f"{d.day} {MESES[d.month - 1]} {d.year}", "JetBrains Mono", 12, 500, t["dim"])
        s.add("</g>")
    return s.render()


_banners: dict[str, str] = {}


def banner(slug: str) -> str:
    if slug not in _banners:
        with urllib.request.urlopen(BANNER_URL.format(slug)) as r:
            _banners[slug] = base64.b64encode(r.read()).decode()
    return f"data:image/webp;base64,{_banners[slug]}"


def chips_row(s: Svg, x, y, items, t, size=16, h=36, gap=10) -> None:
    for item in items:
        x += chip(s, x, y, item, t, size=size, pad=13, h=h) + gap


def tag(s: Svg, x_right, y, label, t) -> None:
    """Etiqueta de versión alineada a la derecha."""
    w = text_width(label, "JetBrains Mono", 15, 600) + 24
    s.add(f'<rect x="{x_right - w:.1f}" y="{y}" width="{w:.1f}" height="30" rx="15" '
          f'fill="rgba({t["accent_rgb"]},0.12)"/>')
    s.text(x_right - w + 12, y + 20, label, "JetBrains Mono", 15, 600, t["accent"])


def project_card(t: dict, p: dict) -> str:
    """Tarjeta para la cuadrícula de 2 columnas (se muestra a unos 490 px)."""
    W, bh = 600, 293
    H = bh + 214
    s = Svg(W, H, f"{p['name']} ({p['tag']}): {p['pitch']} {', '.join(p['chips'])}")
    s.add(
        f'<defs><clipPath id="c"><rect width="{W}" height="{H}" rx="22"/></clipPath></defs>'
        f'<g clip-path="url(#c)"><rect width="{W}" height="{H}" fill="{t["surface"]}"/>'
        f'<image href="{banner(p["slug"])}" width="{W}" height="{bh}" preserveAspectRatio="xMidYMid slice"/>'
        f'<line x1="0" y1="{bh}" x2="{W}" y2="{bh}" stroke="{t["border"]}"/></g>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="none" stroke="{t["border"]}"/>'
    )
    y = bh + 50
    s.text(32, y, p["name"], "Inter", 27, 800, t["strong"], extra=' letter-spacing="-.5"')
    tag(s, W - 32, y - 23, p["tag"], t)
    for j, ln in enumerate(wrap(p["pitch"], "Inter", 18.5, 400, W - 64, 2)):
        s.text(32, y + 36 + j * 27, ln, "Inter", 18.5, 400, t["muted"])
    chips_row(s, 32, H - 62, p["chips"], t)
    return s.render()


def featured_card(t: dict, p: dict) -> str:
    """Proyecto principal: banner entero arriba (sin recortar su texto) y detalle en dos columnas."""
    W = 1200
    bh = round(W * 500 / 1024)  # proporción de los banners de Google Play
    H = bh + 280
    s = Svg(W, H, f"{p['name']} ({p['tag']}): {p['pitch']} " + " ".join(p["points"]))
    s.add(
        f'<defs><clipPath id="c"><rect width="{W}" height="{H}" rx="22"/></clipPath></defs>'
        f'<g clip-path="url(#c)"><rect width="{W}" height="{H}" fill="{t["surface"]}"/>'
        f'<image href="{banner(p["slug"])}" width="{W}" height="{bh}"/>'
        f'<line x1="0" y1="{bh}" x2="{W}" y2="{bh}" stroke="{t["border"]}"/></g>'
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="22" fill="none" stroke="{t["border"]}"/>'
    )
    x, y = 44, bh + 56
    s.text(x, y, f'{p["eyebrow"]} · {p["tag"].upper()}', "JetBrains Mono", 14, 700, t["accent"],
           extra=' letter-spacing="1.5"')
    s.text(x, y + 46, p["name"], "Inter", 38, 800, t["strong"], extra=' letter-spacing="-1"')
    for j, ln in enumerate(wrap(p["pitch"], "Inter", 20, 500, 470, 2)):
        s.text(x, y + 86 + j * 28, ln, "Inter", 20, 500, t["muted"])
    chips_row(s, x, H - 74, p["chips"], t, size=15, h=36, gap=8)
    px = 600
    for i, pt in enumerate(p["points"]):
        py = y + 6 + i * 44
        s.add(f'<rect x="{px}" y="{py - 12}" width="9" height="9" rx="2" fill="{t["teal"]}"/>')
        s.text(px + 24, py - 2, fit(pt, "Inter", 18, 400, W - px - 68), "Inter", 18, 400, t["text"])
    return s.render()


def principles(t: dict) -> str:
    gap, n = 16, len(PRINCIPLES)
    cw = (1200 - gap * (n - 1)) / n
    H = 186
    s = Svg(1200, H, "Cómo trabajo: " + "; ".join(f"{a}: {b}" for a, b in PRINCIPLES))
    for i, (title, text) in enumerate(PRINCIPLES):
        x = i * (cw + gap)
        s.add(f'<g class="f d{i}"><rect x="{x + .5:.1f}" y=".5" width="{cw - 1:.1f}" height="{H - 1}" rx="16" '
              f'fill="{t["surface"]}" stroke="{t["border"]}"/>')
        s.text(x + 26, 46, f"0{i + 1}", "JetBrains Mono", 15, 700, t["accent"])
        s.text(x + 26, 80, title, "Inter", 19, 700, t["strong"])
        for j, ln in enumerate(wrap(text, "Inter", 15, 400, cw - 52, 3)):
            s.text(x + 26, 110 + j * 22, ln, "Inter", 15, 400, t["muted"])
        s.add("</g>")
    return s.render()


def main() -> None:
    OUT.mkdir(exist_ok=True)
    today = dt.date.today()
    token = os.environ.get("GITHUB_TOKEN")
    user = fetch_activity(token) if token else None
    for theme, t in THEMES.items():
        (OUT / f"header-{theme}.svg").write_text(header(t), encoding="utf-8")
        (OUT / f"stats-{theme}.svg").write_text(stats(t), encoding="utf-8")
        (OUT / f"stack-{theme}.svg").write_text(stack(t), encoding="utf-8")
        (OUT / f"timeline-{theme}.svg").write_text(timeline(t, today), encoding="utf-8")
        (OUT / f"principles-{theme}.svg").write_text(principles(t), encoding="utf-8")
        first, *rest = PROJECTS
        (OUT / f"project-{first['slug']}-{theme}.svg").write_text(featured_card(t, first), encoding="utf-8")
        for p in rest:
            (OUT / f"project-{p['slug']}-{theme}.svg").write_text(project_card(t, p), encoding="utf-8")
        if user:
            (OUT / f"activity-{theme}.svg").write_text(activity(t, user), encoding="utf-8")
    if not user:
        print("[!] Sin GITHUB_TOKEN: la actividad no se ha actualizado")
    for f in sorted(OUT.glob("*.svg")):
        print(f"[OK] {f.relative_to(ROOT)}  {f.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
