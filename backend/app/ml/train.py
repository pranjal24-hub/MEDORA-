"""Chalane ke liye (backend folder se):  python -m app.ml.train
Model train karta hai aur confusion matrix / recall chhapta hai (viva mein dikhane ke liye)."""
import json
from app.ml import severity

if __name__ == "__main__":
    m = severity.train()
    print(json.dumps(m, indent=2, ensure_ascii=False))
