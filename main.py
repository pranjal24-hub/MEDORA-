from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.database import get_db
from app import models, schemas


from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MEDORA Backend")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # for development only — we'll restrict this later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
@app.get("/")
def read_root():
    return {"message": "MEDORA backend is running"}

@app.get("/db-check")
def db_check(db: Session = Depends(get_db)):
    result = db.execute(text("SELECT 1"))
    return {"database_connected": True, "result": result.scalar()}

@app.post("/hospitals", response_model=schemas.HospitalResponse)
def create_hospital(hospital: schemas.HospitalCreate, db: Session = Depends(get_db)):
    new_hospital = models.Hospital(**hospital.model_dump())
    db.add(new_hospital)
    db.commit()
    db.refresh(new_hospital)
    return new_hospital

@app.get("/hospitals", response_model=list[schemas.HospitalResponse])
def list_hospitals(db: Session = Depends(get_db)):
    return db.query(models.Hospital).all()


@app.post("/resources", response_model=schemas.ResourceResponse)
def create_resource(resource: schemas.ResourceCreate, db: Session = Depends(get_db)):
    new_resource = models.Resource(**resource.model_dump())
    db.add(new_resource)
    db.commit()
    db.refresh(new_resource)
    return new_resource


@app.get("/resources", response_model=list[schemas.ResourceResponse])
def list_resources(db: Session = Depends(get_db)):
    return db.query(models.Resource).all()


@app.post("/ambulances", response_model=schemas.AmbulanceResponse)
def create_ambulance(ambulance: schemas.AmbulanceCreate, db: Session = Depends(get_db)):
    new_ambulance = models.Ambulance(**ambulance.model_dump())
    db.add(new_ambulance)
    db.commit()
    db.refresh(new_ambulance)
    return new_ambulance


@app.get("/ambulances", response_model=list[schemas.AmbulanceResponse])
def list_ambulances(db: Session = Depends(get_db)):
    return db.query(models.Ambulance).all()


from app.utils import calculate_distance_km

@app.post("/emergency-requests", response_model=schemas.EmergencyRequestResponse)
def create_emergency_request(req: schemas.EmergencyRequestCreate, db: Session = Depends(get_db)):
    # Step 1: find resources of the required type that are currently available
    candidates = (
        db.query(models.Resource, models.Hospital)
        .join(models.Hospital, models.Resource.hospital_id == models.Hospital.id)
        .filter(models.Resource.resource_type == req.required_resource_type)
        .filter(models.Resource.available_count > 0)
        .all()
    )

    if not candidates:
        new_request = models.EmergencyRequest(**req.model_dump(), status="NO_MATCH")
        db.add(new_request)
        db.commit()
        db.refresh(new_request)
        return new_request

    # Step 2: pick the closest hospital among candidates
    best_resource, best_hospital, best_distance = None, None, float("inf")

    for resource, hospital in candidates:
        distance = calculate_distance_km(
            req.accident_latitude, req.accident_longitude,
            hospital.latitude, hospital.longitude
        )
        if distance < best_distance:
            best_distance = distance
            best_resource = resource
            best_hospital = hospital

    # Step 3: save the emergency request with the match
    new_request = models.EmergencyRequest(
        **req.model_dump(),
        status="MATCHED",
        matched_hospital_id=best_hospital.id,
        matched_resource_id=best_resource.id
    )
    db.add(new_request)
    db.commit()
    db.refresh(new_request)
    return new_request


from fastapi import HTTPException

@app.post("/emergency-requests/{request_id}/reserve")
def reserve_resource(request_id: int, db: Session = Depends(get_db)):
    # Get the emergency request
    emergency = db.query(models.EmergencyRequest).filter(
        models.EmergencyRequest.id == request_id
    ).first()

    if not emergency:
        raise HTTPException(status_code=404, detail="Emergency request not found")

    if emergency.status != "MATCHED":
        raise HTTPException(status_code=400, detail=f"Cannot reserve — current status is {emergency.status}")

    # Lock the matched resource row — this is the critical concurrency step
    resource = (
        db.query(models.Resource)
        .filter(models.Resource.id == emergency.matched_resource_id)
        .with_for_update()
        .first()
    )

    if not resource:
        raise HTTPException(status_code=404, detail="Matched resource no longer exists")

    # Re-check availability NOW, while holding the lock — the earlier match could be stale
    if resource.available_count <= 0:
        emergency.status = "FAILED_NO_AVAILABILITY"
        db.commit()
        raise HTTPException(status_code=409, detail="Resource no longer available — reservation failed")

    # Safe to reserve
    resource.available_count -= 1
    emergency.status = "RESERVED"

    db.commit()
    db.refresh(emergency)
    db.refresh(resource)

    return {
        "emergency_request_id": emergency.id,
        "status": emergency.status,
        "resource_id": resource.id,
        "remaining_available": resource.available_count
    }

from app.priority import get_priority_order

@app.get("/emergency-requests/priority-order")
def priority_order(db: Session = Depends(get_db)):
    pending = db.query(models.EmergencyRequest).filter(
        models.EmergencyRequest.status == "MATCHED"
    ).all()

    if not pending:
        return {"ordered_emergency_ids": []}

    emergencies_data = [{"id": e.id, "severity": e.severity} for e in pending]
    ordered_ids = get_priority_order(emergencies_data)

    return {"ordered_emergency_ids": ordered_ids}