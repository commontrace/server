# Global Savings Counter (Frontend) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (- [ ]) syntax for tracking.

**Goal:** Render a live "the commons has saved ~N hours / ~$M of agent work" counter on the CommonTrace landing page, fed by `GET /api/v1/analytics/savings`, fully internationalized across all 9 languages, and silent when the endpoint is empty or unreachable.

**Architecture:** The frontend is a Jinja2 static-site generator (`build.py`) that emits one HTML tree per language into `_site/`. The counter is a progressively-enhanced widget: static HTML markup carrying i18n strings as `data-*` attributes (the established `static/search.js` pattern, because client JS cannot call the build-time `t()` helper), hydrated at runtime by a new `static/savings-counter.js` that fetches the global sums and fills the numbers (the established `templates/dashboard.html` fetch idiom). **No LLM is involved anywhere.** Every number on screen is either a real measured token/minute count summed server-side from the append-only `savings_ledger`, or a money figure that is `tokens × a single published $/Mtok price constant` — never a value asked of a model. The frontend only *displays* sums the server already computed; it performs no estimation. Hours are derived purely by arithmetic (`minutes / 60`).

**Tech Stack:** Python 3.12, Jinja2, vanilla JavaScript (`fetch`, no framework), `translations.json` flat-key i18n, GitHub Actions build-check CI. Tests are Python assertion scripts run with the repo's build venv (the repo has no pytest harness; CI is `python build.py` + `test -f _site/index.html`).

---

## File Structure

| File | Status | Responsibility |
|------|--------|----------------|
| `/tmp/ct-frontend/translations.json` | Modify | Add 6 `home.savings_*` i18n keys to all 9 language blocks (en, fr, zh, es, pt, de, ja, ar, hi). |
| `/tmp/ct-frontend/templates/home.html` | Modify | Add the counter's static markup (hidden by default, carrying i18n `data-*` attributes) below the hero stats; add its scoped CSS in `{% block head %}`; load `savings-counter.js` in `{% block scripts %}`. |
| `/tmp/ct-frontend/static/savings-counter.js` | Create | Fetch `/api/v1/analytics/savings`, format hours + dollars, reveal the counter on success with data; leave it hidden (graceful empty-state) on zero/error/unreachable. |
| `/tmp/ct-frontend/tests/test_savings_counter.py` | Create | Build-check + assertions: all 9 i18n keys present in every language; counter markup + `data-*` attrs + script tag present in generated `_site/index.html` and `_site/fr/index.html`; the JS file is copied to `_site/static/`; `build.py` runs clean. |
| `/tmp/ct-frontend/tests/test_savings_counter_render.js` | Create | Node-only unit test of the JS formatting/reveal logic against a sample endpoint payload (no network): verifies hours/dollars formatting, reveal-on-data, stay-hidden-on-empty, stay-hidden-on-error. |

**Pre-flight (one-time, not a task):** ensure the build venv exists and the baseline build is green.

```bash
test -d /tmp/ctfe-venv || python3 -m venv /tmp/ctfe-venv
/tmp/ctfe-venv/bin/pip install -q jinja2 pygments markdown nh3
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python build.py >/dev/null && test -f _site/index.html && echo "BASELINE GREEN"
```

Expected output ends with: `BASELINE GREEN`

`node` (any v18+) must be on PATH for the JS unit test. Verify: `node --version` prints a version. If `node` is unavailable, skip Task 4 only; the build-check test (Task 3) plus the rendered-markup assertions still fully cover the deliverable, and CI does not run the JS test.

---

## Endpoint contract (consumed, not built here)

The server phase (spec phase 4) builds `GET /api/v1/analytics/savings`. This frontend phase **consumes** it. The contract this plan codes against — matching the spec's "returns global sums" and the existing `analytics.py` no-auth GET-returns-`dict` convention:

```json
{
  "total_minutes_saved": 18240,
  "total_tokens_saved": 412000000,
  "total_usd_saved": 8.24,
  "event_count": 1530
}
```

- `total_minutes_saved` — integer, real summed minutes from the `savings_ledger`. Hours shown = `total_minutes_saved / 60`.
- `total_usd_saved` — number, computed **server-side** as `total_tokens_saved / 1_000_000 × price_per_mtok` (the single published price constant). The frontend renders it verbatim; it never multiplies a model's guess.
- `total_tokens_saved`, `event_count` — present for completeness; `event_count` gates the reveal (0 ⇒ stay hidden).
- Graceful fallback: if `total_usd_saved` is absent/null but minutes exist, the counter shows only the hours clause (no fabricated dollar value).

All four fields are real arithmetic over recorded counts. Flagged for the user below (see Self-Review d).

---

## Task 1 — Add the 6 i18n keys to all 9 languages

**Files:**
- Modify: `/tmp/ct-frontend/translations.json` — insert after `home.footer_tagline` in each language block (en line 48, fr 308, zh 435, es 562, pt 822, de 949, ja 1076, ar 1203, hi 1330; the key after it is always `browse.title`).
- Test: `/tmp/ct-frontend/tests/test_savings_counter.py` (the i18n portion; full file written in Task 3).

