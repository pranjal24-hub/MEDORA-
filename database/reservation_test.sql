-- MEDORA: Atomic resource reservation test
-- Tests row-level locking before reserving a resource.

BEGIN;

SELECT id, resource_code, status
FROM resources
WHERE id = 6
  AND status = 'available'
FOR UPDATE;

UPDATE resources
SET status = 'reserved',
    updated_at = now()
WHERE id = 6;

COMMIT;