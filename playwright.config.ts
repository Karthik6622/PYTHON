import { defineConfig, devices } from '@playwright/test';

const DEFAULT_BASE_URL = "https://personalpartner.streamlit.app/";
// Containers (Docker, Streamlit Cloud) have a tiny /dev/shm and no sandbox: without these flags Chromium crashes or hangs.
const lean = { args: ['--disable-dev-shm-usage', '--no-sandbox', '--disable-gpu'] };
const browsers: Record<string, any> = {
  chromium: { name: 'chromium', use: { ...devices['Desktop Chrome'], launchOptions: lean } },
  chrome: { name: 'chrome', use: { ...devices['Desktop Chrome'], channel: 'chrome', launchOptions: lean } },
  edge: { name: 'edge', use: { ...devices['Desktop Edge'], channel: 'msedge', launchOptions: lean } },
  firefox: { name: 'firefox', use: { ...devices['Desktop Firefox'] } },
  webkit: { name: 'webkit', use: { ...devices['Desktop Safari'] } },
};
const selected = browsers[(process.env.BROWSER || "chrome").toLowerCase()] || browsers.chromium;

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
    ignoreHTTPSErrors: process.env.IGNORE_HTTPS_ERRORS === '1',
  },
  projects: [selected],
});
