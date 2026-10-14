# Tasks: Browser Demo and Screenshots

Five task groups, worked in order. The group that changes infrastructure ends with
`terraform plan -out=tfplan`, a summary of what it adds, changes, and destroys, an apply of
that saved plan, and a check against the deployed API. Verification steps name the
`requirements.md` criteria they prove, as `(verifies 1.5)` — story number, then criterion
number. Run every `terraform` command from `infrastructure/`.

Task 1 comes first on purpose: screenshots can only be taken while the workshop account is
alive, so the deployment work happens before the writing.

Two steps cannot be verified in this environment, because it has no browser and no display.
They are marked **manual** and are the user's to perform; nothing claims they passed until the
user says so.

## Task 1: CORS preflight on the API

- [x] 1.1 Record the current behaviour as the baseline: `curl -i -X OPTIONS` against `/users`,
      `/users/search`, and `/users/{id}` with `Origin`, `Access-Control-Request-Method`, and
      `Access-Control-Request-Headers: authorization`, and note the status.
- [x] 1.2 In `infrastructure/api-gateway.tf`, add a `local.preflight` map keyed by path that
      renders one `options` operation per path with a MOCK integration, the three
      `method.response.header.Access-Control-Allow-*` response parameters, matching
      `responses.200.headers`, no `security` key, and a per-path method list.
- [x] 1.3 Merge `local.preflight[<path>]` into each of the three path objects, leaving the six
      existing operations untouched.
- [x] 1.4 Run `terraform plan -out=tfplan` and summarize the changes. Confirm it changes the
      REST API body and replaces the deployment, and that it does **not** touch the authorizer,
      the CRUD function, or the table. Then run `terraform apply tfplan`.
- [x] 1.5 Verify the preflight is live: the three `OPTIONS` requests from 1.1 now return `200`
      with `Access-Control-Allow-Origin`, `Access-Control-Allow-Headers` containing
      `Authorization`, and `Access-Control-Allow-Methods` listing exactly the methods that path
      has *(verifies 1.1)*.
- [x] 1.6 Verify the exception is bounded: `aws apigateway get-method` reports
      `authorizationType NONE` and `type MOCK` for each `OPTIONS`, and `CUSTOM` for all six data
      methods; an unauthenticated `GET /users` still returns `401`; and the CRUD function's log
      group shows no new invocation from the preflights *(verifies 1.2, 1.3, 1.4)*.
- [x] 1.7 Verify the overwrite-mode hazard did not bite: an authenticated request to a missing
      user still returns `404` **with** the three CORS headers, so the gateway responses in the
      body survived the import *(verifies 1.6)*.

## Task 2: The demo page

- [x] 2.1 Write `demo/index.html`: one file, no dependencies, with form fields for invoke URL,
      app client id, and region, prefilled from the query string, and no deployment-specific
      value committed.
- [x] 2.2 Implement the login: `fetch` to `https://cognito-idp.<region>.amazonaws.com/` with
      `X-Amz-Target: AWSCognitoIdentityProviderService.InitiateAuth` and
      `AuthFlow: USER_PASSWORD_AUTH`, keeping `AuthenticationResult.AccessToken` in a variable,
      clearing the password field, and surfacing a challenge response verbatim instead of
      failing silently.
- [x] 2.3 Implement the six calls plus one deliberately unauthenticated call, each rendering
      the status line and the raw JSON body into a response panel.
- [x] 2.4 Verify the page contains no secret and no deployment identifier: grep the file for the
      invoke URL, pool id, client id, `localStorage`, `sessionStorage`, and `document.cookie`,
      and confirm every hit is absent *(verifies 2.2, 2.5)*.
- [x] 2.5 Verify what the browser will do, by replaying it with `curl` from the command line:
      the preflight to Cognito returns CORS headers, `InitiateAuth` with the `.env.test` user
      returns an `AccessToken`, that token on `GET /users` returns `200`, and the same call
      without the header returns `401` *(verifies 2.3, 2.4, 2.9)*.
- [x] 2.6 **manual** The user serves the page with
      `python3.13 -m http.server 8000 --directory demo`, logs in, runs a call, and confirms the
      response panel shows real data *(verifies 2.6, 2.7, 2.8)*.

## Task 3: Walkthrough and screenshot inventory

- [x] 3.1 Create `docs/screenshots/` with a `.gitkeep`, and `docs/walkthrough.md` with the tour
      of the deployed resources, each paired with its console page.
- [x] 3.2 Add the screenshot inventory: a table of expected filenames, the page or view each
      comes from, and what it proves. List the files, do not embed them, so GitHub shows no
      broken images before the pictures exist *(verifies 3.2, 3.3)*.
- [x] 3.3 Add the "what went wrong and why" section: the five findings from the README plus the
      preflight gap, each with symptom, cause, and how it was caught.
- [x] 3.4 Add the warning about account id, API id, and tokens visible in developer tools, above
      the inventory rather than below it *(verifies 3.5)*.
- [x] 3.5 Link the walkthrough from `README.md` without embedding any image *(verifies 3.4)*.

## Task 4: Preserve the artefacts

- [x] 4.1 Move the end-to-end suite into the repository as `scripts/e2e.sh`, and make it
      self-contained: source `.env.test` relative to the script rather than by absolute path,
      and obtain the access and ID tokens with `aws cognito-idp initiate-auth` instead of
      reading them from files under `/tmp` *(verifies 4.1, 4.2)*.
- [x] 4.2 Write `.env.test.example` with the five variable names and placeholder values, and
      confirm `.gitignore` still excludes `.env.test` itself *(verifies 4.3)*.
- [x] 4.3 Run `scripts/e2e.sh` from a clean shell and confirm it passes without any manual
      setup, proving it is genuinely self-contained *(verifies 4.1)*.
- [x] 4.4 Verify nothing secret is staged: `git check-ignore` confirms `.env.test`,
      `terraform.tfstate`, `build/`, and `.terraform/` are excluded, and a grep over the staged
      tree finds no `eyJ`, no `AWS_SECRET_ACCESS_KEY`, and no password *(verifies 4.5)*.
- [x] 4.5 Record the deliberate exclusions in the walkthrough — Terraform state and the session
      transcript, each with the reason *(verifies 4.6)*.

## Task 5: Regression and handover

- [x] 5.1 Run `python3.13 -m pytest tests/unit -v` and confirm every test still passes. No new
      unit tests belong to this feature: the preflight is answered by API Gateway, and the page
      has no Python.
- [x] 5.2 Run `terraform plan` and confirm `No changes`, so the committed configuration matches
      the deployed API.
- [x] 5.3 Stage everything new, draft a commit message, and show it before committing.
- [x] 5.4 Hand over the remaining manual steps in one list: the browser check, the screenshots,
      and `terraform destroy`.
