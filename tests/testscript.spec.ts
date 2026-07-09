import { test, expect } from '@playwright/test';

test('google search input is visible', async ({ page }) => {
  await page.goto('https://www.google.com/');
  
  const search = page.locator('#LS8OJ > div.k1zIA.rSk4se > svg');
  await expect(search).toBeVisible();
  await page.waitForTimeout(2000);

});


test.only('test', async ({ page }) => {
  await page.goto('https://www.google.com/');
  //await page.getByRole('combobox', { name: 'Search' }).click();
  await expect(page.getByRole('combobox', { name: 'Search' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Google Search' })).toBeVisible();
});