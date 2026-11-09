/*
  Rol POSTGRADO en USUARIOS_PLANILLAS.

  Ve la planilla de Postgrado de TODOS los departamentos, en solo lectura
  (no guarda ni valoriza; eso lo sigue haciendo cada departamento). No ve
  las demás planillas, ni el resumen de valorización, ni la consulta de
  carga académica.

  Como PRESUPUESTO o DGA, va sin departamento (DEPARTAMENTO = NULL): una
  sola fila por correo. Se da desde Administración › Usuarios, rol
  «Postgrado (ver todos)».

  Solo amplía las dos restricciones de la columna ROL. No crea tablas ni
  permisos nuevos. Se puede ejecutar más de una vez.
*/

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_USUARIOS_PLANILLAS_ROL')
    ALTER TABLE dbo.USUARIOS_PLANILLAS DROP CONSTRAINT CK_USUARIOS_PLANILLAS_ROL;
ALTER TABLE dbo.USUARIOS_PLANILLAS ADD CONSTRAINT CK_USUARIOS_PLANILLAS_ROL
    CHECK (ROL IN ('PRESUPUESTO', 'DGA', 'DESARROLLO_HUMANO', 'DEPARTAMENTO', 'AREA',
                   'INVESTIGACION', 'PUESTOS', 'POSTGRADO'));

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_USUARIOS_PLANILLAS_DEPTO')
    ALTER TABLE dbo.USUARIOS_PLANILLAS DROP CONSTRAINT CK_USUARIOS_PLANILLAS_DEPTO;
ALTER TABLE dbo.USUARIOS_PLANILLAS ADD CONSTRAINT CK_USUARIOS_PLANILLAS_DEPTO
    CHECK ((ROL IN ('DEPARTAMENTO', 'AREA', 'INVESTIGACION', 'PUESTOS') AND DEPARTAMENTO IS NOT NULL)
        OR (ROL NOT IN ('DEPARTAMENTO', 'AREA', 'INVESTIGACION', 'PUESTOS') AND DEPARTAMENTO IS NULL));
GO

-- Verificación
SELECT name, definition FROM sys.check_constraints
WHERE parent_object_id = OBJECT_ID('dbo.USUARIOS_PLANILLAS');
