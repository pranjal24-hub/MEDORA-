-- MEDORA: poora database schema ek file mein (PostgreSQL). Re-run safe: purane tables drop karke naye banata hai.
-- Order: pehle schema.sql, phir seed.sql.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
DROP TABLE IF EXISTS resource_releases, resource_updates, reservations, incident_hospitals, incidents, hospital_status, users, ambulances,
  hospital_resources, hospital_services, hospitals CASCADE;

CREATE TABLE hospitals (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  name TEXT NOT NULL,
  city TEXT NOT NULL CHECK (city IN ('Dehradun','Haridwar','Rishikesh','Roorkee')),
  ownership TEXT NOT NULL CHECK (ownership IN ('government','private')),
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  address TEXT,
  phone TEXT,
  emergency_phone TEXT,
  ambulance_phone TEXT,
  website TEXT,
  emergency_24x7 BOOLEAN,          -- NULL = not verified
  trauma_centre BOOLEAN,
  ambulance_service BOOLEAN,
  total_beds INT,
  accreditations TEXT,
  data_quality TEXT NOT NULL CHECK (data_quality IN ('website','maps_only','self_registered')),
  notes TEXT
);

CREATE TABLE hospital_services (
  hospital_id INT NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  service TEXT NOT NULL,
  PRIMARY KEY (hospital_id, service)
);

-- Live availability. total = capacity, available = free now, booked = reserved for an incoming ambulance,
-- occupied = in use. Invariant: available + booked + occupied = total. Reserve = available-1, booked+1 (row lock).
CREATE TABLE hospital_resources (
  hospital_id INT NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  resource_type TEXT NOT NULL CHECK (resource_type IN ('ER_BED','ICU_BED','VENTILATOR','OT')),
  total INT NOT NULL CHECK (total >= 0),
  available INT NOT NULL CHECK (available >= 0),
  booked INT NOT NULL DEFAULT 0 CHECK (booked >= 0),
  occupied INT NOT NULL DEFAULT 0 CHECK (occupied >= 0),
  is_simulated BOOLEAN NOT NULL DEFAULT TRUE,
  basis TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (hospital_id, resource_type),
  CHECK (available + booked + occupied = total)
);

CREATE TABLE ambulances (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE NOT NULL,
  plate TEXT,
  base_name TEXT,
  city TEXT NOT NULL,
  base_lat DOUBLE PRECISION NOT NULL,
  base_lon DOUBLE PRECISION NOT NULL,
  lat DOUBLE PRECISION NOT NULL,   -- current position (live)
  lon DOUBLE PRECISION NOT NULL,
  status TEXT NOT NULL DEFAULT 'AVAILABLE' CHECK (status IN ('AVAILABLE','DISPATCHED','TRANSPORTING','OFFLINE')),
  location_updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
  id SERIAL PRIMARY KEY,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('ambulance','hospital')),
  hospital_id INT REFERENCES hospitals(id),
  ambulance_id INT REFERENCES ambulances(id),
  CHECK ((role='hospital' AND hospital_id IS NOT NULL AND ambulance_id IS NULL)
      OR (role='ambulance' AND ambulance_id IS NOT NULL AND hospital_id IS NULL))
);

CREATE INDEX idx_hospitals_city ON hospitals(city);
CREATE INDEX idx_resources_type_avail ON hospital_resources(resource_type, available);

