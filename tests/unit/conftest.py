# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Shared fixtures for the Users Service unit tests."""

import importlib.util
import json
import sys
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

SRC = Path(__file__).resolve().parents[2] / "src"

# Loading the Lambda modules by path would otherwise leave __pycache__
# directories inside src/, which holds only our own source - and which
# Terraform hashes to decide whether to redeploy a function.
sys.dont_write_bytecode = True

TABLE_NAME = "test-anycompany-users"
EMAIL_INDEX_NAME = "email-index"
REGION = "us-west-2"
USER_POOL_ID = "us-west-2_testpool"
APP_CLIENT_ID = "test-app-client-id"


def load_module(name, path):
    """Load a Lambda module by file path, under a name of our choosing.

    Both functions live in a file called app.py, so importing them by module
    name would mean whichever test imported first wins and the second test
    silently exercises the wrong function. Loading by path with a distinct
    module name keeps the two test files independent.

    The module is executed on every call, so each test gets a fresh copy with
    its own module-scope state - the boto3 table handle and the JWKS cache.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def aws_credentials(monkeypatch):
    """Point botocore at obviously fake credentials.

    mock_aws intercepts the calls anyway, but this guarantees a test can never
    reach the real account if a mock is ever missing or mis-scoped.
    """
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_REGION", REGION)
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)


@pytest.fixture
def users_table(aws_credentials):
    """An empty users table, with the same key schema as the real one."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)
        client.create_table(
            TableName=TABLE_NAME,
            KeySchema=[{"AttributeName": "userid", "KeyType": "HASH"}],
            AttributeDefinitions=[
                {"AttributeName": "userid", "AttributeType": "S"},
                {"AttributeName": "email", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": EMAIL_INDEX_NAME,
                    "KeySchema": [{"AttributeName": "email", "KeyType": "HASH"}],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield boto3.resource("dynamodb", region_name=REGION).Table(TABLE_NAME)


@pytest.fixture
def users_app(users_table, monkeypatch):
    """The CRUD function, imported against the mocked table."""
    monkeypatch.setenv("TABLE_NAME", TABLE_NAME)
    monkeypatch.setenv("EMAIL_INDEX_NAME", EMAIL_INDEX_NAME)
    monkeypatch.setenv("CORS_ALLOW_ORIGIN", "*")
    return load_module("users_app", SRC / "users" / "app.py")


@pytest.fixture
def proxy_event():
    """Build the parts of an API Gateway REST proxy event the handler reads."""

    def make(
        method,
        resource,
        body=None,
        userid=None,
        query=None,
        request_id="test-request-id",
    ):
        if body is not None and not isinstance(body, str):
            body = json.dumps(body)
        return {
            "httpMethod": method,
            "resource": resource,
            "pathParameters": {"userid": userid} if userid else None,
            # API Gateway sends null, not {}, when there is no query string.
            "queryStringParameters": query,
            "body": body,
            "requestContext": {"requestId": request_id},
        }

    return make
