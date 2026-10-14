# Requirements: Customer Search Feature

## Context

Extends the deployed Users Service MVP with search by email address. The DynamoDB table, the
CRUD Lambda function, the Cognito token authorizer, and the API Gateway REST API all already
exist and are modified in place — nothing is recreated.

The MVP put "search or filter endpoints, secondary indexes, pagination" out of scope (see
`../users-service/requirements.md`), so this feature picks up exactly what was deferred.

Criteria use the same two forms as the MVP spec: `WHEN <trigger>, THE <actor> SHALL …` for
event-driven behaviour, and `THE <actor> SHALL …` for an invariant that holds with no
triggering event.

## Story 1 — Search for users by email

**User Story:** As an API consumer, I want to search for users by email address, so that I
can find a specific user without knowing their `userid`.

### Acceptance criteria

1. WHEN a client sends `GET /users/search?email=<value>`, THE SERVICE SHALL return `200` with
   a JSON object whose `users` key is an array of every stored record whose `email` equals
   that value.
2. WHEN no stored record matches, THE SERVICE SHALL return `200` with an empty `users` array,
   and SHALL NOT return `404` — an empty result is a successful search, not a missing
   resource.
3. WHEN the `email` query parameter is absent, empty, or only whitespace, THE SERVICE SHALL
   return `400` with a JSON `message` and SHALL NOT query the index.
4. THE SEARCH ENDPOINT SHALL require the same Cognito access token as every other endpoint,
   and an unauthenticated request SHALL be rejected with `401`.
5. THE SEARCH SHALL read through a DynamoDB global secondary index using `Query`, and SHALL
   NOT scan the table.
6. THE MATCH SHALL be exact and case-sensitive, because it is a DynamoDB key comparison:
   `Grace@example.com` does not find a record stored as `grace@example.com`.
7. WHEN more matches exist than fit in one `Query` page, THE SERVICE SHALL follow
   `LastEvaluatedKey` and return every match.
8. WHEN the `Query` call fails, THE SERVICE SHALL return `500` with a generic JSON `message`
   and SHALL log the underlying error.
9. WHEN a response leaves the search endpoint, THE RESPONSE SHALL carry the same CORS headers
   as every other response, and the function SHALL emit one `INFO` record naming the route.

## Story 2 — The MVP keeps working

**User Story:** As the service owner, I want the new route to leave the five existing
endpoints untouched, so that adding search cannot regress the MVP.

### Acceptance criteria

1. THE EXISTING five routes SHALL keep the behaviour specified in
   `../users-service/requirements.md`.
2. WHEN the index is added, THE TABLE's existing items SHALL survive: DynamoDB updates the
   table in place and backfills the new index from the items already stored. A change that
   would replace the table SHALL NOT be applied.
3. WHEN a client sends `GET /users/search`, THE API SHALL route it to the search handler
   rather than treating `search` as a `userid`.
4. THE AUTHORIZER SHALL need no change, because it already returns a policy covering every
   method in the stage.

## Out of scope

Searching by name, partial or prefix matching, case-insensitive matching, sorting,
client-controlled pagination (page size and continuation tokens), enforcing that an email is
unique across records, and any second index.
