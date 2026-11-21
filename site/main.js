(function () {
  "use strict";

  // Demo button: not a link while DEMO_URL is "#". Once the demo is live it becomes the
  // primary action and the workbook download steps back to a secondary button.
  var btn = document.getElementById("demo-button");
  var workbook = document.getElementById("workbook-button");
  var url = typeof DEMO_URL === "string" ? DEMO_URL : "#";
  if (btn) {
    if (url === "#") {
      btn.textContent = "Live demo coming soon";
      btn.removeAttribute("href");
      btn.setAttribute("aria-disabled", "true");
      btn.classList.add("is-disabled");
      // The live primary action comes first; while the demo is not live, that is the workbook.
      if (workbook && btn.parentNode === workbook.parentNode) {
        btn.parentNode.insertBefore(workbook, btn);
      }
    } else {
      btn.textContent = "Open the live demo";
      btn.setAttribute("href", url);
      if (workbook) workbook.classList.add("ghost");
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
  var range = "$" + (r.low / 1e6).toFixed(dp) + "–" + (r.high / 1e6).toFixed(dp) + "M";
  text("range", range);

  // The bridge as floating bars: removals step down from the naive figure to the
  // defensible price-harmonisation saving; volume consolidation (the rest of the
  // run-rate saving) steps back up to the defensible run-rate figure and its range.
  var labels = [
    "Unit-of-measure errors",
    "Unverified matches",
    "Spot-price benchmark",
    "Internal variance",
    "Non-comparable terms",
    "Contract lock-in",
    "Capture probability"
  ];
  var ladder = document.getElementById("ladder");
  if (ladder) {
    var scale = TIEOUT.naive;
    var level = TIEOUT.naive;
    // [label, value text, bar from, bar to, classes, extra line]
    var rows = [["Naive figure", money1(TIEOUT.naive), 0, level, "total start"]];
    TIEOUT.lever1.steps.forEach(function (v, i) {
      rows.push([labels[i], "−" + money1(v), level - v, level, "cut"]);
      level -= v;
    });
    var l1 = TIEOUT.lever1.defensible;
    rows.push(["Defensible price harmonisation", money1(l1), 0, l1, "total keep"]);
    var volume = r.base - l1;
    if (volume > 0) {
      rows.push(["+ Volume consolidation", "+" + money1(volume), l1, r.base, "keep"]);
    }
    rows.push(["Defensible run-rate saving", money1(r.base), 0, r.base, "total keep end", "range " + range]);
    rows.forEach(function (row) {
      var li = document.createElement("li");
      li.className = row[4];
      var name = document.createElement("span");
      name.className = "name";
      name.textContent = row[0];
      var val = document.createElement("span");
      val.className = "val";
      val.textContent = row[1];
      if (row[5]) {
        var extra = document.createElement("span");
        extra.className = "range";
        extra.textContent = row[5];
        val.appendChild(extra);
      }
      var track = document.createElement("span");
      track.className = "track";
      track.setAttribute("aria-hidden", "true");
      var fill = document.createElement("i");
      fill.style.left = ((row[2] / scale) * 100).toFixed(2) + "%";
      fill.style.width = Math.max(0.6, ((row[3] - row[2]) / scale) * 100).toFixed(2) + "%";
      track.appendChild(fill);
      li.appendChild(name);
      li.appendChild(track);
      li.appendChild(val);
      ladder.appendChild(li);
    });
  }
  function money1(x) {
    return "$" + (x / 1e6).toFixed(1) + "M";
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
        else {
          c.className = "num" + (i === 1 ? " strong" : "");
          c.setAttribute("data-label", ["Tie-Out", "Naive", "Target"][i - 1]);
        }
        c.textContent = s;
        tr.appendChild(c);
      });
      body.appendChild(tr);
    });
  }
})();
