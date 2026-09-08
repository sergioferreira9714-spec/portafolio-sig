# -*- coding: utf-8 -*-
"""
Modelo de pluma gaussiana para dispersion de contaminantes atmosfericos.

Calcula la concentracion a nivel de suelo (z = 0) de un contaminante emitido
por una fuente puntual continua (chimenea), sobre una malla regular, y la
exporta como:
  - figura PNG "hero" para portafolio (mapa de isopletas + umbral legal)
  - figura PNG de analisis de sensibilidad por clase de estabilidad
  - raster ESRI ASCII (.asc) que se abre directo en QGIS / ArcGIS

Sin dependencias propietarias: solo numpy + matplotlib.

Ecuacion (Turner, 1994), fuente continua, reflexion total en el suelo,
receptor a z = 0:

    C(x,y) = Q / (pi * u * sy * sz) * exp(-y^2 / (2 sy^2)) * exp(-H^2 / (2 sz^2))

con sy, sz (coeficientes de dispersion de Briggs, campo abierto) en funcion de
la distancia a favor del viento x y la clase de estabilidad Pasquill-Gifford.

Autor: Sergio Ferreira  ·  sergio.ferreira9714@gmail.com
"""
from __future__ import annotations

import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patheffects as pe
from matplotlib.colors import LogNorm


# ---------------------------------------------------------------------------
# 1. Coeficientes de dispersion de Briggs (campo abierto / rural)
# ---------------------------------------------------------------------------
_BRIGGS_RURAL = {
    # clase: sy = a*x*(1+b*x)^-0.5 ;  sz = c*x*(1+d*x)^e
    "A": dict(a=0.22, b=1e-4, c=0.20,  d=0.0,    e=0.0),
    "B": dict(a=0.16, b=1e-4, c=0.12,  d=0.0,    e=0.0),
    "C": dict(a=0.11, b=1e-4, c=0.08,  d=2e-4,   e=-0.5),
    "D": dict(a=0.08, b=1e-4, c=0.06,  d=1.5e-3, e=-0.5),
    "E": dict(a=0.06, b=1e-4, c=0.03,  d=3e-4,   e=-1.0),
    "F": dict(a=0.04, b=1e-4, c=0.016, d=3e-4,   e=-1.0),
}

_ESTABILIDAD_DESC = {
    "A": "A · muy inestable", "B": "B · inestable", "C": "C · ligeramente inestable",
    "D": "D · neutra", "E": "E · ligeramente estable", "F": "F · estable",
}


def sigmas_briggs(x_m: np.ndarray, estabilidad: str) -> tuple[np.ndarray, np.ndarray]:
    """(sigma_y, sigma_z) en metros para la distancia x (m) a favor del viento."""
    p = _BRIGGS_RURAL[estabilidad.upper()]
    x = np.where(x_m > 0, x_m, np.nan)
    sy = p["a"] * x * (1.0 + p["b"] * x) ** -0.5
    sz = p["c"] * x if p["d"] == 0.0 else p["c"] * x * (1.0 + p["d"] * x) ** p["e"]
    return sy, sz


