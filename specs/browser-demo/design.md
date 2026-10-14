# Design: Browser Demo and Screenshots

## Why this feature exists

The repository is a learning artefact, not a production service: it will be destroyed with
`terraform destroy` and never serve real users. That changes what "done" means. The value is in
what a reader on GitHub can understand, so this feature spends its effort on two things the
earlier work left out — a surface a human can look at, and a written record of the decisions
behind the code.

It also has a deadline the other features did not: screenshots can only be taken while the
workshop account is alive.

## What changes and what does not

| Component | Change |
|---|---|
| `infrastructure/api-gateway.tf` | one `OPTIONS` method per path, MOCK integration, no authorizer |
| `demo/index.html` | new; a single static page, no dependencies |
| `docs/walkthrough.md`, `docs/screenshots/` | new; the documentation surface |
| `README.md` | one link to the walkthrough |
| Authorizer, CRUD function, DynamoDB table, Cognito pool | unchanged |
| The six data methods | unchanged, still `CUSTOM` |

Nothing in `src/` changes. The preflight never reaches a Lambda.

## Part 1 — The preflight

### Why an unauthenticated method is unavoidable

A browser sends the preflight before the real request and deliberately omits credentials from
it: no `Authorization` header, no cookies. An authorizer on `OPTIONS` would therefore see no
token, deny the request, and the browser would never send the real call — the API would be
unreachable from any web page while looking correctly secured.

The alternative for REST APIs v1 is a MOCK integration, which is exactly what the console's
"Enable CORS" button generates. `x-amazon-apigateway-cors`, the declarative form, exists only
for HTTP APIs (v2), so it is not available here.

The exposure is bounded and worth stating precisely, because it is the single exception to
"never deploy a method with authorization `NONE`":

- the method reaches no backend — a MOCK integration is answered by API Gateway itself;
- it reads nothing and writes nothing;
- its response body is the constant `{}`;
- the only information it discloses is which HTTP methods exist on a path, which the OpenAPI
  document in this repository already states publicly.

### Shape

One `local.preflight` map keyed by path, so the three operations differ only in the method list
they advertise:

```hcl
preflight = {
  for path, methods in {
    "/users"          = "GET,POST,OPTIONS"
    "/users/search"   = "GET,OPTIONS"
    "/users/{userid}" = "GET,PUT,DELETE,OPTIONS"
    } : path => { options = { ... } }
}
```

Each path then becomes `merge({ get = …, post = … }, local.preflight["/users"])`. Advertising
only the methods a path really has keeps the document honest; a blanket
`GET,POST,PUT,DELETE,OPTIONS` everywhere would claim that `DELETE /users` exists.

The operation carries no `security` key. Security is declared per operation in this document,
never globally, so omitting it is what makes the method unauthenticated — there is no inherited
requirement to switch off.

The MOCK integration needs three pieces that are easy to get wrong:

1. `requestTemplates = { "application/json" = "{\"statusCode\": 200}" }` — this is what makes
   API Gateway answer at all rather than return `500`.
2. `responses.default.responseParameters` with the three `method.response.header.*` entries.
   The header values are string literals and must be **single-quoted inside the JSON string**
   (`"'Content-Type,Authorization'"`); without the inner quotes API Gateway reads them as a
   mapping expression and the header comes out empty.
3. `responses.200.headers` in the OpenAPI response object, declaring the same three headers.
   A response parameter can only be set on a header the method response declares.

`Access-Control-Allow-Headers` must include `Authorization`, which is the whole point: it is
the header that made the request non-simple in the first place.

### Consequences

- The body hash changes, so `aws_api_gateway_deployment` redeploys the `prod` stage. That is
  how the preflight goes live; a defined-but-undeployed method answers `403`.
- `put_rest_api` runs in overwrite mode. The CORS gateway responses live inside the body for
  exactly this reason and are unaffected.
- Nothing changes for the authorizer: it already returns a stage-wide policy, and the preflight
  never consults it.

## Part 2 — The demo page

### Why a static page and not the Hosted UI

