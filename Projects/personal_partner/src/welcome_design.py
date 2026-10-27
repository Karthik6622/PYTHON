"""Landing-page design for WithYou: nav bar, hero with product preview, feature cards and footer.

HTML strings contain no blank lines or indentation, otherwise Markdown ends the HTML block early.
The CSS is injected only while the welcome view is shown, so other views keep the shared styles.
"""

import html

from .styles import BRAND_HTML, BRAND_MARK_SVG

WELCOME_FONT_CSS = "<style>@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');</style>"

WELCOME_CSS = """
<style>
/* Page canvas */
.stApp, [data-testid="stAppViewContainer"] {
  background:
    radial-gradient(760px 460px at 88% -4%, rgba(233,160,109,.30), transparent 62%),
    radial-gradient(820px 520px at -6% 8%, rgba(43,140,126,.24), transparent 62%),
    radial-gradient(700px 420px at 50% 108%, rgba(11,93,85,.10), transparent 60%),
    #f4f9f7 !important;
}
[data-testid="stMain"], [data-testid="stHeader"] { background: transparent !important; }
.block-container { max-width: 1180px; padding-top: clamp(3.6rem, 6vw, 4.2rem); }
.st-key-ks_welcome { gap: clamp(1.6rem, 4vw, 3rem); font-family: 'Plus Jakarta Sans', system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif; }
.st-key-ks_welcome h1, .st-key-ks_welcome p, .st-key-ks_welcome button, .st-key-ks_welcome a, .st-key-ks_welcome strong { font-family: inherit; }

/* Navigation */
.st-key-ks_nav { position: relative; z-index: 5; background: rgba(255,255,255,.72); border: 1px solid rgba(215,228,225,.9); border-radius: 999px;
  padding: .55rem .6rem .55rem 1.2rem; box-shadow: 0 14px 34px -26px rgba(16,47,50,.55); -webkit-backdrop-filter: blur(14px); backdrop-filter: blur(14px); }
.st-key-ks_nav [data-testid="stHorizontalBlock"] { flex-wrap: nowrap !important; gap: .4rem !important; align-items: center; }
.st-key-ks_nav .stColumn { flex: 0 0 auto !important; width: auto !important; min-width: 0 !important; }
.st-key-ks_nav .stColumn:first-child { flex: 1 1 auto !important; }
.st-key-ks_nav .ks-brand { font-size: 1.28rem; }
.stApp .st-key-nav_login [data-testid^="stBaseButton"] { background: transparent !important; border: 0 !important; box-shadow: none !important; color: var(--ks-ink) !important;
  min-height: 2.5rem; padding: 0 1rem; border-radius: 999px !important; font-weight: 600; }
.stApp .st-key-nav_login [data-testid^="stBaseButton"]:hover { background: var(--ks-soft) !important; color: var(--ks-brand-dark) !important; }
.stApp .st-key-nav_signup [data-testid^="stBaseButton"] { background: var(--ks-ink) !important; border: 1px solid var(--ks-ink) !important; color: #fff !important;
  -webkit-text-fill-color: #fff; min-height: 2.5rem; padding: 0 1.3rem; border-radius: 999px !important; font-weight: 700; box-shadow: 0 10px 20px -12px rgba(16,47,50,.8); }
.stApp .st-key-nav_signup [data-testid^="stBaseButton"]:hover { background: var(--ks-brand) !important; border-color: var(--ks-brand) !important; transform: translateY(-1px); }

/* Hero */
@media (min-width: 901px) {
  .st-key-ks_hero [data-testid="stHorizontalBlock"]:has(.st-key-ks_cta) { flex-wrap: nowrap !important; gap: clamp(2rem, 5vw, 4.5rem) !important; align-items: center; }
  .st-key-ks_hero [data-testid="stHorizontalBlock"]:has(.st-key-ks_cta) > .stColumn { min-width: 0 !important; width: auto !important; }
  .st-key-ks_hero [data-testid="stHorizontalBlock"]:has(.st-key-ks_cta) > .stColumn:nth-child(1) { flex: 1.1 1 0 !important; }
  .st-key-ks_hero [data-testid="stHorizontalBlock"]:has(.st-key-ks_cta) > .stColumn:nth-child(2) { flex: .9 1 0 !important; }
}
.ks-w-badge { display: inline-flex; align-items: center; gap: .55rem; padding: .42rem .95rem .42rem .5rem; border-radius: 999px; background: rgba(255,255,255,.85);
  border: 1px solid var(--ks-line); color: var(--ks-brand-dark); font-weight: 700; font-size: .72rem; letter-spacing: .12em; text-transform: uppercase;
  box-shadow: 0 8px 20px -16px rgba(11,93,85,.7); }
.ks-w-badge i { width: 1.35rem; height: 1.35rem; border-radius: 50%; background: linear-gradient(135deg, #0b5d55, #2b8c7e); display: inline-flex; align-items: center; justify-content: center; }
.ks-w-badge svg { width: .8rem; height: .8rem; fill: #fff; }
.ks-w-hello { color: var(--ks-brand); font-weight: 700; margin: 1rem 0 0; }
.stApp h1.ks-w-title { color: var(--ks-ink); font-size: clamp(2.35rem, 5.2vw, 4.2rem); line-height: 1.04; font-weight: 800; letter-spacing: -.04em; margin: 1.1rem 0 1.15rem; padding: 0; }
.ks-w-title a { display: none !important; }
.ks-w-grad { background: linear-gradient(100deg, #0b5d55 0%, #2b8c7e 50%, #c7743f 100%); -webkit-background-clip: text; background-clip: text; color: transparent; -webkit-text-fill-color: transparent; }
.stApp p.ks-w-lead { color: var(--ks-muted); font-size: clamp(1.02rem, 1.6vw, 1.2rem); line-height: 1.7; max-width: 52ch; margin: 0 0 .4rem; }

.st-key-ks_cta { max-width: 520px; gap: .8rem; margin-top: .8rem; }
.st-key-ks_cta [data-testid="stHorizontalBlock"] { gap: .75rem !important; }
.stApp .st-key-welcome_login [data-testid^="stBaseButton"] { min-height: 3.35rem; border-radius: 999px !important; font-size: 1.02rem; font-weight: 700;
  background: linear-gradient(135deg, #0b5d55 0%, #1d7a6d 100%) !important; border: 0 !important; box-shadow: 0 16px 28px -14px rgba(11,93,85,.85);
  transition: transform .15s ease, box-shadow .15s ease; }
.stApp .st-key-welcome_login [data-testid^="stBaseButton"]:hover { transform: translateY(-2px); box-shadow: 0 20px 32px -14px rgba(11,93,85,.9); background: linear-gradient(135deg, #08463f 0%, #0b5d55 100%) !important; }
.stApp .st-key-welcome_signup [data-testid^="stBaseButton"] { min-height: 3.35rem; border-radius: 999px !important; font-size: 1.02rem; font-weight: 700;
  background: rgba(255,255,255,.9) !important; border: 1.5px solid var(--ks-brand) !important; color: var(--ks-brand-dark) !important; -webkit-text-fill-color: var(--ks-brand-dark); }
.stApp .st-key-welcome_signup [data-testid^="stBaseButton"]:hover { background: var(--ks-soft) !important; transform: translateY(-2px); }
.st-key-ks_cta .ks-or { margin: .5rem 0 .1rem; font-size: .85rem; }
.stApp .st-key-welcome_google [data-testid^="stBaseButton"], .stApp .st-key-welcome_github a { min-height: 3rem; border-radius: 999px !important; background: rgba(255,255,255,.92) !important; font-weight: 600; }
.ks-w-trust { display: flex; gap: .65rem; align-items: flex-start; max-width: 520px; margin-top: .6rem; color: var(--ks-muted); font-size: .86rem; line-height: 1.55; }
.ks-w-trust svg { flex: none; width: 1.05rem; height: 1.05rem; margin-top: .15rem; stroke: var(--ks-brand); fill: none; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }

/* Product preview */
.ks-w-stage { position: relative; width: 100%; max-width: 470px; margin: 0 auto; padding: 2.2rem 0; }
.ks-w-blob { position: absolute; border-radius: 50%; filter: blur(46px); z-index: 0; }
.ks-w-blob.b1 { width: 62%; aspect-ratio: 1; background: rgba(233,160,109,.55); top: 0; right: -6%; }
.ks-w-blob.b2 { width: 56%; aspect-ratio: 1; background: rgba(43,140,126,.45); bottom: 0; left: -8%; }
.ks-w-mock { position: relative; z-index: 1; background: #fff; border: 1px solid var(--ks-line); border-radius: 30px; padding: 1.15rem 1.15rem 1.3rem;
  box-shadow: 0 40px 70px -34px rgba(16,47,50,.55), 0 10px 24px -16px rgba(16,47,50,.25); transform: rotate(1.6deg); }
.ks-w-mhead { display: flex; align-items: center; gap: .7rem; padding: .1rem .2rem .95rem; margin-bottom: .85rem; border-bottom: 1px solid var(--ks-line); }
.ks-w-mhead svg { width: 38px; height: 38px; flex: none; }
.ks-w-mhead b { display: block; color: var(--ks-ink); font-size: 1rem; line-height: 1.2; }
.ks-w-mhead small { display: flex; align-items: center; gap: .35rem; color: var(--ks-muted); font-size: .78rem; }
.ks-w-mhead small i { width: .5rem; height: .5rem; border-radius: 50%; background: #2fbf8f; box-shadow: 0 0 0 3px rgba(47,191,143,.22); }
.ks-w-msg { max-width: 86%; padding: .75rem 1rem; border-radius: 20px; font-size: .93rem; line-height: 1.5; margin: 0 0 .6rem; }
.ks-w-msg.them { background: var(--ks-soft); color: var(--ks-ink); border-bottom-left-radius: 6px; }
.ks-w-msg.me { background: linear-gradient(135deg, #0b5d55, #1d7a6d); color: #fff; margin-left: auto; border-bottom-right-radius: 6px; }
.ks-w-typing { display: inline-flex; gap: .3rem; padding: .7rem .95rem; border-radius: 18px; background: var(--ks-soft); }
.ks-w-typing i { width: .45rem; height: .45rem; border-radius: 50%; background: var(--ks-teal); animation: ks-w-bounce 1.2s infinite ease-in-out; }
.ks-w-typing i:nth-child(2) { animation-delay: .15s; }
.ks-w-typing i:nth-child(3) { animation-delay: .3s; }
@keyframes ks-w-bounce { 0%, 80%, 100% { transform: translateY(0); opacity: .45; } 40% { transform: translateY(-4px); opacity: 1; } }
.ks-w-chip { position: absolute; z-index: 2; display: inline-flex; align-items: center; gap: .5rem; padding: .55rem .95rem; border-radius: 999px; background: #fff;
  border: 1px solid var(--ks-line); color: var(--ks-ink); font-size: .82rem; font-weight: 700; box-shadow: 0 18px 30px -18px rgba(16,47,50,.5); animation: ks-float 7s ease-in-out infinite; }
.ks-w-chip svg { width: 1rem; height: 1rem; stroke: var(--ks-brand); fill: none; stroke-width: 1.9; stroke-linecap: round; stroke-linejoin: round; }
.ks-w-chip.c1 { top: .4rem; left: -1.2rem; }
.ks-w-chip.c2 { bottom: .6rem; right: -.8rem; animation-delay: -3s; }
.ks-w-chip.c2 svg { fill: #e9a06d; stroke: #e9a06d; }

/* Feature cards */
.ks-w-features { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 1.2rem; }
.ks-w-card { position: relative; padding: 1.6rem 1.5rem 1.7rem; border-radius: 26px; background: rgba(255,255,255,.88); border: 1px solid var(--ks-line);
  box-shadow: 0 18px 36px -30px rgba(16,47,50,.6); transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease; }
.ks-w-card:hover { transform: translateY(-6px); border-color: #b9d6cf; box-shadow: 0 28px 44px -28px rgba(11,93,85,.55); }
.ks-w-icon { width: 3.1rem; height: 3.1rem; border-radius: 16px; display: flex; align-items: center; justify-content: center; margin-bottom: 1.1rem;
  background: linear-gradient(135deg, #e3f3ee, #fdeee2); border: 1px solid #d3e6e0; }
.ks-w-icon svg { width: 1.4rem; height: 1.4rem; stroke: var(--ks-brand); fill: none; stroke-width: 1.8; stroke-linecap: round; stroke-linejoin: round; }
.ks-w-card h3 { margin: 0 0 .5rem; padding: 0; color: var(--ks-ink); font-size: 1.12rem; font-weight: 800; letter-spacing: -.02em; line-height: 1.3; }
.ks-w-card h3 a { display: none !important; }
.stApp .ks-w-card p { margin: 0; color: var(--ks-muted); font-size: .97rem; line-height: 1.65; }

/* Footer */
.ks-w-footer { display: flex; align-items: center; justify-content: space-between; gap: .75rem 1.5rem; flex-wrap: wrap; padding: 1.4rem .2rem 0; border-top: 1px solid var(--ks-line);
  color: var(--ks-muted); font-size: .88rem; }
.ks-w-footer .l { display: flex; align-items: center; gap: .8rem; flex-wrap: wrap; }
.ks-w-footer .ks-brand { font-size: 1.05rem; }
.ks-w-footer .ks-brand svg { width: 24px; height: 24px; }
.ks-w-footer strong { color: var(--ks-brand); font-weight: 800; }

@media (max-width: 900px) {
  .ks-w-features { grid-template-columns: 1fr; }
  .ks-w-stage { max-width: 440px; margin-top: 1.2rem; }
  .ks-w-chip.c1 { left: -.2rem; }
  .ks-w-chip.c2 { right: -.2rem; }
}
@media (max-width: 640px) {
  .st-key-nav_signup { display: none; }
  .st-key-ks_nav { padding: .45rem .5rem .45rem 1rem; }
  .ks-w-br { display: none; }
  .ks-w-mock { transform: none; }
  .ks-w-footer { flex-direction: column; text-align: center; }
  .ks-w-footer .l { justify-content: center; }
}
@media (prefers-reduced-motion: reduce) { .ks-w-chip, .ks-w-typing i { animation: none !important; } }
</style>
"""

