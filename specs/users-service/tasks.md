# Users Service — Tasks (MVP)

Six task groups, worked in order. Every group that adds infrastructure ends with
`terraform apply` of a saved plan and a check against the deployed resources. Unit tests
arrive in Task 6. Verification steps name the `requirements.md` criteria they prove, as
`(verifies 3.9)` — story number, then criterion number.

## Task 1: Infrastructure Foundation

- [x] 1.1 Create `infrastructure/main.tf` with the `aws` provider (no `region` argument), the
      `aws_caller_identity` and `aws_region` data sources, and a `locals` block with the
      `anycompany-users` name prefix.
- [x] 1.2 Create `infrastructure/variables.tf` (name prefix, Lambda runtime `python3.13`,
      timeout 10 s, memory 256 MB, stage name `prod`, log retention 30 days, CORS origin) and
      `infrastructure/outputs.tf` with the table name.
- [x] 1.3 Create `infrastructure/dynamodb.tf` with the `anycompany-users` table: hash key
      `userid` of type `S`, `PAY_PER_REQUEST` billing, no `prevent_destroy`.
- [x] 1.4 Run `terraform init`, then `terraform plan -out=tfplan` and summarize what it adds,
      changes, and destroys.
- [x] 1.5 Run `terraform apply tfplan`.
- [x] 1.6 Verify with `aws dynamodb describe-table --table-name anycompany-users`: key schema is
      `userid` HASH and billing mode is `PAY_PER_REQUEST` *(verifies 5.1, 5.2)*.

## Task 2: Business Logic (CRUD Lambda)

- [x] 2.1 Write `src/users/app.py`: module-scope boto3 table handle, JSON `response()` helper
      with CORS headers, `parse_body()` that validates `name`/`email` and returns only those two
      fields, and a `handler` dispatching on `httpMethod` plus `resource`.
- [x] 2.2 Implement `list_users`, `create_user` (uuid4 + ISO 8601 UTC timestamps), `get_user`,
      `update_user`, and `delete_user` with the 400/404/500 behaviour from the requirements,
      logging one INFO record per request via `logging.getLogger()` with `extra={...}` and never
      logging the event or a token.
- [x] 2.3 Create the execution role with a least-privilege policy: `dynamodb:GetItem`,
      `PutItem`, `DeleteItem`, and `Scan` on the table ARN, plus `xray:PutTraceSegments` and
      `xray:PutTelemetryRecords`, plus `AWSLambdaBasicExecutionRole`.
- [x] 2.4 Create `infrastructure/lambda-users.tf`: `archive_file` for `build/users.zip`, the
      `python3.13`/`arm64` function with `tracing_config` `Active`, JSON `logging_config` at
      `INFO`, the timeout/memory variables, `TABLE_NAME` env var, and a log group with 30-day
      retention.
- [x] 2.5 Run `terraform plan -out=tfplan`, summarize the changes, and run
      `terraform apply tfplan`.
- [x] 2.6 Verify by invoking the deployed function: `aws lambda invoke --function-name
      anycompany-users-crud --payload` a synthetic `POST /users` proxy event carrying an extra
      unexpected field, confirm `statusCode` 201 and CORS headers, then confirm with
      `aws dynamodb scan --table-name anycompany-users` that the item holds exactly the five
      fields *(verifies 1.1, 1.3, 1.4, 4.3)*.

## Task 3: API Gateway

- [x] 3.1 Create `infrastructure/api-gateway.tf` with an `aws_api_gateway_rest_api` whose `body`
      is an OpenAPI 3.0 JSON document defining the five operations, each with an `AWS_PROXY`
      `x-amazon-apigateway-integration` to the CRUD function and
      `x-amazon-apigateway-auth: {"type": "AWS_IAM"}`.
- [x] 3.2 Add the `aws_lambda_permission` for API Gateway, the deployment (retriggered on a hash
      of the body), and the `prod` stage with X-Ray tracing.
- [x] 3.3 Enable access logging: an IAM role with `AmazonAPIGatewayPushToCloudWatchLogs`
      registered through `aws_api_gateway_account`, a dedicated log group, and the stage's
      `access_log_settings` with a JSON format. The stage must depend on the account setting —
      without it the apply fails with "CloudWatch Logs role ARN must be set in account settings
      to enable logging".
- [x] 3.4 Add `DEFAULT_4XX` and `DEFAULT_5XX` `aws_api_gateway_gateway_response` resources that
      set the CORS headers, and output the stage invoke URL.
- [x] 3.5 Run `terraform plan -out=tfplan`, summarize the changes, and run
      `terraform apply tfplan`.
- [x] 3.6 Verify with `curl -i "$INVOKE_URL/users"`: the response is `403` (IAM authorization, so
      the API is closed from its first deployment) and carries
      `Access-Control-Allow-Origin: *` from the `DEFAULT_4XX` gateway response
      *(verifies 3.9, 4.3)*.

## Task 4: Authentication

