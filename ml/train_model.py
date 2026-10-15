from pathlib import Path
import joblib
import pandas as pd
import numpy as np

from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

BASE_DIR = Path(__file__).resolve().parent

data = pd.read_csv(BASE_DIR / "hospital_data.csv")

features = [
    "total_beds",
    "occupied_beds",
    "admissions_last_24h",
    "discharges_last_24h",
    "demand_level",
    "hour_of_day"
]

target = "available_beds_next_6h"

data = data[features + [target]].dropna()

X = data[features]
y = data[target]

X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

model = RandomForestRegressor(
    n_estimators=200,
    random_state=42,
    min_samples_leaf=2,
    n_jobs=-1
)

model.fit(X_train, y_train)

predictions = model.predict(X_test)

mae = mean_absolute_error(y_test, predictions)

rmse = np.sqrt(
    mean_squared_error(y_test, predictions)
)

r2 = r2_score(y_test, predictions)

joblib.dump(
    {
        "model": model,
        "features": features,
        "target": target
    },
    BASE_DIR / "hospital_model.pkl"
)

print("MEDORA model trained successfully!")
print("Training records:", len(X_train))
print("Testing records:", len(X_test))
print("MAE:", round(mae, 2))
print("RMSE:", round(rmse, 2))
print("R2 Score:", round(r2, 3))
print("Model saved as hospital_model.pkl")