_LOCK = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2.5"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>'
_CHAT = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-7l-5 4v-4H5a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2Z"/></svg>'
_SLIDERS = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h9M17 7h3M4 17h3M11 17h9"/><circle cx="15" cy="7" r="2"/><circle cx="9" cy="17" r="2"/></svg>'
_HEART = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 21s-7-4.35-7-10a4 4 0 0 1 7-2.6A4 4 0 0 1 19 11c0 5.65-7 10-7 10Z"/></svg>'
_SPARK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 2l1.9 6.1L20 10l-6.1 1.9L12 18l-1.9-6.1L4 10l6.1-1.9L12 2Z"/></svg>'


def nav_brand_html() -> str:
    return BRAND_HTML


def hero_text_html(display_name: str = "") -> str:
    hello = f'<p class="ks-w-hello">Welcome back, {html.escape(display_name)}</p>' if display_name else ""
    return (
        f'<div class="ks-w-badge"><i>{_SPARK}</i>Your personal space to talk, think &amp; grow</div>'
        f'{hello}'
        '<h1 class="ks-w-title">Here for whatever<br class="ks-w-br"> <span class="ks-w-grad">is on your mind.</span></h1>'
        '<p class="ks-w-lead">WithYou is your personal AI companion for everyday conversations, questions, ideas, planning, reflection, '
        'and encouragement, all in one private space.</p>'
    )