The 6 keys (flat dotted keys, exactly matching the file's existing `home.*` convention). `{hours}` and `{dollars}` are the same `{name}` placeholder syntax `make_translator` already substitutes (`build.py:109-111`):

| Key | Purpose |
|-----|---------|
| `home.savings_eyebrow` | Small label above the counter (e.g. "Collective impact") |
| `home.savings_hours` | The hours clause, with `{hours}` placeholder |
| `home.savings_money` | The money clause, with `{dollars}` placeholder |
| `home.savings_joiner` | Word joining the two clauses (e.g. "and") |
| `home.savings_suffix` | Trailing phrase (e.g. "of agent work") |
| `home.savings_approx` | The `~` approximation marker (kept as a key so RTL/locale variants can adjust it) |

### Step 1: Write the failing test (i18n-keys portion)

- [ ] Create `/tmp/ct-frontend/tests/` directory and write `/tmp/ct-frontend/tests/test_savings_counter.py` with the i18n check first (the remaining checks are added in Task 3; write the whole file now so it fails for the right reason):

```python
"""Build-check tests for the global savings counter (frontend).

Run from the repo root with the build venv:
    /tmp/ctfe-venv/bin/python tests/test_savings_counter.py

No pytest: this is a plain assertion script, matching the repo's
build-check CI (python build.py + test -f _site/index.html).
"""

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
TRANSLATIONS = REPO / "translations.json"
SITE = REPO / "_site"

SUPPORTED_LANGS = ["en", "fr", "zh", "es", "pt", "de", "ja", "ar", "hi"]
SAVINGS_KEYS = [
    "home.savings_eyebrow",
    "home.savings_hours",
    "home.savings_money",
    "home.savings_joiner",
    "home.savings_suffix",
    "home.savings_approx",
]

failures = []


def check(cond, msg):
    if not cond:
        failures.append(msg)


def test_i18n_keys_present_all_langs():
    data = json.loads(TRANSLATIONS.read_text())
    for lang in SUPPORTED_LANGS:
        block = data.get(lang)
        check(block is not None, f"[i18n] language block missing: {lang}")
        if block is None:
            continue
        for key in SAVINGS_KEYS:
            check(
                key in block and isinstance(block[key], str) and block[key].strip() != "",
                f"[i18n] {lang} missing non-empty key: {key}",
            )
        # Placeholders must survive in the clause keys.
        check("{hours}" in block.get("home.savings_hours", ""),
              f"[i18n] {lang} home.savings_hours missing {{hours}} placeholder")
        check("{dollars}" in block.get("home.savings_money", ""),
              f"[i18n] {lang} home.savings_money missing {{dollars}} placeholder")


def test_build_runs_clean():
    proc = subprocess.run(
        [sys.executable, "build.py"],
        cwd=str(REPO),
        capture_output=True,
        text=True,
    )
    check(proc.returncode == 0, f"[build] build.py exited {proc.returncode}: {proc.stderr[-500:]}")
    check((SITE / "index.html").exists(), "[build] _site/index.html not generated")


def test_counter_markup_in_generated_html():
    en = (SITE / "index.html").read_text()
    fr = (SITE / "fr" / "index.html").read_text()
    for label, html in (("en", en), ("fr", fr)):
        check('id="savings-counter"' in html,
              f"[markup:{label}] #savings-counter element missing")
        check('class="savings-counter"' in html,
              f"[markup:{label}] .savings-counter class missing")
        check('hidden' in html.split('id="savings-counter"', 1)[1][:200],
              f"[markup:{label}] counter not hidden-by-default")
        check('data-hours-template=' in html,
              f"[markup:{label}] data-hours-template attr missing")
        check('data-money-template=' in html,
              f"[markup:{label}] data-money-template attr missing")
        check('data-joiner=' in html,
              f"[markup:{label}] data-joiner attr missing")
        check('data-suffix=' in html,
              f"[markup:{label}] data-suffix attr missing")
        check('data-approx=' in html,
              f"[markup:{label}] data-approx attr missing")
        check('savings-counter.js' in html,
              f"[markup:{label}] savings-counter.js script tag missing")
    # FR must carry the French clause, proving i18n flows into markup.
    check("heures" in fr or "heure" in fr,
          "[markup:fr] French hours clause not found in data attributes")


def test_js_asset_copied():
    check((SITE / "static" / "savings-counter.js").exists(),
          "[asset] _site/static/savings-counter.js not copied by build")


def main():
    test_i18n_keys_present_all_langs()
    test_build_runs_clean()
    test_counter_markup_in_generated_html()
    test_js_asset_copied()
    if failures:
        print("FAIL")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("PASS: savings counter build-checks green")


if __name__ == "__main__":
    main()
```

### Step 2: Run the test — expect FAIL on the i18n keys

- [ ] Run:

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python tests/test_savings_counter.py
```

Expected: exits non-zero, prints `FAIL`, with lines including `[i18n] en missing non-empty key: home.savings_eyebrow` (and the same for fr, zh, es, pt, de, ja, ar, hi). It will also list the markup/asset failures — expected, those are implemented in Tasks 2-3.

### Step 3: Add the keys (minimal implementation)

- [ ] In `/tmp/ct-frontend/translations.json`, insert the 6 keys **immediately after** the `home.footer_tagline` line in **each** language block. Each insertion is the exact translated block below (4-space indent matching the file). The English block, inserted after line 48:

```json
    "home.savings_eyebrow": "Collective impact",
    "home.savings_hours": "saved ~{hours} hours",
    "home.savings_money": "~${dollars}",
    "home.savings_joiner": "and",
    "home.savings_suffix": "of agent work",
    "home.savings_approx": "~",
```

French (after `home.footer_tagline` in the `fr` block):

```json
    "home.savings_eyebrow": "Impact collectif",
    "home.savings_hours": "a économisé ~{hours} heures",
    "home.savings_money": "~{dollars} $",
    "home.savings_joiner": "et",
    "home.savings_suffix": "de travail d'agent",
    "home.savings_approx": "~",
```

Chinese (`zh`):

```json
    "home.savings_eyebrow": "集体影响",
    "home.savings_hours": "已节省约 {hours} 小时",
    "home.savings_money": "约 {dollars} 美元",
    "home.savings_joiner": "以及",
    "home.savings_suffix": "的智能体工作量",
    "home.savings_approx": "约",
```

Spanish (`es`):

```json
    "home.savings_eyebrow": "Impacto colectivo",
    "home.savings_hours": "ha ahorrado ~{hours} horas",
    "home.savings_money": "~{dollars} $",
    "home.savings_joiner": "y",
    "home.savings_suffix": "de trabajo de agentes",
    "home.savings_approx": "~",
```

Portuguese (`pt`):

```json
    "home.savings_eyebrow": "Impacto coletivo",
    "home.savings_hours": "economizou ~{hours} horas",
    "home.savings_money": "~{dollars} $",
    "home.savings_joiner": "e",
    "home.savings_suffix": "de trabalho de agentes",
    "home.savings_approx": "~",
```

German (`de`):

```json
    "home.savings_eyebrow": "Kollektive Wirkung",
    "home.savings_hours": "hat ~{hours} Stunden gespart",
    "home.savings_money": "~{dollars} $",
    "home.savings_joiner": "und",
    "home.savings_suffix": "an Agentenarbeit",
    "home.savings_approx": "~",
```

Japanese (`ja`):

```json
    "home.savings_eyebrow": "集合的なインパクト",
    "home.savings_hours": "約 {hours} 時間を節約しました",
    "home.savings_money": "約 {dollars} ドル",
    "home.savings_joiner": "および",
    "home.savings_suffix": "のエージェント作業",
    "home.savings_approx": "約",
```

Arabic (`ar`):

```json
    "home.savings_eyebrow": "الأثر الجماعي",
    "home.savings_hours": "وفّر نحو {hours} ساعة",
    "home.savings_money": "نحو {dollars} دولار",
    "home.savings_joiner": "و",
    "home.savings_suffix": "من عمل الوكلاء",
    "home.savings_approx": "نحو",
```

Hindi (`hi`):

```json
    "home.savings_eyebrow": "सामूहिक प्रभाव",
    "home.savings_hours": "ने लगभग {hours} घंटे बचाए",
    "home.savings_money": "लगभग {dollars} डॉलर",
    "home.savings_joiner": "और",
    "home.savings_suffix": "एजेंट कार्य के",
    "home.savings_approx": "लगभग",
```

- [ ] After all 9 insertions, validate the JSON is still well-formed:

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python -c "import json; d=json.load(open('translations.json')); print('keys per lang:', {k: len(v) for k,v in d.items()})"
```

Expected: prints a dict; each language's count is exactly 6 higher than its pre-edit count (e.g. `en` was 258 → now 264; `fr` was 125 → now 131). If `json.load` raises, a comma/brace is wrong — fix before proceeding.

### Step 4: Run the test — expect the i18n check to PASS (markup/asset still fail)

- [ ] Run:

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python tests/test_savings_counter.py
```

Expected: still exits non-zero (`FAIL`), but the `[i18n]` lines are **gone**. Remaining failures are only `[markup:...]` and `[asset]` (and possibly `[markup:fr] French hours clause not found` — addressed in Task 2). This confirms the keys landed correctly.

### Step 5: Commit

- [ ] Commit:

```bash
cd /tmp/ct-frontend && git add translations.json tests/test_savings_counter.py && git commit -m "i18n(home): add savings-counter keys for all 9 languages

Adds home.savings_{eyebrow,hours,money,joiner,suffix,approx} to en, fr,
zh, es, pt, de, ja, ar, hi. Money is tokens x published price (server-
computed); no LLM involved. Test scaffolding added (markup/asset checks
pending Tasks 2-3).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 2 — Add the counter markup + CSS to the homepage template

**Files:**
- Modify: `/tmp/ct-frontend/templates/home.html` — markup inside `{% block content %}` (the hero, around line 460-463); CSS inside `{% block head %}` `<style>` (before the closing `</style>` at line 433); script tag inside `{% block scripts %}` (before `{% endblock %}` at line 598).
- Test: `/tmp/ct-frontend/tests/test_savings_counter.py` (the `test_counter_markup_in_generated_html` portion, already written in Task 1).

The markup is **hidden by default** (`hidden` attribute) and carries all i18n strings as `data-*` attributes, because `static/savings-counter.js` runs client-side and cannot call the Jinja `t()` helper — this mirrors how `static/search.js` reads `data-i18n-*` from `templates/index.html`. The counter is revealed by JS only when real data arrives (graceful empty-state: no data ⇒ stays hidden, exactly like the dashboard's loading/error cells render nothing useful rather than fabricate).

### Step 1: Write the failing test

The markup assertions already exist in `tests/test_savings_counter.py` (`test_counter_markup_in_generated_html`, written in Task 1). No new test code is needed for this task — the relevant checks are the `[markup:en]`, `[markup:fr]`, and `[markup:fr] French hours clause` assertions.

- [ ] (No-op for test authoring — proceed to Step 2 to observe the current failing state.)

### Step 2: Run the test — expect FAIL on markup

- [ ] Run:

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python tests/test_savings_counter.py
```

Expected: `FAIL` with lines including `[markup:en] #savings-counter element missing` and `[markup:fr] #savings-counter element missing` and `[asset] _site/static/savings-counter.js not copied by build`.

### Step 3: Add markup, CSS, and script tag (minimal implementation)

- [ ] **Markup.** In `/tmp/ct-frontend/templates/home.html`, replace the existing hero stats block (lines 460-463):

```html
      <div class="hero__stats">
        {{ total_traces }} traces &middot; {{ all_tags|length }} categories &middot; {{ top_languages|length }}+ languages
      </div>
```

with (keeps the existing stats line unchanged; appends the hidden counter directly beneath it):

```html
      <div class="hero__stats">
        {{ total_traces }} traces &middot; {{ all_tags|length }} categories &middot; {{ top_languages|length }}+ languages
      </div>

      <div
        class="savings-counter"
        id="savings-counter"
        hidden
        data-eyebrow="{{ t('home.savings_eyebrow') }}"
        data-hours-template="{{ t('home.savings_hours') }}"
        data-money-template="{{ t('home.savings_money') }}"
        data-joiner="{{ t('home.savings_joiner') }}"
        data-suffix="{{ t('home.savings_suffix') }}"
        data-approx="{{ t('home.savings_approx') }}">
        <span class="savings-counter__eyebrow">{{ t('home.savings_eyebrow') }}</span>
        <span class="savings-counter__line" id="savings-counter-line"></span>
      </div>
```

- [ ] **CSS.** In the same file, insert the following rules into `{% block head %}` immediately **before** the closing `</style>` (line 433, just after the `@media (prefers-reduced-motion: reduce)` block ending at line 432). Wikipedia/community light aesthetic: muted tertiary eyebrow, secondary body text, the project accent on the numbers, no card/box, no dark surface:

```css

/* ---- Global savings counter (hidden until data arrives) ---- */
.savings-counter {
  margin-top: 1.25rem;
  font-family: var(--font-body, 'Source Sans 3', sans-serif);
  line-height: 1.5;
}

.savings-counter[hidden] {
  display: none;
}

.savings-counter__eyebrow {
  display: block;
  font-family: var(--font-heading, 'Roboto Slab', serif);
  font-size: 0.7rem;
  font-weight: 400;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--text-tertiary, #72777d);
  margin-bottom: 0.25rem;
}

.savings-counter__line {
  font-size: 0.95rem;
  color: var(--text-secondary, #54595d);
}

.savings-counter__num {
  font-weight: 700;
  color: var(--accent, #3366cc);
  font-variant-numeric: tabular-nums;
}
```

- [ ] **Script tag.** In `{% block scripts %}`, add the loader **before** the `{% endblock %}` at line 598 (immediately after the closing `</script>` of the existing homepage IIFE at line 597):

```html
<script src="/static/savings-counter.js?v={{ build_version }}"></script>
```

### Step 4: Run the test — markup assertions PASS (asset still fails)

- [ ] Run:

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python tests/test_savings_counter.py
```

Expected: still `FAIL`, but **all `[markup:...]` lines are gone** (including the French clause check, since `t('home.savings_hours')` for `fr` = `"a économisé ~{hours} heures"` renders into `data-hours-template`, so "heures" appears in `_site/fr/index.html`). The only remaining failure is `[asset] _site/static/savings-counter.js not copied by build` — implemented in Task 3.

### Step 5: Commit

- [ ] Commit:

```bash
cd /tmp/ct-frontend && git add templates/home.html && git commit -m "feat(home): add hidden global savings counter markup + CSS

Counter sits under the hero stats, hidden by default, carrying all i18n
strings as data-* attributes (search.js pattern) for client hydration.
Wikipedia light aesthetic: accent numbers, muted labels, no dark surface.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 3 — Implement the fetch/format/reveal JS and finish the build-check test

**Files:**
- Create: `/tmp/ct-frontend/static/savings-counter.js` — fetch, format, reveal-or-stay-hidden.
- Test: `/tmp/ct-frontend/tests/test_savings_counter.py` (the `test_js_asset_copied` portion, already written in Task 1).

`build.py` copies every file in `static/` into `_site/static/` wholesale (`build.py:168-170`), so creating `static/savings-counter.js` makes the build emit it automatically — no `build.py` change required. The JS mirrors the dashboard fetch idiom (`templates/dashboard.html:318-329`): a fixed `API` base, `getJson`-style fetch, `try/catch`, and a `(n ?? 0).toLocaleString()` formatter. On any failure or empty (`event_count === 0`) it returns without un-hiding the element — the graceful empty-state.

### Step 1: Write the failing test

The asset assertion already exists (`test_js_asset_copied`, Task 1). No new test code needed here.

- [ ] (No-op for test authoring — proceed to Step 2.)

### Step 2: Run the test — expect FAIL on the asset

- [ ] Run:

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python tests/test_savings_counter.py
```

Expected: `FAIL` with the single remaining line `[asset] _site/static/savings-counter.js not copied by build`.

### Step 3: Create the JS (minimal implementation)

- [ ] Write `/tmp/ct-frontend/static/savings-counter.js`:

```javascript
// CommonTrace — Global savings counter
// Fetches anonymized global sums and renders
// "the commons has saved ~N hours and ~$M of agent work".
//
// No LLM is involved: every number is a real measured count summed
// server-side (minutes, tokens) or money = tokens x a published price
// constant computed server-side. This script only formats and displays.
//
// Graceful empty-state: on zero events, error, or unreachable endpoint
// the counter element stays hidden (it ships hidden in the markup).
(function () {
  'use strict';

  var API = 'https://api.commontrace.org/api/v1/analytics';

  // Exposed for unit testing under Node; harmless in the browser.
  function formatCounterLine(data, el) {
    if (!data || typeof data !== 'object') return null;
    var events = Number(data.event_count) || 0;
    var minutes = Number(data.total_minutes_saved) || 0;
    // Nothing real to show -> caller leaves the counter hidden.
    if (events <= 0 || minutes <= 0) return null;

    var hoursTpl = el.getAttribute('data-hours-template') || 'saved ~{hours} hours';
    var moneyTpl = el.getAttribute('data-money-template') || '~${dollars}';
    var joiner = el.getAttribute('data-joiner') || 'and';
    var suffix = el.getAttribute('data-suffix') || 'of agent work';

    var hours = Math.round(minutes / 60);
    var hoursStr = hours.toLocaleString();
    var hoursClause = hoursTpl.replace('{hours}', '<span class="savings-counter__num">' + hoursStr + '</span>');

    var parts = [hoursClause];

    // Money is optional: render it only when the server supplied a real figure.
    var usd = data.total_usd_saved;
    if (usd !== null && usd !== undefined && !isNaN(Number(usd)) && Number(usd) > 0) {
      var usdStr = Number(usd).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      });
      var moneyClause = moneyTpl.replace('{dollars}', '<span class="savings-counter__num">' + usdStr + '</span>');
      parts.push(joiner);
      parts.push(moneyClause);
    }

    parts.push(suffix);
    return parts.join(' ');
  }

  function render(data) {
    var el = document.getElementById('savings-counter');
    if (!el) return;
    var line = formatCounterLine(data, el);
    if (line === null) return; // stay hidden
    var lineEl = document.getElementById('savings-counter-line');
    if (lineEl) lineEl.innerHTML = line;
    el.removeAttribute('hidden');
  }

  function load() {
    if (!document.getElementById('savings-counter')) return;
    fetch(API + '/savings', { headers: { 'Accept': 'application/json' } })
      .then(function (res) {
        if (!res.ok) throw new Error('HTTP ' + res.status);
        return res.json();
      })
      .then(render)
      .catch(function () {
        // Offline / 404 / 5xx: leave the counter hidden, never show a broken figure.
      });
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { formatCounterLine: formatCounterLine };
  } else if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', load);
  } else {
    load();
  }
})();
```

### Step 4: Run the test — expect full PASS

- [ ] Run:

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python tests/test_savings_counter.py
```

