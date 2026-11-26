"""Playwright + TypeScript / JavaScript project renderer (one adapter class, two flavours)."""

from __future__ import annotations

import json
from pathlib import Path
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

RUNTIME_DIR = Path(__file__).with_name("runtime_js")
RUNTIME_JS = (RUNTIME_DIR / "runtime.js").read_text(encoding="utf-8")
ACTIONS_JS = (Path(__file__).resolve().parents[2] / "discovery" / "actions.js").read_text(encoding="utf-8")

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
export const resolve: (page: Page, s: Selector) => Locator = require('./runtime').resolve;
"""

TS_APP = r"""import * as fs from 'fs';
import * as path from 'path';
import type { Locator, Page } from '@playwright/test';
import { loadLocators, resolve } from './locators';
import { Pages } from '../pages';

const rt: any = require('./runtime');
const ROOT = path.join(__dirname, '..');
const FIND_TIMEOUT_MS = Number(process.env.FIND_TIMEOUT || 20) * 1000;

function readJson(name: string): any {
  const file = path.join(ROOT, 'config', name);
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf-8')) : {};
}

export class App {
  readonly page: Page;
  readonly baseUrl: string;
  readonly testCaseId: string;
  readonly steps: Record<string, unknown>[] = [];
  readonly consoleLog: string[] = [];
  readonly warnings: string[] = [];
  readonly fallbacks: Record<string, unknown> = {};
  failure: Record<string, unknown> = {};
  view = '';
  readonly pages: Pages;
  private readonly specs = loadLocators();
  private readonly views = readJson('views.json');
  private readonly auth = readJson('auth.json');
  private readonly resolved: Record<string, any> = {};

