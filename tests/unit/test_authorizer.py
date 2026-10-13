# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Unit tests for the Lambda TOKEN authorizer.

Tokens are signed here with a throwaway RSA key and the JWKS fetch is replaced
with a local function, so no test reaches Cognito or any network.
"""

import json
import logging
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm

from conftest import APP_CLIENT_ID, REGION, SRC, USER_POOL_ID, load_module

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
METHOD_ARN = f"arn:aws:execute-api:{REGION}:123456789012:bllwti9noj/prod/GET/users"
STAGE_RESOURCE = f"arn:aws:execute-api:{REGION}:123456789012:bllwti9noj/prod/*/*"
KID = "test-key-1"
OTHER_KID = "test-key-2"
SUB = "98e1c3e0-4051-70c6-714b-521797590940"


def generate_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


# Generated once for the whole module: RSA key generation is slow, and these are
# throwaway keys for signing test tokens.
PRIVATE_KEY = generate_key()
OTHER_KEY = generate_key()


def jwks_for(*pairs):
    """Build a JWKS document from (kid, private key) pairs."""
    keys = []
    for kid, key in pairs:
        jwk = json.loads(RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update({"kid": kid, "alg": "RS256", "use": "sig"})
        keys.append(jwk)
    return {"keys": keys}


def access_claims(**overrides):
    now = int(time.time())
    claims = {
        "sub": SUB,
        "iss": ISSUER,
        "client_id": APP_CLIENT_ID,
        "token_use": "access",
        "username": "workshop@example.com",
        "scope": "aws.cognito.signin.user.admin",
        "iat": now,
        "exp": now + 3600,
    }
    claims.update(overrides)
    return {k: v for k, v in claims.items() if v is not None}


def sign(claims, key=PRIVATE_KEY, kid=KID):
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": kid})


def event(token, method_arn=METHOD_ARN):
    return {"type": "TOKEN", "authorizationToken": token, "methodArn": method_arn}


@pytest.fixture
def authorizer(monkeypatch):
    """The authorizer, with its JWKS fetch replaced by a local function.

    Patching fetch_data rather than the whole client keeps PyJWKClient's real
    caching and its refetch-on-unknown-kid behaviour under test. The counter
    makes the number of fetches observable.
    """
    monkeypatch.setenv("USER_POOL_ID", USER_POOL_ID)
    monkeypatch.setenv("APP_CLIENT_ID", APP_CLIENT_ID)
    monkeypatch.setenv("AWS_REGION", REGION)

    module = load_module("authorizer_app", SRC / "authorizer" / "app.py")
    module.fetch_calls = 0

    def fake_fetch():
        module.fetch_calls += 1
        return jwks_for((KID, PRIVATE_KEY))

    monkeypatch.setattr(module.jwks_client, "fetch_data", fake_fetch)
    return module


def test_valid_access_token_is_allowed(authorizer):
    policy = authorizer.handler(event(sign(access_claims())), None)

    assert policy["principalId"] == SUB
    statement = policy["policyDocument"]["Statement"][0]
    assert statement["Effect"] == "Allow"
    assert statement["Action"] == "execute-api:Invoke"
    assert statement["Resource"] == [STAGE_RESOURCE]


def test_policy_covers_every_method_in_the_stage(authorizer):
    """Requirement 3.6: the cached policy is replayed across routes."""
    for arn in (
        f"arn:aws:execute-api:{REGION}:123456789012:bllwti9noj/prod/DELETE/users/abc",
        f"arn:aws:execute-api:{REGION}:123456789012:bllwti9noj/prod/POST/users",
    ):
        policy = authorizer.handler(event(sign(access_claims()), arn), None)
        assert policy["policyDocument"]["Statement"][0]["Resource"] == [STAGE_RESOURCE]


def test_stage_resource_survives_a_colon_in_the_path(authorizer):
    """rsplit(':', 1) would split inside the path and corrupt the ARN."""
    arn = f"arn:aws:execute-api:{REGION}:123456789012:bllwti9noj/prod/GET/users/a:b"
    policy = authorizer.handler(event(sign(access_claims()), arn), None)
    assert policy["policyDocument"]["Statement"][0]["Resource"] == [STAGE_RESOURCE]


def test_context_carries_identity_for_the_integration(authorizer):
    policy = authorizer.handler(event(sign(access_claims())), None)
    assert policy["context"] == {
        "userId": SUB,
        "username": "workshop@example.com",
        "scope": "aws.cognito.signin.user.admin",
    }


@pytest.mark.parametrize(
    "token_factory,reason",
    [
        pytest.param(
            lambda: sign(access_claims(token_use="id", client_id=APP_CLIENT_ID)),
            "token_use is not access",
            id="id-token-with-client-id",
        ),
        pytest.param(
            lambda: sign(access_claims(token_use=None, aud=APP_CLIENT_ID)),
            "missing token_use",
            id="id-token-shaped",
        ),
        pytest.param(
            lambda: sign(access_claims(client_id="some-other-app-client")),
            "wrong client_id",
            id="wrong-client-id",
        ),
        pytest.param(
            lambda: sign(access_claims(client_id=None)),
            "missing client_id",
            id="no-client-id",
        ),
        pytest.param(
            lambda: sign(
                access_claims(iss="https://cognito-idp.us-west-2.amazonaws.com/us-west-2_other")
            ),
            "another user pool",
            id="wrong-issuer",
        ),
        pytest.param(
            lambda: sign(access_claims(exp=int(time.time()) - 60)),
            "expired",
            id="expired",
        ),
        pytest.param(
            lambda: sign(access_claims(sub=None)),
            "missing sub",
            id="no-sub",
        ),
        pytest.param(
            lambda: sign(access_claims(), key=OTHER_KEY),
            "signed by a key that is not in the JWKS",
            id="bad-signature",
        ),
        pytest.param(lambda: "", "no token", id="empty-token"),
        pytest.param(lambda: "not.a.jwt", "malformed", id="malformed-token"),
        pytest.param(lambda: "Bearer ", "no token after the prefix", id="bearer-only"),
        pytest.param(
            lambda: jwt.encode(access_claims(), PRIVATE_KEY, algorithm="RS256"),
            "no kid header",
            id="no-kid",
        ),
    ],
)
def test_bad_tokens_are_denied(authorizer, token_factory, reason):
    with pytest.raises(Exception, match="^Unauthorized$"):
        authorizer.handler(event(token_factory()), None)


def test_unsigned_token_is_denied(authorizer):
    """An alg=none token must never be accepted."""
    token = jwt.encode(access_claims(), key=None, algorithm="none", headers={"kid": KID})
    with pytest.raises(Exception, match="^Unauthorized$"):
        authorizer.handler(event(token), None)


def test_denial_logs_a_reason_but_never_the_token(authorizer, caplog):
    token = sign(access_claims(client_id="some-other-app-client"))

    with caplog.at_level(logging.INFO):
        with pytest.raises(Exception, match="^Unauthorized$"):
            authorizer.handler(event(token), None)

    logged = "\n".join(r.getMessage() + str(r.__dict__) for r in caplog.records)
    assert "authorization denied" in logged
    assert "client_id is not this app client" in logged
    assert token not in logged
    assert "eyJ" not in logged


def test_success_logs_the_principal_and_resource(authorizer, caplog):
    with caplog.at_level(logging.INFO):
        authorizer.handler(event(sign(access_claims())), None)

    granted = [r for r in caplog.records if r.message == "authorization granted"]
    assert len(granted) == 1
    assert granted[0].principal == SUB
    assert granted[0].resource == STAGE_RESOURCE


def test_bearer_prefix_is_accepted_case_insensitively(authorizer):
    token = sign(access_claims())
    for prefix in ("Bearer ", "bearer ", "BEARER "):
        policy = authorizer.handler(event(prefix + token), None)
        assert policy["principalId"] == SUB


def test_jwks_is_fetched_once_across_invocations(authorizer):
    """Requirement 3.7: only a cold start fetches the JWKS."""
    for _ in range(3):
        authorizer.handler(event(sign(access_claims())), None)
    assert authorizer.fetch_calls == 1


def test_unknown_kid_triggers_one_refetch_then_denies(authorizer):
    """A key rotation must not need a cold start to be noticed."""
    authorizer.handler(event(sign(access_claims())), None)
    assert authorizer.fetch_calls == 1

    with pytest.raises(Exception, match="^Unauthorized$"):
        authorizer.handler(event(sign(access_claims(), kid=OTHER_KID)), None)

    # The client refetched, looking for the unknown kid, then gave up.
    assert authorizer.fetch_calls == 2


def test_rotated_key_is_picked_up_without_a_cold_start(authorizer, monkeypatch):
    authorizer.handler(event(sign(access_claims())), None)

    def fetch_rotated():
        authorizer.fetch_calls += 1
        return jwks_for((KID, PRIVATE_KEY), (OTHER_KID, OTHER_KEY))

    monkeypatch.setattr(authorizer.jwks_client, "fetch_data", fetch_rotated)

    policy = authorizer.handler(
        event(sign(access_claims(), key=OTHER_KEY, kid=OTHER_KID)), None
    )
    assert policy["principalId"] == SUB


def test_jwks_connection_failure_fails_closed(authorizer, monkeypatch, caplog):
    def unreachable():
        raise jwt.exceptions.PyJWKClientConnectionError("cannot reach the endpoint")

    monkeypatch.setattr(authorizer.jwks_client, "fetch_data", unreachable)

    with caplog.at_level(logging.INFO):
        with pytest.raises(Exception, match="^Unauthorized$"):
            authorizer.handler(event(sign(access_claims())), None)

    # Logged as an infrastructure fault, not as a rejected token.
    assert "could not reach the JWKS endpoint" in caplog.text
    assert any(r.levelno >= logging.ERROR for r in caplog.records)


@pytest.mark.parametrize(
    "method_arn",
    ["", "not-an-arn", "arn:aws:execute-api:us-west-2:123456789012:onlyapi"],
)
def test_malformed_method_arn_is_denied(authorizer, method_arn):
    with pytest.raises(Exception, match="^Unauthorized$"):
        authorizer.handler(event(sign(access_claims()), method_arn), None)
