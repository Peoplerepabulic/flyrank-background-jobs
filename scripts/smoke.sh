#!/usr/bin/env bash
# Smoke test: POST -> 202, poll GET until complete, idempotency replay demo.
set -euo pipefail

BASE="${BASE:-http://127.0.0.1:8000}"
KEY="smoke-$(date +%s)"

echo "== 1) POST /reports (expect HTTP 202, fast) =="
START_MS=$(date +%s%3N)
RAW=$(curl -s -w '\n%{http_code}' -X POST "$BASE/reports" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $KEY" \
  -d '{"title":"Smoke Test Report","sections":["intro","body","conclusion"]}')
END_MS=$(date +%s%3N)
BODY=$(echo "$RAW" | sed '$d')
CODE=$(echo "$RAW" | tail -n1)
echo "status: $CODE  latency: $((END_MS - START_MS)) ms"
echo "body:   $BODY"
[ "$CODE" = "202" ] || { echo "FAIL: expected 202"; exit 1; }
JOB_ID=$(echo "$BODY" | python3 -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
echo "job_id: $JOB_ID"

echo
echo "== 2) GET /reports/$JOB_ID polling (expect pending -> running -> complete) =="
SEEN=""
for i in $(seq 1 40); do
  POLL=$(curl -s "$BASE/reports/$JOB_ID")
  STATUS=$(echo "$POLL" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
  PROG=$(echo "$POLL" | python3 -c "import sys,json;print(json.load(sys.stdin)['progress'])")
  echo "  t+$((i * 2))s  status=$STATUS progress=$PROG"
  case "$STATUS" in
    pending|running) SEEN="$SEEN $STATUS";;
    complete) break;;
    failed) echo "FAIL: job failed: $POLL"; exit 1;;
    *) echo "FAIL: unexpected status $STATUS"; exit 1;;
  esac
  sleep 2
done
[ "$STATUS" = "complete" ] || { echo "FAIL: job never completed"; exit 1; }
echo "$SEEN" | grep -q pending  || echo "NOTE: did not observe 'pending' (job was picked up fast)"
echo "$SEEN" | grep -q running  || { echo "FAIL: never observed 'running'"; exit 1; }
RESULT=$(echo "$POLL" | python3 -c "import sys,json;r=json.load(sys.stdin)['result'];print(r['title'], r['sections_rendered'], r['summary'], r['generated_at'])")
echo "result payload: $RESULT"

echo
echo "== 3) Idempotency replay: same Idempotency-Key (expect HTTP 200, SAME job_id) =="
RAW2=$(curl -s -w '\n%{http_code}' -X POST "$BASE/reports" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $KEY" \
  -d '{"title":"A totally different title","sections":[]}')
BODY2=$(echo "$RAW2" | sed '$d'); CODE2=$(echo "$RAW2" | tail -n1)
echo "status: $CODE2"
echo "body:   $BODY2"
[ "$CODE2" = "200" ] || { echo "FAIL: expected 200 on replay"; exit 1; }
JOB2=$(echo "$BODY2" | python3 -c "import sys,json;print(json.load(sys.stdin)['job_id'])")
[ "$JOB2" = "$JOB_ID" ] || { echo "FAIL: replay returned a different job_id"; exit 1; }
echo "replay returned the SAME job_id -> idempotent OK"

echo
echo "== 4) Unknown job_id (expect 404) =="
C404=$(curl -s -o /dev/null -w '%{http_code}' "$BASE/reports/does-not-exist")
echo "status: $C404"; [ "$C404" = "404" ] || { echo "FAIL: expected 404"; exit 1; }

echo
echo "SMOKE TEST PASSED"
