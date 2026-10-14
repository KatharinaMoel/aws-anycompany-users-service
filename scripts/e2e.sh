#!/bin/bash
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
# SPDX-License-Identifier: MIT-0
#
# End-to-end checks against the deployed AnyCompany Users Service.
#
#   ./scripts/e2e.sh
#
# Self-contained: it reads .env.test from the repository root and fetches its own
# tokens from Cognito, so nothing has to be prepared by hand first. Needs the AWS
# CLI with credentials for the account the service is deployed in, because
# initiate-auth is called through it.
#
# Every assertion names the behaviour it checks. A failure prints what was
# expected and what arrived; the exit status is non-zero if anything failed.

set -u

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ ! -f "$ROOT/.env.test" ]; then
  echo "No $ROOT/.env.test - copy .env.test.example and fill it in." >&2
  exit 2
fi

set -a
# shellcheck disable=SC1091  # created from .env.test.example, not in git
. "$ROOT/.env.test"
set +a

for required in API_INVOKE_URL APP_CLIENT_ID TEST_USER_EMAIL TEST_USER_PASSWORD; do
  if [ -z "${!required:-}" ]; then
    echo "$required is missing from .env.test" >&2
    exit 2
  fi
done

URL="$API_INVOKE_URL"
BODYFILE="$(mktemp)"
HDRFILE="$(mktemp)"
trap 'rm -f "$BODYFILE" "$HDRFILE"' EXIT