Expected output (exit 0): `PASS: savings counter build-checks green`

### Step 5: Commit

- [ ] Commit:

```bash
cd /tmp/ct-frontend && git add static/savings-counter.js tests/test_savings_counter.py && git commit -m "feat(home): savings-counter fetch + format + graceful empty-state

Fetches /api/v1/analytics/savings (dashboard fetch idiom). Renders hours
(minutes/60) and optional server-computed dollars; stays hidden on zero
events, error, or offline. No estimation, no LLM. Build-check test green.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 4 — JS unit test: formatting, reveal-on-data, hidden-on-empty/error

**Files:**
- Create: `/tmp/ct-frontend/tests/test_savings_counter_render.js` — Node unit test of `formatCounterLine` against sample payloads, with a tiny stub element (no DOM, no network).
- Depends on: `static/savings-counter.js` exporting `formatCounterLine` (Task 3, Step 3 — the `module.exports` branch).

This satisfies the spec's "counter renders from a sample endpoint payload" test, isolated from the network. It is a developer/local check; CI (`.github/workflows/ci.yml`) stays build-only, so no CI change is required.

### Step 1: Write the failing test

- [ ] Write `/tmp/ct-frontend/tests/test_savings_counter_render.js`:

```javascript
// Node unit test for the savings-counter formatter.
// Run from repo root:  node tests/test_savings_counter_render.js
// No DOM, no network: we stub the element's getAttribute.

