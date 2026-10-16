# MEDORA

## An Intelligent Real-Time Emergency Resource Allocation and Coordination System for Better Critical Resource Availability

## 1. Project Overview

MEDORA is an emergency resource allocation and coordination system designed to help emergency teams identify suitable hospitals and available critical medical resources during emergencies.

The system aims to support emergency request prioritization, hospital resource matching, and safe reservation management. It combines database management concepts with operating system scheduling principles to improve resource coordination and reduce conflicts during simultaneous reservation requests.

## 2. Problem Statement

During medical emergencies, identifying suitable hospitals and available resources such as ICU beds, general beds, ventilators, and oxygen cylinders can be challenging. Delays in locating resources and coordinating reservations may affect emergency response.

MEDORA aims to address this problem by organizing hospital resource information, matching emergency requests with suitable available resources, prioritizing requests according to severity, and managing reservations through database transactions and concurrency control.

## 3. Project Objectives

- Develop a centralized database for hospitals, ambulances, patients, emergency requests, and medical resources.
- Match emergency requests with suitable available hospital resources based on resource type and location.
- Support priority-based scheduling of emergency requests.
- Reduce the risk of race conditions and double booking during concurrent reservations.
- Manage resource reservations, expiry, and event history.
- Explore machine-learning-based resource availability prediction in future development.

## 4. Team Members

- **Avika Puri** — Team Lead
- **Pranjal Rawat** — Database Development
- **Aayush Bahuguna** — Integration and Ambulance Interface
- **Dishav** — Interface Development

## 5. Technologies Used

- **Database:** PostgreSQL
- **Programming Languages:** C++, Python
- **Frontend:** HTML, CSS, JavaScript
- **Development Tools:** VS Code, Git, GitHub

## 6. Phase I — Planning and Design

Phase I focused on identifying the problem, defining the requirements, and establishing the initial system design.

### Work Completed

- Identified the challenges involved in emergency medical resource allocation.
- Defined the project objectives and proposed system workflow.
- Identified the main entities and relationships required for the database.
- Designed the initial database structure for hospitals, resources, ambulances, patients, emergency requests, and reservations.
- Planned priority-based emergency request scheduling using operating system concepts.
- Established the initial project structure and version-control workflow.

### Phase I Outcome

A defined project scope, initial system architecture, and database design foundation were established for further implementation.

## 7. Phase II — Implementation and Testing

Phase II focused on implementing the database design and developing and testing core resource allocation workflows.

### 7.1 Database Implementation

- Implemented the PostgreSQL database schema.
- Created tables for hospitals, resources, ambulances, patients, emergency requests, reservations, and reservation events.
- Defined primary keys, foreign keys, constraints, indexes, and appropriate data types.
- Added sample hospital, resource, ambulance, and patient records for testing.

### 7.2 Hospital Resource Matching

- Developed SQL queries to identify available resources that match an emergency request.
- Used hospital and emergency-location coordinates to calculate approximate distances.
- Ranked matching resources by distance to help identify nearby suitable options.

### 7.3 Reservation Management

- Implemented a PostgreSQL function for validating emergency requests and resources before creating reservations.
- Updated resource and emergency-request statuses as part of the reservation workflow.
- Used transactions and row-level locking to help manage concurrent access to resources.
- Added a partial unique index to prevent multiple pending or confirmed reservations for the same resource.

### 7.4 Concurrency Control and Race-Condition Prevention

- Implemented database-level safeguards to reduce conflicts when multiple requests target the same resource.
- Used row-level locking with `SELECT ... FOR UPDATE` in reservation-related workflows.
- Performed a manual two-session test to observe how one transaction waits for another transaction holding a resource lock.
- Tested rejection of a resource-type mismatch to ensure that an incompatible resource was not reserved for a request.

### 7.5 Reservation Expiry and Event Logging

- Implemented and tested a workflow for expiring eligible pending reservations.
- Released the associated resource and reopened the corresponding emergency request in the tested expiry workflow.
- Recorded reservation events, timestamps, and relevant details using PostgreSQL's JSONB data type.

### 7.6 Testing and Version Control

- Tested resource matching, reservation creation, resource-type validation, and reservation expiry using SQL queries.
- Tested row-locking behavior using separate database sessions.
- Maintained database implementation files in Git and GitHub.

### Phase II Outcome

The database schema and several core database workflows have been implemented and tested. Full integration across the backend, user interface, and all emergency coordination workflows remains part of ongoing development.

## 8. Database Design

The PostgreSQL database contains the following main tables:

| Table | Purpose |
|---|---|
| `hospitals` | Stores hospital information and location coordinates. |
| `resources` | Stores individual medical resources and their types and statuses. |
| `ambulances` | Stores ambulance details and location information. |
| `patients` | Stores patient reference information. |
| `emergency_requests` | Stores emergency details, severity, required resources, and request status. |
| `reservations` | Tracks resource reservations, status, and expiry. |
| `reservation_events` | Maintains a history of reservation-related events. |

## 9. Key Features

- Hospital and medical resource management.
- Emergency request tracking and severity classification.
- Resource matching based on type, availability, and approximate distance.
- Transaction-based resource reservation.
- Row-level locking and database constraints to reduce race conditions and double booking.
- Reservation expiry handling and event logging.
- Initial C++ components for emergency request and priority-scheduling logic.

## 10. Project Structure

```text
MEDORA/
├── database/
│   ├── schema.sql
│   ├── seed.sql
│   ├── resource_matching.sql
│   ├── reserve_resource.sql
│   ├── reservation_test.sql
│   ├── reservation_transaction.sql
│   ├── concurrency_test.sql
│   ├── reservation_expiry.sql
│   └── scheduling/
│       ├── EmergencyRequest.cpp
│       ├── EmergencyRequest.h
│       ├── PriorityScheduling.cpp
│       └── PriorityScheduling.h
├── README.md
└── ...
```

*Note: This structure represents the expected layout. Keep only files and folders that actually exist in the repository.*

## 11. Future Development

- Integrate the database with the backend and user interface.
- Connect emergency request submission with the complete resource-matching and reservation workflow.
- Integrate and further validate priority-based scheduling.
- Expand concurrent reservation testing and transaction failure handling.
- Develop end-to-end emergency coordination workflows.
- Explore machine-learning-based resource availability prediction using hospital occupancy and resource usage data.
- Explore route optimization to support ambulance coordination.

## 12. Current Project Status

**Phase I:** Problem identification, requirements, initial architecture, and database design foundation.

**Phase II:** PostgreSQL schema implementation, resource matching, reservation management, concurrency-control demonstrations, reservation expiry, event logging, and database testing.

**Overall Status:** Core database components have been implemented and tested. Full application integration and further validation are ongoing.