-- ---------- Live status, accidents, reservations ----------
CREATE TABLE hospital_status (
  hospital_id INT PRIMARY KEY REFERENCES hospitals(id) ON DELETE CASCADE,
  load TEXT NOT NULL DEFAULT 'NORMAL' CHECK (load IN ('NORMAL','BUSY','OVERLOADED')),
  diverting BOOLEAN NOT NULL DEFAULT FALSE,      -- TRUE = abhi naye emergency patients nahi le sakte
  note TEXT,
  confirmed_at TIMESTAMPTZ,                      -- hospital ne aakhri baar kab resource sach batayi
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE incidents (
  id SERIAL PRIMARY KEY,
  source TEXT NOT NULL CHECK (source IN ('MEDORA','AMBULANCE_VOICE')),
  location_text TEXT,
  lat DOUBLE PRECISION NOT NULL,
  lon DOUBLE PRECISION NOT NULL,
  ambulance_id INT REFERENCES ambulances(id),
  eta_to_scene_min DOUBLE PRECISION,
  status TEXT NOT NULL DEFAULT 'REPORTED'
    CHECK (status IN ('REPORTED','ASSESSED','RESERVED','ARRIVED','CANCELLED')),
  -- paramedic report
  severity TEXT CHECK (severity IN ('CRITICAL','MODERATE','LOW')),   -- START triage: red / yellow / green
  patients INT NOT NULL DEFAULT 1 CHECK (patients >= 1),
  needs JSONB NOT NULL DEFAULT '{}',          -- {"ICU_BED":1,"VENTILATOR":1,"OT":1,"ER_BED":1}
  specialties TEXT[] NOT NULL DEFAULT '{}',   -- {"Neurosurgery","Orthopaedics"}
  report JSONB NOT NULL DEFAULT '{}',         -- age, mechanism, gcs, spo2, bp, hr, notes
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  assessed_at TIMESTAMPTZ,
  arrived_at TIMESTAMPTZ,
  cancelled_at TIMESTAMPTZ,
  preempt_count INT NOT NULL DEFAULT 0,        -- kitni baar iski booking zyada zaroori patient ko gayi
  reserved_hospital_id INT REFERENCES hospitals(id)
);
CREATE INDEX idx_incidents_amb_closed ON incidents(ambulance_id, id DESC);

-- accident aate hi jin hospitals ko notify kiya
CREATE TABLE incident_hospitals (
  incident_id INT NOT NULL REFERENCES incidents(id) ON DELETE CASCADE,
  hospital_id INT NOT NULL REFERENCES hospitals(id),
  distance_km DOUBLE PRECISION NOT NULL,
  eta_hospital_min DOUBLE PRECISION NOT NULL,   -- scene -> hospital
  status TEXT NOT NULL DEFAULT 'NOTIFIED' CHECK (status IN ('NOTIFIED','RESERVED','STOOD_DOWN')),
  notified_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (incident_id, hospital_id)
);
CREATE INDEX idx_ih_hospital ON incident_hospitals(hospital_id, status);

CREATE TABLE reservations (
  id SERIAL PRIMARY KEY,
  incident_id INT NOT NULL REFERENCES incidents(id),
  hospital_id INT NOT NULL REFERENCES hospitals(id),
  items JSONB NOT NULL,            -- abhi bachi hui reserved/occupied cheezein {"ICU_BED":1,...}
  status TEXT NOT NULL DEFAULT 'BOOKED' CHECK (status IN ('BOOKED','ADMITTED','RELEASED','CANCELLED','PREEMPTED')),
  preempted_by INT REFERENCES incidents(id),   -- kis incident ne ye bed le liya
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  admitted_at TIMESTAMPTZ,
  released_at TIMESTAMPTZ
);
CREATE INDEX idx_res_hospital_booked ON reservations(hospital_id, status);
-- ek incident par ek hi active reservation (double booking roke)
CREATE UNIQUE INDEX uq_active_reservation ON reservations(incident_id) WHERE status IN ('BOOKED','ADMITTED');

-- hospital ke resource confirm / update ka itihaas (login, har 15 min, alert, manual)
CREATE TABLE resource_updates (
  id BIGSERIAL PRIMARY KEY,
  hospital_id INT NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  at TIMESTAMPTZ NOT NULL DEFAULT now(),
  source TEXT NOT NULL CHECK (source IN ('SIGNUP','LOGIN','PERIODIC','ALERT','MANUAL')),
  snapshot JSONB NOT NULL                      -- {"ER_BED":{"total":10,"available":4,"booked":1,"occupied":5}, ...}
);
CREATE INDEX idx_resource_updates_h ON resource_updates(hospital_id, at DESC);

-- ML ke liye data: har baar jab hospital koi bed / ventilator / OT free karta hai, wo kitni der ruka tha.
-- "Bed kab khali hoga" model isi se seekhta hai (bed_forecast.py).
CREATE TABLE resource_releases (
  id BIGSERIAL PRIMARY KEY,
  hospital_id INT NOT NULL REFERENCES hospitals(id) ON DELETE CASCADE,
  resource_type TEXT NOT NULL,
  qty INT NOT NULL,
  severity TEXT,
  occupied_min DOUBLE PRECISION NOT NULL,        -- admit se release tak (minutes)
  released_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_releases_h ON resource_releases(hospital_id, resource_type, id DESC);
