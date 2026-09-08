# -*- coding: utf-8 -*-
"""
Fusión y unificación topológica de polígonos catastrales.

En cartografía catastral un mismo predio suele quedar dividido en varios
fragmentos durante la digitalización. Esta rutina los consolida en un único
polígono por identificador y migra los atributos a la capa de unidades,
traduciendo los campos numéricos a los códigos de dominio de destino.

Reglas:
  * Fusión geométrica: se toma el fragmento de mayor área como base y se hace
    unión progresiva del resto (unary_union). Un fragmento por predio al final.
  * Traducción de atributos:
        tipo   1 -> 'Convencional'      2 -> 'No Convencional'
        planta N -> 'PS-0N'   (piso 3 -> 'PS-03')

Autocontenido: genera un bloque catastral sintético (sin datos reales) y produce:

    salidas/antes_despues.png    fragmentos  ->  predios unificados
    salidas/proceso.gif          unión progresiva de un predio fragmentado
    salidas/tabla_atributos.png  traducción numérico -> dominio
    datos_muestra/fragmentos.geojson
    datos_muestra/unidades.geojson

Requiere: numpy, pandas, matplotlib, shapely, Pillow.  No usa arcpy ni QGIS.

Autor: Sergio Ferreira  ·  sergio.ferreira9714@gmail.com
"""
from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.animation import PillowWriter
from matplotlib.patches import Patch
from shapely.geometry import Polygon, LineString, mapping
from shapely.ops import unary_union, split


# ---------------------------------------------------------------------------
# 1. Traducción de atributos numéricos -> códigos de dominio
# ---------------------------------------------------------------------------
def map_tipo_construccion(v) -> str | None:
    """1/'1'/'01' -> Convencional ; 2/'2'/'02' -> No Convencional ; otro -> None."""
    s = "" if v is None else str(v).strip()
    if not s:
        return None
    try:
        s = str(int(float(s)))
    except ValueError:
        s = s.upper()
    return {"1": "Convencional", "2": "No Convencional",
            "CONVENCIONAL": "Convencional",
            "NO CONVENCIONAL": "No Convencional"}.get(s)


def map_planta(v) -> str | None:
    """Número de piso -> código de dominio ('3' -> 'PS-03'). Ya-codificado se respeta."""
    s = "" if v is None else str(v).strip().upper()
    if not s:
        return None
    if s[:3] in ("PS-", "MZ-", "ST-"):
        return s
    try:
        n = int(float(s))
    except ValueError:
        return None
    return f"PS-{n:02d}" if n > 0 else None


# ---------------------------------------------------------------------------
# 2. Datos sintéticos: bloque con predios fragmentados
# ---------------------------------------------------------------------------
def _codigo(i: int) -> str:
    return ("25175" + "00000000000000000" + f"{i + 1:08d}")[:30]


def _trocear(poly: Polygon, n_cortes: int, rng: np.random.Generator,
             max_piezas: int = 4) -> list[Polygon]:
    """Parte un polígono con n rectas aleatorias que lo cruzan por completo.

    Si quedan más de `max_piezas` trozos, los más pequeños se fusionan en el
    vecino con el que comparten más frontera (evita astillas irreales)."""
    piezas = [poly]
    minx, miny, maxx, maxy = poly.bounds
    diag = np.hypot(maxx - minx, maxy - miny)
    cx, cy = poly.centroid.x, poly.centroid.y
    for _ in range(n_cortes):
        ang = rng.uniform(0, np.pi)
        off = rng.uniform(-0.25, 0.25) * diag
        d = np.array([np.cos(ang), np.sin(ang)])
        nrm = np.array([-d[1], d[0]])
        p = np.array([cx, cy]) + nrm * off
        linea = LineString([tuple(p - d * diag), tuple(p + d * diag)])
        nuevas = []
        for pz in piezas:
            if linea.crosses(pz):
                nuevas.extend(g for g in split(pz, linea).geoms
                              if isinstance(g, Polygon) and g.area > 1.0)
            else:
                nuevas.append(pz)
        piezas = nuevas

    while len(piezas) > max_piezas:
        piezas.sort(key=lambda p: p.area)
        chico = piezas.pop(0)
        j = max(range(len(piezas)),
                key=lambda i: chico.buffer(0.05).intersection(
                    piezas[i].buffer(0.05)).area)
        piezas[j] = unary_union([piezas[j], chico]).buffer(0)
    return piezas


