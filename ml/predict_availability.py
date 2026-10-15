from pathlib import Path
import joblib
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "hospital_model.pkl"


def predict_available_beds(
    total_beds,
    occupied_beds,
    admissions_last_24h,
    discharges_last_24h,
    demand_level,
    hour_of_day
):
    if not MODEL_PATH.exists():
        raise FileNotFoundError(
            "Please run train_model.py first."
        )

    if total_beds < 1:
        raise ValueError("Total beds must be positive.")

    if not 0 <= occupied_beds <= total_beds:
        raise ValueError("Invalid occupied bed count.")

    if admissions_last_24h < 0 or discharges_last_24h < 0:
        raise ValueError("Admissions and discharges cannot be negative.")

    if not 1 <= demand_level <= 5:
        raise ValueError("Demand level must be between 1 and 5.")

    if not 0 <= hour_of_day <= 23:
        raise ValueError("Hour must be between 0 and 23.")

    bundle = joblib.load(MODEL_PATH)

    model = bundle["model"]
    features = bundle["features"]

    hospital_data = pd.DataFrame([{
        "total_beds": total_beds,
        "occupied_beds": occupied_beds,
        "admissions_last_24h": admissions_last_24h,
        "discharges_last_24h": discharges_last_24h,
        "demand_level": demand_level,
        "hour_of_day": hour_of_day
    }], columns=features)

    prediction = model.predict(hospital_data)[0]

    return max(
        0,
        min(total_beds, int(round(float(prediction))))
    )


if __name__ == "__main__":
    print("MEDORA - Bed Availability Prediction")

    total = int(input("Enter total beds: "))
    occupied = int(input("Enter occupied beds: "))
    admissions = int(input("Admissions in last 24 hours: "))
    discharges = int(input("Discharges in last 24 hours: "))
    demand = int(input("Demand level (1-5): "))
    hour = int(input("Current hour (0-23): "))

    result = predict_available_beds(
        total,
        occupied,
        admissions,
        discharges,
        demand,
        hour
    )

    print(
        "Predicted available beds in next 6 hours:",
        result
    )

    print(
        "Verify actual availability in PostgreSQL before booking."
    )