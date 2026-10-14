# Screenshots

The running service, captured in the AWS console and the demo client shortly before the
deployment was destroyed. This page only shows the pictures. What each one proves, and what it
does not, is in the caption under the same heading in the [walkthrough](../walkthrough.md#screenshots);
how they were taken is in [`screenshot-process.md`](../screenshot-process.md).

The captions live in one place on purpose, so that a correction cannot reach one copy and miss
the other.

## 01 — API Gateway → Resources

![API Gateway resource tree with GET /users selected](01-api-resources.png)

[Caption in the walkthrough](../walkthrough.md#01--api-gateway--resources)

## 02 — API Gateway → Stages → prod

![The prod stage with X-Ray tracing and access logging active](02-api-stage.png)

[Caption in the walkthrough](../walkthrough.md#02--api-gateway--stages--prod)

## 03 — Lambda → anycompany-users-crud → Configuration

![General configuration of the CRUD function](03-lambda-crud.png)

[Caption in the walkthrough](../walkthrough.md#03--lambda--anycompany-users-crud--configuration)

## 04 — DynamoDB → table → Indexes

![The email-index global secondary index](04-dynamodb-index.png)

[Caption in the walkthrough](../walkthrough.md#04--dynamodb--table--indexes)

## 05 — DynamoDB → Item explorer

![A scan of the users table returning two items](05-dynamodb-items.png)

[Caption in the walkthrough](../walkthrough.md#05--dynamodb--item-explorer)

## 06 — Cognito → user pool → Users

![The user pool's single user](06-cognito-user.png)

[Caption in the walkthrough](../walkthrough.md#06--cognito--user-pool--users)

## 07 — CloudWatch Logs, entries expanded

![Expanded JSON log events of the CRUD function](07-cloudwatch-json-log.png)

[Caption in the walkthrough](../walkthrough.md#07--cloudwatch-logs-entries-expanded)

## 08 — CloudWatch → Application Signals → Trace Map

![Trace map from the client through the API Gateway stage to both functions](08-xray-service-map.png)

[Caption in the walkthrough](../walkthrough.md#08--cloudwatch--application-signals--trace-map)

## 09 — The demo client, logged in

![The demo client with a token in memory and a 200 response](09-browser-authorized.png)

[Caption in the walkthrough](../walkthrough.md#09--the-demo-client-logged-in)

## 10 — The demo client, rejected

![The demo client showing a 401 response](10-browser-401.png)

[Caption in the walkthrough](../walkthrough.md#10--the-demo-client-rejected)

## 11 — The demo client next to `.env.test`

![The demo client signed in, beside the editor showing .env.test](11-demo-and-env-test.png)

[Caption in the walkthrough](../walkthrough.md#11--the-demo-client-next-to-envtest)

## 12 — API Gateway → Resources → `OPTIONS /users/{userid}`

![The OPTIONS method on /users/{userid} with no authorization and a mock integration](12-api-options-preflight.png)

[Caption in the walkthrough](../walkthrough.md#12--api-gateway--resources--options-usersuserid)

## 13 — Lambda → anycompany-users-crud → Monitoring and operations tools

![Logging configuration of the CRUD function](13-lambda-logging.png)

[Caption in the walkthrough](../walkthrough.md#13--lambda--anycompany-users-crud--monitoring-and-operations-tools)

## 14 — DynamoDB → table → Settings

![Table settings with deletion protection off](14-dynamodb-deletion-protection.png)

[Caption in the walkthrough](../walkthrough.md#14--dynamodb--table--settings)

## 15 — X-Ray → Analytics, filtered to the CRUD function

![X-Ray analytics for the CRUD function](15-xray-analytics.png)

[Caption in the walkthrough](../walkthrough.md#15--x-ray--analytics-filtered-to-the-crud-function)
