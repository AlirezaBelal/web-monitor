import { chromium } from "playwright";
import AxeBuilder from "@axe-core/playwright";
import assert from "node:assert/strict";
import { createServer } from "node:http";
import { readFile, writeFile, mkdir } from "node:fs/promises";
import { resolve, extname } from "node:path";
const root = resolve(process.env.QA_ROOT || "docs"),
  out = resolve(process.env.QA_OUTPUT || "evidence");
await mkdir(out, { recursive: true });
const server = createServer(async (req, res) => {
  try {
    const name = new URL(req.url, "http://localhost").pathname;
    const file = resolve(root, "." + (name === "/" ? "/index.html" : name));
    if (!file.startsWith(root)) throw Error();
    const data = await readFile(file);
    res.setHeader(
      "Content-Type",
      {
        ".html": "text/html",
        ".js": "application/javascript",
        ".css": "text/css",
        ".svg": "image/svg+xml",
      }[extname(file)] || "text/plain",
    );
    res.end(data);
  } catch {
    res.statusCode = 404;
    res.end("Not found");
  }
});
await new Promise((r) => server.listen(0, "127.0.0.1", r));
const url = process.env.QA_URL || `http://127.0.0.1:${server.address().port}/`;
const browser = await chromium.launch(),
  results = [];