def generar_bloque(seed: int = 7):
    rng = np.random.default_rng(seed)
    xs = np.concatenate([[0], np.cumsum(rng.uniform(14, 30, size=6))])
    ys = np.concatenate([[0], np.cumsum(rng.uniform(14, 28, size=5))])
    gx, gy = np.meshgrid(xs, ys)
    jit = rng.normal(0, 1.8, size=gx.shape + (2,))
    jit[0, :] = jit[-1, :] = jit[:, 0] = jit[:, -1] = 0.0
    gx, gy = gx + jit[..., 0], gy + jit[..., 1]

    parcelas = []
    k = 0
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            parcelas.append(Polygon([
                (gx[r, c], gy[r, c]), (gx[r, c + 1], gy[r, c + 1]),
                (gx[r + 1, c + 1], gy[r + 1, c + 1]), (gx[r + 1, c], gy[r + 1, c])]))
            k += 1

    # ~40% de las parcelas se fragmentan en 2-4 trozos
    fragmentar = rng.random(len(parcelas)) < 0.42
    filas = []
    for i, poly in enumerate(parcelas):
        tipo = int(rng.integers(1, 3))          # 1 o 2, consistente por predio
        planta = int(rng.integers(1, 5))        # piso 1..4
        trozos = _trocear(poly, int(rng.integers(1, 4)), rng) if fragmentar[i] else [poly]
        for pz in trozos:
            filas.append({"codigo": _codigo(i), "tipo": tipo, "planta": planta,
                          "geometry": pz, "area_m2": round(pz.area, 2)})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# 3. Fusión
# ---------------------------------------------------------------------------
def fusionar(fragmentos: pd.DataFrame) -> pd.DataFrame:
    filas = []
    for cod, g in fragmentos.groupby("codigo"):
        geom = unary_union(list(g["geometry"])).buffer(0)
        tipo = g["tipo"].iloc[0]
        planta = g["planta"].iloc[0]
        filas.append({
            "codigo": cod,
            "n_fragmentos": len(g),
            "geometry": geom,
            "area_m2": round(geom.area, 2),
            "TIPO_CONSTRUCCION": map_tipo_construccion(tipo),
            "PLANTA": map_planta(planta),
        })
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# 4. Salidas
# ---------------------------------------------------------------------------
def _dibujar(ax, geoms, colores, lw=0.8, ec="0.2"):
    for geom, col in zip(geoms, colores):
        polys = geom.geoms if geom.geom_type == "MultiPolygon" else [geom]
        for p in polys:
            xs, ys = p.exterior.xy
            ax.fill(xs, ys, facecolor=col, edgecolor=ec, linewidth=lw, zorder=2)
    ax.set_aspect("equal")
    ax.set_xticks([]); ax.set_yticks([])


def figura_antes_despues(fragmentos, unidades, ruta_png):
    cods = list(unidades["codigo"])
    cmap = plt.get_cmap("tab20")
    color_de = {c: cmap(i % 20) for i, c in enumerate(cods)}

    fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 6))
    _dibujar(a1, list(fragmentos["geometry"]),
             [color_de[c] for c in fragmentos["codigo"]], lw=0.7, ec="0.15")
    a1.set_title(f"Antes — {len(fragmentos)} fragmentos\n"
                 f"(líneas internas = cortes de digitalización)", fontsize=11)

    _dibujar(a2, list(unidades["geometry"]),
             [color_de[c] for c in unidades["codigo"]], lw=1.4, ec="0.1")
    a2.set_title(f"Después — {len(unidades)} predios unificados\n"
                 "(un polígono por código, atributos traducidos a dominio)", fontsize=11)

    n_frag = int((unidades["n_fragmentos"] > 1).sum())
    fig.suptitle("Fusión y unificación topológica de polígonos catastrales  ·  "
                 f"{n_frag} predios estaban fragmentados", fontsize=13, fontweight="bold")
    fig.text(0.5, 0.02, "Datos sintéticos · Sergio Ferreira · sergio.ferreira9714@gmail.com",
             ha="center", fontsize=8, color="0.45")
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def gif_proceso(fragmentos, ruta_gif):
    """Anima la unión progresiva del predio con más fragmentos."""
    cod = fragmentos["codigo"].value_counts().idxmax()
    g = fragmentos[fragmentos["codigo"] == cod].copy()
    g = g.sort_values("area_m2", ascending=False).reset_index(drop=True)
    piezas = list(g["geometry"])
    minx, miny, maxx, maxy = unary_union(piezas).bounds
    pad = 0.08 * max(maxx - minx, maxy - miny)

    fig, ax = plt.subplots(figsize=(5.6, 5.6))
    writer = PillowWriter(fps=1)
    n = len(piezas)
    with writer.saving(fig, ruta_gif, dpi=110):
        for k in range(n + 2):
            ax.clear()
            ax.set_xlim(minx - pad, maxx + pad); ax.set_ylim(miny - pad, maxy + pad)
            ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
            paso = min(max(k, 1), n)
            acum = unary_union(piezas[:paso]).buffer(0)
            ap = acum.geoms if acum.geom_type == "MultiPolygon" else [acum]
            for p in ap:
                xs, ys = p.exterior.xy
                ax.fill(xs, ys, facecolor="#1f77b4", edgecolor="0.1",
                        linewidth=1.6, zorder=3)
            for p in piezas[paso:]:
                xs, ys = p.exterior.xy
                ax.fill(xs, ys, facecolor="none", edgecolor="0.4",
                        linewidth=1.0, hatch="////", zorder=2)
            if k >= n:
                ax.set_title(f"Predio {cod[-4:]} — unificado", fontsize=11)
            else:
                ax.set_title(f"Predio {cod[-4:]} — unión {paso}/{n}", fontsize=11)
            writer.grab_frame()
    plt.close(fig)


