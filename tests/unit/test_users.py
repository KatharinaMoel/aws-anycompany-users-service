# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Unit tests for the CRUD Lambda function.

Each test names the acceptance criterion from specs/users-service/requirements.md
that it checks.
"""

import json
import logging
import uuid

import pytest
from botocore.exceptions import ClientError

RECORD_FIELDS = {"userid", "name", "email", "createdAt", "updatedAt"}
VALID = {"name": "Grace Hopper", "email": "grace@example.com"}


def body_of(response):
    return json.loads(response["body"])


def create(users_app, proxy_event, payload=None):
    return users_app.handler(
        proxy_event("POST", "/users", payload if payload is not None else VALID), None
    )


# --------------------------------------------------------------------------
# Story 1 - create and list users
# --------------------------------------------------------------------------


def test_1_1_post_returns_201_with_the_five_fields(users_app, proxy_event):
    response = create(users_app, proxy_event)
    assert response["statusCode"] == 201
    record = body_of(response)
    assert set(record) == RECORD_FIELDS
    assert record["name"] == VALID["name"]
    assert record["email"] == VALID["email"]


def test_1_1_created_record_is_persisted(users_app, proxy_event, users_table):
    userid = body_of(create(users_app, proxy_event))["userid"]
    stored = users_table.get_item(Key={"userid": userid})["Item"]
    assert stored["name"] == VALID["name"]


def test_1_2_userid_is_a_server_generated_uuid4(users_app, proxy_event):
    userid = body_of(create(users_app, proxy_event))["userid"]
    assert str(uuid.UUID(userid, version=4)) == userid


def test_1_2_client_supplied_userid_is_ignored(users_app, proxy_event):
    record = body_of(create(users_app, proxy_event, {**VALID, "userid": "spoofed"}))
    assert record["userid"] != "spoofed"


def test_1_3_unrecognised_fields_are_not_persisted(
    users_app, proxy_event, users_table
):
    response = create(
        users_app,
        proxy_event,
        {**VALID, "role": "admin", "createdAt": "1999-01-01T00:00:00+00:00"},
    )
    record = body_of(response)
    assert set(record) == RECORD_FIELDS
    assert not record["createdAt"].startswith("1999")

    stored = users_table.get_item(Key={"userid": record["userid"]})["Item"]
    assert set(stored) == RECORD_FIELDS


def test_1_4_created_and_updated_match_on_create(users_app, proxy_event):
    record = body_of(create(users_app, proxy_event))
    assert record["createdAt"] == record["updatedAt"]
    # ISO 8601 in UTC
    assert record["createdAt"].endswith("+00:00")


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not json at all", id="malformed-json"),
        pytest.param('["not", "an", "object"]', id="json-array"),
        pytest.param('"a bare string"', id="json-string"),
        pytest.param({"email": "nobody@example.com"}, id="name-missing"),
        pytest.param({**VALID, "name": ""}, id="name-empty"),
        pytest.param({**VALID, "name": "   "}, id="name-whitespace-only"),
        pytest.param({**VALID, "name": 42}, id="name-not-a-string"),
        pytest.param({"name": "No Email"}, id="email-missing"),
        pytest.param({**VALID, "email": ""}, id="email-empty"),
        pytest.param(None, id="no-body"),
    ],
)
def test_1_5_invalid_post_returns_400(users_app, proxy_event, payload):
    response = users_app.handler(proxy_event("POST", "/users", payload), None)
    assert response["statusCode"] == 400
    assert "message" in body_of(response)


def test_1_5_invalid_post_writes_nothing(users_app, proxy_event, users_table):
    users_app.handler(proxy_event("POST", "/users", {"name": "", "email": ""}), None)
    assert users_table.scan()["Count"] == 0


def test_1_6_get_users_returns_an_envelope(users_app, proxy_event):
    create(users_app, proxy_event)
    response = users_app.handler(proxy_event("GET", "/users"), None)
    assert response["statusCode"] == 200
    assert len(body_of(response)["users"]) == 1


def test_1_6_get_users_returns_an_empty_array_when_none_exist(users_app, proxy_event):
    response = users_app.handler(proxy_event("GET", "/users"), None)
    assert body_of(response) == {"users": []}


def test_1_6_get_users_returns_every_record(users_app, proxy_event):
    for n in range(5):
        create(users_app, proxy_event, {"name": f"User {n}", "email": f"u{n}@x.com"})
    response = users_app.handler(proxy_event("GET", "/users"), None)
    assert len(body_of(response)["users"]) == 5


# --------------------------------------------------------------------------
# Story 2 - read, update, delete a single user
# --------------------------------------------------------------------------


def test_2_1_get_one_returns_the_record(users_app, proxy_event):
    created = body_of(create(users_app, proxy_event))
    response = users_app.handler(
        proxy_event("GET", "/users/{userid}", userid=created["userid"]), None
    )
    assert response["statusCode"] == 200
    assert body_of(response) == created


def test_2_2_get_unknown_id_returns_404(users_app, proxy_event):
    response = users_app.handler(
        proxy_event("GET", "/users/{userid}", userid=str(uuid.uuid4())), None
    )
    assert response["statusCode"] == 404
    assert body_of(response)["message"] == users_app.NOT_FOUND


def test_2_3_put_replaces_fields_and_refreshes_updated_at(users_app, proxy_event):
    created = body_of(create(users_app, proxy_event))
    changed = {"name": "Grace B. Hopper", "email": "ghopper@example.com"}

    response = users_app.handler(
        proxy_event("PUT", "/users/{userid}", changed, userid=created["userid"]), None
    )
    assert response["statusCode"] == 200

    record = body_of(response)
    assert record["name"] == changed["name"]
    assert record["email"] == changed["email"]
    assert record["userid"] == created["userid"]
    assert record["createdAt"] == created["createdAt"]
    assert record["updatedAt"] >= created["updatedAt"]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param("not json", id="malformed-json"),
        pytest.param({**VALID, "name": ""}, id="name-empty"),
        pytest.param({"name": "No Email"}, id="email-missing"),
    ],
)
def test_2_4_invalid_put_returns_400_and_changes_nothing(
    users_app, proxy_event, users_table, payload
):
    created = body_of(create(users_app, proxy_event))
    response = users_app.handler(
        proxy_event("PUT", "/users/{userid}", payload, userid=created["userid"]), None
    )
    assert response["statusCode"] == 400

    stored = users_table.get_item(Key={"userid": created["userid"]})["Item"]
    assert stored["name"] == VALID["name"]
    assert stored["updatedAt"] == created["updatedAt"]


def test_2_5_put_unknown_id_returns_404_and_creates_nothing(
    users_app, proxy_event, users_table
):
    response = users_app.handler(
        proxy_event("PUT", "/users/{userid}", VALID, userid=str(uuid.uuid4())), None
    )
    assert response["statusCode"] == 404
    assert users_table.scan()["Count"] == 0


def test_2_6_delete_returns_200_and_an_empty_object(users_app, proxy_event):
    created = body_of(create(users_app, proxy_event))
    response = users_app.handler(
        proxy_event("DELETE", "/users/{userid}", userid=created["userid"]), None
    )
    assert response["statusCode"] == 200
    assert body_of(response) == {}


def test_2_6_get_after_delete_returns_404(users_app, proxy_event):
    created = body_of(create(users_app, proxy_event))
    users_app.handler(
        proxy_event("DELETE", "/users/{userid}", userid=created["userid"]), None
    )
    response = users_app.handler(
        proxy_event("GET", "/users/{userid}", userid=created["userid"]), None
    )
    assert response["statusCode"] == 404


def test_2_6_delete_unknown_id_returns_404(users_app, proxy_event):
    response = users_app.handler(
        proxy_event("DELETE", "/users/{userid}", userid=str(uuid.uuid4())), None
    )
    assert response["statusCode"] == 404


# --------------------------------------------------------------------------
# Story 4 - operable service
# --------------------------------------------------------------------------


def test_4_1_logs_one_info_record_naming_the_route(users_app, proxy_event, caplog):
    with caplog.at_level(logging.INFO):
        users_app.handler(proxy_event("GET", "/users"), None)

    records = [r for r in caplog.records if r.message == "request handled"]
    assert len(records) == 1
    assert records[0].route == "GET /users"
    assert records[0].status == 200
    assert records[0].api_request_id == "test-request-id"


def test_4_1_never_logs_the_event_or_a_token(users_app, proxy_event, caplog):
    event = proxy_event("POST", "/users", VALID)
    event["headers"] = {"Authorization": "eyJraWQiOiJzZWNyZXQifQ.payload.signature"}

    with caplog.at_level(logging.INFO):
        users_app.handler(event, None)

    logged = "\n".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "eyJ" not in logged
    assert "Authorization" not in logged
    assert "pathParameters" not in logged


def test_4_2_dynamodb_failure_returns_a_generic_500(
    users_app, proxy_event, monkeypatch, caplog
):
    error = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow down"}},
        "Scan",
    )
    monkeypatch.setattr(users_app.table, "scan", lambda **kwargs: (_ for _ in ()).throw(error))

    with caplog.at_level(logging.INFO):
        response = users_app.handler(proxy_event("GET", "/users"), None)

    assert response["statusCode"] == 500
    assert body_of(response) == {"message": users_app.GENERIC_DB_ERROR}
    # The detail goes to the log, not to the caller.
    assert "ProvisionedThroughputExceededException" in caplog.text
    assert "ProvisionedThroughputExceededException" not in response["body"]


def test_4_2_unexpected_error_returns_a_generic_500(
    users_app, proxy_event, monkeypatch
):
    monkeypatch.setattr(
        users_app.table, "scan", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom"))
    )
    response = users_app.handler(proxy_event("GET", "/users"), None)
    assert response["statusCode"] == 500
    assert body_of(response) == {"message": users_app.INTERNAL_ERROR}


@pytest.mark.parametrize(
    "method,resource,payload,userid",
    [
        ("GET", "/users", None, None),
        ("POST", "/users", VALID, None),
        ("POST", "/users", {"name": ""}, None),
        ("GET", "/users/{userid}", None, "11111111-1111-4111-8111-111111111111"),
        ("PATCH", "/users", None, None),
    ],
)
def test_4_3_every_response_carries_cors_headers(
    users_app, proxy_event, method, resource, payload, userid
):
    response = users_app.handler(
        proxy_event(method, resource, payload, userid=userid), None
    )
    headers = response["headers"]
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert "Access-Control-Allow-Headers" in headers
    assert "Access-Control-Allow-Methods" in headers
    assert headers["Content-Type"] == "application/json"


def test_unmatched_route_returns_405(users_app, proxy_event):
    response = users_app.handler(proxy_event("PATCH", "/users"), None)
    assert response["statusCode"] == 405


def test_missing_path_parameter_returns_400(users_app, proxy_event):
    event = proxy_event("GET", "/users/{userid}")
    event["pathParameters"] = None
    response = users_app.handler(event, None)
    assert response["statusCode"] == 400
