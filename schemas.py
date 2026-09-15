from pydantic import BaseModel
from typing import Optional

class HospitalCreate(BaseModel):
    name: str
    latitude: float
    longitude: float
    address: Optional[str] = None
    contact_number: Optional[str] = None

class HospitalResponse(BaseModel):
    id: int
    name: str
    latitude: float
    longitude: float
    address: Optional[str]
    contact_number: Optional[str]

    class Config:
        from_attributes = True


class ResourceCreate(BaseModel):
    hospital_id: int
    resource_type: str
    total_count: int
    available_count: int

class ResourceResponse(BaseModel):
    id: int
    hospital_id: int
    resource_type: str
    total_count: int
    available_count: int

    class Config:
        from_attributes = True


class AmbulanceCreate(BaseModel):
    identifier: str

class AmbulanceResponse(BaseModel):
    id: int
    identifier: str
    status: str

    class Config:
        from_attributes = True

class EmergencyRequestCreate(BaseModel):
    ambulance_id: int
    accident_latitude: float
    accident_longitude: float
    severity: str
    required_resource_type: str

class EmergencyRequestResponse(BaseModel):
    id: int
    ambulance_id: int
    accident_latitude: float
    accident_longitude: float
    severity: str
    required_resource_type: str
    status: str
    matched_hospital_id: Optional[int]
    matched_resource_id: Optional[int]

    class Config:
        from_attributes = True