- [x] 4.1 Create `infrastructure/cognito.tf`: user pool with `username_attributes = ["email"]`,
      an app client with no secret and `ALLOW_USER_PASSWORD_AUTH`, `ALLOW_USER_SRP_AUTH`, and
      `ALLOW_REFRESH_TOKEN_AUTH`, and outputs for the pool id and client id.
- [x] 4.2 Write `src/authorizer/app.py`: read the token from `authorizationToken`, lazily fetch
      and cache the JWKS in a module-level variable, verify signature, `exp`, and `iss` with
      `PyJWT`, require `token_use == "access"` and a matching `client_id`, return an `Allow`
      policy for `<api-id>/<stage>/*/*`, and `raise Exception("Unauthorized")` otherwise —
      logging reasons but never the token.
- [x] 4.3 Create `infrastructure/lambda-authorizer.tf`: `null_resource` running
      `python3.13 -m pip install -t build/authorizer PyJWT[crypto]`, `archive_file` for
      `build/authorizer.zip`, the `python3.13`/`arm64` function with X-Ray, JSON logs, the
      timeout/memory variables, and `USER_POOL_ID`/`APP_CLIENT_ID` env vars, plus its IAM role
      and the invoke permission for API Gateway.
- [x] 4.4 Switch the OpenAPI body in `api-gateway.tf` from `AWS_IAM` to the `CognitoAuthorizer`
      security scheme (`x-amazon-apigateway-authtype: custom`,
      `x-amazon-apigateway-authorizer` of type `token`, identity source `Authorization`,
      300 s result TTL), reference it from all five operations, and confirm the body hash forces
      a fresh `prod` deployment.
- [x] 4.5 Run `terraform plan -out=tfplan`, summarize the changes, and run
      `terraform apply tfplan`.
- [x] 4.6 Verify against the deployed API: create a workshop user with
      `aws cognito-idp admin-create-user` and `admin-set-user-password`, fetch an access token
      with `aws cognito-idp initiate-auth --auth-flow USER_PASSWORD_AUTH`, then confirm
      `curl -i -H "Authorization: $TOKEN" "$INVOKE_URL/users"` returns `200` while
      `curl -i "$INVOKE_URL/users"` returns `401` *(verifies 3.2, 3.6, 3.8)*.

## Task 5: End-to-End Verification

- [x] 5.1 With a fresh access token, `curl -X POST "$INVOKE_URL/users"` with a valid name and
      email, confirm `201`, and capture the generated `userid`.
- [x] 5.2 Confirm `GET /users` lists the record and `GET /users/{userid}` returns it with
      matching `createdAt` and `updatedAt` *(verifies 1.4, 1.6, 2.1)*.
- [x] 5.3 `PUT /users/{userid}` with a new name and email, confirm `200` with a refreshed
      `updatedAt` and an unchanged `createdAt`, then `DELETE /users/{userid}`, confirm `200`
      with `{}`, and confirm the following `GET` returns `404` *(verifies 2.3, 2.6)*.
- [x] 5.4 Confirm the error paths: `POST` with an empty `name` returns `400`, `POST` with an
      extra unexpected field stores only the five fields, `GET` on a random uuid returns `404`,
      a request with no `Authorization` header returns `401`, and an ID token instead of an
      access token returns `401` *(verifies 1.3, 1.5, 2.2, 3.2, 3.4)*.
- [x] 5.5 Verify observability on the deployed stack: `aws logs tail` the two function log groups
      and the access-log group to confirm JSON records naming the route, with no event dumps or
      tokens, and confirm with `aws xray get-trace-summaries` that a trace covers the stage and
      both functions *(verifies 4.1, 4.4)*.

## Task 6: Unit Tests

- [x] 6.1 Install the test dependencies with
      `python3.13 -m pip install --user pytest "moto[dynamodb]>=5" "PyJWT[crypto]"`.
- [x] 6.2 Create `tests/unit/` with `conftest.py`: a `mock_aws` fixture creating the users
      table, env-var fixtures for `TABLE_NAME`/`USER_POOL_ID`/`APP_CLIENT_ID`, and a factory
      building API Gateway proxy events.
- [x] 6.3 Write `tests/unit/test_users.py` with at least one test per acceptance criterion in
      Stories 1 and 2 that a unit test can reach: the five happy paths, `400` on a non-object
      body and on an empty `name` or `email`, unrecognised fields dropped, `404` on unknown ids,
      `PUT` not upserting, `200 {}` on delete, and a generic `500` when the DynamoDB call raises
      `ClientError`.
- [x] 6.4 Write `tests/unit/test_authorizer.py` with a locally generated RSA key and a patched
      JWKS cache: a valid access token yields an `Allow` policy scoped to
      `<api-id>/<stage>/*/*`, while an ID token, a wrong `client_id`, a token from another user
      pool (wrong `iss`), an expired token, and a bad signature each raise `Unauthorized`; also
      assert the JWKS is fetched once across two invocations *(verifies 3.3, 3.4, 3.5, 3.7)*.
- [x] 6.5 Run `python3.13 -m pytest tests/unit -v` and confirm every test passes.
