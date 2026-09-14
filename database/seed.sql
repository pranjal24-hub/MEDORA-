-- MEDORA Sample Data

-- Hospitals
INSERT INTO hospitals (name, address, latitude, longitude, contact_phone)
VALUES
(
    'Kailash Hospital',
    'Main Haridwar Road, Near Jogiwala Chowk, Dehradun, Uttarakhand',
    30.288311,
    78.064203,
    '0135-2663000'
),
(
    'Max Super Speciality Hospital',
    'Mussoorie Diversion Road, Malsi, Dehradun, Uttarakhand',
    30.379095,
    78.074684,
    '0135-3500800'
),
(
    'Velmed Hospital',
    'Turner Road, Clement Town, Dehradun, Uttarakhand',
    30.316000,
    78.030000,
    '01762-512666'
);

-- Sample hospital resources for MEDORA

INSERT INTO resources
    (hospital_id, resource_code, type, status)
VALUES
    -- Kailash Hospital
    (3, 'K-ICU-01', 'icu_bed', 'available'),
    (3, 'K-ICU-02', 'icu_bed', 'available'),
    (3, 'K-VENT-01', 'ventilator', 'available'),

    -- Max Super Speciality Hospital
    (4, 'M-ICU-01', 'icu_bed', 'available'),
    (4, 'M-ICU-02', 'icu_bed', 'available'),
    (4, 'M-VENT-01', 'ventilator', 'available'),

    -- Velmed Hospital
    (5, 'V-ICU-01', 'icu_bed', 'available'),
    (5, 'V-GEN-01', 'general_bed', 'available');


    -- Sample ambulances for MEDORA

INSERT INTO ambulances
    (vehicle_number, latitude, longitude, last_location_at)
VALUES
    ('UK07-AMB-001', 30.3165, 78.0322, now()),
    ('UK07-AMB-002', 30.3300, 78.0600, now()),
    ('UK07-AMB-003', 30.2900, 78.0450, now());