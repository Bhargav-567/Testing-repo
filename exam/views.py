from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.hashers import make_password, check_password
from django.contrib import messages
import json
import pandas as pd
import uuid
from datetime import datetime
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# NEW IMPORTS for Hybrid Grader
# from .ai_service import evaluate_answer  # Updated to hybrid
from .grader import DescriptiveAnswerGrader, Concept, QuestionConfig  # NEW

from .firebase_config import db

# Admin credentials (UNCHANGED)
ADMIN_USER = 'Admin'
ADMIN_PASS = 'key123'
ADMIN_REGISTER_CODE = 'Boss@2025'
ADMIN_DOC_ID = "8BxExHElJPAbZmMr4oeF"

# ==================== DATABASE HELPER (UNCHANGED) ====================
def get_admin_doc():
    doc_ref = db.collection('admin_users').document(ADMIN_DOC_ID)
    doc = doc_ref.get()
    return doc_ref, doc

# ==================== AUTH VIEWS (UNCHANGED) ====================
def login(request):
    error = None
    if request.method == 'POST':
        if 'reset_password' in request.POST:
            register_code = request.POST.get('register_code', '')
            contact_info = request.POST.get('contact_info', '').strip()
            new_password = request.POST.get('new_password', '')
            
            if register_code != 'Boss@2025':
                error = "Invalid Admin Register Code."
                return render(request, 'login.html', {'error': error})
               
            doc_ref, doc = get_admin_doc()
            if not doc.exists:
                error = "Admin credentials not found in database."
                return render(request, 'login.html', {'error': error})
            
            password_hash = make_password(new_password)
            update_data = {
                'password_hash': password_hash,
                'email_or_mobile': contact_info,
                'updated_at': datetime.utcnow()
            }
            doc_ref.update(update_data)
            return redirect('login')
        
        login_type = request.POST.get('login_type')
        if login_type == 'admin':
            username = request.POST.get('username')
            password = request.POST.get('password')
            
            doc_ref, doc = get_admin_doc()
            if not doc.exists:
                error = "Admin credentials not set."
                return render(request, 'login.html', {'error': error})
            
            admin_data = doc.to_dict()
            stored_username = admin_data.get('username')
            stored_password_hash = admin_data.get('password_hash')
            
            if (username == stored_username and 
                check_password(password, stored_password_hash)):
                request.session['admin_logged_in'] = True
                return redirect('admin_dashboard')
            else:
                error = 'Invalid credentials'
        
        elif login_type == 'student':
            name = request.POST.get('student_name')
            pern_no = request.POST.get('pern_no')
            if name and pern_no:
                request.session['student_name'] = name
                request.session['student_logged_in'] = True
                request.session['pern_no'] = pern_no
                return redirect('enter_exam_code')
            else:
                error = 'Enter your name and PERN no'

    return render(request, 'login.html', {'error': error})

def logout(request):
    request.session.flush()
    return redirect('login')

# ==================== ADMIN VIEWS (UPDATED) ====================
def admin_dashboard(request):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    return render(request, 'admin_dashboard.html')

# NEW: Enhanced admin_upload with CONCEPT columns
@csrf_exempt
def admin_upload(request):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    if request.method == 'POST':
        if 'file' not in request.FILES:
            return JsonResponse({'error': 'No file selected'}, status=400)
        
        file = request.FILES['file']
        try:
            df = pd.read_excel(file) if file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(file)
            
            # Clear existing questions
            for doc in db.collection('questions').stream():
                doc.reference.delete()
            
            questions_data = []
            for idx, row in df.iterrows():
                q_id = str(row.get('Q_ID', f'Q{idx+1}'))
                q_type = str(row.get('Type', row.get('type', 'mcq'))).lower().strip()
                
                # NEW: Parse CONCEPT columns
                concepts = []
                if 'Concept_Names' in df.columns and 'Concept_Keywords' in df.columns:
                    names_str = str(row.get('Concept_Names', '')).strip()
                    kws_str = str(row.get('Concept_Keywords', '')).strip()
                    if names_str and kws_str:
                        names = [n.strip() for n in names_str.split(',')]
                        kw_lists = [kws.strip().split(',') for kws in kws_str.split(';')]
                        for name, kws in zip(names, kw_lists):
                            if name:
                                concepts.append({
                                    'name': name,
                                    'keywords': [kw.strip() for kw in kws if kw.strip()]
                                })
                
                options = [str(row.get(f'option{i}', '')) for i in range(1, 5)]
                options = [opt for opt in options if opt.strip() and opt != 'nan']
                
                q_data = {
                    'id': str(row.get('Q_ID', f'q{idx+1}')),
                    'question': str(row['Question']),
                    'type': str(row['Type']).lower().strip(),
                    'teacher_answer': str(row.get('Teacher_Answer', '')),
                    'max_score': float(row.get('Max_Score', 10.0 if row['Type'].lower() == 'descriptive' else 1.0)),  # ✅ NEW
                    'concepts': row.get('Concept_Names', '').split(',') if row.get('Concept_Names') else [],
                    'options': row.get('Options', '').split('|') if row.get('Options') else []
                }
                db.collection('questions').document(q_id).set(q_data)
                questions_data.append(q_data)
            
            # Save config summary
            db.collection('questions').document('config').set({
                'questions': questions_data,
                'total_questions': len(questions_data),
                'updated_at': SERVER_TIMESTAMP
            })
            
            return JsonResponse({
                'success': True,
                'message': f'✅ Uploaded {len(questions_data)} questions with concepts!',
                'concepts_count': sum(1 for q in questions_data if q['concepts'])
            })
        except Exception as e:
            return JsonResponse({'error': str(e)}, status=400)
    
    return render(request, 'admin_upload.html')

