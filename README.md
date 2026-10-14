# AnyCompany Users Service

A serverless REST API for managing user records, built spec-first: the requirements,
design, and task breakdown in [`specs/`](specs/) were written before any code, and the
implementation follows them.

Built during an AWS serverless workshop with Claude Code, as a learning exercise rather than a
production service: the deployment it describes has been destroyed.

**[`docs/walkthrough.md`](docs/walkthrough.md)** is the tour — what the running service looked
like, what went wrong on the way, and how each problem was found.

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

Each path also answers `OPTIONS` without authorization, as a MOCK integration returning CORS
headers and `{}`. A browser sends no credentials on a preflight, so that method cannot require a
token without making the API unusable from any web page.

A record holds exactly five fields: `userid` (uuid4, generated server-side), `name`,
`email`, `createdAt`, and `updatedAt` (ISO 8601, UTC). Unrecognised fields in a request
body are dropped rather than stored. Search is an exact, case-sensitive match through the
`email-index` GSI, never a table scan.

## Layout

| Path | Contents |
|---|---|
| `specs/users-service/` | requirements, design, and tasks for the MVP |
| `specs/customer-search/` | the same three documents for the search feature |
| `specs/browser-demo/` | the same three for the preflight, the client, and this documentation |
| `infrastructure/` | all Terraform, one file per concern |
| `src/users/` | the CRUD function |
| `src/authorizer/` | the token authorizer |
| `tests/unit/` | pytest suite, 84 test cases |
| `scripts/e2e.sh` | 43 end-to-end assertions against the deployed API |
| `demo/index.html` | a dependency-free browser client, for seeing it run |
| `docs/walkthrough.md` | the resource tour, the screenshots, and the findings |
| `docs/architecture.svg` | the architecture diagram, drawn for this repository |
| `docs/how-this-was-built.md` | the process: the spec loop, the verification discipline, where the method failed |
| `docs/screenshot-process.md` | how the images were produced, and the two prompts that handed the work over |
| `docs/screenshots/` | the images themselves, with a gallery page |
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

### What the three commands do

Terraform compares three things: the configuration in the `.tf` files, its own record of what it
created last time (the *state*), and what actually exists in AWS. Every command is a step in
that comparison.

- **`terraform init`** downloads the three providers named in `main.tf` — `aws`, `archive`,
  and `null` — into `infrastructure/.terraform/`. The exact versions it picked are pinned in
  `.terraform.lock.hcl`, which is committed so that every machine resolves the same ones.
  Nothing touches AWS yet.
- **`terraform plan -out=tfplan`** reads the configuration and the state, asks AWS what
  currently exists, and works out what would have to be created, changed, or destroyed to make
  AWS match the configuration. The summary it prints is the thing to read before going on.
  `-out=tfplan` saves exactly that set of changes, so the apply cannot do something the summary
  did not show.
- **`terraform apply tfplan`** carries out the saved plan, then writes the result to
  `terraform.tfstate`. That file is how the next `plan` or `destroy` knows which real
  resources belong to this configuration.

Apart from the lock file, nothing these commands produce is committed. `.terraform/` is a
download, `tfplan` is stale the moment it is applied, and the state holds every resource
identifier in the account — and, because a saved plan bundles a copy of the state, so does
`tfplan`.

### Where the Lambda packages come from

A Lambda function is deployed as a zip file. Terraform builds both zips on the machine running
it, in `build/` at the repository root, and uploads them. `build/` is never committed: it is
`src/` plus packages that pip can download again.

- **The CRUD function** has no third-party dependencies, so its package is simply
  `src/users/` zipped into `build/users.zip`, without `__pycache__`, so that running the tests
  cannot change it. Lambda's Python runtime already provides `boto3`.
- **The authorizer** needs PyJWT and `cryptography`. A `null_resource` in
  `lambda-authorizer.tf` runs a shell command locally: empty `build/authorizer/`, install
  `src/authorizer/requirements.txt` into it with `python3.13 -m pip install -t`, and copy
  `app.py` next to the packages. That folder is then zipped into `build/authorizer.zip`. The
  step reruns only when `requirements.txt` or `app.py` changes, because those two files' hashes
  are its triggers.

Each function records the hash of its zip (`source_code_hash`), so a `plan` shows a code
update only when the zip's contents actually changed.

The packages are built for the processor of the machine running Terraform, because pip
installs the wheels that fit where it runs. The workshop machine was arm64 (Graviton), matching
the functions' `arm64` architecture. On an x86 machine the same command would package x86
builds of `cryptography`, which the arm64 function could not load.

`terraform destroy` removes the AWS resources and leaves `build/` and an emptied state behind.

One consequence of the trigger mechanism: deleting `build/` while the state still records a
deployment makes the next `plan` fail, because the install step has not changed and does not
rerun, so there is no folder to zip. `terraform plan -replace=null_resource.authorizer_dependencies
-out=tfplan` forces the rebuild. After a `destroy`, a fresh apply rebuilds everything anyway.

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

84 test cases from 52 test functions (six use `@pytest.mark.parametrize`), 97% statement
coverage. DynamoDB is mocked with moto 5's `mock_aws`, and the
authorizer tests sign tokens with a throwaway RSA key, so **no test touches AWS or the
network**. Each test is named for the acceptance criterion it checks.

Against a live deployment, `./scripts/e2e.sh` runs 43 assertions over the six endpoints, the
authorization rules, and the CORS preflight. It reads `.env.test` (copy `.env.test.example`) and
fetches its own Cognito token, so it needs no setup beyond that file.

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
- **CORS headers on responses are only half of CORS.** Every endpoint requires an
  `Authorization` header, which makes a browser `fetch` non-simple and triggers a preflight —
  and an API with no `OPTIONS` method answers that with `403`, so no web page can reach it. The
  preflight needs its own unauthenticated MOCK method.
- **PyJWT must be 2.15.1 or newer.** In 2.10.1 `PyJWKClient` reads its JWKS cache but
  never populates it, so the authorizer refetched the JWKS on every invocation. A unit
  test pins this down.

## Licence

MIT-0. See [LICENSE](LICENSE).
