# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""CRUD handler for the AnyCompany Users Service.

Routes API Gateway REST (v1) proxy events by httpMethod and resource.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

# With the function's log format set to JSON, fields passed in extra={...} become JSON keys.
logger = logging.getLogger()
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
EMAIL_INDEX_NAME = os.environ.get("EMAIL_INDEX_NAME", "email-index")
CORS_ALLOW_ORIGIN = os.environ.get("CORS_ALLOW_ORIGIN", "*")

# Module scope, so the client and its connection pool are reused across invocations.
table = boto3.resource("dynamodb").Table(TABLE_NAME)

RESPONSE_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": CORS_ALLOW_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,DELETE,OPTIONS",
}

GENERIC_DB_ERROR = "Could not complete the request"
INTERNAL_ERROR = "Internal server error"
NOT_FOUND = "User not found"


class ValidationError(Exception):
    """Raised when a request body is not a user record we can store."""


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def response(status, body):
    return {
        "statusCode": status,
        "headers": dict(RESPONSE_HEADERS),
        "body": json.dumps(body),
    }


def parse_body(event):
    """Return only the name and email from the request body.

    Anything else a client sends - userid, createdAt, or an unknown field - is
    dropped here, so it can never reach the table.
    """
    try:
        body = json.loads(event.get("body") or "")
    except (TypeError, ValueError):
        raise ValidationError("Request body must be valid JSON")

    if not isinstance(body, dict):
        raise ValidationError("Request body must be a JSON object")

    fields = {}
    for field in ("name", "email"):
        value = body.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValidationError(f"Field '{field}' must be a non-empty string")
        fields[field] = value.strip()
    return fields


def path_userid(event):
    userid = (event.get("pathParameters") or {}).get("userid")
    if not userid:
        raise ValidationError("Path parameter 'userid' is required")
    return userid


def list_users(event):
    users = []
    kwargs = {}
    while True:
        page = table.scan(**kwargs)
        users.extend(page.get("Items", []))
        start_key = page.get("LastEvaluatedKey")
        if not start_key:
            break
        kwargs["ExclusiveStartKey"] = start_key
    return response(200, {"users": users})


def search_users(event):
    """Find records by exact email, through the email index rather than a scan."""
    # API Gateway sends queryStringParameters as null when the request carries
    # no query string, so fall back to an empty dict before reading from it.
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


def create_user(event):
    fields = parse_body(event)
    timestamp = now_iso()
    item = {
        "userid": str(uuid.uuid4()),
        **fields,
        "createdAt": timestamp,
        "updatedAt": timestamp,
    }
    table.put_item(Item=item)
    return response(201, item)


def get_user(event):
    item = table.get_item(Key={"userid": path_userid(event)}).get("Item")
    if item is None:
        return response(404, {"message": NOT_FOUND})
    return response(200, item)


def update_user(event):
    userid = path_userid(event)
    fields = parse_body(event)

    existing = table.get_item(Key={"userid": userid}).get("Item")
    if existing is None:
        return response(404, {"message": NOT_FOUND})

    timestamp = now_iso()
    item = {
        "userid": userid,
        **fields,
        # Fall back to now if a stored record somehow has no createdAt.
        "createdAt": existing.get("createdAt", timestamp),
        "updatedAt": timestamp,
    }
    table.put_item(Item=item)
    return response(200, item)


def delete_user(event):
    userid = path_userid(event)
    try:
        table.delete_item(
            Key={"userid": userid},
            ConditionExpression="attribute_exists(userid)",
        )
    except ClientError as error:
        if error.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return response(404, {"message": NOT_FOUND})
        raise
    return response(200, {})


ROUTES = {
    ("GET", "/users"): list_users,
    ("GET", "/users/search"): search_users,
    ("POST", "/users"): create_user,
    ("GET", "/users/{userid}"): get_user,
    ("PUT", "/users/{userid}"): update_user,
    ("DELETE", "/users/{userid}"): delete_user,
}


def handler(event, context):
    method = event.get("httpMethod")
    resource = event.get("resource")
    route = f"{method} {resource}"
    userid = (event.get("pathParameters") or {}).get("userid")

    # The API Gateway request id also appears in the stage access log, so it is
    # what ties a function record to the access-log record for the same call.
    context_fields = {
        "route": route,
        "userid": userid,
        "api_request_id": (event.get("requestContext") or {}).get("requestId", ""),
    }

    operation = ROUTES.get((method, resource))
    if operation is None:
        result = response(405, {"message": "Method not allowed"})
    else:
        try:
            result = operation(event)
        except ValidationError as error:
            result = response(400, {"message": str(error)})
        except ClientError as error:
            # Details to the log, a generic message to the client.
            logger.exception(
                "DynamoDB call failed", extra={**context_fields, "error": str(error)}
            )
            result = response(500, {"message": GENERIC_DB_ERROR})
        except Exception:
            # Nothing should reach here, but a bug must not become a bare 502
            # without a JSON body.
            logger.exception("Request failed", extra=context_fields)
            result = response(500, {"message": INTERNAL_ERROR})

    logger.info(
        "request handled",
        extra={**context_fields, "status": result["statusCode"]},
    )
    return result
