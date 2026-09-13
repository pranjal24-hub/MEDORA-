--
-- PostgreSQL database dump
--

\restrict 7lFFkywOycGRHRgMAbL1pIPNJr4MzhD3cheRg80GOLZJFZOm6l027vfGe2eQNDz

-- Dumped from database version 18.6 (Postgres.app)
-- Dumped by pg_dump version 18.6 (Postgres.app)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: request_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.request_status AS ENUM (
    'open',
    'matched',
    'reserved',
    'closed',
    'cancelled'
);


--
-- Name: reservation_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.reservation_status AS ENUM (
    'pending',
    'confirmed',
    'expired',
    'cancelled'
);


--
-- Name: resource_status; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.resource_status AS ENUM (
    'available',
    'locked',
    'reserved',
    'occupied',
    'maintenance'
);


--
-- Name: resource_type; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.resource_type AS ENUM (
    'icu_bed',
    'general_bed',
    'ventilator',
    'oxygen_cylinder',
    'operating_theatre'
);


--
-- Name: severity_level; Type: TYPE; Schema: public; Owner: -
--

CREATE TYPE public.severity_level AS ENUM (
    'low',
    'medium',
    'high',
    'critical'
);


--
-- Name: release_expired_reservations(); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.release_expired_reservations() RETURNS integer
    LANGUAGE plpgsql
    AS $$
DECLARE released_count INTEGER;
BEGIN
  WITH expired AS (
    UPDATE reservations SET status = 'expired'
    WHERE status = 'pending' AND expires_at <= now() RETURNING id, resource_id
  ), restored AS (
    UPDATE resources SET status = 'available', updated_at = now()
    WHERE id IN (SELECT resource_id FROM expired) RETURNING id
  ) SELECT count(*) INTO released_count FROM restored;
  RETURN released_count;
END; $$;


--
-- Name: reserve_resource(bigint, bigint, integer); Type: FUNCTION; Schema: public; Owner: -
--

CREATE FUNCTION public.reserve_resource(p_request_id bigint, p_hospital_id bigint, p_ttl_minutes integer DEFAULT 15) RETURNS bigint
    LANGUAGE plpgsql
    AS $$
DECLARE v_resource_id BIGINT; v_reservation_id BIGINT;
BEGIN
  IF p_ttl_minutes < 1 THEN RAISE EXCEPTION 'Reservation TTL must be at least one minute'; END IF;
  SELECT r.id INTO v_resource_id
  FROM resources r JOIN emergency_requests e ON e.id = p_request_id
  WHERE r.hospital_id = p_hospital_id AND r.type = e.required_resource AND r.status = 'available'
  ORDER BY r.id FOR UPDATE OF r SKIP LOCKED LIMIT 1;
  IF v_resource_id IS NULL THEN RAISE EXCEPTION 'No matching resource is available'; END IF;
  UPDATE resources SET status = 'reserved', updated_at = now() WHERE id = v_resource_id;
  INSERT INTO reservations (request_id, resource_id, expires_at)
  VALUES (p_request_id, v_resource_id, now() + make_interval(mins => p_ttl_minutes)) RETURNING id INTO v_reservation_id;
  UPDATE emergency_requests SET status = 'reserved' WHERE id = p_request_id;
  INSERT INTO reservation_events(reservation_id, event_type, details)
  VALUES (v_reservation_id, 'created', jsonb_build_object('hospital_id', p_hospital_id));
  RETURN v_reservation_id;
END; $$;


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: ambulances; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.ambulances (
    id bigint NOT NULL,
    vehicle_number text NOT NULL,
    latitude numeric(9,6),
    longitude numeric(9,6),
    last_location_at timestamp with time zone,
    is_active boolean DEFAULT true NOT NULL
);


--
-- Name: ambulances_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.ambulances ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.ambulances_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: emergency_requests; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.emergency_requests (
    id bigint NOT NULL,
    patient_id bigint NOT NULL,
    ambulance_id bigint NOT NULL,
    required_resource public.resource_type NOT NULL,
    severity public.severity_level NOT NULL,
    pickup_latitude numeric(9,6) NOT NULL,
    pickup_longitude numeric(9,6) NOT NULL,
    status public.request_status DEFAULT 'open'::public.request_status NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    closed_at timestamp with time zone
);


--
-- Name: emergency_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.emergency_requests ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.emergency_requests_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: hospitals; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.hospitals (
    id bigint NOT NULL,
    name text NOT NULL,
    address text NOT NULL,
    latitude numeric(9,6) NOT NULL,
    longitude numeric(9,6) NOT NULL,
    contact_phone text,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp with time zone DEFAULT now() NOT NULL,
    CONSTRAINT hospitals_latitude_check CHECK (((latitude >= ('-90'::integer)::numeric) AND (latitude <= (90)::numeric))),
    CONSTRAINT hospitals_longitude_check CHECK (((longitude >= ('-180'::integer)::numeric) AND (longitude <= (180)::numeric)))
);


