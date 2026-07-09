import { test, expect } from '@playwright/test';

// Increase default timeout for tests in this file to handle slow pages
test.setTimeout(120000);

test('google search input is visible', async ({ page }) => {
  await page.goto('https://www.google.com/');
  
  const search = page.locator('#LS8OJ > div.k1zIA.rSk4se > svg');
  await expect(search).toBeVisible();
  await page.waitForTimeout(2000);

});


test('test', async ({ page }) => {
  await page.goto('https://www.google.com/');
  //await page.getByRole('combobox', { name: 'Search' }).click();
  await expect(page.getByRole('combobox', { name: 'Search' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Google Search' })).toBeVisible();
});



test('dickssportinggoods', async ({ page }) => {
  await page.goto('https://www.dickssportinggoods.com/');
  await page.getByTestId('TopNavBar').getByRole('link', { name: 'ScoreCard+' }).click();
  await expect(page.getByRole('rowheader')).toContainText('Benefits');
  await expect(page.locator('tbody')).toContainText('EARN GOLD STATUS(Active DICK’S Cardholder Status or $500 Yearly Spend Required)$10 Bonus Reward††');
  await expect(page.locator('tbody')).toContainText('EARN GOLD STATUS(Active DICK’S Cardholder Status or $500 Yearly Spend Required)3X Points, Once Per Year***');
});


test.only('test5', async ({ page }) => {
  // Increase per-test time allowance and replace fixed waits with explicit element waits
  await page.goto('https://www.dickssportinggoods.com/');
  await page.getByTestId('TopNavBar').getByRole('link', { name: 'Gift Cards' }).click();

  const cardInput = page.getByRole('textbox', { name: 'Enter Card Number' });
  await expect(cardInput).toBeVisible({ timeout: 15000 });
  await cardInput.scrollIntoViewIfNeeded();
  await cardInput.focus();
  await cardInput.fill('123456');

  const pinInput = page.getByRole('textbox', { name: 'Enter PIN' });
  await expect(pinInput).toBeVisible({ timeout: 15000 });
  await pinInput.scrollIntoViewIfNeeded();
  await pinInput.focus();
  await pinInput.fill('123456');
  await page.getByRole('button', { name: 'Check Balance' }).scrollIntoViewIfNeeded();
  await page.getByRole('button', { name: 'Check Balance' }).focus();
  await page.getByRole('button', { name: 'Check Balance' }).click();
  await expect(page.locator('#termsAndConditions')).toContainText('Invalid Gift Card or Invalid Pin', { timeout: 15000 });
  await page.goto('https://www.dickssportinggoods.com/s/policy/price-match-policy');
  await expect(page.getByText('How It Works')).toBeVisible({ timeout: 15000 });
  await expect(page.getByRole('main')).toContainText('Online');
  await page.getByRole('tab', { name: 'In Store' }).click();
  await expect(page.locator('#tabs-bb7acded0c-item-e72ebaeb1e-tab')).toContainText('In Store');
  await expect(page.getByLabel('New Arrivals')).toMatchAriaSnapshot(`
    - heading "New Arrivals" [level=2]
    - link "SHOP ALL":
      - /url: https://www.dickssportinggoods.com/f/shop-all-new-arrivals
    - link /Nike Women's Air Max \\d+ Premium Shoes Nike Women's Air Max \\d+ Premium Shoes \\$\\d+\\.\\d+ - \\$\\d+\\.\\d+/:
      - /url: /p/nike-womens-air-max-270-premium-shoes-26nikwcasurmx270prgqy/26nikwcasurmx270prgqy?AEMpl=NewArrivalsTab
      - img /Nike Women's Air Max \\d+ Premium Shoes/
      - text: ""
    - text: Add to Cart
    - link /CALIA Women's Inspire Halter Support Top CALIA Women's Inspire Halter Support Top \\$\\d+\\.\\d+/:
      - /url: /p/calia-womens-inspire-halter-support-top-26jlownsprhltrsppapt/26jlownsprhltrsppapt?AEMpl=NewArrivalsTab
      - img "CALIA Women's Inspire Halter Support Top"
      - text: ""
    - text: Add to Cart
    - link /Nike Men's Air Max \\d+ Premium Shoes Nike Men's Air Max \\d+ Premium Shoes \\$\\d+\\.\\d+ - \\$\\d+\\.\\d+/:
      - /url: /p/nike-mens-air-max-270-premium-shoes-26nikmcasurmx270prqdm/26nikmcasurmx270prqdm?AEMpl=NewArrivalsTab
      - img /Nike Men's Air Max \\d+ Premium Shoes/
      - text: ""
    - text: Add to Cart
    - link /Nike Men's Club Fleece Washed Flow Shorts Nike Men's Club Fleece Washed Flow Shorts \\$\\d+\\.\\d+/:
      - /url: /p/nike-mens-club-fleece-washed-flow-shorts-25nikmcasumnkclbflrck/25nikmcasumnkclbflrck?AEMpl=NewArrivalsTab
      - img "Nike Men's Club Fleece Washed Flow Shorts"
      - text: ""
    - text: Add to Cart
    - link /On Men's Cloudboom Volt Running Shoes On Men's Cloudboom Volt Running Shoes \\$\\d+\\.\\d+/:
      - /url: /p/on-mens-cloudboom-volt-running-shoes-25onxmrunncldbmvltske/25onxmrunncldbmvltske?AEMpl=NewArrivalsTab
      - img "On Men's Cloudboom Volt Running Shoes"
      - text: ""
    - text: Add to Cart
    - link /Stanley \\d+ oz\\. Flowstate Spring Bottle Stanley \\d+ oz\\. Flowstate Spring Bottle \\$\\d+\\.\\d+/:
      - /url: /p/stanley-20-ozflowstate-spring-bottle-26stauhydr20zflwstjwk/26stauhydr20zflwstjwk?AEMpl=NewArrivalsTab
      - img /Stanley \\d+ oz\\. Flowstate Spring Bottle/
      - text: ""
    - text: Add to Cart
    - link /Owala \\d+ oz\\. FreeSip Sway Golf Travel Tumbler Owala \\d+ oz\\. FreeSip Sway Golf Travel Tumbler \\$\\d+\\.\\d+/:
      - /url: /p/owala-30-ozfreesip-sway-golf-travel-tumbler-25owauhydr30zfrspshhs/25owauhydr30zfrspshhs?AEMpl=NewArrivalsTab
      - img /Owala \\d+ oz\\. FreeSip Sway Golf Travel Tumbler/
      - text: ""
    - text: Add to Cart
    - link /Nike Everyday Elevated Ankle Socks - 6 Pairs Nike Everyday Elevated Ankle Socks - 6 Pairs \\$\\d+\\.\\d+/:
      - /url: /p/nike-everyday-elevated-ankle-socks-6-pairs-26nikufitnnkdlvdnkgsi/26nikufitnnkdlvdnkgsi?AEMpl=NewArrivalsTab
      - img "Nike Everyday Elevated Ankle Socks - 6 Pairs"
      - text: ""
    - text: Add to Cart
    - link /GCI Outdoor Comfort Pro Rocker 2\\.0 Chair GCI Outdoor Comfort Pro Rocker 2\\.0 Chair \\$\\d+\\.\\d+/:
      - /url: /p/gci-outdoor-comfort-pro-rocker-2-0-chair-25gciacasucmfrtprrpyi/25gciacasucmfrtprrpyi?AEMpl=NewArrivalsTab
      - img "GCI Outdoor Comfort Pro Rocker 2.0 Chair"
      - text: ""
    - text: Add to Cart
    - link /DSG Quarter Crew Socks – 6 Pack DSG Quarter Crew Socks – 6 Pack \\$\\d+\\.\\d+/:
      - /url: /p/dsg-mens-quarter-crew-socks-6-pack-23qyfmdsg6pkqtrcrsox/23qyfmdsg6pkqtrcrsox?AEMpl=NewArrivalsTab
      - img "DSG Quarter Crew Socks – 6 Pack"
      - text: ""
    - text: Add to Cart
    - link /GOAT USA Youth OG T-Shirt GOAT USA Youth OG T-Shirt \\$\\d+\\.\\d+/:
      - /url: /p/goat-usa-youth-og-t-shirt-20viqyythgtshrtxxlxa/20viqyythgtshrtxxlxa?AEMpl=NewArrivalsTab
      - img "GOAT USA Youth OG T-Shirt"
      - text: ""
    - text: Add to Cart
    - link /Bad Birdie Men's Evolution Ridge Performance Golf Polo Bad Birdie Men's Evolution Ridge Performance Golf Polo \\$\\d+\\.\\d+ - \\$\\d+\\.\\d+/:
      - /url: /p/bad-birdie-mens-evolution-ridge-performance-golf-polo-25badmgolfvltnrdgpyug/25badmgolfvltnrdgpyug?AEMpl=NewArrivalsTab
      - img "Bad Birdie Men's Evolution Ridge Performance Golf Polo"
      - text: ""
    - text: Add to Cart
    - link /Nike Kids' Grade School Air Force 1 Shoes Nike Kids' Grade School Air Force 1 Shoes \\$\\d+\\.\\d+ - \\$\\d+\\.\\d+/:
      - /url: /p/nike-kids-grade-school-air-force-1-shoes-20nikyrfrc1whtrdbbys/20nikyrfrc1whtrdbbys?AEMpl=NewArrivalsTab
      - img "Nike Kids' Grade School Air Force 1 Shoes"
      - text: ""
    - text: Add to Cart
    - link /VRST Men's Golf Pivot Printed Polo VRST Men's Golf Pivot Printed Polo \\$\\d+\\.\\d+ - \\$\\d+\\.\\d+/:
      - /url: /p/vrst-mens-golf-mesh-print-polo-24krmmmshprntplxxmga/24krmmmshprntplxxmga?AEMpl=NewArrivalsTab
      - img "VRST Men's Golf Pivot Printed Polo"
      - text: ""
    - text: Add to Cart
    - link /YETI Roadie \\d+ Hard Cooler YETI Roadie \\d+ Hard Cooler \\$\\d+\\.\\d+/:
      - /url: /p/yeti-roadie-15-hard-cooler-24yeturd15xxxxxxxrec/24yeturd15xxxxxxxrec?AEMpl=NewArrivalsTab
      - img /YETI Roadie \\d+ Hard Cooler/
      - text: ""
    - text: Add to Cart
    `);
});

test('new arrivals block has 15 products', async ({ page }) => {
  await page.goto('https://www.dickssportinggoods.com/s/policy/price-match-policy');

  const newArrivalsSection = page.locator('li:has-text("New Arrivals")');
  await expect(newArrivalsSection).toBeVisible({ timeout: 15000 });

  const productCards = page.locator('#NewArrivalsTab > div.slides > div > div > div > div');
  await expect(productCards).toHaveCount(15, { timeout: 15000 });
});
//#NewArrivalsTab > div.slides > div > div > div > div

