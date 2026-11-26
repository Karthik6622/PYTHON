// Browser runtime shared by the generated Playwright TypeScript / JavaScript projects: it opens the application, wakes it, steps into an
// embedded frame, signs in, replays the recorded clicks of a view and finds elements robustly (the same behaviour as the Python runtime).
const fs = require('fs');
const path = require('path');

const ACTIONS_JS = fs.readFileSync(path.join(__dirname, 'actions.js'), 'utf-8');
const LOGIN_OPENER = /^(get started|log ?in|sign ?in)\b/i;
const LOGIN_SUBMIT = /^(log ?in|sign ?in|submit|continue|enter)$/i;
const WAKE_BUTTON = /get this app back up/i;
const PASSWORD_FIELD = 'input[type=password]:visible';
const USER_FIELD = 'input[type=email]:visible, input[type=text]:visible, input:not([type]):visible';
const FIND_TIMEOUT = Number(process.env.FIND_TIMEOUT || 20) * 1000;
const IDLE_GIVE_UP = Number(process.env.IDLE_GIVE_UP || 5) * 1000;
const SIGNATURE_JS =
  "() => (document.body ? document.body.innerText.length : 0) + ':' + " +
  "document.querySelectorAll('input,button,a,select,textarea,[role],[data-testid]').length + ':' + " +
  "((document.querySelector('[data-testid=stApp]') && document.title === 'Streamlit') || document.querySelector('[data-testid=stSkeleton]') || " +
  "document.querySelector('[data-stale=true]') || /running/i.test((document.querySelector('[data-testid=stStatusWidget]') || {}).innerText || '') " +
  "|| document.readyState === 'loading' ? 'loading' : 'ready')";
const IFRAMES_JS =
  "() => Array.from(document.querySelectorAll('iframe')).map((f) => { const r = f.getBoundingClientRect(); " +
  "return { src: f.src || '', area: r.width * r.height }; }).concat([{ src: '', area: -(innerWidth * innerHeight) }])";
const toFunction = (source) => (0, eval)(`(${source})`); // Playwright for Node only calls a function value, not a string that holds one
const ACTIONS_FN = toFunction(ACTIONS_JS);
const SIGNATURE_FN = toFunction(SIGNATURE_JS);
const IFRAMES_FN = toFunction(IFRAMES_JS);
const EMBEDDED = new Map();

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

const hostOf = (url) => { try { return new URL(url).hostname.toLowerCase().replace(/^www\./, ''); } catch (e) { return ''; } };
const withoutHash = (url) => url.split('#')[0];

async function settle(page, maxMs = 15000, quietMs = 1200) {
  let waited = 0, stable = 0, last = '';
  while (waited < maxMs) {
    await page.waitForTimeout(300);
    waited += 300;
    let signature;
    try { signature = await page.evaluate(SIGNATURE_FN); } catch (e) { stable = 0; continue; }
    stable = signature === last ? stable + 300 : 0;
    last = signature;
    if (stable >= quietMs && signature.endsWith(':ready')) return;
  }
}

async function isIdle(page) {
  try {
    const first = await page.evaluate(SIGNATURE_FN);
    await page.waitForTimeout(600);
    return first.endsWith(':ready') && (await page.evaluate(SIGNATURE_FN)) === first;
  } catch (e) { return false; }
}

async function wakeSleepingApp(page, warnings, maxMs = 90000) {
  try {
    const button = page.getByRole('button', { name: WAKE_BUTTON });
    if (!(await button.count())) return;
    await button.first().click();
    let waited = 0;
    while (waited < maxMs && (await page.getByRole('button', { name: WAKE_BUTTON }).count())) { await page.waitForTimeout(1000); waited += 1000; }
    warnings.push('The application was asleep and was woken up.');
  } catch (e) { /* best effort */ }
}

async function embeddedAppUrl(page, waitS = 25) {
  let candidate = null;
  for (let tick = 0; tick < waitS; tick++) {
    let frames, plain;
    try {
      frames = await page.evaluate(IFRAMES_FN);
      plain = await page.evaluate("document.querySelectorAll('iframe').length === 0 && document.body && document.body.innerText.length > 200");
    } catch (e) { return candidate; }
    if (plain) return null;
    const view = -frames[frames.length - 1].area || 1;
    for (const frame of frames.slice(0, -1)) {
      const src = frame.src;
      if (!(src.startsWith('http') && hostOf(src) === hostOf(page.url()) && withoutHash(src) !== withoutHash(page.url()))) continue;
      candidate = src;
      if (frame.area > 0.5 * view) return src;
    }
    if (candidate === null && tick >= 5) return null;
    await page.waitForTimeout(1000);
  }
  return candidate;
}