def figura_tabla_atributos(fragmentos, unidades, ruta_png, n=6):
    base = (fragmentos.groupby("codigo").agg(tipo=("tipo", "first"),
            planta=("planta", "first"), frag=("codigo", "size")).reset_index())
    m = base.merge(unidades[["codigo", "TIPO_CONSTRUCCION", "PLANTA"]], on="codigo")
    m = m[m["frag"] > 1].head(n)
    celdas = [[r.codigo[-6:], r.frag, r.tipo, r.TIPO_CONSTRUCCION, r.planta, r.PLANTA]
              for r in m.itertuples()]
    fig, ax = plt.subplots(figsize=(9, 0.5 + 0.42 * len(celdas)))
    ax.axis("off")
    t = ax.table(cellText=celdas,
                 colLabels=["código", "frag.", "tipo (orig.)", "TIPO_CONSTRUCCION",
                            "planta (orig.)", "PLANTA"],
                 cellLoc="center", loc="center")
    t.auto_set_font_size(False); t.set_fontsize(9)
    t.auto_set_column_width(col=list(range(6)))
    t.scale(1, 1.5)
    for c in range(6):
        t[0, c].set_facecolor("#1F3864"); t[0, c].set_text_props(color="white")
    ax.set_title("Traducción de atributos: numérico (terreno) → código de dominio (unidad)",
                 fontsize=11, fontweight="bold", pad=12)
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def exportar_geojson(df, ruta, props):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {k: (r[k] if not isinstance(r[k], float) else round(r[k], 2))
                        for k in props},
         "geometry": mapping(r["geometry"])}
        for _, r in df.iterrows()]}
    with open(ruta, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dir_sal = os.path.join(raiz, "salidas")
    dir_dat = os.path.join(raiz, "datos_muestra")
    os.makedirs(dir_sal, exist_ok=True)
    os.makedirs(dir_dat, exist_ok=True)

    fragmentos = generar_bloque(seed=7)
    unidades = fusionar(fragmentos)

    figura_antes_despues(fragmentos, unidades, os.path.join(dir_sal, "antes_despues.png"))
    gif_proceso(fragmentos, os.path.join(dir_sal, "proceso.gif"))
    figura_tabla_atributos(fragmentos, unidades, os.path.join(dir_sal, "tabla_atributos.png"))
    exportar_geojson(fragmentos, os.path.join(dir_dat, "fragmentos.geojson"),
                     ["codigo", "tipo", "planta", "area_m2"])
    exportar_geojson(unidades, os.path.join(dir_dat, "unidades.geojson"),
                     ["codigo", "n_fragmentos", "area_m2", "TIPO_CONSTRUCCION", "PLANTA"])

    n_frag = int((unidades["n_fragmentos"] > 1).sum())
    print(f"Fragmentos: {len(fragmentos)}  ->  Predios: {len(unidades)}  "
          f"({n_frag} estaban fragmentados)")
    print(unidades.sort_values("n_fragmentos", ascending=False)
          [["codigo", "n_fragmentos", "area_m2", "TIPO_CONSTRUCCION", "PLANTA"]]
          .head(6).to_string(index=False))
    print("\nOK ->", dir_sal)
