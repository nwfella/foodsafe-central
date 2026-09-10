/* FoodSafe Central - jsdom boot + interaction verification.
 *
 * Loads the BAKED index.html with scripts enabled and a stubbed canvas, then
 * asserts the render path actually works with real data: baked payload present,
 * stat tiles filled, ≥1 card, every card index resolves to a record, search and
 * quick-filter narrow results, theme switch swaps the class + persists, the
 * timeline chart drew bars, and no boot error was thrown.
 *
 * Usage:  npm i -D jsdom  &&  node scripts/verify_site.js
 * Exit code 0 = pass.
 */
const fs = require("fs");
const path = require("path");
const { JSDOM, VirtualConsole } = require("jsdom");

const file = path.resolve(__dirname, "..", "index.html");
const html = fs.readFileSync(file, "utf8");
const fails = [];
const info = [];
const ok = (cond, msg) => (cond ? info.push("  ok   " + msg) : fails.push("  FAIL " + msg));

// ---- stub canvas 2d context (jsdom has no canvas without the native pkg) ----
const drawCalls = { fillRect: 0, fillText: 0, beginPath: 0, clearRect: 0 };
function stubCtx() {
  const noop = () => {};
  return new Proxy(
    {
      fillRect: () => drawCalls.fillRect++,
      fillText: () => drawCalls.fillText++,
      beginPath: () => drawCalls.beginPath++,
      clearRect: () => drawCalls.clearRect++,
      moveTo: noop, lineTo: noop, stroke: noop, fill: noop, setTransform: noop, arc: noop, closePath: noop,
      createLinearGradient: () => ({ addColorStop() {} }),
      measureText: () => ({ width: 10 }),
      getImageData: () => ({ data: new Uint8ClampedArray(8) }),
      set fillStyle(v) {}, get fillStyle() { return "#000"; },
      set strokeStyle(v) {}, get strokeStyle() { return "#000"; },
      set font(v) {}, get font() { return "10px sans-serif"; },
      set lineWidth(v) {}, get lineWidth() { return 1; },
      set textAlign(v) {}, get textAlign() { return "left"; },
      set textBaseline(v) {}, get textBaseline() { return "top"; },
    },
    { get: (t, p) => (p in t ? t[p] : noop) }
  );
}

const vc = new VirtualConsole();
const consoleErrors = [];
vc.on("jsdomError", (e) => consoleErrors.push(String(e && e.message)));
vc.on("error", (m) => consoleErrors.push(String(m)));

const dom = new JSDOM(html, {
  runScripts: "dangerously",
  pretendToBeVisual: true,
  url: "https://nwfella.github.io/foodsafe-central/",
  virtualConsole: vc,
  beforeParse(window) {
    window.HTMLCanvasElement.prototype.getContext = function () { return stubCtx(); };
    window.matchMedia = window.matchMedia || (() => ({ matches: false, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {} }));
    window.__bootErr = null;
    window.addEventListener("error", (e) => { window.__bootErr = (e && (e.error && e.error.stack || e.message)) || "error"; });
    const store = {};
    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); }, removeItem: (k) => { delete store[k]; }, clear: () => {} },
    });
  },
});
const w = dom.window;
const d = w.document;

