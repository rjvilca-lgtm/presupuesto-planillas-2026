/*
  Ficha TC: centros de costo de gestión con un solo concepto de horas.

  1. DHUM 01.01.07.03.01 (GESTION ADMINISTRATIVA PREGRADO FHMCN) tenía horas
     de dictado (académicas y cronológicas) y Otras Actividades Pregrado:
     venían del centro genérico 03.01.11.02.01 «ESCUELA» de 2026. Queda con
     un solo concepto, «Gestión Administrativa Pregrado».
     Lo ya guardado en 2027 se pasa a ese concepto con las horas que contaban
     para el docente (cronológicas + otras; las académicas no suman al total),
     así el total de cada docente no cambia. Se sube la versión del plan TC de
     DHUM: quien lo tenga abierto verá el aviso para recargar en vez de
     volver a guardar la estructura vieja.

  2. Mismo concepto con dos nombres en un centro de costo (en 2026 el
     I semestre usaba uno en mayúsculas y el II el estándar, con los mismos
     docentes). Se deja un solo nombre.

  No se tocan los centros de Investigación: «Gestión Administrativa
  Investigación» y «Horas de Investigación» se usaban a la vez, con distintos
  docentes; son actividades distintas.

  Si un plan 2027 ya tiene horas en un nombre que se quita (punto 2), el
  script se detiene sin cambiar nada (al 2026-10-29 no había ninguno).
  Se puede ejecutar más de una vez.
*/

SET XACT_ABORT ON;
BEGIN TRANSACTION;

------------------------------------------------------------------ 1. DHUM
DECLARE @nuevo nvarchar(200) = N'Gestión Administrativa Pregrado';
DECLARE @viejos TABLE (CONCEPTO nvarchar(200), CUENTA bit);
INSERT INTO @viejos VALUES
    (N'Horas Dictado Pregrado (académicas)', 0),     -- ya están en las cronológicas
    (N'Horas Dictado Pregrado (cronológicas)', 1),
    (N'Otras Actividades Pregrado', 1);

INSERT INTO dbo.DATOS_ENTRADA (PRESUPUESTO, HOJA_ORIGEN, ORIGEN, DNI, NOMBRE, CENTRO_COSTO,
                               CONCEPTO, MES, HORAS)
SELECT d.PRESUPUESTO, d.HOJA_ORIGEN, d.ORIGEN, d.DNI, MAX(d.NOMBRE), d.CENTRO_COSTO,
       @nuevo, d.MES, SUM(d.HORAS)
FROM dbo.DATOS_ENTRADA d
JOIN @viejos v ON v.CONCEPTO = LTRIM(RTRIM(d.CONCEPTO)) AND v.CUENTA = 1
WHERE d.PRESUPUESTO = 'PPTO2027' AND d.ORIGEN = 'DHUM' AND d.CENTRO_COSTO = '01.01.07.03.01'
  AND NOT EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA x
                  WHERE x.PRESUPUESTO = d.PRESUPUESTO AND x.HOJA_ORIGEN = d.HOJA_ORIGEN
                    AND x.ORIGEN = d.ORIGEN AND x.DNI = d.DNI AND x.CENTRO_COSTO = d.CENTRO_COSTO
                    AND x.CONCEPTO = @nuevo AND x.MES = d.MES)
GROUP BY d.PRESUPUESTO, d.HOJA_ORIGEN, d.ORIGEN, d.DNI, d.CENTRO_COSTO, d.MES
HAVING SUM(d.HORAS) > 0;
PRINT CONCAT('DHUM: filas guardadas pasadas a Gestión Administrativa Pregrado: ', @@ROWCOUNT);

DELETE d FROM dbo.DATOS_ENTRADA d
JOIN @viejos v ON v.CONCEPTO = LTRIM(RTRIM(d.CONCEPTO))
WHERE d.PRESUPUESTO = 'PPTO2027' AND d.ORIGEN = 'DHUM' AND d.CENTRO_COSTO = '01.01.07.03.01';
PRINT CONCAT('DHUM: filas de dictado/otras quitadas: ', @@ROWCOUNT);

-- Solo la primera vez (mientras la estructura vieja exista)
UPDATE dbo.GUARDADOS_2027
SET VERSION = VERSION + 1, EMAIL = N'Presupuesto (ajuste de conceptos)',
    FECHA = DATEADD(hour, -5, SYSUTCDATETIME())
WHERE PRESUPUESTO = 'PPTO2027' AND ORIGEN = 'DHUM'
  AND HOJA_ORIGEN IN ('1. Plan TC-I', 'Plan TC-II')
  AND EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC
              WHERE DEPARTAMENTO = 'DHUM' AND CENTRO_COSTO = N'01.01.07.03.01'
                AND CONCEPTO <> @nuevo);

DELETE FROM dbo.CECO_CONCEPTO_TC
WHERE DEPARTAMENTO = 'DHUM' AND CENTRO_COSTO = N'01.01.07.03.01' AND CONCEPTO <> @nuevo;
IF NOT EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC
               WHERE DEPARTAMENTO = 'DHUM' AND CENTRO_COSTO = N'01.01.07.03.01')
    INSERT INTO dbo.CECO_CONCEPTO_TC (DEPARTAMENTO, CENTRO_COSTO, CONCEPTO)
    VALUES ('DHUM', N'01.01.07.03.01', @nuevo);

------------------------------------------------- 2. Un nombre por concepto
DECLARE @pares TABLE (DEPARTAMENTO varchar(10), CENTRO_COSTO nvarchar(100),
                      VARIANTE nvarchar(200), ESTANDAR nvarchar(200));
