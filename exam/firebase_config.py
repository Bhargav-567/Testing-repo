import os
import firebase_admin
from firebase_admin import credentials, firestore
from django.conf import settings


# def safe_float(value, default=0.0):
#     """Safely convert Firestore value to float"""
#     if value is None:
#         return default
#     try:
#         return float(value)
#     except (ValueError, TypeError):
#         return default

# # Usage in views:
# score = safe_float(data.get('total_score'))
# total = safe_float(data.get('max_possible', 1))
# percentage = (score / total) * 100 if total > 0 else 0


print("📦 Loading firebase_config module...")

CREDENTIAL_PATH = os.path.join(
    settings.BASE_DIR,
    "firebase-credentials.json"
)

print("🔍 Looking for Firebase credentials at:", CREDENTIAL_PATH)

if not os.path.exists(CREDENTIAL_PATH):
    raise FileNotFoundError(
        f"Firebase credentials file NOT FOUND at {CREDENTIAL_PATH}"
    )

cred = credentials.Certificate(CREDENTIAL_PATH)

if not firebase_admin._apps:
    firebase_admin.initialize_app(cred)

db = firestore.client()
print("✅ Firebase initialized successfully")

