# Tasks: Customer Search Feature

Five task groups, worked in order. Every group that changes infrastructure ends with
`terraform plan -out=tfplan`, a summary of what it adds, changes, and destroys, an apply of
that saved plan, and a check against the deployed resources. Unit tests arrive last.
Verification steps name the `requirements.md` criteria they prove, as `(verifies 1.5)` — story
number, then criterion number. Run every `terraform` command from `infrastructure/`.

## Task 1: DynamoDB global secondary index

- [x] 1.1 In `infrastructure/dynamodb.tf`, declare the `email` attribute (type `S`) and a
      `global_secondary_index` named `email-index` with `email` as its hash key and
      `projection_type = "ALL"`.
- [x] 1.2 Run `terraform plan -out=tfplan` and summarize the changes. **Confirm the table says
      `will be updated in-place` and not `must be replaced`** — a replacement would destroy
      every stored record. Do not apply if it says replaced.
- [x] 1.3 Run `terraform apply tfplan`.
- [x] 1.4 Verify with `aws dynamodb describe-table --table-name anycompany-users`: an index
      named `email-index` exists, its `IndexStatus` is `ACTIVE`, its key schema is
      `email`/`HASH`, and `Backfilling` is absent or `false`
      *(verifies 1.5, 2.2)*.
- [x] 1.5 Verify no data was lost: `ItemCount` and a `scan` still show the records that were
      there before the apply *(verifies 2.2)*.

## Task 2: Search handler and its IAM permission

- [x] 2.1 In `src/users/app.py`, import `Key` from `boto3.dynamodb.conditions`, read
      `EMAIL_INDEX_NAME` from the environment, and add `search_users`: read `email` from
      `(event.get("queryStringParameters") or {})`, raise `ValidationError` when it is missing
      or blank, then `table.query` the index following `LastEvaluatedKey`, returning
      `{"users": [...]}`.
- [x] 2.2 Register `("GET", "/users/search")` in `ROUTES`, and pass `EMAIL_INDEX_NAME` to the
      function's `environment` block in `infrastructure/lambda-users.tf`.
- [x] 2.3 Add a policy statement granting `dynamodb:Query` on
      `"${aws_dynamodb_table.users.arn}/index/email-index"` — the index has its own ARN, so the
      existing table-only policy denies the query.
- [x] 2.4 Run `terraform plan -out=tfplan`, summarize the changes, and run
      `terraform apply tfplan`.
- [x] 2.5 Verify by invoking the deployed function directly, before the API route exists:
      `aws lambda invoke --function-name anycompany-users-crud --payload` a synthetic
      `GET /users/search` proxy event with `queryStringParameters`, confirm `statusCode` 200
      and the matching record; then send the same event with `queryStringParameters` set to
      `null` and confirm `400` *(verifies 1.1, 1.3)*.

## Task 3: API Gateway route

- [x] 3.1 Add `/users/search` to the OpenAPI body in `infrastructure/api-gateway.tf`: a `get`
      operation with a required `email` query parameter, reusing `local.cognito_security` and
      `local.lambda_integration`.
- [x] 3.2 Run `terraform plan -out=tfplan`, summarize the changes — the body hash should also
      force a new deployment — and run `terraform apply tfplan`.
- [x] 3.3 Verify the route is live and protected: with an access token,
      `curl -i "$API_INVOKE_URL/users/search?email=<known>"` returns `200`; without the header
      it returns `401`; and `aws apigateway get-method` reports `CUSTOM` for the new method
      *(verifies 1.4)*.
- [x] 3.4 Verify path precedence did not break the existing route:
      `GET /users/<a real uuid>` still returns that record, and `GET /users/search` is not
      treated as a `userid` lookup *(verifies 2.3)*.

## Task 4: End-to-end verification

- [x] 4.1 With an access token from `.env.test`, `POST /users` a record with a known email,
      then `GET /users/search?email=<that email>` and confirm `200` with that record in the
      `users` array *(verifies 1.1)*.
- [x] 4.2 Search an email that no record has, and confirm `200` with `{"users": []}` rather
      than a `404` *(verifies 1.2)*.
- [x] 4.3 Confirm the error and edge cases: `GET /users/search` with no query string returns
      `400`, `?email=` returns `400`, and the same email in a different case returns an empty
      array *(verifies 1.3, 1.6)*.
- [x] 4.4 Confirm the search is observable: `aws logs tail` the CRUD log group shows one JSON
      `INFO` record naming route `GET /users/search` with no event dump or token
      *(verifies 1.9)*.
- [x] 4.5 Re-run the MVP end-to-end suite and confirm all of its checks still pass
      *(verifies 2.1)*.

## Task 5: Unit tests

- [x] 5.1 In `tests/unit/conftest.py`, add the `email` attribute definition and the
      `email-index` GSI to the mocked table, and set `EMAIL_INDEX_NAME` in the `users_app`
      fixture.
- [x] 5.2 Write a test for a successful search: two records with different emails, searching
      one returns exactly that record inside the `users` envelope.
- [x] 5.3 Write tests for the `400` cases: `queryStringParameters` is `null`, `email` is
      absent, `email` is empty, and `email` is whitespace only — asserting nothing is queried.
- [x] 5.4 Write tests for the remaining criteria: no match returns `200` with an empty array,
      two records sharing an email both come back, a case-mismatched search returns empty, and
      a `ClientError` from `query` returns a generic `500`.
- [x] 5.5 Run `python3.13 -m pytest tests/unit -v --cov=src` and confirm every test passes,
      including the MVP's.
