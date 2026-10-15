from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from predict_availability import predict_available_beds

app = FastAPI(
    title="MEDORA ML API",
    description="Hospital resource availability prediction",
    version="1.0"
)


class AvailabilityInput(BaseModel):
    total_beds: int = Field(ge=1)
    occupied_beds: int = Field(ge=0)
    admissions_last_24h: int = Field(ge=0)
    discharges_last_24h: int = Field(ge=0)
    demand_level: int = Field(ge=1, le=5)
    hour_of_day: int = Field(ge=0, le=23)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "service": "MEDORA ML"
    }


@app.post("/predict-availability")
def predict(data: AvailabilityInput):
    try:
        beds = predict_available_beds(
            **data.model_dump()
        )

        return {
            "predicted_available_beds_next_6h": beds,
            "note": (
                "Forecast only. Verify current PostgreSQL "
                "availability before making a reservation."
            )
        }

    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc)
        ) from exc