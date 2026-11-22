// Regenerated from data/samples.json, each sample's results.json and data/demo/scorecard.json.
const TIEOUT = {
  "currency": "USD",
  "samples": [
    {
      "id": "demo",
      "label": "Two mid-size manufacturers, $522M combined spend",
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
      "assets": {
        "bridge": "assets/bridge.png",
        "workbook": "assets/tieout_workbook.xlsx",
        "deck": "assets/tieout_deck.pptx"
      }
    },
    {
      "id": "bolt_on",
      "label": "Small bolt-on acquisition, $232M combined spend",
      "naive": 6285735.886207168,
      "defensible_recurring": {
        "base": 2791713.1128055356,
        "high": 3683587.911273871,
        "low": 1853225.4495820259
      },
      "lever1": {
        "defensible": 884206.8196951268,
        "steps": [
          2364763.951047487,
          1258975.8685612758,
          926342.9484467385,
          85019.79260365339,
          86285.45031338977,
          47212.5482544105,
          632928.5072850861
        ]
      },
      "assets": {
        "bridge": "assets/samples/bolt_on/bridge.png",
        "workbook": "assets/samples/bolt_on/tieout_workbook.xlsx",
        "deck": "assets/samples/bolt_on/tieout_deck.pptx"
      }
    },
    {
      "id": "messy_data",
      "label": "Merger with messy master data, $263M combined spend",
      "naive": 23561785.49408795,
      "defensible_recurring": {
        "base": 4332049.596699124,
        "high": 5767278.97924567,
        "low": 2800806.407236506
      },
      "lever1": {
        "defensible": 2247477.1147867553,
        "steps": [
          10456100.154108226,
          4318525.559621792,
          3255505.6411717394,
          194206.60490877833,
          660242.8845543563,
          488390.5837972271,
          1941336.9511390743
        ]
      },
      "assets": {
        "bridge": "assets/samples/messy_data/bridge.png",
        "workbook": "assets/samples/messy_data/tieout_workbook.xlsx",
        "deck": "assets/samples/messy_data/tieout_deck.pptx"
      }
    },
    {
      "id": "high_overlap",
      "label": "Two firms with overlapping suppliers, $312M combined spend",
      "naive": 18656205.414814956,
      "defensible_recurring": {
        "base": 5396286.437833104,
        "high": 6956577.48086377,
        "low": 3634562.500780168
      },
      "lever1": {
        "defensible": 3393023.193247397,
        "steps": [
          4821226.833986236,
          3868186.196600454,
          2714348.05583563,
          324988.7745456882,
          665422.41511025,
          774619.4514400214,
          2094390.4940492804
        ]
      },
      "assets": {
        "bridge": "assets/samples/high_overlap/bridge.png",
        "workbook": "assets/samples/high_overlap/tieout_workbook.xlsx",
        "deck": "assets/samples/high_overlap/tieout_deck.pptx"
      }
    }
  ],
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
