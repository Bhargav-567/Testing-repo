import os
import sys
import django

# Add project to path
sys.path.insert(0, os.path.dirname(__file__))

# Configure Django settings
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'exam_project.settings')
django.setup()

# Now test Firebase
from exam.firebase_config import get_firestore_client

print("\n" + "="*50)
print("Testing Firebase Connection...")
print("="*50 + "\n")

db = get_firestore_client()

if db:
    print("✅ Firebase connected successfully!")
    print("\n✅ Your app should work fine!")
else:
    print("❌ Firebase connection failed!")
    print("   Check:")
    print("   1. firebase-credentials.json exists in project root")
    print("   2. FIREBASE_CRED path is correct in settings.py")


