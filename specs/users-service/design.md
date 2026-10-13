# Users Service — Design (MVP)

## Architecture

    Client (curl / app)
      │  Authorization: <Cognito access token>
      ▼
    API Gateway REST API (v1)  ── OpenAPI 3.0 body, stage "prod"
      │   X-Ray active tracing, JSON access logs
      │   DEFAULT_4XX / DEFAULT_5XX gateway responses carry CORS headers
      │
      ├─► Lambda TOKEN authorizer ──► Cognito user pool JWKS (cached in module scope)
      │        returns Allow/Deny policy for the whole stage, 300 s cache
      │
      └─► Lambda CRUD function (AWS_PROXY) ──► DynamoDB table (on-demand)

All resources live in one AWS region, taken from the environment rather than hardcoded.

## Components

| Component | Resource | Notes |
|---|---|---|
| Users table | `aws_dynamodb_table.users` | `anycompany-users`, hash key `userid` (S), `PAY_PER_REQUEST` |
| CRUD function | `aws_lambda_function.users` | `src/users/`, `python3.13`, `arm64`, 10 s timeout, 256 MB, X-Ray `Active`, JSON log format, env `TABLE_NAME` |
| REST API | `aws_api_gateway_rest_api.users` | body from OpenAPI 3.0 JSON, five methods |
| Stage | `aws_api_gateway_stage.prod` | X-Ray on, JSON access logs to its own log group |
| Account logging role | `aws_api_gateway_account` + IAM role | prerequisite for REST API access logs — see below |
| User pool | `aws_cognito_user_pool.users` | `username_attributes = ["email"]` |
| User pool client | `aws_cognito_user_pool_client.users` | no secret; `ALLOW_USER_PASSWORD_AUTH`, `ALLOW_USER_SRP_AUTH`, `ALLOW_REFRESH_TOKEN_AUTH` |
| Authorizer function | `aws_lambda_function.authorizer` | `src/authorizer/`, 10 s timeout, deps installed into `build/authorizer` at packaging time |
| Authorizer wiring | OpenAPI `securitySchemes` | `x-amazon-apigateway-authtype: custom`, TOKEN type, identity source `Authorization` header |

Region is never hardcoded: the provider block has no `region` argument and ARNs are built
from the `aws_caller_identity` and `aws_region` data sources.

Both functions get an explicit 10 s timeout rather than Lambda's 3 s default, because the
authorizer's cold start includes an HTTPS round trip to the JWKS endpoint, and 256 MB rather
than the 128 MB default so `cryptography` imports without a sluggish cold start. Both log
groups are created explicitly with 30-day retention, so nothing is left with the implicit
never-expire default.

## API contract

| Method | Resource | Success | Errors |
|---|---|---|---|
| `GET` | `/users` | `200 {"users": [...]}` | `500` |
| `POST` | `/users` | `201 {record}` | `400`, `500` |
| `GET` | `/users/{userid}` | `200 {record}` | `404`, `500` |
| `PUT` | `/users/{userid}` | `200 {record}` | `400`, `404`, `500` |
| `DELETE` | `/users/{userid}` | `200 {}` | `404`, `500` |

Every response — success or error — is built by one helper that attaches
`Content-Type: application/json` plus the CORS headers (`Access-Control-Allow-Origin: *`,
`Access-Control-Allow-Headers`, `Access-Control-Allow-Methods`).

## CRUD function design

`src/users/app.py` exposes `handler(event, context)` and dispatches on
`(event["httpMethod"], event["resource"])`, so `/users` and `/users/{userid}` stay distinct
and an unmatched pair returns `405`:

| Key | Function | DynamoDB call |
|---|---|---|
| `GET /users` | `list_users` | `scan` |
| `POST /users` | `create_user` | `put_item` |
| `GET /users/{userid}` | `get_user` | `get_item` |
| `PUT /users/{userid}` | `update_user` | `get_item`, then `put_item` |
| `DELETE /users/{userid}` | `delete_user` | `delete_item` with `ConditionExpression="attribute_exists(userid)"` |