const path = require('path');
const { formatCounterLine } = require(path.join(__dirname, '..', 'static', 'savings-counter.js'));

const failures = [];
function check(cond, msg) { if (!cond) failures.push(msg); }

// Stub element returning the English templates the build would emit.
const ATTRS = {
  'data-hours-template': 'saved ~{hours} hours',
  'data-money-template': '~${dollars}',
  'data-joiner': 'and',
  'data-suffix': 'of agent work',
  'data-approx': '~',
};
const el = { getAttribute: (k) => (k in ATTRS ? ATTRS[k] : null) };

// 1. Full payload -> hours + dollars + suffix, numbers wrapped, dollars 2dp.
const full = formatCounterLine(
  { total_minutes_saved: 18240, total_tokens_saved: 412000000, total_usd_saved: 8.24, event_count: 1530 },
  el
);
check(full !== null, 'full payload should render a line');
check(full.indexOf('304') !== -1, 'hours should be 18240/60 = 304 (got: ' + full + ')');
check(full.indexOf('8.24') !== -1, 'dollars should render as 8.24');
check(full.indexOf('of agent work') !== -1, 'suffix should be present');
check(full.indexOf('and') !== -1, 'joiner should be present when money exists');
check(full.indexOf('savings-counter__num') !== -1, 'numbers should be wrapped in the num span');

