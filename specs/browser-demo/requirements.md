# Requirements: Browser Demo and Screenshots

## Context

The deployed service has no human-facing surface. Every endpoint demands a Cognito access
token in the `Authorization` header, so opening an invoke URL in a browser yields `401`, and a
page that calls the API with `fetch` never gets that far: an `Authorization` header makes the
request non-simple, the browser sends a preflight `OPTIONS` first, and the API answers

    OPTIONS /users -> 403 {"message":"Missing Authentication Token"}

on all three paths, because no `OPTIONS` method is defined. Measured against the live API
before this feature was specified.

This feature adds the preflight, a single static page that exercises the service through a real
browser, and a documentation page that holds the screenshots.

Criteria use the same two forms as the earlier specs: `WHEN <trigger>, THE <actor> SHALL …` for
event-driven behaviour, and `THE <actor> SHALL …` for an invariant that holds with no
triggering event.

## Story 1 — A browser is allowed to call the API

**User Story:** As a user with a browser, I want the API to answer the preflight request my
browser sends before any authenticated call, so that a web page can use the service at all.

### Acceptance criteria

1. WHEN a browser sends `OPTIONS` to `/users`, `/users/search`, or `/users/{userid}` with
   `Origin`, `Access-Control-Request-Method`, and
   `Access-Control-Request-Headers: authorization,content-type`, THE API SHALL return `200`
   with `Access-Control-Allow-Origin`, `Access-Control-Allow-Headers` that include
   `Authorization`, and `Access-Control-Allow-Methods` that include the requested method.
2. THE PREFLIGHT METHOD SHALL carry no authorizer. A browser sends no `Authorization` header
   on a preflight, so an authorizer would reject it and the browser would block the real
   request before it is ever made. This is a deliberate, bounded exception to the rule that no
   method on this API is deployed with authorization `NONE`: it is the only method that
   reaches no backend, reads nothing, and returns nothing but headers.
3. THE PREFLIGHT SHALL be a MOCK integration. It SHALL NOT invoke the CRUD function, SHALL NOT
   appear as a route in that function's `ROUTES` table, and its response body SHALL be `{}`.
4. THE SIX DATA METHODS SHALL keep `CUSTOM` authorization unchanged, and a request to any of
   them without a token SHALL still return `401`.
5. WHEN the OpenAPI body changes, THE PROD STAGE SHALL be redeployed, so the preflight is live
   and not merely defined.
6. THE CORS GATEWAY RESPONSES declared in the body SHALL survive the change, because
   `put_rest_api` runs in overwrite mode and replaces the whole definition.

## Story 2 — A user exercises the service in a browser

**User Story:** As someone showing the service to another person, I want a page that logs in
and calls every endpoint, so that the running service can be seen and photographed rather than
only described.

### Acceptance criteria

1. THE REPOSITORY SHALL contain one static page, `demo/index.html`, with no build step, no
   package manager, and no third-party dependency.
2. THE COMMITTED PAGE SHALL NOT contain any deployment-specific identifier — no invoke URL, no
   user pool id, no app client id, no email, no password. It SHALL read them from form fields,
   prefillable from the query string (`?api=…&client=…&region=…`), so the file stays valid for
   any account.
3. WHEN the user submits an email and password, THE PAGE SHALL obtain a token by calling
   Cognito `InitiateAuth` with `USER_PASSWORD_AUTH` directly over HTTPS, without the AWS SDK
   and without a client secret.
4. THE PAGE SHALL use the **access** token from `AuthenticationResult.AccessToken`, not the ID
   token, because the authorizer requires `token_use: access` and a matching `client_id`.
5. THE PAGE SHALL keep the token in a JavaScript variable only. It SHALL NOT write the token or
   the password to `localStorage`, `sessionStorage`, a cookie, the URL, or the DOM.
6. WHEN the user is logged in, THE PAGE SHALL offer list, create, search, fetch one, update,
   and delete, each sending `Authorization: <access token>`.
7. WHEN a call returns a non-2xx status, THE PAGE SHALL show the status code and the `message`
   from the body, and SHALL NOT fail silently.
8. THE PAGE SHALL display the raw JSON of every response, so that a screenshot shows what the
   service actually returned.
9. THE PAGE SHALL offer one deliberately unauthenticated call, so that the `401` is
   reproducible in the browser and can be photographed as evidence that the authorizer works.

## Story 3 — The running service is documented with screenshots

**User Story:** As a reader of the repository, I want to see the deployed resources and the
service in use, so that I can judge what was built without deploying it myself.

### Acceptance criteria

1. THE REPOSITORY SHALL contain `docs/walkthrough.md` and a `docs/screenshots/` directory.
2. THE WALKTHROUGH SHALL name every expected image file, the console page or browser view it
   comes from, and what that image is meant to prove.
3. THE WALKTHROUGH SHALL NOT embed an image file that is not in the repository, because a
   missing target renders as a broken image on GitHub. Expected-but-absent images SHALL be
   listed instead.
4. THE README SHALL link to the walkthrough and SHALL NOT embed the images itself, because it
   is already long.
5. THE WALKTHROUGH SHALL warn that console screenshots carry the AWS account id and the API
   id, and that a browser screenshot can carry a token if developer tools are open.

## Story 4 — Every artefact is either published or deliberately excluded

**User Story:** As someone using this repository to learn, I want every file that was needed to
reach the current state either in the repository or excluded on purpose with the reason
recorded, so that nothing valuable is lost when the workshop environment disappears and nothing
secret is published by accident.

### Acceptance criteria

1. THE REPOSITORY SHALL contain the end-to-end verification suite that was used to check the
   deployed API, which until now lived outside the repository under `/tmp` and would be lost
   with the environment.
2. THAT SUITE SHALL read its configuration from `.env.test` and SHALL NOT contain a hardcoded
   invoke URL, user pool id, app client id, email address, password, or token.
3. THE REPOSITORY SHALL contain `.env.test.example` naming the required variables with
   placeholder values, and `.env.test` itself SHALL remain ignored by git.
4. THE REPOSITORY SHALL contain the project's Claude Code configuration — `.claude/settings.json`
   and `.claude/skills/` — because the tooling is part of what the project demonstrates.
5. THE REPOSITORY SHALL NOT contain Terraform state, provider binaries, build output, or any
   token, password, or AWS credential.
6. THE WALKTHROUGH SHALL record which artefacts were deliberately not published and why, naming
   at least the Terraform state and the session transcript.

## Out of scope

Hosting the page anywhere (S3, CloudFront, Amplify), the Cognito Hosted UI and the OAuth
authorization-code flow, refresh-token handling and token renewal, the `NEW_PASSWORD_REQUIRED`
and MFA challenges, restricting `Access-Control-Allow-Origin` to a named origin instead of
`*`, any CSS framework or build tooling, and automated browser tests.
