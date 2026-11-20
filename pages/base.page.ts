import type { Locator } from '@playwright/test';
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
