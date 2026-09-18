-- MEDORA: Concurrency control test
-- Demonstrates PostgreSQL row-level locking
-- to prevent double booking of the same ICU bed.

BEGIN;

-- Lock the ICU bed before checking/reserving it.
SELECT id, resource_code, status
FROM resources
WHERE id = 9
  AND type = 'icu_bed'
  AND status = 'available'
FOR UPDATE;

-- Reserve the resource only if it is still available.
UPDATE resources
SET status = 'reserved',
    updated_at = now()
WHERE id = 9
  AND status = 'available';

COMMIT;