"""SYNTHETIC training data (asli mareez ka data nahi hai).

Ye generator ek "chhupi hui asli halat" (LOW / MODERATE / CRITICAL) se vitals nikalta hai, jinke average CDC 2021 / START ke
thresholds ke aas-paas rakhe gaye hain. Do cheezein jaan-boojh kar kharab ki gayi hain taaki problem asli jaisi mushkil ho:
  - overlap: kuch CRITICAL mareez dekhne mein MODERATE jaise lagte hain (chhupa hua shock), kuch LOW darr ya dard se MODERATE jaise
  - missing: paramedic har field nahi bharta (har numeric field 22% baar khali)
Isliye is data par jo accuracy aayegi wo SIRF in assumptions ke liye sahi hai, asli duniya ke liye nahi.
"""
import numpy as np
from app.ml.features import FEATURES, FLAGS, NUMERIC

PRIOR = [0.45, 0.35, 0.20]                 # LOW, MODERATE, CRITICAL
LOOKS_MILDER = {2: 0.12, 1: 0.08}          # asli class -> itni baar halat ek darje halki dikhti hai
LOOKS_WORSE = {0: 0.03}                    # LOW kabhi MODERATE jaisa dikhta hai
MISSING_NUM = 0.22
MISSING_CMD = 0.25                         # walking / obeys pata na ho

# class -> (rr, sbp, pulse, spo2, gcs) ke (mean, sd) ; critical ke rr aur gcs mixed hain (neeche code mein)
P = {
    0: dict(rr=(17, 2.5), sbp=(128, 14), pulse=(86, 12), spo2=(97.5, 1.4), gcs=(14.9, 0.4)),
    1: dict(rr=(21, 3.8), sbp=(126, 14), pulse=(96, 13), spo2=(95.5, 2.2), gcs=(13.8, 1.3)),
    2: dict(rr=(30, 7.0), sbp=(86, 22), pulse=(126, 22), spo2=(85.0, 7.0), gcs=(8.0, 3.5)),
}
# class -> flag probabilities: penetrating, pelvis, flail, crush_amput, bleed, high_mech ; walking, obeys
FLAGP = {0: (.0005, .0002, .0, .0005, .002, .12, .85, .997),
         1: (.01, .01, .005, .015, .03, .35, .15, .90),
         2: (.25, .12, .08, .12, .35, .60, .02, .35)}


def generate(n: int, seed: int = 7):
    rng = np.random.default_rng(seed)
    y = rng.choice(3, size=n, p=PRIOR)
    look = y.copy()
    for cls, p in LOOKS_MILDER.items():
        idx = np.where((y == cls) & (rng.random(n) < p))[0]
        look[idx] = cls - 1
    for cls, p in LOOKS_WORSE.items():
        idx = np.where((y == cls) & (rng.random(n) < p))[0]
        look[idx] = cls + 1

    grp = rng.choice(3, size=n, p=[0.12, 0.65, 0.23])             # bachcha, vayask, buzurg
    age = np.where(grp == 0, rng.integers(1, 13, n), np.where(grp == 1, np.clip(rng.normal(35, 14, n), 13, 64), rng.integers(65, 91, n))).astype(float)

    X = {k: np.zeros(n) for k in FEATURES if k != "shock_idx"}
    X["age"] = age
    for cls in range(3):
        m = look == cls
        k = int(m.sum())
        if not k:
            continue
        for name in ("rr", "sbp", "pulse", "spo2", "gcs"):
            mu, sd = P[cls][name]
            X[name][m] = rng.normal(mu, sd, k)
        if cls == 2:                                               # critical: kuch ki saans bahut dheemi (head injury), kuch ki bahut tez
            slow = rng.random(k) < 0.2
            rr = X["rr"][m]; rr[slow] = rng.normal(8, 2, int(slow.sum())); X["rr"][m] = rr
        for j, name in enumerate(("penetrating", "pelvis", "flail", "crush_amput", "bleed", "high_mech", "walking", "obeys")):
            X[name][m] = (rng.random(k) < FLAGP[cls][j]).astype(float)
    child = age < 10
    X["sbp"] = np.where(child, X["sbp"] * 0.72 + age, np.where(age >= 65, X["sbp"] + 8, X["sbp"]))     # bachon ka BP kam
    X["pulse"] = np.where(child, X["pulse"] + 25, X["pulse"])
    X["rr"] = np.where(child, X["rr"] + 6, X["rr"])
    X["rr"] = np.clip(X["rr"], 3, 70); X["sbp"] = np.clip(X["sbp"], 30, 220); X["pulse"] = np.clip(X["pulse"], 25, 220)
    X["spo2"] = np.clip(X["spo2"], 50, 100); X["gcs"] = np.clip(np.round(X["gcs"]), 3, 15)

    for name in ("rr", "sbp", "pulse", "spo2", "gcs"):              # paramedic ne nahi bhara
        X[name][rng.random(n) < MISSING_NUM] = np.nan
    for name in ("walking", "obeys"):
        X[name][rng.random(n) < MISSING_CMD] = np.nan
    sbp, pulse = X["sbp"], X["pulse"]
    with np.errstate(invalid="ignore", divide="ignore"):
        shock = np.where(sbp > 0, pulse / sbp, np.nan)
    M = np.column_stack([X[k] for k in FEATURES if k != "shock_idx"] + [shock])
    return M, y
