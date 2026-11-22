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

  if (typeof TIEOUT === "undefined" || !TIEOUT.samples || !TIEOUT.samples.length) return;

  var samples = TIEOUT.samples;
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Headline rounding (PRD 6.11): nearest $1M from $10M up, else nearest $0.1M.
  function millions(x) {
    var m = x / 1e6;
    return m >= 10 ? Math.round(m).toFixed(0) : m.toFixed(1);
  }
  function money(x) {
    return "$" + millions(x) + "M";
  }
  function money1(x) {
    return "$" + (x / 1e6).toFixed(1) + "M";
  }
  function pct(x) {
    return (x * 100).toFixed(1) + "%";
  }
  // The upper end sets the precision of both ends.
  function rangeText(low, high, top) {
    var dp = (top === undefined ? high : top) >= 1e7 ? 0 : 1;
    return "$" + (low / 1e6).toFixed(dp) + "–" + (high / 1e6).toFixed(dp) + "M";
  }
  function bind(id, s) {
    var els = document.querySelectorAll('[data-bind="' + id + '"]');
    for (var i = 0; i < els.length; i++) els[i].textContent = s;
  }
  function setAttr(selector, attr, value) {
    var els = document.querySelectorAll(selector);
    for (var i = 0; i < els.length; i++) els[i].setAttribute(attr, value);
  }

  // The headline counts up to its value on arrival; the final text is always the exact one.
  var counting = 0;
  function headline(sample) {
    var r = sample.defensible_recurring;
    var token = ++counting;
    function draw(t) {
      if (token !== counting) return;
      if (t >= 1) {
        counting++; // any frame still queued for this sample is now stale
        bind("naive", money(sample.naive));
        bind("range", rangeText(r.low, r.high));
        return;
      }
      var e = 1 - Math.pow(1 - t, 3);
      var m = sample.naive * e;
      // Counting keeps the final figure's precision, so the last frame does not jump.
      bind("naive", "$" + (sample.naive >= 1e7 ? Math.round(m / 1e6).toFixed(0) : (m / 1e6).toFixed(1)) + "M");
      bind("range", rangeText(r.low * e, r.high * e, r.high));
    }
    if (reduced || !window.requestAnimationFrame) return draw(1);
    var start = null;
    function frame(now) {
      if (start === null) start = now;
      var t = Math.min(1, (now - start) / 700);
      draw(t);
      if (t < 1 && token === counting) window.requestAnimationFrame(frame);
    }
    window.requestAnimationFrame(frame);
    // Frames can be throttled (a background tab); the exact figures land regardless.
    window.setTimeout(function () {
      draw(1);
    }, 900);
  }

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
  function ladder(sample) {
    var list = document.getElementById("ladder");
    if (!list) return;
    while (list.firstChild) list.removeChild(list.firstChild);
    var r = sample.defensible_recurring;
    var scale = sample.naive;
    var level = sample.naive;
    // [label, value text, bar from, bar to, classes, extra line]
    var rows = [["Naive figure", money1(sample.naive), 0, level, "total start"]];
    sample.lever1.steps.forEach(function (v, i) {
      rows.push([labels[i], "−" + money1(v), level - v, level, "cut"]);
      level -= v;
    });
    var l1 = sample.lever1.defensible;
    rows.push(["Defensible price harmonisation", money1(l1), 0, l1, "total keep"]);
    var volume = r.base - l1;
    if (volume > 0) {
      rows.push(["+ Volume consolidation", "+" + money1(volume), l1, r.base, "keep"]);
    }
    rows.push([
      "Defensible run-rate saving",
      money1(r.base),
      0,
      r.base,
      "total keep end",
      "range " + rangeText(r.low, r.high)
    ]);
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
      list.appendChild(li);
    });
  }

  function show(index) {
    var sample = samples[index];
    bind("sample", sample.label);
    bind("sample-number", String(index + 1));
    bind("sample-count", String(samples.length));
    headline(sample);
    ladder(sample);
    setAttr('[data-asset="workbook"]', "href", sample.assets.workbook);
    setAttr('[data-asset="deck"]', "href", sample.assets.deck);
    setAttr('[data-asset="bridge"]', "href", sample.assets.bridge);
    setAttr('img[data-asset="bridge"]', "src", sample.assets.bridge);
  }

  // A random sample on every visit (or ?sample=<id>), then "Show another sample" walks
  // through the rest in order, so every sample is seen before one repeats.
  var current = Math.floor(Math.random() * samples.length);
  var asked = /[?&]sample=([\w-]+)/.exec(window.location.search);
  if (asked) {
    samples.forEach(function (s, i) {
      if (s.id === asked[1]) current = i;
    });
  }
  show(current);

  var next = document.getElementById("next-sample");
  var bar = document.getElementById("sample-bar");
  if (bar) bar.hidden = false;
  if (next && samples.length > 1) {
    var swapping = false;
    var fading = document.querySelectorAll(".swaps");
    next.addEventListener("click", function () {
      if (swapping) return;
      current = (current + 1) % samples.length;
      if (reduced) return show(current);
      swapping = true;
      for (var i = 0; i < fading.length; i++) fading[i].classList.add("is-leaving");
      window.setTimeout(function () {
        show(current);
        for (var j = 0; j < fading.length; j++) fading[j].classList.remove("is-leaving");
        swapping = false;
      }, 220);
    });
  } else if (next) {
    next.hidden = true;
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
