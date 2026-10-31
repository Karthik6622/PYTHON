"""Playwright + TypeScript / JavaScript project renderer (one adapter class, two flavours)."""

from __future__ import annotations

import json
from urllib.parse import urlparse

from ats.generation.adapters.common import (
    ENV_EXAMPLE,
    ENV_PLACEHOLDER,
    GITIGNORE,
    FrameworkAdapter,
    RenderContext,
    attr_of,
    comment_safe,
    js_str,
    locators_json,
    module_slug,
    pascal,
    py_ident,
    readme,
    step_text,
)
from ats.models import AutomationStep

# ---------------------------------------------------------------- TypeScript runtime (raw strings: file text as written)
TS_LOCATORS = r"""import * as fs from 'fs';
import * as path from 'path';
import type { Locator, Page } from '@playwright/test';

export type Selector = { kind: string; value: string; name?: string; exact?: boolean };
export type LocatorSpec = { preferred: Selector } & Record<string, unknown>;

const FILE = path.join(__dirname, '..', 'config', 'locators.json');

export function loadLocators(): Record<string, LocatorSpec> {
  return JSON.parse(fs.readFileSync(FILE, 'utf-8'));
}

// No silent fallback: a stale locator must fail loudly so it can be analysed (and healed with approval).
export function resolve(page: Page, s: Selector): Locator {
  const exact = !!s.exact;
  switch (s.kind) {
    case 'testid': return page.getByTestId(s.value);
    case 'role': return s.name ? page.getByRole(s.value as any, { name: s.name, exact }) : page.getByRole(s.value as any);
    case 'label': return page.getByLabel(s.value, { exact });
    case 'placeholder': return page.getByPlaceholder(s.value, { exact });
    case 'text': return page.getByText(s.value, { exact });
    case 'id': return page.locator(`[id="${s.value.replace(/"/g, '\\"')}"]`);
    case 'name': return page.locator(`[name="${s.value.replace(/"/g, '\\"')}"]`);
    case 'xpath': return page.locator(`xpath=${s.value}`);
    default: return page.locator(s.value);
  }
}
"""

TS_APP = r"""import * as fs from 'fs';
import * as path from 'path';
import type { Locator, Page } from '@playwright/test';
import { loadLocators, resolve } from './locators';
import { Pages } from '../pages';

const ROOT = path.join(__dirname, '..');

export class App {
  readonly page: Page;
  readonly baseUrl: string;
  readonly testCaseId: string;
  readonly steps: Record<string, unknown>[] = [];
  readonly consoleLog: string[] = [];
  failure: Record<string, unknown> = {};
  readonly pages: Pages;
  private readonly specs = loadLocators();

  constructor(page: Page, baseUrl: string, testCaseId: string) {
    this.page = page;
    this.baseUrl = baseUrl.replace(/\/+$/, '') + '/';
    this.testCaseId = testCaseId;
    this.pages = new Pages(this);
    page.on('console', (m) => {
      if (m.type() === 'error' || m.type() === 'warning') this.consoleLog.push(`${m.type()}: ${m.text().slice(0, 300)}`);
    });
    page.on('pageerror', (e) => this.consoleLog.push(`pageerror: ${String(e).slice(0, 300)}`));
  }

  /** Substitute {{env:NAME}} placeholders from the environment (values never appear in code or reports). */
  val(text: string): string {
    return text.replace(/\{\{env:([A-Za-z_][A-Za-z0-9_]*)\}\}/g, (_m, name: string) => {
      const value = process.env[name];
      if (value === undefined) throw new Error(`Environment variable ${name} is not set`);
      return value;
    });
  }

  locator(key: string): Locator {
    const spec = this.specs[key];
    if (!spec) throw new Error(`Unknown element key: ${key}`);
    return resolve(this.page, spec.preferred);
  }

  async goto(target: string): Promise<void> {
    const url = /^https?:\/\//.test(target) ? target : new URL(target.replace(/^\/+/, ''), this.baseUrl).toString();
    await this.page.goto(url, { waitUntil: 'domcontentloaded' });
  }

  async step(description: string, meta: { action?: string; element?: string }, body: () => Promise<void>): Promise<void> {
    const record: Record<string, unknown> = { index: this.steps.length + 1, description, action: meta.action || '', element: meta.element || '', status: 'running' };
    this.steps.push(record);
    try {
      await body();
      record.status = 'passed';
    } catch (error) {
      record.status = 'failed';
      record.error = String((error as Error).message || error).slice(0, 1500);
      this.failure = { step: record.index, action: meta.action || '', element: meta.element || '', error: record.error };
      throw error;
    }
  }

  async finish(failed: boolean): Promise<void> {
    const folder = path.join(ROOT, 'reports', 'evidence', this.testCaseId);
    fs.mkdirSync(folder, { recursive: true });
    fs.writeFileSync(path.join(folder, 'steps.json'), JSON.stringify(this.steps, null, 2));
    if (!failed) return;
    const info: Record<string, unknown> = { test_case_id: this.testCaseId, console: this.consoleLog.slice(-20), ...this.failure };
    try {
      info.url = this.page.url();
      info.title = await this.page.title();
      fs.writeFileSync(path.join(folder, 'dom.html'), (await this.page.content()).slice(0, 500000));
      await this.page.screenshot({ path: path.join(folder, 'screenshot.png') });
    } catch (error) {
      info.evidence_error = String(error).slice(0, 200);
    }
    fs.writeFileSync(path.join(folder, 'failure.json'), JSON.stringify(info, null, 2));
  }
}
"""

