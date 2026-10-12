
-- MEDORA: Atomic resource reservation function.
-- Locks the request and resource, validates both,
-- creates a 15-minute reservation, and logs the event.

CREATE OR REPLACE FUNCTION reserve_resource_v2(
    p_request_id BIGINT,
    p_resource_id BIGINT
)
RETURNS BIGINT
LANGUAGE plpgsql
AS $$
DECLARE
    v_required_resource resource_type;
    v_request_status request_status;
    v_resource_type resource_type;
    v_resource_status resource_status;
    v_reservation_id BIGINT;
BEGIN
    -- Lock and validate the emergency request.
    SELECT required_resource, status
    INTO v_required_resource, v_request_status
    FROM emergency_requests
    WHERE id = p_request_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Emergency request % does not exist',
            p_request_id;
    END IF;

    IF v_request_status <> 'open' THEN
        RAISE EXCEPTION 'Request % is not open',
            p_request_id;
    END IF;

    -- Do not create a second reservation record for a request.
    IF EXISTS (
        SELECT 1
        FROM reservations
        WHERE request_id = p_request_id
    ) THEN
        RAISE EXCEPTION
            'Request % already has reservation history',
            p_request_id;
    END IF;

    -- Lock and validate the requested resource.
    SELECT type, status
    INTO v_resource_type, v_resource_status
    FROM resources
    WHERE id = p_resource_id
    FOR UPDATE;

    IF NOT FOUND THEN
        RAISE EXCEPTION 'Resource % does not exist',
            p_resource_id;
    END IF;

    IF v_resource_status <> 'available' THEN
        RAISE EXCEPTION 'Resource % is not available',
            p_resource_id;
    END IF;

    IF v_resource_type <> v_required_resource THEN
        RAISE EXCEPTION
            'Resource type does not match request %',
            p_request_id;
    END IF;

    -- Reserve the resource.
    UPDATE resources
    SET status = 'reserved',
        updated_at = now()
    WHERE id = p_resource_id;

    -- Create the pending reservation with a 15-minute expiry.
    INSERT INTO reservations (
        request_id,
        resource_id,
        status,
        expires_at
    )
    VALUES (
        p_request_id,
        p_resource_id,
        'pending',
        now() + interval '15 minutes'
    )
    RETURNING id INTO v_reservation_id;

    -- Update the emergency request.
    UPDATE emergency_requests
    SET status = 'reserved'
    WHERE id = p_request_id;

    -- Record the reservation event.
    INSERT INTO reservation_events (
        reservation_id,
        event_type,
        details
    )
    VALUES (
        v_reservation_id,
        'reservation_created',
        jsonb_build_object(
            'request_id', p_request_id,
            'resource_id', p_resource_id,
            'expiry_minutes', 15
        )
    );

    RETURN v_reservation_id;
END;
$$;