// 2. Empty payload (zero events) -> null (counter stays hidden).
const empty = formatCounterLine(
  { total_minutes_saved: 0, total_tokens_saved: 0, total_usd_saved: 0, event_count: 0 },
  el
);
check(empty === null, 'zero-event payload should return null (stay hidden)');

// 3. Minutes but no money -> hours clause only, no joiner, no dollar sign.
const noMoney = formatCounterLine(
  { total_minutes_saved: 600, total_tokens_saved: 5000000, total_usd_saved: null, event_count: 12 },
  el
);
check(noMoney !== null, 'minutes-only payload should render');
check(noMoney.indexOf('10') !== -1, 'hours should be 600/60 = 10');
check(noMoney.indexOf('$') === -1, 'no dollar sign when usd is null');
check(noMoney.indexOf(' and ') === -1, 'no joiner when money is absent');

// 4. Garbage / missing payload -> null.
check(formatCounterLine(null, el) === null, 'null payload -> null');
check(formatCounterLine({}, el) === null, 'empty object -> null');

if (failures.length) {
  console.log('FAIL');
  failures.forEach((f) => console.log('  - ' + f));
  process.exit(1);
}
console.log('PASS: savings-counter formatter unit test green');
```

### Step 2: Run the test — expect PASS

- [ ] Because `formatCounterLine` was already implemented and exported in Task 3, this test passes on first run (it is a regression guard on that logic). Run:

```bash
cd /tmp/ct-frontend && node tests/test_savings_counter_render.js
```

Expected output (exit 0): `PASS: savings-counter formatter unit test green`

If `node` is not installed, this prints `node: command not found`; skip this task (it is not part of CI) and rely on Task 3's build-check, which already proves the asset ships.

### Step 3: Confirm it actually guards (mutation sanity-check)

- [ ] Temporarily verify the test fails if the logic regresses. Run this one-liner that patches the hours divisor to a wrong value in a throwaway copy and confirms the test catches it (does not modify the real file):

```bash
cd /tmp/ct-frontend && cp static/savings-counter.js /tmp/scjs.bak && sed -i 's#minutes / 60#minutes / 99#' static/savings-counter.js && node tests/test_savings_counter_render.js; echo "exit=$?"; cp /tmp/scjs.bak static/savings-counter.js && rm /tmp/scjs.bak
```

Expected: prints `FAIL` with `hours should be 18240/60 = 304` and `exit=1`, then restores the file. (This proves the test is not a no-op. The final `cp` restores the correct `minutes / 60`.) Re-run `node tests/test_savings_counter_render.js` once more and confirm it is back to `PASS`.

### Step 4: Run the full build-check once more (no regression)

- [ ] Confirm the Python build-check still passes after all JS work:

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python tests/test_savings_counter.py
```

