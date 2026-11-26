() => {
  const MAX_ELEMENTS = 400;
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const cut = (s, n) => { s = norm(s); return s.length > n ? s.slice(0, n) : s; };
  const isVisible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 0 && r.height > 0 && st.visibility !== 'hidden' && st.display !== 'none' && parseFloat(st.opacity || '1') > 0;
  };
  const q = (sel, root) => { try { return Array.from((root || document).querySelectorAll(sel)); } catch (e) { return []; } };
  const esc = (v) => (window.CSS && CSS.escape) ? CSS.escape(v) : v.replace(/([^\w-])/g, '\\$1');
  const attr = (el, n) => el.getAttribute(n) || '';
  // Icon fonts render ligature names (e.g. 'add', 'keyboard_double_arrow_left') as text; they are aria-hidden, so they are not part of the accessible name.
  const ICONS = 'svg,[aria-hidden="true"],[data-testid="stIconMaterial"],[data-testid="stIconEmoji"],.material-icons,.material-symbols-outlined,[class*="material-symbols"]';
  const textOf = (el) => {
    if (!el) return '';
    if (!el.querySelector || !el.querySelector(ICONS)) return el.innerText || el.textContent || '';
    const clone = el.cloneNode(true);
    clone.querySelectorAll(ICONS).forEach((n) => n.remove());
    return clone.textContent || '';
  };

  const IMPLICIT = { a: 'link', button: 'button', select: 'combobox', textarea: 'textbox', summary: 'button', img: 'img', nav: 'navigation', table: 'table', dialog: 'dialog', h1: 'heading', h2: 'heading', h3: 'heading', h4: 'heading', h5: 'heading', h6: 'heading', ul: 'list', ol: 'list', caption: 'caption', legend: 'group' };
  const INPUT_ROLE = { button: 'button', submit: 'button', reset: 'button', image: 'button', checkbox: 'checkbox', radio: 'radio', range: 'slider', number: 'spinbutton', search: 'searchbox', email: 'textbox', tel: 'textbox', text: 'textbox', url: 'textbox', password: 'textbox' };
  const roleOf = (el) => {
    const explicit = attr(el, 'role');
    if (explicit) return explicit.split(' ')[0];
    const tag = el.tagName.toLowerCase();
    if (tag === 'input') return INPUT_ROLE[(el.type || 'text').toLowerCase()] || 'textbox';
    if (tag === 'a' && !el.hasAttribute('href')) return '';
    return IMPLICIT[tag] || '';
  };
  const labelOf = (el) => {
    if (el.labels && el.labels.length) return cut(Array.from(el.labels).map((l) => textOf(l)).join(' '), 100);
    const id = el.id;
    if (id) { const l = document.querySelector('label[for="' + id.replace(/"/g, '\\"') + '"]'); if (l) return cut(textOf(l), 100); }
    const wrap = el.closest('label');
    return wrap ? cut(textOf(wrap), 100) : '';
  };
  const accName = (el) => {
    const by = attr(el, 'aria-labelledby');
    if (by) {
      const t = by.split(/\s+/).map((i) => { const n = document.getElementById(i); return n ? n.textContent : ''; }).join(' ');
      if (norm(t)) return cut(t, 100);
    }
    const aria = attr(el, 'aria-label');
    if (aria) return cut(aria, 100);
    const tag = el.tagName.toLowerCase();
    const type = (el.type || '').toLowerCase();
    if (tag === 'input' && ['button', 'submit', 'reset'].includes(type)) return cut(el.value || type, 100);
    if (tag === 'input' || tag === 'select' || tag === 'textarea') return labelOf(el) || cut(attr(el, 'placeholder') || attr(el, 'title'), 100);
    if (tag === 'img') return cut(attr(el, 'alt'), 100);
    return cut(textOf(el), 100) || cut(attr(el, 'title') || attr(el, 'alt'), 100);
  };
  const cssPath = (el) => {
    if (el.id && q('#' + esc(el.id)).length === 1) return '#' + esc(el.id);
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1 && node !== document.body && parts.length < 6) {
      let part = node.tagName.toLowerCase();
      if (node.id && q('#' + esc(node.id)).length === 1) { parts.unshift('#' + esc(node.id)); break; }
      const parent = node.parentElement;
      if (parent) {
        const same = Array.from(parent.children).filter((c) => c.tagName === node.tagName);
        if (same.length > 1) part += ':nth-of-type(' + (same.indexOf(node) + 1) + ')';
      }
      parts.unshift(part);
      node = node.parentElement;
    }
    return parts.join(' > ');
  };
  const xpathOf = (el) => {
    if (el.id && q('#' + esc(el.id)).length === 1) return '//*[@id="' + el.id + '"]';
    const parts = [];
    let node = el;
    while (node && node.nodeType === 1) {
      let i = 1, sib = node.previousElementSibling;
      while (sib) { if (sib.tagName === node.tagName) i++; sib = sib.previousElementSibling; }
      parts.unshift(node.tagName.toLowerCase() + '[' + i + ']');
      node = node.parentElement;
    }
    return '/' + parts.join('/');
  };
  const landmarkOf = (el) => {
    const p = el.closest('nav,header,main,footer,aside,form,dialog,[role=dialog],[role=navigation],[role=banner],[role=main],[role=search],section[aria-label],[role=tabpanel]');
    if (!p) return '';
    const label = attr(p, 'aria-label') || attr(p, 'id') || '';
    return (attr(p, 'role') || p.tagName.toLowerCase()) + (label ? ':' + cut(label, 40) : '');
  };

  const FORM_SEL = 'form,[data-testid="stForm"]';  // Streamlit renders st.form as a div
  const forms = q(FORM_SEL).filter((f) => !f.parentElement || !f.parentElement.closest(FORM_SEL));
  const SELECTOR = [
    'a[href]', 'button', 'input:not([type=hidden])', 'select', 'textarea', 'summary',
    '[role=button]', '[role=link]', '[role=tab]', '[role=menuitem]', '[role=checkbox]', '[role=radio]', '[role=switch]',
    '[role=combobox]', '[role=textbox]', '[role=option]', '[data-testid]', '[data-test]', '[data-qa]', '[data-cy]',
    '[contenteditable=true]', '[tabindex]:not([tabindex="-1"])',
    // what a person READS: headings and messages are elements too, so tests can assert on them by role and name
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6', '[role=heading]', '[role=alert]', '[role=status]', 'caption', 'legend',
  ].join(',');
  const INTERACTIVE_TAGS = ['a', 'button', 'input', 'select', 'textarea', 'summary'];
  const isContainer = (el) => {
    // Layout wrappers that only match through data-testid / tabindex (frameworks tag every block) are noise, not controls.
    if (INTERACTIVE_TAGS.includes(el.tagName.toLowerCase()) || attr(el, 'role') || el.isContentEditable) return false;
    if (/^h[1-6]$/.test(el.tagName.toLowerCase()) || el.tagName === 'CAPTION' || el.tagName === 'LEGEND') return false;
    return !!el.querySelector('a[href],button,input,select,textarea,[role=button],[role=tab],[role=link]') || norm(el.textContent).length > 140;
  };
  const seen = new Set();
  const elements = [];
  for (const el of q(SELECTOR)) {
    if (seen.has(el) || elements.length >= MAX_ELEMENTS) continue;
    seen.add(el);
    if (isContainer(el)) continue;
    const tag = el.tagName.toLowerCase();
    const type = (el.type || '').toLowerCase();
    const testid = attr(el, 'data-testid') || attr(el, 'data-test') || attr(el, 'data-qa') || attr(el, 'data-cy');
    const testidAttr = el.hasAttribute('data-testid') ? 'data-testid' : el.hasAttribute('data-test') ? 'data-test' : el.hasAttribute('data-qa') ? 'data-qa' : el.hasAttribute('data-cy') ? 'data-cy' : '';
    const aria = {};
    for (const a of el.attributes) if (a.name.startsWith('aria-')) aria[a.name] = cut(a.value, 80);
    const item = {
      reveal: (() => {  // the collapsed sections (details / summary) that must be open for the element to be on screen
        const labels = [];
        let d = el.tagName.toLowerCase() === 'summary' ? (el.parentElement && el.parentElement.parentElement) : el.parentElement;
        d = d && d.closest('details');
        while (d) {
          const s = d.querySelector(':scope > summary');
          if (s) labels.unshift(cut(textOf(s), 60));
          d = d.parentElement ? d.parentElement.closest('details') : null;
        }
        return labels;
      })(),
      tag, type, role: roleOf(el), name: accName(el), text: cut(textOf(el), 120),
      id: el.id || '', name_attr: attr(el, 'name'), testid, testid_attr: testidAttr,
      classes: Array.from(el.classList).slice(0, 4), placeholder: attr(el, 'placeholder'),
      href: tag === 'a' ? attr(el, 'href') : '', label: labelOf(el), title: attr(el, 'title'), alt: attr(el, 'alt'), aria,
      visible: isVisible(el), disabled: !!el.disabled || attr(el, 'aria-disabled') === 'true', required: !!el.required,
      validation: el.willValidate && el.checkValidity && !el.checkValidity() ? cut(el.validationMessage, 160) : '',
      readonly: !!el.readOnly, checked: !!el.checked, maxlength: attr(el, 'maxlength'), min: attr(el, 'min'), max: attr(el, 'max'),
      pattern: attr(el, 'pattern'), autocomplete: attr(el, 'autocomplete'),
      options: tag === 'select' ? Array.from(el.options).slice(0, 25).map((o) => cut(o.text, 60)) : [],
      form: forms.indexOf(el.closest(FORM_SEL)), landmark: landmarkOf(el), css: cssPath(el), xpath: xpathOf(el),
      counts: {
        id: el.id ? q('[id="' + el.id.replace(/"/g, '\\"') + '"]').length : 0,
        testid: testid ? q('[' + testidAttr + '="' + testid.replace(/"/g, '\\"') + '"]').length : 0,
        name_attr: attr(el, 'name') ? q('[name="' + attr(el, 'name').replace(/"/g, '\\"') + '"]').length : 0,
      },
    };
    elements.push(item);
  }
  elements.forEach((e, i) => { e.index = i; });

  const formInfo = forms.slice(0, 20).map((f, i) => ({
    index: i, id: f.id || '', name: attr(f, 'name'), action: attr(f, 'action'), method: (typeof f.method === 'string' && f.method ? f.method : 'get').toLowerCase(),
    fields: elements.filter((e) => e.form === i && !['button', 'submit', 'reset'].includes(e.type) && e.tag !== 'button').map((e) => e.index),
    submit: cut(((f.querySelector('button[type=submit],input[type=submit],[data-testid*="FormSubmit"] button,button[kind*="FormSubmit"],button:not([type])') || {}).innerText) || '', 60),
  }));
  const tables = q('table').slice(0, 10).map((t) => ({
    headers: q('th', t).slice(0, 15).map((h) => cut(h.innerText, 40)), rows: q('tr', t).length,
    caption: cut((t.querySelector('caption') || {}).innerText || '', 60),
  }));
  const navigation = q('nav,[role=navigation]').slice(0, 6).map((n) => ({
    label: attr(n, 'aria-label') || attr(n, 'id') || 'navigation',
    links: q('a[href]', n).slice(0, 30).map((a) => ({ text: cut(a.innerText, 40), href: attr(a, 'href') })),
  }));
  const components = {
    forms: forms.length, tables: tables.length, modals: q('dialog,[role=dialog],[aria-modal=true]').length,
    tabs: q('[role=tab]').length, accordions: q('details,[aria-expanded]').length, iframes: q('iframe').length,
    images: q('img').length, videos: q('video').length, dropdowns: q('select,[role=combobox],[role=listbox]').length,
  };
  // Visible static text a test may assert on (labels, paragraphs, captions, table cells), without the text of controls and headings.
  const CONTROL_ROLES = ['button', 'link', 'textbox', 'searchbox', 'combobox', 'spinbutton', 'checkbox', 'radio', 'switch', 'tab', 'menuitem', 'option', 'slider'];
  const controlText = new Set(elements.filter((e) => e.visible && (INTERACTIVE_TAGS.includes(e.tag) || CONTROL_ROLES.includes(e.role))).flatMap((e) => [e.name, e.text, e.label]).filter(Boolean).map((t) => t.toLowerCase()));
  const textBlocks = [];
  const seenText = new Set();
  for (const el of q('p,li,td,th,label,small,figcaption,blockquote,[data-testid=stMarkdownContainer],[data-testid=stCaptionContainer],[data-testid=stText]')) {
    if (textBlocks.length >= 60 || !isVisible(el) || el.closest('button,a,[role=button],[role=tab],[role=radio],h1,h2,h3,h4,h5,h6')) continue;
    if (el.querySelector('p,li,td,th,label')) continue;  // the innermost block carries the text
    const t = cut(textOf(el), 160);
    if (t.length < 2 || seenText.has(t.toLowerCase()) || controlText.has(t.toLowerCase())) continue;
    seenText.add(t.toLowerCase());
    textBlocks.push(t);
  }
  const messages = q('[role=alert],[role=status],[data-testid=stAlert],[data-testid=stNotification],[data-testid=stToast],.alert,.error,.success,.warning,[class*="error-message"],[class*="toast"]')
    .filter(isVisible).map((m) => cut(textOf(m), 200)).filter((t, i, a) => t && a.indexOf(t) === i).slice(0, 10);
  return {
    title: document.title || '', lang: document.documentElement.lang || '',
    headings: q('h1,h2,h3,h4,h5,h6,[role=heading]').filter(isVisible).slice(0, 30).map((h) => (h.tagName.toLowerCase().match(/^h[1-6]$/) ? h.tagName.toLowerCase() : 'h' + (attr(h, 'aria-level') || '2')) + ': ' + cut(textOf(h), 80)),
    elements, forms: formInfo, tables, navigation, components, texts: textBlocks, messages,
    links: Array.from(new Set(q('a[href]').map((a) => a.href))).slice(0, 300),
    body_text: cut(document.body ? document.body.innerText : '', 800),
    has_password_field: q('input[type=password]').length > 0,
  };
}
