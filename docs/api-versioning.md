# API Versioning

This project supports two public API paths:

- `/api/v1/*`: explicit versioned endpoints.
- `/api/*`: legacy compatibility path with version negotiation.

## Legacy `/api` negotiation

For requests under `/api/*`, the server negotiates API version with this precedence:

1. `x-api-version` request header
2. `api_version` query parameter
3. default version `1`

If the resolved version is not supported, the server returns `400`.

## Response headers

When request path is `/api/*` and negotiation succeeds, response includes:

- `x-api-version: 1`
- `x-api-legacy: true`

## Examples

### Default negotiation (no version provided)

```bash
curl -i http://127.0.0.1:2088/api/health
```

Expected:

- HTTP `200`
- `x-api-version: 1`
- `x-api-legacy: true`

### Header-based version selection

```bash
curl -i -H 'x-api-version: 1' http://127.0.0.1:2088/api/health
```

### Query-based version selection

```bash
curl -i 'http://127.0.0.1:2088/api/health?api_version=1'
```

### Unsupported version

```bash
curl -i -H 'x-api-version: 2' http://127.0.0.1:2088/api/health
```

Expected:

- HTTP `400`
- error detail indicates unsupported version