Expected output (exit 0): `PASS: savings counter build-checks green`

### Step 5: Commit

- [ ] Commit:

```bash
cd /tmp/ct-frontend && git add tests/test_savings_counter_render.js && git commit -m "test(home): node unit test for savings-counter formatter

Covers full payload (hours+dollars, 2dp, num-span wrap), zero-event ->
hidden, minutes-only -> no money clause, garbage -> null. Mutation-checked.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Task 5 — Wire the JS test into CI (build-check parity)

**Files:**
- Modify: `/tmp/ct-frontend/.github/workflows/ci.yml` — add a step running the Python build-check after the existing `Verify output` step (line ending `test -f _site/index.html`), and a Node step for the formatter test.
- Test: the workflow itself; validated locally by replaying its commands.

The repo's CI is the project's "test approach" (no pytest). Adding the build-check there makes the i18n + markup + asset guarantees enforced on every PR, matching the spec's "build.py produces the page without error" and "all 9 i18n keys present" requirements.

### Step 1: Write the failing check (replay current CI locally — proves the new steps are absent)

- [ ] Confirm the workflow does **not** yet run the savings tests:

```bash
cd /tmp/ct-frontend && grep -c "test_savings_counter" .github/workflows/ci.yml || echo "0"
```

Expected: prints `0` (the workflow has no savings test step yet).

### Step 2: Run the project's CI commands locally — they pass but skip our tests

- [ ] Replay the exact current CI body to confirm the baseline is green (and that nothing yet runs our tests):

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python build.py >/dev/null && test -f _site/index.html && echo "CI-BASELINE-OK"
```

