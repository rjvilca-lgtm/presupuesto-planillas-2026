/*
  Consistencia de centros de costo dentro de cada facultad (solo lectura).

  La facultad de un departamento es la DIRECCION de CENTROS_COSTOS_2027 en la
  que tiene más centros asignados (así DHUM, DMAT y DCN quedan en FHMCN aunque
  también tengan centros en otras facultades). Solo se revisan las facultades
  con más de un departamento.

  El penúltimo nivel del código indica la sección del centro:
    .01 Facultad e institutos   .02 Departamento   .03 Escuela / pregrado
    .04 Postgrado y formación   .05 Investigación  .06 Servicio y proyección (SYPS)
  En .02 cada departamento tiene el suyo, así que ahí las diferencias son normales.

  1) Centros que tienen unos departamentos de la facultad y otros no.
  2) Ficha del plan TC: conceptos activos que tienen unos departamentos y otros no
     (solo entre los departamentos que tienen asignado ese centro).
*/
WITH asig AS (
    SELECT d.DEPARTAMENTO, d.CENTRO_COSTO, c.DIRECCION
    FROM dbo.CECOS_DEPARTAMENTO_2027 d
    JOIN dbo.CENTROS_COSTOS_2027 c ON c.CENTRO_COSTO = d.CENTRO_COSTO
    WHERE d.DEPARTAMENTO IN (SELECT CODIGO FROM dbo.Departamentos)
      AND c.DIRECCION LIKE 'FACULTAD%'
),
casa AS (
    SELECT DEPARTAMENTO, DIRECCION FROM (
        SELECT DEPARTAMENTO, DIRECCION,
               ROW_NUMBER() OVER (PARTITION BY DEPARTAMENTO ORDER BY COUNT(*) DESC) AS rn
        FROM asig GROUP BY DEPARTAMENTO, DIRECCION) x
    WHERE rn = 1
),
fac AS (
    SELECT DIRECCION, COUNT(*) AS N_DEPTOS FROM casa GROUP BY DIRECCION HAVING COUNT(*) > 1
),
centro AS (
    SELECT c.CENTRO_COSTO, c.DESCRIPCION_CC, c.DIRECCION, f.N_DEPTOS,
           SUBSTRING(c.CENTRO_COSTO, 10, 2) AS SEC
    FROM dbo.CENTROS_COSTOS_2027 c JOIN fac f ON f.DIRECCION = c.DIRECCION
),
cruce AS (
    SELECT ce.*, ca.DEPARTAMENTO,
           CASE WHEN EXISTS (SELECT 1 FROM dbo.CECOS_DEPARTAMENTO_2027 d
                             WHERE d.DEPARTAMENTO = ca.DEPARTAMENTO
                               AND d.CENTRO_COSTO = ce.CENTRO_COSTO) THEN 1 ELSE 0 END AS TIENE
    FROM centro ce JOIN casa ca ON ca.DIRECCION = ce.DIRECCION
)
SELECT DIRECCION AS FACULTAD,
       CASE SEC WHEN '01' THEN '01 Facultad e institutos' WHEN '02' THEN '02 Departamento'
                WHEN '03' THEN '03 Escuela / pregrado'    WHEN '04' THEN '04 Postgrado'
                WHEN '05' THEN '05 Investigación'         WHEN '06' THEN '06 SYPS'
                ELSE SEC END AS SECCION,
       CENTRO_COSTO, DESCRIPCION_CC,
       STRING_AGG(CASE WHEN TIENE = 1 THEN DEPARTAMENTO END, ', ')
           WITHIN GROUP (ORDER BY DEPARTAMENTO) AS LO_TIENEN,
       STRING_AGG(CASE WHEN TIENE = 0 THEN DEPARTAMENTO END, ', ')
           WITHIN GROUP (ORDER BY DEPARTAMENTO) AS NO_LO_TIENEN
FROM cruce
GROUP BY DIRECCION, SEC, CENTRO_COSTO, DESCRIPCION_CC, N_DEPTOS
HAVING SUM(TIENE) < MAX(N_DEPTOS)          -- alguien no lo tiene
ORDER BY FACULTAD, CENTRO_COSTO;


-- 2) Ficha del plan TC
WITH asig AS (
    SELECT d.DEPARTAMENTO, d.CENTRO_COSTO, c.DIRECCION
    FROM dbo.CECOS_DEPARTAMENTO_2027 d
    JOIN dbo.CENTROS_COSTOS_2027 c ON c.CENTRO_COSTO = d.CENTRO_COSTO
    WHERE d.DEPARTAMENTO IN (SELECT CODIGO FROM dbo.Departamentos)
      AND c.DIRECCION LIKE 'FACULTAD%'
),
casa AS (
    SELECT DEPARTAMENTO, DIRECCION FROM (
        SELECT DEPARTAMENTO, DIRECCION,
               ROW_NUMBER() OVER (PARTITION BY DEPARTAMENTO ORDER BY COUNT(*) DESC) AS rn
        FROM asig GROUP BY DEPARTAMENTO, DIRECCION) x
    WHERE rn = 1
),
fac AS (SELECT DIRECCION FROM casa GROUP BY DIRECCION HAVING COUNT(*) > 1),
-- departamentos de la facultad que tienen asignado cada centro
con_centro AS (
    SELECT a.DIRECCION, a.CENTRO_COSTO, a.DEPARTAMENTO
    FROM asig a JOIN casa ca ON ca.DEPARTAMENTO = a.DEPARTAMENTO AND ca.DIRECCION = a.DIRECCION
    WHERE a.DIRECCION IN (SELECT DIRECCION FROM fac)
),
conceptos AS (
    SELECT DISTINCT cc.DIRECCION, t.CENTRO_COSTO, t.CONCEPTO
    FROM dbo.CECO_CONCEPTO_TC t
    JOIN con_centro cc ON cc.DEPARTAMENTO = t.DEPARTAMENTO AND cc.CENTRO_COSTO = t.CENTRO_COSTO
    WHERE t.ACTIVO = 1
),
cruce AS (
    SELECT k.DIRECCION, k.CENTRO_COSTO, k.CONCEPTO, cc.DEPARTAMENTO,
           CASE WHEN EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC t
                             WHERE t.DEPARTAMENTO = cc.DEPARTAMENTO AND t.CENTRO_COSTO = k.CENTRO_COSTO
                               AND t.CONCEPTO = k.CONCEPTO AND t.ACTIVO = 1) THEN 1 ELSE 0 END AS TIENE
    FROM conceptos k
    JOIN con_centro cc ON cc.DIRECCION = k.DIRECCION AND cc.CENTRO_COSTO = k.CENTRO_COSTO
)
SELECT x.DIRECCION AS FACULTAD, x.CENTRO_COSTO, c.DESCRIPCION_CC, x.CONCEPTO,
       STRING_AGG(CASE WHEN TIENE = 1 THEN DEPARTAMENTO END, ', ')
           WITHIN GROUP (ORDER BY DEPARTAMENTO) AS EN_SU_FICHA,
       STRING_AGG(CASE WHEN TIENE = 0 THEN DEPARTAMENTO END, ', ')
           WITHIN GROUP (ORDER BY DEPARTAMENTO) AS FALTA_EN
FROM cruce x JOIN dbo.CENTROS_COSTOS_2027 c ON c.CENTRO_COSTO = x.CENTRO_COSTO
GROUP BY x.DIRECCION, x.CENTRO_COSTO, c.DESCRIPCION_CC, x.CONCEPTO
HAVING MIN(TIENE) = 0
ORDER BY FACULTAD, x.CENTRO_COSTO, x.CONCEPTO;
