/* FoodSafe Central - jsdom boot + interaction verification.
 *
 * Loads the BAKED index.html with scripts enabled and a stubbed canvas, then asserts
 * the render path actually works with real data: baked payload, stat tiles, ≥1 card,
 * every card index resolving to a record, search / agency / region / quick filters
 * narrowing results AND moving the timeline chart, theme switching (class + persisted
 * + real computed colours), canvas bars drawn, chart empty state, the static noscript
 * snapshot, the Lil Mandalay attribution, and no boot error.
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
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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
    },
    {
      get: (t, p) => (p in t ? t[p] : noop),
      set: (t, p, v) => { t[p] = v; return true; },
    }
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

const set = (sel, val, evt) => {
  const el = d.querySelector(sel);
  el.value = val;
  el.dispatchEvent(new w.Event(evt || "change", { bubbles: true }));
};
const chip = (k) => d.querySelector(`[data-quick='${k}']`).dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
const cards = () => [...d.querySelectorAll("#list .card")];
const switchTheme = (t) => d.querySelector(`[data-theme='${t}']`).dispatchEvent(new w.MouseEvent("click", { bubbles: true }));

(async () => {
  await sleep(500);
  try {
    // 1. payload baked + global lexical binding present
    const n = w.eval('typeof RECALLS_DATA !== "undefined" && RECALLS_DATA && RECALLS_DATA.recalls ? RECALLS_DATA.recalls.length : 0');
    const meta = w.eval("RECALLS_DATA.meta");
    ok(n > 1000, `baked payload present (${n} recalls)`);
    ok(meta.by_agency.FDA > 0, `meta.by_agency.FDA = ${meta.by_agency.FDA}`);
    ok(meta.by_agency["USDA FSIS"] > 0, `meta.by_agency.USDA FSIS = ${meta.by_agency["USDA FSIS"]}`);
    ok(!("null" in meta.by_hazard), `no null hazard bucket in meta (${JSON.stringify(meta.by_hazard)})`);

    // 2. stat tiles + header pills populated (not the "–" placeholder)
    const stats = ["#sActive", "#sNew", "#sFda", "#sUsda", "#cActive", "#cTotal", "#cNew", "#cUsda"].map((s) => (d.querySelector(s) || {}).textContent);
    ok(stats.every((t) => t && t !== "–" && t !== ""), "all stat tiles + header pills filled: " + stats.join("/"));
    ok(/\d{4}/.test((d.querySelector("#cUpdated") || {}).textContent || ""), `freshness date rendered: ${d.querySelector("#cUpdated").textContent}`);

    // 3. cards rendered, every card index resolves to a record
    ok(cards().length > 0, `cards rendered (${cards().length})`);
    const badIdx = cards().filter((c) => !Number.isInteger(Number(c.dataset.i)) || !w.eval(`RECALLS_DATA.recalls[${Number(c.dataset.i)}]`));
    ok(badIdx.length === 0, `every card index resolves to a record (${badIdx.length} bad of ${cards().length})`);
    ok(!/>\s*<script/i.test(cards().map((c) => c.innerHTML).join("")), "no unescaped script leakage in rendered cards");

    // 4. detail sheet
    cards()[0].dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    const sheet = d.querySelector("#sheet");
    ok(d.querySelector("#ov").classList.contains("open"), "card click opens the detail overlay");
    ok(/view official notice/.test(sheet.textContent) && /https?:\/\//.test(sheet.innerHTML), "detail sheet links to the official notice");
    ok(/Lil Mandalay/.test(d.querySelector("footer").textContent), "attribution present in footer");
    ok(/🤗/.test(d.querySelector("footer").textContent) && /💚|❤|🧡|💖/.test(d.querySelector("footer").textContent), "hug + heart emojis present in attribution");
    d.querySelector(".close").dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    ok(!d.querySelector("#ov").classList.contains("open"), "detail overlay closes");

    // 5. search-by-brand narrows
    const total = cards().length;
    const brand = w.eval("(RECALLS_DATA.recalls.find(r => r.product.brand_name && r.product.brand_name.length > 4) || {}).product.brand_name");
    set("#q", brand, "input");
    await sleep(200);
    const afterSearch = cards().length;
    ok(afterSearch > 0 && afterSearch <= total, `search by brand "${brand}" narrows cards (${total} -> ${afterSearch})`);

    // 6. agency filter (clear search so this is a real filter test)
    set("#q", "", "input");
    set("#agency", "USDA FSIS");
    await sleep(200);
    const usda = cards();
    ok(usda.length > 0 && usda.every((c) => /USDA FSIS/.test(c.textContent)), `USDA filter shows only USDA FSIS cards (${usda.length})`);
    ok(d.querySelector("#chSub").textContent.indexOf("USDA FSIS") >= 0, `timeline subtitle follows the agency filter (${JSON.stringify(d.querySelector("#chSub").textContent)})`);

    // 6b. the four top stat tiles are clickable filters, kept in sync with selects + chips
    const tiles = [...d.querySelectorAll("[data-stat]")];
    const pressed = () => Object.fromEntries(tiles.map((t) => [t.dataset.stat, t.getAttribute("aria-pressed")]));
    const clickTile = (k) => d.querySelector(`[data-stat='${k}']`).dispatchEvent(new w.MouseEvent("click", { bubbles: true }));
    ok(tiles.length === 4, `four stat tiles present (${tiles.length})`);
    ok(tiles.every((t) => t.tagName === "BUTTON" && t.getAttribute("type") === "button"), "stat tiles are real <button type=button> elements");
    chip("reset");
    await sleep(250);
    ok(JSON.stringify(pressed()) === JSON.stringify({ active: "true", recent7: "false", fda: "false", usda: "false" }),
      `default tile state mirrors the default filters: ${JSON.stringify(pressed())}`);

    clickTile("fda");
    await sleep(250);
    ok(d.querySelector("#agency").value === "FDA", "FDA tile drives the agency select (tile -> select sync)");
    ok(pressed().fda === "true" && pressed().usda === "false", `FDA tile presses and USDA releases: ${JSON.stringify(pressed())}`);
    ok(cards().length > 0 && cards().every((c) => /FDA/.test(c.textContent)), `FDA tile scopes the list to FDA (${cards().length})`);
    ok(d.querySelector("#chSub").textContent.indexOf("FDA") >= 0, `timeline follows the FDA tile (${JSON.stringify(d.querySelector("#chSub").textContent)})`);

    set("#agency", "USDA FSIS");
    await sleep(250);
    ok(pressed().usda === "true" && pressed().fda === "false", `select drives the tiles back the other way: ${JSON.stringify(pressed())}`);
    ok(cards().every((c) => /USDA FSIS/.test(c.textContent)), `USDA tile agrees with the select (${cards().length} cards)`);

    clickTile("usda");
    await sleep(250);
    ok(d.querySelector("#agency").value === "", "clicking the pressed tile again clears the agency filter");

    clickTile("recent7");
    await sleep(250);
    ok(pressed().recent7 === "true", "last-7-days tile presses");
    ok(d.querySelector("[data-quick='week']").getAttribute("aria-pressed") === "true", "7-day tile lights the matching quick chip (tile -> chip sync)");
    ok(d.querySelector("#chSub").textContent.indexOf("last 7 days") >= 0, `timeline follows the 7-day tile (${JSON.stringify(d.querySelector("#chSub").textContent)})`);
    ok(d.querySelector("#countLine").textContent.indexOf("last 7 days") >= 0, `count line follows the 7-day tile (${JSON.stringify(d.querySelector("#countLine").textContent)})`);
    clickTile("recent7");
    await sleep(250);
    ok(pressed().recent7 === "false" && d.querySelector("[data-quick='week']").getAttribute("aria-pressed") === "false", "7-day tile toggles back off and clears the chip");

    const activeCount = cards().length;
    clickTile("active");
    await sleep(250);
    ok(d.querySelector("#status").value === "", "Active tile un-press flips the status select to all statuses");
    ok(pressed().active === "false", "Active tile shows unpressed while showing all statuses");
    ok(cards().length >= activeCount, `all-statuses view is >= the active-only view (${activeCount} -> ${cards().length})`);
    clickTile("active");
    await sleep(250);
    ok(d.querySelector("#status").value === "ACTIVE" && pressed().active === "true", "clicking the Active tile again restores active-only");

    chip("reset");
    await sleep(250);
    ok(JSON.stringify(pressed()) === JSON.stringify({ active: "true", recent7: "false", fda: "false", usda: "false" }),
      `reset restores the default tile state: ${JSON.stringify(pressed())}`);
    ok(d.querySelector("#chSub").textContent.indexOf("FDA") < 0 && d.querySelector("#chSub").textContent.indexOf("USDA") < 0, "reset also clears the tile scope from the timeline");

    // 7. REGION filter must move the timeline chart, not just the list
    chip("reset");
    await sleep(250);
    const regionSel = d.querySelector("#state");
    const region = [...regionSel.options].map((o) => o.value).filter((v) => v && v !== "NATIONWIDE")[0];
    const before = drawCalls.fillRect;
    set("#state", region);
    await sleep(250);
    const sub = d.querySelector("#chSub").textContent;
    ok(sub.indexOf(region) >= 0, `timeline subtitle names the region (${JSON.stringify(sub)})`);
    ok(/\d+ recalls/.test(sub), "timeline subtitle still reports a count");
    ok(drawCalls.fillRect > before, `timeline redrew after the region filter (fillRect ${before} -> ${drawCalls.fillRect})`);
    const rc = cards();
    ok(rc.length > 0 && rc.every((c) => c.textContent.indexOf(region) >= 0 || /Nationwide/.test(c.textContent)), `region filter scopes cards to ${region} (${rc.length})`);
    ok(d.querySelector("#countLine").textContent.indexOf(region) >= 0, `count line names the region (${JSON.stringify(d.querySelector("#countLine").textContent)})`);
    ok(d.querySelector("#state").value === region, `region select stays on ${region}`);

    // 7b. reset clears the scope from the chart again
    chip("reset");
    await sleep(250);
    ok(d.querySelector("#chSub").textContent.indexOf(region) < 0, `reset clears the region from the timeline subtitle (${JSON.stringify(d.querySelector("#chSub").textContent)})`);

    // 7c. empty scope -> chart empty state, not a blank axis
    set("#q", "zzzznomatchzzzz", "input");
    await sleep(250);
    ok(/0 recalls/.test(d.querySelector("#chSub").textContent), `empty scope reported (${JSON.stringify(d.querySelector("#chSub").textContent)})`);
    ok(drawCalls.fillText > 0, "empty-state chart still draws its message");
    set("#q", "", "input");
    await sleep(200);
    ok(!/zzzznomatchzzzz/.test(d.querySelector("#chSub").textContent), "clearing the search restores the chart scope label");

    // 8. quick chip: Class I
    chip("class1");
    await sleep(250);
    const c1 = cards();
    ok(c1.length > 0 && c1.every((c) => /Class I|Class n\/a/.test(c.textContent)), `Class I quick filter applied (${c1.length} cards)`);
    ok(d.querySelector("[data-quick='class1']").getAttribute("aria-pressed") === "true", "quick chip reflects pressed state");
    ok(d.querySelector("#chSub").textContent.indexOf("Class I") >= 0, `timeline subtitle follows the Class I quick chip (${JSON.stringify(d.querySelector("#chSub").textContent)})`);
    chip("class1");
    await sleep(200);

    // 9. theme switching
    switchTheme("chartreuse");
    ok(/theme-chartreuse/.test(d.documentElement.className), "chartreuse theme applied: " + d.documentElement.className);
    ok(w.localStorage.getItem("foodsafe-theme") === "chartreuse", "theme persisted to localStorage");
    ok(d.querySelector("[data-theme='chartreuse']").getAttribute("aria-pressed") === "true", "active swatch marked pressed");
    ["pantry", "paper", "berry"].forEach((t) => {
      switchTheme(t);
      ok(new RegExp("theme-" + t).test(d.documentElement.className), `theme ${t} applies`);
    });

    // 9b. each theme really re-colours the page (computed custom properties)
    const expect = { pantry: "#58a6ff", chartreuse: "#d4ff00", paper: "#1f6feb", berry: "#ff6ec7" };
    const seen = {};
    Object.keys(expect).forEach((t) => {
      d.documentElement.className = "theme-" + t;
      const cs = w.getComputedStyle(d.documentElement);
      seen[t] = cs.getPropertyValue("--accent").trim();
      ok(seen[t] === expect[t], `theme ${t} accent = ${seen[t]} (expected ${expect[t]})`);
      ok(cs.getPropertyValue("--bg").trim() && cs.getPropertyValue("--text").trim(), `theme ${t} defines bg + text colours`);
    });
    ok(new Set(Object.values(seen)).size === 4, `all 4 themes use distinct accents: ${JSON.stringify(seen)}`);
    ok(/^#d4ff00$/.test(seen.chartreuse), `chartreuse is really chartreuse (${seen.chartreuse})`);
    d.documentElement.className = "theme-chartreuse";

    // 10. chart drew bars + labels
    ok(drawCalls.fillRect >= 12, `timeline drew bars (fillRect=${drawCalls.fillRect})`);
    ok(drawCalls.fillText >= 15, `timeline drew axis/month/value labels (fillText=${drawCalls.fillText})`);

    // 11. static no-JS snapshot (inside <noscript> => raw text when scripting is on)
    ok(/<noscript>[\s\S]*Recall snapshot[\s\S]*<\/noscript>/.test(html), "static snapshot wrapped in <noscript>");
    ok(/Recall snapshot — no JavaScript required/.test(html) && /fsis\.usda\.gov\/recalls/.test(html), "snapshot carries counts + official FSIS link");
    ok(/__SUMMARY_START__/.test(html) && /__SUMMARY_END__/.test(html) && /__DATA_START__/.test(html), "bake markers preserved (re-bakeable)");

    // 12. boot errors
    ok(!w.__bootErr, "no boot error thrown" + (w.__bootErr ? ": " + w.__bootErr : ""));
    ok(consoleErrors.length === 0, "no jsdom console errors" + (consoleErrors.length ? ": " + consoleErrors.join(" | ") : ""));

    console.log(info.join("\n"));
    if (fails.length) {
      console.log("\n" + fails.join("\n"));
      console.log(`\nRESULT: FAIL (${fails.length} failed, ${info.length} passed)`);
      process.exit(1);
    }
    console.log(`\nRESULT: PASS (${info.length} checks)`);
  } catch (e) {
    console.log(info.join("\n"));
    console.log("\n" + fails.join("\n"));
    console.log("FATAL: " + (e && e.stack || e));
    process.exit(1);
  }
})();
