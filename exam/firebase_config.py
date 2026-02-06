<<<<<<< HEAD
import firebase_admin
from firebase_admin import credentials, firestore
from django.conf import settings
import os

# Global variable to store db connection
_db = None
_initialized = False

def get_firestore_client():
    """
    Lazily initialize Firebase and return Firestore client
    This function is called when database is needed
    """
    global _db, _initialized
    
    # If already initialized, return existing connection
    if _initialized and _db is not None:
        return _db
    
    try:
        # Get credentials path from settings
        cred_path = settings.FIREBASE_CRED
        
        print(f"🔍 Looking for Firebase credentials at: {cred_path}")
        
        # Check if file exists
        if not os.path.exists(cred_path):
            print(f"❌ ERROR: Firebase credentials file not found at {cred_path}")
            print(f"   Please ensure 'firebase-credentials.json' is in your project root folder")
            return None
        
        print(f"✅ Found credentials file: {cred_path}")
        
        # Initialize Firebase if not already done
        if not firebase_admin._apps:
            print("🔌 Initializing Firebase...")
            cred = credentials.Certificate(str(cred_path))
            firebase_admin.initialize_app(cred)
            print("✅ Firebase initialized successfully!")
        else:
            print("ℹ️  Firebase already initialized")
        
        # Get Firestore client
        _db = firestore.client()
        _initialized = True
        
        print("✅ Connected to Firestore!")
        return _db
    
    except FileNotFoundError as e:
        print(f"❌ File not found: {e}")
        return None
    
    except ValueError as e:
        print(f"❌ Invalid credentials: {e}")
        return None
    
    except Exception as e:
        print(f"❌ Error connecting to Firebase: {e}")
        import traceback
        traceback.print_exc()
        return None

# Initialize on first import (attempt, won't fail if credentials missing)
try:
    print("📦 Loading firebase_config module...")
    get_firestore_client()
except Exception as e:
    print(f"⚠️  Warning during firebase_config load: {e}")

# Export for use in views
db = get_firestore_client()
=======
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

>>>>>>> dev
