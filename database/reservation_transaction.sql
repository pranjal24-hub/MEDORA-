-- MEDORA: Atomic reservation transaction
-- Reserves an ICU bed safely for an emergency request.

BEGIN;

-- Lock the resource row before making changes.
SELECT id, resource_code, status
FROM resources
WHERE id = 7
  AND type = 'icu_bed'
  AND status = 'available'
FOR UPDATE;

-- Reserve the resource.
UPDATE resources
SET status = 'reserved',
    updated_at = now()
WHERE id = 7
  AND status = 'available';

-- Create the reservation record.
INSERT INTO reservations
    (request_id, resource_id, status, expires_at)
VALUES
    (2, 7, 'pending', now() + interval '15 minutes');

-- Mark the emergency request as reserved.
UPDATE emergency_requests
SET status = 'reserved'
WHERE id = 2
  AND status = 'open';

COMMIT;