# MEDORA

## An Intelligent Real-Time Emergency Resource Allocation and Coordination System for Better Critical Resource Availability

## 1. Project Overview

MEDORA is an emergency resource allocation and coordination system designed to help emergency teams identify suitable hospitals and available critical medical resources during emergencies.

The system supports emergency request prioritization, hospital resource matching, and safe reservation management. It combines database management concepts with operating system scheduling principles to improve resource coordination and reduce conflicts during simultaneous reservation requests.

## 2. Problem Statement

During medical emergencies, identifying suitable hospitals and available resources such as ICU beds, general beds, ventilators, and operating theatres can be challenging. Delays in locating resources and coordinating reservations may affect emergency response, and several ambulances can head to the same hospital and double-book the last bed.

MEDORA addresses this by organizing hospital resource information, matching emergency requests with suitable available resources, prioritizing requests according to severity, and managing reservations through database transactions and concurrency control.

## 3. Project Objectives

- Develop a centralized database for hospitals, ambulances, emergency incidents, and medical resources.
- Match emergency requests with suitable available hospital resources based on resource type, load, and location.
- Support priority-based scheduling of emergency requests.
- Reduce the risk of race conditions and double booking during concurrent reservations.
- Manage resource reservations, release, and event history.
- Provide live coordination between the ambulance and hospitals.
- Use machine learning as an advisory tool for severity and bed availability.

## 4. Team Members

- **Avika Puri** — Team Lead
- **Pranjal Rawat** — Database Development
- **Dishav** — Integration and Ambulance Interface
- **Aayush Bahuguna** — Interface Development

## 5. Technologies Used

- **Database:** PostgreSQL
- **Backend:** Python, FastAPI, psycopg2, WebSocket
- **Frontend:** HTML, CSS, JavaScript, Leaflet with OpenStreetMap and OSRM routing
- **Machine learning:** scikit-learn, NumPy
- **Development Tools:** VS Code, Git, GitHub

## 6. Phase I — Planning and Design

Phase I focused on identifying the problem, defining the requirements, and establishing the initial system design.

- Identified the challenges involved in emergency medical resource allocation.
- Defined the project objectives and proposed system workflow.
- Identified the main entities and relationships required for the database.
- Designed the initial database structure for hospitals, resources, ambulances, patients, emergency requests, and reservations.
- Planned priority-based emergency request scheduling using operating system concepts.
- Established the initial project structure and version-control workflow.

**Outcome:** A defined project scope, initial system architecture, and database design foundation.

## 7. Phase II — Database Implementation and Testing

Phase II implemented the database design and tested the core resource allocation workflows. These files are kept in the `old/` folder as the original prototype.

- **Database:** implemented the PostgreSQL schema with keys, constraints, indexes and sample data.
- **Resource matching:** SQL queries that find available resources for a request and rank them by approximate distance.
- **Reservation management:** a PostgreSQL function that validates a request and resource before reserving, with transactions and row-level locking, and a partial unique index so one resource cannot have two pending or confirmed reservations.
- **Concurrency control:** `SELECT ... FOR UPDATE`, a manual two-session test showing one transaction waiting for the other, and a test that rejects a resource-type mismatch.
- **Expiry and event logging:** expiring eligible pending reservations, releasing the resource, reopening the request, and recording events in JSONB.

**Outcome:** The core database workflows were implemented and tested with SQL.

## 8. Phase III — Full Application (current)

Phase III integrated the database with a backend, live dashboards and machine learning.

### 8.1 How the system works

1. **Accident report.** Anyone can report from the public page, or the paramedic can speak the location.
2. **Nearest ambulance.** The nearest available ambulance is picked with `FOR UPDATE SKIP LOCKED`, so two reports never take the same ambulance.
3. **Hospitals are alerted in rings** of 20, 40, 60, 80 and 100 km. A ring widens only if nearby hospitals cannot help.
4. **Provisional ranking.** Before the paramedic reports, hospitals get an early estimate from distance, load and resources.
5. **Paramedic report.** Severity (Critical, Moderate, Low), patients, ICU, ventilator, surgery, injury type and optional vitals.
6. **Ranking and booking.** Hospitals are scored (lower is better) from ETA, load, trauma centre, specialties and inbound ambulances. The bed is reserved in one transaction with row locks.
7. **Details after booking.** The paramedic can book with only a severity, then fill in the rest. The booking is updated and the hospital is told.
8. **Live route.** The ambulance location and road route are pushed to hospitals over WebSocket.

### 8.2 Safety and priority rules

- PostgreSQL is the single source of truth. Machine learning is advisory and never books anything.
- A unique partial index allows one active reservation per incident.
- A CHECK constraint keeps `available + booked + occupied = total` for every resource.
- Reservation requests go through a priority dispatcher: a 20 ms batch window, then Critical before Moderate before Low, then earlier incident, then earlier arrival. Aging raises a waiting request one level every few seconds so Low is never starved. This is the operating system scheduling idea from Phase I, now in Python (`dispatch.py`).
- Preemption: a Critical case can take a booked bed from a less urgent case when no free hospital exists or the free one is much worse. An ambulance about to arrive (under 2 minutes) is protected, and one case can be preempted at most twice.
- Hospitals confirm their real counts at login and every 15 minutes. Until then the numbers are marked as estimates.

### 8.3 Machine learning (advisory)

- **Severity suggestion.** `HistGradientBoostingClassifier` trained on synthetic data anchored to START and CDC 2021 field triage. Thresholds come from a cost matrix, and a rule floor means the model can never rate a case below the CDC red criteria.
- **Bed free-up forecast.** Log-normal duration priors, Bayesian shrinkage from real release history, and a Monte Carlo estimate of the next free time.