# A JSON map rather than the KEY=value shorthand, so a comma in the password
# cannot split the argument.
AUTH_PARAMS=$(python3.13 -I -c '
import json, os
print(json.dumps({"USERNAME": os.environ["TEST_USER_EMAIL"],
                  "PASSWORD": os.environ["TEST_USER_PASSWORD"]}))')

AUTH=$(aws cognito-idp initiate-auth \
  --client-id "$APP_CLIENT_ID" \
  --auth-flow USER_PASSWORD_AUTH \
  --auth-parameters "$AUTH_PARAMS" \
  --output json) || { echo "initiate-auth failed" >&2; exit 2; }

# The access token authorizes the calls; the ID token is fetched only so the
# suite can prove that it is rejected.
read -r TOK IDTOK <<<"$(python3.13 -I -c '
import json, sys
r = json.load(sys.stdin)["AuthenticationResult"]
print(r["AccessToken"], r["IdToken"])' <<<"$AUTH")"

PASS=0
FAIL=0

# call <method> <path> [body] [auth-header-value]  -> status in $STATUS, body in $BODY
# The default for the fourth argument is ${4-...}, not ${4:-...}: an explicitly
# empty string must mean "send no Authorization header", which is how the
# unauthenticated cases are expressed.
call() {
  local method=$1 path=$2 body=${3-} auth=${4-$TOK}
  local args=(-s -o "$BODYFILE" -w '%{http_code}' -X "$method")
  [ -n "$auth" ] && args+=(-H "Authorization: $auth")
  [ -n "$body" ] && args+=(-H 'Content-Type: application/json' -d "$body")
  STATUS=$(curl "${args[@]}" "$URL$path")
  BODY=$(cat "$BODYFILE")
}

# preflight <path> <requested-method>  -> $STATUS, $ALLOW_METHODS, $ALLOW_HEADERS
preflight() {
  STATUS=$(curl -s -o /dev/null -D "$HDRFILE" -w '%{http_code}' -X OPTIONS "$URL$1" \
    -H 'Origin: http://localhost:8000' \
    -H "Access-Control-Request-Method: $2" \
    -H 'Access-Control-Request-Headers: authorization,content-type')
  ALLOW_METHODS=$(grep -i '^access-control-allow-methods:' "$HDRFILE" | tr -d '\r' | cut -d' ' -f2-)
  ALLOW_HEADERS=$(grep -i '^access-control-allow-headers:' "$HDRFILE" | tr -d '\r' | cut -d' ' -f2-)
}

check() { # check <label> <expected> <actual>
  if [ "$2" = "$3" ]; then
    PASS=$((PASS + 1))
    printf '  PASS  %-52s %s\n' "$1" "$3"
  else
    FAIL=$((FAIL + 1))
    printf '  FAIL  %-52s expected %s, got %s\n' "$1" "$2" "$3"
  fi
}

jget() { python3.13 -I -c "import json,sys;print(json.load(sys.stdin).get('$1',''))" <<<"$BODY"; }

echo "== create a user"
call POST /users '{"name":"Grace Hopper","email":"grace@example.com"}'
check "POST /users status" 201 "$STATUS"
USERID=$(jget userid)
CREATED=$(jget createdAt)
UPDATED=$(jget updatedAt)
check "userid is a uuid4" true "$(python3.13 -I -c "
import uuid, sys
v = sys.argv[1]
print(str(str(uuid.UUID(v, version=4)) == v).lower())" "$USERID" 2>/dev/null || echo false)"
check "createdAt == updatedAt on create" "$CREATED" "$UPDATED"
echo "        userid=$USERID"

echo "== read it back"
call GET /users
check "GET /users status" 200 "$STATUS"
check "GET /users lists the new record" true "$(python3.13 -I -c "
import json, sys
d = json.load(sys.stdin)
print(str(any(u['userid'] == sys.argv[1] for u in d['users'])).lower())" "$USERID" <<<"$BODY")"
check "GET /users returns a users envelope" true "$(python3.13 -I -c "
import json, sys
print(str(isinstance(json.load(sys.stdin).get('users'), list)).lower())" <<<"$BODY")"
call GET "/users/$USERID"
check "GET /users/{userid} status" 200 "$STATUS"
check "createdAt matches the create response" "$CREATED" "$(jget createdAt)"
check "updatedAt matches the create response" "$UPDATED" "$(jget updatedAt)"

echo "== update, delete, confirm gone"
sleep 1 # so a refreshed updatedAt is visibly later
call PUT "/users/$USERID" '{"name":"Grace B. Hopper","email":"grace.hopper@example.com"}'
check "PUT status" 200 "$STATUS"
check "PUT applied the new name" "Grace B. Hopper" "$(jget name)"
check "PUT left createdAt unchanged" "$CREATED" "$(jget createdAt)"
NEW_UPDATED=$(jget updatedAt)
check "PUT refreshed updatedAt" true "$(python3.13 -I -c "
import sys
print(str(sys.argv[1] > sys.argv[2]).lower())" "$NEW_UPDATED" "$UPDATED")"
call DELETE "/users/$USERID"
check "DELETE status" 200 "$STATUS"
check "DELETE body is an empty JSON object" "{}" "$BODY"
call GET "/users/$USERID"
check "GET after DELETE" 404 "$STATUS"
call DELETE "/users/$USERID"
check "DELETE of an unknown id" 404 "$STATUS"

echo "== error paths"
call POST /users '{"name":"","email":"nobody@example.com"}'
check "POST with an empty name" 400 "$STATUS"
call POST /users '{"name":"   ","email":"nobody@example.com"}'
check "POST with a whitespace-only name" 400 "$STATUS"
call POST /users '{"email":"nobody@example.com"}'
check "POST with no name field" 400 "$STATUS"
call POST /users 'not json at all'
check "POST with a malformed body" 400 "$STATUS"
call POST /users '["not","an","object"]'
check "POST with a JSON array body" 400 "$STATUS"
call PUT "/users/00000000-0000-0000-0000-000000000000" '{"name":"Nobody","email":"n@example.com"}'
check "PUT on an unknown id" 404 "$STATUS"
call GET "/users/00000000-0000-0000-0000-000000000000"
check "GET on an unknown id" 404 "$STATUS"

echo "== unexpected fields are not persisted"
call POST /users '{"name":"Mass Assignment","email":"ma@example.com","userid":"spoofed","role":"admin","createdAt":"1999-01-01T00:00:00+00:00"}'
check "POST with extra fields status" 201 "$STATUS"
MA_ID=$(jget userid)
check "spoofed userid ignored" true "$(python3.13 -I -c "
import sys
print(str(sys.argv[1] != 'spoofed').lower())" "$MA_ID")"
check "spoofed createdAt ignored" true "$(python3.13 -I -c "
import sys
print(str(not sys.argv[1].startswith('1999')).lower())" "$(jget createdAt)")"
call GET "/users/$MA_ID"
check "stored record holds exactly the five fields" "createdAt,email,name,updatedAt,userid" \
  "$(python3.13 -I -c "import json,sys;print(','.join(sorted(json.load(sys.stdin))))" <<<"$BODY")"
call DELETE "/users/$MA_ID" # tidy up

echo "== authorization"
call GET /users '' ''
check "no Authorization header" 401 "$STATUS"
call GET /users '' "$IDTOK"
check "ID token instead of access token" 401 "$STATUS"
call GET /users '' "not.a.jwt"
check "malformed token" 401 "$STATUS"

echo "== search by email"
SEARCH_EMAIL="search-probe-$RANDOM@example.com"
call POST /users "{\"name\":\"Search Probe\",\"email\":\"$SEARCH_EMAIL\"}"
check "POST the probe record" 201 "$STATUS"
PROBE_ID=$(jget userid)
call GET "/users/search?email=$SEARCH_EMAIL"
check "search finds the probe" true "$(python3.13 -I -c "
import json, sys
users = json.load(sys.stdin)['users']
print(str(len(users) == 1 and users[0]['userid'] == sys.argv[1]).lower())" "$PROBE_ID" <<<"$BODY")"
call GET "/users/search?email=nobody-has-this@example.com"
check "search with no match is 200, not 404" 200 "$STATUS"
check "search with no match returns an empty array" '{"users": []}' "$BODY"
call GET "/users/search?email=$(python3.13 -I -c "import sys;print(sys.argv[1].upper())" "$SEARCH_EMAIL")"
check "search is case-sensitive" '{"users": []}' "$BODY"
call GET "/users/search"
check "search with no query string" 400 "$STATUS"
call GET "/users/search?email="
check "search with an empty email" 400 "$STATUS"
call DELETE "/users/$PROBE_ID" # tidy up

echo "== CORS preflight"
preflight /users GET
check "OPTIONS /users status" 200 "$STATUS"
check "OPTIONS /users advertises its methods" "GET,POST,OPTIONS" "$ALLOW_METHODS"
check "OPTIONS /users allows the Authorization header" "Content-Type,Authorization" "$ALLOW_HEADERS"
preflight /users/search GET
check "OPTIONS /users/search advertises its methods" "GET,OPTIONS" "$ALLOW_METHODS"
preflight /users/00000000-0000-0000-0000-000000000000 PUT
check "OPTIONS /users/{userid} advertises its methods" "GET,PUT,DELETE,OPTIONS" "$ALLOW_METHODS"

echo
echo "  $PASS passed, $FAIL failed"
exit $((FAIL > 0))
