#!/usr/bin/env bash
# check.sh — local pre-commit review: security checks then unit tests.
# Run from the project root: bash check.sh
# Exit code is 0 only if every check and every test passes.

set -euo pipefail

PASS=0
FAIL=0

ok()   { echo "  OK  $1"; PASS=$((PASS + 1)); }
fail() { echo " FAIL $1"; FAIL=$((FAIL + 1)); }

echo ""
echo "=== Security checks ==="
echo ""

# 1. No | safe in templates (unsanitised output).
if grep -rn "| safe" app/templates/ 2>/dev/null | grep -qv "{#"; then
  fail "| safe found in templates — review for XSS risk:"
  grep -rn "| safe" app/templates/ | grep -v "{#"
else
  ok "No | safe in templates"
fi

# 2. Every /admin route definition must have @admin_required somewhere in
# the decorator block above it (within the 5 lines before 'def ').
# This tolerates @limiter.limit() or other decorators between them.
UNPROTECTED=$(python3 - <<'PYEOF'
import re

with open('app/routes.py') as f:
    lines = f.readlines()

results = []
for i, line in enumerate(lines):
    if re.match(r"^def ", line):
        # Scan back up to 6 decorator lines looking for the route and the guard.
        block = lines[max(0, i-6):i]
        block_text = "".join(block)
        if re.search(r'@main\.route\([^)]*\/admin', block_text):
            if '@admin_required' not in block_text:
                # Find the route line number for the report.
                for j, b in enumerate(block):
                    if re.search(r'@main\.route\([^)]*\/admin', b):
                        results.append(f"  line {max(0,i-6)+j+1}: {b.rstrip()}")
print("\n".join(results))
PYEOF
)
if [ -n "$UNPROTECTED" ]; then
  fail "@admin_required missing on route(s):"
  echo "$UNPROTECTED"
else
  ok "All /admin routes decorated with @admin_required"
fi

# 3. No POST form in any template is missing a CSRF token field.
MISSING_CSRF=""
for f in app/templates/*.html; do
  if grep -qi 'method.*post' "$f"; then
    if ! grep -q 'csrf_token\|hidden_tag' "$f"; then
      MISSING_CSRF="$MISSING_CSRF $f"
    fi
  fi
done
if [ -n "$MISSING_CSRF" ]; then
  fail "POST form missing csrf_token in:$MISSING_CSRF"
else
  ok "All POST forms include csrf_token"
fi

# 4. No plaintext password comparisons (should always use check_password).
if grep -n "\.password ==" app/routes.py app/models.py 2>/dev/null | grep -qv "#"; then
  fail "Plaintext password comparison found"
  grep -n "\.password ==" app/routes.py app/models.py | grep -v "#"
else
  ok "No plaintext password comparisons"
fi

# 5. No hardcoded SECRET_KEY or credentials.
if grep -En "SECRET_KEY\s*=\s*['\"][^'\"]{8}" app/__init__.py app/routes.py 2>/dev/null | grep -qv "os.environ\|config\["; then
  fail "Hardcoded SECRET_KEY found"
else
  ok "SECRET_KEY loaded from environment only"
fi

# 6. All requirements.txt entries are pinned to exact versions.
UNPINNED=$(grep -v "^#\|^$\|==" requirements.txt 2>/dev/null || true)
if [ -n "$UNPINNED" ]; then
  fail "Unpinned dependencies in requirements.txt:"
  echo "$UNPINNED"
else
  ok "All dependencies pinned with =="
fi

# 7. No next= redirect without safe_next_url guard.
# Count redirect(request.args.get('next')) calls not routed through safe_next_url.
RAW_NEXT=$(grep -n "redirect(request.args.get('next')" app/routes.py 2>/dev/null || true)
if [ -n "$RAW_NEXT" ]; then
  fail "Raw next= redirect (bypasses safe_next_url):"
  echo "$RAW_NEXT"
else
  ok "No raw next= redirects"
fi

echo ""
echo "=== Unit tests ==="
echo ""

# Activate venv if present and not already active.
if [ -z "${VIRTUAL_ENV:-}" ] && [ -f venv/bin/activate ]; then
  # shellcheck disable=SC1091
  source venv/bin/activate
fi

python -m pytest tests/ -v
PYTEST_EXIT=$?

echo ""
echo "=== Summary ==="
echo "  Security checks passed : $PASS"
echo "  Security checks failed : $FAIL"

if [ "$FAIL" -gt 0 ] || [ "$PYTEST_EXIT" -ne 0 ]; then
  echo ""
  echo "REVIEW FAILED — do not commit until all checks pass."
  exit 1
else
  echo ""
  echo "All checks passed."
  exit 0
fi
