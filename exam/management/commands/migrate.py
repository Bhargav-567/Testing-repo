# exam/management/commands/migrate_results.py
from django.core.management.base import BaseCommand
from exam.views import db  # Adjust import path

class Command(BaseCommand):
    help = 'Migrate flat results to hierarchical structure'
    
    def handle(self, *args, **options):
        print("🔄 Migrating results to new structure...")
        
        # Query ALL old flat results
        old_results = db.collection('results').stream()
        migrated = 0
        skipped = 0
        
        for result in old_results:
            r_data = result.to_dict()
            pern_no = r_data.get('pern_no')
            exam_code = r_data.get('exam_code')
            
            if pern_no and exam_code:
                # Create new path
                submission_id = result.id
                new_path = f"results/{exam_code}/{pern_no}/{submission_id}"
                
                # Copy data
                db.document(new_path).set(r_data)
                print(f"✅ Migrated {result.id} → {new_path}")
                migrated += 1
            else:
                print(f"❌ Skipped {result.id} (missing pern_no/exam_code)")
                skipped += 1
        
        print(f"🎉 Migration complete: {migrated} migrated, {skipped} skipped")
