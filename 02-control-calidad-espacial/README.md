# 02 · Control de calidad espacial con bandas de tolerancia

> **En preparación** — versión generalizada, con datos sintéticos.

## El problema

Verificar, sobre miles de predios, si el **área calculada geométricamente**
coincide —dentro de una tolerancia— con el **área registral**, y marcar
automáticamente los que deben corregirse.

## El enfoque

Rutina que, para cada predio:

1. Cruza la capa con la fuente registral (CSV / tabla) por número predial.
2. Calcula `Diferencia_% = |área_geométrica − área_registral| / área_registral · 100`.
3. Aplica una **banda de tolerancia según el tamaño del predio**
   (más estricta cuanto mayor es el área).
4. Escribe el veredicto `Cumple` / `Corregir` en la capa.
5. Exporta un **reporte a Excel** con las columnas de auditoría.

| Área registral | Tolerancia |
|---|---|
| ≤ 80 m² | 7 % |
| ≤ 250 m² | 6 % |
| ≤ 500 m² | 4 % |
| > 500 m² | 3 % |

## Qué se publicará aquí

- Código generalizado.
- Datos de muestra sintéticos (capa + tabla registral ficticia).
- Reporte Excel de ejemplo y mapa Cumple / Corregir.
- Variante que ejecuta el mismo cálculo **directamente en PostGIS**
  (`ST_Area` en vivo, sin recálculos manuales).
