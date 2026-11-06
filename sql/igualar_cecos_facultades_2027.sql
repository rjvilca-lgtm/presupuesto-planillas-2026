/*
  Iguala los centros de costo y la ficha del plan TC entre los departamentos de
  una misma facultad (diferencias halladas con sql/verificar_cecos_facultad_2027.sql
  el 06/11/2026).

  No se tocan los centros propios de cada departamento (su departamento, sus
  escuelas, diplomados, maestrías y proyectos), ni los institutos y centros que
  hoy tiene un solo departamento.

  Ningún concepto que se desactiva tiene datos 2027 guardados (si los tuviera,
  no se desactiva). Todo en una transacción y anotado en AUDITORIA_CECOS_2027.
  Se puede ejecutar más de una vez.
*/
SET XACT_ABORT ON;
BEGIN TRAN;

DECLARE @ahora datetime2 = DATEADD(hour, -5, SYSUTCDATETIME());
DECLARE @quien nvarchar(200) = N'sql/igualar_cecos_facultades_2027.sql';

-- 1. Centros que pueden presupuestar
DECLARE @asignar TABLE (DEPARTAMENTO varchar(20), CENTRO_COSTO varchar(20));
INSERT INTO @asignar VALUES
    ('DCCOMP', '01.01.04.01.01'),   -- Facultad de Arquitectura, Computación e Ingeniería
    ('DCCOMP', '01.01.04.06.06'),   -- Gestión hídrica Quilca-Chili (SYPS FACI)
    ('DEDU',   '01.01.05.01.01'),   -- Facultad de Educación y Psicología
    ('DMAT',   '01.01.07.05.04');   -- Proyectos externos - concursos FHMCN

INSERT INTO dbo.CECOS_DEPARTAMENTO_2027 (DEPARTAMENTO, CENTRO_COSTO)
OUTPUT @ahora, @quien, N'ASIGNAR', inserted.DEPARTAMENTO + N' · ' + inserted.CENTRO_COSTO
  INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
SELECT a.DEPARTAMENTO, a.CENTRO_COSTO
FROM @asignar a
WHERE EXISTS (SELECT 1 FROM dbo.CENTROS_COSTOS_2027 c WHERE c.CENTRO_COSTO = a.CENTRO_COSTO)
  AND NOT EXISTS (SELECT 1 FROM dbo.CECOS_DEPARTAMENTO_2027 x
                  WHERE x.DEPARTAMENTO = a.DEPARTAMENTO AND x.CENTRO_COSTO = a.CENTRO_COSTO);

-- 2. Ficha del plan TC: conceptos que ya usan los demás departamentos de la facultad
DECLARE @ficha TABLE (DEPARTAMENTO varchar(20), CENTRO_COSTO varchar(20), CONCEPTO nvarchar(200));
INSERT INTO @ficha VALUES
    -- FACI
    ('DCCOMP', '01.01.04.01.01', N'Facultad de Arquitectura, Computación e Ingeniería'),
    ('DCCOMP', '01.01.04.06.03', N'Servicio a Terceros'),
    -- Educación y Psicología
    ('DEDU',   '01.01.05.05.01', N'Gestión Administrativa Investigación'),
    ('DPSI',   '01.01.05.05.01', N'Horas de Investigación'),
    ('DPSI',   '01.01.05.06.02', N'Proyectos Solidarios'),
    ('DEDU',   '01.01.05.06.04', N'Debate Público'),
    -- Humanidades, Matemática y Ciencias Naturales
    ('DCN',    '01.01.07.01.01', N'Facultad de Humanidades, Matemática y Ciencias Naturales'),
    ('DMAT',   '01.01.07.01.01', N'Facultad de Humanidades, Matemática y Ciencias Naturales'),
    ('DCN',    '01.01.07.03.01', N'Gestión Administrativa Pregrado'),
    ('DMAT',   '01.01.07.03.01', N'Gestión Administrativa Pregrado'),
    ('DCN',    '01.01.07.04.01', N'Gestión Administrativa Postgrado'),
    ('DHUM',   '01.01.07.05.01', N'Gestión Administrativa Investigación'),
    ('DCN',    '01.01.07.06.01', N'Gestión Administrativa SYPS'),
    ('DHUM',   '01.01.07.06.03', N'Servicio a Terceros'),
    ('DMAT',   '01.01.07.06.03', N'Servicio a Terceros');

