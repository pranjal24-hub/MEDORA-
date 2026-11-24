"""Severity advisory model: vitals + red-flag injuries -> LOW / MODERATE / CRITICAL ka SUJHAV.

ML faisla nahi karta. Final = max(ML sujhav, clinical rule floor). Paramedic hamesha badal sakta hai.
Model: HistGradientBoostingClassifier (khali values ko khud sambhalta hai, isliye adhoora form bhi chalta hai).
"""
import json
import math
import os
import time
import threading
import numpy as np
from app.ml.features import CLASSES, FEATURES, NUMERIC, clean, rule_floor, suggest_needs, vector
from app.ml.make_data import generate

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(HERE, "models", "severity.joblib")
METRICS_PATH = os.path.join(HERE, "models", "severity_metrics.json")
RANK = {"LOW": 0, "MODERATE": 1, "CRITICAL": 2}
# COST[asli][sujhav]: rows/cols = LOW, MODERATE, CRITICAL
COST = np.array([[0.0, 0.5, 2.0],
                 [3.0, 0.0, 1.0],
                 [10.0, 5.0, 0.0]])
_state = {"model": None, "t_crit": 0.25, "t_low": 0.55, "source": "rules", "lock": threading.Lock()}


def _final(p, floor, t_crit, t_low):
    """p = [p_low, p_mod, p_crit]. Upgrade ki taraf jhuko (under-triage zyada khatarnak hai)."""
    if floor or p[2] >= t_crit:
        return 2
    return 0 if p[0] >= t_low else 1


def _baseline(rows):
    """Sirf rules: red criterion -> CRITICAL; chal sakta hai -> LOW; baaki MODERATE (START jaisa)."""
    out = []
    for r in rows:
        c = dict(zip(FEATURES[:-1], r[:-1]))
        floor, _ = rule_floor(c)
        out.append(2 if floor else (0 if c["walking"] == 1.0 else 1))
    return np.array(out)


def _report(y, pred):
    cm = np.zeros((3, 3), dtype=int)
    for t, p in zip(y, pred):
        cm[t][p] += 1
    rec = {CLASSES[i]: round(float(cm[i][i] / max(cm[i].sum(), 1)), 4) for i in range(3)}
    crit = cm[2]
    return {"confusion_matrix(rows=true, cols=suggested, order=LOW,MODERATE,CRITICAL)": cm.tolist(), "recall": rec,
            "critical_missed_as_low": round(float(crit[0] / max(crit.sum(), 1)), 4),
            "critical_missed_as_moderate": round(float(crit[1] / max(crit.sum(), 1)), 4),
            "overtriage_low_to_critical": round(float(cm[0][2] / max(cm[0].sum(), 1)), 4),
            "overtriage_low_to_moderate": round(float(cm[0][1] / max(cm[0].sum(), 1)), 4)}


