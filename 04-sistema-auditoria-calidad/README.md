# 04 · Sistema de auditoría de calidad catastral

Aplicación full-stack para el **aseguramiento de calidad** de la digitalización
catastral de un proyecto: ingiere la geodatabase, la contrasta contra el registro
alfanumérico, corre validaciones automáticas y sirve todo en un panel web y en un
informe estático.

Diseñado y desarrollado por Sergio Ferreira para un proyecto de auditoría
catastral. No se reproducen aquí sus datos, credenciales ni pantallas reales;
las cifras de esta ficha y de la maqueta son **ficticias**.

![Maqueta del panel](mockup/dashboard_mock.png)

*Maqueta con datos ficticios, mismo diseño que el panel real.
El HTML de la maqueta está en [`mockup/dashboard_mock.html`](mockup/dashboard_mock.html).*

---

## Arquitectura

```
Navegador  ──►  FastAPI (api_dashboard.py, ~84 endpoints REST)
                     │
        ┌────────────┼─────────────┐
   validaciones   análisis      reportes        ← módulos de lógica
   (8 checks)  (topología,   (Excel, CSV,
               contraste,    tablas)
               VUR, vínculo)
                     │
              schema_calidad.py                 ← esquema único (~18 tablas)
                     │
              scope_resolver.py                 ← router de BD
              ┌──────┴──────┐
        PostgreSQL /     SQLite + shapely
         PostGIS         (portátil, sin BD)
       (producción)
```

- **Motor dual.** El mismo esquema y la misma lógica corren sobre
  **PostgreSQL/PostGIS** (producción, multiusuario, índices GiST) o sobre
  **SQLite + shapely** (un archivo, sin instalar nada). `scope_resolver.py`
  decide; `modo_manager.py` migra en ambos sentidos. Los dos motores son
  *first-class* y deben dar el mismo resultado.
- **Ingesta de GDB.** `gdb_auditor.py` lee la File Geodatabase con **arcpy**;
  `semantic_mapper.py` normaliza los nombres de campo antes de insertar en
  `capas_geo`.
- **Índice espacial.** El check de solapamientos agrupa geometrías por manzana y
  usa un `STRtree` de shapely para las intersecciones pairwise.
- **Exportable.** `Generar_Tablero.bat` produce un `Control_Calidad.html`
  autónomo con los datos incrustados: se comparte sin levantar el servidor.

## Las 8 validaciones automáticas

| # | Check | Detecta |
|---|-------|---------|
| 1 | Capa incorrecta | TERRENO en la tabla UNIDAD o viceversa |
| 2 | Predios duplicados | mismo número predial repetido |
| 3 | Saltos secuenciales | huecos en la numeración de predios |
| 4 | Solapamiento geométrico | polígonos que se intersectan (STRtree) |
| 5 | Unidades en déficit | unidades sin su TERRENO "padre" |
| 6 | Desfase GDB / BD | conteos de geometría vs registro no cuadran |
| 7 | Duplicados intra-capa | mismo predial dos veces en la misma capa |
| 8 | Sin geometría | predios en BD sin polígono dibujado |

Semáforo verde / ámbar / rojo con umbrales por check.

## Reportes

Validaciones · Excepciones · **Omisiones y comisiones** (por estado y por
digitalizador) · **Contraste GDB** (OK / ALERTA / CRÍTICO) · **Topología**
(solapes y huecos con mapa Leaflet interactivo) · **Cumplimiento de área**
(registral vs geográfica, bandas de tolerancia por tamaño — la misma regla del
[caso 02](../02-control-calidad-espacial/)) · **Vínculo unidad↔terreno**
(correctas / omisiones / comisiones / discrepancias) · Distribución por etapa ·
**Auditoría completa a Excel** multi-hoja · Predios por grupo (filtros por
digitalizador, coordinador, estado…).

## Decisiones de diseño

- **Esquema único como fuente de verdad** (`schema_calidad.py`): PostgreSQL y
  SQLite se construyen del mismo diccionario de tablas e índices.
- **La lógica vive en Python, no en la BD.** Existe una versión PL/pgSQL de
  referencia, pero el motor la replica en Python para que SQLite funcione igual
  sin PostGIS. Portabilidad por encima de rendimiento máximo.
- **API centralizada, módulos añadibles.** Una validación nueva = un módulo nuevo
  + un endpoint, sin tocar el núcleo.
- **Dos formas de consumo:** panel en vivo (`localhost:8000`) para el trabajo
  diario, e informe estático para compartir con dirección.

## Stack

FastAPI · uvicorn · psycopg2 · **PostgreSQL / PostGIS** · SQLite · **shapely**
(STRtree, operaciones geométricas) · pyproj · **arcpy** (lectura de GDB) ·
openpyxl · Leaflet · HTML/CSS/JS. ~14.800 líneas de Python en ~25 módulos.

## Qué se publica aquí

Solo esta ficha y la **maqueta** (`mockup/`, datos ficticios). El código fuente,
el esquema, los backups y los informes con datos reales pertenecen al proyecto y
no se incluyen.
