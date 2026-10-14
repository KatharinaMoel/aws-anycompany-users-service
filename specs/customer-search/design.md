# Design: Customer Search Feature

Every change below modifies a resource that is already deployed. Nothing is recreated, and
the table keeps its data.

## Changes at a glance

| Component | File | Change |
|---|---|---|
| Users table | `infrastructure/dynamodb.tf` | add the `email` attribute and an `email-index` GSI |
| CRUD IAM policy | `infrastructure/lambda-users.tf` | allow `dynamodb:Query` on the **index** ARN |
| CRUD function | `src/users/app.py` | add a `search_users` route handler |
| CRUD function env | `infrastructure/lambda-users.tf` | pass `EMAIL_INDEX_NAME` |
| REST API | `infrastructure/api-gateway.tf` | add `/users/search` to the OpenAPI body |

## DynamoDB global secondary index

```hcl
resource "aws_dynamodb_table" "users" {
  name         = var.name_prefix
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "userid"

  attribute {
    name = "userid"
    type = "S"
  }

  # A GSI key must be declared as an attribute on the table.
  attribute {
    name = "email"
    type = "S"
  }

  global_secondary_index {
    name            = "email-index"
    hash_key        = "email"
    projection_type = "ALL"
  }
}
```

| Property | Value |
|---|---|
| Index name | `email-index` |
| Partition key | `email` (String) |
| Projection | `ALL` — the handler returns whole records, so no second read |
| Capacity | inherited from the table's `PAY_PER_REQUEST` billing |

Three things to know about adding an index to a live table:

- It is an **in-place update**, not a replacement. The plan must say
  `will be updated in-place`; if it ever says `must be replaced`, stop — that destroys every
  stored record.
- DynamoDB allows **one GSI per table update**, so a future second index needs its own apply.
- The index is not usable the moment the apply returns: DynamoDB backfills it from the items
  already in the table, and `IndexStatus` moves `CREATING` → `ACTIVE`. The AWS provider waits
  for `ACTIVE`, but a query issued against a still-backfilling index returns incomplete
  results rather than an error, which is why Task 1 verifies the status explicitly.
- `projection_type = "ALL"` duplicates every attribute into the index, so the table's storage
  roughly doubles. That is the right trade here (five small attributes, and the alternative
  is a second read per hit), but it is a real cost, not a free lookup.

## IAM: the index has its own ARN

This is the step most easily missed. DynamoDB authorizes a query against a GSI on the
**index** ARN, so the MVP's table-only policy denies the search with `AccessDeniedException`
even though the function can already read the table.

```hcl
statement {
  sid       = "UsersEmailIndexQuery"
  actions   = ["dynamodb:Query"]
  resources = ["${aws_dynamodb_table.users.arn}/index/email-index"]
}
```

Kept as a separate statement rather than widened into the existing one, so the function gains
`Query` on the index only — not on the table.

## Search handler

`src/users/app.py` gains one function and one routing entry. It reuses the helpers the MVP
already has, so validation, error mapping, CORS headers, and logging all come for free:
raising `ValidationError` yields the `400`, and a `ClientError` from `Query` is already caught
and turned into a generic `500` with the detail logged.

```python
from boto3.dynamodb.conditions import Key

EMAIL_INDEX_NAME = os.environ.get("EMAIL_INDEX_NAME", "email-index")


def search_users(event):
    # API Gateway sends queryStringParameters as null when there is no query
    # string, so fall back to an empty dict before reading the parameter.
    email = (event.get("queryStringParameters") or {}).get("email")
    if not isinstance(email, str) or not email.strip():
        raise ValidationError("Query parameter 'email' is required")

    users = []
    kwargs = {
        "IndexName": EMAIL_INDEX_NAME,
        "KeyConditionExpression": Key("email").eq(email.strip()),
    }
    while True:
        page = table.query(**kwargs)
        users.extend(page.get("Items", []))
        start_key = page.get("LastEvaluatedKey")
        if not start_key:
            break
        kwargs["ExclusiveStartKey"] = start_key

    return response(200, {"users": users})


ROUTES = {
    ("GET", "/users"): list_users,
    ("GET", "/users/search"): search_users,
    ...
}
```

Two deliberate choices:

- **The response is `{"users": [...]}`**, the same envelope as `GET /users`, not a bare array.
  Two list endpoints returning different shapes would be a wart, and an envelope leaves room
  to add a continuation token later without breaking clients.
- **`email.strip()` is the search term**, matching the MVP's `parse_body`, which stores the
  stripped value. Searching `" grace@example.com "` therefore finds `grace@example.com`.
  Case is *not* normalised, because the stored value is not either — requirement 1.6.

## API Gateway

A new path in the same `locals.openapi_body`, reusing the fragments the MVP already defines,
so the integration and the authorizer stay defined in one place:

```hcl
"/users/search" = {
  get = {
    operationId = "searchUsers"
    summary     = "Find users by exact email address."
    parameters = [{
      name        = "email"
      in          = "query"
      required    = true
      description = "Exact, case-sensitive email address to match."
      schema      = { type = "string" }
    }]
    responses = {
      "200" = { description = "A users array, empty when nothing matches." }
      "400" = { description = "The email query parameter is missing or blank." }
    }
    security                          = local.cognito_security
    "x-amazon-apigateway-integration" = local.lambda_integration
  }
}
```

Note the security scheme is this project's `CognitoAuthorizer`, referenced through
`local.cognito_security` — the same list the five existing operations use.

**Path precedence.** API Gateway matches a literal segment such as `search` ahead of a path
variable such as `{userid}`, whatever order the paths appear in the body, so
`GET /users/search` reaches the new handler and `GET /users/<uuid>` still reaches `get_user`.
The side effect — a record whose `userid` was literally `search` would become unreachable at
`/users/{userid}` — cannot occur here, because `userid` is always a server-generated uuid4.

## What does not change

- **The authorizer.** It already returns a policy for `<api-id>/<stage>/*/*`, so the new
  method is covered with no redeploy of that function. This is the payoff of the stage-wide
  policy the MVP chose because API Gateway caches the result.
- **The gateway responses.** They live inside the OpenAPI body, so the body re-import that
  adds this path cannot wipe them.
- **The deployment trigger.** `aws_api_gateway_deployment` already redeploys on
  `sha1(aws_api_gateway_rest_api.users.body)`, so adding the path redeploys `prod` by itself.

## Testing approach

`tests/unit/conftest.py` gains the index on the mocked table, which moto 5 supports:

```python
client.create_table(
    TableName=TABLE_NAME,
    KeySchema=[{"AttributeName": "userid", "KeyType": "HASH"}],
    AttributeDefinitions=[
        {"AttributeName": "userid", "AttributeType": "S"},
        {"AttributeName": "email", "AttributeType": "S"},
    ],
    GlobalSecondaryIndexes=[{
        "IndexName": "email-index",
        "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
        "Projection": {"ProjectionType": "ALL"},
    }],
    BillingMode="PAY_PER_REQUEST",
)
```

The `users_app` fixture also sets `EMAIL_INDEX_NAME`. Existing tests are unaffected: adding
an index changes nothing about `get_item`, `put_item`, `delete_item`, or `scan`.

## Implementation order, and why

1. **The index first.** The handler's query fails until the GSI exists and is `ACTIVE`.
2. **Handler and IAM together.** Either alone is broken: the code without the permission gets
   `AccessDeniedException`, the permission without the code does nothing.
3. **The API route third.** Only now is there something working behind it, so the first
   `curl` against `/users/search` is a true test rather than a known failure.
4. **End-to-end, then unit tests**, matching the MVP's task order.
