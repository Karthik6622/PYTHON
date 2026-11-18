import * as fs from 'fs';
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