Shared helpers: `parse_body` (JSON decode, object check, and non-empty `name`/`email`
validation, returning a 400 on failure), `now_iso`
(`datetime.now(timezone.utc).isoformat()`), and `response(status, body)`. `parse_body` returns
only `name` and `email`, so unrecognised fields in a request body are dropped before anything
reaches the table — a client cannot inject `userid`, `createdAt`, or anything else.

The boto3 resource and the table handle are created at module scope so they are reused across
invocations. `ClientError` from any call is caught, logged with `extra={"error": ...}`, and
turned into a generic `500`; the conditional-check failure on `DELETE` maps to `404` instead.

Logging: `logging.getLogger()` at `INFO`, one record per request with fields passed in `extra`
(`route`, `userid`, `status`). The event, the `Authorization` header, and tokens are never
logged.

### IAM policy (least privilege)

- `dynamodb:GetItem`, `dynamodb:PutItem`, `dynamodb:DeleteItem`, `dynamodb:Scan`, scoped to the
  users table ARN — exactly the four calls in the routing table above, no wildcards.
- `xray:PutTraceSegments` and `xray:PutTelemetryRecords`. Both are required; granting only the
  first leaves active tracing silently incomplete.
- `AWSLambdaBasicExecutionRole` for the CloudWatch Logs actions.

## Authorizer design

`src/authorizer/app.py` implements a TOKEN authorizer, using `PyJWT` with `cryptography` for
RS256 signature verification:

1. Read the bearer token from `event["authorizationToken"]`, tolerating an optional `Bearer `
   prefix.
2. Look the signing key up with a module-scope `jwt.PyJWKClient` pointed at
   `https://cognito-idp.<region>.amazonaws.com/<user-pool-id>/.well-known/jwks.json`. Its
   `lifespan` is set past any container lifetime, so only a cold start fetches; it still
   refetches by itself when a token's `kid` is absent from the cached set, so a Cognito key
   rotation does not have to wait for containers to recycle.
3. Verify the signature and `exp` with `PyJWT`, checking `iss` against the user pool, with
   `exp`, `iss`, `sub`, `token_use`, and `client_id` all in the `require` list so a token
   missing any of them fails verification outright. Audience verification is off, because a
   Cognito access token carries `client_id` rather than `aud`.
4. Require `token_use == "access"` and `client_id == APP_CLIENT_ID`. This is what rejects ID
   tokens and tokens minted for a different app client.
5. On success return an `Allow` policy whose resource is the whole stage, derived from
   `event["methodArn"]`: `arn:aws:execute-api:<region>:<account>:<api-id>/<stage>/*/*`. A
   stage-wide resource is required because API Gateway caches the policy for 300 s and reuses
   it across routes.
6. On any failure, `raise Exception("Unauthorized")`, which API Gateway renders as `401`.

The `principalId` is the token's `sub`; `userId`, `username`, and `scope` are returned in
`context` for downstream use. Failures log the reason (for example `token_use mismatch`) but
never the token, and an unreachable JWKS endpoint is logged as an error with a traceback
rather than as a rejected token — it still fails closed with a `401`.

The `methodArn` is split on its first five colons rather than its last one, so a request path
that itself contains a colon cannot shift the boundary and produce a malformed resource ARN.

Why TOKEN rather than REQUEST: the JWT is the only input the decision needs, the policy is
deliberately route-independent, API Gateway rejects a missing `Authorization` header before any
Lambda runs, and the authorizer's event contains nothing but a token and an ARN — so there is no
request data to leak into a log. A REQUEST authorizer would be needed for a token in a cookie or
query string, per-method rules, or a composite cache key such as token plus tenant header.

## API Gateway and access logging

- The REST API is defined by an OpenAPI 3.0 JSON `body`, so the endpoint documentation and the
  deployed API cannot drift apart.