TS_FIXTURES = r"""import { test as base, expect } from '@playwright/test';
import { App } from './app';

const DEFAULT_BASE_URL = __BASE_URL__;

export const escapeRegExp = (text: string): string => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

export const test = base.extend<{ app: App }>({
  app: async ({ page }, use, testInfo) => {
    const match = testInfo.title.match(/TC_[A-Z0-9]+_\d{3}/i);
    const app = new App(page, process.env.BASE_URL || DEFAULT_BASE_URL, match ? match[0].toUpperCase() : 'UNKNOWN');
    await use(app);
    await app.finish(testInfo.status !== 'passed' && testInfo.status !== 'skipped');
  },
});

export { expect };
"""

TS_BASE_PAGE = r"""import type { Locator } from '@playwright/test';
import type { App } from '../utils/app';

export class BasePage {
  readonly path: string = '/';
  protected readonly app: App;

  constructor(app: App) {
    this.app = app;
  }

  protected locator(key: string): Locator {
    return this.app.locator(key);
  }

  async open(): Promise<void> {
    await this.app.goto(this.path);
  }
}
"""

TS_CONFIG = r"""import { defineConfig, devices } from '@playwright/test';

const DEFAULT_BASE_URL = __BASE_URL__;
const browsers: Record<string, any> = {
  chromium: { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  chrome: { name: 'chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
  edge: { name: 'edge', use: { ...devices['Desktop Edge'], channel: 'msedge' } },
  firefox: { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  webkit: { name: 'webkit', use: { ...devices['Desktop Safari'] } },
};
const selected = browsers[(process.env.BROWSER || __BROWSER__).toLowerCase()] || browsers.chromium;

export default defineConfig({
  testDir: './tests',
  timeout: 45_000,
  expect: { timeout: 10_000 },
  retries: 0,
  workers: Number(process.env.WORKERS || 2),
  outputDir: 'reports/artifacts',
  reporter: [['list'], ['junit', { outputFile: 'reports/junit.xml' }]],
  use: {
    baseURL: process.env.BASE_URL || DEFAULT_BASE_URL,
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    video: 'retain-on-failure',
    ignoreHTTPSErrors: process.env.IGNORE_HTTPS_ERRORS === '1',
  },
  projects: [selected],
});
"""

TSCONFIG = """{
  "compilerOptions": {
    "target": "ES2020",
    "module": "commonjs",
    "strict": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "types": ["node"]
  },
  "include": ["tests", "pages", "utils", "playwright.config.ts"]
}
"""

