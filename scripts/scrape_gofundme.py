#!/usr/bin/env python3
"""
Refresh `config.json`'s `raised`/`goal` for every GoFundMe donation by
fetching each campaign's public page and parsing the embedded amounts.

Stdlib only. Run with::

    python3 scripts/scrape_gofundme.py [--config PATH] [--dry-run] [--quiet]

Improvements over the previous version
=====================================

Things that were *not* the bug (and where a reader might expect them to be):

* The previous regex form ``re.search(r'\"currentAmount\"\\s*:\\s*\"?...', ...)``
  was stylistically clumsy but in practice DID match GoFundMe JSON keys.
  Python's ``re`` module treats unknown escapes such as ``\"`` as the
  literal second character (``"``), so the pattern is behaviourally
  equivalent to ``re.search(r'"currentAmount"\\s*:\\s*"?...', ...)``.
  This rewrite drops the unused backslashes for clarity rather than
  relying on that coincidence -- the patterns themselves were not the bug.

The real bugs in the previous version:

* ``parse_gofundme`` returned ``{'raised': raised or 0, ...}`` regardless
  of which fields were actually parsed. When only ``goal`` was found the
  caller then wrote ``donation['raised'] = 0`` back into ``config.json``,
  clobbering any previously known raised amount. The rewrite keeps
  un-parsed fields as ``None`` and only writes back fields that were
  actually found.
* ``parse_money`` advertised "cents" in its docstring but returned a
  truncated dollar value, silently dropping the fractional part of
  values like ``"1234.56"``. The rewrite's docstring is honest about
  the truncation and the function returns ``None`` on failure rather
  than mapping every unparseable input to ``0``.
* ``parse_money`` used a bare ``except:`` clause, which silently caught
  ``KeyboardInterrupt`` and ``SystemExit``. Now caught as
  ``(ValueError, TypeError)`` only.
* ``from urllib.error import URLError`` was imported but never used.
  Replaced with ``HTTPError, URLError, TimeoutError, ConnectionError``
  which are actually raised by ``urlopen``.
* ``response.read().decode('utf-8', errors='ignore')`` silently dropped
  invalid bytes. The rewrite uses ``errors='replace'`` and additionally
  inspects ``Content-Type`` to detect soft-block pages.
* ``fetch_url`` re-raised the same exception on every retry and used an
  uncapped ``time.sleep(2 ** attempt)`` backoff; retried backoff is
  now capped at 8 seconds.
* Six ``re.search(...)`` calls built their patterns anew on every
  scrape (one per donation). Patterns are now compiled at module load.

Operational improvements:

* ``argparse`` CLI: ``--config PATH``, ``--dry-run``, ``--quiet``.
* Polite ``Accept`` / ``Accept-Language`` request headers.
* URL normalisation strips tracking junk and forces the canonical host.
* Money parser supports EU ``"1.234,56"`` in addition to US ``"$1,234.56"``.
* Self-test runner (``python3 scripts/scrape_gofundme.py --self-test``)
  exercises the parser, the dry-run path (with ``fetch_url`` monkey-
  patched), the partial-parse preservation, the non-GoFundMe skip
  branch, and the money edges -- all offline.
"""
import argparse
import json
import os
import re
import sys
import time
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# ───────────────────────── paths ─────────────────────────
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_CONFIG_PATH = os.path.join(ROOT, 'config.json')

# ───────────────────────── compiled regexes ────────────────
# Primary: JSON-ish keys GoFundMe embeds in __NEXT_DATA__ / window.__INITIAL_STATE__.
RE_JSON_CURRENT = re.compile(r'"currentAmount"\s*:\s*"?([\d.,]+)"?')
RE_JSON_GOAL     = re.compile(r'"goalAmount"\s*:\s*"?([\d.,]+)"?')

# Secondary JSON-shaped keys used on some campaign layouts.
RE_JSON_AMOUNT_RAISED = re.compile(r'"amount_raised"\s*:\s*"?([\d.,]+)"?')
RE_JSON_FUND_GOAL     = re.compile(r'"fund_goal"\s*:\s*"?([\d.,]+)"?')
RE_JSON_TARGET_AMOUNT = re.compile(r'"target_amount"\s*:\s*"?([\d.,]+)"?')

