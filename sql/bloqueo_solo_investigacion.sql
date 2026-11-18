/*
  «Habilitar solo Investigación» (Presupuesto › Plazos y bloqueos).

  ESTADO_DEPARTAMENTO.BLOQUEO acepta un tercer valor, 'SOLO_INV': el
  departamento queda en solo lectura salvo la planilla de Investigación, que
  puede modificar y valorizar (solo sp_Valorizar_Investigacion_2027), aunque
  esté bloqueado por fecha o cerrado. Para quitarlo, Presupuesto elige
  Bloquear, Desbloquear o Usar fecha general.

  Solo cambia la restricción CHECK; no toca datos. Se puede ejecutar más de una vez.
*/

IF EXISTS (SELECT 1 FROM sys.check_constraints
           WHERE name = 'CK_ESTADO_DEPARTAMENTO_BLOQUEO'
             AND parent_object_id = OBJECT_ID('dbo.ESTADO_DEPARTAMENTO'))
    ALTER TABLE dbo.ESTADO_DEPARTAMENTO DROP CONSTRAINT CK_ESTADO_DEPARTAMENTO_BLOQUEO;
GO

ALTER TABLE dbo.ESTADO_DEPARTAMENTO ADD CONSTRAINT CK_ESTADO_DEPARTAMENTO_BLOQUEO
    CHECK (BLOQUEO IS NULL OR BLOQUEO IN ('ABIERTO', 'BLOQUEADO', 'SOLO_INV'));
GO

-- Verificación: debe listar los tres valores
SELECT definition FROM sys.check_constraints WHERE name = 'CK_ESTADO_DEPARTAMENTO_BLOQUEO';
