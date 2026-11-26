(arg) => {
  const norm = (s) => (s || '').replace(/\s+/g, ' ').trim();
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const st = getComputedStyle(el);
    return r.width > 1 && r.height > 1 && st.visibility !== 'hidden' && st.display !== 'none' && parseFloat(st.opacity || '1') > 0.05;
  };
  const ICONS = 'svg,[aria-hidden="true"],[data-testid*="Icon"],[data-testid*="icon"],.material-icons,[class*="material-symbols"]';
  const textOf = (el) => { const c = el.cloneNode(true); c.querySelectorAll(ICONS).forEach((n) => n.remove()); return norm(c.textContent); };
  const roleOf = (el) => {
    const r = (el.getAttribute('role') || '').split(' ')[0];
    if (r) return r;
    const t = el.tagName.toLowerCase();
    if (t === 'a') return el.hasAttribute('href') ? 'link' : '';
    if (t === 'button') return 'button';
    if (t === 'input') {
      const ty = (el.type || '').toLowerCase();
      if (['button', 'submit', 'reset', 'image'].includes(ty)) return 'button';
      if (ty === 'radio') return 'radio';
    }
    return '';
  };
  const ROLES = new Set(['link', 'button', 'tab', 'radio', 'menuitem', 'menuitemradio', 'treeitem']);
  // Framework chrome (Streamlit toolbar, chat input, uploaders, ...) never leads to another application view.
  const CHROME = '[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],[data-testid="stStatusWidget"],' +
    '[data-testid="stChatInput"],[data-testid="stFileUploader"],[data-testid="stDownloadButton"],[data-testid="stSidebarCollapseButton"],' +
    '[data-testid="stSidebarCollapsedControl"],[data-testid="stTooltipIcon"],[data-testid="stCodeCopyButton"]';
  const FORM = 'form,[data-testid="stForm"]';
  const NAV = 'nav,[role=navigation],[role=tablist],[role=menu],[role=menubar],[role=tree],[data-testid="stSidebarNav"]';
  const SIDE = '[data-testid="stSidebar"],aside,header,[role=banner],[role=complementary]';
  const labelOf = (el, role) => {
    const aria = norm(el.getAttribute('aria-label'));
    if (role === 'radio' && el.tagName === 'INPUT') {
      const l = el.closest('label') || (el.id ? document.querySelector('label[for="' + el.id.replace(/"/g, '\\"') + '"]') : null);
      return l ? textOf(l) : aria;
    }
    if (el.tagName === 'INPUT') return norm(el.value) || aria;
    return textOf(el) || aria || norm(el.getAttribute('title'));
  };
  const find = arg && arg.find;
  const out = [];
  const counts = {};
  const nodes = document.querySelectorAll('a[href],button,input[type=button],input[type=submit],input[type=radio],' +
    '[role=button],[role=link],[role=tab],[role=radio],[role=menuitem],[role=menuitemradio],[role=treeitem]');
  for (const el of nodes) {
    const role = roleOf(el);
    if (!ROLES.has(role)) continue;
    const target = role === 'radio' && el.tagName === 'INPUT' ? (el.closest('label') || el) : el;
    const label = labelOf(el, role).slice(0, 80);
    const key = role + '|' + label.toLowerCase();
    const nth = counts[key] = counts[key] === undefined ? 0 : counts[key] + 1;
    if (find) {
      if (role === find.role && label === find.label && nth === find.nth) return target;
      continue;
    }
    const item = { role, label, nth, href: '', region: el.closest(NAV) ? 'nav' : (el.closest(SIDE) ? 'side' : 'main') };
    let skip = !label || label.length > 60 || !!el.closest(CHROME) || el.disabled || el.getAttribute('aria-disabled') === 'true' || !visible(target);
    if (role === 'tab' && el.getAttribute('aria-selected') === 'true') skip = true;
    if (role === 'radio' && (el.checked || el.getAttribute('aria-checked') === 'true')) skip = true;
    // A radio group in the page body is a setting (changing it may be saved); only navigation radios are explored.
    if (role === 'radio' && item.region === 'main') skip = true;
    if (role === 'button' && (el.closest(FORM) || (el.getAttribute('type') || '').toLowerCase() === 'submit')) skip = true;
    if (role === 'link') {
      const href = el.getAttribute('href') || '';
      if (href.startsWith('#') && !/^#[!/]/.test(href)) skip = true;
      else {
        try { const u = new URL(el.href, location.href); if (!/^https?:$/.test(u.protocol)) skip = true; item.href = u.href; } catch (e) { skip = true; }
        if (el.target === '_blank' || el.hasAttribute('download')) skip = true;
      }
    }
    if (!skip) out.push(item);
  }
  return find ? null : out;
}
