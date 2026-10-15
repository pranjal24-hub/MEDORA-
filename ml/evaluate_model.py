from pathlib import Path
import joblib
import pandas as pd
import numpy as np

from sklearn.model_selection import train_test_split
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score
)

BASE_DIR = Path(__file__).resolve().parent

data = pd.read_csv(BASE_DIR / "hospital_data.csv")

bundle = joblib.load(
    BASE_DIR / "hospital_model.pkl"
)

features = bundle["features"]
target = bundle["target"]
model = bundle["model"]

data = data[features + [target]].dropna()

X = data[features]
y = data[target]

_, X_test, _, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42
)

predictions = model.predict(X_test)

mae = mean_absolute_error(y_test, predictions)

rmse = np.sqrt(
    mean_squared_error(y_test, predictions)
)

r2 = r2_score(y_test, predictions)

print("MEDORA Model Evaluation")
print("-----------------------")
print("MAE:", round(mae, 2))
print("RMSE:", round(rmse, 2))
print("R2 Score:", round(r2, 3))