UPDATE t SET ACTIVO = 1
OUTPUT @ahora, @quien, N'FICHA TC REACTIVAR', inserted.DEPARTAMENTO + N' · ' + inserted.CENTRO_COSTO + N': ' + inserted.CONCEPTO
  INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
FROM dbo.CECO_CONCEPTO_TC t
JOIN @ficha f ON f.DEPARTAMENTO = t.DEPARTAMENTO AND f.CENTRO_COSTO = t.CENTRO_COSTO AND f.CONCEPTO = t.CONCEPTO
WHERE t.ACTIVO = 0;

INSERT INTO dbo.CECO_CONCEPTO_TC (DEPARTAMENTO, CENTRO_COSTO, CONCEPTO, ACTIVO)
OUTPUT @ahora, @quien, N'FICHA TC AGREGAR', inserted.DEPARTAMENTO + N' · ' + inserted.CENTRO_COSTO + N': ' + inserted.CONCEPTO
  INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
SELECT f.DEPARTAMENTO, f.CENTRO_COSTO, f.CONCEPTO, 1
FROM @ficha f
WHERE EXISTS (SELECT 1 FROM dbo.CECOS_DEPARTAMENTO_2027 x
              WHERE x.DEPARTAMENTO = f.DEPARTAMENTO AND x.CENTRO_COSTO = f.CENTRO_COSTO)
  AND NOT EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC x WHERE x.DEPARTAMENTO = f.DEPARTAMENTO
                  AND x.CENTRO_COSTO = f.CENTRO_COSTO AND x.CONCEPTO = f.CONCEPTO);

-- 3. Se desactivan (sin datos guardados):
--    DMAT «Gestion Administrativa Pregrado FHMCN» en 01.01.07.03.01: nombre
--      duplicado; queda «Gestión Administrativa Pregrado», como DHUM.
--    DPSI «Horas de Investigación» en 01.01.05.01.01 (centro de la facultad):
--      pasa a 01.01.05.05.01, el centro de investigación, como DEDU.
DECLARE @quitar TABLE (DEPARTAMENTO varchar(20), CENTRO_COSTO varchar(20), CONCEPTO nvarchar(200));
INSERT INTO @quitar VALUES
    ('DMAT', '01.01.07.03.01', N'Gestion Administrativa Pregrado FHMCN'),
    ('DPSI', '01.01.05.01.01', N'Horas de Investigación');

UPDATE t SET ACTIVO = 0
OUTPUT @ahora, @quien, N'FICHA TC QUITAR', inserted.DEPARTAMENTO + N' · ' + inserted.CENTRO_COSTO + N': ' + inserted.CONCEPTO
  INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
FROM dbo.CECO_CONCEPTO_TC t
JOIN @quitar q ON q.DEPARTAMENTO = t.DEPARTAMENTO AND q.CENTRO_COSTO = t.CENTRO_COSTO AND q.CONCEPTO = t.CONCEPTO
WHERE t.ACTIVO = 1
  AND NOT EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA e WHERE e.PRESUPUESTO = 'PPTO2027'
                  AND e.ORIGEN = t.DEPARTAMENTO AND e.CENTRO_COSTO = t.CENTRO_COSTO
                  AND e.CONCEPTO = t.CONCEPTO);

COMMIT;

-- Resumen de lo hecho (luego ejecutar sql/verificar_cecos_facultad_2027.sql)
SELECT ACCION, DETALLE FROM dbo.AUDITORIA_CECOS_2027
WHERE EMAIL = @quien AND FECHA >= DATEADD(minute, -1, @ahora)
ORDER BY ACCION, DETALLE;
