# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Unit tests for GET /users/search.

Each test names the acceptance criterion from
specs/customer-search/requirements.md that it checks.
"""

import json
import logging

import pytest
from botocore.exceptions import ClientError

from conftest import EMAIL_INDEX_NAME

SEARCH = ("GET", "/users/search")


def body_of(response):
    return json.loads(response["body"])


def search(users_app, proxy_event, query):
    return users_app.handler(proxy_event(*SEARCH, query=query), None)


def store(users_app, proxy_event, name, email):
    created = users_app.handler(
        proxy_event("POST", "/users", {"name": name, "email": email}), None
    )
    return body_of(created)


# --------------------------------------------------------------------------
# Story 1 - search for users by email
# --------------------------------------------------------------------------


def test_1_1_search_returns_the_matching_record(users_app, proxy_event):
    grace = store(users_app, proxy_event, "Grace Hopper", "grace@example.com")
    store(users_app, proxy_event, "Ada Lovelace", "ada@example.com")

    response = search(users_app, proxy_event, {"email": "grace@example.com"})

    assert response["statusCode"] == 200
    users = body_of(response)["users"]
    assert len(users) == 1
    assert users[0] == grace


def test_1_1_search_returns_every_record_sharing_an_email(users_app, proxy_event):
    """Email is not enforced unique, so a match may be more than one record."""
    for name in ("First Signup", "Second Signup"):
        store(users_app, proxy_event, name, "shared@example.com")

    users = body_of(search(users_app, proxy_event, {"email": "shared@example.com"}))["users"]
    assert len(users) == 2
    assert {u["name"] for u in users} == {"First Signup", "Second Signup"}


def test_1_2_no_match_returns_200_and_an_empty_array(users_app, proxy_event):
    store(users_app, proxy_event, "Grace Hopper", "grace@example.com")

    response = search(users_app, proxy_event, {"email": "nobody@example.com"})

    assert response["statusCode"] == 200
    assert body_of(response) == {"users": []}


@pytest.mark.parametrize(
    "query",
    [
        pytest.param(None, id="no-query-string"),
        pytest.param({}, id="empty-query-string"),
        pytest.param({"name": "Grace"}, id="wrong-parameter"),
        pytest.param({"email": ""}, id="empty-email"),
        pytest.param({"email": "   "}, id="whitespace-only-email"),
    ],
)
def test_1_3_missing_email_returns_400_without_querying(
    users_app, proxy_event, monkeypatch, query
):
    def must_not_run(**kwargs):
        raise AssertionError("the index was queried despite an invalid request")

    monkeypatch.setattr(users_app.table, "query", must_not_run)

    response = search(users_app, proxy_event, query)
    assert response["statusCode"] == 400
    assert "message" in body_of(response)


def test_1_5_search_queries_the_index_and_never_scans(
    users_app, proxy_event, monkeypatch
):
    calls = []
    real_query = users_app.table.query
    monkeypatch.setattr(
        users_app.table, "query", lambda **kw: (calls.append(kw), real_query(**kw))[1]
    )
    monkeypatch.setattr(
        users_app.table,
        "scan",
        lambda **kw: (_ for _ in ()).throw(AssertionError("search scanned the table")),
    )

    search(users_app, proxy_event, {"email": "grace@example.com"})

    assert len(calls) == 1
    assert calls[0]["IndexName"] == EMAIL_INDEX_NAME


def test_1_6_the_match_is_case_sensitive(users_app, proxy_event):
    store(users_app, proxy_event, "Grace Hopper", "grace@example.com")

    users = body_of(search(users_app, proxy_event, {"email": "GRACE@example.com"}))["users"]
    assert users == []


def test_1_6_surrounding_whitespace_is_stripped(users_app, proxy_event):
    """parse_body stores the stripped value, so the search term is stripped too."""
    store(users_app, proxy_event, "Grace Hopper", "grace@example.com")

    users = body_of(search(users_app, proxy_event, {"email": "  grace@example.com  "}))["users"]
    assert len(users) == 1


def test_1_7_search_follows_pagination(users_app, proxy_event, monkeypatch):
    pages = [
        {
            "Items": [{"userid": "1", "email": "shared@example.com"}],
            "LastEvaluatedKey": {"email": "shared@example.com", "userid": "1"},
        },
        {"Items": [{"userid": "2", "email": "shared@example.com"}]},
    ]
    calls = []

    def paged_query(**kwargs):
        calls.append(kwargs)
        return pages[len(calls) - 1]

    monkeypatch.setattr(users_app.table, "query", paged_query)

    users = body_of(search(users_app, proxy_event, {"email": "shared@example.com"}))["users"]

    assert len(users) == 2
    assert len(calls) == 2
    assert calls[1]["ExclusiveStartKey"] == pages[0]["LastEvaluatedKey"]


def test_1_8_query_failure_returns_a_generic_500(
    users_app, proxy_event, monkeypatch, caplog
):
    error = ClientError(
        {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow down"}},
        "Query",
    )
    monkeypatch.setattr(
        users_app.table, "query", lambda **kw: (_ for _ in ()).throw(error)
    )

    with caplog.at_level(logging.INFO):
        response = search(users_app, proxy_event, {"email": "grace@example.com"})

    assert response["statusCode"] == 500
    assert body_of(response) == {"message": users_app.GENERIC_DB_ERROR}
    assert "ProvisionedThroughputExceededException" in caplog.text
    assert "ProvisionedThroughputExceededException" not in response["body"]


def test_1_9_responses_carry_cors_headers_and_log_the_route(
    users_app, proxy_event, caplog
):
    with caplog.at_level(logging.INFO):
        response = search(users_app, proxy_event, {"email": "grace@example.com"})

    headers = response["headers"]
    assert headers["Access-Control-Allow-Origin"] == "*"
    assert "Access-Control-Allow-Headers" in headers
    assert "Access-Control-Allow-Methods" in headers

    records = [r for r in caplog.records if r.message == "request handled"]
    assert len(records) == 1
    assert records[0].route == "GET /users/search"
    assert records[0].status == 200


# --------------------------------------------------------------------------
# Story 2 - the MVP keeps working
# --------------------------------------------------------------------------


def test_2_1_the_existing_routes_are_untouched(users_app, proxy_event):
    created = store(users_app, proxy_event, "Grace Hopper", "grace@example.com")

    listed = users_app.handler(proxy_event("GET", "/users"), None)
    fetched = users_app.handler(
        proxy_event("GET", "/users/{userid}", userid=created["userid"]), None
    )

    assert listed["statusCode"] == 200
    assert len(body_of(listed)["users"]) == 1
    assert fetched["statusCode"] == 200
    assert body_of(fetched) == created


def test_2_3_search_is_not_treated_as_a_userid(users_app, proxy_event):
    """The literal path wins at the API; the handler keys the two routes apart."""
    as_search = users_app.handler(
        proxy_event(*SEARCH, query={"email": "grace@example.com"}), None
    )
    as_userid = users_app.handler(
        proxy_event("GET", "/users/{userid}", userid="search"), None
    )

    assert as_search["statusCode"] == 200
    assert as_userid["statusCode"] == 404
