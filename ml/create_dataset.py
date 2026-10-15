import pandas as pd
import numpy as np

np.random.seed(42)

n = 500

total_beds = np.random.randint(50, 301, n)

occupied_beds = np.array([
    np.random.randint(0, beds + 1)
    for beds in total_beds
])

admissions = np.random.poisson(8, n)
discharges = np.random.poisson(7, n)

demand_level = np.random.randint(1, 6, n)
hour_of_day = np.random.randint(0, 24, n)

available_beds = total_beds - occupied_beds

noise = np.random.normal(0, 4, n)

future_beds = np.clip(
    np.rint(
        available_beds
        + discharges
        - admissions
        - (demand_level - 1) * 1.5
        + noise
    ),
    0,
    total_beds
).astype(int)

data = pd.DataFrame({
    "total_beds": total_beds,
    "occupied_beds": occupied_beds,
    "admissions_last_24h": admissions,
    "discharges_last_24h": discharges,
    "demand_level": demand_level,
    "hour_of_day": hour_of_day,
    "available_beds_next_6h": future_beds
})

data.to_csv("hospital_data.csv", index=False)

print("Dataset created successfully!")
print(data.head())
print("Total records:", len(data))