The Cognito Hosted UI would need a domain, an OAuth client with callback URLs, and the
authorization-code flow — more infrastructure than the thing it demonstrates, and it issues
tokens through a redirect that is awkward to photograph. `USER_PASSWORD_AUTH` is already
enabled on the app client, the client has no secret (`generate_secret = false`), and Cognito's
`InitiateAuth` is an unauthenticated API that needs no SigV4. A plain `fetch` is enough.

Verified against the live endpoint before writing the page:

    OPTIONS https://cognito-idp.us-west-2.amazonaws.com/
      -> 200, access-control-allow-origin: *, access-control-allow-headers: content-type,x-amz-target

So the browser's preflight to Cognito succeeds and the login works from any origin.

### Flow

```
    browser (http://localhost:8000)
      │
      │ 1. POST https://cognito-idp.<region>.amazonaws.com/
      │    X-Amz-Target: AWSCognitoIdentityProviderService.InitiateAuth
      │    { AuthFlow: USER_PASSWORD_AUTH, ClientId, AuthParameters: { USERNAME, PASSWORD } }
      │    <- AuthenticationResult.AccessToken          (kept in a JS variable)
      ▼
    2. fetch <invoke url>/users
         preflight OPTIONS  -> 200 + CORS headers       (this feature)
         GET + Authorization -> authorizer -> CRUD -> DynamoDB
```

### Decisions

- **No deployment identifiers in the committed file.** Invoke URL, app client id, and region
  are form fields, prefilled from the query string. The file stays valid for any account, and
  nothing account-specific enters git.
- **Access token, never the ID token.** `AuthenticationResult.AccessToken`. The ID token is
  rejected with `401` because it carries `aud` instead of `client_id` and
  `token_use: id` — the authorizer checks both.
- **The token lives in one variable.** Not in `localStorage`, not in `sessionStorage`, not in a
  cookie, not in the URL, and not printed into the page. The password field is cleared after a
  successful login. This matters because the page exists to be screenshotted: a token rendered
  into the DOM would end up in an image in a public repository.
- **Raw JSON is shown deliberately.** The response panel prints status line and body verbatim,
  so a screenshot is evidence rather than decoration.
- **One unauthenticated button.** It sends `GET /users` with no `Authorization` header, so the
  `401` from the authorizer is reproducible in the browser and can be photographed next to the
  working call.
- **No framework, no build step.** One file, opened with
  `python3.13 -m http.server 8000 --directory demo`. A reader can read the whole client in one
  sitting, which a bundled application would not allow.

### Limits worth knowing

- `USER_PASSWORD_AUTH` sends the password to Cognito over TLS; it is fine for a disposable
  workshop user and wrong for a real application, where SRP or the hosted flow belongs.
- The page handles no challenges. If Cognito answers with `NEW_PASSWORD_REQUIRED` or an MFA
  challenge instead of a token, the page shows the raw response and stops. The workshop user
  was created with a permanent password, so this does not arise here.
- Tokens expire after an hour; the page has no refresh handling and simply reports the `401`.

## Part 3 — The documentation surface

`docs/walkthrough.md` carries three kinds of content, in this order:

1. **What was built**, as a short tour of the deployed resources, each paired with the console
   page that shows it.
2. **The screenshot inventory**: a table of expected filenames, where each comes from, and
   what it proves. Images are listed, not embedded, until the files exist — an embedded
   `![](…)` whose target is missing renders as a broken image on GitHub.
3. **What went wrong and why**, the part that is hardest to reconstruct later and most useful
   to a reader: the five findings already summarized in the README, plus the preflight gap this
   feature closes, each with the symptom, the cause, and how it was caught.

The README gets one link and no images; it is already long.

Screenshots carry the AWS account id and the API id, and a browser screenshot with developer
tools open can carry a bearer token. The walkthrough says so where a reader will see it before
taking the pictures.

## Verification strategy

The preflight and the Cognito call are verifiable from the command line by replaying exactly
what the browser sends, including `Origin` and `Access-Control-Request-Headers`, and that is
how the task list checks them.

The browser itself is not verifiable here: this environment has no browser and no display. The
final confirmation — the page loading, logging in, and rendering a response — is a manual step
performed by the user, and the task list marks it as such rather than claiming it was checked.
