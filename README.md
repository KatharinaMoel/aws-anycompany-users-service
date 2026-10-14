# AnyCompany Users Service

A serverless REST API for managing user records, built spec-first: the requirements,
design, and task breakdown in [`specs/`](specs/) were written before any code, and the
implementation follows them.

Built during an AWS serverless workshop with Claude Code.

## Architecture

    Client
      │  Authorization: <Cognito access token>
      ▼
    API Gateway REST API (v1)  ── OpenAPI 3.0 body, stage "prod"
      │   X-Ray active tracing, JSON access logs
      │   DEFAULT_4XX / DEFAULT_5XX carry CORS headers
      │
      ├─► Lambda TOKEN authorizer ──► Cognito user pool JWKS (cached per container)
      │        returns an Allow policy for the whole stage, cached 300 s
      │
      └─► Lambda CRUD function (AWS_PROXY) ──► DynamoDB table (on-demand)
                                                 └─ email-index GSI

| Concern | Choice |
|---|---|
| IaC | Terraform |
| Language | Python 3.13 |
| Compute | AWS Lambda, `arm64` |
| Database | DynamoDB, on-demand billing |
| API | API Gateway REST API (v1), defined by an OpenAPI 3.0 body |
| Auth | Cognito user pool + Lambda TOKEN authorizer |

## Endpoints

Every endpoint requires a Cognito **access** token in the `Authorization` header.

| Method | Path | Success | Errors |
|---|---|---|---|
| `GET` | `/users` | `200 {"users": [...]}` | `500` |
| `POST` | `/users` | `201 {record}` | `400`, `500` |
| `GET` | `/users/search?email=<value>` | `200 {"users": [...]}` | `400`, `500` |
| `GET` | `/users/{userid}` | `200 {record}` | `404`, `500` |
| `PUT` | `/users/{userid}` | `200 {record}` | `400`, `404`, `500` |
| `DELETE` | `/users/{userid}` | `200 {}` | `404`, `500` |

A record holds exactly five fields: `userid` (uuid4, generated server-side), `name`,
`email`, `createdAt`, and `updatedAt` (ISO 8601, UTC). Unrecognised fields in a request
body are dropped rather than stored. Search is an exact, case-sensitive match through the
`email-index` GSI, never a table scan.

## Layout

| Path | Contents |
|---|---|
| `specs/users-service/` | requirements, design, and tasks for the MVP |
| `specs/customer-search/` | the same three documents for the search feature |
| `infrastructure/` | all Terraform, one file per concern |
| `src/users/` | the CRUD function |
| `src/authorizer/` | the token authorizer |
| `tests/unit/` | pytest suite, 84 tests |
| `build/` | Lambda packages Terraform assembles; not committed |

## Deploying

Requires Terraform, Python 3.13, and AWS credentials. The region comes from the
environment, so the provider block has no `region` argument:

```bash
export AWS_REGION=us-west-2

cd infrastructure
terraform init
terraform plan -out=tfplan      # read the summary before applying
terraform apply tfplan
```

Run every `terraform` command from `infrastructure/`; that directory is the root module.
Adding the GSI takes several minutes, because DynamoDB backfills the index.

Outputs include the invoke URL, the user pool id, and the app client id.

### Getting a token

```bash
POOL=$(terraform output -raw user_pool_id)
CLIENT=$(terraform output -raw app_client_id)

aws cognito-idp admin-create-user --user-pool-id "$POOL" --username you@example.com \
  --user-attributes Name=email,Value=you@example.com Name=email_verified,Value=true \
  --message-action SUPPRESS
aws cognito-idp admin-set-user-password --user-pool-id "$POOL" \
  --username you@example.com --password 'ChangeMe123!' --permanent

aws cognito-idp initiate-auth --client-id "$CLIENT" --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters USERNAME=you@example.com,PASSWORD='ChangeMe123!' \
  --query 'AuthenticationResult.AccessToken' --output text
```

Use the **access** token, not the ID token: the authorizer requires `token_use: access`
and a matching `client_id`, so an ID token is rejected with `401`.

### Tearing down

```bash
cd infrastructure && terraform destroy
```

Note that this also clears the account-level API Gateway CloudWatch Logs role, which is
shared by every REST API in that account and region.

## Tests

```bash
python3.13 -m pip install --user pytest pytest-cov "moto[dynamodb]>=5" "PyJWT[crypto]" boto3
python3.13 -m pytest tests/unit -v --cov=src
```

84 tests, 97% statement coverage. DynamoDB is mocked with moto 5's `mock_aws`, and the
authorizer tests sign tokens with a throwaway RSA key, so **no test touches AWS or the
network**. Each test is named for the acceptance criterion it checks.

## Notes worth knowing

A few behaviours that cost time to discover, and are encoded in the specs and tests:

- **A GSI query is authorized on the index ARN**, not the table ARN. A table-only IAM
  policy denies the search even though the function can already read the table.
- **`put_rest_api` runs in overwrite mode**, so a change to the OpenAPI body discards any
  gateway response declared outside the document. The CORS gateway responses therefore
  live inside the body.
- **A REST API stage cannot write access logs** until the account's API Gateway settings
  carry a CloudWatch Logs role. That setting is account- and region-wide singleton state.
- **The authorizer returns a stage-wide policy** (`<api-id>/<stage>/*/*`) because API
  Gateway caches the result for 300 s and replays it across routes. A policy naming one
  method would deny the others — and it means adding a route needs no authorizer change.
- **PyJWT must be 2.15.1 or newer.** In 2.10.1 `PyJWKClient` reads its JWKS cache but
  never populates it, so the authorizer refetched the JWKS on every invocation. A unit
  test pins this down.

## Licence

MIT-0. See [LICENSE](LICENSE).