# ---------------------------------------------------------------------------
# 2. Modelo de pluma
# ---------------------------------------------------------------------------
def pluma_gaussiana(
    Q_g_s: float,
    u_m_s: float,
    H_m: float,
    estabilidad: str,
    direccion_viento_deg: float = 270.0,
    extent_m: tuple[float, float, float, float] = (-500, 6000, -1600, 1600),
    paso_m: float = 20.0,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Concentracion a nivel de suelo en ug/m3 sobre una malla regular.

    direccion_viento_deg : DE DONDE sopla el viento, convencion meteo
                           (270 = viento del oeste => el penacho va al este)
    extent_m : (xmin, xmax, ymin, ymax) en metros, fuente en (0, 0)
    Devuelve (X, Y, C) con C en ug/m3.
    """
    xmin, xmax, ymin, ymax = extent_m
    xs = np.arange(xmin, xmax + paso_m, paso_m)
    ys = np.arange(ymin, ymax + paso_m, paso_m)
    X, Y = np.meshgrid(xs, ys)

    # Azimut HACIA donde va el viento (desde el norte, horario):
    az_hacia = (direccion_viento_deg + 180.0) % 360.0
    # a angulo matematico (desde el eje +X, antihorario):
    phi = np.deg2rad(90.0 - az_hacia)

    # Proyeccion de cada celda sobre los ejes del penacho
    x_dw = X * np.cos(phi) + Y * np.sin(phi)     # a favor del viento
    y_cw = -X * np.sin(phi) + Y * np.cos(phi)    # transversal

    sy, sz = sigmas_briggs(x_dw, estabilidad)
    with np.errstate(divide="ignore", invalid="ignore"):
        C = (Q_g_s / (np.pi * u_m_s * sy * sz)
             * np.exp(-(y_cw ** 2) / (2.0 * sy ** 2))
             * np.exp(-(H_m ** 2) / (2.0 * sz ** 2)))

    C = np.where(x_dw > 0, C, 0.0)
    C = np.nan_to_num(C, nan=0.0, posinf=0.0, neginf=0.0)
    return X, Y, C * 1.0e6   # g/m3 -> ug/m3


def metricas(X: np.ndarray, C: np.ndarray, umbral: float) -> dict:
    paso = float(X[0, 1] - X[0, 0])
    idx = np.unravel_index(np.argmax(C), C.shape)
    return {
        "c_max": float(C.max()),
        "x_cmax_km": float(X[idx] / 1000.0),
        "area_umbral_km2": float(np.sum(C > umbral) * paso ** 2 / 1e6),
        "alcance_umbral_km": (float(X[C > umbral].max() / 1000.0)
                              if np.any(C > umbral) else 0.0),
    }


# ---------------------------------------------------------------------------
# 3. Exportar raster ESRI ASCII (QGIS / ArcGIS)
# ---------------------------------------------------------------------------
def exportar_ascii(ruta: str, X: np.ndarray, Y: np.ndarray, C: np.ndarray) -> None:
    paso = float(X[0, 1] - X[0, 0])
    with open(ruta, "w", encoding="ascii") as f:
        f.write(f"ncols {C.shape[1]}\nnrows {C.shape[0]}\n")
        f.write(f"xllcorner {float(X.min())}\nyllcorner {float(Y.min())}\n")
        f.write(f"cellsize {paso}\nNODATA_value -9999\n")
        for fila in np.flipud(C):
            f.write(" ".join(f"{v:.6g}" for v in fila) + "\n")


# ---------------------------------------------------------------------------
# 4. Figuras
# ---------------------------------------------------------------------------
_NIVELES = np.array([1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000], dtype=float)
_STROKE = [pe.withStroke(linewidth=2.2, foreground="black")]


def _fondo(ax, X, Y, C):
    Xk, Yk = X / 1000.0, Y / 1000.0
    lv = _NIVELES[_NIVELES <= max(C.max() * 1.2, _NIVELES[1])]
    if lv.size < 2:
        lv = _NIVELES[:4]
    cf = ax.contourf(Xk, Yk, np.ma.masked_less_equal(C, lv[0]),
                     levels=lv, norm=LogNorm(), cmap="inferno", extend="max")
    ax.set_aspect("equal")
    ax.grid(alpha=0.15)
    return cf


def figura_hero(X, Y, C, esc, umbral, contaminante, ruta_png):
    m = metricas(X, C, umbral)
    fig, ax = plt.subplots(figsize=(12.5, 5.0))
    cf = _fondo(ax, X, Y, C)
    ax.set_xlim(-1.2, 6.0)
    ax.set_ylim(-1.75, 1.9)
    ax.set_xticks(range(-1, 7))

    # isopleta de umbral (leyenda, sin etiqueta inline)
    if C.max() > umbral:
        cs = ax.contour(X / 1000.0, Y / 1000.0, C, levels=[umbral],
                        colors="cyan", linewidths=2.2)
        cs.collections[0].set_label(f"Umbral {umbral:g} µg/m³ (RD 102/2011)")
        ax.legend(loc="upper right", fontsize=8, framealpha=0.9)

    # fuente
    ax.plot(0, 0, marker="^", ms=14, mfc="white", mec="black", mew=1.5, zorder=6)
    ax.annotate("Fuente", (0, 0), xytext=(7, -14), textcoords="offset points",
                fontsize=8.5, color="white", path_effects=_STROKE)

    # viento (esquina superior izquierda, en zona vacia)
    th = np.deg2rad(90.0 - ((esc["dir"] + 180.0) % 360.0))
    x0, y0 = -0.85, 1.45
    ax.annotate("", xy=(x0 + 0.7 * np.cos(th), y0 + 0.7 * np.sin(th)), xytext=(x0, y0),
                arrowprops=dict(arrowstyle="-|>", color="deepskyblue", lw=2.6))
    ax.text(x0, y0 + 0.22, f"viento {esc['dir']:g}° · {esc['u']:g} m/s",
            fontsize=8.5, color="deepskyblue", path_effects=_STROKE)

    ax.text(0.012, 0.03,
            f"Estabilidad {_ESTABILIDAD_DESC[esc['estab']]}\n"
            f"Q = {esc['Q']:g} g/s   ·   H efectiva = {esc['H']:g} m\n"
            f"C máx = {m['c_max']:.0f} µg/m³ a {m['x_cmax_km']:.2f} km viento abajo\n"
            f"Área > umbral = {m['area_umbral_km2']:.2f} km²   ·   "
            f"alcance = {m['alcance_umbral_km']:.2f} km",
            transform=ax.transAxes, va="bottom", ha="left", fontsize=8.5,
            bbox=dict(boxstyle="round", fc="black", ec="none", alpha=0.6), color="white")

    ax.set_xlabel("Distancia E–O (km)")
    ax.set_ylabel("Distancia N–S (km)")
    ax.set_title(f"Dispersión de {contaminante} · modelo de pluma gaussiana", loc="left",
                 fontsize=13, fontweight="bold", pad=8)
    cb = fig.colorbar(cf, ax=ax, shrink=0.92, pad=0.015)
    cb.set_label(f"{contaminante} a nivel de suelo (µg/m³)")
    fig.text(0.5, 0.005,
             "Coeficientes de dispersión de Briggs (campo abierto) · receptor z = 0 · "
             "Sergio Ferreira · sergio.ferreira9714@gmail.com",
             ha="center", fontsize=7.5, color="0.45")
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return m


def figura_sensibilidad(escenario_base, umbral, contaminante, ruta_png):
    fig, axes = plt.subplots(2, 3, figsize=(14, 6.0), sharex=True, sharey=True)
    cf = None
    for ax, estab in zip(axes.ravel(), "ABCDEF"):
        X, Y, C = pluma_gaussiana(estabilidad=estab, **escenario_base)
        cf = _fondo(ax, X, Y, C)
        ax.set_xlim(-0.6, 6.0)
        ax.set_ylim(-1.6, 1.6)
        if C.max() > umbral:
            ax.contour(X / 1000.0, Y / 1000.0, C, levels=[umbral],
                       colors="cyan", linewidths=1.6)
        ax.plot(0, 0, marker="^", ms=9, mfc="white", mec="black", mew=1.2)
        m = metricas(X, C, umbral)
        ax.set_title(_ESTABILIDAD_DESC[estab], fontsize=9.5, fontweight="bold")
        ax.text(0.02, 0.04,
                f"C máx {m['c_max']:.0f} µg/m³\n{m['area_umbral_km2']:.2f} km² > umbral",
                transform=ax.transAxes, va="bottom", fontsize=8,
                bbox=dict(boxstyle="round", fc="black", ec="none", alpha=0.55), color="white")
    for ax in axes[-1]:
        ax.set_xlabel("E–O (km)")
    for ax in axes[:, 0]:
        ax.set_ylabel("N–S (km)")
    fig.suptitle(f"Sensibilidad a la estabilidad atmosférica — {contaminante}   "
                 f"(Q={escenario_base['Q_g_s']:g} g/s · u={escenario_base['u_m_s']:g} m/s · "
                 f"H={escenario_base['H_m']:g} m)",
                 fontsize=12, fontweight="bold")
    cb = fig.colorbar(cf, ax=axes, shrink=0.85, pad=0.02)
    cb.set_label(f"{contaminante} a nivel de suelo (µg/m³)")
    fig.text(0.5, 0.005, "Isopleta cian = umbral legal (200 µg/m³) · Sergio Ferreira · "
             "sergio.ferreira9714@gmail.com", ha="center", fontsize=7.5, color="0.45")
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# 5. Escenario de prueba
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    salida = os.path.dirname(os.path.abspath(__file__))

    # Chimenea industrial pequena, emision de NO2.
    # Umbral horario NO2 (RD 102/2011 / Directiva 2008/50/CE): 200 ug/m3.
    CONTAM, UMBRAL = "NO₂", 200.0
    base = dict(Q_g_s=50.0, u_m_s=5.0, H_m=45.0, direccion_viento_deg=270.0)

    X, Y, C = pluma_gaussiana(estabilidad="D", **base)
    esc = dict(estab="D", u=base["u_m_s"], H=base["H_m"], Q=base["Q_g_s"],
               dir=base["direccion_viento_deg"])
    m = figura_hero(X, Y, C, esc, UMBRAL, CONTAM, os.path.join(salida, "pluma_hero.png"))
    exportar_ascii(os.path.join(salida, "pluma_NO2_estabD.asc"), X, Y, C)
    print("HERO (estab D):", {k: round(v, 3) for k, v in m.items()})

    figura_sensibilidad(base, UMBRAL, CONTAM, os.path.join(salida, "pluma_sensibilidad.png"))
    print("OK ->", salida)
