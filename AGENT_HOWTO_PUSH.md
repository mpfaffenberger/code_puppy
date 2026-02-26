# How to Push Pages to the Sharing Platform

> **Audience:** AI agents, CLI scripts, and programmatic clients.
> This document explains how to publish HTML pages to Code Puppy's
> `/sharing` platform via its REST API.

---

## 1. Authentication

All write operations (**upload** and **delete**) require a valid
**puppy token** — an RS256 JWT issued by `puppy-frontend`.

### Where to find the token

```
~/.code_puppy/puppy.cfg
```

Parse it with any INI/config parser:

```ini
[puppy]
puppy_token = eyJhbGciOiJSUzI1NiIs...
```

### Shell one-liner to extract it

```bash
PUPPY_TOKEN=$(grep '^puppy_token' ~/.code_puppy/puppy.cfg | cut -d'=' -f2- | xargs)
```

### Python one-liner

```python
import configparser, pathlib

cfg = configparser.ConfigParser()
cfg.read(pathlib.Path.home() / ".code_puppy" / "puppy.cfg")
PUPPY_TOKEN = cfg.get("puppy", "puppy_token")
```

### How to pass it

Use the `Authorization` header:

```
Authorization: Bearer <puppy_token>
```

Alternatively, you can use the `X-Puppy-Token` header (handy for
tools that don't support `Authorization`):

```
X-Puppy-Token: <puppy_token>
```

---

## 2. Upload a Page

```
POST /api/sharing/upload
Content-Type: application/json
Authorization: Bearer <puppy_token>
```

### Request Body

| Field | Type | Required | Description |
|-------|------|:--------:|-------------|
| `name` | string | ✅ | URL-safe slug (1-100 chars). Unique within a business. |
| `business` | string | ✅ | Business unit slug (see §4). |
| `html_content` | string | ✅ | Full HTML document as a string. |
| `description` | string | — | Short description (max 500 chars). |
| `access_level` | string | — | `"public"`, `"business"` (default), or `"private"`. |

### Access Levels

| Level | Who can view |
|-------|--------------|
| `public` | Anyone with the link |
| `business` | Users in the same business unit |
| `private` | Only the page owner |

### Example — curl

```bash
PUPPY_TOKEN=$(grep '^puppy_token' ~/.code_puppy/puppy.cfg | cut -d'=' -f2- | xargs)

curl -X POST http://localhost:8080/api/sharing/upload \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $PUPPY_TOKEN" \
  -d '{
    "name": "my-dashboard",
    "business": "david-glick",
    "description": "Q1 metrics dashboard",
    "access_level": "business",
    "html_content": "<!DOCTYPE html><html><head><title>Dashboard</title></head><body><h1>Hello</h1></body></html>"
  }'
```

### Example — Python (stdlib only)

```python
import configparser
import json
import os
import pathlib
import urllib.request

os.environ["no_proxy"] = "localhost,127.0.0.1"  # bypass corporate proxy

cfg = configparser.ConfigParser()
cfg.read(pathlib.Path.home() / ".code_puppy" / "puppy.cfg")
token = cfg.get("puppy", "puppy_token")

payload = {
    "name": "my-dashboard",
    "business": "david-glick",
    "description": "Q1 metrics dashboard",
    "access_level": "business",
    "html_content": "<h1>Hello from Python!</h1>",
}

req = urllib.request.Request(
    "http://localhost:8080/api/sharing/upload",
    data=json.dumps(payload).encode(),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    },
    method="POST",
)

with urllib.request.urlopen(req, timeout=15) as resp:
    result = json.loads(resp.read())
    print(result)  # {"success": true, "data": {"url": "/sharing/david-glick/my-dashboard", ...}}
```

### Success Response (200)

```json
{
  "success": true,
  "message": "🐶 Page 'my-dashboard' created in 'david-glick' (v1)!",
  "data": {
    "id": "bf802ce0-...",
    "name": "my-dashboard",
    "business": "david-glick",
    "version": 1,
    "action": "created",
    "url": "/sharing/david-glick/my-dashboard"
  }
}
```

If the page already exists **and you are the owner**, it bumps the
version automatically (`"action": "updated"`).

---

## 3. Delete a Page

```
DELETE /api/sharing/pages/{business}/{name}
Authorization: Bearer <puppy_token>
```

Only the page **owner** (the user who uploaded it) can delete.

### Example

```bash
curl -X DELETE http://localhost:8080/api/sharing/pages/david-glick/my-dashboard \
  -H "Authorization: Bearer $PUPPY_TOKEN"
```

### Success Response (200)

```json
{
  "success": true,
  "message": "🐶 Page 'my-dashboard' deleted from 'david-glick' successfully!"
}
```

---

## 4. Business Unit Slugs

The `business` field is a kebab-case slug identifying the org section.
To list all available business units:

```
GET /api/sharing/svps
```

This returns ~139 SVP-level leaders. Each has an `id` field you can
use as the `business` value:

```json
{
  "id": "david-glick",
  "name": "David Glick",
  "vp": "David Glick (SVP)",
  "job_title": "SVP, Enterprise Business Services",
  "win_nbr": 230659640
}
```

You can also use **any custom slug** (e.g. `"my-team"`, `"hackathon-2026"`).
It will show up as a new section if pages exist under it.

There is also a `"general"` catch-all for pages that don't belong
to a specific org.

---

## 5. Read-Only Endpoints (No Auth Required)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/sharing/businesses` | List all business units with page counts |
| GET | `/api/sharing/svps` | List all SVP-level business unit options |
| GET | `/api/sharing/pages/{business}` | List pages in a business unit |
| GET | `/api/sharing/pages/{business}/{name}` | View a single page |
| GET | `/api/sharing/my-pages` | List pages owned by the current session user |
| GET | `/api/sharing/my-org-context` | Get the current user's VP/SVP/EVP chain |

---

## 6. Error Responses

| HTTP Code | Meaning | Common Cause |
|:---------:|---------|-----|
| 401 | Unauthorized | Missing or invalid puppy token |
| 403 | Forbidden | Trying to delete someone else's page |
| 404 | Not Found | Page or business doesn't exist |
| 422 | Validation Error | Bad request body (missing fields, etc.) |
| 500 | Server Error | Postgres down or key not configured |

### 401 Example

```json
{"detail": "Missing puppy token. Pass Authorization: Bearer <puppy_token>"}
```

```json
{"detail": "Puppy token has expired. Run `puppy login` to refresh."}
```

---

## 7. Tips for Agents

1. **Always set `no_proxy`** — Walmart's corporate proxy will intercept
   `localhost` requests. Set `no_proxy=localhost,127.0.0.1` in your
   environment before making requests.

2. **Use `127.0.0.1`** instead of `localhost` if proxy issues persist.

3. **HTML content** — Send a complete HTML document. Tailwind CDN
   works well for quick styling:
   ```html
   <!DOCTYPE html>
   <html>
   <head>
     <title>My Page</title>
     <script src="https://cdn.tailwindcss.com"></script>
   </head>
   <body class="bg-gray-50 p-8">
     <h1 class="text-2xl font-bold">Hello!</h1>
   </body>
   </html>
   ```

4. **Versioning is automatic** — Re-uploading the same `name` +
   `business` combo bumps the version. No need to delete first.

5. **Page names are slugs** — Use kebab-case: `my-cool-report`,
   `q1-2026-metrics`. They become part of the URL.

6. **The token contains your identity** — The server extracts
   `userid`, `name`, `email`, and `win` from the JWT claims.
   No need to pass user info separately.

7. **View your published page** at:
   ```
   http://localhost:8080/sharing/{business}/{name}
   ```
