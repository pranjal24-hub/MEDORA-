{
  "trained_at": "2026-11-24 09:35:04",
  "rows": 30000,
  "test_rows": 6000,
  "t_crit": 0.34,
  "t_low": 0.75,
  "cost_matrix(rows=true, cols=suggested)": [
    [
      0.0,
      0.5,
      2.0
    ],
    [
      3.0,
      0.0,
      1.0
    ],
    [
      10.0,
      5.0,
      0.0
    ]
  ],
  "avg_cost_per_patient": {
    "ml_plus_rules": 0.334,
    "rules_only_baseline": 0.41
  },
  "ml_plus_rules": {
    "confusion_matrix(rows=true, cols=suggested, order=LOW,MODERATE,CRITICAL)": [
      [
        2070,
        530,
        82
      ],
      [
        190,
        1477,
        388
      ],
      [
        5,
        113,
        1145
      ]
    ],
    "recall": {
      "LOW": 0.7718,
      "MODERATE": 0.7187,
      "CRITICAL": 0.9066
    },
    "critical_missed_as_low": 0.004,
    "critical_missed_as_moderate": 0.0895,
    "overtriage_low_to_critical": 0.0306,
    "overtriage_low_to_moderate": 0.1976
  },
  "rules_only_baseline": {
    "confusion_matrix(rows=true, cols=suggested, order=LOW,MODERATE,CRITICAL)": [
      [
        1703,
        897,
        82
      ],
      [
        268,
        1412,
        375
      ],
      [
        12,
        110,
        1141
      ]
    ],
    "recall": {
      "LOW": 0.635,
      "MODERATE": 0.6871,
      "CRITICAL": 0.9034
    },
    "critical_missed_as_low": 0.0095,
    "critical_missed_as_moderate": 0.0871,
    "overtriage_low_to_critical": 0.0306,
    "overtriage_low_to_moderate": 0.3345
  },
  "WARNING": "Ye nateeje SYNTHETIC data par hain (make_data.py ki assumptions). Asli mareezon par pata nahi."
}