"""WebSocket push helpers: DB se pata karo kise bhejna hai, phir hub.emit."""
from app import hub
from app.db import query


def _ih(iid):
    # incident ke connected hospitals lao
    return [r["hospital_id"] for r in query(
        "SELECT hospital_id FROM incident_hospitals WHERE incident_id=%s AND status<>'STOOD_DOWN'", (iid,))]


def refresh_incident(iid, extra_hospitals=(), also_ambulance=True):
    """Incident se jude hospitals + ambulance ko refresh bhejo."""
    ids = set(_ih(iid)) | set(extra_hospitals)
    keys = hub.hospitals(ids)

    if also_ambulance:
        # incident ki ambulance ko bhi refresh kro
        r = query("SELECT ambulance_id FROM incidents WHERE id=%s", (iid,))
        if r and r[0]["ambulance_id"]:
            keys += hub.ambulance(r[0]["ambulance_id"])

    hub.emit(keys, {"type": "refresh"})


def refresh_hospitals(ids):
    # selected hospitals ko refresh bhejo
    hub.emit(hub.hospitals(ids), {"type": "refresh"})


def refresh_waiting_ambulances():
    """Hospital ke resource/status badle: jin ambulances ke paas options khule hain unhe naye options dikhao."""
    # assessment wale cases ki ambulances lao
    rows = query("SELECT DISTINCT ambulance_id FROM incidents WHERE status='ASSESSED' AND ambulance_id IS NOT NULL")
    hub.emit([k for r in rows for k in hub.ambulance(r["ambulance_id"])], {"type": "refresh"})


def notice(ambulance_id, text, level="info"):
    # ambulance ko notification bhejo
    hub.emit(hub.ambulance(ambulance_id), {"type": "notice", "text": text, "level": level})


def alert(hospital_ids, incident_id):
    """Naya accident: hospital dashboard ko turant alert bhejo."""
    # accident ki location nikal ke hospitals ko alert kro
    r = query("SELECT location_text FROM incidents WHERE id=%s", (incident_id,))
    hub.emit(hub.hospitals(hospital_ids), {"type": "alert", "incident_id": incident_id,
                                           "location": r[0]["location_text"] if r else None})