-- MEDORA: Hospital and resource matching
-- Finds active hospitals with the required resource
-- and orders them by distance from the emergency location.

SELECT
    h.id AS hospital_id,
    h.name AS hospital_name,
    h.address,
    r.id AS resource_id,
    r.resource_code,
    r.type AS resource_type,
    r.status,

    ROUND(
        (
            6371 * acos(
                LEAST(
                    1,
                    GREATEST(
                        -1,
                        cos(radians(er.pickup_latitude))
                        * cos(radians(h.latitude))
                        * cos(radians(h.longitude) - radians(er.pickup_longitude))
                        + sin(radians(er.pickup_latitude))
                        * sin(radians(h.latitude))
                    )
                )
            )
        )::numeric,
        2
    ) AS distance_km

FROM emergency_requests er
JOIN hospitals h
    ON h.is_active = true
JOIN resources r
    ON r.hospital_id = h.id
    AND r.type = er.required_resource
    AND r.status = 'available'

WHERE er.id = 3

ORDER BY distance_km ASC;