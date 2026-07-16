#!/usr/bin/env python3
"""
Generate static donation pages for SEO from config.json.
Produces donation-<id>-<lang>.html for each donation and each language in config.json.translations.
Each generated page includes client-side integration JS that will attempt to fetch live progress
from an external API or (for GoFundMe) use a CORS proxy to scrape the public page.
"""
import json
import os
import html

ROOT = os.path.dirname(os.path.dirname(__file__)) if os.path.basename(__file__) == 'generate_donation_pages.py' else '.'
CFG_PATH = os.path.join(ROOT, 'config.json')

with open(CFG_PATH, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

site = cfg.get('site', {})
translations = cfg.get('translations', {})

def safe(s):
    return html.escape(str(s)) if s is not None else ''

out_files = []

# Client-side JS to embed in each static page (keeps runtime logic centralized)
CLIENT_JS = r'''
async function tryFetchExternal(apiUrl){{
  try{{
    const r = await fetch(apiUrl);
    if(r.ok) return await r.json();
  }}catch(e){{console.warn('external json fetch failed',e);}}return null
}}

async function fetchViaProxy(url){{
  // Use jina.ai proxy to fetch HTML (may be rate limited)
  const proxy = 'https://r.jina.ai/http://';
  try{{
    const strip = url.replace(/^https?:\/\//, '');
    const r = await fetch(proxy + strip);
    if(r.ok) return await r.text();
  }}catch(e){{console.warn('proxy fetch failed',e);}}return null
}}

function parseMoney(s){{
  if(!s) return null;
  const m = String(s).match(/([0-9,.]+)/);
  if(!m) return null; return Number(m[1].replace(/[,]/g,''))
}}

function parseGoFundMe(htmlText){{
  if(!htmlText) return null;
  // try JSON-like fields
  let m = htmlText.match(/"currentAmount"\s*:\s*"?([0-9,\.]+)"?/i);
  if(m && m[1]) return {{raised: parseMoney(m[1])}};
  m = htmlText.match(/"goalAmount"\s*:\s*"?([0-9,\.]+)"?/i);
  const raisedMatch = htmlText.match(/Raised\s*to\s*date[^\$\d]*\$?([0-9,.,]+)/i) || htmlText.match(/\$([0-9,.,]+)\s*raised/i);
  let raised = null, goal = null;
  if(raisedMatch) raised = parseMoney(raisedMatch[1]);
  if(m && m[1]) goal = parseMoney(m[1]);
  if(raised || goal) return {{raised,goal}};
  // meta og:description
  m = htmlText.match(/<meta\s+property="og:description"\s+content="([^"]+)"/i);
  if(m && m[1]){{
    const txt = m[1]; const r = txt.match(/\$([0-9,.,]+)/);
    if(r) return {{raised: parseMoney(r[1])}};
  }}
  return null
}}

async function updateProgress(donation){{
  // donation is an object with url, platform, external (api_url), raised, goal
  if(donation.external && donation.external.api_url){{
    const data = await tryFetchExternal(donation.external.api_url);
    if(data){{ if(data.raised) donation.raised = data.raised; if(data.goal) donation.goal = data.goal; }}
  }} else if((donation.platform||'').toLowerCase()==='gofundme' && donation.url){{
    const htmlText = await fetchViaProxy(donation.url);
    const parsed = parseGoFundMe(htmlText);
    if(parsed){{ if(parsed.raised) donation.raised = parsed.raised; if(parsed.goal) donation.goal = parsed.goal; }}
  }}
  // update DOM
  try{{
    const raisedEl = document.getElementById('raised-amount');
    const goalEl = document.getElementById('goal-amount');
    const percentEl = document.getElementById('percent');
    const fill = document.querySelector('.progress-fill');
    if(raisedEl) raisedEl.textContent = donation.raised.toLocaleString();
    if(goalEl) goalEl.textContent = donation.goal.toLocaleString();
    if(fill) fill.style.width = Math.min(100, Math.round(donation.raised/donation.goal*100)) + '%';
    if(percentEl) percentEl.textContent = Math.min(100, Math.round(donation.raised/donation.goal*100)) + '%';
  }}catch(e){{console.warn('update DOM failed',e)}}
}}
'''

for donation in cfg.get('donations', []):
    for lang_code, texts in translations.items():
        # prefer localized name/description when available
        name_local = donation.get('i18n', {}).get(lang_code, {}).get('name') or donation.get('name')
        desc_local = donation.get('i18n', {}).get(lang_code, {}).get('description') or donation.get('description')
        title = f"{name_local} - {site.get('title','')}"
        meta_desc = desc_local or donation.get('description','')
        fname = f"donation-{donation.get('id')}-{lang_code}.html"
        path = os.path.join(ROOT, fname)

        raised = donation.get('raised', 0)
        goal = donation.get('goal', 0) or 0

        # Build static HTML content with embedded client-side integration JS
        template = '''<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<meta name="description" content="{meta_desc}">
<meta property="og:title" content="{og_title}">
<meta property="og:description" content="{og_desc}">
<meta property="og:image" content="{og_image}">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{fname}">
<style>body{{font-family:Segoe UI, Tahoma, Geneva, Verdana, sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:20px}}.container{{max-width:900px;margin:0 auto;background:#fff;border-radius:10px;padding:24px;box-shadow:0 10px 40px rgba(0,0,0,.12)}}.back{{display:inline-block;margin-bottom:16px;color:#667eea;text-decoration:none}}.hero{{display:flex;flex-direction:column;gap:16px}}.hero img{{width:100%;height:360px;object-fit:cover;border-radius:8px}}h1{{color:#333;margin:0}}.meta{{color:#666}}.progress{{margin:12px 0}}.progress-bar{{width:100%;height:12px;background:#e9e9e9;border-radius:999px;overflow:hidden}}.progress-fill{{height:100%;background:linear-gradient(90deg,#667eea 0%,#764ba2 100%)}}.actions{{display:flex;gap:12px;margin-top:18px}}.btn{{padding:12px 18px;border-radius:6px;border:none;cursor:pointer;font-weight:600}}.btn-primary{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;text-decoration:none}}.btn-ghost{{background:#f0f0f0;color:#333;text-decoration:none}}.no-found{{padding:40px;text-align:center;color:#666}}</style>
</head>
<body>
  <div class="container">
    <a href="index.html" class="back">← {back_text}</a>
    <div class="hero">
      <img src="{image}" alt="{name}">
      <div class="details">
        <h1>{name}</h1>
        <div class="meta">{category_text}: {category} • {urgency_text}: {urgency}</div>
        <p style="margin-top:12px;color:#444">{description}</p>
        <div class="progress">
          <div style="display:flex;justify-content:space-between;color:#666;margin-bottom:8px">
            <div>{raised_text}</div>
            <div><strong>$<span id="raised-amount">{raised}</span> / $<span id="goal-amount">{goal}</span></strong></div>
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width:{percent}%"></div></div>
          <div style="text-align:right;color:#888;margin-top:6px"><span id="percent">{percent}%</span></div>
        </div>
        <div class="actions">
          <a class="btn btn-primary" href="{url}" target="_blank">{donate_text}</a>
          <a class="btn btn-ghost" id="open-issue-btn" href="#">{contact_text}</a>
        </div>
        <div style="margin-top:18px;color:#777;font-size:0.95em">{suggest_text}</div>
      </div>
   </div>
  </div>
 </div>
 <script>
 // Embedded donation object (server-rendered values)
 const donation = __JSON_OBJ__;
 __CLIENT_JS__
 // attempt to update progress on load and setup issue link
 updateProgress(donation).then(() => {{
  const issueUrlBase = 'https://github.com/r4k5o-hub/pleasedonate/issues/new';
  const title = encodeURIComponent(__ISSUE_TITLE__);
  const body = encodeURIComponent(__ISSUE_BODY__);
  const fullIssueUrl = issueUrlBase + '?title=' + title + '&body=' + body;
  const issueBtn = document.getElementById('open-issue-btn');
  if(issueBtn){{ issueBtn.setAttribute('href', fullIssueUrl); issueBtn.setAttribute('target','_blank'); }}
 }});
 </script>
</body>
</html>'''

        json_obj = json.dumps({
            'id': donation.get('id'),
            'name': donation.get('name'),
            'url': donation.get('url'),
            'platform': donation.get('platform'),
            'external': donation.get('external', {}),
            'raised': donation.get('raised', 0),
            'goal': donation.get('goal', 0),
        })

        client_js = """{client_js}"""

        # Fill template
        content = template.format(
            lang=safe(lang_code),
            title=safe(name_local) + ' - ' + safe(site.get('title','')),
            meta_desc=safe(meta_desc),
            og_title=safe(name_local),
            og_desc=safe(meta_desc),
            og_image=safe(donation.get('image') or ''),
            fname=fname,
            back_text=safe(texts.get('backToList','Back to list')),
            image=safe(donation.get('image')),
            name=safe(name_local),
            category_text=safe(texts.get('category','Category')),
            category=safe(donation.get('category') or 'N/A'),
            urgency_text=safe(texts.get('urgency','Urgency')),
            urgency=safe(donation.get('urgency') or 'N/A'),
            description=safe(desc_local or donation.get('description') or ''),
            raised=safe(str(donation.get('raised',0))),
            goal=safe(str(donation.get('goal',0))),
            raised_text=safe(texts.get('raised','Raised')),
            percent=str(min(100, int((donation.get('raised',0)/max(1, donation.get('goal',1)))*100))),
            url=safe(donation.get('url')),
            donate_text=safe(texts.get('donate','Donate')),
            contact_subject=safe(texts.get('contactEmailSubject','Donation question for')),
            contact_text=safe(texts.get('contactOwner','Contact owner')),
            suggest_text=safe(texts.get('suggestOpenIssue','If you have problems or want to suggest a donation, please open an issue or contact the owners listed in the repository.')),
        )

        # Insert JSON and client JS tokens (replace safe tokens)
        content = content.replace('__JSON_OBJ__', json_obj).replace('__CLIENT_JS__', CLIENT_JS)

        # Build issue URL components
        issue_title = safe(texts.get('contactEmailSubject','Donation question for')) + ' ' + safe(donation.get('name'))
        issue_body = 'Please mention @r4k5O and @r4k5o-hub when opening the issue.\\n\\nDescribe your question or suggestion about the donation: ' + safe(donation.get('name'))
        
        content = content.replace('__ISSUE_TITLE__', issue_title).replace('__ISSUE_BODY__', issue_body)

        # write file
        with open(path, 'w', encoding='utf-8') as out:
            out.write(content)
        out_files.append(fname)

print('Generated:', ', '.join(out_files))