# ---------------------------------------------------------------- JavaScript runtime
JS_LOCATORS = r"""const fs = require('fs');
const path = require('path');

const FILE = path.join(__dirname, '..', 'config', 'locators.json');

function loadLocators() {
  return JSON.parse(fs.readFileSync(FILE, 'utf-8'));
}

// No silent fallback: a stale locator must fail loudly so it can be analysed (and healed with approval).
function resolve(page, s) {
  const exact = !!s.exact;
  switch (s.kind) {
    case 'testid': return page.getByTestId(s.value);
    case 'role': return s.name ? page.getByRole(s.value, { name: s.name, exact }) : page.getByRole(s.value);
    case 'label': return page.getByLabel(s.value, { exact });
    case 'placeholder': return page.getByPlaceholder(s.value, { exact });
    case 'text': return page.getByText(s.value, { exact });
    case 'id': return page.locator(`[id="${s.value.replace(/"/g, '\\"')}"]`);
    case 'name': return page.locator(`[name="${s.value.replace(/"/g, '\\"')}"]`);
    case 'xpath': return page.locator(`xpath=${s.value}`);
    default: return page.locator(s.value);
  }
}

module.exports = { loadLocators, resolve };
"""

JS_APP = r"""const fs = require('fs');
const path = require('path');
const { loadLocators, resolve } = require('./locators');
const { Pages } = require('../pages');

const ROOT = path.join(__dirname, '..');

class App {
  constructor(page, baseUrl, testCaseId) {
    this.page = page;
    this.baseUrl = baseUrl.replace(/\/+$/, '') + '/';
    this.testCaseId = testCaseId;
    this.steps = [];
    this.consoleLog = [];
    this.failure = {};
    this.specs = loadLocators();
    this.pages = new Pages(this);
    page.on('console', (m) => {
      if (m.type() === 'error' || m.type() === 'warning') this.consoleLog.push(`${m.type()}: ${m.text().slice(0, 300)}`);
    });
    page.on('pageerror', (e) => this.consoleLog.push(`pageerror: ${String(e).slice(0, 300)}`));
  }

  /** Substitute {{env:NAME}} placeholders from the environment (values never appear in code or reports). */
  val(text) {
    return text.replace(/\{\{env:([A-Za-z_][A-Za-z0-9_]*)\}\}/g, (_m, name) => {
      const value = process.env[name];
      if (value === undefined) throw new Error(`Environment variable ${name} is not set`);
      return value;
    });
  }

  locator(key) {
    const spec = this.specs[key];
    if (!spec) throw new Error(`Unknown element key: ${key}`);
    return resolve(this.page, spec.preferred);
  }

  async goto(target) {
    const url = /^https?:\/\//.test(target) ? target : new URL(target.replace(/^\/+/, ''), this.baseUrl).toString();
    await this.page.goto(url, { waitUntil: 'domcontentloaded' });
  }

  async step(description, meta, body) {
    const record = { index: this.steps.length + 1, description, action: meta.action || '', element: meta.element || '', status: 'running' };
    this.steps.push(record);
    try {
      await body();
      record.status = 'passed';
    } catch (error) {
      record.status = 'failed';
      record.error = String((error && error.message) || error).slice(0, 1500);
      this.failure = { step: record.index, action: meta.action || '', element: meta.element || '', error: record.error };
      throw error;
    }
  }

  async finish(failed) {
    const folder = path.join(ROOT, 'reports', 'evidence', this.testCaseId);
    fs.mkdirSync(folder, { recursive: true });
    fs.writeFileSync(path.join(folder, 'steps.json'), JSON.stringify(this.steps, null, 2));
    if (!failed) return;
    const info = { test_case_id: this.testCaseId, console: this.consoleLog.slice(-20), ...this.failure };
    try {
      info.url = this.page.url();
      info.title = await this.page.title();
      fs.writeFileSync(path.join(folder, 'dom.html'), (await this.page.content()).slice(0, 500000));
      await this.page.screenshot({ path: path.join(folder, 'screenshot.png') });
    } catch (error) {
      info.evidence_error = String(error).slice(0, 200);
    }
    fs.writeFileSync(path.join(folder, 'failure.json'), JSON.stringify(info, null, 2));
  }
}

module.exports = { App };
"""

JS_FIXTURES = r"""const base = require('@playwright/test');
const { App } = require('./app');

const DEFAULT_BASE_URL = __BASE_URL__;
const expect = base.expect;
const escapeRegExp = (text) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const test = base.test.extend({
  app: async ({ page }, use, testInfo) => {
    const match = testInfo.title.match(/TC_[A-Z0-9]+_\d{3}/i);
    const app = new App(page, process.env.BASE_URL || DEFAULT_BASE_URL, match ? match[0].toUpperCase() : 'UNKNOWN');
    await use(app);
    await app.finish(testInfo.status !== 'passed' && testInfo.status !== 'skipped');
  },
});

module.exports = { test, expect, escapeRegExp };
"""