Expected output: `CI-BASELINE-OK`

### Step 3: Add the CI steps (minimal implementation)

- [ ] In `/tmp/ct-frontend/.github/workflows/ci.yml`, replace the final `Verify output` step:

```yaml
      - name: Verify output
        run: test -f _site/index.html
```

with (adds the Python build-check and a Node formatter check; both deps are already in the runner or installed inline):

```yaml
      - name: Verify output
        run: test -f _site/index.html
      - name: Savings counter build-checks
        run: python tests/test_savings_counter.py
      - name: Savings counter formatter unit test
        run: node tests/test_savings_counter_render.js
```

### Step 4: Run the test — validate the workflow steps locally

- [ ] YAML-lint the workflow and replay both new step commands exactly as CI will:

```bash
cd /tmp/ct-frontend && /tmp/ctfe-venv/bin/python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')" 2>/dev/null || python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml')); print('YAML OK')"; /tmp/ctfe-venv/bin/python tests/test_savings_counter.py && node tests/test_savings_counter_render.js
```

Expected: `YAML OK`, then `PASS: savings counter build-checks green`, then `PASS: savings-counter formatter unit test green`. (If `yaml` is not installed in either interpreter, install it with `/tmp/ctfe-venv/bin/pip install -q pyyaml` and re-run; the two `PASS` lines are the load-bearing assertions.)

### Step 5: Commit

- [ ] Commit:

