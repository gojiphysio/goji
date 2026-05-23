# Plato - App Manifest

Source: https://clinic.platomedical.com/developers/1.0/apps_manifest
Captured: 2026-05-23

---

The app manifest is a JSON file (`manifest.json`) that contains information about your app such as the platform version, product, location, and so on.

## Sample manifest

```json
{
  "name": "My Awesome App",
  "version": "1.2.5",
  "app-platform-version": "1.0",
  "author": "ABC Pte Ltd",
  "email": "abc@def.com",
  "privacy-policy": "https://my-domain.com/terms.pdf",
  "read-more": "https://my-domain.com/link/to/read/more/about/the/app",
  "icon": "https://my-domain.com/icon.png",
  "description": "My app is really awesome! Please download it!",
  "permissions": ["appointment", "patient", "queue"],
  "feature-cards": [
    {
      "title": "1. Save time with automations",
      "description": "Lorem ipsum dolor sit amet...",
      "icon": "https://my-domain.com/icon.png"
    }
  ],
  "details": "This app is really very awesome. Full details can be found here.",
  "app-type": "external",
  "app-secret": "eb55a742-bd13-11e9-9cb5-2a2ae2dbcce4",
  "settings-page": "https://my-domain.com/my-url",
  "faq-page": "https://my-domain.com/faq-url",
  "developer-website": "https://my-domain.com",
  "telephone": "+6591234567",
  "locations": [
    { "location": "patient-tab",          "name": "New Tab",    "url": "https://my-domain.com/my-url", "type": "iframe" },
    { "location": "patient-folder",       "name": "New Folder", "url": "https://my-domain.com/my-url", "type": "external" },
    { "location": "patient-visit-bottom", "name": "New Button", "url": "https://my-domain.com/my-url", "type": "iframe" },
    { "location": "sidebar",              "name": "New Page",   "url": "https://my-domain.com/my-url", "type": "external" },
    { "location": "intelligence",         "name": "New Report", "url": "https://my-domain.com/my-url", "type": "iframe" }
  ]
}
```

## Field reference

| Field | Required | Description |
|---|---|---|
| `name` | yes | Name of your app. Max 35 chars. |
| `version` | yes | Version number. |
| `app-platform-version` | yes | Always `1.0`. |
| `author` | yes | Developer/company name. |
| `email` | yes | Valid email for Plato communications. |
| `privacy-policy` | yes | URL to privacy policy. |
| `icon` | optional* | Square icon (>=512x512px), HTTPS. Mandatory for Public Apps. |
| `description` | optional | Brief description. Max 110 chars. |
| `permissions` | optional | Array of API resources the app can access without an API key. |
| `feature-cards` | optional* | Up to 3 value propositions. Mandatory for Public Apps. |
| `details` | optional* | Free-form. Allowed HTML tags: `<i>`, `<b>`, `<u>`, `<ul>`, `<ol>`, `<li>`. Mandatory for Public Apps. |
| `app-type` | yes | Always `external`. |
| `app-secret` | yes | Any secret string; used to validate auth tokens. |
| `settings-page` | optional | URL to settings page (shown after install). |
| `faq-page` | optional | URL to FAQ. |
| `developer-website` | optional* | Mandatory for Public Apps. |
| `telephone` | optional* | E.164 format. Mandatory for Public Apps. |
| `locations` | yes | Array of location objects (see below). |

## Allowed permission values

`*`, `adjustment`, `appointment`, `contact`, `corporate`, `deliveryorder`, `expense`, `facility`, `graphing`, `inventory`, `invoice`, `patient`, `patient_note`, `payment`, `purchaseorder`, `purchaserequisition`, `queue`, `reports`, `search`, `supplier`, `task`, `transfer`, `systemsetup`.

Use `*` to allow access to all API endpoints.

## Location object

Each `locations` entry must have:

- `location`: location code (e.g. `patient-tab`, `sidebar`, `intelligence`)
- `name`: display name shown in Plato UI
- `url`: app URL (HTTPS)
- `type`: `iframe` (within Plato tab) or `external` (new tab)

---

## Notes for Goji BI

- Permission set for a future in-Plato BI tab would be: `appointment`, `invoice`, `patient`, `queue`, `payment`, `reports`, `systemsetup`. No write permissions needed.
- `location: intelligence` is the right spot for a reporting/analytics tab inside Plato - this is the natural mounting point if we ever embed a Looker Studio iframe.
