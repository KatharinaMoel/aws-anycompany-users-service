# Users Service — Requirements (MVP)

A RESTful API for managing AnyCompany user records, protected by JWT access tokens issued by
an Amazon Cognito user pool. Scope is the MVP only: five CRUD endpoints, one DynamoDB table,
one authorizer.

Criteria are written in one of two forms: `WHEN <trigger>, THE <actor> SHALL <behaviour>` for
event-driven behaviour, and `THE <actor> SHALL <behaviour>` for an invariant that holds with no
triggering event.

A user record has five fields:

| Field | Type | Origin |
|---|---|---|
| `userid` | string (uuid4) | generated server-side on create |
| `name` | string, non-empty | client-supplied |
| `email` | string, non-empty | client-supplied |
| `createdAt` | ISO 8601 timestamp, UTC | set on create |
| `updatedAt` | ISO 8601 timestamp, UTC | set on create and on every update |

## Story 1 — Create and list users

**User Story:** As an API consumer, I want to create user records and list the ones that exist,
so that an application can register users and show a directory.

### Acceptance criteria

1. WHEN a client sends `POST /users` with a JSON body holding a non-empty `name` and a
   non-empty `email`, THE SERVICE SHALL store a new record and return `201` with a JSON body
   containing `userid`, `name`, `email`, `createdAt`, and `updatedAt`.
2. WHEN a record is created, THE SERVICE SHALL generate `userid` itself as a uuid4 and SHALL
   ignore any `userid` present in the request body.
3. WHEN a `POST` or `PUT` body carries fields beyond `name` and `email`, THE SERVICE SHALL
   ignore them and SHALL persist only `userid`, `name`, `email`, `createdAt`, and `updatedAt`.
4. WHEN a record is created, THE SERVICE SHALL set `createdAt` and `updatedAt` to the same
   ISO 8601 UTC timestamp.
5. WHEN a client sends `POST /users` whose body is not valid JSON, is not a JSON object, or
   whose `name` or `email` is missing, empty, or not a string, THE SERVICE SHALL return `400`
   with a JSON `message` and SHALL NOT write to the table.
6. WHEN a client sends `GET /users`, THE SERVICE SHALL return `200` with a JSON object whose
   `users` key is an array of every stored record, and SHALL return an empty array when no
   records exist.

## Story 2 — Read, update, and delete a single user

**User Story:** As an API consumer, I want to fetch, change, and remove one user by id, so that
records stay accurate over time.

### Acceptance criteria

1. WHEN a client sends `GET /users/{userid}` for a stored record, THE SERVICE SHALL return
   `200` with that record's five fields.
2. WHEN a client sends `GET /users/{userid}` for a `userid` that is not stored, THE SERVICE
   SHALL return `404` with a JSON `message`.
3. WHEN a client sends `PUT /users/{userid}` for a stored record with a non-empty `name` and
   `email`, THE SERVICE SHALL overwrite both fields, refresh `updatedAt`, leave `createdAt`
   and `userid` unchanged, and return `200` with the updated record.
4. WHEN a client sends `PUT /users/{userid}` whose body is invalid JSON or whose `name` or
   `email` is missing or empty, THE SERVICE SHALL return `400` and SHALL NOT modify the
   record.
5. WHEN a client sends `PUT /users/{userid}` for a `userid` that is not stored, THE SERVICE
   SHALL return `404` and SHALL NOT create a record.
6. WHEN a client sends `DELETE /users/{userid}` for a stored record, THE SERVICE SHALL remove
   it and return `200` with the body `{}`; a following `GET /users/{userid}` SHALL return
   `404`. WHEN the `userid` is not stored, THE SERVICE SHALL return `404`.

## Story 3 — Authenticated access only

**User Story:** As the service owner, I want every endpoint to require a Cognito access token
issued for this app client, so that user data is never reachable anonymously.

### Acceptance criteria

1. THE SERVICE SHALL use an Amazon Cognito user pool as its identity provider.
2. WHEN a request arrives with no `Authorization` header, THE API SHALL reject it with `401`
   and SHALL NOT invoke the CRUD function.
3. WHEN the presented token's signature does not verify against the user pool's JWKS, or the
   token is expired, or its `iss` is not this user pool, THE AUTHORIZER SHALL deny the
   request and THE API SHALL return `401`.
4. WHEN the presented token is a Cognito ID token (`token_use` is not `access`), THE
   AUTHORIZER SHALL deny the request and THE API SHALL return `401`.
5. WHEN the presented token's `client_id` is not the configured app client, THE AUTHORIZER
   SHALL deny the request and THE API SHALL return `401`.
6. WHEN the presented token is a valid, unexpired access token for the configured app client,
   THE AUTHORIZER SHALL return an `Allow` policy covering every method of every resource in
   the stage, and THE API SHALL route the request to the CRUD function.
7. THE AUTHORIZER SHALL hold the JWKS in module scope and SHALL fetch the JWKS endpoint only
   on a cold start.
8. THE USER POOL SHALL support email/password authentication through the `USER_PASSWORD_AUTH`
   flow, so that a client can obtain an access token.
9. WHEN the API is deployed before the authorizer exists, THE API SHALL require `AWS_IAM`
   authorization on every method, so that an unsigned request receives `403` from the very
   first deployment. The `403` of this IAM phase and the `401` of criterion 2 are both
   intended: the status code changes when the authorizer goes live, but the API is never
   anonymously reachable.

## Story 4 — Operable service

**User Story:** As an on-call engineer, I want structured logs and traces for every request, so
that I can diagnose failures without leaking secrets.

### Acceptance criteria

1. WHEN either Lambda function handles an invocation, THE FUNCTION SHALL emit at least one
   `INFO` record in JSON format naming the route (`httpMethod` and `resource`) with context
   passed in `extra`, and SHALL NOT log the whole event, the `Authorization` header, or any
   token.
2. WHEN a DynamoDB call fails, THE SERVICE SHALL return `500` with a generic JSON `message`
   and SHALL log the underlying error.
3. WHEN any response leaves the API, including API Gateway's own `DEFAULT_4XX` and
   `DEFAULT_5XX` responses, THE RESPONSE SHALL carry `Access-Control-Allow-Origin: *`; the
   function's own responses SHALL also carry `Access-Control-Allow-Headers` and
   `Access-Control-Allow-Methods`.
4. WHEN a request is handled, THE STAGE SHALL emit a JSON access-log record to CloudWatch Logs
   and X-Ray SHALL record a trace covering the stage and both Lambda functions.

## Story 5 — Managed storage

**User Story:** As a developer, I want user records in a managed NoSQL table, so that storage
scales without capacity planning.

### Acceptance criteria

1. THE SERVICE SHALL store user records in a single DynamoDB table with `userid` (String) as
   the partition key.
2. THE TABLE SHALL use `PAY_PER_REQUEST` billing.

## Out of scope for the MVP

Search or filter endpoints, secondary indexes, pagination, admin-only or owner-only
authorization rules, `OPTIONS` preflight integrations, custom domain names, usage plans, and
multi-environment deployment.
