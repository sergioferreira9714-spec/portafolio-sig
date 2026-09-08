# Sergio Ferreira — Portafolio SIG

**Analista SIG.** Automatización de geoprocesamiento, control de calidad espacial
y modelación ambiental. Trabajo indistintamente en **ArcGIS** (arcpy / Python
toolboxes) y **QGIS / PostGIS**, sin depender de una licencia concreta.

> *GIS analyst — geoprocessing automation, spatial data quality and environmental
> spatial analysis. Dual stack ArcGIS / QGIS + PostGIS.*

Todo el código de este repositorio es reproducible y usa **datos sintéticos**:
sin identificadores de cliente, sin rutas reales, sin datos reales. Los trabajos
hechos para terceros se describen y se acreditan a su titular.

---

## 01 · Fusión y unificación topológica de polígonos

Consolidar los fragmentos de un predio en un único polígono por identificador y
migrar los atributos traduciendo los campos numéricos a códigos de dominio.

![Antes / después](01-fusion-poligonos-catastro/salidas/antes_despues.png)

Unión progresiva por área · traducción `1/2 → Convencional/No Convencional`,
`3 → PS-03` · deduplicación en re-ejecuciones.
**[Ver caso →](01-fusion-poligonos-catastro/)**

## 02 · Control de calidad espacial con bandas de tolerancia

Comparar el área geométrica con el área registral, aplicar una tolerancia según
el tamaño del predio y emitir un veredicto automático **Cumple / Corregir**.

![Mapa de control de calidad](02-control-calidad-espacial/salidas/mapa_qc.png)

Reporte Excel de auditoría · misma regla implementada también en **PostGIS**
(`ST_Area` en vivo, sin recálculos manuales).
**[Ver caso →](02-control-calidad-espacial/)**

## 03 · Modelación ambiental → entidades SIG

Del modelo físico a la cartografía de decisión.

**A. Pluma gaussiana** — modelo propio de dispersión de contaminantes, de
principio a fin, reproducible sin software propietario.

![Pluma gaussiana](03-modelacion-ambiental/salidas/pluma_hero.png)

**B. Componente SIG en un estudio de ruido aeroportuario** (K2 Applus+) —
recreación demostrativa del flujo **campo continuo → isófonas → Área de
Influencia Directa → cruce con receptores sensibles**.

![Isófonas y AID](03-modelacion-ambiental/salidas/isofonas_aid.png)

**[Ver caso →](03-modelacion-ambiental/)**

---

## Stack

| | |
|---|---|
| **Lenguaje** | Python (numpy, pandas, matplotlib, shapely) |
| **SIG** | ArcGIS Pro (arcpy, Python toolboxes `.pyt`), QGIS (PyQGIS, Processing) |
| **Datos espaciales** | PostgreSQL / PostGIS, File Geodatabase, GeoJSON, raster ASCII |
| **Aplicación** | catastro multipropósito · evaluación de impacto ambiental (ruido, calidad del aire) |

## Cómo ejecutar

Cada caso trae su propio `codigo/` y se ejecuta con
`python codigo/<script>.py`. Dependencias: `numpy pandas matplotlib shapely
openpyxl Pillow`. No requiere ArcGIS ni QGIS instalados.

## Contacto

**Sergio Ferreira** · sergio.ferreira9714@gmail.com ·
GitHub [@sergioferreira9714-spec](https://github.com/sergioferreira9714-spec)
