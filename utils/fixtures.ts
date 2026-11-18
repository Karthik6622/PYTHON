import { test as base, expect } from '@playwright/test';
import { App } from './app';

const DEFAULT_BASE_URL = "https://personalpartner.streamlit.app/";

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
