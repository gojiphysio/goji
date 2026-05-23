# Plato - App Authentication

Source: https://clinic.platomedical.com/developers/1.0/apps_auth
Captured: 2026-05-23

---

With each page load of your app, Plato passes a short-lived authentication token as a query string.

Sample request to your app from Plato:

```
https://my-domain.com/my-url?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

This token needs to be sent back to Plato from your server-side to authenticate the app and retrieve contextual data.

## Validate the token

```bash
curl -X POST "https://clinic.platomedical.com/apps/context" \
  -H "Content-Type: application/json" \
  -d '{
    "app_id": "0bb8d013a4aaa09511b28e0335dca05d",
    "app_secret": "eb55a742-bd13-11e9-9cb5-2a2ae2dbcce4",
    "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
  }'
```

## Response

```json
{
  "user":     { "username": "...", "email": "...", "database": "..." },
  "patient":  { "...": "..." },
  "invoice":  { "...": "..." },
  "provider": { "name": "...", "mcr": "..." },
  "location": { "name": "...", "hci": "...", "uen": "..." }
}
```

- `user` = the currently logged in Plato user
- `patient` = the current patient (if any)
- `invoice` = the current invoice (if any)
- `provider`, `location` = clinic-side identifiers (e.g. MCR for doctor, HCI/UEN for clinic in Singapore)

The context token only retrieves info from the **current context**. To read or modify other data, use the Plato API.

## Sample PHP implementation

```php
define("APP_ID", "xxxxxxxxxxxxxxx");
define("APP_SECRET", "xxxxxxxxxxxxxxx");

$contextdata = json_decode(exec(
  'curl -X POST "https://clinic.platomedical.com/apps/context" '
  . '-H "Content-Type: application/json" '
  . '-d "{ \"app_id\": \"'.APP_ID.'\", \"app_secret\": \"'.APP_SECRET.'\", \"token\": \"'.$_GET['token'].'\"}"'
), true);

if (empty($contextdata['user'])) {
  die("Error Authenticating!");
}

echo "Patient Name: ".$contextdata['patient']['name'];
echo "Invoice No: ".$contextdata['invoice']['invoice'];
echo "Username: ".$contextdata['user']['username'];
echo "Clinic ID: ".$contextdata['user']['database'];

// If the manifest has the required permissions, you can hit the Plato API directly:
echo exec('curl -X GET -u '.APP_ID.':'.APP_SECRET
  .' "https://clinic.platomedical.com/api/'.$contextdata['user']['database'].'/patient"'
  .' -H "accept: application/json"');
```

---

## Notes for Goji BI

- Only relevant if we go the in-Plato embedded BI route. For an external Looker Studio dashboard, this is unused.
- `provider.mcr` (in Singapore physio context, this carries the AHPC registration number), `location.hci` (Singapore healthcare licensing) and `location.uen` are Singapore-specific identifiers. Confirmed against Goji's data on 2026-05-23.
