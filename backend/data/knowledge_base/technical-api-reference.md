# API Reference & Rate Limits

The Nimbus REST API lets you read data and manage resources programmatically.

## Authentication
All requests require a bearer token: `Authorization: Bearer <API_KEY>`. Create API keys
under **Settings → Developer → API keys**. Keys inherit the permissions of the workspace
role that created them.

## Base URL & versioning
The base URL is `https://api.nimbus.example/v1`. Breaking changes ship under a new version
prefix; the previous version is supported for 12 months.

## Rate limits
- Starter plan: 60 requests/minute
- Pro plan: 600 requests/minute
Exceeding the limit returns HTTP 429 with a `Retry-After` header. Implement exponential
backoff and honor `Retry-After`.

## Common endpoints
- `GET /v1/datasets` — list datasets
- `POST /v1/queries` — run a query
- `GET /v1/exports/{id}` — check export status