  constructor(page: Page, baseUrl: string, testCaseId: string) {
    this.page = page;
    this.baseUrl = baseUrl.replace(/\/+$/, '') + '/';
    this.testCaseId = testCaseId;
    this.pages = new Pages(this);
    page.setDefaultTimeout(FIND_TIMEOUT_MS);
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

  /** The element's selector: the one that was verified to match exactly one element in this step (see step()). */
  locator(key: string): Locator {
    const spec = this.specs[key];
    if (!spec) throw new Error(`Unknown element key: ${key}`);
    const chosen = this.resolved[key];
    if (!chosen) return resolve(this.page, spec.preferred);
    let found = resolve(this.page, chosen.selector);
    if (chosen.narrow) found = found.locator('visible=true');
    return chosen.narrow === 'first' ? found.first() : found;
  }

  private async resolveKey(key: string, wait: boolean): Promise<void> {
    const spec = this.specs[key];
    if (!spec) throw new Error(`Unknown element key: ${key}`);
    this.resolved[key] = await rt.findSelector(this.page, key, spec, this.fallbacks, wait);
    if (wait) await rt.reveal(this.page, spec, this.locator(key));
  }

  private startUrl(): string {
    const start = String(this.views.start_url || '');
    const pathname = start ? new URL(start).pathname : '/';
    return new URL(pathname.replace(/^\/+/, ''), this.baseUrl).toString();
  }

  async goto(target: string): Promise<void> {
    const url = /^https?:\/\//.test(target) ? target : new URL(target.replace(/^\/+/, ''), this.baseUrl).toString();
    await rt.openPage(this.page, url, this.warnings);
  }

  async signIn(): Promise<void> {
    const user = this.auth.username_env || 'TEST_APP_USERNAME';
    const pass = this.auth.password_env || 'TEST_APP_PASSWORD';
    if (!['env_credentials', 'login_workflow'].includes(this.auth.mode) || !process.env[user] || !process.env[pass]) {
      throw new Error(`This test needs a signed-in session: set the credential variables ${user} and ${pass}`);
    }
    const problem = await rt.signIn(this.page, process.env[user], process.env[pass], this.auth, this.startUrl(), this.warnings);
    if (problem) throw new Error(problem);
  }

  /** Put a fresh browser on a discovered view: open (and sign in when needed), then repeat the recorded clicks. */
  async openView(key: string, retry = true): Promise<void> {
    const view = (this.views.views || {})[key];
    if (!view) { await this.goto('/'); return; }
    if (view.signed_in) await this.signIn();
    else await rt.openPage(this.page, this.startUrl(), this.warnings);
    for (const recorded of view.steps || []) {
      if (!(await rt.clickControl(this.page, recorded))) throw new Error(`Could not reach the '${view.name || key}' view: the control '${recorded.label}' was not found`);
    }
    if (!(await rt.arrived(this.page, view))) {
      // a replay that landed elsewhere (a click on a page that was still rendering) is repeated once from a fresh page
      if (retry) { await this.openView(key, false); return; }
      this.warnings.push(`The '${view.name || key}' view could not be confirmed by its headings ${JSON.stringify(view.headings)}.`);
    }
    this.view = key;
  }

  async settle(maxMs = 4000): Promise<void> {
    await rt.settle(this.page, maxMs, 600);
  }

  async select(locator: Locator, label: string): Promise<void> {
    await rt.selectOption(this.page, locator, label);
    await this.settle();
  }

  /** Click like a person: a styled control that is not 'actionable' is clicked by force, then through the DOM. */
  async click(locator: Locator, double = false): Promise<void> {
    await rt.forceClick(locator, double);
    await this.settle();
  }

  async check(locator: Locator, checked = true): Promise<void> {
    await rt.forceCheck(locator, checked);
    await this.settle();
  }

  async step(description: string, meta: { action?: string; element?: string }, body: () => Promise<void>): Promise<void> {
    const record: Record<string, unknown> = { index: this.steps.length + 1, description, action: meta.action || '', element: meta.element || '', status: 'running' };
    this.steps.push(record);
    try {
      if (meta.element) {
        if (meta.action === 'expect_hidden') await this.resolveKey(meta.element, false).catch(() => undefined);
        else await this.resolveKey(meta.element, true);
      }
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
    if (Object.keys(this.fallbacks).length) fs.writeFileSync(path.join(folder, 'fallbacks.json'), JSON.stringify(this.fallbacks, null, 2));
    if (!failed) return;
    const info: Record<string, unknown> = { test_case_id: this.testCaseId, console: this.consoleLog.slice(-20), view: this.view, warnings: this.warnings.slice(-5), ...this.failure };
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
// Containers (Docker, Streamlit Cloud) have a tiny /dev/shm and no sandbox: without these flags Chromium crashes or hangs.
const lean = { args: ['--disable-dev-shm-usage', '--no-sandbox', '--disable-gpu'] };
const browsers: Record<string, any> = {
  chromium: { name: 'chromium', use: { ...devices['Desktop Chrome'], launchOptions: lean } },
  chrome: { name: 'chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome', launchOptions: lean } },
  edge: { name: 'edge', use: { ...devices['Desktop Edge'], channel: 'msedge', launchOptions: lean } },
  firefox: { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  webkit: { name: 'webkit', use: { ...devices['Desktop Safari'] } },
};
const selected = browsers[(process.env.BROWSER || __BROWSER__).toLowerCase()] || browsers.chromium;

export default defineConfig({
  testDir: './tests',
  timeout: 120_000,
  expect: { timeout: Number(process.env.EXPECT_TIMEOUT || 15) * 1000 },
  retries: 0,
  workers: Number(process.env.WORKERS || 2),
  outputDir: 'reports/artifacts',
  reporter: [['list'], ['junit', { outputFile: 'reports/junit.xml' }]],
  use: {
    baseURL: process.env.BASE_URL || DEFAULT_BASE_URL,
    viewport: { width: 1366, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
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
const { resolve } = require('./runtime');

module.exports = { loadLocators, resolve };
"""

JS_APP = r"""const fs = require('fs');
const path = require('path');
const { loadLocators, resolve } = require('./locators');
const { Pages } = require('../pages');
const rt = require('./runtime');

const ROOT = path.join(__dirname, '..');
const FIND_TIMEOUT_MS = Number(process.env.FIND_TIMEOUT || 20) * 1000;

function readJson(name) {
  const file = path.join(ROOT, 'config', name);
  return fs.existsSync(file) ? JSON.parse(fs.readFileSync(file, 'utf-8')) : {};
}

class App {
  constructor(page, baseUrl, testCaseId) {
    this.page = page;
    this.baseUrl = baseUrl.replace(/\/+$/, '') + '/';
    this.testCaseId = testCaseId;
    this.steps = [];
    this.consoleLog = [];
    this.warnings = [];
    this.fallbacks = {};
    this.failure = {};
    this.view = '';
    this.specs = loadLocators();
    this.views = readJson('views.json');
    this.auth = readJson('auth.json');
    this.resolved = {};
    this.pages = new Pages(this);
    page.setDefaultTimeout(FIND_TIMEOUT_MS);
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

  /** The element's selector: the one that was verified to match exactly one element in this step (see step()). */
  locator(key) {
    const spec = this.specs[key];
    if (!spec) throw new Error(`Unknown element key: ${key}`);
    const chosen = this.resolved[key];
    if (!chosen) return resolve(this.page, spec.preferred);
    let found = resolve(this.page, chosen.selector);
    if (chosen.narrow) found = found.locator('visible=true');
    return chosen.narrow === 'first' ? found.first() : found;
  }

  async resolveKey(key, wait) {
    const spec = this.specs[key];
    if (!spec) throw new Error(`Unknown element key: ${key}`);
    this.resolved[key] = await rt.findSelector(this.page, key, spec, this.fallbacks, wait);
    if (wait) await rt.reveal(this.page, spec, this.locator(key));
  }

  startUrl() {
    const start = String(this.views.start_url || '');
    const pathname = start ? new URL(start).pathname : '/';
    return new URL(pathname.replace(/^\/+/, ''), this.baseUrl).toString();
  }

  async goto(target) {
    const url = /^https?:\/\//.test(target) ? target : new URL(target.replace(/^\/+/, ''), this.baseUrl).toString();
    await rt.openPage(this.page, url, this.warnings);
  }

  async signIn() {
    const user = this.auth.username_env || 'TEST_APP_USERNAME';
    const pass = this.auth.password_env || 'TEST_APP_PASSWORD';
    if (!['env_credentials', 'login_workflow'].includes(this.auth.mode) || !process.env[user] || !process.env[pass]) {
      throw new Error(`This test needs a signed-in session: set the credential variables ${user} and ${pass}`);
    }
    const problem = await rt.signIn(this.page, process.env[user], process.env[pass], this.auth, this.startUrl(), this.warnings);
    if (problem) throw new Error(problem);
  }

  /** Put a fresh browser on a discovered view: open (and sign in when needed), then repeat the recorded clicks. */
  async openView(key, retry = true) {
    const view = (this.views.views || {})[key];
    if (!view) { await this.goto('/'); return; }
    if (view.signed_in) await this.signIn();
    else await rt.openPage(this.page, this.startUrl(), this.warnings);
    for (const recorded of view.steps || []) {
      if (!(await rt.clickControl(this.page, recorded))) throw new Error(`Could not reach the '${view.name || key}' view: the control '${recorded.label}' was not found`);
    }
    if (!(await rt.arrived(this.page, view))) {
      // a replay that landed elsewhere (a click on a page that was still rendering) is repeated once from a fresh page
      if (retry) { await this.openView(key, false); return; }
      this.warnings.push(`The '${view.name || key}' view could not be confirmed by its headings ${JSON.stringify(view.headings)}.`);
    }
    this.view = key;
  }

  async settle(maxMs = 4000) {
    await rt.settle(this.page, maxMs, 600);
  }

  async select(locator, label) {
    await rt.selectOption(this.page, locator, label);
    await this.settle();
  }

  /** Click like a person: a styled control that is not 'actionable' is clicked by force, then through the DOM. */
  async click(locator, double = false) {
    await rt.forceClick(locator, double);
    await this.settle();
  }

  async check(locator, checked = true) {
    await rt.forceCheck(locator, checked);
    await this.settle();
  }

  async step(description, meta, body) {
    const record = { index: this.steps.length + 1, description, action: meta.action || '', element: meta.element || '', status: 'running' };
    this.steps.push(record);
    try {
      if (meta.element) {
        if (meta.action === 'expect_hidden') await this.resolveKey(meta.element, false).catch(() => undefined);
        else await this.resolveKey(meta.element, true);
      }
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
    if (Object.keys(this.fallbacks).length) fs.writeFileSync(path.join(folder, 'fallbacks.json'), JSON.stringify(this.fallbacks, null, 2));
    if (!failed) return;
    const info = { test_case_id: this.testCaseId, console: this.consoleLog.slice(-20), view: this.view, warnings: this.warnings.slice(-5), ...this.failure };
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
            files[f"tests/{module_slug(module_key)}.spec.{ext}"] = self._tests(module_key, items, ref, ctx.locators, bool(ctx.views))
        for page_key, keys in used.items():
            files[f"pages/{py_ident(page_key, 'page')}.page.{ext}"] = self._page(ctx, page_key, keys)
        files[f"pages/index.{ext}"] = self._pages_index(used)
        files[f"pages/base.page.{ext}"] = TS_BASE_PAGE if self.ts else JS_BASE_PAGE
        files[f"utils/locators.{ext}"] = TS_LOCATORS if self.ts else JS_LOCATORS
        files[f"utils/app.{ext}"] = TS_APP if self.ts else JS_APP
        files["utils/runtime.js"] = RUNTIME_JS  # shared by both flavours; Playwright loads plain JS from a TypeScript project
        files["utils/actions.js"] = ACTIONS_JS
        files["config/views.json"] = json.dumps(ctx.views or {"views": {}}, indent=2, ensure_ascii=False) + "\n"
        files["config/auth.json"] = json.dumps(ctx.auth or {}, indent=2) + "\n"
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
    def _tests(self, module: str, items: list, ref, locators: dict | None = None, views: bool = False) -> str:  # type: ignore[no-untyped-def]
        header = "import { test, expect, escapeRegExp } from '../utils/fixtures';" if self.ts else "const { test, expect, escapeRegExp } = require('../utils/fixtures');"
        lines = [f"// Automated tests for module: {comment_safe(module)} (generated by RK Testing Studio)", header, "", f"test.describe({js_str(module)}, () => {{"]
        for item in items:
            tc, script = item.test_case, item.script
            lines.append(f"  // {tc.test_case_id} | Scenario {tc.scenario_id} | Expected: {comment_safe(tc.expected_result, 200)}")
            if script.notes:
                lines.append(f"  // Note: {comment_safe(script.notes, 200)}")
            lines.append(f"  test({js_str(tc.test_case_id + ' - ' + tc.title)}, async ({{ app }}) => {{")
            steps = list(script.steps)
            start = next((locators[s.element].page_key for s in steps if s.element and locators and s.element in locators), None) if views else None
            if start:
                while steps and steps[0].action == "goto":  # the runtime opens the start view itself (sign-in and recorded clicks included)
                    steps.pop(0)
                lines.append(f"    await app.step({js_str('Open the application on the ' + start + ' view')}, {{ action: 'open_view', element: '' }}, async () => {{")
                lines.append(f"      await app.openView({js_str(start)});")
                lines.append("    });")
            for step in steps:
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
            "click": f"await app.click({loc});",
            "dblclick": f"await app.click({loc}, true);",
            "fill": f"await {loc}.fill({v});",
            "clear": f"await {loc}.clear();",
            "select": f"await app.select({loc}, {v});",
            "check": f"await app.check({loc}, true);",
            "uncheck": f"await app.check({loc}, false);",
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