```bash
cd /tmp/ct-frontend && git add .github/workflows/ci.yml && git commit -m "ci: run savings-counter build-check + formatter test on PR/push

Enforces all-9-language i18n keys, counter markup, asset copy, and the
JS formatter logic on every build. No LLM, no network in the tests.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

### (a) Spec-coverage checklist

The frontend's scope is spec phase 5 ("Frontend global — counter + i18n") plus the surface defined in **Surfaces §3** and **Components → Frontend**. Mapping each frontend-relevant requirement to a task:

| Spec requirement (source) | Task |
|---------------------------|------|
| `GET /analytics/savings` returns global sums; frontend renders a live "the commons has saved ~N hours / ~$M of agent work" counter on the landing page (Surfaces §3) | Tasks 2 (markup) + 3 (fetch/render) |
| Counter on landing / stats page (Components → Frontend) | Task 2 — placed on `home.html`, the landing page (the only public stats surface; `dashboard.html` is owner-only/unlisted) |
| i18n keys for all 9 languages (Components → Frontend; Surfaces §3 "i18n, all 9 languages") | Task 1 — 6 keys × 9 langs, exact strings shown |
| Money = tokens × canonical price; no value asked of a model (Core constraint; Savings model) | Endpoint contract + Task 3 — frontend renders server-computed `total_usd_saved`; hours = `minutes/60`; no estimation in JS. Stated in Architecture. |
| Every figure `~`-prefixed, no false precision (Savings model) | Task 1 (`home.savings_approx` + `~` baked into hours/money template strings) + Task 3 (hours rounded to whole, dollars fixed 2dp) |
| Graceful empty / unreachable handling — hide the counter / show nothing (your task brief; spec "Server increment fails (offline) → best-effort") | Task 2 (ships `hidden`) + Task 3 (`catch` and `event_count<=0`/`minutes<=0` ⇒ stay hidden) |
| Test: counter renders from a sample endpoint payload | Task 4 (`test_savings_counter_render.js`) |
| Test: all 9 i18n keys present | Task 1/3 (`test_i18n_keys_present_all_langs`) |
| Test: build.py produces the page without error | Task 3/5 (`test_build_runs_clean` + CI step) |
| Aesthetic: Wikipedia/community, light, warm, content-first, no dark-startup styling | Task 2 CSS — accent numbers, muted tertiary eyebrow, secondary body text, no card/box/dark surface; reuses existing `--text-*`/`--accent` light-theme vars |

Out of scope for this repo (other phases): the `savings_ledger` migration, `POST /telemetry/savings`, the `/analytics/savings` endpoint implementation, the skill hooks, and outbound-impact — all in spec phases 1-4 (server/skill). This plan **consumes** the endpoint; the contract is documented and flagged.

### (b) Placeholder scan result

Scanned the plan for every banned token: `TBD`, `TODO`, `implement later`, `add error handling`, `add validation`, `handle edge cases`, `write tests for the above`, `similar to Task N`. **None present.** Every code step shows complete code; every test step gives an exact command and exact expected output. The literal string `{hours}`/`{dollars}`/`{count}` occurrences are i18n placeholder *syntax* (the substitution tokens `make_translator` processes at `build.py:109-111`), not plan placeholders — they are load-bearing and must appear verbatim. The JS `module.exports`/`load` dual path is fully written, not deferred.

### (c) Type/name consistency check

- `formatCounterLine(data, el)` — defined and exported in Task 3 (Step 3), imported and called in Task 4 (Step 1). Signature matches: `(payload object, element-with-getAttribute)` → `string | null`. ✓
- DOM ids/classes: `#savings-counter`, `.savings-counter`, `#savings-counter-line`, `.savings-counter__num`, `.savings-counter__eyebrow`, `.savings-counter__line` — defined in Task 2 markup + CSS, referenced by `document.getElementById('savings-counter')` / `getElementById('savings-counter-line')` in Task 3, and asserted in Task 1's `test_counter_markup_in_generated_html`. All names align. ✓
- `data-*` attributes: `data-eyebrow`, `data-hours-template`, `data-money-template`, `data-joiner`, `data-suffix`, `data-approx` — emitted in Task 2 markup, read via `getAttribute` in Task 3 and in the Task 4 stub `ATTRS`, asserted in Task 1. Names align. ✓
- i18n keys `home.savings_{eyebrow,hours,money,joiner,suffix,approx}` — added in Task 1, consumed by `t(...)` in Task 2 markup, listed in `SAVINGS_KEYS` in the Task 1 test. Identical spelling throughout. ✓
- Endpoint fields `total_minutes_saved`, `total_tokens_saved`, `total_usd_saved`, `event_count` — defined in the contract section, read in Task 3 `formatCounterLine`, exercised in Task 4 payloads. Identical. ✓
- Test/asset filenames: `tests/test_savings_counter.py`, `tests/test_savings_counter_render.js`, `static/savings-counter.js` — created and re-referenced consistently across Tasks 1-5 and the CI step. ✓
- Anchored line numbers verified against the live repo: `translations.json` `home.footer_tagline` at lang lines 48/308/435/562/822/949/1076/1203/1330 (followed by `browse.title`); `home.html` hero stats 460-463, `</style>` 433, `{% block scripts %}` end 598; `build.py` static copy 168-170; `dashboard.html` fetch idiom 318-329; `search.js` data-attr i18n 11-15; `ci.yml` final step `test -f _site/index.html`. ✓

### (d) Decisions flagged for the user

1. **Endpoint money field ownership.** The plan assumes `GET /api/v1/analytics/savings` returns a server-computed `total_usd_saved` (= `total_tokens_saved/1e6 × price_per_mtok`), so the frontend never multiplies by a price and the NO-LLM/published-constant rule is honored entirely server-side. If the server phase instead returns only `total_tokens_saved` and expects the *frontend* to apply the price constant, the price would need to be injected as a `build.py` global (e.g. `env.globals["price_per_mtok"]` from an env var) and a `data-price-per-mtok` attribute — a small, contained change to Tasks 2-3. Confirm which side owns the multiplier. The plan defaults to server-side (cleaner; single source of truth for the constant, matching the spec putting `price_per_mtok` in skill config rather than the static site).

2. **Placement: landing only, not a separate stats page.** The brief says "landing/stats page." This repo has no public stats page — `dashboard.html`/`dashboard-pro.html` are owner-only and unlisted (`build.py:286-301`, EN-only). The plan puts the counter on the public **landing page** (`home.html`) under the hero stats, which is the correct public surface. If a public stats page is desired later, the same hidden-markup + `savings-counter.js` pair drops in unchanged.

3. **English copy wording.** I chose `"Collective impact"` / `"saved ~{hours} hours"` / `"and"` / `"of agent work"`, composing to: *"Collective impact — saved ~304 hours and ~$8.24 of agent work."* The spec's literal phrasing is "the commons has saved ~N hours / ~$M of agent work." If you want the exact "the commons has saved" subject visible, change `home.savings_hours` to `"the commons has saved ~{hours} hours"` (and the 8 translations analogously) — a one-line-per-language edit in Task 1, no code change. The 7 partially-translated languages (125 keys vs en/es 258) already receive these 6 keys, so the counter is fully localized even where other strings are not.

4. **CI adds a Node step.** Task 5 introduces `node tests/test_savings_counter_render.js` into CI. GitHub's `ubuntu-latest` ships Node, so no `setup-node` is strictly required, but if you prefer an explicit pin, add `- uses: actions/setup-node@v4` before that step. Flagged because it widens the CI toolchain beyond the current Python-only build-check.
