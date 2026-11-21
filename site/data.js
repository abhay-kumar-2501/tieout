// Regenerated from data/demo/results/results.json and data/demo/scorecard.json.
const TIEOUT = {
  "currency": "USD",
  "naive": 32336297.803873297,
  "defensible_recurring": {
    "base": 9608632.765002705,
    "high": 12602946.847917799,
    "low": 6335444.983300518
  },
  "lever1": {
    "defensible": 5426560.769098472,
    "steps": [
      7642579.363043372,
      7933555.8702983335,
      5716046.268452533,
      422381.218977429,
      723467.9742473513,
      477403.24472216703,
      3994303.09503364
    ]
  },
  "scorecard": {
    "held_out_seed": 4,
    "metrics": {
      "false_savings_rate": {
        "tool": 0.003116347205975484,
        "baseline": 0.17720464330760033,
        "target": 0.02,
        "direction": "<="
      },
      "item_precision": {
        "tool": 0.9827973074046372,
        "baseline": 0.3576007326007326,
        "target": 0.97,
        "direction": ">="
      },
      "item_recall": {
        "tool": 0.8342857142857143,
        "baseline": 0.49587301587301585,
        "target": 0.8,
        "direction": ">="
      },
      "planted_savings_recall": {
        "tool": 0.62196529225784,
        "baseline": 0.5418431449628148,
        "target": null,
        "direction": null
      },
      "unit_error_catch_rate": {
        "tool": 0.9857142857142858,
        "baseline": 0.4142857142857143,
        "target": 0.95,
        "direction": ">="
      },
      "vendor_precision": {
        "tool": 0.9959677419354839,
        "baseline": 0.03326033397207775,
        "target": 0.98,
        "direction": ">="
      },
      "vendor_recall": {
        "tool": 0.9629629629629629,
        "baseline": 0.9473684210526315,
        "target": 0.9,
        "direction": ">="
      }
    }
  }
};