def train(n: int = 30000, seed: int = 7, save: bool = True) -> dict:
    from sklearn.ensemble import HistGradientBoostingClassifier
    import joblib
    X, y = generate(n, seed)
    idx = np.random.default_rng(seed).permutation(n)
    a, b = int(n * 0.6), int(n * 0.8)
    tr, va, te = idx[:a], idx[a:b], idx[b:]
    w = np.where(y[tr] == 2, 2.0, 1.0)                              # critical galti zyada mehngi
    clf = HistGradientBoostingClassifier(max_depth=4, max_iter=250, learning_rate=0.07, l2_regularization=1.0, random_state=seed)
    clf.fit(X[tr], y[tr], sample_weight=w)

    def floors(rows):
        return [rule_floor(dict(zip(FEATURES[:-1], r[:-1])))[0] is not None for r in rows]

    pv, fv = clf.predict_proba(X[va]), floors(X[va])
    # thresholds ek COST se chune jaate hain: kam gambhir bolna (under-triage) zyada mehnga, zyada gambhir bolna (over-triage) sasta
    cost = COST
    best, t_low, best_cost = 0.25, 0.55, 1e9
    yv = y[va]
    for tc in np.arange(0.05, 0.71, 0.01):
        for tl in np.arange(0.40, 0.91, 0.05):
            pred = np.array([_final(p, f, tc, tl) for p, f in zip(pv, fv)])
            c = float(cost[yv, pred].mean())
            if c < best_cost:
                best, t_low, best_cost = float(round(tc, 2)), float(round(tl, 2)), c

    pt, ft = clf.predict_proba(X[te]), floors(X[te])
    ml_pred = np.array([_final(p, f, best, t_low) for p, f in zip(pt, ft)])
    base_pred = _baseline(X[te])
    metrics = {"trained_at": time.strftime("%Y-%m-%d %H:%M:%S"), "rows": n, "test_rows": int(len(te)),
               "t_crit": best, "t_low": t_low, "cost_matrix(rows=true, cols=suggested)": COST.tolist(),
               "avg_cost_per_patient": {"ml_plus_rules": round(float(COST[y[te], ml_pred].mean()), 3), "rules_only_baseline": round(float(COST[y[te], base_pred].mean()), 3)},
               "ml_plus_rules": _report(y[te], ml_pred), "rules_only_baseline": _report(y[te], base_pred),
               "WARNING": "Ye nateeje SYNTHETIC data par hain (make_data.py ki assumptions). Asli mareezon par pata nahi."}
    if save:
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        joblib.dump({"clf": clf, "t_crit": best, "t_low": t_low}, MODEL_PATH)
        with open(METRICS_PATH, "w", encoding="utf-8") as f:
            json.dump(metrics, f, indent=2, ensure_ascii=False)
    _state.update(model=clf, t_crit=best, t_low=t_low, source="ml")
    return metrics


def warm():
    """Server start par: saved model load karo; na mile ya version alag ho to khud train (kuch second)."""
    with _state["lock"]:
        if _state["model"] is not None:
            return
        try:
            import joblib
            d = joblib.load(MODEL_PATH)
            _state.update(model=d["clf"], t_crit=d["t_crit"], t_low=d["t_low"], source="ml")
        except Exception:
            try:
                train()
            except Exception as e:                                  # sklearn na ho to bhi app chale (sirf rules)
                print("ML severity model unavailable, rules only:", e)


def info() -> dict:
    try:
        with open(METRICS_PATH, encoding="utf-8") as f:
            m = json.load(f)
    except Exception:
        m = None
    return {"source": _state["source"], "metrics": m}


def predict(raw: dict) -> dict:
    c = clean(raw)
    floor, reasons = rule_floor(c)
    known = sum(1 for k in NUMERIC if c[k] == c[k]) + sum(1 for k in ("walking", "obeys") if c[k] == c[k])
    probs, ml_sev = None, None
    if _state["model"] is not None:
        p = _state["model"].predict_proba(np.array([vector(c)]))[0]
        probs = {CLASSES[i]: round(float(p[i]), 3) for i in range(3)}
        ml_sev = CLASSES[_final(p, False, _state["t_crit"], _state["t_low"])]
    if ml_sev is None:                                              # model nahi: sirf rules
        ml_sev = "LOW" if c["walking"] == 1.0 else "MODERATE"
    final = CLASSES[max(RANK[ml_sev], 2 if floor else 0)]
    if final == "CRITICAL" and not reasons:
        reasons = ["overall pattern of the vitals entered looks like critical patients"]
    if final != "CRITICAL" and known == 0:
        reasons = ["no vitals entered yet, so this is only a default"]
    conf = "low" if known < 3 else ("medium" if known < 5 else "high")
    return {"suggested": final, "ml_only": ml_sev, "rule_floor": floor, "probabilities": probs, "confidence": conf,
            "fields_known": known, "reasons": reasons, "needs": suggest_needs(c, final), "source": _state["source"]}
