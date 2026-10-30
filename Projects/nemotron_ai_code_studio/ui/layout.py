"""Resizable panes and small page-level behaviours that Streamlit cannot do on its own.

A zero-height component iframe (same origin as the app) installs, once, a few handles on the parent document:
drag between Explorer | Editor | Agent and between Editor | Terminal, use the arrow buttons to shrink or widen a pane, or
double-click a handle to hide or restore the pane. Sizes persist in localStorage. The same script keeps the chat scrolled to
the newest message and hides platform badges (for example "Manage app") that would otherwise cover the agent input.
"""

from __future__ import annotations

import streamlit.components.v1 as components

VERSION = 5

SCRIPT = r"""
<script>
(function () {
  var P, D;
  try { P = window.parent; D = P.document; } catch (e) { return; }
  var VERSION = __VERSION__;
  if (P.__rkLayout) {
    if (P.__rkLayout.v === VERSION) { P.__rkLayout.tick(); return; }
    P.__rkLayout.stop();
  }
  var root = D.documentElement;
  var KEY = 'rk.layout.v1';
  var PRESETS = { side: [0, .72, 1, 1.5], agent: [0, .72, 1, 1.55], bottom: [0, .6, 1, 1.7] };
  var VARS = { side: '--side-w', agent: '--agent-w', bottom: '--bottom-h' };
  var CLS = { side: 'rk-no-side', agent: 'rk-no-agent', bottom: 'rk-no-bottom' };
  var state = { side: null, agent: null, bottom: null, last: {} };
  var inResize = false;
  try { var saved = JSON.parse(P.localStorage.getItem(KEY) || '{}'); for (var k in state) { if (saved[k] !== undefined) state[k] = saved[k]; } } catch (e) {}

  function q(sel) { return D.querySelector(sel); }
  function col(name) { var el = q('div.st-key-' + name); return el ? el.closest('[data-testid="stColumn"]') : null; }
  function rect(el) { return el ? el.getBoundingClientRect() : null; }
  function save() { try { P.localStorage.setItem(KEY, JSON.stringify(state)); } catch (e) {} }

  function defaults() {
    var probe = D.createElement('div');
    probe.style.cssText = 'position:fixed;visibility:hidden;pointer-events:none;left:-9999px;top:0;';
    D.body.appendChild(probe);
    var out = {};
    probe.style.width = 'var(--side-w-d)'; out.side = probe.offsetWidth;
    probe.style.width = 'var(--agent-w-d)'; out.agent = probe.offsetWidth;
    probe.style.width = '0'; probe.style.height = 'var(--bottom-h-d)'; out.bottom = probe.offsetHeight;
    D.body.removeChild(probe);
    return out;
  }
  function limits(kind) {
    var vw = P.innerWidth, vh = P.innerHeight;
    var side = state.side === null ? defaults().side : state.side, agent = state.agent === null ? defaults().agent : state.agent;
    if (kind === 'side') return { min: 170, max: Math.max(170, Math.min(640, vw - 58 - agent - 260)), snap: 90 };
    if (kind === 'agent') return { min: 280, max: Math.max(280, Math.min(900, vw - 58 - side - 260)), snap: 160 };
    return { min: 110, max: Math.max(110, vh - 52 - 28 - 170), snap: 60 };
  }
  function current(kind) {
    if (state[kind] !== null) return state[kind];
    return defaults()[kind];
  }
  function apply(kind, px, persist) {
    var lim = limits(kind);
    if (px === null) {
      root.style.removeProperty(VARS[kind]); root.classList.remove(CLS[kind]); state[kind] = null;
    } else if (px < lim.snap) {
      root.style.setProperty(VARS[kind], '0px'); root.classList.add(CLS[kind]);
      if (state[kind]) state.last[kind] = state[kind];
      state[kind] = 0;
    } else {
      px = Math.round(Math.max(lim.min, Math.min(lim.max, px)));
      root.style.setProperty(VARS[kind], px + 'px'); root.classList.remove(CLS[kind]); state[kind] = px;
    }
    if (persist !== false) save();
    place();
    if (!inResize) { inResize = true; try { P.dispatchEvent(new P.Event('resize')); } finally { inResize = false; } }
  }
  function step(kind, dir) {
    var d = defaults()[kind], cur = current(kind), list = PRESETS[kind].map(function (f) { return Math.round(d * f); });
    var target = null, i;
    if (dir < 0) { for (i = list.length - 1; i >= 0; i--) { if (list[i] < cur - 6) { target = list[i]; break; } } if (target === null) target = 0; }
    else { for (i = 0; i < list.length; i++) { if (list[i] > cur + 6) { target = list[i]; break; } } if (target === null) target = list[list.length - 1]; }
    apply(kind, target);
  }
  function toggle(kind) {
    var cur = current(kind);
    if (cur > 0) { apply(kind, 0); } else { apply(kind, state.last[kind] || defaults()[kind]); }
  }

  var handles = {};
  function make(kind, orient, glyphs, labels) {
    var el = D.createElement('div');
    el.className = 'rk-split ' + orient; el.setAttribute('data-rk', kind);
    el.title = 'Drag to resize. Double-click to hide or show.';
    el.innerHTML = '<div class="grip"></div><div class="btns"><button type="button" data-d="-1"></button><button type="button" data-d="1"></button></div>';
    var btns = el.querySelectorAll('button');
    btns[0].textContent = glyphs[0]; btns[0].title = labels[0];
    btns[1].textContent = glyphs[1]; btns[1].title = labels[1];
    btns[0].addEventListener('click', function (e) { e.stopPropagation(); step(kind, -1); });
    btns[1].addEventListener('click', function (e) { e.stopPropagation(); step(kind, 1); });
    btns[0].addEventListener('pointerdown', function (e) { e.stopPropagation(); });
    btns[1].addEventListener('pointerdown', function (e) { e.stopPropagation(); });
    el.addEventListener('dblclick', function (e) { if (e.target.tagName !== 'BUTTON') toggle(kind); });
    el.addEventListener('pointerdown', function (e) {
      if (e.target.tagName === 'BUTTON') return;
      e.preventDefault();
      try { el.setPointerCapture(e.pointerId); } catch (x) {}
      el.classList.add('drag'); root.classList.add('rk-dragging');
      var move = function (ev) {
        if (kind === 'side') { var c = col('sidebar'); var left = (col('activity') ? rect(col('activity')).right : 58); apply('side', ev.clientX - left, false); }
        else if (kind === 'agent') { apply('agent', P.innerWidth - ev.clientX, false); }
        else { apply('bottom', P.innerHeight - 28 - ev.clientY, false); }
      };
      var up = function () {
        el.classList.remove('drag'); root.classList.remove('rk-dragging');
        el.removeEventListener('pointermove', move); el.removeEventListener('pointerup', up); el.removeEventListener('pointercancel', up);
        save();
      };
      el.addEventListener('pointermove', move); el.addEventListener('pointerup', up); el.addEventListener('pointercancel', up);
    });
    D.body.appendChild(el);
    handles[kind] = el;
  }

  function place() {
    var title = q('div.st-key-titlebar'), bar = q('div.st-key-statusbar');
    var top = title ? rect(title).bottom : 52, bottom = bar ? rect(bar).top : P.innerHeight - 28;
    var sc = rect(col('sidebar')), ac = rect(col('agent')), cc = rect(col('centre'));
    if (sc && handles.side) { var x = sc.right; handles.side.style.cssText = 'left:' + Math.max(0, Math.min(P.innerWidth - 12, x - 6)) + 'px;top:' + top + 'px;height:' + (bottom - top) + 'px;'; }
    if (ac && handles.agent) { var xa = ac.left; handles.agent.style.cssText = 'left:' + Math.max(0, Math.min(P.innerWidth - 12, xa - 6)) + 'px;top:' + top + 'px;height:' + (bottom - top) + 'px;'; }
    var bp = q('div.st-key-bottompanel');
    if (cc && handles.bottom) {
      var by = (bp && bp.offsetParent !== null) ? rect(bp).top : bottom;
      handles.bottom.style.cssText = 'left:' + cc.left + 'px;width:' + cc.width + 'px;top:' + Math.max(top + 40, by - 6) + 'px;';
    }
  }

  function hideBadges(doc) {
    try {
      var sel = '[class*="viewerBadge"],[data-testid="manage-app-button"],[class*="_terminalButton_"],[class*="_profileContainer_"],[class*="stDeployButton"]';
      doc.querySelectorAll(sel).forEach(function (el) { el.style.setProperty('display', 'none', 'important'); });
      var walker = doc.createTreeWalker(doc.body, NodeFilter.SHOW_TEXT, null), node, hits = [];
      while ((node = walker.nextNode())) { if (/^\s*Manage app\s*$/i.test(node.nodeValue)) hits.push(node.parentElement); }
      hits.forEach(function (el) {
        var up = el, fixed = null;
        for (var i = 0; i < 8 && up && up !== doc.body; i++, up = up.parentElement) {
          var cs = (doc.defaultView || P).getComputedStyle(up);
          if (cs.position === 'fixed' || cs.position === 'sticky') { fixed = up; break; }
        }
        (fixed || el).style.setProperty('display', 'none', 'important');
      });
    } catch (e) {}
  }
  function docs() {
    var list = [D];
    try { if (P.top && P.top !== P && P.top.document) list.push(P.top.document); } catch (e) {}
    return list;
  }

  var lastBadge = 0;
  function tick() {
    if (!D.body) return;
    if (!handles.side) {
      make('side', 'v', ['\u2039', '\u203A'], ['Shrink the Explorer', 'Widen the Explorer']);
      make('agent', 'v', ['\u203A', '\u2039'], ['Shrink the Agent panel', 'Widen the Agent panel']);
      make('bottom', 'h', ['\u2304', '\u2303'], ['Shrink the Terminal panel', 'Widen the Terminal panel']);
      ['side', 'agent', 'bottom'].forEach(function (kind) { if (state[kind] !== null) apply(kind, state[kind], false); });
    }
    place();
    var chat = q('div.st-key-chat');
    if (chat) {
      if (chat.__rkH === undefined) { chat.scrollTop = chat.scrollHeight; }
      else if (chat.scrollHeight !== chat.__rkH && chat.scrollTop + chat.clientHeight >= chat.__rkH - 90) { chat.scrollTop = chat.scrollHeight; }
      chat.__rkH = chat.scrollHeight;
    }
    var tb = q('div.st-key-termbox');
    if (tb) {
      if (tb.__rkH === undefined || tb.scrollHeight !== tb.__rkH) { tb.scrollTop = tb.scrollHeight; }
      tb.__rkH = tb.scrollHeight;
      var ti = tb.querySelector('input');
      if (ti && ti !== P.__rkTermInput) {
        P.__rkTermInput = ti;
        var ae = D.activeElement;
        if (!ae || ae === D.body) ti.focus({ preventScroll: true });
      }
    }
    var now = Date.now();
    if (now - lastBadge > 1200) { lastBadge = now; docs().forEach(hideBadges); }
  }

  var timer = P.setInterval(tick, 250);
  var onResize = function () {
    if (inResize) return;
    inResize = true;
    try { ['side', 'agent', 'bottom'].forEach(function (kind) { if (state[kind]) apply(kind, state[kind], false); }); place(); } finally { inResize = false; }
  };
  P.addEventListener('resize', onResize);
  P.__rkLayout = {
    v: VERSION, tick: tick,
    stop: function () {
      P.clearInterval(timer); P.removeEventListener('resize', onResize);
      for (var k in handles) { if (handles[k].parentNode) handles[k].parentNode.removeChild(handles[k]); }
    }
  };
  tick();
})();
</script>
""".replace("__VERSION__", str(VERSION))


def install_layout() -> None:
    components.html(SCRIPT, height=0)
