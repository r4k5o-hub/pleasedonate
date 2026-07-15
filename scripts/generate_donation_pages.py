#!/usr/bin/env python3
"""
Generate static donation pages for SEO from config.json.
Produces donation-<id>-<lang>.html for each donation and each language in config.json.translations.
"""
import json
import os
import html
import re

try:
    import requests
except Exception:
    requests = None

ROOT = os.path.dirname(os.path.dirname(__file__)) if os.path.basename(__file__) == 'generate_donation_pages.py' else '.'
CFG_PATH = os.path.join(ROOT, 'config.json')

with open(CFG_PATH, 'r', encoding='utf-8') as f:
    cfg = json.load(f)

site = cfg.get('site', {})
translations = cfg.get('translations', {})

def safe(s):
    return html.escape(str(s)) if s is not None else ''

out_files = []

for donation in cfg.get('donations', []):
    for lang_code, texts in translations.items():
        title = f"{donation.get('name')} - {site.get('title','')}"
        meta_desc = donation.get('description','')
        fname = f"donation-{donation.get('id')}-{lang_code}.html"
        path = os.path.join(ROOT, fname)

        # Build static HTML content
        content = f'''<!doctype html>
<html lang="{safe(lang_code)}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{safe(donation.get('name'))} - {safe(site.get('title',''))}</title>
<meta name="description" content="{safe(meta_desc)}">
<meta property="og:title" content="{safe(donation.get('name'))}">
<meta property="og:description" content="{safe(meta_desc)}">
<meta property="og:image" content="{safe(donation.get('image') or '')}">
<meta name="twitter:card" content="summary_large_image">
<link rel="canonical" href="{fname}">
<style>body{{font-family:Segoe UI, Tahoma, Geneva, Verdana, sans-serif;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);min-height:100vh;padding:20px}}.container{{max-width:900px;margin:0 auto;background:#fff;border-radius:10px;padding:24px;box-shadow:0 10px 40px rgba(0,0,0,.12)}}.back{{display:inline-block;margin-bottom:16px;color:#667eea;text-decoration:none}}.hero{{display:flex;flex-direction:column;gap:16px}}.hero img{{width:100%;height:360px;object-fit:cover;border-radius:8px}}h1{{color:#333;margin:0}}.meta{{color:#666}}.progress{{margin:12px 0}}.progress-bar{{width:100%;height:12px;background:#e9e9e9;border-radius:999px;overflow:hidden}}.progress-fill{{height:100%;background:linear-gradient(90deg,#667eea 0%,#764ba2 100%)}}.actions{{display:flex;gap:12px;margin-top:18px}}.btn{{padding:12px 18px;border-radius:6px;border:none;cursor:pointer;font-weight:600}}.btn-primary{{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;text-decoration:none}}.btn-ghost{{background:#f0f0f0;color:#333;text-decoration:none}}.no-found{{padding:40px;text-align:center;color:#666}}</style>
</head>
<body>
  <div class="container">
    <a href="index.html" class="back">← {safe(texts.get('backToList','Back to list'))}</a>
    <div class="hero">
      <img src="{safe(donation.get('image'))}" alt="{safe(donation.get('name'))}">
      <div class="details">
        <h1>{safe(donation.get('name'))}</h1>
        <div class="meta">{safe(texts.get('category','Category'))}: {safe(donation.get('category') or 'N/A')} • {safe(texts.get('urgency','Urgency'))}: {safe(donation.get('urgency') or 'N/A')}</div>
        <p style="margin-top:12px;color:#444">{safe(donation.get('description') or '')}</p>
        <div class="progress">
          <div style="display:flex;justify-content:space-between;color:#666;margin-bottom:8px">
            <div>{safe(texts.get('raised','Raised'))}</div>
            <div><strong>${safe(str(donation.get('raised',0)))} / ${safe(str(donation.get('goal',0)))}</strong></div>
          </div>
          <div class="progress-bar"><div class="progress-fill" style="width:{min(100, int((donation.get('raised',0)/max(1, donation.get('goal',1)))*100))}%"></div></div>
          <div style="text-align:right;color:#888;margin-top:6px">{min(100, int((donation.get('raised',0)/max(1, donation.get('goal',1)))*100))}%</div>
        </div>
        <div class="actions">
          <a class="btn btn-primary" href="{safe(donation.get('url'))}" target="_blank">{safe(texts.get('donate','Donate'))}</a>
          <a class="btn btn-ghost" href="mailto:r4k5o-hub@example.com?subject={safe(texts.get('contactEmailSubject','Donation question for'))}%20{safe(donation.get('name'))}">{safe(texts.get('contactOwner','Contact owner'))}</a>
        </div>
        <div style="margin-top:18px;color:#777;font-size:0.95em">{safe(texts.get('suggestOpenIssue','If you have problems or want to suggest a donation, please open an issue or contact the owners listed in the repository.'))}</div>
      </div>
    </div>
  </div>
</body>
</html>'''

        # write file
        with open(path, 'w', encoding='utf-8') as out:
            out.write(content)
        out_files.append(fname)

print('Generated:', ', '.join(out_files))