def trust_html() -> str:
    return (
        f'<div class="ks-w-trust">{_LOCK}<span>Your conversations are connected to your account and designed to stay personal to you. '
        'WithYou is an AI assistant, not a human, therapist, doctor, or emergency service.</span></div>'
    )


def preview_html() -> str:
    return (
        '<div class="ks-w-stage" aria-hidden="true">'
        '<div class="ks-w-blob b1"></div><div class="ks-w-blob b2"></div>'
        f'<div class="ks-w-chip c1">{_LOCK}Private by design</div>'
        '<div class="ks-w-mock">'
        f'<div class="ks-w-mhead">{BRAND_MARK_SVG}<div><b>WithYou</b><small><i></i>Here with you</small></div></div>'
        '<div class="ks-w-msg them">Good evening. How did today go?</div>'
        '<div class="ks-w-msg me">Long day. I have a big presentation tomorrow and I am a little nervous.</div>'
        '<div class="ks-w-msg them">That is a lot to carry. Want to talk it through, or shall we plan a quick run-through together?</div>'
        '<div class="ks-w-typing"><i></i><i></i><i></i></div>'
        '</div>'
        f'<div class="ks-w-chip c2">{_HEART}Warm, natural replies</div>'
        '</div>'
    )


def _card(icon: str, title: str, text: str) -> str:
    return f'<div class="ks-w-card"><div class="ks-w-icon">{icon}</div><h3>{title}</h3><p>{text}</p></div>'


def features_html() -> str:
    return (
        '<div class="ks-w-features">'
        + _card(_LOCK, "Your conversations, your space", "Your chats stay connected to your account, so you can come back anytime and continue where you left off.")
        + _card(_CHAT, "Always ready to talk", "Ask a question, share a thought, make a plan, or simply have a conversation whenever you need one.")
        + _card(_SLIDERS, "Made to feel personal", "Choose how you like to chat and enjoy responses that feel warm, natural, and helpful.")
        + '</div>'
    )


def footer_html() -> str:
    return (
        f'<footer class="ks-w-footer"><div class="l">{BRAND_HTML}<span>A personal AI companion</span></div>'
        '<div>Powered by <strong>RK</strong></div></footer>'
    )