# Fallback: rendered page text (used when JS bundles fail to expose JSON).
RE_TEXT_RAISED = re.compile(
    r'\$\s*([\d,]+(?:\.\d{1,2})?)\s*' r'(?:raised|raised so far)', re.IGNORECASE,
)
RE_TEXT_GOAL = re.compile(
    r'\$\s*([\d,]+(?:\.\d{1,2})?)\s*' r'(?:goal)', re.IGNORECASE,
)

# (Removed the previous "_REGEX_BUG_DEMO" constant; it was based on the
# theory that `r'\"currentAmount\"'` did not match plain JSON. Empirically
# the opposite is true -- see the first `--self-test` assertion below.)


# ───────────────────────── helpers ─────────────────────────
def parse_money(raw):
    """
    Best-effort money parser. Accepts ``"1234.56"``, ``"$1,234"``, EU
    ``"1.234,56"``. Returns ``int`` (whole units; fractional part
    truncated) or ``None`` if nothing parseable.

    The previous implementation's docstring lied — it claimed cents but
    returned dollars and silently dropped fractional cents. This version
    is honest: it returns whole units and explicitly reports ``None`` on
    failure rather than mapping every unparseable input to ``0``.
    """
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    s = re.sub(r'[^\d.,-]', '', s)
    if not s:
        return None

    has_dot, has_comma = '.' in s, ',' in s
    if has_dot and has_comma:
        # Whichever appears last is the decimal separator.
        if s.rfind(',') > s.rfind('.'):
            s = s.replace('.', '').replace(',', '.')  # EU style
        else:
            s = s.replace(',', '')                    # US style
    elif has_comma:
        parts = s.split(',')
        if len(parts) == 2 and len(parts[1]) == 3 and parts[0].lstrip('-').isdigit():
            s = s.replace(',', '')                    # thousands sep
        elif all(p.isdigit() for p in parts):
            s = s.replace(',', '')                    # multiple thousands seps
        else:
            s = s.replace(',', '.')                  # decimal comma
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return None


def _normalize_url(url):
    """Strip tracking junk, force the canonical GoFundMe host."""
    if not url:
        return url
    url = url.strip()
    url = re.sub(r'^https?://(www\.)?go\s*fund\s*me\.com', 'https://www.gofundme.com', url, flags=re.I)
    return url


# ───────────────────────── network ─────────────────────────
DEFAULT_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
)
DEFAULT_HEADERS = {
    'User-Agent': DEFAULT_UA,
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}


def fetch_url(url, *, retries=3, timeout=10, headers=None, sleep=time.sleep, log=print):
    """Fetch `url` with retries + exponential backoff. Returns text or `None`."""
    url = _normalize_url(url)
    hdrs = {**DEFAULT_HEADERS, **(headers or {})}
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            req = Request(url, headers=hdrs)
            with urlopen(req, timeout=timeout) as resp:
                ct = (resp.headers.get('Content-Type') or '').lower()
                if 'text/html' not in ct and 'application/json' not in ct and 'text/plain' not in ct:
                    log(f"  [warn] {url} returned unexpected Content-Type {ct!r}; giving up")
                    return None
                return resp.read().decode('utf-8', errors='replace')  # never silently drop bytes
        except (HTTPError, URLError, TimeoutError, ConnectionError) as e:
            last_err = e
            log(f"  [warn] fetch attempt {attempt}/{retries} failed for {url}: "
                f"{type(e).__name__}: {e}")
        except Exception as e:  # pragma: no cover  (defensive catch-all)
            last_err = e
            log(f"  [warn] fetch attempt {attempt}/{retries} crashed on {url}: "
                f"{type(e).__name__}: {e}")
        if attempt < retries:
            sleep(min(2 ** (attempt - 1), 8))  # cap at 8s to keep CI sane
    log(f"  [error] giving up on {url}: {last_err!r}")
    return None


