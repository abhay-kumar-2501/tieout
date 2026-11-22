(function () {
  "use strict";

  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ------------------------------------------------------------------ demo buttons
  // Not links while DEMO_URL is "#". Once the demo is live the hero button becomes the
  // primary action and the workbook download steps back to a secondary button.
  var url = typeof DEMO_URL === "string" ? DEMO_URL : "#";
  var workbookButton = document.getElementById("workbook-button");
  ["demo-button", "demo-button-2"].forEach(function (id) {
    var btn = document.getElementById(id);
    if (!btn) return;
    if (url === "#") {
      btn.textContent = "Live demo coming soon";
      btn.removeAttribute("href");
      btn.setAttribute("aria-disabled", "true");
      btn.classList.add("is-disabled");
      if (id === "demo-button" && workbookButton && btn.parentNode === workbookButton.parentNode) {
        workbookButton.classList.remove("ghost");
        btn.parentNode.insertBefore(workbookButton, btn);
      }
    } else {
      btn.setAttribute("href", url);
    }
  });

  // ------------------------------------------------------------------ glossary terms
  // Hover and focus show the tip in CSS; a tap toggles it, and Escape closes it.
  Array.prototype.forEach.call(document.querySelectorAll(".term"), function (term) {
    term.setAttribute("aria-expanded", "false");
    term.addEventListener("click", function () {
      term.setAttribute("aria-expanded", term.getAttribute("aria-expanded") === "true" ? "false" : "true");
    });
    term.addEventListener("blur", function () {
      term.setAttribute("aria-expanded", "false");
    });
    term.addEventListener("keydown", function (e) {
      if (e.key === "Escape") {
        term.setAttribute("aria-expanded", "false");
        term.blur();
      }
    });
  });

  // ------------------------------------------------------------------ scroll reveal
  var watchers = [];
  function onReveal(el, fn) {
    watchers.push([el, fn]);
    if (io) io.observe(el);
    else fn();
  }
  var io = null;
  if (!reduced && "IntersectionObserver" in window) {
    io = new IntersectionObserver(
      function (entries) {
        entries.forEach(function (entry) {
          if (!entry.isIntersecting) return;
          io.unobserve(entry.target);
          watchers.forEach(function (w) {
            if (w[0] === entry.target) w[1]();
          });
        });
      },
      { rootMargin: "0px 0px -10% 0px", threshold: 0.05 }
    );
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-reveal]"), function (el) {
    onReveal(el, function () {
      el.classList.add("is-in");
    });
  });

  if (typeof TIEOUT === "undefined" || !TIEOUT.samples || !TIEOUT.samples.length) return;
  var samples = TIEOUT.samples;

  // ------------------------------------------------------------------ formatting
  // Headline rounding (PRD 6.11): nearest $1M from $10M up, else nearest $0.1M.
  function millions(x) {
    var m = x / 1e6;
    return m >= 10 ? Math.round(m).toFixed(0) : m.toFixed(1);
  }
  function money(x) {
    return "$" + millions(x) + "M";
  }
  function money1(x) {
    // Below a tenth of a million a small step would round to zero; show thousands.
    if (Math.abs(x) < 1e5) return "$" + Math.round(x / 1e3) + "k";
    return "$" + (x / 1e6).toFixed(1) + "M";
  }
  // The upper end sets the precision of both ends.
  function rangeText(low, high, top) {
    var dp = (top === undefined ? high : top) >= 1e7 ? 0 : 1;
    return "$" + (low / 1e6).toFixed(dp) + "–" + (high / 1e6).toFixed(dp) + "M";
  }
  function pct(x) {
    return (x * 100).toFixed(1) + "%";
  }
  function whole(x) {
    return Math.round(x).toLocaleString("en-US");
  }
  function price(x) {
    if (x >= 100) return "$" + x.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    if (x >= 1) return "$" + x.toFixed(2);
    return "$" + x.toPrecision(3);
  }
  function spend(x) {
    return x >= 1e9 ? "$" + (x / 1e9).toFixed(1) + "B" : money(x);
  }
  var UNIT_NAMES = {
    EA: "each", PC: "piece", BX: "box", CS: "case", PK: "pack", BG: "bag", RL: "roll",
    FT: "foot", M: "metre", MTR: "metre", GAL: "gallon", L: "litre", LT: "litre",
    KG: "kilogram", LB: "pound", PR: "pair"
  };
  function unitName(code) {
    return UNIT_NAMES[code] || code;
  }
  // "per single item (EA)" reads better than "per each".
  function unitPhrase(code) {
    var name = code === "EA" || code === "PC" ? "single item" : unitName(code);
    return name + " (" + code + ")";
  }

  function bind(id, s) {
    var els = document.querySelectorAll('[data-bind="' + id + '"]');
    for (var i = 0; i < els.length; i++) els[i].textContent = s;
  }
  function setAttr(selector, attr, value) {
    var els = document.querySelectorAll(selector);
    for (var i = 0; i < els.length; i++) els[i].setAttribute(attr, value);
  }
  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function icon(name) {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("class", "i");
    svg.setAttribute("aria-hidden", "true");
    var use = document.createElementNS(ns, "use");
    use.setAttribute("href", "#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  function clear(node) {
    while (node.firstChild) node.removeChild(node.firstChild);
  }
  // Two frames, so that a state set now is painted before the next change animates.
  function later(fn) {
    if (reduced || !window.requestAnimationFrame) return fn();
    window.requestAnimationFrame(function () {
      window.requestAnimationFrame(fn);
    });
  }

  // ------------------------------------------------------------------ hero
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
      var t = Math.min(1, (now - start) / 900);
      draw(t);
      if (t < 1 && token === counting) window.requestAnimationFrame(frame);
    }
    window.requestAnimationFrame(frame);
    // Frames can be throttled (a background tab); the exact figures land regardless.
    window.setTimeout(function () {
      draw(1);
    }, 1100);
  }

  // The meter: the quick estimate as one bar. The parts that do not hold up turn to
  // hatching one after another; what holds up stays teal, and the bulk-buying saving
  // (volume consolidation) grows on top of it to the defensible yearly figure.
  function meter(sample) {
    var track = document.getElementById("meter-track");
    var box = document.getElementById("meter");
    var card = document.querySelector(".shrink");
    if (!track || !box) return;
    clear(track);
    var r = sample.defensible_recurring;
    var scale = sample.naive;
    var l1 = sample.lever1.defensible;
    function seg(cls, from, to, delay) {
      var s = el("span", "seg " + cls);
      s.style.left = ((from / scale) * 100).toFixed(3) + "%";
      s.style.width = ((Math.max(0, to - from) / scale) * 100).toFixed(3) + "%";
      s.style.setProperty("--d", delay + "s");
      track.appendChild(s);
      return s;
    }
    seg("seg-keep", 0, l1, 0);
    var level = l1;
    sample.lever1.steps.forEach(function (v, i) {
      seg("seg-gone", level, level + v, 0.25 + i * 0.12);
      level += v;
    });
    var bulk = seg("seg-bulk", l1, r.base, 1.3);
    bulk.style.setProperty("--w", bulk.style.width);
    var range = document.querySelector("#meter-range span");
    if (range) {
      range.style.left = ((r.low / scale) * 100).toFixed(3) + "%";
      range.style.width = (((r.high - r.low) / scale) * 100).toFixed(3) + "%";
    }
    bind("gone-share", Math.round((1 - l1 / sample.naive) * 100) + "%");
    box.classList.add("is-before");
    if (card) card.classList.remove("is-run");
    later(function () {
      box.classList.remove("is-before");
      if (card) card.classList.add("is-run");
    });
  }

  // ------------------------------------------------------------------ chapter 1
  function overlap(sample) {
    var o = sample.story && sample.story.overlap;
    if (!o) return;
    bind("items-a", whole(o.items.a));
    bind("items-b", whole(o.items.b));
    bind("items-both", whole(o.items.both));
    bind("vendors-both", whole(o.vendors.both));
    bind("spend-total", spend(o.spend.a + o.spend.b));
    // Circle areas follow the item counts; the overlap is drawn wide enough to read
    // and grows with the share of the smaller list that both companies buy.
    var maxR = 150;
    var big = Math.max(o.items.a, o.items.b);
    var ra = maxR * Math.sqrt(o.items.a / big);
    var rb = maxR * Math.sqrt(o.items.b / big);
    var share = o.items.both / Math.min(o.items.a, o.items.b);
    var lens = Math.max(0.35, Math.min(0.9, share)) * 2 * Math.min(ra, rb);
    var d = ra + rb - lens;
    var mid = 320 + (ra - rb) / 2;
    var ax = mid - d / 2 - (ra - rb) / 2;
    var bx = ax + d;
    var cy = 170;
    function circle(id, cx, rr) {
      var c = document.getElementById(id);
      if (!c) return;
      c.setAttribute("cx", cx.toFixed(1));
      c.setAttribute("cy", String(cy));
      c.setAttribute("r", rr.toFixed(1));
    }
    circle("venn-a", ax, ra);
    circle("clip-a-c", ax, ra);
    circle("venn-b", bx, rb);
    circle("venn-lens", bx, rb);
  }

  // ------------------------------------------------------------------ chapter 2
  var kind = "match";
  var tied = false;
  var current = 0;

  function tokens(list, mark) {
    var frag = document.createDocumentFragment();
    var n = 0;
    list.forEach(function (t) {
      var text = t[0];
      var g = t[1];
      if (!/[^\s,;]/.test(text)) {
        frag.appendChild(document.createTextNode(text));
        return;
      }
      var span = el("span", "tok", text);
      if (g > 0) {
        span.className += " g" + (((g - 1) % 8) + 1);
        span.setAttribute("data-g", mark + g);
      } else if (g === -1) span.className += " drop";
      else if (g === -2) span.className += " pack";
      else if (g === -3) span.className += " clash";
      span.style.setProperty("--d", (n++ * 0.04).toFixed(2) + "s");
      frag.appendChild(span);
    });
    return frag;
  }

  function recordCard(node, rec, label, example) {
    clear(node);
    var head = el("div", "rec-head");
    head.appendChild(el("span", null, label));
    head.appendChild(el("span", null, rec.lines + (rec.lines === 1 ? " purchase line" : " purchase lines")));
    node.appendChild(head);
    var dl = el("dl", "rec-body");
    function row(name, content, cls) {
      var r = el("div", "rec-row" + (cls ? " " + cls : ""));
      r.appendChild(el("dt", null, name));
      var dd = el("dd");
      dd.appendChild(content);
      r.appendChild(dd);
      dl.appendChild(r);
    }
    row("Supplier", tokens(rec.vendor_tokens, "v"));
    row("Item", tokens(rec.item_tokens, "i"));
    var unit = document.createDocumentFragment();
    var code = el("span", "tok unit-code", rec.uom);
    if (example.kind === "trap") code.className += " unit-hit";
    unit.appendChild(code);
    unit.appendChild(el("span", "unit-name", " (" + unitName(rec.uom) + ")"));
    row("Unit", unit);
    var p = document.createDocumentFragment();
    p.appendChild(el("span", "price-tag", price(rec.price)));
    p.appendChild(el("span", "per", rec.uom === "EA" ? " each" : " per " + unitName(rec.uom)));
    row("Price paid", p, "price");
    node.appendChild(dl);
  }

  function quoted(text) {
    var q = el("q", null, text);
    return q;
  }
  function reason(parts) {
    var li = el("li");
    parts.forEach(function (p) {
      li.appendChild(typeof p === "string" ? document.createTextNode(p) : p);
    });
    return li;
  }
  function noteReason(note) {
    var shortFirst = note.a.length <= note.b.length;
    var s = shortFirst ? note.a : note.b;
    var l = shortFirst ? note.b : note.a;
    if (note.kind === "abbr") return reason([quoted(s), " is short for ", quoted(l)]);
    if (note.kind === "slip") return reason([quoted(note.a), " and ", quoted(note.b), " are one name with a typing slip"]);
    if (note.kind === "format") return reason([quoted(note.a), " and ", quoted(note.b), " are the same size, written two ways"]);
    return null;
  }
  function droppedWords(example) {
    var seen = {};
    var out = [];
    ["a", "b"].forEach(function (side) {
      example[side].vendor_tokens.forEach(function (t) {
        var key = t[0].toUpperCase().replace(/[^A-Z]/g, "");
        if (t[1] === -1 && !seen[key]) {
          seen[key] = true;
          out.push(t[0]);
        }
      });
    });
    return out;
  }
  function sameCount(example) {
    var noted = {};
    var groups = {};
    example.a.item_tokens.forEach(function (t) {
      if (t[1] > 0) groups[t[1]] = (groups[t[1]] || "") + " " + t[0];
    });
    example.notes.item.forEach(function (n) {
      Object.keys(groups).forEach(function (g) {
        if (groups[g].trim() === n.a) noted[g] = true;
      });
    });
    return Object.keys(groups).filter(function (g) {
      return !noted[g];
    }).length;
  }
  function clashWords(list) {
    return list
      .filter(function (t) {
        return t[1] === -3;
      })
      .map(function (t) {
        return t[0];
      })
      .join(" ");
  }
  function packWords(list) {
    return list
      .filter(function (t) {
        return t[1] === -2;
      })
      .map(function (t) {
        return t[0];
      })
      .join(" ");
  }

  function verdict(example) {
    var box = document.getElementById("verdict");
    clear(box);
    var a = example.a;
    var b = example.b;
    var cls = { match: "v-yes", lookalike: "v-no", trap: "v-trap" }[example.kind];
    box.className = "verdict " + cls;
    var ic = el("div", "v-icon");
    ic.appendChild(icon({ match: "check", lookalike: "cross", trap: "alert" }[example.kind]));
    box.appendChild(ic);
    var body = el("div");
    var list = el("ul", "v-reasons");
    var money_ = el("p", "v-money");

    if (example.kind === "match") {
      body.appendChild(el("p", "v-title", example.same_supplier ? "Same supplier, same item." : "Same item."));
      body.appendChild(el("p", "v-text", "Written differently, but every difference has an innocent explanation:"));
      example.notes.vendor.concat(example.notes.item).forEach(function (n) {
        var li = noteReason(n);
        if (li) list.appendChild(li);
      });
      var dropped = droppedWords(example);
      if (dropped.length) {
        var parts = [];
        dropped.forEach(function (w, i) {
          if (i) parts.push(i === dropped.length - 1 ? " and " : ", ");
          parts.push(quoted(w));
        });
        parts.push(dropped.length > 1 ? " only state the legal form of the business, so they are ignored" : " only states the legal form of the business, so it is ignored");
        list.appendChild(reason(parts));
      }
      [a, b].forEach(function (rec) {
        var p = packWords(rec.item_tokens);
        if (p) list.appendChild(reason([quoted(p), " states the pack size, so prices can be compared per piece"]));
      });
      var same = sameCount(example);
      if (same) list.appendChild(reason([same + (same === 1 ? " other detail matches" : " other details match") + " word for word, in any order"]));
      body.appendChild(list);
      box.appendChild(body);
      var unitNote = a.uom !== b.uom ? " (after converting " + unitName(a.uom) + " and " + unitName(b.uom) + " to one unit)" : "";
      money_.className += " good";
      money_.textContent =
        "Now the prices compare like for like" + unitNote + ": Company A pays " + price(a.price_base) +
        ", Company B " + price(b.price_base) + " per " + (a.base_unit || unitName(a.uom)) + ". That gap is a saving that can count.";
      box.appendChild(money_);
    } else if (example.kind === "lookalike") {
      var ca = clashWords(a.item_tokens);
      var cb = clashWords(b.item_tokens);
      body.appendChild(el("p", "v-title", "Close, but not proven the same."));
      var t = el("p", "v-text");
      t.appendChild(document.createTextNode("Nearly every word lines up, but one number does not: "));
      t.appendChild(quoted(ca));
      t.appendChild(document.createTextNode(" against "));
      t.appendChild(quoted(cb));
      t.appendChild(
        document.createTextNode(
          ". That can mean a different size, grade or count, so Tie-Out sets the pair aside for a person to check. Until then, its price gap is not counted."
        )
      );
      body.appendChild(t);
      example.notes.item.forEach(function (n) {
        var li = noteReason(n);
        if (li) list.appendChild(li);
      });
      if (list.childNodes.length) body.appendChild(list);
      box.appendChild(body);
      money_.className += " bad";
      money_.textContent =
        "A quick estimate treats them as one item and counts the gap between " + price(a.price) + " and " + price(b.price) + " as a saving.";
      box.appendChild(money_);
    } else {
      body.appendChild(el("p", "v-title", "Same item, different units."));
      var known = a.price_base !== null && b.price_base !== null;
      var text =
        "Company A records it per " + unitPhrase(a.uom) + " at " + price(a.price) + "; Company B per " + unitPhrase(b.uom) +
        " at " + price(b.price) + ". ";
      text += known
        ? "Converted to one unit, they pay " + price(a.price_base) + " and " + price(b.price_base) + " per " + a.base_unit + "."
        : "Neither record says how many come in a " +
          unitName(a.price_base === null ? a.uom : b.uom) +
          ", so there is no fair way to compare the two prices. The gap is an illusion of units.";
      body.appendChild(el("p", "v-text", text));
      box.appendChild(body);
      money_.className += " bad";
      money_.textContent =
        "The quick estimate counted this one gap as " + money1(example.removed) + " of savings a year. Tie-Out takes it out.";
      box.appendChild(money_);
    }

    if (example.evidence) {
      var d = el("details", "engine");
      d.appendChild(el("summary", null, "What the matching engine recorded"));
      d.appendChild(el("p", null, example.evidence));
      box.appendChild(d);
    }
  }

  var PROMPTS = {
    match: "Two records, one from each company. Are they the same thing?",
    lookalike: "These two look almost identical. Same item?",
    trap: "Company A seems to pay far more for this. Is that a saving waiting to happen?"
  };

  function renderTie() {
    var sample = samples[current];
    var ex = sample.story && sample.story.examples ? sample.story.examples : {};
    var wrap = document.getElementById("tieout");
    if (!wrap) return;
    // A sample without one of the three examples hides its tab.
    Array.prototype.forEach.call(wrap.querySelectorAll('[role="tab"]'), function (tab) {
      tab.hidden = !ex[tab.getAttribute("data-kind")];
    });
    if (!ex[kind]) kind = ["match", "lookalike", "trap"].filter(function (k) { return ex[k]; })[0];
    if (!kind) {
      wrap.hidden = true;
      return;
    }
    wrap.hidden = false;
    var example = ex[kind];
    var panel = document.getElementById("tie-panel");
    panel.classList.toggle("trap-mode", kind === "trap");
    panel.classList.remove("is-tied", "v-no");
    panel.setAttribute("aria-labelledby", "tab-" + kind);
    document.getElementById("tie-prompt").textContent = PROMPTS[kind];
    recordCard(document.getElementById("rec-a"), example.a, "Company A", example);
    recordCard(document.getElementById("rec-b"), example.b, "Company B", example);
    var old = panel.querySelector(".ratio-badge");
    if (old) old.parentNode.removeChild(old);
    if (kind === "trap") {
      var badge = el("p", "ratio-badge");
      badge.appendChild(icon("alert"));
      badge.appendChild(document.createTextNode(example.ratio.toFixed(0) + "× the price?"));
      panel.querySelector(".cards").insertAdjacentElement("afterend", badge);
    }
    var button = document.getElementById("tie-button");
    button.textContent = "Tie them out";
    button.setAttribute("aria-expanded", "false");
    document.getElementById("verdict").hidden = true;
    tied = false;
  }

  function tie() {
    var sample = samples[current];
    var example = sample.story.examples[kind];
    var panel = document.getElementById("tie-panel");
    var button = document.getElementById("tie-button");
    var box = document.getElementById("verdict");
    if (tied) return renderTie();
    tied = true;
    panel.classList.add("is-tied");
    panel.classList.toggle("v-no", kind === "lookalike");
    var badge = panel.querySelector(".ratio-badge");
    if (badge) badge.hidden = true;
    verdict(example);
    box.hidden = false;
    button.textContent = "Reset";
    button.setAttribute("aria-expanded", "true");
  }

  function setupTie() {
    var wrap = document.getElementById("tieout");
    if (!wrap) return;
    var tabs = Array.prototype.slice.call(wrap.querySelectorAll('[role="tab"]'));
    function select(tab, focus) {
      tabs.forEach(function (t) {
        var on = t === tab;
        t.setAttribute("aria-selected", on ? "true" : "false");
        t.tabIndex = on ? 0 : -1;
      });
      kind = tab.getAttribute("data-kind");
      renderTie();
      if (focus) tab.focus();
    }
    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        select(tab, false);
      });
      tab.addEventListener("keydown", function (e) {
        var visible = tabs.filter(function (t) { return !t.hidden; });
        var i = visible.indexOf(tab);
        var next = null;
        if (e.key === "ArrowRight") next = visible[(i + 1) % visible.length];
        if (e.key === "ArrowLeft") next = visible[(i - 1 + visible.length) % visible.length];
        if (e.key === "Home") next = visible[0];
        if (e.key === "End") next = visible[visible.length - 1];
        if (next) {
          e.preventDefault();
          select(next, true);
        }
      });
    });
    document.getElementById("tie-button").addEventListener("click", tie);
    // Hovering or tapping a highlighted word lights up its partner on the other card.
    var panel = document.getElementById("tie-panel");
    function hot(target, on) {
      var g = target && target.getAttribute && target.getAttribute("data-g");
      Array.prototype.forEach.call(panel.querySelectorAll(".tok.is-hot"), function (t) {
        t.classList.remove("is-hot");
      });
      if (!g || !on || !panel.classList.contains("is-tied")) return;
      Array.prototype.forEach.call(panel.querySelectorAll('.tok[data-g="' + g + '"]'), function (t) {
        t.classList.add("is-hot");
      });
    }
    panel.addEventListener("mouseover", function (e) {
      hot(e.target, true);
    });
    panel.addEventListener("mouseout", function (e) {
      hot(e.target, false);
    });
    panel.addEventListener("click", function (e) {
      if (e.target.classList && e.target.classList.contains("tok")) hot(e.target, true);
    });
  }

  // ------------------------------------------------------------------ chapter 3
  var STEPS = [
    {
      name: "Unit mix-ups",
      title: "Unit-of-measure errors",
      why: "Prices recorded in different units: a box against a single piece. The gap is an illusion of units, not a saving.",
      example: "trap"
    },
    {
      name: "Unproven matches",
      title: "Unverified matches",
      why: "We could not prove the two items are the same thing, so their gap does not count. They wait for a person to review.",
      example: "lookalike"
    },
    {
      name: "One-off low prices",
      title: "Spot-price benchmark",
      why: "Some of the cheapest prices were one-off or tiny orders. We compare against a price that was paid regularly, on real volume."
    },
    {
      name: "Gaps inside one company",
      title: "Internal variance",
      why: "Part of the gap is between two sites of the same company. That saving was there without the merger, so it is not a merger saving."
    },
    {
      name: "Different delivery terms",
      title: "Non-comparable terms",
      why: "One price included delivery and the other did not. Not like for like, so it is held back."
    },
    {
      name: "Locked by contracts",
      title: "Contract lock-in",
      why: "Some volume is under contract for years beyond the plan, so its price cannot be renegotiated in time to count."
    },
    {
      name: "Not won in negotiation",
      title: "Capture probability",
      why: "Even a real gap is not won in full at the negotiating table. We count only the share a buyer can expect to win: more when it is the same supplier."
    }
  ];

  var selectedStep = 0;
  function bridge(sample) {
    var chart = document.getElementById("bridge-chart");
    var wrapEl = document.getElementById("bridge");
    if (!chart) return;
    clear(chart);
    var r = sample.defensible_recurring;
    var scale = sample.naive;
    var l1 = sample.lever1.defensible;
    var rows = [
      {
        cls: "s-start is-total", name: "The quick estimate", title: "The quick estimate", val: money1(sample.naive),
        from: 0, to: sample.naive, amount: sample.naive, tone: "",
        why: "Pay the lower of the two prices on everything both companies seem to buy, and add up the difference. This is where most merger plans start."
      }
    ];
    var level = sample.naive;
    sample.lever1.steps.forEach(function (v, i) {
      var s = STEPS[i];
      rows.push({
        cls: "s-gone", name: s.name, title: s.title, val: "−" + money1(v), from: level - v, to: level,
        amount: -v, tone: "t-gone", why: s.why, example: s.example
      });
      level -= v;
    });
    rows.push({
      cls: "s-keep is-total", name: "Price savings that hold up", title: "Defensible price savings", val: money1(l1),
      from: 0, to: l1, amount: l1, tone: "t-keep",
      why: "What is left: price gaps on items proven to be the same, compared like for like, that the combined company can expect to win."
    });
    var volume = r.base - l1;
    if (volume > 0) {
      rows.push({
        cls: "s-bulk", name: "+ Buying in bulk", title: "Volume consolidation", val: "+" + money1(volume),
        from: l1, to: r.base, amount: volume, tone: "t-keep",
        why: "Buying both companies' volume from fewer suppliers earns a bulk discount, estimated category by category with a cautious discount rate."
      });
    }
    rows.push({
      cls: "s-end is-total is-last", name: "Holds up, every year", title: "Defensible yearly saving", val: money1(r.base),
      from: 0, to: r.base, amount: r.base, tone: "t-keep", range: true,
      why: "The number to put in front of a board: " + rangeText(r.low, r.high) + " a year, with " + money1(r.base) +
        " as the central case. Every dollar traces back to purchase lines."
    });
    chart.style.setProperty("--n", rows.length);
    if (selectedStep >= rows.length) selectedStep = 0;

    var why = el("div", "step-why");
    why.id = "step-why";
    why.setAttribute("aria-live", "polite");

    function showWhy(i) {
      var row = rows[i];
      clear(why);
      var card = el("div", "why-card " + row.tone);
      var text = el("div");
      text.appendChild(el("p", "why-kicker", i === 0 ? "Starting point" : row.tone === "t-gone" ? "Taken out" : "Kept"));
      text.appendChild(el("p", "why-title", row.title));
      var p = el("p", "why-text", row.why + " ");
      if (row.example && samples[current].story && samples[current].story.examples[row.example]) {
        var a = el("a", null, "See a real example");
        a.href = "#ch-records";
        a.addEventListener("click", function () {
          var tab = document.getElementById("tab-" + row.example);
          if (tab) tab.click();
        });
        p.appendChild(a);
      }
      text.appendChild(p);
      card.appendChild(text);
      var amt = el("p", "why-amount", row.val);
      if (i > 0) {
        amt.appendChild(el("small", null, Math.round((Math.abs(row.amount) / sample.naive) * 100) + "% of the quick estimate"));
      }
      card.appendChild(amt);
      why.appendChild(card);
      Array.prototype.forEach.call(chart.querySelectorAll(".step"), function (b, j) {
        b.setAttribute("aria-pressed", j === i ? "true" : "false");
        b.style.order = String(j * 2);
      });
      why.style.order = String(i * 2 + 1);
    }

    rows.forEach(function (row, i) {
      var b = el("button", "step " + row.cls);
      b.type = "button";
      b.setAttribute("aria-controls", "step-why");
      b.style.setProperty("--from", (row.from / scale).toFixed(4));
      b.style.setProperty("--to", (row.to / scale).toFixed(4));
      b.appendChild(el("span", "step-name", row.name));
      var val = el("span", "step-val", row.val);
      b.appendChild(val);
      var track = el("span", "step-track");
      track.setAttribute("aria-hidden", "true");
      var bar = el("span", "step-bar");
      bar.style.setProperty("--d", (i * 0.07).toFixed(2) + "s");
      track.appendChild(bar);
      if (row.range) {
        var rg = el("span", "step-range");
        rg.style.setProperty("--lo", (r.low / scale).toFixed(4));
        rg.style.setProperty("--hi", (r.high / scale).toFixed(4));
        track.appendChild(rg);
      }
      b.appendChild(track);
      b.addEventListener("click", function () {
        selectedStep = i;
        showWhy(i);
      });
      chart.appendChild(b);
    });
    chart.appendChild(why);
    showWhy(selectedStep);
    if (wrapEl && !wrapEl.getAttribute("data-shown")) {
      wrapEl.classList.add("is-before");
      wrapEl.setAttribute("data-shown", "true");
      onReveal(wrapEl, function () {
        later(function () {
          wrapEl.classList.remove("is-before");
        });
      });
    }
  }

  // ------------------------------------------------------------------ chapter 4
  function dots(id, rate, label) {
    var box = document.getElementById(id);
    if (!box) return;
    clear(box);
    var bad = Math.round(rate * 1000);
    box.setAttribute("aria-label", label + ": " + bad + " of every 1,000 dollars of savings rest on wrong matches");
    // The false dollars fill in from the top-left, one row after another.
    for (var i = 0; i < 1000; i++) {
      var d = el("i");
      if (i < bad) {
        d.className = "bad";
        d.style.setProperty("--d", (i * 0.004).toFixed(3) + "s");
      }
      box.appendChild(d);
    }
    box.classList.add("is-before");
    onReveal(box, function () {
      later(function () {
        box.classList.remove("is-before");
      });
    });
  }

  function trust() {
    var m = TIEOUT.scorecard.metrics;
    bind("seed", String(TIEOUT.scorecard.held_out_seed));
    var fsr = m.false_savings_rate;
    if (fsr) {
      bind("fsr-baseline", "$" + Math.round(fsr.baseline * 1000));
      bind("fsr-tool", "$" + Math.round(fsr.tool * 1000));
      dots("dots-baseline", fsr.baseline, "The usual quick method");
      dots("dots-tool", fsr.tool, "Tie-Out");
    }
    var list = document.getElementById("vs-list");
    if (list) {
      [
        ["item_precision", "When it says two items are the same, how often is it right?"],
        ["unit_error_catch_rate", "Of the unit and pack-size traps hidden in the data, how many does it catch?"],
        ["vendor_precision", "When it says two suppliers are one company, how often is it right?"]
      ].forEach(function (q) {
        var metric = m[q[0]];
        if (!metric) return;
        var li = el("li");
        li.appendChild(el("p", "vs-q", q[1]));
        [["tool", "Tie-Out", metric.tool], ["base", "Usual method", metric.baseline]].forEach(function (s) {
          var row = el("div", "vs-row " + s[0]);
          row.appendChild(el("span", "who", s[1]));
          var bar = el("span", "bar");
          var fill = el("i");
          fill.style.setProperty("--w", (s[2] * 100).toFixed(1) + "%");
          bar.appendChild(fill);
          row.appendChild(bar);
          // Never round up to a perfect score: 99.6 stays 99.6, not 100.
          var per = s[2] * 100;
          var shown = Math.round(per) === 100 && per < 100 ? per.toFixed(1) : String(Math.round(per));
          row.appendChild(el("span", "n", shown + " in 100"));
          li.appendChild(row);
        });
        list.appendChild(li);
      });
      list.classList.add("is-before");
      onReveal(list, function () {
        later(function () {
          list.classList.remove("is-before");
        });
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
        var metric = m[k];
        if (!metric) return;
        var tr = el("tr");
        var target = metric.target === null ? "none" : metric.direction.replace("<=", "≤").replace(">=", "≥") + " " + pct(metric.target);
        [names[k], pct(metric.tool), pct(metric.baseline), target].forEach(function (s, i) {
          var c = el(i === 0 ? "th" : "td", null, s);
          if (i === 0) c.scope = "row";
          else {
            c.className = "num" + (i === 1 ? " strong" : "");
            c.setAttribute("data-label", ["Tie-Out", "Naive", "Target"][i - 1]);
          }
          tr.appendChild(c);
        });
        body.appendChild(tr);
      });
    }
  }

  // ------------------------------------------------------------------ what you get
  function sheet(sample) {
    var grid = document.getElementById("sheet-grid");
    if (!grid) return;
    clear(grid);
    var r = sample.defensible_recurring;
    var l1 = sample.lever1.defensible;
    var removed = sample.naive - l1;
    var rows = [
      ["Quick estimate (for contrast)", money1(sample.naive), ""],
      ["Removed by the seven checks", "−" + money1(removed), "neg"],
      ["Price savings that hold up", money1(l1), ""],
      ["+ Buying in bulk", "+" + money1(Math.max(0, r.base - l1)), ""],
      ["Defensible yearly saving", money1(r.base), "hl"],
      ["Low to high range", rangeText(r.low, r.high), ""],
      ["Tie-out check", "OK", "ok"]
    ];
    rows.forEach(function (row, i) {
      grid.appendChild(el("span", "rn", String(i + 2)));
      grid.appendChild(el("span", row[2] === "hl" ? "hl" : "", row[0]));
      grid.appendChild(el("span", "v " + row[2], row[1]));
    });
  }

  // ------------------------------------------------------------------ samples
  function show(index) {
    current = index;
    var sample = samples[index];
    bind("sample", sample.label);
    bind("sample-number", String(index + 1));
    bind("sample-count", String(samples.length));
    headline(sample);
    meter(sample);
    overlap(sample);
    renderTie();
    bridge(sample);
    sheet(sample);
    setAttr('[data-asset="workbook"]', "href", sample.assets.workbook);
    setAttr('[data-asset="deck"]', "href", sample.assets.deck);
    setAttr('[data-asset="bridge"]', "href", sample.assets.bridge);
    setAttr('img[data-asset="bridge"]', "src", sample.assets.bridge);
  }

  // A random sample on every visit (or ?sample=<id>), then "Show another sample" walks
  // through the rest in order, so every sample is seen before one repeats.
  var start = Math.floor(Math.random() * samples.length);
  var asked = /[?&]sample=([\w-]+)/.exec(window.location.search);
  if (asked) {
    samples.forEach(function (s, i) {
      if (s.id === asked[1]) start = i;
    });
  }
  setupTie();
  trust();
  show(start);

  var next = document.getElementById("next-sample");
  if (next && samples.length > 1) {
    var swapping = false;
    next.addEventListener("click", function () {
      if (swapping) return;
      var to = (current + 1) % samples.length;
      if (reduced) return show(to);
      swapping = true;
      var fading = document.querySelectorAll(".swaps");
      for (var i = 0; i < fading.length; i++) fading[i].classList.add("is-leaving");
      window.setTimeout(function () {
        show(to);
        for (var j = 0; j < fading.length; j++) fading[j].classList.remove("is-leaving");
        swapping = false;
      }, 220);
    });
  } else if (next) {
    next.hidden = true;
  }
})();
