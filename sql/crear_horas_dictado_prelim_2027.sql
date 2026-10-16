/*
  Horas de dictado preliminares 2027 para precargar el Plan TC.

  Los departamentos llenaron las horas de dictado de sus docentes TC por
  semestre (BASE_HORAS_DOCENTES_TC_2027.xlsx). Al abrir la ficha TC, las de
  cada docente aparecen ya escritas en "Horas Dictado Pregrado (académicas)"
  (y sus cronológicas calculadas), mientras ese docente no tenga nada guardado
  en ese semestre. El departamento las revisa, completa el resto del plan y
  guarda.

  Este script solo crea la tabla. Los datos llevan DNI y NO van en el
  repositorio (es público): se cargan con el script generado aparte
  (cargar_horas_dictado_prelim_2027.sql), que ya trae las horas repartidas
  por centro de costo.

  Se puede ejecutar más de una vez.
*/

IF OBJECT_ID('dbo.HORAS_DICTADO_PRELIM_2027', 'U') IS NULL
    CREATE TABLE dbo.HORAS_DICTADO_PRELIM_2027 (
        DNI          nvarchar(20)  NOT NULL,
        DPTO         varchar(10)   NOT NULL,
        HOJA_ORIGEN  nvarchar(100) NOT NULL,   -- '1. Plan TC-I' o 'Plan TC-II'
        CENTRO_COSTO nvarchar(50)  NOT NULL,
        HORAS        decimal(10,2) NOT NULL,   -- horas académicas semanales
        CONSTRAINT PK_HORAS_DICTADO_PRELIM_2027 PRIMARY KEY (DPTO, HOJA_ORIGEN, DNI, CENTRO_COSTO)
    );
GO

IF EXISTS (SELECT 1 FROM sys.database_principals WHERE name = 'rol_app_planillas' AND type = 'R')
    GRANT SELECT ON dbo.HORAS_DICTADO_PRELIM_2027 TO rol_app_planillas;
GO

SELECT OBJECT_ID('dbo.HORAS_DICTADO_PRELIM_2027', 'U') AS tabla;
