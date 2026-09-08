# -*- coding: utf-8 -*-
"""
Recreación demostrativa · Componente SIG en un estudio de ruido.

Muestra EL MÉTODO con el que se pasa de la salida de un modelo acústico a las
entidades geográficas con las que se decide sobre el Área de Influencia Directa
(AID) de un proyecto:

    campo continuo (dB(A))  ->  isófonas  ->  AID  ->  cruce con receptores

TODO es sintético y está rotulado como tal. No reproduce ni deriva de ningún
entregable de K2 Applus+ ni de terceros; solo ilustra el flujo de trabajo SIG.

Salidas:
    salidas/proceso_isofonas.png      las 3 etapas del método, lado a lado
    salidas/isofonas_aid.png          mapa final: isófonas + AID + receptores
    salidas/receptores_afectados.csv  tabla de receptores por nivel de exposición
    datos_muestra/isofonas.geojson    curvas de isófona (líneas)
    datos_muestra/aid.geojson         polígono del AID
    datos_muestra/receptores.geojson  receptores sensibles (puntos)

Requiere: numpy, pandas, matplotlib, shapely.

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
from matplotlib.lines import Line2D
from shapely.geometry import Polygon, LineString, Point, mapping
from shapely.ops import unary_union


# ---------------------------------------------------------------------------
# 1. Campo continuo sintético de nivel sonoro alrededor de dos pistas
# ---------------------------------------------------------------------------
PISTAS = [((-1900, -700), (1900, -700)),
          ((-1900,  700), (1900,  700))]        # dos pistas paralelas (m)
EXTENT = (-13000, 13000, -8000, 8000)           # dominio (m)
PASO = 120.0                                    # resolución de malla (m)

NIVELES_ISOFONA = [55, 60, 65, 70, 75]          # dB(A)
UMBRAL_AID = 65                                 # dB(A) — límite del AID (demostrativo)


def _suaviza(A, k=3):
    """Suavizado box 3x3 sin dependencias (deja isófonas limpias)."""
    B = A.astype(float)
    for _ in range(k):
        B = (B + np.roll(B, 1, 0) + np.roll(B, -1, 0)
             + np.roll(B, 1, 1) + np.roll(B, -1, 1)) / 5.0
    return B


def _dist_segmento(px, py, a, b):
    """Distancia de los puntos (px,py) al segmento a-b, vectorizada."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = np.clip(((px - ax) * dx + (py - ay) * dy) / L2, 0.0, 1.0)
    cx, cy = ax + t * dx, ay + t * dy
    return np.hypot(px - cx, py - cy)


def campo_sonoro(seed: int = 3):
    rng = np.random.default_rng(seed)
    xmin, xmax, ymin, ymax = EXTENT
    xs = np.arange(xmin, xmax + PASO, PASO)
    ys = np.arange(ymin, ymax + PASO, PASO)
    X, Y = np.meshgrid(xs, ys)

    d = np.minimum.reduce([_dist_segmento(X, Y, a, b) for a, b in PISTAS])
    d = np.maximum(d, 30.0)

    # Nivel base: fuente lineal (divergencia cilíndrica) + absorción atmosférica.
    # Calibrado para que la isófona de 65 dB(A) alcance varios km, como en un
    # aeropuerto real.
    L = 105.0 - 11.0 * np.log10(d) - 0.0010 * d

    # Directividad: corredores de despegue/aterrizaje en los extremos de pista
    # (transición suave, sin escalón).
    off_axis = np.abs(Y - np.where(Y >= 0, 700, -700))
    fac_corredor = 1.0 / (1.0 + np.exp(-(np.abs(X) - 1900.0) / 500.0))
    L = L + 5.0 * fac_corredor * np.exp(-off_axis / 2200.0)

    # Micro-variabilidad (terreno/meteo) + suavizado -> isófonas limpias.
    L = _suaviza(L + rng.normal(0, 0.5, size=L.shape), k=3)
    return X, Y, L


