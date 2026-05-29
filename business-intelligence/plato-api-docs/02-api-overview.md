# Plato API - Overview

Source: https://clinic.platomedical.com/developers/1.0/api
Captured: 2026-05-23

---

Plato's APIs belong to the Representational State Transfer (REST) category. They allow you to perform 'RESTful' operations such as reading, modifying, adding or deleting data from your Plato account.

You would need developer resources experienced in RESTful APIs to link with Plato's API.

## HTTP commands

| Command | Purpose |
|---|---|
| POST   | Create an object. |
| GET    | Fetch one or more objects. |
| PUT    | Update an object. Only the fields that need to be updated need to be specified here. |
| DELETE | Remove an object. |

## Sample GET request

```bash
curl -X GET "https://clinic.platomedical.com/api/databasename/appointment" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx"
```

## Sample POST request

```bash
curl -X POST "https://clinic.platomedical.com/api/databasename/appointment" \
  -H "accept: application/json" \
  -H "Authorization: Bearer xxxxxxxxxxxxx" \
  -H "Content-Type: application/json" \
  -d '{
    "patient_id": "10CACFF1-9685-274C-A357-C4B20EBD369E",
    "title": "John Doe",
    "description": "Some Notes",
    "starttime": "2018-01-01 09:00:00",
    "endtime": "2018-01-01 10:00:00",
    "color": "blue"
  }'
```

Note the URL pattern: `https://clinic.platomedical.com/api/{databasename}/{resource}`. The `databasename` is the per-clinic database identifier (Goji's will be assigned when the Plato account is set up).
