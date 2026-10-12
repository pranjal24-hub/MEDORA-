
-- MEDORA: Safely expire overdue pending reservations.
-- Only releases resources that are still marked reserved.
-- All changes and event logging occur in one transaction.

BEGIN;

WITH expired AS (
    UPDATE reservations res
    SET status = 'expired'
    WHERE res.status = 'pending'
      AND res.expires_at <= now()
      AND EXISTS (
          SELECT 1
          FROM resources r
          WHERE r.id = res.resource_id
            AND r.status = 'reserved'
      )
    RETURNING res.id, res.request_id, res.resource_id
),
released AS (
    UPDATE resources r
    SET status = 'available',
        updated_at = now()
    FROM expired e
    WHERE r.id = e.resource_id
      AND r.status = 'reserved'
    RETURNING r.id
),
reopened AS (
    UPDATE emergency_requests er
    SET status = 'open'
    FROM expired e
    WHERE er.id = e.request_id
      AND er.status = 'reserved'
    RETURNING er.id
)
INSERT INTO reservation_events (
    reservation_id,
    event_type,
    details
)
SELECT
    e.id,
    'reservation_expired',
    jsonb_build_object(
        'request_id', e.request_id,
        'resource_id', e.resource_id,
        'resource_released',
            EXISTS (SELECT 1 FROM released r WHERE r.id = e.resource_id),
        'request_reopened',
            EXISTS (SELECT 1 FROM reopened er WHERE er.id = e.request_id)
    )
FROM expired e;

COMMIT;
