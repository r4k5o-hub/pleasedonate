# pleasedonate Documentation

**pleasedonate** is a static-first fundraising platform built on GitHub Pages. It generates SEO-optimized donation pages automatically and provides live progress tracking from external fundraising platforms.

## Table of Contents

- [Quick Start](#quick-start)
- [How It Works](#how-it-works)
- [Configuration](#configuration)
- [Page Generation](#page-generation)
- [Live Tracking](#live-tracking)
- [Workflow Automation](#workflow-automation)
- [Contributing](#contributing)

---

## Quick Start

1. **Edit config.json** with your donation details
2. **Run the generator script** to create static pages:
   ```bash
   python scripts/generate_donation_pages.py
   ```
3. **Push to GitHub** – pages deploy automatically via GitHub Pages

---

## How It Works

### Architecture

```
config.json
    ↓
generate_donation_pages.py (Python script)
    ↓
donation-{id}-{lang}.html (static HTML pages)
    ↓
GitHub Pages (auto-deployed)
    ↓
Browser loads page + client-side JS
    ↓
Live tracking fetches current progress
```

### The Three Layers

1. **Configuration** (`config.json`)
   - Define donations, metadata, translations
   - Only authorized users can modify via GitHub protection

2. **Static Generation** (`scripts/generate_donation_pages.py`)
   - Converts config into SEO-optimized HTML
   - Embeds client-side JavaScript for live tracking
   - Produces one page per donation × language combination

3. **Live Tracking** (Client-side JavaScript)
   - Runs in the browser when users view a donation page
   - Fetches current progress from external platforms
   - Updates the progress bar and amounts in real-time
   - Zero backend requirements

---

## Configuration

### config.json Structure

```json
{
  "site": {
    "title": "pleasedonate",
    "description": "Help people who need it"
  },
  "translations": {
    "en": {
      "backToList": "Back to list",
      "category": "Category",
      "urgency": "Urgency",
      "raised": "Raised",
      "donate": "Donate now",
      "contactOwner": "Contact owner",
      "contactEmailSubject": "Donation question for",
      "suggestOpenIssue": "If you have problems or want to suggest a donation, please open an issue or contact the owners..."
    },
    "de": { ... }
  },
  "donations": [
    {
      "id": 1,
      "name": "Amelie's Fund",
      "description": "Support Amelie's project",
      "goal": 5000,
      "raised": 2350,
      "platform": "gofundme",
      "url": "https://www.gofundme.com/f/...",
      "category": "medical",
      "urgency": "high",
      "image": "https://example.com/image.jpg",
      "i18n": {
        "en": {
          "name": "Amelie's Wonderful Lift Fund",
          "description": "This campaign supports Amelie..."
        },
        "de": {
          "name": "Amelies fabelhafter Lift",
          "description": "Diese Kampagne unterstützt Amelie..."
        }
      }
    }
  ]
}
```

### Key Fields

| Field | Type | Purpose |
|-------|------|---------|
| `id` | int | Unique donation identifier (used in URLs) |
| `name` | string | Default name (English fallback) |
| `description` | string | Default description |
| `goal` | number | Target fundraising amount |
| `raised` | number | Current amount raised (for initial display) |
| `platform` | string | `"gofundme"` or other supported platform |
| `url` | string | Link to the actual fundraising campaign |
| `category` | string | e.g., `"medical"`, `"education"`, `"emergency"` |
| `urgency` | string | e.g., `"high"`, `"medium"`, `"low"` |
| `image` | string | Campaign image URL (for OG meta tags) |
| `i18n` | object | Localized name/description per language |

---

## Page Generation

### The Script: `generate_donation_pages.py`

This Python script is the engine that transforms `config.json` into static HTML pages.

#### What It Does

1. **Reads config.json** and extracts donation data + translations
2. **For each donation × language combination**, generates a standalone HTML file
   - File naming: `donation-{id}-{lang}.html`
   - Example: `donation-1-en.html`, `donation-1-de.html`

3. **Embeds metadata** for SEO:
   - `<title>`, `<meta name="description">`, Open Graph tags
   - Canonical URLs
   - Language tags

4. **Includes client-side JavaScript** in the generated HTML:
   - Detects the platform (GoFundMe, etc.)
   - Fetches live progress data at runtime
   - Updates the progress bar, amounts, and percentages

5. **Creates localized UI strings** from translations:
   - Button labels, progress text, contact form links
   - All user-facing text pulled from `translations` in config.json

#### Why This Approach?

- **SEO-friendly**: Each donation gets its own static page with proper meta tags (shareable on social media)
- **Fast**: Pre-rendered HTML loads instantly; no server rendering
- **Portable**: Works on GitHub Pages with zero backend infrastructure
- **Maintainable**: Single config file; script generates the rest

#### Running the Script

```bash
# From the repository root:
python scripts/generate_donation_pages.py

# Output:
# Generated: donation-1-en.html, donation-1-de.html, ...
```

#### Script Flow

```python
1. Load config.json
2. For each donation:
   3. For each language in translations:
      4. Extract localized name & description
      5. Create HTML from template
      6. Inject donation metadata as JSON object
      7. Inject client-side JavaScript code
      8. Generate GitHub issue link (mentions @r4k5O @r4k5o-hub)
      9. Write file as donation-{id}-{lang}.html
10. Print summary of generated files
```

---

## Live Tracking

### How Live Progress Works

When a user views `donation-1-en.html` in the browser:

1. **Page loads** with initial `raised` and `goal` from config.json
2. **Client-side JS runs** (embedded in the page):
   ```javascript
   updateProgress(donation);  // Fetch live data
   ```

3. **For GoFundMe campaigns**, the script:
   - Calls a CORS proxy (`jina.ai`) to fetch the GoFundMe page
   - Parses HTML for `"currentAmount"`, `"goalAmount"`, or other fields
   - Extracts raised and goal amounts using regex
   - Updates the DOM in real-time

4. **For platforms with APIs**, the script:
   - Checks if `external.api_url` is set in config
   - Fetches JSON from that API
   - Updates the displayed amounts

### Supported Platforms

| Platform | Method | Setup |
|----------|--------|-------|
| **GoFundMe** | CORS proxy + HTML scraping | Just add URL and `platform: "gofundme"` |
| **Custom API** | JSON endpoint | Set `external.api_url` in config |

### Example: Adding a Custom API

```json
{
  "id": 2,
  "name": "Project X",
  "platform": "custom",
  "url": "https://example.com/campaign",
  "external": {
    "api_url": "https://api.example.com/campaigns/123",
    "live_tracking": true
  },
  ...
}
```

The client-side JS will fetch from the API and expect:
```json
{
  "raised": 2350,
  "goal": 5000
}
```

---

## Workflow Automation

### GitHub Workflow Protection

A GitHub workflow restricts edits to `config.json` to authorized users only:

- **Allowed**: `@r4k5O` and `@r4k5o-hub`
- **Blocked**: All other users

This ensures the donation list cannot be tampered with.

### Automatic Page Regeneration (Optional)

You can configure a workflow to automatically run the script when `config.json` changes:

```yaml
# .github/workflows/generate-pages.yml
name: Generate Donation Pages

on:
  push:
    paths:
      - config.json
    branches:
      - main

jobs:
  generate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
      - run: python scripts/generate_donation_pages.py
      - uses: stefanzweifel/git-auto-commit-action@v4
        with:
          commit_message: "Auto-generate donation pages"
```

---

## Contributing

### To Add a New Donation

1. **Edit `config.json`** (only authorized users):
   ```json
   {
     "id": 2,
     "name": "New Campaign",
     "description": "Help someone in need",
     "goal": 10000,
     "raised": 0,
     "platform": "gofundme",
     "url": "https://www.gofundme.com/f/...",
     "category": "education",
     "urgency": "medium",
     "image": "https://example.com/image.jpg",
     "i18n": {
       "en": { "name": "...", "description": "..." },
       "de": { "name": "...", "description": "..." }
     }
   }
   ```

2. **Run the generator**:
   ```bash
   python scripts/generate_donation_pages.py
   ```

3. **Commit and push**:
   ```bash
   git add config.json donation-2-*.html
   git commit -m "Add new campaign: New Campaign"
   git push
   ```

4. **Pages deploy automatically** via GitHub Pages!

### To Modify Page Styling

Edit the `<style>` block in `scripts/generate_donation_pages.py` (line 121).
All generated pages will inherit the updated styles.

### To Add a New Language

1. Add translation strings to `config.json`:
   ```json
   "translations": {
     "fr": {
       "backToList": "Retour à la liste",
       ...
     }
   }
   ```

2. Add `i18n` entries to all donations:
   ```json
   "i18n": {
     "fr": {
       "name": "Nom en français",
       "description": "Description..."
     }
   }
   ```

3. Run the generator – it will create `donation-{id}-fr.html` files automatically!

---

## File Structure

```
pleasedonate/
├── README.md                     # User-facing introduction
├── DOCS.md                       # This file
├── config.json                   # Central configuration
├── index.html                    # Homepage (lists all donations)
├── donation.html                 # Single donation template (for testing)
├── donation-1-en.html            # Generated page (English)
├── donation-1-de.html            # Generated page (German)
├── donation-2-en.html            # Generated page (English)
├── donation-2-de.html            # Generated page (German)
├── scripts/
│   └── generate_donation_pages.py # The generator script
└── .github/
    └── workflows/
        └── (optional workflows)
```

---

## Troubleshooting

### Pages Don't Update

**Problem**: Changed `config.json` but pages still show old content.

**Solution**: Run `python scripts/generate_donation_pages.py` and commit the regenerated HTML files.

### Live Progress Shows Incorrect Amount

**Problem**: The progress bar doesn't match the actual GoFundMe campaign.

**Solution**: 
- The CORS proxy may be rate-limited or slow
- Check browser console for errors (`F12` → Console)
- Try reloading the page
- Consider using a custom API if GoFundMe becomes unreliable

### Some Languages Missing

**Problem**: Only EN and DE pages are generated.

**Solution**: Add the language code to `config.json`'s `translations` object and add `i18n` entries to all donations.

---

## See Also

- [README.md](./README.md) – Platform overview
- [config.json](./config.json) – Live configuration
- `.github/workflows/` – CI/CD automation
