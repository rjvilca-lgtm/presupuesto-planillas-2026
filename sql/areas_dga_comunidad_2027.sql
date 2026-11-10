/*
  Áreas de ayudantías (y prácticas) 2027:

  1. La Dirección de Gestión Académica pasa de GESAC a DGA. DGA es también el
     código de la carga académica: comparten ORIGEN en DATOS_ENTRADA y
     PLANILLA, pero con distinta HOJA_ORIGEN / ORIGEN ('Ayudantias',
     'Practicas' y 'Carga Academica'), y cada sp borra solo lo suyo. La app
     ya no marca el flujo de la carga académica al guardar las ayudantías
     del área DGA. Si GESAC ya tuviera datos o usuarios, el script se detiene
     sin cambiar nada.

  2. Nueva área DCU · Dirección de Comunidad Universitaria. No es una
     dirección del catálogo: sus centros son los 01.03.01.04.* de PERSONA Y
     CULTURA. Para eso AREAS_2027 recibe la columna PREFIJO_CECO (opcional):
     si tiene valor, el área ve solo los centros de su dirección que empiezan
     con él. El área PYC (Persona y Cultura) sigue viendo todos los suyos.

  No toca CENTROS_COSTOS ni CENTROS_COSTOS_2027. Se puede ejecutar más de una vez.
*/

IF COL_LENGTH('dbo.AREAS_2027', 'PREFIJO_CECO') IS NULL
    ALTER TABLE dbo.AREAS_2027 ADD PREFIJO_CECO nvarchar(50) NULL;
GO

SET XACT_ABORT ON;
BEGIN TRAN;

IF EXISTS (SELECT 1 FROM dbo.AREAS_2027 WHERE CODIGO = 'GESAC')
BEGIN
    IF EXISTS (SELECT 1 FROM dbo.USUARIOS_PLANILLAS WHERE DEPARTAMENTO = 'GESAC')
       OR EXISTS (SELECT 1 FROM dbo.DATOS_ENTRADA WHERE ORIGEN = 'GESAC')
       OR EXISTS (SELECT 1 FROM dbo.PLANILLA WHERE ORIGEN_2 = 'GESAC')
       OR EXISTS (SELECT 1 FROM dbo.GUARDADOS_2027 WHERE ORIGEN = 'GESAC')
        THROW 50001, 'GESAC ya tiene usuarios o datos: revisarlos antes de renombrar a DGA.', 1;
    DELETE FROM dbo.ESTADO_DEPARTAMENTO WHERE DEPARTAMENTO = 'GESAC';   -- solo fechas, sin datos
    UPDATE dbo.AREAS_2027 SET CODIGO = 'DGA' WHERE CODIGO = 'GESAC';
END

IF NOT EXISTS (SELECT 1 FROM dbo.AREAS_2027 WHERE CODIGO = 'DCU')
    INSERT INTO dbo.AREAS_2027 (CODIGO, DESCRIPCION, DIRECCION, ACTIVO, PREFIJO_CECO)
    VALUES ('DCU', N'Dirección de Comunidad Universitaria', N'PERSONA Y CULTURA', 1,
            N'01.03.01.04.');

COMMIT;
GO

-- Verificación: DGA y DCU en la lista; DCU con 9 centros (01.03.01.04.01 a .09)
SELECT CODIGO, DESCRIPCION, DIRECCION, PREFIJO_CECO, ACTIVO FROM dbo.AREAS_2027
WHERE CODIGO IN ('DGA', 'GESAC', 'DCU', 'PYC');
SELECT a.CODIGO, COUNT(*) AS CENTROS
FROM dbo.AREAS_2027 a JOIN dbo.CENTROS_COSTOS_2027 c ON c.DIRECCION = a.DIRECCION
WHERE a.CODIGO IN ('DGA', 'DCU', 'PYC')
  AND (a.PREFIJO_CECO IS NULL OR c.CENTRO_COSTO LIKE a.PREFIJO_CECO + '%')
GROUP BY a.CODIGO;
