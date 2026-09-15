from sqlalchemy import Column, Integer, String, Float, Text, TIMESTAMP, ForeignKey
from sqlalchemy.sql import func
from app.database import Base

class Hospital(Base):
    __tablename__ = "hospitals"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    address = Column(Text)
    contact_number = Column(String(20))
    created_at = Column(TIMESTAMP, server_default=func.now())


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    hospital_id = Column(Integer, ForeignKey("hospitals.id"), nullable=False)
    resource_type = Column(String(50), nullable=False)
    total_count = Column(Integer, nullable=False)
    available_count = Column(Integer, nullable=False)
    updated_at = Column(TIMESTAMP, server_default=func.now())


class Ambulance(Base):
    __tablename__ = "ambulances"

    id = Column(Integer, primary_key=True, index=True)
    identifier = Column(String(50), unique=True, nullable=False)
    status = Column(String(20), default="AVAILABLE")
    created_at = Column(TIMESTAMP, server_default=func.now())


class EmergencyRequest(Base):
    __tablename__ = "emergency_requests"

    id = Column(Integer, primary_key=True, index=True)
    ambulance_id = Column(Integer, ForeignKey("ambulances.id"))
    accident_latitude = Column(Float, nullable=False)
    accident_longitude = Column(Float, nullable=False)
    severity = Column(String(20), nullable=False)
    required_resource_type = Column(String(50), nullable=False)
    status = Column(String(30), default="PENDING")
    matched_hospital_id = Column(Integer, ForeignKey("hospitals.id"))
    matched_resource_id = Column(Integer, ForeignKey("resources.id"))
    created_at = Column(TIMESTAMP, server_default=func.now())