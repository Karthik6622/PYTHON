import { defineConfig, devices } from '@playwright/test';

const DEFAULT_BASE_URL = "https://personalpartner.streamlit.app/";
const browsers: Record<string, any> = {
  chromium: { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  chrome: { name: 'chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome' } },
  edge: { name: 'edge', use: { ...devices['Desktop Edge'], channel: 'msedge' } },
  firefox: { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  webkit: { name: 'webkit', use: { ...devices['Desktop Safari'] } },
};
const selected = browsers[(process.env.BROWSER || "chromium").toLowerCase()] || browsers.chromium;

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
