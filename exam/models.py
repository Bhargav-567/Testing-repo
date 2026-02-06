from django.db import models

# Firestore-native
from django.contrib.auth.models import User
import uuid

class ExamResult:
    def __init__(self, student_id, total_score, results, exam_id=None):
        self.id = exam_id or str(uuid.uuid4())
        self.student_id = student_id
        self.total_score = total_score
        self.results = results  # List of {'q_id': '..', 'score': 8.5, 'details': {...}}
        self.timestamp = firestore.SERVER_TIMESTAMP
        self.save()
    
    def save(self):
        data = {
            'student_id': self.student_id,
            'total_score': self.total_score,
            'results': self.results,
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        db.collection('exam_results').document(self.id).set(data)
    
    @classmethod
    def get_by_student(cls, student_id):
        results = db.collection('exam_results').where('student_id', '==', student_id).stream()
        return [doc.to_dict() for doc in results]