setTimeout(() => {
  try {
    // 1. payload baked + global lexical binding present
    const hasData = w.eval('typeof RECALLS_DATA !== "undefined" && RECALLS_DATA && RECALLS_DATA.recalls ? RECALLS_DATA.recalls.length : 0');
    ok(hasData > 1000, `baked payload present (${hasData} recalls)`);
    const meta = w.eval('RECALLS_DATA.meta');
    ok(meta && meta.by_agency && meta.by_agency.FDA > 0, `meta.by_agency.FDA = ${meta && meta.by_agency && meta.by_agency.FDA}`);
    ok(meta && meta.by_agency && meta.by_agency["USDA FSIS"] > 0, `meta.by_agency.USDA FSIS = ${meta && meta.by_agency && meta.by_agency["USDA FSIS"]}`);

    // 2. stat tiles + header pills populated (not the "–" placeholder)
    const stats = ["#sActive", "#sNew", "#sFda", "#sUsda", "#cActive", "#cTotal", "#cNew", "#cUsda"].map((s) => (d.querySelector(s) || {}).textContent);
    ok(stats.every((t) => t && t !== "–" && t !== ""), "all stat tiles + header pills filled: " + stats.join("/"));
    ok(/\d{4}/.test((d.querySelector("#cUpdated") || {}).textContent || ""), "freshness date rendered: " + (d.querySelector("#cUpdated") || {}).textContent);

    // 3. cards rendered, and every card's index resolves to a record
    const cards = [...d.querySelectorAll("#list .card")];
    ok(cards.length > 0, `cards rendered (${cards.length})`);
    const badIdx = cards.filter((c) => {
      const i = Number(c.dataset.i);
      const r = w.eval(`RECALLS_DATA.recalls[${i}]`);
      return !Number.isInteger(i) || !r;
    });
    ok(badIdx.length === 0, `every card index resolves to a record (${badIdx.length} bad of ${cards.length})`);

    // 4. no angle-bracket leakage from unescaped fields
    ok(!/&lt;script|>\s*<script/i.test(cards.map((c) => c.innerHTML).join("")), "no unescaped script leakage in rendered cards");

    // 5. card click opens the detail sheet with the official link
    const first = cards[0];
    first.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    const sheet = d.querySelector("#sheet");
    ok(d.querySelector("#ov").classList.contains("open"), "card click opens the detail overlay");
    ok(/view official notice/.test(sheet.textContent) && /https?:\/\//.test(sheet.innerHTML), "detail sheet links to the official notice");
    ok(/Lil Mandalay/.test(d.querySelector("footer").textContent), "attribution present in footer");
    ok(/🤗/.test(d.querySelector("footer").textContent) && /💚|❤|🧡|💖/.test(d.querySelector("footer").textContent), "hug + heart emojis present in attribution");
    d.querySelector(".close").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    ok(!d.querySelector("#ov").classList.contains("open"), "detail overlay closes");

    // 6. search narrows results (search-as-you-type)
    const total = d.querySelectorAll("#list .card").length;
    const brand = w.eval('(RECALLS_DATA.recalls.find(r => r.product.brand_name && r.product.brand_name.length > 4) || {}).product.brand_name');
    const q = d.querySelector("#q");
    q.value = brand;
    q.dispatchEvent(new w.Event("input", { bubbles: true }));
    const afterSearch = w.eval("new Promise(res => setTimeout(() => res(document.querySelectorAll('#list .card').length), 150))");
    afterSearch.then((n) => {
      ok(n > 0 && n <= total, `search by brand "${brand}" narrows cards (${total} -> ${n})`);

      // 7. agency filter -> USDA only (clear the search first so this is a real filter test)
      d.querySelector("#q").value = "";
      d.querySelector("#q").dispatchEvent(new w.Event("input", { bubbles: true }));
      d.querySelector("#agency").value = "USDA FSIS";
      d.querySelector("#agency").dispatchEvent(new w.Event("change", { bubbles: true }));
      setTimeout(() => {
        const usdaCards = [...d.querySelectorAll("#list .card")];
        const usdaOk = usdaCards.length > 0 && usdaCards.every((c) => /USDA FSIS/.test(c.textContent));
        ok(usdaOk, `USDA filter shows only USDA FSIS cards (${usdaCards.length})`);

        // 8. quick chip: Class I
        d.querySelector("[data-quick='reset']").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
        setTimeout(() => {
          d.querySelector("[data-quick='class1']").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
          setTimeout(() => {
            const c1 = [...d.querySelectorAll("#list .card")];
            ok(c1.length > 0 && c1.every((c) => /Class I|FSIS/.test(c.textContent)), `Class I quick filter applied (${c1.length} cards)`);
            ok(d.querySelector("[data-quick='class1']").getAttribute("aria-pressed") === "true", "quick chip reflects pressed state");

            // 9. theme switching
            const sw = d.querySelector("[data-theme='chartreuse']");
            sw.dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
            ok(/theme-chartreuse/.test(d.documentElement.className), "chartreuse theme applied: " + d.documentElement.className);
            ok(w.localStorage.getItem("foodsafe-theme") === "chartreuse", "theme persisted to localStorage");
            ok(sw.getAttribute("aria-pressed") === "true", "active swatch marked pressed");
            ["pantry", "paper", "berry"].forEach((t) => {
              d.querySelector(`[data-theme='${t}']`).dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
              ok(new RegExp("theme-" + t).test(d.documentElement.className), `theme ${t} applies`);
            });

            // 10. chart drew bars + labels + value labels
            ok(drawCalls.fillRect >= 12, `timeline drew bars (fillRect=${drawCalls.fillRect})`);
            ok(drawCalls.fillText >= 15, `timeline drew axis/month/value labels (fillText=${drawCalls.fillText})`);

            // 11. static no-JS summary baked
            const ns = d.querySelector(".noscript");
            ok(/Recall snapshot/.test(ns.textContent) && /<a href="https:\/\/www\./.test(ns.innerHTML), "static noscript summary baked with official links");

            // 12. boot errors
            ok(!w.__bootErr, "no boot error thrown" + (w.__bootErr ? ": " + w.__bootErr : ""));
            ok(consoleErrors.length === 0, "no jsdom console errors" + (consoleErrors.length ? ": " + consoleErrors.join(" | ") : ""));

            console.log(info.join("\n"));
            if (fails.length) {
              console.log("\n" + fails.join("\n"));
              console.log(`\nRESULT: FAIL (${fails.length} checks failed, ${info.length} passed)`);
              process.exit(1);
            }
            console.log(`\nRESULT: PASS (${info.length} checks)`);
          }, 200);
        }, 250);
      }, 250);
    });
  } catch (e) {
    console.log(info.join("\n"));
    console.log("FATAL: " + (e && e.stack || e));
    process.exit(1);
  }
}, 400);
