# Plato - Apps on Plato

Source: https://clinic.platomedical.com/developers/1.0/apps
Captured: 2026-05-23

---

The best way to build on top of Plato is to build an App. You can add tabs, buttons and iframes inside Plato. You can help customers automate their work or enhance their EMR.

## Types of apps

- **Private Apps:** custom self-installed applications, installed on a single organization's app store only. No approval process required.
- **Public Apps:** publicly available on Plato's App store, installable by any organization. Contact support@platomedical.com to deploy a public app.

## Building your first app

Apps on Plato reside inside iframes. This makes it really easy/fast to deploy apps on Plato.

To deploy your first app:

1. Go to "System Setup" -> "Apps".
2. Go to "Custom Apps".
3. Click "New App".
4. Add your manifest file.
5. Click "Save".

That's it - your first app is live.

---

## Notes for Goji BI

- Not directly relevant to the analytics build, but worth keeping in mind: if we ever want a "BI dashboard" tab that appears INSIDE Plato (right-click on a patient -> "View revenue history"), this is the mechanism.
- Private app route is the right path for an internal Goji-only embedded view.