--
-- Name: hospitals_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.hospitals ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.hospitals_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: patients; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.patients (
    id bigint NOT NULL,
    external_reference text,
    display_name text,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: patients_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.patients ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.patients_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: reservation_events; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reservation_events (
    id bigint NOT NULL,
    reservation_id bigint NOT NULL,
    event_type text NOT NULL,
    event_at timestamp with time zone DEFAULT now() NOT NULL,
    details jsonb DEFAULT '{}'::jsonb NOT NULL
);


--
-- Name: reservation_events_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.reservation_events ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.reservation_events_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: reservations; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.reservations (
    id bigint NOT NULL,
    request_id bigint NOT NULL,
    resource_id bigint NOT NULL,
    status public.reservation_status DEFAULT 'pending'::public.reservation_status NOT NULL,
    expires_at timestamp with time zone NOT NULL,
    confirmed_at timestamp with time zone,
    created_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: reservations_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.reservations ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.reservations_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: resources; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.resources (
    id bigint NOT NULL,
    hospital_id bigint NOT NULL,
    resource_code text NOT NULL,
    type public.resource_type NOT NULL,
    status public.resource_status DEFAULT 'available'::public.resource_status NOT NULL,
    updated_at timestamp with time zone DEFAULT now() NOT NULL
);


--
-- Name: resources_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

ALTER TABLE public.resources ALTER COLUMN id ADD GENERATED ALWAYS AS IDENTITY (
    SEQUENCE NAME public.resources_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1
);


--
-- Name: ambulances ambulances_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ambulances
    ADD CONSTRAINT ambulances_pkey PRIMARY KEY (id);


--
-- Name: ambulances ambulances_vehicle_number_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.ambulances
    ADD CONSTRAINT ambulances_vehicle_number_key UNIQUE (vehicle_number);


--
-- Name: emergency_requests emergency_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_requests
    ADD CONSTRAINT emergency_requests_pkey PRIMARY KEY (id);


--
-- Name: hospitals hospitals_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.hospitals
    ADD CONSTRAINT hospitals_pkey PRIMARY KEY (id);


--
-- Name: patients patients_external_reference_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_external_reference_key UNIQUE (external_reference);


--
-- Name: patients patients_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.patients
    ADD CONSTRAINT patients_pkey PRIMARY KEY (id);


--
-- Name: reservation_events reservation_events_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reservation_events
    ADD CONSTRAINT reservation_events_pkey PRIMARY KEY (id);


--
-- Name: reservations reservations_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_pkey PRIMARY KEY (id);


--
-- Name: reservations reservations_request_id_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_request_id_key UNIQUE (request_id);


--
-- Name: resources resources_hospital_id_resource_code_key; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resources
    ADD CONSTRAINT resources_hospital_id_resource_code_key UNIQUE (hospital_id, resource_code);


--
-- Name: resources resources_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resources
    ADD CONSTRAINT resources_pkey PRIMARY KEY (id);


--
-- Name: emergency_priority_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX emergency_priority_idx ON public.emergency_requests USING btree (status, severity, created_at);


--
-- Name: one_live_reservation_per_resource; Type: INDEX; Schema: public; Owner: -
--

CREATE UNIQUE INDEX one_live_reservation_per_resource ON public.reservations USING btree (resource_id) WHERE (status = ANY (ARRAY['pending'::public.reservation_status, 'confirmed'::public.reservation_status]));


--
-- Name: resources_matching_idx; Type: INDEX; Schema: public; Owner: -
--

CREATE INDEX resources_matching_idx ON public.resources USING btree (hospital_id, type, status);


--
-- Name: emergency_requests emergency_requests_ambulance_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_requests
    ADD CONSTRAINT emergency_requests_ambulance_id_fkey FOREIGN KEY (ambulance_id) REFERENCES public.ambulances(id);


--
-- Name: emergency_requests emergency_requests_patient_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.emergency_requests
    ADD CONSTRAINT emergency_requests_patient_id_fkey FOREIGN KEY (patient_id) REFERENCES public.patients(id);


--
-- Name: reservation_events reservation_events_reservation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reservation_events
    ADD CONSTRAINT reservation_events_reservation_id_fkey FOREIGN KEY (reservation_id) REFERENCES public.reservations(id);


--
-- Name: reservations reservations_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.emergency_requests(id);


--
-- Name: reservations reservations_resource_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.reservations
    ADD CONSTRAINT reservations_resource_id_fkey FOREIGN KEY (resource_id) REFERENCES public.resources(id);


--
-- Name: resources resources_hospital_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.resources
    ADD CONSTRAINT resources_hospital_id_fkey FOREIGN KEY (hospital_id) REFERENCES public.hospitals(id);


--
-- PostgreSQL database dump complete
--

\unrestrict 7lFFkywOycGRHRgMAbL1pIPNJr4MzhD3cheRg80GOLZJFZOm6l027vfGe2eQNDz