async function openPage(page, url, warnings = []) {
  const known = EMBEDDED.get(withoutHash(url));
  if (known) {
    await page.goto(known, { waitUntil: 'domcontentloaded' });
    await settle(page);
    return;
  }
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  try { await page.waitForLoadState('networkidle', { timeout: 3000 }); } catch (e) { /* long-polling apps never go idle */ }
  await wakeSleepingApp(page, warnings);
  const inner = await embeddedAppUrl(page);
  if (inner) {
    EMBEDDED.set(withoutHash(url), inner);
    warnings.push(`The site embeds its application in a frame; the application URL (${inner}) was used directly.`);
    await page.goto(inner, { waitUntil: 'domcontentloaded' });
  }
  await settle(page);
}

async function revealLoginForm(page) {
  if (await page.locator(PASSWORD_FIELD).count()) return;
  for (const role of ['button', 'link']) {
    const opener = page.getByRole(role, { name: LOGIN_OPENER });
    if (await opener.count()) {
      await opener.first().click();
      await settle(page, 6000, 1000);
      if (await page.locator(PASSWORD_FIELD).count()) return;
    }
  }
}

/** Returns null on success, otherwise a short problem description. */
async function signIn(page, username, password, auth, startUrl, warnings = []) {
  try {
    await openPage(page, auth.login_url || startUrl, warnings);
    let submit;
    if (auth.username_selector && auth.password_selector) {
      await page.locator(auth.username_selector).first().fill(username);
      await page.locator(auth.password_selector).first().fill(password);
      submit = auth.submit_selector;
    } else {
      await revealLoginForm(page);
      await page.locator(USER_FIELD).first().fill(username);
      await page.locator(PASSWORD_FIELD).first().fill(password);
      submit = 'button[type=submit], input[type=submit]';
    }
    if (submit && (await page.locator(submit).count())) await page.locator(submit).first().click();
    else if (!auth.submit_selector && (await page.getByRole('button', { name: LOGIN_SUBMIT }).count())) await page.getByRole('button', { name: LOGIN_SUBMIT }).first().click();
    else await page.keyboard.press('Enter');
    await settle(page, 15000, 1500);
    if (auth.success_url_contains && !page.url().includes(auth.success_url_contains)) return 'Login could not be confirmed (success URL fragment not found).';
    if (await page.locator(PASSWORD_FIELD).count()) return 'A password field is still visible after login; the sign-in may have failed (check the credentials).';
  } catch (e) {
    return `Login workflow failed: ${String((e && e.message) || e).split('\n')[0].slice(0, 160)}`;
  }
  return null;
}

async function clickControl(page, step) {
  if (step.role === 'url') { await openPage(page, step.href); return true; }
  const handle = await page.evaluateHandle(ACTIONS_FN, { find: { role: step.role, label: step.label, nth: step.nth || 0 } });
  const element = handle.asElement();
  if (!element) return false;
  try { await element.click({ timeout: 5000 }); } catch (e) {
    try { await element.click({ timeout: 3000, force: true }); } catch (e2) { await element.evaluate((node) => node.click()); }
  }
  try { await page.waitForLoadState('domcontentloaded', { timeout: 10000 }); } catch (e) { /* single-page apps do not navigate */ }
  await settle(page, 12000, 1200);
  return true;
}

const describe = (s) => `${s.kind}=${JSON.stringify(s.value)}${s.name ? ` name=${JSON.stringify(s.name)}` : ''}`;

async function byFingerprint(page, spec) {
  const fp = spec.fingerprint || {};
  const role = fp.role || spec.role, name = fp.name || spec.name;
  const candidates = [];
  if (role && name) candidates.push({ kind: 'role', value: role, name, exact: true });
  if (fp.label) candidates.push({ kind: 'label', value: fp.label, exact: true });
  if (fp.placeholder) candidates.push({ kind: 'placeholder', value: fp.placeholder, exact: true });
  for (const text of [fp.text, name]) if (text && !(role && name)) candidates.push({ kind: 'text', value: text, exact: true });
  for (const selector of candidates) {
    try {
      const found = resolve(page, selector);
      if ((await found.count()) === 1) return { selector, found };
    } catch (e) { /* try the next */ }
  }
  return null;
}

/** The selector that matches exactly one element now: preferred, then recorded alternatives, then the element's fingerprint.
 *  Returns { selector, narrow }: narrow is '' (the selector itself), 'visible' (the one visible match of several) or 'first'
 *  (the same control more than once on screen, e.g. in the sidebar and in the page: the first visible one). */
