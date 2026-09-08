# 01 · Fusión y unificación topológica de polígonos

> **En preparación** — versión generalizada, con datos sintéticos.

## El problema

En cartografía catastral, un mismo predio suele quedar dividido en varios
fragmentos durante la digitalización. Hay que consolidarlos en un único polígono
por identificador, sin generar huecos ni solapes, y llevar sus atributos a la
capa de destino respetando los dominios.

## El enfoque

Herramienta de geoprocesamiento (ArcGIS Python toolbox / PyQGIS) que:

1. Agrupa los fragmentos por código de predio.
2. Toma el fragmento de mayor área como base y hace **unión progresiva** del resto.
3. Elimina los secundarios y actualiza la geometría del principal.
4. Migra atributos a la capa de unidades, **traduciendo campos numéricos a los
   códigos de dominio** de destino (p. ej. `1 → Convencional`, `2 → No Convencional`).
5. Deduplica en re-ejecuciones y avisa (sin abortar) cuando una geometría de
   entrada no se puede fusionar.

## Qué se publicará aquí

- Código generalizado (sin identificadores de cliente ni rutas reales).
- Datos de muestra sintéticos.
- Figuras antes / después y del proceso paso a paso.
