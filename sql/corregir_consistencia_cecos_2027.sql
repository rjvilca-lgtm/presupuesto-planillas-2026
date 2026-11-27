/*
  Restos de la recodificación de centros 2027 (19/11) en la ficha TC.

  1. Fichas TC de DAIC, DIEE y DIIA: en 01.01.05.01.01 conviven el concepto
     antiguo «Facultad de Arquitectura, Computación e Ingeniería» (FACI antes de
     separarse Computación) y el nuevo «FACULTAD DE ARQUITECTURA E INGENIERÍA».
     Las horas guardadas con el nombre antiguo pasan al nuevo (ningún docente
     tiene los dos en el mismo mes: no hay que sumar) y el antiguo se desactiva.
     El centro no cambia, así que el importe valorizado tampoco.

  No toca CENTROS_COSTOS ni CENTROS_COSTOS_2027. Se puede ejecutar más de una vez.
*/

SET XACT_ABORT ON;
BEGIN TRAN;

DECLARE @centro varchar(20) = '01.01.05.01.01',
        @viejo  nvarchar(200) = N'Facultad de Arquitectura, Computación e Ingeniería',
        @nuevo  nvarchar(200) = N'FACULTAD DE ARQUITECTURA E INGENIERÍA';

-- 1a. Seguridad: si un docente tuviera los dos conceptos el mismo mes, detenerse
IF EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA a JOIN dbo.DATOS_ENTRADA b
             ON b.PRESUPUESTO = a.PRESUPUESTO AND b.ORIGEN = a.ORIGEN AND b.HOJA_ORIGEN = a.HOJA_ORIGEN
            AND b.DNI = a.DNI AND ISNULL(b.MES, '') = ISNULL(a.MES, '')
            AND LTRIM(RTRIM(b.CENTRO_COSTO)) = @centro AND b.CONCEPTO = @nuevo
           WHERE a.PRESUPUESTO = 'PPTO2027' AND LTRIM(RTRIM(a.CENTRO_COSTO)) = @centro
             AND a.CONCEPTO = @viejo)
    THROW 50001, 'Hay docentes con los dos conceptos de facultad en el mismo mes: revisar a mano.', 1;

-- 1b. Horas guardadas y valorizadas: al concepto nuevo
UPDATE dbo.DATOS_ENTRADA SET CONCEPTO = @nuevo
WHERE PRESUPUESTO = 'PPTO2027' AND LTRIM(RTRIM(CENTRO_COSTO)) = @centro AND CONCEPTO = @viejo;
PRINT CONCAT('DATOS_ENTRADA: ', @@ROWCOUNT);
UPDATE dbo.PLANILLA SET CONCEPTO = @nuevo
WHERE AÑO = '2027' AND LTRIM(RTRIM(CENTRO_COSTO)) = @centro AND CONCEPTO = @viejo;
PRINT CONCAT('PLANILLA 2027: ', @@ROWCOUNT);

-- 1c. Ficha TC: el concepto nuevo activo en cada departamento que tenía el viejo; el viejo, inactivo
INSERT INTO dbo.CECO_CONCEPTO_TC (DEPARTAMENTO, CENTRO_COSTO, CONCEPTO, ACTIVO)
SELECT t.DEPARTAMENTO, @centro, @nuevo, 1 FROM dbo.CECO_CONCEPTO_TC t
WHERE t.CENTRO_COSTO = @centro AND t.CONCEPTO = @viejo
  AND NOT EXISTS (SELECT 1 FROM dbo.CECO_CONCEPTO_TC x WHERE x.DEPARTAMENTO = t.DEPARTAMENTO
                  AND x.CENTRO_COSTO = @centro AND x.CONCEPTO = @nuevo);
UPDATE dbo.CECO_CONCEPTO_TC SET ACTIVO = 1
WHERE CENTRO_COSTO = @centro AND CONCEPTO = @nuevo
  AND DEPARTAMENTO IN (SELECT DEPARTAMENTO FROM dbo.CECO_CONCEPTO_TC
                       WHERE CENTRO_COSTO = @centro AND CONCEPTO = @viejo);
UPDATE dbo.CECO_CONCEPTO_TC SET ACTIVO = 0
WHERE CENTRO_COSTO = @centro AND CONCEPTO = @viejo AND ACTIVO = 1;
PRINT CONCAT('Ficha TC, concepto antiguo desactivado: ', @@ROWCOUNT);

INSERT INTO dbo.AUDITORIA_CECOS_2027 (FECHA, EMAIL, ACCION, DETALLE)
VALUES (DATEADD(HOUR, -5, SYSUTCDATETIME()), 'script', 'CORREGIR',
        N'Ficha TC DAIC/DIEE/DIIA: «Facultad de Arquitectura, Computación e Ingeniería» → «FACULTAD DE ARQUITECTURA E INGENIERÍA»');

COMMIT;
GO

-- Verificación 1: un solo concepto de facultad activo por departamento en 01.01.05.01.01
SELECT DEPARTAMENTO, CONCEPTO, ACTIVO FROM dbo.CECO_CONCEPTO_TC
WHERE CENTRO_COSTO = '01.01.05.01.01' ORDER BY DEPARTAMENTO, ACTIVO DESC;
-- Verificación 2: nada guardado con el concepto antiguo (esperado: 0)
SELECT COUNT(*) AS FILAS_CONCEPTO_ANTIGUO FROM dbo.DATOS_ENTRADA
WHERE PRESUPUESTO = 'PPTO2027' AND CONCEPTO = N'Facultad de Arquitectura, Computación e Ingeniería';
-- Verificación 3: focos con cuentas y sin centros (esperado: ninguno)
SELECT u.FOCO, COUNT(*) AS CUENTAS FROM dbo.USUARIOS_FOCOS_2027 u
WHERE NOT EXISTS (SELECT 1 FROM dbo.vw_CENTROS_2027_PROYECTO p WHERE p.FOCO = u.FOCO)
GROUP BY u.FOCO;
