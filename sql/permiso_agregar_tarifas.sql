/*
  Desarrollo Humano › Tarifas › «Agregar tarifa» / «Agregar puesto».

  La app ya podía leer y modificar tarifas_2027 (SELECT, UPDATE); para dar de
  alta tipos nuevos (Horas adicionales, Ayudantías y puestos nuevos) necesita
  INSERT. No se da DELETE: la app no borra tarifas. Cada alta queda en
  AUDITORIA_DESARROLLO_HUMANO (ACCION = 'ALTA').

  No toca datos. Se puede ejecutar más de una vez.
*/

GRANT INSERT ON dbo.tarifas_2027 TO rol_app_planillas;
GO

-- Verificación: SELECT, UPDATE e INSERT
EXECUTE AS USER = 'app_planillas';
SELECT permission_name FROM fn_my_permissions('dbo.tarifas_2027', 'OBJECT')
WHERE subentity_name = '';
REVERT;
