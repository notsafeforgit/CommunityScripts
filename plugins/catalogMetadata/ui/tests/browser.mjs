// Run against a Stash checkout with ui/v3 dependencies installed.
// STASH_UI_ROOT=/path/to/stash/ui/v3 node plugins/catalogMetadata/ui/tests/browser.mjs
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { mkdtemp, readFile, writeFile, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const host = process.env.STASH_UI_ROOT;
if (!host)
  throw new Error("Set STASH_UI_ROOT to a Stash ui/v3 checkout with dependencies installed");
const requireHost = createRequire(path.join(host, "package.json"));
const { createServer } = await import(pathToFileURL(requireHost.resolve("vite")).href);
const { default: tailwindcss } = await import(
  pathToFileURL(requireHost.resolve("@tailwindcss/vite")).href
);
const { chromium, expect } = requireHost("@playwright/test");
const here = path.dirname(fileURLToPath(import.meta.url));
const fixture = await mkdtemp(path.join(host, "node_modules/.catalog-review-test-"));
let server, browser, page;
try {
  const source = (await readFile(path.join(here, "fixture.jsx"), "utf8"))
    .replace("__CATALOG_ENTRY__", path.resolve(here, "../index.js"))
    .replaceAll("../src/", `${host}/src/`)
    .replace("../tests/browser/fixture/style.css", `${host}/tests/browser/fixture/style.css`);
  await writeFile(path.join(fixture, "fixture.jsx"), source);
  await writeFile(
    path.join(fixture, "index.html"),
    '<html lang="en"><head><meta name="viewport" content="width=device-width, initial-scale=1"></head><body><div id="root"></div><script type="module" src="./fixture.jsx"></script></body></html>',
  );
  server = await createServer({
    configFile: false,
    root: fixture,
    base: "/stash/",
    plugins: [tailwindcss()],
    resolve: { alias: { "@": path.join(host, "src"), src: path.join(host, "src") } },
    server: {
      host: "127.0.0.1",
      port: 3028,
      strictPort: true,
      fs: { allow: [host, path.resolve(here, "..")] },
    },
  });
  await server.listen();
  browser = await chromium.launch({ headless: true });
  page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("http://127.0.0.1:3028/stash/catalogMetadata/review?fail-list");
  await expect(page.getByText("Could not load catalog reviews")).toBeVisible();
  await page.getByRole("button", { name: "Retry", exact: true }).click();
  await expect(page.getByRole("link", { name: "Plugin settings", exact: true })).toHaveAttribute(
    "href",
    "/stash/settings/plugins",
  );
  await page.getByRole("button", { name: "Review account", exact: true }).click();
  await expect(page.getByText("Multiple performers match this account.")).toBeVisible();
  const picker = page.getByRole("combobox", { name: "Stash performer" });
  await picker.fill("Second person");
  await page.getByRole("option", { name: /Sam \(Second person\)/ }).click();
  await page.getByRole("button", { name: "Preview link", exact: true }).click();
  await expect(page.getByRole("region", { name: "Proposed changes" })).toContainText(
    "reddit:id:t2_20",
  );
  assert.equal(
    await page.evaluate(
      () => window.reviewRequests.filter((r) => r.name === "PluginMutationV3").length,
    ),
    0,
  );
  await page.getByRole("button", { name: "Apply reviewed link" }).click();
  await expect(
    page.getByText("The review is out of date. Preview again before applying."),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply reviewed link" })).toHaveCount(0);
  await page.getByRole("button", { name: "Preview link", exact: true }).click();
  await page.getByRole("button", { name: "Apply reviewed link" }).click();
  await expect(page.getByText("Linked 2 accounts and merged 1 catalogs.")).toBeVisible();
  assert.equal(
    await page.evaluate(
      () => window.reviewRequests.filter((r) => r.name === "PluginMutationV3").length,
    ),
    2,
  );
  assert.ok(
    await page.evaluate(() =>
      window.reviewRequests.every((r) => r.plugin_id === "catalogMetadata"),
    ),
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("http://127.0.0.1:3028/stash/catalogMetadata/review?dry");
  await page.getByRole("button", { name: "Review account", exact: true }).click();
  await picker.fill("Second person");
  await page.getByRole("option", { name: /Sam \(Second person\)/ }).click();
  await page.getByRole("button", { name: "Preview link", exact: true }).click();
  await expect(page.getByRole("button", { name: "Apply reviewed link" })).toBeDisabled();
  assert.ok(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1),
    "Mobile page overflows",
  );
  await page.screenshot({ path: "/tmp/catalog-review-mobile.png", fullPage: true });
  await picker.fill("First person");
  await page.getByRole("option", { name: /Sam \(First person\)/ }).click();
  await expect(page.getByRole("region", { name: "Proposed changes" })).toHaveCount(0);
  assert.equal(
    await page.evaluate(
      () => window.reviewRequests.filter((r) => r.name === "PluginMutationV3").length,
    ),
    0,
  );
  assert.deepEqual(errors, []);
  console.log(
    "Catalog review browser checks passed: shared host, evidence, explicit apply, retry, stale preview, dry run, mobile, base path.",
  );
} catch (error) {
  if (page) {
    await page.screenshot({ path: "/tmp/catalog-review-failure.png", fullPage: true });
    console.error(
      await page.evaluate(() => ({
        styles: [...document.styleSheets].map((s) => s.href),
        scroll: [
          ...document.querySelectorAll(".catalog-review-scroll, .catalog-review-layout"),
        ].map((e) => ({
          element: e.className,
          height: e.clientHeight,
          scrollHeight: e.scrollHeight,
          overflow: getComputedStyle(e).overflowY,
          display: getComputedStyle(e).display,
        })),
      })),
    );
  }
  throw error;
} finally {
  await browser?.close();
  await server?.close();
  await rm(fixture, { recursive: true, force: true });
}
