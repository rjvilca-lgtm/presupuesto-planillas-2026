/*
  Computación (DCCOMP) tras la nueva codificación del 19/11 (migracion_cecos_2027_v2).

  FACI se dividió en Facultad de Computación (01.01.04.*) y Facultad de
  Arquitectura e Ingeniería (01.01.05.*). La migración pasó los centros de la
  antigua FACI (01.01.04.*) a 01.01.05.* en todas las fichas, también en la de
  DCCOMP, que ahora tiene su propia facultad. Resultado: la ficha TC de DCCOMP
  ofrece la Facultad, la gestión de postgrado, de investigación y SYPS de FACI,
  y DCCOMP tiene asignados 11 centros de FACI.

  Este script:
    1. En la ficha TC de DCCOMP (CECO_CONCEPTO_TC) cambia cada centro 01.01.05.*
       por su equivalente de Computación 01.01.04.* (mismo concepto; el de la
       facultad pasa a «Facultad de Computación»).
    2. Quita a DCCOMP los centros 01.01.05.* (FACI) de CECOS_DEPARTAMENTO_2027.

  Se detiene sin cambiar nada si DCCOMP tiene datos 2027 guardados en algún
  centro 01.01.05.* (hoy no tiene). No toca CENTROS_COSTOS ni
  CENTROS_COSTOS_2027 ni los demás departamentos. Se puede ejecutar más de una vez.
*/

SET XACT_ABORT ON;
BEGIN TRAN;

IF EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA
           WHERE PRESUPUESTO = 'PPTO2027' AND ORIGEN = 'DCCOMP'
             AND LTRIM(RTRIM(CENTRO_COSTO)) LIKE '01.01.05.%')
    THROW 50001, 'DCCOMP tiene datos 2027 en centros de FACI (01.01.05.*): revisarlos antes.', 1;

DECLARE @mapa TABLE (ANTES varchar(20), DESPUES varchar(20));
INSERT INTO @mapa VALUES
    ('01.01.05.01.01', '01.01.04.01.01'),   -- Facultad
    ('01.01.05.04.01', '01.01.04.04.01'),   -- Gestión administrativa postgrado
    ('01.01.05.05.01', '01.01.04.05.01'),   -- Gestión administrativa investigación
    ('01.01.05.06.01', '01.01.04.06.01'),   -- Gestión administrativa SYPS
    ('01.01.05.06.02', '01.01.04.06.02'),   -- Proyectos solidarios
    ('01.01.05.06.03', '01.01.04.06.03'),   -- Servicios a terceros
    ('01.01.05.06.04', '01.01.04.06.04');   -- Debate público

-- 1. Ficha TC: si ya existe la fila de destino, se borra la de FACI; si no, se cambia el centro
DELETE t FROM dbo.CECO_CONCEPTO_TC t JOIN @mapa m ON m.ANTES = t.CENTRO_COSTO
WHERE t.DEPARTAMENTO = 'DCCOMP'
  AND EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC x
              WHERE x.DEPARTAMENTO = 'DCCOMP' AND x.CENTRO_COSTO = m.DESPUES
                AND x.CONCEPTO = t.CONCEPTO);
UPDATE t SET t.CENTRO_COSTO = m.DESPUES
FROM dbo.CECO_CONCEPTO_TC t JOIN @mapa m ON m.ANTES = t.CENTRO_COSTO
WHERE t.DEPARTAMENTO = 'DCCOMP';
UPDATE dbo.CECO_CONCEPTO_TC SET CONCEPTO = N'Facultad de Computación'
WHERE DEPARTAMENTO = 'DCCOMP' AND CENTRO_COSTO = '01.01.04.01.01'
  AND CONCEPTO = N'Facultad de Arquitectura, Computación e Ingeniería';

-- 2. Centros asignados: fuera los de FACI
DELETE FROM dbo.CECOS_DEPARTAMENTO_2027
WHERE DEPARTAMENTO = 'DCCOMP' AND CENTRO_COSTO LIKE '01.01.05.%';

INSERT INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
VALUES (DATEADD(HOUR, -5, SYSUTCDATETIME()), 'script', 'CORREGIR',
        N'DCCOMP: ficha TC y centros de FACI (01.01.05) → Facultad de Computación (01.01.04)');

COMMIT;
GO

-- Verificación 1: ficha TC de DCCOMP, solo centros 01.01.04.* y '0'
SELECT CENTRO_COSTO, CONCEPTO, ACTIVO FROM dbo.CECO_CONCEPTO_TC
WHERE DEPARTAMENTO = 'DCCOMP' ORDER BY CENTRO_COSTO, CONCEPTO;
-- Verificación 2: centros de DCCOMP por facultad (debe quedar solo FACULTAD DE COMPUTACION, 31)
SELECT c.DIRECCION, COUNT(*) AS CENTROS
FROM dbo.CECOS_DEPARTAMENTO_2027 d JOIN dbo.CENTROS_COSTOS_2027 c ON c.CENTRO_COSTO = d.CENTRO_COSTO
WHERE d.DEPARTAMENTO = 'DCCOMP' GROUP BY c.DIRECCION;
