(function () {
  "use strict";

  // Demo button: not a link while DEMO_URL is "#".
  var btn = document.getElementById("demo-button");
  var url = typeof DEMO_URL === "string" ? DEMO_URL : "#";
  if (btn) {
    if (url === "#") {
      btn.textContent = "Live demo coming soon";
      btn.removeAttribute("href");
      btn.setAttribute("aria-disabled", "true");
      btn.classList.add("is-disabled");
    } else {
      btn.textContent = "Open the live demo";
      btn.setAttribute("href", url);
    }
  }

  if (typeof TIEOUT === "undefined") return;

  // Headline rounding (PRD 6.11): nearest $1M from $10M up, else nearest $0.1M.
  function millions(x) {
    var m = x / 1e6;
    return m >= 10 ? Math.round(m).toFixed(0) : m.toFixed(1);
  }
  function money(x) {
    return "$" + millions(x) + "M";
  }
  function pct(x) {
    return (x * 100).toFixed(1) + "%";
  }
  function text(id, s) {
    var el = document.querySelector('[data-bind="' + id + '"]');
    if (el) el.textContent = s;
  }

  var r = TIEOUT.defensible_recurring;
  text("naive", money(TIEOUT.naive));
  // The upper end sets the precision of both ends.
  var dp = r.high >= 1e7 ? 0 : 1;
  text("range", "$" + (r.low / 1e6).toFixed(dp) + "–" + (r.high / 1e6).toFixed(dp) + "M");

  var labels = [
    "Unit-of-measure errors",
    "Unverified matches",
    "Spot-price benchmark",
    "Internal variance",
    "Non-comparable terms",
    "Contract lock-in",
    "Capture probability"
  ];
  var list = document.getElementById("bridge-steps");
  if (list) {
    var rows = [["Naive figure", TIEOUT.naive, "start"]];
    TIEOUT.lever1.steps.forEach(function (v, i) {
      rows.push([labels[i], v, "cut"]);
    });
    rows.push(["Defensible price harmonisation", TIEOUT.lever1.defensible, "end"]);
    rows.forEach(function (row, i) {
      var li = document.createElement("li");
      li.className = row[2];
      var name = document.createElement("span");
      name.className = "name";
      name.textContent = (row[2] === "cut" ? "Remove: " : "") + row[0];
      var val = document.createElement("span");
      val.className = "val";
      val.textContent = (row[2] === "cut" ? "−" : "") + "$" + (row[1] / 1e6).toFixed(1) + "M";
      var bar = document.createElement("span");
      bar.className = "bar";
      bar.setAttribute("aria-hidden", "true");
      var fill = document.createElement("i");
      fill.style.width = Math.max(0.8, (row[1] / TIEOUT.naive) * 100).toFixed(1) + "%";
      bar.appendChild(fill);
      li.appendChild(name);
      li.appendChild(val);
      li.appendChild(bar);
      list.appendChild(li);
    });
  }

  var names = {
    vendor_precision: "Vendor match precision",
    vendor_recall: "Vendor match recall",
    item_precision: "Item match precision",
    item_recall: "Item match recall",
    false_savings_rate: "False-savings rate",
    unit_error_catch_rate: "Unit-error catch rate",
    planted_savings_recall: "Planted-savings recall"
  };
  var body = document.getElementById("score-rows");
  if (body) {
    Object.keys(names).forEach(function (k) {
      var m = TIEOUT.scorecard.metrics[k];
      if (!m) return;
      var tr = document.createElement("tr");
      var target = m.target === null ? "none" : m.direction.replace("<=", "≤").replace(">=", "≥") + " " + pct(m.target);
      [names[k], pct(m.tool), pct(m.baseline), target].forEach(function (s, i) {
        var c = document.createElement(i === 0 ? "th" : "td");
        if (i === 0) c.scope = "row";
        else c.className = "num" + (i === 1 ? " strong" : "");
        c.textContent = s;
        tr.appendChild(c);
      });
      body.appendChild(tr);
    });
  }
})();