JS_BASE_PAGE = r"""class BasePage {
  constructor(app) {
    this.app = app;
    this.path = '/';
  }

  locator(key) {
    return this.app.locator(key);
  }

  async open() {
    await this.app.goto(this.path);
  }
}

module.exports = { BasePage };
"""

class PlaywrightJsAdapter(FrameworkAdapter):
    def __init__(self, typescript: bool) -> None:
        self.ts = typescript
        self.key = "playwright_typescript" if typescript else "playwright_javascript"
        self.ext = "ts" if typescript else "js"

    # ------------------------------------------------------------------
    def render(self, ctx: RenderContext) -> dict[str, str]:
        ext = self.ext
        used: dict[str, list[str]] = {}
        for item in ctx.cases:
            for step in item.script.steps:
                if step.element:
                    page_key = ctx.locators[step.element].page_key
                    bucket = used.setdefault(page_key, [])
                    if step.element not in bucket:
                        bucket.append(step.element)

        def ref(key: str) -> str:
            return f"app.pages.{py_ident(ctx.locators[key].page_key, 'page')}.{attr_of(key)}"

        base_url = js_str(ctx.base_url)
        files: dict[str, str] = {}
        for module_key, items in ctx.modules().items():
            files[f"tests/{module_slug(module_key)}.spec.{ext}"] = self._tests(module_key, items, ref)
        for page_key, keys in used.items():
            files[f"pages/{py_ident(page_key, 'page')}.page.{ext}"] = self._page(ctx, page_key, keys)
        files[f"pages/index.{ext}"] = self._pages_index(used)
        files[f"pages/base.page.{ext}"] = TS_BASE_PAGE if self.ts else JS_BASE_PAGE
        files[f"utils/locators.{ext}"] = TS_LOCATORS if self.ts else JS_LOCATORS
        files[f"utils/app.{ext}"] = TS_APP if self.ts else JS_APP
        files[f"utils/fixtures.{ext}"] = (TS_FIXTURES if self.ts else JS_FIXTURES).replace("__BASE_URL__", base_url)
        config = TS_CONFIG if self.ts else self._js_config()
        files[f"playwright.config.{ext}"] = config.replace("__BASE_URL__", base_url).replace("__BROWSER__", js_str(ctx.browser))
        files["config/locators.json"] = locators_json(ctx)
        package = {
            "name": "ai-generated-tests", "version": "1.0.0", "private": True,
            "scripts": {"test": "playwright test"},
            "devDependencies": {"@playwright/test": ctx.playwright_version, **({"typescript": "^5.4.0", "@types/node": "^20.11.0"} if self.ts else {})},
        }  # fmt: skip
        files["package.json"] = json.dumps(package, indent=2) + "\n"
        if self.ts:
            files["tsconfig.json"] = TSCONFIG
        files["README.md"] = readme(ctx, f"Playwright + {'TypeScript' if self.ts else 'JavaScript'}", "npm install\nnpx playwright install", f"BROWSER={ctx.browser} npx playwright test")
        files[".gitignore"] = GITIGNORE
        files[".env.example"] = ENV_EXAMPLE
        return files

    @staticmethod
    def _js_config() -> str:
        text = TS_CONFIG.replace("import { defineConfig, devices } from '@playwright/test';", "const { defineConfig, devices } = require('@playwright/test');")
        text = text.replace("const browsers: Record<string, any> = {", "const browsers = {").replace("export default defineConfig({", "module.exports = defineConfig({")
        return text

    # ------------------------------------------------------------------
    def _tests(self, module: str, items: list, ref) -> str:  # type: ignore[no-untyped-def]
        header = "import { test, expect, escapeRegExp } from '../utils/fixtures';" if self.ts else "const { test, expect, escapeRegExp } = require('../utils/fixtures');"
        lines = [f"// Automated tests for module: {comment_safe(module)} (generated by AI Autonomous Testing Studio)", header, "", f"test.describe({js_str(module)}, () => {{"]
        for item in items:
            tc, script = item.test_case, item.script
            lines.append(f"  // {tc.test_case_id} | Scenario {tc.scenario_id} | Expected: {comment_safe(tc.expected_result, 200)}")
            if script.notes:
                lines.append(f"  // Note: {comment_safe(script.notes, 200)}")
            lines.append(f"  test({js_str(tc.test_case_id + ' - ' + tc.title)}, async ({{ app }}) => {{")
            for step in script.steps:
                meta = f"{{ action: {js_str(step.action)}, element: {js_str(step.element or '')} }}"
                lines.append(f"    await app.step({js_str(step_text(step, tc))}, {meta}, async () => {{")
                lines.append(f"      {self._statement(step, ref)}")
                lines.append("    });")
            if not script.steps:
                lines.append("    test.skip(true, 'No automatable steps');")
            lines.append("  });")
            lines.append("")
        lines.append("});")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _statement(step: AutomationStep, ref) -> str:  # type: ignore[no-untyped-def]
        loc = ref(step.element) if step.element else ""
        text = step.value or ""
        v = f"app.val({js_str(text)})" if ENV_PLACEHOLDER.search(text) else js_str(text)
        mapping = {
            "goto": f"await app.goto({v});",
            "click": f"await {loc}.click();",
            "dblclick": f"await {loc}.dblclick();",
            "fill": f"await {loc}.fill({v});",
            "clear": f"await {loc}.clear();",
            "select": f"await {loc}.selectOption({{ label: {v} }});",
            "check": f"await {loc}.check();",
            "uncheck": f"await {loc}.uncheck();",
            "press": f"await {loc}.press({v});",
            "hover": f"await {loc}.hover();",
            "expect_visible": f"await expect({loc}).toBeVisible();",
            "expect_hidden": f"await expect({loc}).toBeHidden();",
            "expect_text": f"await expect({loc}).toContainText({v});",
            "expect_value": f"await expect({loc}).toHaveValue({v});",
            "expect_enabled": f"await expect({loc}).toBeEnabled();",
            "expect_disabled": f"await expect({loc}).toBeDisabled();",
            "expect_url_contains": f"await expect(app.page).toHaveURL(new RegExp(escapeRegExp({v})));",
            "expect_title_contains": f"await expect(app.page).toHaveTitle(new RegExp(escapeRegExp({v})));",
        }
        return mapping[step.action]

    def _page(self, ctx: RenderContext, page_key: str, keys: list[str]) -> str:
        url = next((ctx.locators[k].page_url for k in keys if ctx.locators[k].page_url), "/")
        parsed = urlparse(url)
        path = (parsed.path or "/") + (f"?{parsed.query}" if parsed.query else "")
        cls = f"{pascal(page_key)}Page"
        if self.ts:
            lines = ["import type { Locator } from '@playwright/test';", "import { BasePage } from './base.page';", "", f"export class {cls} extends BasePage {{", f"  readonly path = {js_str(path)};"]
        else:
            lines = ["const { BasePage } = require('./base.page');", "", f"class {cls} extends BasePage {{", "  constructor(app) {", "    super(app);", f"    this.path = {js_str(path)};", "  }"]
        for key in keys:
            spec = ctx.locators[key]
            doc = comment_safe(spec.intent or spec.name or spec.role or key, 80)
            ret = ": Locator" if self.ts else ""
            lines += ["", f"  /** {doc} */", f"  get {attr_of(key)}(){ret} {{", f"    return this.locator({js_str(key)});", "  }"]
        lines.append("}")
        if not self.ts:
            lines += ["", f"module.exports = {{ {cls} }};"]
        return "\n".join(lines) + "\n"

    def _pages_index(self, used: dict[str, list[str]]) -> str:
        classes = [(py_ident(k, "page"), f"{pascal(k)}Page", k) for k in used]
        if self.ts:
            lines = [f"import {{ {c} }} from './{ident}.page';" for ident, c, _ in classes]
            lines += ["", "export class Pages {"]
            lines += [f"  readonly {ident}: {c};" for ident, c, _ in classes]
            lines += ["", "  constructor(app: any) {"]
            lines += [f"    this.{ident} = new {c}(app);" for ident, c, _ in classes]
            lines += ["  }", "}"]
        else:
            lines = [f"const {{ {c} }} = require('./{ident}.page');" for ident, c, _ in classes]
            lines += ["", "class Pages {", "  constructor(app) {"]
            lines += [f"    this.{ident} = new {c}(app);" for ident, c, _ in classes]
            lines += ["  }", "}", "", "module.exports = { Pages };"]
        return "\n".join(lines) + "\n"