- The `prod` stage enables X-Ray active tracing and JSON access logs to a dedicated log group.
- **Access logging has an account-level prerequisite.** A REST API stage cannot write access
  logs until the account's API Gateway settings carry a CloudWatch Logs role ARN. The stack
  therefore creates an IAM role with `AmazonAPIGatewayPushToCloudWatchLogs` and registers it
  with `aws_api_gateway_account`; the stage depends on it. Without this, `terraform apply`
  fails with *"CloudWatch Logs role ARN must be set in account settings to enable logging"*.
- Caveat: `aws_api_gateway_account` is **account- and region-wide singleton state**, not a
  per-stack resource. If several people run this workshop in one AWS account, the last `apply`
  wins, and any one `terraform destroy` removes the role from the account, breaking access
  logging for every other API in that region. Accepted for the workshop; it is the reason
  requirement 4.4 is satisfiable at all.
- `DEFAULT_4XX` and `DEFAULT_5XX` gateway responses add the CORS headers to errors API Gateway
  generates itself, before any integration runs.

## Two-phase authentication rollout

Requirement 3.9 says the API must never be anonymously reachable, so the OpenAPI body ships
in two states:

- **Phase 1 (Task 3)** — every method carries
  `x-amazon-apigateway-auth: {"type": "AWS_IAM"}`. The API exists but unsigned calls get
  `403`.
- **Phase 2 (Task 4)** — the `AWS_IAM` blocks are replaced by a `security` requirement
  referencing the `CognitoAuthorizer` security scheme, and the authorizer function is wired
  in. Redeployment is forced by hashing the rendered body into the deployment's
  `triggers`/`description`.

## Terraform layout (`infrastructure/`, one file per concern)

| File | Contents |
|---|---|
| `main.tf` | provider (no `region`), `aws_caller_identity`, `aws_region`, `locals` with the `anycompany-users` prefix |
| `variables.tf` | name prefix, Lambda runtime, timeout, memory size, stage name, log retention, CORS origin |
| `dynamodb.tf` | users table |
| `lambda-users.tf` | role, least-privilege policy, `archive_file`, function, log group |
| `api-gateway.tf` | REST API with the OpenAPI body, deployment, `prod` stage, access-log group, account logging role and `aws_api_gateway_account`, gateway responses, `lambda_permission` |
| `cognito.tf` | user pool and app client |
| `lambda-authorizer.tf` | dependency install into `build/authorizer`, `archive_file`, function, role, authorizer invoke permission |
| `outputs.tf` | invoke URL, table name, user pool id, app client id |

## Packaging

`src/users/` has no third-party dependencies, so Terraform zips it straight from source into
`build/users.zip`. The authorizer needs `PyJWT[crypto]`, so a `null_resource` with a
`local-exec` provisioner runs
`python3.13 -m pip install -t build/authorizer PyJWT[crypto]`, copies `src/authorizer/app.py`
alongside it, and `archive_file` zips `build/authorizer` into `build/authorizer.zip`. The
workstation is Graviton, so the wheels are the arm64 builds the `arm64` Lambda needs.
`build/` is never committed and `src/` never holds third-party packages.

## Data flow — authenticated `POST /users`

1. Client sends `POST /prod/users` with an access token and a JSON body.
2. API Gateway invokes the authorizer with `authorizationToken` and `methodArn`.
3. The authorizer verifies the token against the JWKS — fetched from Cognito on a cold start,
   served from the module-level cache afterwards — and returns a stage-wide `Allow`.
4. API Gateway proxies the request to the CRUD function with `httpMethod=POST`,
   `resource=/users`.
5. `create_user` validates the body, drops unrecognised fields, generates a uuid4 and
   timestamps, and calls `put_item`.
6. A `201` with CORS headers goes back; the stage writes a JSON access-log record and X-Ray
   stitches stage, authorizer, and CRUD segments into one trace.

## Testing approach

`tests/unit/` with `python3.13 -m pytest`. `moto` 5's `mock_aws` backs the DynamoDB table for
the CRUD tests; API Gateway proxy events are built by a small fixture factory. Authorizer
tests generate a throwaway RSA key, sign tokens locally, and patch the module-level JWKS
cache, so no network and no real Cognito pool are involved. Every acceptance criterion that a
unit test can reach gets at least one test, happy path and error path alike.
