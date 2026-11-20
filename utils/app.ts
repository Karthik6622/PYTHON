import * as fs from 'fs';
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