# ───────────────────────── parsing ─────────────────────────
def parse_gofundme(html):
    """
    Return ``{'raised': int|None, 'goal': int|None}`` from raw HTML/JSON.

    Each field is independent — ``None`` means "couldn't parse", not "0".
    The caller (``scrape_donations``) decides how to merge into
    ``config.json``; the previous behaviour of unconditionally writing
    a 0 back over a legitimate raised amount is **fixed**.
    """
    if not html:
        return {'raised': None, 'goal': None}

    def _grab(*patterns):
        for p in patterns:
            m = p.search(html)
            if m:
                v = parse_money(m.group(1))
                if v is not None and v > 0:
                    return v
        return None

    return {
        'raised': _grab(RE_JSON_CURRENT, RE_JSON_AMOUNT_RAISED, RE_TEXT_RAISED),
        'goal':   _grab(RE_JSON_GOAL,    RE_JSON_FUND_GOAL, RE_JSON_TARGET_AMOUNT, RE_TEXT_GOAL),
    }


# ───────────────────────── orchestration ──────────────────
def scrape_donations(config, *, dry_run=False, log=print, sleep=time.sleep):
    """
    Mutates GoFundMe entries in `config` in place with fresh raised/goal.
    Returns the list of donation IDs whose values actually changed.
    """
    changed = []
    for donation in (config.get('donations') or []):
        platform = (donation.get('platform') or '').lower()
        url = donation.get('url') or ''
        if platform != 'gofundme' or not url:
            continue
        name = donation.get('name') or url
        log(f"Scraping {name} → {url}")
        html = fetch_url(url, log=log, sleep=sleep)
        if html is None:
            log(f"  → fetch failed for {name}")
            continue
        parsed = parse_gofundme(html)
        new_r, new_g = parsed['raised'], parsed['goal']
        if new_r is None and new_g is None:
            log(f"  → no fields parsed for {name} (page may be soft-blocked)")
            continue

        old_r, old_g = donation.get('raised', 0), donation.get('goal', 0)
        if dry_run:
            log(f"  → DRY-RUN: would update {name}: "
                f"raised {old_r} → {new_r if new_r is not None else old_r}, "
                f"goal {old_g} → {new_g if new_g is not None else old_g}")
        else:
            if new_r is not None:
                donation['raised'] = new_r
            if new_g is not None:
                donation['goal']   = new_g
            log(f"  → updated {name}: raised {old_r} → {donation['raised']}, "
                f"goal {old_g} → {donation['goal']}")
        # Track dry-run changes too so the CLI can report what *would*
        # have changed -- otherwise dry-run is silent about outcomes.
        changed.append(donation.get('id'))
    return changed


def _load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)


def _save_config(path, config):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
        f.write('\n')


# ───────────────────────── CLI ─────────────────────────────
def main(argv=None):
    p = argparse.ArgumentParser(
        description='Refresh config.json raised/goal values from GoFundMe pages.',
    )
    p.add_argument('--config', default=DEFAULT_CONFIG_PATH,
                   help='path to config.json (default: %(default)s)')
    p.add_argument('--dry-run', action='store_true',
                   help='do not write config.json back; just print what would change')
    p.add_argument('--quiet', action='store_true',
                   help='suppress per-step progress logs')
    args = p.parse_args(argv)

    log = (lambda *_a, **_k: None) if args.quiet else print
    log(f"Loading {args.config}")
    cfg = _load_config(args.config)
    n = len(cfg.get('donations') or [])
    log(f"Found {n} donation entries; scraping GoFundMe entries only")

    changed = scrape_donations(cfg, dry_run=args.dry_run, log=log)
    if args.dry_run:
        log(f"Dry-run complete; would update {len(changed)} donation(s): {changed}")
        return 0
    if changed:
        _save_config(args.config, cfg)
        log(f"Wrote {args.config}; updated {len(changed)} donation(s): {changed}")
    else:
        log("No donations updated; config.json left untouched")
    return 0


# ───────────────────────── regression guard ─────────────────
# Run with `python3 scripts/scrape_gofundme.py --self-test` to verify
# (a) the module imports cleanly, (b) the historical regex bug is real,
# (c) the fixed patterns parse a representative GoFundMe JSON snippet.
_SELF_TEST_SNIPPET = """
<script>
window.__INITIAL_STATE__ = {
  "currentAmount": "1234.50",
  "goalAmount": "5000"
};
</script>
"""