INSERT INTO @pares VALUES
    ('DAIC',   N'01.01.04.02.01', N'GESTION ADMINISTRATIVA DAIC', N'Gestión Administrativa del Departamento'),
    ('DCCOMP', N'01.01.04.02.02', N'GESTION ADMINISTRATIVA DCC',  N'Gestión Administrativa del Departamento'),
    ('DCEE',   N'01.01.02.02.01', N'GESTION ADMINISTRATIVA DCEE', N'Gestión Administrativa del Departamento'),
    ('DCS',    N'01.01.06.02.01', N'GESTION ADMINISTRATIVA DCS',  N'Gestión Administrativa del Departamento'),
    ('DDER',   N'01.01.03.02.01', N'GESTION ADMINISTRATIVA DDCP', N'Gestión Administrativa del Departamento'),
    ('DEDU',   N'01.01.05.02.02', N'GESTION ADMINISTRATIVA DE',   N'Gestión Administrativa del Departamento'),
    ('DIIA',   N'01.01.04.02.03', N'GESTION ADMINISTRATIVA DII',  N'Gestión Administrativa del Departamento'),
    ('DAIC',   N'01.01.04.06.01', N'GESTION ADMINISTRATIVA SERVICIO Y PROYECCION A LA SOCIEDAD DAIC', N'Gestión Administrativa SYPS'),
    ('DCCOMP', N'01.01.04.06.01', N'GESTION ADMINISTRATIVA SERVICIO Y PROYECCION A LA SOCIEDAD DCC',  N'Gestión Administrativa SYPS'),
    ('DDER',   N'01.01.03.06.01', N'GESTION ADMINISTRATIVA SERVICIO Y PROYECCION A LA SOCIEDAD DCP',  N'Gestión Administrativa SYPS'),
    ('DEDU',   N'01.01.05.06.01', N'GESTION ADMINISTRATIVA SERVICIO Y PROYECCION A LA SOCIEDAD DED',  N'Gestión Administrativa SYPS'),
    ('DIIA',   N'01.01.04.06.01', N'GESTION ADMINISTRATIVA SERVICIO Y PROYECCION A LA SOCIEDAD DII',  N'Gestión Administrativa SYPS'),
    ('DAIC',   N'01.01.04.06.02', N'PROYECTOS SOLIDARIOS DAIC', N'Proyectos Solidarios'),
    ('DCCOMP', N'01.01.04.06.02', N'PROYECTOS SOLIDARIOS DCC',  N'Proyectos Solidarios'),
    ('DAIC',   N'01.01.04.06.03', N'SERVICIOS A TERCEROS DAIC', N'Servicio a Terceros'),
    -- DEDU: el II semestre de 2026 usaba un concepto de otro centro
    ('DEDU',   N'01.01.05.06.02', N'PROYECTOS SOLIDARIOS DED', N'Proyectos Solidarios'),
    ('DEDU',   N'01.01.05.06.02', N'Centro de Gestión de Proyectos e Infraestructura', N'Proyectos Solidarios'),
    ('DEDU',   N'01.01.05.01.04', N'Proyectos Solidarios', N'CENTRO DE DESARROLLO PARA LA EDUCACION');

IF EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA d JOIN @pares p
             ON d.ORIGEN = p.DEPARTAMENTO AND d.CENTRO_COSTO = p.CENTRO_COSTO
            AND LTRIM(RTRIM(d.CONCEPTO)) = p.VARIANTE
           WHERE d.PRESUPUESTO = 'PPTO2027')
    THROW 50031, 'Hay planes 2027 con horas en un nombre que se quita: no se cambió nada. Avisa para pasarlas al nombre estándar.', 1;

INSERT INTO dbo.CECO_CONCEPTO_TC (DEPARTAMENTO, CENTRO_COSTO, CONCEPTO)
SELECT DISTINCT p.DEPARTAMENTO, p.CENTRO_COSTO, p.ESTANDAR FROM @pares p
WHERE NOT EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC t
                  WHERE t.DEPARTAMENTO = p.DEPARTAMENTO AND t.CENTRO_COSTO = p.CENTRO_COSTO
                    AND t.CONCEPTO = p.ESTANDAR);
PRINT CONCAT('Nombres estándar agregados: ', @@ROWCOUNT);

DELETE t FROM dbo.CECO_CONCEPTO_TC t
JOIN @pares p ON t.DEPARTAMENTO = p.DEPARTAMENTO AND t.CENTRO_COSTO = p.CENTRO_COSTO
             AND t.CONCEPTO = p.VARIANTE;
PRINT CONCAT('Nombres repetidos quitados: ', @@ROWCOUNT);

COMMIT;
GO

-- Verificación: centros de gestión, de departamento, SYPS, proyectos y centros
-- con más de un concepto (solo deben quedar los de Investigación y DMAT
-- 01.01.07.02.02, que también tiene Gestión de Dirección)
SELECT t.DEPARTAMENTO, t.CENTRO_COSTO, c.DESCRIPCION_CC, COUNT(*) AS CONCEPTOS,
       STRING_AGG(CAST(t.CONCEPTO AS nvarchar(max)), ' | ') AS NOMBRES
FROM dbo.CECO_CONCEPTO_TC t
JOIN dbo.CENTROS_COSTOS_2027 c ON c.CENTRO_COSTO = t.CENTRO_COSTO
WHERE t.ACTIVO = 1 AND c.DESCRIPCION_CC NOT LIKE 'ESCUELA%'
GROUP BY t.DEPARTAMENTO, t.CENTRO_COSTO, c.DESCRIPCION_CC
HAVING COUNT(*) > 1
ORDER BY t.DEPARTAMENTO, t.CENTRO_COSTO;

SELECT CENTRO_COSTO, CONCEPTO FROM dbo.CECO_CONCEPTO_TC
WHERE DEPARTAMENTO = 'DHUM' AND CENTRO_COSTO = N'01.01.07.03.01';
