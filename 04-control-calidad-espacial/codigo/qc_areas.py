# -*- coding: utf-8 -*-
"""
Control de calidad de areas prediales con bandas de tolerancia.

Compara, para cada predio, el AREA GEOMETRICA (calculada sobre la geometria)
contra el AREA REGISTRAL (la que figura en el folio de matricula), y emite un
veredicto automatico:

    Cumple             -> la diferencia esta dentro de la tolerancia
    Corregir           -> la diferencia supera la tolerancia
    Sin Area Registral -> no hay dato registral para comparar

La tolerancia depende del tamano del predio (mas estricta cuanto mayor es):

    area registral <=  80 m2  ->  7 %
    area registral <= 250 m2  ->  6 %
    area registral <= 500 m2  ->  4 %
    area registral  > 500 m2  ->  3 %

Este script es autocontenido: genera un bloque catastral sintetico (sin datos
reales), corre el control y produce:

    salidas/mapa_qc.png       mapa tematico Cumple / Corregir / Sin area
    salidas/reporte_qc.xlsx   reporte de auditoria con formato
    datos_muestra/predios.geojson   geometria sintetica generada
    datos_muestra/registral.csv     tabla registral sintetica (con errores)

Requiere: numpy, pandas, matplotlib, shapely, openpyxl.  No usa arcpy ni QGIS.

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
from matplotlib.patches import Patch
from shapely.geometry import Polygon, mapping


# ---------------------------------------------------------------------------
# 1. Regla de negocio: banda de tolerancia
# ---------------------------------------------------------------------------
def limite_tolerancia(area_registral: float) -> float:
    """Tolerancia (%) admisible segun el tamano del predio."""
    if area_registral <= 80:
        return 7.0
    if area_registral <= 250:
        return 6.0
    if area_registral <= 500:
        return 4.0
    return 3.0


def evaluar_predio(area_geom: float, area_registral: float | None) -> dict:
    """Aplica la regla a un predio y devuelve diferencia, limite y veredicto."""
    if area_registral is None or not np.isfinite(area_registral) or area_registral <= 0:
        return {"diferencia_pct": np.nan, "limite_pct": np.nan,
                "evaluacion": "Sin Area Registral"}
    dif = abs(area_geom - area_registral) / area_registral * 100.0
    lim = limite_tolerancia(area_registral)
    return {"diferencia_pct": round(dif, 2), "limite_pct": lim,
            "evaluacion": "Corregir" if dif > lim else "Cumple"}


# ---------------------------------------------------------------------------
# 2. Datos sinteticos (un bloque catastral ficticio)
# ---------------------------------------------------------------------------
def _codigo_predial(i: int, rng: np.random.Generator) -> str:
    """Codigo predial sintetico de 30 digitos (formato colombiano, ficticio)."""
    base = "25175" "00" "00" "0000"          # depto+mpio+zona+sector+comuna+barrio
    manzana = "{:04d}".format(1 + i // 100)
    predio = "{:04d}".format(1 + i % 100)
    resto = "".join(str(d) for d in rng.integers(0, 10, size=30 - len(base) - 8))
    return (base + manzana + predio + resto)[:30]


def generar_bloque(seed: int = 42):
    """Devuelve (predios_df, tabla_registral_df).

    predios_df    : codigo, geometry (shapely Polygon), area_geom_m2
    tabla_registral_df : codigo, area_registral_m2  (con errores inyectados)
    """
    rng = np.random.default_rng(seed)

    # Lineas de retícula con espaciado irregular -> predios de tamanos muy
    # distintos, para que caigan en las cuatro bandas de tolerancia.
    xs = np.concatenate([[0], np.cumsum(rng.uniform(6, 40, size=8))])
    ys = np.concatenate([[0], np.cumsum(rng.uniform(6, 38, size=7))])
    gx, gy = np.meshgrid(xs, ys)

    # Jitter de los nodos interiores (los bordes del bloque quedan rectos).
    jit = rng.normal(0, 2.4, size=gx.shape + (2,))
    jit[0, :] = jit[-1, :] = jit[:, 0] = jit[:, -1] = 0.0
    gx = gx + jit[..., 0]
    gy = gy + jit[..., 1]

    filas = []
    k = 0
    for r in range(len(ys) - 1):
        for c in range(len(xs) - 1):
            poly = Polygon([
                (gx[r, c],     gy[r, c]),
                (gx[r, c + 1], gy[r, c + 1]),
                (gx[r + 1, c + 1], gy[r + 1, c + 1]),
                (gx[r + 1, c], gy[r + 1, c]),
            ])
            filas.append({"codigo": _codigo_predial(k, rng),
                          "geometry": poly,
                          "area_geom_m2": round(poly.area, 2)})
            k += 1
    predios = pd.DataFrame(filas)

    # --- Area registral = area_geom * factor, con errores controlados ---
    n = len(predios)
    clase = rng.choice(["ok", "error", "sin"], size=n, p=[0.62, 0.30, 0.08])
    factor = np.where(
        clase == "ok",
        1.0 + rng.normal(0, 0.012, n),                     # dentro de tolerancia
        1.0 + rng.choice([-1, 1], n) * rng.uniform(0.045, 0.13, n),  # fuera
    )
    area_reg = np.round(predios["area_geom_m2"].to_numpy() * factor, 2)
    area_reg = np.where(clase == "sin", np.nan, area_reg)

    tabla = pd.DataFrame({"codigo": predios["codigo"], "area_registral_m2": area_reg})
    return predios, tabla


# ---------------------------------------------------------------------------
# 3. Proceso de control
# ---------------------------------------------------------------------------
def controlar(predios: pd.DataFrame, tabla_registral: pd.DataFrame) -> pd.DataFrame:
    df = predios.merge(tabla_registral, on="codigo", how="left")
    ev = df.apply(lambda r: evaluar_predio(r["area_geom_m2"], r["area_registral_m2"]),
                  axis=1, result_type="expand")
    return pd.concat([df, ev], axis=1)


# ---------------------------------------------------------------------------
# 4. Salidas
# ---------------------------------------------------------------------------
_COLOR = {"Cumple": "#2e7d32", "Corregir": "#c62828", "Sin Area Registral": "#9e9e9e"}
_FILL = {"Cumple": "#c8e6c9", "Corregir": "#ffcdd2", "Sin Area Registral": "#eeeeee"}


def mapa_qc(df: pd.DataFrame, ruta_png: str) -> None:
    fig, ax = plt.subplots(figsize=(11, 9))
    for _, r in df.iterrows():
        ev = r["evaluacion"]
        xs, ys = r["geometry"].exterior.xy
        ax.fill(xs, ys, facecolor=_FILL[ev], edgecolor="0.25", linewidth=0.8, zorder=2)
        cx, cy = r["geometry"].centroid.x, r["geometry"].centroid.y
        etq = r["codigo"][-4:]
        if ev == "Sin Area Registral":
            sub = "s/reg"
        else:
            sub = f"Δ {r['diferencia_pct']:.1f}%"
        ax.text(cx, cy, f"{etq}\n{sub}", ha="center", va="center", fontsize=6.5,
                color=_COLOR[ev], zorder=3)

    resumen = df["evaluacion"].value_counts().to_dict()
    tot = len(df)
    n_ok = resumen.get("Cumple", 0)

    etq_leg = {"Cumple": "Cumple", "Corregir": "Corregir",
               "Sin Area Registral": "Sin área registral"}
    ax.legend(handles=[Patch(facecolor=_FILL[k], edgecolor="0.25", label=etq_leg[k])
                       for k in ("Cumple", "Corregir", "Sin Area Registral")],
              loc="upper center", bbox_to_anchor=(0.5, -0.08), ncol=3, fontsize=9,
              frameon=False)
    ax.set_aspect("equal")
    ax.set_xlabel("m")
    ax.set_ylabel("m")
    ax.set_title(
        "Control de calidad de áreas prediales — bloque sintético\n"
        f"{tot} predios  ·  {n_ok} Cumple ({100*n_ok/tot:.0f}%)  ·  "
        f"{resumen.get('Corregir', 0)} Corregir  ·  "
        f"{resumen.get('Sin Area Registral', 0)} sin área registral",
        fontsize=12, fontweight="bold")
    fig.text(0.5, 0.005, "Datos sintéticos · Sergio Ferreira · sergio.ferreira9714@gmail.com",
             ha="center", fontsize=8, color="0.45")
    fig.savefig(ruta_png, dpi=150, bbox_inches="tight")
    plt.close(fig)


def reporte_excel(df: pd.DataFrame, ruta_xlsx: str) -> None:
    from openpyxl.styles import Font, PatternFill, Alignment
    from openpyxl.utils import get_column_letter

    cols = ["codigo", "area_geom_m2", "area_registral_m2", "diferencia_pct",
            "limite_pct", "evaluacion"]
    titulos = ["Numero Predial", "Area Geometrica (m2)", "Area Registral (m2)",
               "Diferencia (%)", "Limite (%)", "Evaluacion"]
    out = df[cols].sort_values(["evaluacion", "diferencia_pct"],
                               ascending=[True, False]).reset_index(drop=True)

    with pd.ExcelWriter(ruta_xlsx, engine="openpyxl") as xw:
        out.to_excel(xw, index=False, sheet_name="QC_Areas", header=titulos, startrow=0)
        ws = xw.sheets["QC_Areas"]

        head_fill = PatternFill("solid", fgColor="1F3864")
        for c, _ in enumerate(titulos, start=1):
            cel = ws.cell(row=1, column=c)
            cel.font = Font(bold=True, color="FFFFFF")
            cel.fill = head_fill
            cel.alignment = Alignment(horizontal="center")

        fills = {"Cumple": PatternFill("solid", fgColor="C8E6C9"),
                 "Corregir": PatternFill("solid", fgColor="FFCDD2"),
                 "Sin Area Registral": PatternFill("solid", fgColor="EEEEEE")}
        col_ev = titulos.index("Evaluacion") + 1
        for r in range(2, len(out) + 2):
            ev = ws.cell(row=r, column=col_ev).value
            if ev in fills:
                ws.cell(row=r, column=col_ev).fill = fills[ev]

        for c in range(1, len(titulos) + 1):
            ws.column_dimensions[get_column_letter(c)].width = \
                max(14, len(titulos[c - 1]) + 2)
        ws.freeze_panes = "A2"


def exportar_datos_muestra(predios: pd.DataFrame, tabla: pd.DataFrame,
                           carpeta: str) -> None:
    os.makedirs(carpeta, exist_ok=True)
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature",
         "properties": {"codigo": r["codigo"], "area_geom_m2": r["area_geom_m2"]},
         "geometry": mapping(r["geometry"])}
        for _, r in predios.iterrows()]}
    with open(os.path.join(carpeta, "predios.geojson"), "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=1)
    tabla.to_csv(os.path.join(carpeta, "registral.csv"), index=False)


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    raiz = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dir_sal = os.path.join(raiz, "salidas")
    dir_dat = os.path.join(raiz, "datos_muestra")
    os.makedirs(dir_sal, exist_ok=True)

    predios, tabla = generar_bloque(seed=42)
    exportar_datos_muestra(predios, tabla, dir_dat)

    df = controlar(predios, tabla)

    mapa_qc(df, os.path.join(dir_sal, "mapa_qc.png"))
    reporte_excel(df, os.path.join(dir_sal, "reporte_qc.xlsx"))

    print(df["evaluacion"].value_counts().to_string())
    peor = df.dropna(subset=["diferencia_pct"]).nlargest(3, "diferencia_pct")
    print("\nMayores desviaciones:")
    print(peor[["codigo", "area_geom_m2", "area_registral_m2",
                "diferencia_pct", "limite_pct", "evaluacion"]].to_string(index=False))
    print("\nOK ->", dir_sal)