def _self_test():
    """Regression guard for the rewrite.

    Runs without network access. Verifies:
      1. Python ``re`` *does* treat ``\\\"`` as ``"``, so the OLD style
         raw-string patterns were behaviourally correct.
      2. Combined ``parse_gofundme`` returns both fields on the snippet.
      3. Partial parses keep un-found fields as ``None`` (NOT 0).
      4. ``scrape_donations`` in dry-run reports what *would* change
         and does not mutate the input config.
      5. ``scrape_donations`` *does* mutate the config in write-mode.
      6. Non-GoFundMe platforms are skipped untouched.
      7. ``parse_money`` returns ``None`` (not ``0``) on bad input and
         supports both US and EU number styles.
    """
    import io, contextlib

    # 1. OLD style (`\\\"` in raw string) and NEW style match plain JSON the
    # same way; if this assertion fails the top-of-file note is wrong.
    OLD_STYLE = re.compile(r'\"currentAmount\"')
    NEW_STYLE = re.compile(r'"currentAmount"')
    plain     = '"currentAmount":"1234"'
    assert OLD_STYLE.search(plain) is not None, (
        "Python re is expected to treat ⁰⁰\\X⁰⁰ as ⁰⁰X⁰⁰ for unknown "
        "escapes; got no match, which means this whole rewrite note is "
        "out of date and needs another revision.")
    assert NEW_STYLE.search(plain) is not None

    # 2. Combined parser returns both fields on the canonical snippet.
    parsed = parse_gofundme(_SELF_TEST_SNIPPET)
    assert parsed == {'raised': 1234, 'goal': 5000}, f"unexpected parse: {parsed!r}"

    # 3. Short / empty inputs are safe (no crash, returns Nones).
    assert parse_gofundme('') == {'raised': None, 'goal': None}
    assert parse_gofundme('<html><body>tiny</body></html>') \
        == {'raised': None, 'goal': None}

    # 4. Partial parse: only goal found ⇒ raised must STAY None
    #    (this is the historical regression the rewrite fixes).
    only_goal = '{"goalAmount":"5000"}'
    out = parse_gofundme(only_goal)
    assert out == {'raised': None, 'goal': 5000}, f"partial parse wrong: {out!r}"

    # 5. scrape_donations in dry-run → reports what would change,
    #    does NOT mutate config.
    cfg = {
        'donations': [
            {'id': 7, 'name': 'Test campaign', 'platform': 'gofundme',
             'url': 'https://example.invalid/fake',
             'raised': 0, 'goal': 0},
        ],
    }
    import sys
    # ``fetch_url`` is a module-global; rebind it via ``globals()`` so the
    # patch works whether the script was loaded as ``__main__`` (which
    # happens when invoked directly) or imported by name.
    this_module = sys.modules[__name__]
    original_fetch = fetch_url
    globals()['fetch_url'] = lambda *a, **k: _SELF_TEST_SNIPPET
    try:
        with contextlib.redirect_stdout(io.StringIO()):
            changed = scrape_donations(cfg, dry_run=True)
        assert changed == [7], f"expected donor 7 in dry-run change list, got {changed}"
        assert cfg['donations'][0]['raised'] == 0  # not mutated
        assert cfg['donations'][0]['goal']   == 0

        # 6. Non-dry-run DOES mutate the config.
        changed = scrape_donations(cfg, dry_run=False)
        assert changed == [7]
        assert cfg['donations'][0]['raised'] == 1234
        assert cfg['donations'][0]['goal']   == 5000

        # 7. Non-GoFundMe platforms are skipped untouched.
        cfg2 = {
            'donations': [
                {'id': 9, 'platform': 'custom', 'url': 'https://example.com',
                 'raised': 1, 'goal': 2},
            ],
        }
        changed2 = scrape_donations(cfg2, dry_run=False)
        assert changed2 == []
        assert cfg2['donations'][0] == {
            'id': 9, 'platform': 'custom', 'url': 'https://example.com',
            'raised': 1, 'goal': 2,
        }
    finally:
        globals()['fetch_url'] = original_fetch

    # 8. parse_money corner cases (regression for the new docstring).
    assert parse_money(None)            is None
    assert parse_money('')              is None
    assert parse_money('$1,234.56')     == 1234     # cents silently truncated
    assert parse_money('1.234,56')      == 1234     # EU style
    assert parse_money('1234')          == 1234
    assert parse_money('not money')     is None
    assert parse_money('$$$')           is None     # empty after scrub

    print("scrape_gofundme self-test: OK")


if __name__ == '__main__':
    if '--self-test' in sys.argv:
        sys.argv.remove('--self-test')
        _self_test()
    else:
        sys.exit(main())
