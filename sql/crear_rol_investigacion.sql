/*
  Rol INVESTIGACION (gestor de investigación) en USUARIOS_PLANILLAS.

  Como DEPARTAMENTO, lleva el código del departamento (una fila por cada
  departamento que gestiona). En la app solo ve la planilla de Investigación
  de esos departamentos y puede guardarla, no valorizarla. Si un
  departamento tiene gestor, sus usuarios ven esa planilla en solo lectura y
  la valorizan desde «Resumen y valorización».

  No crea tablas ni permisos nuevos: la app ya lee USUARIOS_PLANILLAS.
  Se puede ejecutar más de una vez.
*/

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_USUARIOS_PLANILLAS_ROL')
    ALTER TABLE dbo.USUARIOS_PLANILLAS DROP CONSTRAINT CK_USUARIOS_PLANILLAS_ROL;
ALTER TABLE dbo.USUARIOS_PLANILLAS ADD CONSTRAINT CK_USUARIOS_PLANILLAS_ROL
    CHECK (ROL IN ('PRESUPUESTO', 'DGA', 'DESARROLLO_HUMANO', 'DEPARTAMENTO', 'AREA',
                   'INVESTIGACION'));

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_USUARIOS_PLANILLAS_DEPTO')
    ALTER TABLE dbo.USUARIOS_PLANILLAS DROP CONSTRAINT CK_USUARIOS_PLANILLAS_DEPTO;
ALTER TABLE dbo.USUARIOS_PLANILLAS ADD CONSTRAINT CK_USUARIOS_PLANILLAS_DEPTO
    CHECK ((ROL IN ('DEPARTAMENTO', 'AREA', 'INVESTIGACION') AND DEPARTAMENTO IS NOT NULL)
        OR (ROL NOT IN ('DEPARTAMENTO', 'AREA', 'INVESTIGACION') AND DEPARTAMENTO IS NULL));
GO

-- Verificación
SELECT name, definition FROM sys.check_constraints
WHERE parent_object_id = OBJECT_ID('dbo.USUARIOS_PLANILLAS');