# ---------------------------------------------------------------------------
# 2. Isófonas y AID como entidades geográficas
# ---------------------------------------------------------------------------
def _paths_a_polys(cs, nivel_idx):
    polys = []
    for seg in cs.allsegs[nivel_idx]:
        if len(seg) >= 4:
            p = Polygon(seg)
            if not p.is_valid:
                p = p.buffer(0)
            if p.area > 0:
                polys.append(p)
    return polys


def extraer_entidades(X, Y, L):
    fig, ax = plt.subplots()
    cs = ax.contour(X, Y, L, levels=NIVELES_ISOFONA)
    isofonas = {}
    for i, nivel in enumerate(NIVELES_ISOFONA):
        lineas = [LineString(seg) for seg in cs.allsegs[i] if len(seg) >= 2]
        isofonas[nivel] = lineas
    idx_aid = NIVELES_ISOFONA.index(UMBRAL_AID)
    polys_aid = _paths_a_polys(cs, idx_aid)
    plt.close(fig)

    aid = max(polys_aid, key=lambda p: p.area) if polys_aid else None
    if aid is not None and len(polys_aid) > 1:
        aid = unary_union(polys_aid).buffer(0)
    return isofonas, aid


# ---------------------------------------------------------------------------
# 3. Receptores sensibles sintéticos y su cruce con el AID
# ---------------------------------------------------------------------------
def generar_receptores(X, Y, L, aid, seed: int = 11):
    rng = np.random.default_rng(seed)
    xmin, xmax, ymin, ymax = EXTENT
    tipos = (["Vivienda"] * 40 + ["Colegio"] * 4 + ["Hospital"] * 2
             + ["Centro comunitario"] * 4)
    rng.shuffle(tipos)

    n_cluster = 30                       # asentamientos cercanos a la operación
    cx = rng.normal(0, 5500, n_cluster)
    cy = rng.normal(0, 3500, n_cluster)
    n_disp = len(tipos) - n_cluster      # población dispersa
    dx = rng.uniform(xmin * 0.8, xmax * 0.8, n_disp)
    dy = rng.uniform(ymin * 0.8, ymax * 0.8, n_disp)
    px = np.clip(np.concatenate([cx, dx]), xmin * 0.95, xmax * 0.95)
    py = np.clip(np.concatenate([cy, dy]), ymin * 0.95, ymax * 0.95)

    xs, ys = X[0], Y[:, 0]
    filas = []
    for t, x, y in zip(tipos, px, py):
        ix = int(np.clip(np.searchsorted(xs, x), 0, L.shape[1] - 1))
        iy = int(np.clip(np.searchsorted(ys, y), 0, L.shape[0] - 1))
        nivel = float(L[iy, ix])
        banda = "< 55"
        for n in NIVELES_ISOFONA:
            if nivel >= n:
                banda = f"≥ {n}"
        dentro = bool(aid is not None and aid.contains(Point(x, y)))
        filas.append({"tipo": t, "x": round(x, 1), "y": round(y, 1),
                      "nivel_dBA": round(nivel, 1), "banda": banda,
                      "en_AID": dentro,
                      "geometry": Point(x, y)})
    return pd.DataFrame(filas)


# ---------------------------------------------------------------------------
# 4. Figuras
# ---------------------------------------------------------------------------
_CMAP = "turbo"
_BANDAS_FILL = [(55, "#2c7fb8"), (60, "#7fcdbb"), (65, "#fed976"),
                (70, "#fd8d3c"), (75, "#e31a1c")]


def _poly_parts(geom):
    """Lista de Polygon, sea geom un Polygon o un MultiPolygon."""
    if geom is None:
        return []
    return list(geom.geoms) if geom.geom_type == "MultiPolygon" else [geom]


def _pinta_campo(ax, X, Y, L, con_barra=False, fig=None):
    cf = ax.contourf(X / 1000, Y / 1000, L, levels=np.arange(45, 90, 2.5),
                     cmap=_CMAP, extend="both")
    _pistas(ax)
    ax.set_aspect("equal")
    if con_barra and fig is not None:
        cb = fig.colorbar(cf, ax=ax, shrink=0.8, pad=0.02)
        cb.set_label("Nivel sonoro L (dB(A))")
    return cf


