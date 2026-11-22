// Regenerated from data/samples.json, each sample's results (results.json and the result tables) and data/demo/scorecard.json.
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
      },
      "story": {
        "overlap": {
          "items": {
            "a": 5500,
            "b": 3500,
            "both": 1337
          },
          "vendors": {
            "a": 1468,
            "b": 966,
            "both": 401
          },
          "spend": {
            "a": 340736403.0956,
            "b": 181178523.9922
          }
        },
        "examples": {
          "match": {
            "kind": "match",
            "same_supplier": true,
            "a": {
              "company": "acquirer",
              "vendor": "Capastbro Autom Group NV",
              "description": "RELAY PLUG-IN 3PDT 24VAC 5A 14 PIN",
              "uom": "EA",
              "price": 20.9644,
              "price_base": 20.9644,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 8,
              "vendor_tokens": [
                [
                  "Capastbro",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "Autom",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "Group",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "NV",
                  -1
                ]
              ],
              "item_tokens": [
                [
                  "RELAY",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "PLUG-IN",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "3PDT",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "24VAC",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "5A",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "14",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "PIN",
                  7
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "CAPASTBRO AUTOMATION GROUP NV",
              "description": "RLY,PLUG-IN,3PDT,24VAC,5A,14 PIN",
              "uom": "PC",
              "price": 15.2748,
              "price_base": 15.2748,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 7,
              "vendor_tokens": [
                [
                  "CAPASTBRO",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "AUTOMATION",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "GROUP",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "NV",
                  -1
                ]
              ],
              "item_tokens": [
                [
                  "RLY",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "PLUG-IN",
                  2
                ],
                [
                  ",",
                  0
                ],
                [
                  "3PDT",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "24VAC",
                  4
                ],
                [
                  ",",
                  0
                ],
                [
                  "5A",
                  5
                ],
                [
                  ",",
                  0
                ],
                [
                  "14",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "PIN",
                  7
                ]
              ]
            },
            "notes": {
              "vendor": [
                {
                  "kind": "abbr",
                  "a": "Autom",
                  "b": "AUTOMATION"
                }
              ],
              "item": [
                {
                  "kind": "abbr",
                  "a": "RELAY",
                  "b": "RLY"
                }
              ]
            },
            "stage": "I3",
            "tier": "B",
            "similarity": 1.0,
            "evidence": "I3 description similarity 1.00 (character n-gram TF-IDF). Agreeing attributes: current 5A, poles 3, voltage 24V, vtype AC. Tier B: similarity 1.00 is at or above 0.78 and 3 critical attributes agree with no conflict."
          },
          "lookalike": {
            "kind": "lookalike",
            "same_supplier": true,
            "a": {
              "company": "acquirer",
              "vendor": "Alekale Maintenance Supply, LLC.",
              "description": "CORDLESS RECIP SAW 36V 1/2 SQ KIT 2 BATT",
              "uom": "EA",
              "price": 144.9561,
              "price_base": 144.9561,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 3,
              "vendor_tokens": [
                [
                  "Alekale",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "Maintenance",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "Supply",
                  3
                ],
                [
                  ", ",
                  0
                ],
                [
                  "LLC.",
                  -1
                ]
              ],
              "item_tokens": [
                [
                  "CORDLESS",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "RECIP",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "SAW",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "36V",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "1/2",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "SQ",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "KIT",
                  7
                ],
                [
                  " ",
                  0
                ],
                [
                  "2",
                  -3
                ],
                [
                  " ",
                  0
                ],
                [
                  "BATT",
                  8
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "ALEKALE MAINTENANCE SUPPLY LLC",
              "description": "CORDLESS,36V,RECIP SAW,1/2 SQ,KIT 1 BATT",
              "uom": "PC",
              "price": 221.8627,
              "price_base": 221.8627,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 2,
              "vendor_tokens": [
                [
                  "ALEKALE",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "MAINTENANCE",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "SUPPLY",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "LLC",
                  -1
                ]
              ],
              "item_tokens": [
                [
                  "CORDLESS",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "36V",
                  4
                ],
                [
                  ",",
                  0
                ],
                [
                  "RECIP",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "SAW",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "1/2",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "SQ",
                  6
                ],
                [
                  ",",
                  0
                ],
                [
                  "KIT",
                  7
                ],
                [
                  " ",
                  0
                ],
                [
                  "1",
                  -3
                ],
                [
                  " ",
                  0
                ],
                [
                  "BATT",
                  8
                ]
              ]
            },
            "notes": {
              "vendor": [],
              "item": []
            },
            "stage": "I3",
            "tier": "C",
            "similarity": 0.99,
            "evidence": "I3 description similarity 0.99 (character n-gram TF-IDF). Agreeing attributes: 36V. Other numbers in the descriptions differ (2 vs 1). Tier C, review only: other numbers in the descriptions differ. Text similarity alone never matches."
          },
          "trap": {
            "kind": "trap",
            "same_supplier": false,
            "a": {
              "company": "acquirer",
              "vendor": "Femdalen & Lebelu Incorporated",
              "description": "PACKING TAPE 3IN 60YD 2.0MIL TAN",
              "uom": "BX",
              "price": 75.8124,
              "price_base": null,
              "base_unit": null,
              "conv": "unconverted",
              "lines": 46,
              "vendor_tokens": [
                [
                  "Femdalen",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "&",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Lebelu",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Incorporated",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "PACKING",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "TAPE",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "3IN",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "60YD",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "2.0MIL",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "TAN",
                  6
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "NAHER PALLET INCORPORATED",
              "description": "TAPE,PACKING,3IN,60YD,2.0MIL,TAN",
              "uom": "EA",
              "price": 2.0836,
              "price_base": 2.0836,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 27,
              "vendor_tokens": [
                [
                  "NAHER",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "PALLET",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "INCORPORATED",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "TAPE",
                  2
                ],
                [
                  ",",
                  0
                ],
                [
                  "PACKING",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "3IN",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "60YD",
                  4
                ],
                [
                  ",",
                  0
                ],
                [
                  "2.0MIL",
                  5
                ],
                [
                  ",",
                  0
                ],
                [
                  "TAN",
                  6
                ]
              ]
            },
            "notes": {
              "vendor": [],
              "item": []
            },
            "removed": 1827091.79,
            "ratio": 36.4
          }
        }
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
      },
      "story": {
        "overlap": {
          "items": {
            "a": 3300,
            "b": 540,
            "both": 190
          },
          "vendors": {
            "a": 882,
            "b": 212,
            "both": 172
          },
          "spend": {
            "a": 204635544.5594,
            "b": 27492691.7213
          }
        },
        "examples": {
          "match": {
            "kind": "match",
            "same_supplier": true,
            "a": {
              "company": "acquirer",
              "vendor": "Kihalir Indl Co",
              "description": "GATE VALVE 6IN 600# FS A105 FLG RF",
              "uom": "EA",
              "price": 566.8912,
              "price_base": 566.8912,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 7,
              "vendor_tokens": [
                [
                  "Kihalir",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "Indl",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "Co",
                  -1
                ]
              ],
              "item_tokens": [
                [
                  "GATE",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "VALVE",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "6IN",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "600#",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "FS",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "A105",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "FLG",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "RF",
                  7
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "KIHALIR INDUSTRIAL CO",
              "description": "VLV,GATE,6\",CL600,FS A105,FLG RF",
              "uom": "EA",
              "price": 649.8336,
              "price_base": 649.8336,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 3,
              "vendor_tokens": [
                [
                  "KIHALIR",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "INDUSTRIAL",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "CO",
                  -1
                ]
              ],
              "item_tokens": [
                [
                  "VLV",
                  2
                ],
                [
                  ",",
                  0
                ],
                [
                  "GATE",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "6\"",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "CL600",
                  0
                ],
                [
                  ",",
                  0
                ],
                [
                  "FS",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "A105",
                  5
                ],
                [
                  ",",
                  0
                ],
                [
                  "FLG",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "RF",
                  7
                ]
              ]
            },
            "notes": {
              "vendor": [
                {
                  "kind": "abbr",
                  "a": "Indl",
                  "b": "INDUSTRIAL"
                }
              ],
              "item": [
                {
                  "kind": "abbr",
                  "a": "VALVE",
                  "b": "VLV"
                },
                {
                  "kind": "format",
                  "a": "6IN",
                  "b": "6\""
                }
              ]
            },
            "stage": "I3",
            "tier": "B",
            "similarity": 0.8,
            "evidence": "I3 description similarity 0.80 (character n-gram TF-IDF). Agreeing attributes: class CL600, end FLANGED, kind GATE VALVE, material CARBON STEEL, size 6IN. Tier B: similarity 0.80 is at or above 0.78 and 4 critical attributes agree with no conflict."
          },
          "lookalike": {
            "kind": "lookalike",
            "same_supplier": false,
            "a": {
              "company": "acquirer",
              "vendor": "Veneradre & Ganen Co",
              "description": "GRS CALCIUM SULFONATE NLGI 2 FOOD GRADE H1",
              "uom": "GAL",
              "price": 39.2679,
              "price_base": 10.3735,
              "base_unit": "litre",
              "conv": "confirmed",
              "lines": 3,
              "vendor_tokens": [
                [
                  "Veneradre",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "&",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Ganen",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Co",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "GRS",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "CALCIUM",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "SULFONATE",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "NLGI",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "2",
                  -3
                ],
                [
                  " ",
                  0
                ],
                [
                  "FOOD",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "GRADE",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "H1",
                  0
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "BRELMARA LUBRICANTS CO",
              "description": "GRS,CALCIUM SULFONATE,NLGI 1,FOOD GRADE",
              "uom": "LT",
              "price": 10.9119,
              "price_base": 10.9119,
              "base_unit": "litre",
              "conv": "confirmed",
              "lines": 6,
              "vendor_tokens": [
                [
                  "BRELMARA",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "LUBRICANTS",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "CO",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "GRS",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "CALCIUM",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "SULFONATE",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "NLGI",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "1",
                  -3
                ],
                [
                  ",",
                  0
                ],
                [
                  "FOOD",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "GRADE",
                  6
                ]
              ]
            },
            "notes": {
              "vendor": [],
              "item": []
            },
            "stage": "I3",
            "tier": "C",
            "similarity": 0.97,
            "evidence": "I3 description similarity 0.97 (character n-gram TF-IDF). Agreeing attributes: none. Other numbers in the descriptions differ (2 vs 1). Tier C, review only: other numbers in the descriptions differ. Text similarity alone never matches."
          },
          "trap": {
            "kind": "trap",
            "same_supplier": false,
            "a": {
              "company": "acquirer",
              "vendor": "Kalavma Toools Ltd",
              "description": "TAP M4X0.7 SPIRAL FLUTE HSS TIN",
              "uom": "EA",
              "price": 15.7885,
              "price_base": 15.7885,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 21,
              "vendor_tokens": [
                [
                  "Kalavma",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Toools",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Ltd",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "TAP",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "M4X0.7",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "SPIRAL",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "FLUTE",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "HSS",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "TIN",
                  6
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "KURNSOND TOOLS INC",
              "description": "TAP,M4X0.7,SPIRAL FLUTE,HSS TIN",
              "uom": "CS",
              "price": 193.9175,
              "price_base": null,
              "base_unit": null,
              "conv": "unconverted",
              "lines": 24,
              "vendor_tokens": [
                [
                  "KURNSOND",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "TOOLS",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "INC",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "TAP",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "M4X0.7",
                  2
                ],
                [
                  ",",
                  0
                ],
                [
                  "SPIRAL",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "FLUTE",
                  4
                ],
                [
                  ",",
                  0
                ],
                [
                  "HSS",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "TIN",
                  6
                ]
              ]
            },
            "notes": {
              "vendor": [],
              "item": []
            },
            "removed": 673039.42,
            "ratio": 12.3
          }
        }
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
      },
      "story": {
        "overlap": {
          "items": {
            "a": 2750,
            "b": 1750,
            "both": 673
          },
          "vendors": {
            "a": 740,
            "b": 478,
            "both": 187
          },
          "spend": {
            "a": 171196793.569,
            "b": 91410195.8086
          }
        },
        "examples": {
          "match": {
            "kind": "match",
            "same_supplier": true,
            "a": {
              "company": "acquirer",
              "vendor": "Dosurn Flid Systems Company",
              "description": "BFLY VALVE 6IN 200# DI VITON WAFER",
              "uom": "EA",
              "price": 310.5886,
              "price_base": 310.5886,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 3,
              "vendor_tokens": [
                [
                  "Dosurn",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "Flid",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "Systems",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "Company",
                  -1
                ]
              ],
              "item_tokens": [
                [
                  "BFLY",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "VALVE",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "6IN",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "200#",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "DI",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "VITON",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "WAFER",
                  6
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "DOSURN FLUID SYSTEMS COMPANY",
              "description": "VLV,BUTTERFLY,CL200,6\",DI VIT,WAFER",
              "uom": "EA",
              "price": 334.2575,
              "price_base": 334.2575,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 4,
              "vendor_tokens": [
                [
                  "DOSURN",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "FLUID",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "SYSTEMS",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "COMPANY",
                  -1
                ]
              ],
              "item_tokens": [
                [
                  "VLV",
                  2
                ],
                [
                  ",",
                  0
                ],
                [
                  "BUTTERFLY",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "CL200",
                  0
                ],
                [
                  ",",
                  0
                ],
                [
                  "6\"",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "DI",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "VIT",
                  5
                ],
                [
                  ",",
                  0
                ],
                [
                  "WAFER",
                  6
                ]
              ]
            },
            "notes": {
              "vendor": [
                {
                  "kind": "slip",
                  "a": "Flid",
                  "b": "FLUID"
                }
              ],
              "item": [
                {
                  "kind": "abbr",
                  "a": "BFLY",
                  "b": "BUTTERFLY"
                },
                {
                  "kind": "abbr",
                  "a": "VALVE",
                  "b": "VLV"
                },
                {
                  "kind": "format",
                  "a": "6IN",
                  "b": "6\""
                },
                {
                  "kind": "abbr",
                  "a": "VITON",
                  "b": "VIT"
                }
              ]
            },
            "stage": "I3",
            "tier": "B",
            "similarity": 0.86,
            "evidence": "I3 description similarity 0.86 (character n-gram TF-IDF). Agreeing attributes: class CL200, end WAFER, kind BUTTERFLY VALVE, size 6IN. Tier B: similarity 0.86 is at or above 0.78 and 3 critical attributes agree with no conflict."
          },
          "lookalike": {
            "kind": "lookalike",
            "same_supplier": false,
            "a": {
              "company": "acquirer",
              "vendor": "Serovhe Industrial Corporation",
              "description": "SAFETY GLASSES SHADE 3 HARD COAT Z87+ U6 CS/12",
              "uom": "CS",
              "price": 47.7649,
              "price_base": 3.9804,
              "base_unit": "each",
              "conv": "parsed",
              "lines": 2,
              "vendor_tokens": [
                [
                  "Serovhe",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Industrial",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Corporation",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "SAFETY",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "GLASSES",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "SHADE",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "3",
                  -3
                ],
                [
                  " ",
                  0
                ],
                [
                  "HARD",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "COAT",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "Z87+",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "U6",
                  7
                ],
                [
                  " ",
                  0
                ],
                [
                  "CS/12",
                  -2
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "LANDCORA DIST CO",
              "description": "GLSS,SFTY,HARD COAT,SHADE 5,Z87+ U6",
              "uom": "BX",
              "price": 39.1382,
              "price_base": null,
              "base_unit": null,
              "conv": "unconverted",
              "lines": 1,
              "vendor_tokens": [
                [
                  "LANDCORA",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "DIST",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "CO",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "GLSS",
                  2
                ],
                [
                  ",",
                  0
                ],
                [
                  "SFTY",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "HARD",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "COAT",
                  5
                ],
                [
                  ",",
                  0
                ],
                [
                  "SHADE",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "5",
                  -3
                ],
                [
                  ",",
                  0
                ],
                [
                  "Z87+",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "U6",
                  7
                ]
              ]
            },
            "notes": {
              "vendor": [],
              "item": [
                {
                  "kind": "abbr",
                  "a": "SAFETY",
                  "b": "SFTY"
                },
                {
                  "kind": "abbr",
                  "a": "GLASSES",
                  "b": "GLSS"
                }
              ]
            },
            "stage": "I3",
            "tier": "C",
            "similarity": 0.98,
            "evidence": "I3 description similarity 0.98 (character n-gram TF-IDF). Agreeing attributes: lens SHADE, type GLASSES. Other numbers in the descriptions differ (3 vs 5). Tier C, review only: other numbers in the descriptions differ. Text similarity alone never matches."
          },
          "trap": {
            "kind": "trap",
            "same_supplier": false,
            "a": {
              "company": "acquirer",
              "vendor": "Serovhe Industrial Corporation",
              "description": "DRL BIT JOBBER 12MM HSS TIN 140 DEG",
              "uom": "EA",
              "price": 7.0219,
              "price_base": 7.0219,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 34,
              "vendor_tokens": [
                [
                  "Serovhe",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Industrial",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Corporation",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "DRL",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "BIT",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "JOBBER",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "12MM",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "HSS",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "TIN",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "140",
                  7
                ],
                [
                  " ",
                  0
                ],
                [
                  "DEG",
                  8
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "MOXFATON INDUSTRIAL SUPPLY COR",
              "description": "BIT,DRL JOBBER,12MM,HSS TIN,140 DEG",
              "uom": "BX",
              "price": 84.3766,
              "price_base": null,
              "base_unit": null,
              "conv": "unconverted",
              "lines": 35,
              "vendor_tokens": [
                [
                  "MOXFATON",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "INDUSTRIAL",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "SUPPLY",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "COR",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "BIT",
                  2
                ],
                [
                  ",",
                  0
                ],
                [
                  "DRL",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "JOBBER",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "12MM",
                  4
                ],
                [
                  ",",
                  0
                ],
                [
                  "HSS",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "TIN",
                  6
                ],
                [
                  ",",
                  0
                ],
                [
                  "140",
                  7
                ],
                [
                  " ",
                  0
                ],
                [
                  "DEG",
                  8
                ]
              ]
            },
            "notes": {
              "vendor": [],
              "item": []
            },
            "removed": 1391220.31,
            "ratio": 12.0
          }
        }
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
      },
      "story": {
        "overlap": {
          "items": {
            "a": 3300,
            "b": 2100,
            "both": 1252
          },
          "vendors": {
            "a": 892,
            "b": 571,
            "both": 372
          },
          "spend": {
            "a": 203948929.87949997,
            "b": 108156253.61729999
          }
        },
        "examples": {
          "match": {
            "kind": "match",
            "same_supplier": true,
            "a": {
              "company": "acquirer",
              "vendor": "Seremvene Cutting Tools Industrial Corpo",
              "description": "SANDING BELT 4X36 120 GRIT ZIRC",
              "uom": "EA",
              "price": 4.7811,
              "price_base": 4.7811,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 4,
              "vendor_tokens": [
                [
                  "Seremvene",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "Cutting",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "Tools",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "Industrial",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "Corpo",
                  -1
                ]
              ],
              "item_tokens": [
                [
                  "SANDING",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "BELT",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "4X36",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "120",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "GRIT",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "ZIRC",
                  6
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "SEREMVENE CUTTING TOLS INDUSTR",
              "description": "BELT,SNDG,4X36,120 GRIT,ZIRC",
              "uom": "EA",
              "price": 5.1638,
              "price_base": 5.1638,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 2,
              "vendor_tokens": [
                [
                  "SEREMVENE",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "CUTTING",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "TOLS",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "INDUSTR",
                  4
                ]
              ],
              "item_tokens": [
                [
                  "BELT",
                  2
                ],
                [
                  ",",
                  0
                ],
                [
                  "SNDG",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "4X36",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "120",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "GRIT",
                  5
                ],
                [
                  ",",
                  0
                ],
                [
                  "ZIRC",
                  6
                ]
              ]
            },
            "notes": {
              "vendor": [
                {
                  "kind": "slip",
                  "a": "Tools",
                  "b": "TOLS"
                },
                {
                  "kind": "abbr",
                  "a": "Industrial",
                  "b": "INDUSTR"
                }
              ],
              "item": [
                {
                  "kind": "abbr",
                  "a": "SANDING",
                  "b": "SNDG"
                }
              ]
            },
            "stage": "I3",
            "tier": "B",
            "similarity": 1.0,
            "evidence": "I3 description similarity 1.00 (character n-gram TF-IDF). Agreeing attributes: bore 36IN, diameter 4IN, grit 120, kind BELT, material ZIRCONIA. Tier B: similarity 1.00 is at or above 0.78 and 3 critical attributes agree with no conflict."
          },
          "lookalike": {
            "kind": "lookalike",
            "same_supplier": false,
            "a": {
              "company": "acquirer",
              "vendor": "Bafest Industrial Corporation",
              "description": "GREASE LITHIUM COMPLEX NLGI 3 EP",
              "uom": "GAL",
              "price": 39.7501,
              "price_base": 10.5009,
              "base_unit": "litre",
              "conv": "confirmed",
              "lines": 4,
              "vendor_tokens": [
                [
                  "Bafest",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Industrial",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Corporation",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "GREASE",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "LITHIUM",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "COMPLEX",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "NLGI",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "3",
                  -3
                ],
                [
                  " ",
                  0
                ],
                [
                  "EP",
                  5
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "TOCORO SUPPLY EAST INC",
              "description": "GRS,NLGI 2,LITHIUM COMPLEX,EP",
              "uom": "L",
              "price": 15.1293,
              "price_base": 15.1293,
              "base_unit": "litre",
              "conv": "confirmed",
              "lines": 5,
              "vendor_tokens": [
                [
                  "TOCORO",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "SUPPLY",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "EAST",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "INC",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "GRS",
                  1
                ],
                [
                  ",",
                  0
                ],
                [
                  "NLGI",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "2",
                  -3
                ],
                [
                  ",",
                  0
                ],
                [
                  "LITHIUM",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "COMPLEX",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "EP",
                  5
                ]
              ]
            },
            "notes": {
              "vendor": [],
              "item": [
                {
                  "kind": "abbr",
                  "a": "GREASE",
                  "b": "GRS"
                }
              ]
            },
            "stage": "I3",
            "tier": "C",
            "similarity": 0.98,
            "evidence": "I3 description similarity 0.98 (character n-gram TF-IDF). Agreeing attributes: none. Other numbers in the descriptions differ (3 vs 2). Tier C, review only: other numbers in the descriptions differ. Text similarity alone never matches."
          },
          "trap": {
            "kind": "trap",
            "same_supplier": false,
            "a": {
              "company": "acquirer",
              "vendor": "Noronoran Supply Corp",
              "description": "DRILL BIT JOBBER 12MM HSS BLKOX 140 DEG",
              "uom": "EA",
              "price": 17.1223,
              "price_base": 17.1223,
              "base_unit": "each",
              "conv": "confirmed",
              "lines": 24,
              "vendor_tokens": [
                [
                  "Noronoran",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Supply",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "Corp",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "DRILL",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "BIT",
                  2
                ],
                [
                  " ",
                  0
                ],
                [
                  "JOBBER",
                  3
                ],
                [
                  " ",
                  0
                ],
                [
                  "12MM",
                  4
                ],
                [
                  " ",
                  0
                ],
                [
                  "HSS",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "BLKOX",
                  6
                ],
                [
                  " ",
                  0
                ],
                [
                  "140",
                  7
                ],
                [
                  " ",
                  0
                ],
                [
                  "DEG",
                  8
                ]
              ]
            },
            "b": {
              "company": "target",
              "vendor": "FARANA INDUSTRIAL SUPPLY CORPO",
              "description": "BIT,DRL JOBBER,12MM,HSS BLKOX,140 DEG",
              "uom": "BX",
              "price": 210.4593,
              "price_base": null,
              "base_unit": null,
              "conv": "unconverted",
              "lines": 27,
              "vendor_tokens": [
                [
                  "FARANA",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "INDUSTRIAL",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "SUPPLY",
                  0
                ],
                [
                  " ",
                  0
                ],
                [
                  "CORPO",
                  0
                ]
              ],
              "item_tokens": [
                [
                  "BIT",
                  2
                ],
                [
                  ",",
                  0
                ],
                [
                  "DRL",
                  1
                ],
                [
                  " ",
                  0
                ],
                [
                  "JOBBER",
                  3
                ],
                [
                  ",",
                  0
                ],
                [
                  "12MM",
                  4
                ],
                [
                  ",",
                  0
                ],
                [
                  "HSS",
                  5
                ],
                [
                  " ",
                  0
                ],
                [
                  "BLKOX",
                  6
                ],
                [
                  ",",
                  0
                ],
                [
                  "140",
                  7
                ],
                [
                  " ",
                  0
                ],
                [
                  "DEG",
                  8
                ]
              ]
            },
            "notes": {
              "vendor": [],
              "item": [
                {
                  "kind": "abbr",
                  "a": "DRILL",
                  "b": "DRL"
                }
              ]
            },
            "removed": 679308.91,
            "ratio": 12.3
          }
        }
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