try {
  for (const [width, height] of [
    [320, 700],
    [375, 812],
    [390, 844],
    [768, 1024],
    [1024, 768],
    [1440, 1000],
    [1920, 1080],
  ]) {
    const context = await browser.newContext({
        viewport: { width, height },
        reducedMotion: "reduce",
      }),
      page = await context.newPage(),
      errors = [],
      bad = [],
      external = [];
    page.on("pageerror", (e) => errors.push(e.message));
    page.on("console", (m) => {
      if (m.type() === "error") errors.push(m.text());
    });
    page.on("response", (r) => {
      if (r.status() >= 400) bad.push(r.url());
    });
    page.on("request", (r) => {
      if (new URL(r.url()).origin !== new URL(url).origin)
        external.push(r.url());
    });
    await page.goto(url, { waitUntil: "networkidle" });
    assert.equal(await page.locator(".target").count(), 3);
    await page.keyboard.press("Tab");
    assert.equal(
      await page.locator(":focus").textContent(),
      "Skip to main content",
    );
    await page.keyboard.press("Enter");
    assert.equal(await page.locator(":focus").getAttribute("id"), "top");
    await page.locator("#before").focus();
    await page.keyboard.press("Tab");
    assert.equal(await page.locator(":focus").getAttribute("id"), "after");
    await page.keyboard.press("Tab");
    assert.equal(await page.locator(":focus").getAttribute("id"), "compare");
    assert(
      await page
        .locator(":focus")
        .evaluate((e) => getComputedStyle(e).outlineStyle !== "none"),
    );
    await page.keyboard.press("Enter");
    assert.match(
      await page.locator("#comparison-status").textContent(),
      /^Changed/,
    );
    await page.locator("#before").fill(" A\nB ");
    await page.locator("#after").fill("A B");
    await page.locator("#compare").click();
    assert.match(
      await page.locator("#comparison-status").textContent(),
      /^Equivalent/,
    );
    await page.locator("#clear").click();
    await page.locator("#compare").click();
    assert.equal(await page.locator(":focus").getAttribute("id"), "before");
    assert.equal(
      await page.locator("#before").getAttribute("aria-invalid"),
      "true",
    );
    await page.locator("#before").fill("plain");
    await page.locator("#after").fill('<img src=x onerror="alert(1)">');
    await page.locator("#compare").click();
    assert.equal(await page.locator("#difference img").count(), 0);
    assert.match(await page.locator("#added").textContent(), /<img/);
    await page.locator("#before").evaluate((e) => {
      e.value = "x".repeat(20001);
      e.dispatchEvent(new Event("input"));
    });
    await page.locator("#compare").click();
    assert.match(
      await page.locator("#comparison-status").textContent(),
      /at most 20,000/,
    );
    await page.locator("#restore").click();
    await page.locator("#compare").click();
    async function cycle(n) {
      await page.locator("#run").click();
      await page.waitForFunction(
        (n) =>
          document
            .querySelector("#cycle-state")
            .textContent.startsWith(`Cycle ${n} complete`),
        n,
      );
    }
    await cycle(1);
    assert.equal(await page.locator(".event.changed").count(), 0);
    assert.equal(await page.locator(".event.failure").count(), 1);
    await cycle(2);
    assert.equal(await page.locator(".event.recovery").count(), 1);
    await page.locator("#filter").selectOption("changes");
    assert.equal(await page.locator(".event").count(), 0);
    assert(await page.locator("#empty").isVisible());
    await page.locator("#filter").selectOption("all");
    await cycle(3);
    assert.match(
      await page.locator(".target").nth(1).textContent(),
      /Pending retry/,
    );
    assert.match(
      await page.locator(".target").nth(1).textContent(),
      /Committed: Release 2.4/,
    );
    await cycle(4);
    assert.match(
      await page.locator(".target").nth(1).textContent(),
      /Committed: Release 2.5/,
    );
    await page.locator("#filter").selectOption("failures");
    assert.equal(await page.locator(".event").count(), 2);
    await page.locator("#filter").selectOption("recovery");
    assert.equal(await page.locator(".event").count(), 1);
    await page.locator("#reset").click();
    await page.locator("#run").evaluate((e) => {
      e.click();
      e.click();
      document.querySelector("#reset").click();
      document.querySelector("#filter").value = "changes";
      document.querySelector("#filter").dispatchEvent(new Event("change"));
    });
    await page.waitForTimeout(250);
    assert.match(await page.locator("#cycle-state").textContent(), /^Ready/);
    assert.equal(await page.locator(".event").count(), 0);
    assert.equal(await page.locator("#run").isEnabled(), true);
    await page.locator("#reset").click();
    await cycle(1);
    await cycle(2);
    await cycle(3);
    await cycle(4);
    await page.locator("summary").focus();
    await page.keyboard.press("Enter");
    assert((await page.locator("details").getAttribute("open")) !== null);
    assert(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
      "horizontal overflow " + width,
    );
    const layout = await page
      .locator("button,select,textarea,header nav a")
      .evaluateAll((xs) =>
        xs.map((e) => {
          const r = e.getBoundingClientRect();
          return {
            id: e.id || e.textContent.trim(),
            x: r.x,
            y: r.y,
            w: r.width,
            h: r.height,
            scroll: e.scrollWidth,
            client: e.clientWidth,
          };
        }),
      );
    assert(
      layout.every((e) => e.h >= 44),
      "touch height",
    );
    assert(
      layout.every((e) => e.x >= 0 && e.x + e.w <= width + 1),
      "controls outside viewport",
    );
    for (let i = 0; i < layout.length; i++)
      for (let j = i + 1; j < layout.length; j++) {
        const a = layout[i],
          b = layout[j];
        assert(
          !(
            a.x < b.x + b.w - 1 &&
            a.x + a.w > b.x + 1 &&
            a.y < b.y + b.h - 1 &&
            a.y + a.h > b.y + 1
          ),
          "overlapping controls",
        );
      }
    const axe = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
      .analyze();
    await writeFile(`${out}/axe-${width}.json`, JSON.stringify(axe, null, 2));
    assert.deepEqual(
      axe.violations.map((v) => ({
        id: v.id,
        targets: v.nodes.map((n) => n.target),
      })),
      [],
    );
    await page.locator("summary").click();
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({
      path: `${out}/product-${width}.png`,
      fullPage: true,
    });
    assert.deepEqual(errors, []);
    assert.deepEqual(bad, []);
    assert.deepEqual(external, []);
    results.push({
      width,
      height,
      url,
      axeViolations: axe.violations.length,
      keyboard: "passed",
      controls: "passed",
      interaction: "passed",
      externalRequests: external,
      consoleErrors: errors,
    });
    await context.close();
  }
} finally {
  await writeFile(`${out}/results.json`, JSON.stringify(results, null, 2));
  await browser.close();
  await new Promise((r) => server.close(r));
}
console.log(JSON.stringify(results, null, 2));