async function findSelector(page, key, spec, fallbacks, wait = true) {
  const candidates = [spec.preferred, ...(spec.alternatives || [])];
  const started = Date.now();
  let ambiguous = null;
  for (;;) {
    for (let index = 0; index < candidates.length; index++) {
      let count, narrow = '';
      try {
        const found = resolve(page, candidates[index]);
        count = await found.count();
        if (count > 1 && (await found.locator('visible=true').count()) === 1) { count = 1; narrow = 'visible'; }
      } catch (e) { continue; }
      if (count === 1) {
        if (index) fallbacks[key] = { selector: candidates[index], preferred: candidates[0], index };
        return { selector: candidates[index], narrow };
      }
      if (count > 1 && !ambiguous) ambiguous = { selector: candidates[index], index };
    }
    const elapsed = Date.now() - started;
    if (elapsed > 1500 || !wait) {
      const hit = await byFingerprint(page, spec);
      if (hit) { fallbacks[key] = { selector: hit.selector, preferred: candidates[0], index: candidates.length, fingerprint: true }; return { selector: hit.selector, narrow: '' }; }
    }
    if (!wait || (ambiguous && elapsed > 2000) || elapsed > FIND_TIMEOUT) break;
    if (elapsed > IDLE_GIVE_UP && (await isIdle(page))) break;
    await page.waitForTimeout(300);
  }
  const seconds = Math.round((Date.now() - started) / 1000);
  if (ambiguous) {
    const s = ambiguous.selector;
    if (s.kind === 'role' && s.name && (await resolve(page, s).locator('visible=true').count()) > 1) {
      fallbacks[key] = { selector: s, preferred: candidates[0], index: ambiguous.index, ambiguous: true };
      return { selector: s, narrow: 'first' };
    }
    throw new Error(`Ambiguous locator for '${key}': ${describe(s)} matched several elements and no recorded alternative is unique.`);
  }
  throw new Error(`Element not found: '${key}' is not on the current view after ${seconds}s. Tried: ${candidates.slice(0, 4).map(describe).join(', ')}`);
}

/** A click may be forced only on something a person could see or use: a visible element, or the hidden input behind a styled checkbox / radio. */
async function forceable(locator) {
  try {
    return (await locator.isVisible()) || (await locator.evaluate((e) => e.tagName === 'INPUT' && ['checkbox', 'radio'].includes((e.type || '').toLowerCase())));
  } catch (e) { return false; }
}

async function forceClick(locator, double = false) {
  const action = (options) => (double ? locator.dblclick(options) : locator.click(options));
  try { await action({ timeout: 6000 }); } catch (e) {
    if ((await locator.count()) !== 1 || !(await forceable(locator))) throw e;
    try { await action({ timeout: 3000, force: true }); } catch (e2) { await locator.evaluate((node) => node.click()); }
  }
}

async function forceCheck(locator, checked = true) {
  const action = (options) => (checked ? locator.check(options) : locator.uncheck(options));
  try { await action({ timeout: 6000 }); } catch (e) {
    if ((await locator.count()) !== 1 || !(await forceable(locator))) throw e;
    try { await action({ timeout: 3000, force: true }); } catch (e2) { await locator.evaluate((node) => node.click()); }
  }
}

/** Choose an option: a native <select> uses selectOption; a custom dropdown (a combobox widget) is opened and its option clicked. */
async function selectOption(page, locator, label) {
  try { await locator.selectOption({ label }, { timeout: 6000 }); } catch (e) {
    if (!String((e && e.message) || e).includes('not a <select>')) throw e;
    await forceClick(locator);
    let option = page.getByRole('option', { name: label, exact: true });
    if (!(await option.count())) option = page.getByRole('option', { name: label });
    await option.locator('visible=true').first().click();
  }
}

/** Open the collapsed sections (expanders, accordions) that hold the element: discovery saw them open, a fresh page has them closed. */
async function reveal(page, spec, locator) {
  const labels = spec.reveal || [];
  try { if (!labels.length || (await locator.count()) !== 1 || (await locator.isVisible())) return; } catch (e) { return; }
  for (const label of labels) {
    const summary = page.locator('summary').filter({ hasText: label }).locator('visible=true');
    if (await summary.count()) { await summary.first().click(); await page.waitForTimeout(300); }
  }
  await settle(page, 2000, 600);
}

/** True when one of the view's stable headings is on screen (a replay that landed elsewhere is repeated once). */
async function arrived(page, view, waitMs = 6000) {
  const headings = view.headings || [];
  if (!headings.length) return true;
  for (let waited = 0; waited <= waitMs; waited += 500) {
    for (const heading of headings) {
      try {
        if ((await page.getByRole('heading', { name: heading, exact: true }).count()) || (await page.getByText(heading, { exact: true }).count())) return true;
      } catch (e) { /* the page is re-rendering */ }
    }
    await page.waitForTimeout(500);
  }
  return false;
}

module.exports = { resolve, settle, isIdle, openPage, signIn, clickControl, findSelector, forceClick, forceCheck, selectOption, reveal, arrived };
