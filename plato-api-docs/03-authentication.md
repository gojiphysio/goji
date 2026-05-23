# Plato API - Authentication

Source: https://clinic.platomedical.com/developers/1.0/api_auth
Captured: 2026-05-23

---

Plato uses **Bearer token authentication**. The API key needs to be passed as the bearer token in the header of all requests:

```
Authorization: Bearer xxxxxxxxxxxxx
```

## Generating an API key

The "admin" user of a Plato account can provision API keys.

1. Make sure you are logged in as an admin user.
2. Go to System Setup -> General Settings.
3. Click on the API tab.
4. Click Generate API Key.

Only trusted users should be given access to the API key.

## Using the API key

The API key needs to be passed in the request header.

```bash
curl -X GET "https://clinic.platomedical.com/api/DATABASENAME/appointment" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx"
```

## Making API calls from 'Apps on Plato'

Public and Private apps on Plato can make API calls without an API key.

These apps require the necessary permissions specified in the Manifest file. Once the permissions are specified, you can make API calls simply by specifying the App ID and App Secret in the authentication header.

```bash
curl -X GET -u APP_ID:APP_SECRET \
  "https://clinic.platomedical.com/api/DATABASENAME/appointment" \
  -H "accept: application/json"
```

## Notes for Goji BI

- For our ingestion jobs we'll use the bearer-token approach (the simpler path), with the key stored in GCP Secret Manager.
- The App ID/Secret approach is only relevant if Goji ever wants to publish a Plato app for other clinics.