def admin_codes(request):
    # UNCHANGED
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add':
            code = request.POST.get('code')
            test_name = request.POST.get('test_name', 'New Test')
            duration = int(request.POST.get('duration', 60))
            
            if db.collection('exam_codes').document(code).get().exists:
                codes = list(db.collection('exam_codes').stream())
                return render(request, 'admin_codes.html', {
                    'error': 'Code already exists', 'codes': codes
                })
            
            db.collection('exam_codes').document(code).set({
                'code': code, 'test_name': test_name, 'duration': duration,
                'active': False, 'created_at': SERVER_TIMESTAMP
            })
        elif action == 'activate':
            code = request.POST.get('code')
            db.collection('exam_codes').document(code).update({'active': True})
        elif action == 'deactivate':
            code = request.POST.get('code')
            db.collection('exam_codes').document(code).update({'active': False})
        elif action == 'update_name':
            code = request.POST.get('code')
            test_name = request.POST.get('test_name')
            db.collection('exam_codes').document(code).update({'test_name': test_name})
    
    codes = list(db.collection('exam_codes').stream())
    return render(request, 'admin_codes.html', {'codes': codes})

# NEW: Enhanced admin_stats with PERN/Name SEARCH
def clean_firestore_data(data):
    """Convert Firestore timestamps to JSON-safe strings"""
    if isinstance(data, dict):
        return {k: clean_firestore_data(v) for k, v in data.items()}
    elif hasattr(data, 'isoformat'):  # Timestamp
        return data.isoformat()
    elif data is None:
        return None
    else:
        return str(data)

def admin_stats(request):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    codes = list(db.collection('exam_codes').stream())
    stats_data = {}
    
    for code_doc in codes:
        code_id = code_doc.id
        results = list(db.collection('results').where('exam_code', '==', code_id).stream())
        
        if results:
            clean_results = []
            scores, totals = [], []
            
            for r in results:
                r_dict = r.to_dict()
                # 🔥 FIX: Clean ALL Firestore data
                r_clean = clean_firestore_data(r_dict)
                
                clean_results.append({
                    'doc_id': r.id,
                    'student_name': r_clean['student_name'],
                    'pern_no': r_clean.get('pern_no', 'N/A'),
                    'score': f"{r_clean['score']}/{r_clean['total']}",
                    'percentage': f"{(r_clean['score'] / r_clean['total']) * 100:.1f}%",
                    'timestamp': r_clean.get('timestamp', 'N/A')
                })
                
                scores.append(float(r_clean['score']))
                totals.append(float(r_clean['total']))
            
            stats_data[code_id] = {
                'test_name': code_doc.to_dict().get('test_name', 'Unnamed'),
                'total_tests': len(results),
                'avg_score': sum(scores) / len(scores),
                'max_score': max(scores),
                'min_score': min(scores),
                'total_questions': totals[0],
                'results': clean_results
            }
        else:
            stats_data[code_id] = {
                'test_name': code_doc.to_dict().get('test_name', 'Unnamed'),
                'total_tests': 0,
                'avg_score': 0,
                'max_score': 0,
                'min_score': 0,
                'total_questions': 0,
                'results': []
            }
    
    return render(request, 'admin_stats.html', {
        'codes': codes,
        'stats': stats_data
    })

def download_results(request, code):
    # UNCHANGED
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    results = list(db.collection('results').where('exam_code', '==', code).stream())
    data = [{
        'Student Name': r.to_dict()['student_name'],
        'PERN No': r.to_dict().get('pern_no', 'N/A'),
        'Score': f"{r.to_dict()['score']}/{r.to_dict()['total']}",
        'Percentage': f"{(r.to_dict()['score'] / r.to_dict()['total']) * 100:.2f}%",
        'Timestamp': r.to_dict()['timestamp']
    } for r in results]
    
    df = pd.DataFrame(data)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{code}_results.csv"'
    df.to_csv(path_or_buf=response, index=False)
    return response

# NEW: API for detailed result modal
@csrf_exempt
def student_result_detail(request, doc_id):
    doc = db.collection('results').document(doc_id).get()
    if doc.exists:
        data = doc.to_dict()
        # Enhance details with teacher answers
        for detail in data.get('details', []):
            q_doc = db.collection('questions').document(detail.get('q_id', '')).get()
            if q_doc.exists:
                q_data = q_doc.to_dict()
                detail['details'] = detail.get('details', {})
                detail['details']['teacher_answer'] = q_data.get('teacher_answer', '')
                detail['details']['student_answer'] = detail.get('your_answer', '')
        return JsonResponse(data)
    return JsonResponse({'error': 'Not found'}, status=404)

