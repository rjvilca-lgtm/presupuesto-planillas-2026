/*
  Puestos nuevos 2027: rol PUESTOS en USUARIOS_PLANILLAS.

  Como DEPARTAMENTO, lleva un código: el del departamento o el del área no
  académica cuyos puestos nuevos registra (una fila por cada uno). En la app
  ve solo la pestaña «Puestos nuevos». Lo que registra va a DATOS_ENTRADA
  con HOJA_ORIGEN = 'Puestos nuevos' (en HORAS la cantidad de puestos del
  mes, en TARIFA el costo mensual y en IMPORTE puestos × costo).

  El costo mensual de cada puesto (sueldo, bonos, Edenred y cargas sociales)
  va en tarifas_2027 con HOJA_ORIGEN = 'Puestos nuevos'. Esos montos NO están
  en este archivo (el repositorio es público): se cargan con
  sql/cargar_costos_puestos_2027_privado.sql, que queda solo en la carpeta
  local, y después se pueden ajustar desde Administración › Parámetros.

  No crea tablas ni permisos nuevos: la app ya escribe DATOS_ENTRADA y lee
  tarifas_2027. Se puede ejecutar más de una vez.
*/

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_USUARIOS_PLANILLAS_ROL')
    ALTER TABLE dbo.USUARIOS_PLANILLAS DROP CONSTRAINT CK_USUARIOS_PLANILLAS_ROL;
ALTER TABLE dbo.USUARIOS_PLANILLAS ADD CONSTRAINT CK_USUARIOS_PLANILLAS_ROL
    CHECK (ROL IN ('PRESUPUESTO', 'DGA', 'DESARROLLO_HUMANO', 'DEPARTAMENTO', 'AREA',
                   'INVESTIGACION', 'PUESTOS'));

IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name = 'CK_USUARIOS_PLANILLAS_DEPTO')
    ALTER TABLE dbo.USUARIOS_PLANILLAS DROP CONSTRAINT CK_USUARIOS_PLANILLAS_DEPTO;
ALTER TABLE dbo.USUARIOS_PLANILLAS ADD CONSTRAINT CK_USUARIOS_PLANILLAS_DEPTO
    CHECK ((ROL IN ('DEPARTAMENTO', 'AREA', 'INVESTIGACION', 'PUESTOS') AND DEPARTAMENTO IS NOT NULL)
        OR (ROL NOT IN ('DEPARTAMENTO', 'AREA', 'INVESTIGACION', 'PUESTOS') AND DEPARTAMENTO IS NULL));
GO

-- Verificación
SELECT name, definition FROM sys.check_constraints
WHERE parent_object_id = OBJECT_ID('dbo.USUARIOS_PLANILLAS');
SELECT COUNT(*) AS COSTOS_DE_PUESTOS_CARGADOS FROM dbo.tarifas_2027
WHERE HOJA_ORIGEN = 'Puestos nuevos';
