#!/usr/bin/env bash
set -euo pipefail

G=${GERRIT_URL:-http://gerrit:8080}
PASS=${SEED_PASSWORD:-secret}
JAR=$(mktemp)

creds() { for u in admin alice bob; do echo "$u / $PASS"; done; }

until curl -sf "$G/config/server/version" >/dev/null; do sleep 2; done
curl -sf "$G/projects/demo" >/dev/null && {
	creds
	exit 0
}

curl -sf -c "$JAR" -b "$JAR" -o /dev/null "$G/login/%23%2F?user_name=admin"
curl -sf -c "$JAR" -b "$JAR" -o /dev/null "$G/"
XSRF=$(awk '$6=="XSRF_TOKEN"{print $7}' "$JAR")

curl -sf -o /dev/null -b "$JAR" -H "X-Gerrit-Auth: $XSRF" -H 'Content-Type: application/json' \
	-X PUT "$G/a/accounts/self/password.http" -d "{\"http_password\":\"$PASS\"}"

api() { curl -sf -o /dev/null -u "admin:$PASS" -H 'Content-Type: application/json' -X "$1" "$G/a$2" -d "$3"; }

for u in alice bob; do
	api PUT "/accounts/$u" "{\"name\":\"$u\",\"email\":\"$u@example.com\",\"http_password\":\"$PASS\"}"
done
api PUT /projects/demo '{"create_empty_commit":true}'
for i in 1 2 3; do
	api POST /changes/ "{\"project\":\"demo\",\"branch\":\"master\",\"subject\":\"Seed change $i\"}"
done

creds
