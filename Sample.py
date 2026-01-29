# login_api_test.py
import requests

# -----------------------------
# CONFIGURATION
# -----------------------------
url = "https://example.test/api/login"  # Dummy API
headers = {
    "Content-Type": "application/json"
}

valid_payload = {
    "username": "testuser",
    "password": "password123"
}

invalid_payload = {
    "username": "wronguser",
    "password": "wrongpass"
}

# -----------------------------
# TEST CASE 1: Valid Login
# -----------------------------
response = requests.post(url, json=valid_payload, headers=headers)

if response.status_code == 200:
    print("[PASS] Valid login successful")
else:
    print("[FAIL] Valid login failed")

# -----------------------------
# TEST CASE 2: Invalid Login
# -----------------------------
response = requests.post(url, json=invalid_payload, headers=headers)

if response.status_code == 401:
    print("[PASS] Invalid login correctly rejected")
else:
    print("[FAIL] Invalid login not handled properly")

# -----------------------------
# TEST CASE 3: Blank Username
# -----------------------------
blank_user = {
    "username": "",
    "password": "password123"
}

response = requests.post(url, json=blank_user, headers=headers)

if response.status_code == 400:
    print("[PASS] Blank username validation working")
else:
    print("[FAIL] Blank username validation missing")

# -----------------------------
# TEST CASE 4: Blank Password
# -----------------------------
blank_pass = {
    "username": "testuser",
    "password": ""
}

response = requests.post(url, json=blank_pass, headers=headers)

if response.status_code == 400:
    print("[PASS] Blank password validation working")
else:
    print("[FAIL] Blank password validation missing")
