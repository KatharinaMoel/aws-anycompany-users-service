# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0

"""Lambda TOKEN authorizer for the AnyCompany Users Service.

Accepts only Cognito access tokens that this user pool issued for this app
client, and returns a policy covering every method in the stage because API
Gateway caches the result and replays it across routes.
"""

import logging
import os

import jwt  # PyJWT
from jwt.exceptions import (
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
)

# With the function's log format set to JSON, fields passed in extra={...} become JSON keys.
logger = logging.getLogger()
logger.setLevel(logging.INFO)

USER_POOL_ID = os.environ["USER_POOL_ID"]
APP_CLIENT_ID = os.environ["APP_CLIENT_ID"]
REGION = os.environ["AWS_REGION"]  # set by the Lambda runtime

ISSUER = f"https://cognito-idp.{REGION}.amazonaws.com/{USER_POOL_ID}"
JWKS_URL = f"{ISSUER}/.well-known/jwks.json"

# One client per execution environment. It downloads Cognito's public keys the
# first time it needs them and holds them for `lifespan` seconds - set well past
# any container lifetime, so in practice only a cold start fetches. A key
# rotation is still handled, because PyJWKClient refetches the set when a
# token's kid is missing from it.
JWKS_LIFESPAN_SECONDS = 86400
JWKS_TIMEOUT_SECONDS = 5

jwks_client = jwt.PyJWKClient(
    JWKS_URL,
    timeout=JWKS_TIMEOUT_SECONDS,
    lifespan=JWKS_LIFESPAN_SECONDS,
)


class Unauthorized(Exception):
    """Raised for any token this authorizer will not accept."""


def validate_token(token):
    """Return the claims of a valid access token, or raise."""
    # The token's kid header names the key that signed it; the client looks that
    # key up in the JWKS it holds.
    signing_key = jwks_client.get_signing_key_from_jwt(token)

    claims = jwt.decode(
        token,
        signing_key.key,
        algorithms=["RS256"],
        issuer=ISSUER,
        # A Cognito access token carries client_id, not aud, so audience
        # verification is off here and client_id is checked below. Requiring
        # both claims means a token without them fails verification outright,
        # rather than failing a comparison against None further down.
        options={
            "verify_aud": False,
            "require": ["exp", "iss", "sub", "token_use", "client_id"],
        },
    )

    # Rejects ID tokens, which this pool signs with the very same keys.
    if claims["token_use"] != "access":
        raise Unauthorized("token_use is not access")

    if claims["client_id"] != APP_CLIENT_ID:
        raise Unauthorized("client_id is not this app client")

    return claims


def stage_resource(method_arn):
    """Widen a single method ARN to every method of every resource in the stage.

    arn:aws:execute-api:<region>:<account>:<api-id>/<stage>/GET/users
      becomes
    arn:aws:execute-api:<region>:<account>:<api-id>/<stage>/*/*

    API Gateway caches this policy for authorizerResultTtlInSeconds and replays
    it for other routes, so a policy naming one method would deny the rest.
    """
    # Split on the first five colons rather than the last one: a request path
    # may itself contain a colon, which would shift the boundary.
    parts = method_arn.split(":", 5)
    if len(parts) < 6:
        raise Unauthorized("unexpected methodArn")

    path = parts[5].split("/")
    if len(path) < 2:
        raise Unauthorized("unexpected methodArn path")

    api_id, stage = path[0], path[1]
    return f"{':'.join(parts[:5])}:{api_id}/{stage}/*/*"


def allow_policy(claims, method_arn):
    return {
        "principalId": claims["sub"],
        "policyDocument": {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "execute-api:Invoke",
                    "Effect": "Allow",
                    "Resource": [stage_resource(method_arn)],
                }
            ],
        },
        # Available to the integration as $context.authorizer.<key>.
        "context": {
            "userId": claims["sub"],
            "username": claims.get("username", ""),
            "scope": claims.get("scope", ""),
        },
    }


def handler(event, context):
    # Never log the event: it carries the caller's token.
    token = (event.get("authorizationToken") or "").strip()
    if token[:7].lower() == "bearer ":
        token = token[7:].strip()

    try:
        if not token:
            raise Unauthorized("no token presented")
        policy = allow_policy(validate_token(token), event.get("methodArn", ""))
    except PyJWKClientConnectionError:
        # Fail closed, but this is an infrastructure fault rather than a bad
        # token, so it is logged as an error with a traceback.
        logger.exception("could not reach the JWKS endpoint")
        raise Exception("Unauthorized")
    except (Unauthorized, InvalidTokenError, PyJWKClientError) as error:
        # An expected denial: absent, malformed, expired, or not ours. The
        # reason is safe to log; the token never is.
        logger.warning(
            "authorization denied",
            extra={"reason": f"{type(error).__name__}: {error}"},
        )
        # API Gateway turns this exact message into a 401 response.
        raise Exception("Unauthorized")
    except Exception:
        logger.exception("authorizer failed")
        raise Exception("Unauthorized")

    logger.info(
        "authorization granted",
        extra={
            "principal": policy["principalId"],
            "resource": policy["policyDocument"]["Statement"][0]["Resource"][0],
        },
    )
    return policy