# ==================== STUDENT VIEWS (UPDATED submit_exam) ====================
def enter_exam_code(request):
    # UNCHANGED
    if not request.session.get('student_logged_in'):
        return redirect('login')
    
    if request.method == 'POST':
        code = request.POST.get('exam_code')
        code_doc = db.collection('exam_codes').document(code).get()
        
        if not code_doc.exists:
            return render(request, 'enter_exam_code.html', {'error': 'Invalid exam code'})
        
        code_data = code_doc.to_dict()
        if not code_data.get('active', False):
            return render(request, 'enter_exam_code.html', {'error': 'Exam not active'})
        
        questions = list(db.collection('questions').stream())
        if not questions:
            return render(request, 'enter_exam_code.html', {'error': 'No questions loaded'})
        
        request.session['exam_code'] = code
        request.session['exam_duration'] = code_data.get('duration', 60)
        request.session['exam_start_time'] = datetime.now().isoformat()
        return redirect('take_exam')
    
    return render(request, 'enter_exam_code.html')

def take_exam(request):
    # UNCHANGED
    if not request.session.get('student_logged_in') or 'exam_code' not in request.session:
        return redirect('enter_exam_code')
    
    questions = list(db.collection('questions').stream())
    questions_data = [{
        'id': q.id, 'question': q.to_dict()['question'],
        'type': q.to_dict()['type'], 'options': q.to_dict().get('options', [])
    } for q in questions]
    
    return render(request, 'take_exam.html', {
        'questions': json.dumps(questions_data),
        'duration': request.session.get('exam_duration', 60),
        'student_name': request.session.get('student_name'),
        'exam_code': request.session.get('exam_code')
    })

@csrf_exempt
def submit_exam(request):
    print("\n🚀 NEW HYBRID EXAM EVALUATION")
    
    if request.method != 'POST':
        return JsonResponse({'error': 'POST only'}, status=400)
    
    try:
        data = json.loads(request.body)
        answers = data.get('answers', {})
        student_name = request.session.get('student_name')
        exam_code = request.session.get('exam_code')
        pern_no = request.session.get('pern_no')
        
        # NEW: Get config + individual questions
        config_doc = db.collection('questions').document('config').get()
        questions = config_doc.to_dict()['questions'] if config_doc.exists else []
        
        if not questions:
            questions_docs = list(db.collection('questions').stream())
            questions = [q.to_dict() for q in questions_docs if q.id != 'config']
        
        score = 0
        result_details = []
        grader = DescriptiveAnswerGrader()  # NEW Transformer grader
        
        for q in questions:
            q_id = q['id']
            user_ans = answers.get(q_id, {})
            q_type = q['type']
            
            if q_type == 'mcq':
                selected = user_ans.get('selectedOption', '')
                is_correct = selected == q.get('correct_option')
                q_score = q['max_score'] if is_correct else 0.0
                score += q_score
                details = {'type': 'MCQ', 'correct': is_correct, 'max_score': q['max_score']}
            
            else:  # descriptive
                student_ans = user_ans.get('answer', '')
                if not student_ans.strip():
                    q_score = 0.0
                    details = {'type': 'Descriptive', 'score': 0.0, 'max_score': q['max_score']}
                else:
                    # NEW: Hybrid grading with concepts
                    concepts = [Concept(**c) for c in q.get('concepts', [])]
                    cfg = QuestionConfig(q_id, q['teacher_answer'], concepts, q['max_score'])
                    result = grader.grade(cfg, student_ans)
                    q_score = result['final_score']
                    score += q_score
                    details = {
                        'type': 'Descriptive',
                        'concept_score': result['concept_score'],
                        'relation_score': result['relation_score'],
                        'semantic_similarity': result['semantic_similarity'],
                        'penalty': result['penalty'],
                        'max_score': q['max_score']
                    }
            
            result_details.append({
                'q_id': q_id,
                'question': q['question'][:100] + '...' if len(q['question']) > 100 else q['question'],
                'your_answer': user_ans.get('answer', user_ans.get('selectedOption', '')),
                'score': round(q_score, 1),
                'details': details
            })
        
        # Save enhanced results
        result_id = str(uuid.uuid4())
        total_max = sum(q.get('max_score', 1.0) for q in questions)
        result_data = {
            'exam_code': exam_code,
            'student_name': student_name,
            'pern_no': pern_no,
            'total_score': float(score),
            'total_questions': len(questions),
            'total_max_score': total_max,
            'percentage': round((score / total_max) * 100, 1),
            'details': result_details,
            'timestamp': SERVER_TIMESTAMP
        }
        db.collection('results').document(result_id).set(result_data)
        
        return JsonResponse({
            'success': True,
            'total_score': round(score, 1),
            'percentage': round((score / total_max) * 100, 1),
            'details': result_details
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

def student_results(request):
    if not request.session.get('student_logged_in'):
        return redirect('login')
    return render(request, 'results.html')
