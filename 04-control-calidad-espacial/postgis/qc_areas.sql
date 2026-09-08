-- ===========================================================================
-- Control de calidad de áreas prediales en PostGIS
-- ===========================================================================
-- Misma regla de negocio que codigo/qc_areas.py, pero ejecutada EN VIVO sobre
-- la geometría: el área geométrica NO se almacena, se calcula con ST_Area() en
-- cada consulta, así nunca queda desactualizada tras una edición en QGIS.
--
-- Requisitos:
--   * extensión postgis
--   * tabla `predio` con geometría en un CRS proyectado en metros
--     (p. ej. MAGNA-SIRGAS / Origen Nacional, EPSG:9377).
--     Si la geometría está en grados (EPSG:4326), sustituir ST_Area(geom)
--     por ST_Area(geom::geography).
--   * tabla `predio_registral(codigo text, area_registral_m2 double precision)`
--     con el área del folio de matrícula.
-- ===========================================================================

CREATE EXTENSION IF NOT EXISTS postgis;

-- Tolerancia (%) admisible según el tamaño del predio.
-- Equivalente exacto de limite_tolerancia() en el script de Python.
CREATE OR REPLACE FUNCTION qc_limite_tolerancia(area_registral double precision)
RETURNS double precision
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
    SELECT CASE
        WHEN area_registral IS NULL OR area_registral <= 0 THEN NULL
        WHEN area_registral <=  80 THEN 7.0
        WHEN area_registral <= 250 THEN 6.0
        WHEN area_registral <= 500 THEN 4.0
        ELSE 3.0
    END;
$$;

-- Vista de control. Se recalcula sola en cada SELECT.
CREATE OR REPLACE VIEW qc_areas AS
SELECT
    p.codigo,
    round(ST_Area(p.geom)::numeric, 2)                       AS area_geom_m2,
    round(r.area_registral_m2::numeric, 2)                   AS area_registral_m2,
    round((abs(ST_Area(p.geom) - r.area_registral_m2)
           / NULLIF(r.area_registral_m2, 0) * 100)::numeric, 2) AS diferencia_pct,
    qc_limite_tolerancia(r.area_registral_m2)                AS limite_pct,
    CASE
        WHEN r.area_registral_m2 IS NULL OR r.area_registral_m2 <= 0
            THEN 'Sin Area Registral'
        WHEN abs(ST_Area(p.geom) - r.area_registral_m2) / r.area_registral_m2 * 100
             > qc_limite_tolerancia(r.area_registral_m2)
            THEN 'Corregir'
        ELSE 'Cumple'
    END                                                     AS evaluacion
FROM predio p
LEFT JOIN predio_registral r ON r.codigo = p.codigo;

-- ---------------------------------------------------------------------------
-- Consultas típicas
-- ---------------------------------------------------------------------------
--   SELECT evaluacion, count(*) FROM qc_areas GROUP BY evaluacion;
--   SELECT * FROM qc_areas WHERE evaluacion = 'Corregir' ORDER BY diferencia_pct DESC;

-- ---------------------------------------------------------------------------
-- Opcional: materializar el veredicto en la tabla de predios (2 columnas),
-- útil si otras herramientas lo leen directo. Se puede lanzar tras cada carga.
-- ---------------------------------------------------------------------------
--   ALTER TABLE predio ADD COLUMN IF NOT EXISTS diferencia_pct double precision;
--   ALTER TABLE predio ADD COLUMN IF NOT EXISTS evaluacion     text;
--   UPDATE predio p
--      SET diferencia_pct = q.diferencia_pct,
--          evaluacion     = q.evaluacion
--     FROM qc_areas q
--    WHERE q.codigo = p.codigo;
