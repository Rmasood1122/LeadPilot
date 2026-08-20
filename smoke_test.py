"""End-to-end backend smoke test — no external API keys required except
ANTHROPIC_API_KEY (strategy creation calls Claude).

Run this AFTER:
  - uvicorn app.main:app --reload   (in one terminal)
  - celery worker + beat running    (in two more terminals)

Usage:
    pip install requests
    python smoke_test.py
"""

import sys
import time

import requests

BASE = "http://localhost:8000"


def check(label, condition, extra=""):
    status = "PASS" if condition else "FAIL"
    print(f"[{status}] {label} {extra}")
    if not condition:
        sys.exit(1)


# 1. Health check
r = requests.get(f"{BASE}/health")
check("GET /health", r.status_code == 200, r.text)

# 2. Signup
email = f"smoketest_{int(time.time())}@example.com"
r = requests.post(f"{BASE}/auth/signup", json={
    "email": email,
    "password": "TestPassword123!",
})
check("POST /auth/signup", r.status_code in (200, 201), f"status={r.status_code} body={r.text}")
tokens = r.json()
access_token = tokens.get("access_token")
check("access_token received", bool(access_token))

headers = {"Authorization": f"Bearer {access_token}"}

# 3. Login (separately, to confirm login path works too)
r = requests.post(f"{BASE}/auth/login", json={
    "email": email,
    "password": "TestPassword123!",
})
check("POST /auth/login", r.status_code == 200, f"status={r.status_code}")

# 4. Auth/me
r = requests.get(f"{BASE}/auth/me", headers=headers)
check("GET /auth/me", r.status_code == 200, f"status={r.status_code} body={r.text}")

# 5. Create a product
r = requests.post(f"{BASE}/products", headers=headers, json={
    "user_email": email,
    "name": "Smoke Test Product",
    "description": "A test SaaS product for smoke testing",
    "type": "skill",
})
check("POST /products", r.status_code in (200, 201), f"status={r.status_code} body={r.text}")
product = r.json()
product_id = product.get("id")
check("product_id received", bool(product_id))

# 6. List products (confirms the product we made is retrievable)
r = requests.get(f"{BASE}/products/{product_id}", headers=headers) if False else None
# (no GET /products/{id} route in this API — listing strategies instead is
#  the next real step, but that requires ANTHROPIC_API_KEY, so we stop here)

print("\nAll auth + product smoke tests passed.")
print(f"product_id={product_id}")
print("Strategy creation (POST /products/{id}/strategies) needs ANTHROPIC_API_KEY")
print("— add it to .env and re-run once you have a real key.")