## 9. Database Design

| Table | Purpose |
|---|---|
| `hospitals`, `hospital_services` | Hospital details, location, trauma centre, specialties. |
| `hospital_resources` | ER beds, ICU beds, ventilators, OT: total, available, booked, occupied. |
| `hospital_status` | Load, diverting flag, last confirmation time. |
| `ambulances` | Ambulance, base, live location, status. |
| `users` | Ambulance and hospital logins (bcrypt through pgcrypto). |
| `incidents` | Accident, severity, patients, needs, report, status. |
| `incident_hospitals` | Which hospitals were alerted, at what distance and ETA. |
| `reservations` | Booked resources per incident (BOOKED, ADMITTED, PREEMPTED, CANCELLED, RELEASED). |
| `resource_updates`, `resource_releases` | History of hospital updates and bed releases (used by the forecast). |

## 10. Project Structure

```text
MEDORA/
├── backend/
│   ├── app/
│   │   ├── main.py        app start, routers, WebSocket, serves the frontend
│   │   ├── incidents.py   report, assessment, details, ranking, reservation, preemption
│   │   ├── dispatch.py    priority dispatcher for reservation requests
│   │   ├── hospital.py    hospital dashboard API, resources, admit and release
│   │   ├── hub.py         WebSocket hub and live ambulance state
│   │   ├── push.py        who to notify, and when
│   │   ├── auth.py        login and JWT
│   │   ├── signup.py      hospital and ambulance signup
│   │   ├── geo.py         distance and ETA helpers
│   │   ├── db.py          PostgreSQL connection pool
│   │   ├── ml_api.py      ML endpoints
│   │   └── ml/            severity model, bed forecast, training
│   ├── requirements.txt
│   ├── simulate.py        load test with many ambulances
│   └── test_db.py         quick database check
├── database/
│   ├── schema.sql         tables, constraints, indexes
│   └── seed.sql           hospitals (Dehradun, Haridwar, Rishikesh, Roorkee), ambulances, demo users
├── frontend/
│   ├── index.html  app.js  style.css   landing page and both dashboards
│   ├── login.html  signup.html  auth.js
│   └── config.js                       backend address
├── old/                   Phase II prototype (SQL tests, C++ scheduling)
└── README.md
```

## 11. Run it on your own computer

Requirements: Python 3.12, PostgreSQL 17, a modern browser.

```powershell
# 1. database
createdb -U postgres medora
psql -U postgres -d medora -f database/schema.sql
psql -U postgres -d medora -f database/seed.sql

# 2. backend
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `backend/.env` (never commit this file):

```text
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/medora
JWT_SECRET=put-a-long-random-string-here
```

```powershell
# 3. start
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>. The backend also serves the frontend, so one command is enough. API documentation is at `/docs`.

### Demo logins (for testing only)

| Role | Username | Password |
|---|---|---|
| Ambulance | `amb01` to `amb10` | `amb01@medora` (same pattern for each) |
| Hospital | `hosp-dehmax`, `hosp-dehsmi`, `hosp-dehhih`, `hosp-dehdmc`, `hosp-dehpan`, `hosp-harprm`, `hosp-harssb`, `hosp-rskaim`, `hosp-rskpan`, `hosp-roosak` | `<username>@medora` |

### Common problems

- **`.\venv\...` not found:** in PowerShell the path must start with `.\`.
- **`DLL load failed ... Application Control policy`:** Windows Smart App Control is blocking a compiled Python file. Check Windows Security, Protection history.
- **Backend runs but nothing updates:** confirm `schema.sql` and `seed.sql` were run on the same database as `DATABASE_URL`.

## 12. Team Work Areas

| Member | Area | Main files |
|---|---|---|
| Avika Puri | Coordination, machine learning, documentation, testing | `backend/app/ml/`, `ml_api.py`, `simulate.py`, `README.md` |
| Pranjal Rawat  | Database | `database/schema.sql`, `seed.sql`, `backend/app/db.py`, `test_db.py` |
| Dishav And Avika Puri| Integration and ambulance interface | `incidents.py`, `dispatch.py`, `hub.py`, `push.py`, `geo.py`, `main.py` |
| Ayush And Dishav | Interface (landing page, ambulance and hospital dashboards) | `frontend/`, `auth.py`, `signup.py`, `hospital.py` |

## 13. Working on this repository

- Do not push directly to `main`. Create a branch (`git checkout -b feature/<name>`), push it, and open a Pull Request.
- Run `git pull origin main` before you start work each day.
- Never commit `.env`, `venv/`, `credentials.csv` or zip files.

## 14. Future Development

- Ambulance accept and decline with patient slots and a timeout.
- Duplicate report merge and per-patient severity.
- Extra ambulances for large incidents.
- Hospital accept and decline with a timeout.
- ETA correction and hospital-accept probability from real data.
- Replace synthetic training data with real hospital and ambulance records.

## 15. Current Project Status

**Phase I:** Problem identification, requirements, initial architecture, and database design foundation.

**Phase II:** PostgreSQL schema, resource matching, reservation management, concurrency-control demonstrations, expiry and event logging.

**Phase III:** Backend, live dashboards, priority dispatcher, preemption, WebSocket updates and advisory machine learning, tested with concurrent ambulances for no double booking.

**Overall Status:** The core system works end to end on a local computer. Remaining items are listed under Future Development.