def _pistas(ax):
    for (a, b) in PISTAS:
        ax.plot([a[0] / 1000, b[0] / 1000], [a[1] / 1000, b[1] / 1000],
                color="black", lw=3, solid_capstyle="butt", zorder=5)


def _pinta_isofonas(ax, X, Y, L):
    cs = ax.contour(X / 1000, Y / 1000, L, levels=NIVELES_ISOFONA,
                    colors=[c for _, c in _BANDAS_FILL], linewidths=1.8)
    ax.clabel(cs, fmt="%d", fontsize=7)
    _pistas(ax)
    ax.set_aspect("equal")


def figura_proceso(X, Y, L, isofonas, aid, receptores, ruta_png):
    fig, axs = plt.subplots(1, 3, figsize=(16, 5.4))

    _pinta_campo(axs[0], X, Y, L, con_barra=True, fig=fig)
    axs[0].set_title("1 · Campo continuo\n(salida del modelo acústico)", fontsize=11)

    _pinta_isofonas(axs[1], X, Y, L)
    axs[1].set_title("2 · Isófonas\n(curvas de igual nivel, entidades lineales)", fontsize=11)

    for part in _poly_parts(aid):
        xa, ya = part.exterior.xy
        axs[2].fill(np.array(xa) / 1000, np.array(ya) / 1000, facecolor="#fdae6b",
                    edgecolor="#a63603", lw=2.2, alpha=0.55, zorder=2)
    _pistas(axs[2])
    dentro = receptores[receptores["en_AID"]]
    fuera = receptores[~receptores["en_AID"]]
    axs[2].scatter(fuera["x"] / 1000, fuera["y"] / 1000, s=14, c="0.5",
                   label="Receptor fuera del AID", zorder=4)
    axs[2].scatter(dentro["x"] / 1000, dentro["y"] / 1000, s=32, c="#a63603",
                   edgecolor="white", linewidth=0.6,
                   label="Receptor en el AID", zorder=5)
    axs[2].set_aspect("equal")
    axs[2].legend(loc="lower left", fontsize=8)
    axs[2].set_title(f"3 · AID (≥ {UMBRAL_AID} dB(A)) + receptores\n"
                     "(polígono de decisión + cruce)", fontsize=11)

    for ax in axs:
        ax.set_xlabel("km")
    axs[0].set_ylabel("km")
    fig.suptitle("De la salida del modelo a las entidades de decisión — recreación demostrativa",
                 fontsize=13, fontweight="bold")
    fig.text(0.5, 0.01, "Datos sintéticos · no reproduce material de K2 Applus+ · "
             "Sergio Ferreira · sergio.ferreira9714@gmail.com",
             ha="center", fontsize=7.5, color="0.45")
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def figura_final(X, Y, L, aid, receptores, ruta_png):
    fig, ax = plt.subplots(figsize=(11, 8.5))
    # Bandas ascendentes: cada nivel rellena de n hacia arriba y las bandas
    # superiores se superponen -> sin huecos en el núcleo.
    for n, c in _BANDAS_FILL:
        ax.contourf(X / 1000, Y / 1000, L, levels=[n, 200], colors=[c], alpha=0.5)
    _pinta_isofonas(ax, X, Y, L)

    for part in _poly_parts(aid):
        xa, ya = part.exterior.xy
        ax.plot(np.array(xa) / 1000, np.array(ya) / 1000, color="#6a0000",
                lw=2.6, zorder=6)

    col = {"Vivienda": "o", "Colegio": "s", "Hospital": "P", "Centro comunitario": "^"}
    for t, mk in col.items():
        sub = receptores[receptores["tipo"] == t]
        dentro = sub["en_AID"].to_numpy()
        ax.scatter(sub["x"] / 1000, sub["y"] / 1000, marker=mk,
                   s=np.where(dentro, 70, 26),
                   c=np.where(dentro, "#a63603", "0.55"),
                   edgecolor="white", linewidth=0.5, zorder=7)

    n_aid = int(receptores["en_AID"].sum())
    sens = receptores[(receptores["en_AID"]) & (receptores["tipo"] != "Vivienda")]
    area_km2 = aid.area / 1e6 if aid is not None else 0.0
    ax.text(0.012, 0.02,
            f"AID: {area_km2:.1f} km²\n"
            f"Receptores en el AID: {n_aid} / {len(receptores)}\n"
            f"  · viviendas: {int(((receptores['en_AID']) & (receptores['tipo']=='Vivienda')).sum())}\n"
            f"  · usos sensibles: {len(sens)} ({', '.join(sorted(set(sens['tipo']))) or '—'})",
            transform=ax.transAxes, va="bottom", fontsize=9,
            bbox=dict(boxstyle="round", fc="white", ec="0.6"))

    leg = [Line2D([0], [0], marker=m, color="w", markerfacecolor="#a63603",
                  markeredgecolor="white", markersize=9, label=t)
           for t, m in col.items()]
    leg.append(Line2D([0], [0], color="#6a0000", lw=2.6, label=f"AID (≥ {UMBRAL_AID} dB(A))"))
    ax.legend(handles=leg, loc="upper right", fontsize=8)

    ax.set_aspect("equal")
    ax.set_xlabel("km"); ax.set_ylabel("km")
    ax.set_title("Isófonas, Área de Influencia Directa y receptores sensibles\n"
                 "recreación demostrativa del componente SIG", fontsize=12, fontweight="bold")
    fig.text(0.5, 0.005, "Datos sintéticos · no reproduce material de K2 Applus+ · "
             "Sergio Ferreira · sergio.ferreira9714@gmail.com",
             ha="center", fontsize=7.5, color="0.45")
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 5. Export
# ---------------------------------------------------------------------------
def exportar(isofonas, aid, receptores, carpeta):
    os.makedirs(carpeta, exist_ok=True)

    feats = []
    for nivel, lineas in isofonas.items():
        for ln in lineas:
            feats.append({"type": "Feature", "properties": {"nivel_dBA": nivel},
                          "geometry": mapping(ln)})
    with open(os.path.join(carpeta, "isofonas.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": feats}, f,
                  ensure_ascii=False, indent=1)

    with open(os.path.join(carpeta, "aid.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature",
             "properties": {"umbral_dBA": UMBRAL_AID,
                            "area_km2": round(aid.area / 1e6, 3) if aid else None},
             "geometry": mapping(aid) if aid else None}]}, f,
                  ensure_ascii=False, indent=1)

    with open(os.path.join(carpeta, "receptores.geojson"), "w", encoding="utf-8") as f:
        json.dump({"type": "FeatureCollection", "features": [
            {"type": "Feature",
             "properties": {k: r[k] for k in ("tipo", "nivel_dBA", "banda", "en_AID")},
             "geometry": mapping(r["geometry"])}
            for _, r in receptores.iterrows()]}, f, ensure_ascii=False, indent=1)


# ---------------------------------------------------------------------------
# 6. Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dir_sal = os.path.join(raiz, "salidas")
    dir_dat = os.path.join(raiz, "datos_muestra")
    os.makedirs(dir_sal, exist_ok=True)

    X, Y, L = campo_sonoro()
    isofonas, aid = extraer_entidades(X, Y, L)
    receptores = generar_receptores(X, Y, L, aid)

    figura_proceso(X, Y, L, isofonas, aid, receptores,
                   os.path.join(dir_sal, "proceso_isofonas.png"))
    figura_final(X, Y, L, aid, receptores, os.path.join(dir_sal, "isofonas_aid.png"))
    receptores.drop(columns="geometry").to_csv(
        os.path.join(dir_sal, "receptores_afectados.csv"), index=False)
    exportar(isofonas, aid, receptores, dir_dat)

    print(f"AID: {aid.area / 1e6:.2f} km²  ·  receptores en AID: "
          f"{int(receptores['en_AID'].sum())}/{len(receptores)}")
    print(receptores[receptores["en_AID"]].groupby("tipo").size().to_string())
    print("\nOK ->", dir_sal)
