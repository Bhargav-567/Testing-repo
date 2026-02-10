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
from io import BytesIO

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
    
    # Handle the File Upload (POST)
    if request.method == 'POST':
        if 'file' not in request.FILES:
            return render(request, 'admin_upload.html', {'error': 'No file selected'})
        
        exam_code = request.POST.get('exam_code', '').strip()
        duration = request.POST.get('duration', '60')
        file = request.FILES['file']

        if not exam_code:
            return render(request, 'admin_upload.html', {'error': 'Please provide an Exam Code'})
        
        try:
            df = pd.read_excel(file) if file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(file)
            
            # 1. Update/Create Exam Record
            db.collection('exam_codes').document(exam_code).set({
                'code': exam_code,
                'test_name': f"Test {exam_code}",
                'duration': int(duration),
                'active': True,
                'created_at': SERVER_TIMESTAMP
            })

            questions_data = []
            # Inside the df.iterrows() loop in admin_upload
            names_str = str(row.get('Concept_Names', '')).strip()
            kws_str = str(row.get('Concept_Keywords', '')).strip()

            if names_str and names_str != 'nan':
                names = [n.strip() for n in names_str.split(',') if n.strip()]
                # SPLIT keywords by semicolon first, then comma
                kw_groups = [g.strip() for g in kws_str.split(';') if g.strip()]
                
                for i, name in enumerate(names):
                    # FIX: Ensure current_keywords is a list of STRINGS
                    if i < len(kw_groups):
                        current_keywords = [k.strip().lower() for k in kw_groups[i].split(',') if k.strip()]
                    else:
                        current_keywords = [name.lower()]
                        
                    concepts.append({
                        'name': name,
                        'keywords': current_keywords # This must be a flat list of strings
                    })

                # --- Save Question ---
                q_id = f"{exam_code}_{idx}"
                q_data = {
                    'id': q_id,
                    'exam_code': exam_code,
                    'question': str(row.get('Question', '')),
                    'type': str(row.get('Type', 'mcq')).lower().strip(),
                    'teacher_answer': str(row.get('Teacher_Answer', '')),
                    'max_score': float(row.get('Max_Score', 1.0)),
                    'concepts': concepts,
                    'options': str(row.get('Options', '')).split('|') if str(row.get('Type')) == 'mcq' else []
                }
                db.collection('questions').document(q_id).set(q_data)
                questions_data.append(q_data)

            # SUCCESS RETURN
            return render(request, 'admin_upload.html', {
                'success': f'✅ Successfully uploaded {len(questions_data)} questions for exam {exam_code}!'
            })

        except Exception as e:
            # ERROR RETURN (within POST)
            return render(request, 'admin_upload.html', {'error': f"Processing Error: {str(e)}"})

    # DEFAULT RETURN (For GET requests when the page first loads)
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
    
    # 1. GET THE SEARCH QUERY
    selected_code = request.GET.get('code','')
    search_query = request.GET.get('search', '').strip()
    
    codes = db.collection('exam_codes').stream()
    print(f"seach quesry {search_query} , selected code {selected_code}")
    stats = {}
    total_results_count = 0
    search_results_count = 0

    if selected_code:
        print(f"The user is looking for {selected_code}")
        # 2. Target the specific subcollection for this exam
        # Path: results/[exam_code]/submissions/
        results_ref = db.collection('results').document(selected_code).collection('submissions')
        docs = results_ref.stream()
        
        exam_results = []
        scores = []

        count_query = results_ref.count()
        count_result = count_query.get()
        print(f"Total documents: {count_result[0][0].value}")
        
        for doc in docs:
            data = doc.to_dict()
            data['doc_id'] = doc.id
            print(f"Doc Id: {doc.id}")
            # Normalize data for searching
            student_name = str(data.get('student_name', '')).lower()
            pern_no = str(data.get('pern_no', '')).lower()
            query = search_query.lower()

            print(f"Name {student_name}, Pern {pern_no}, query {query}.")

            # 3. Apply Filtering Logic
            # If no search query, add everyone. If query exists, match Name or PERN
            raw_timestamp = data.get('timestamp')
            formatted_date = ""

            if raw_timestamp:
                try:
                    formatted_date = raw_timestamp.strftime('%Y-%m-%dT%H:%M:%S')
                except AttributeError:
                    formatted_date = str(raw_timestamp)

            if not search_query or (query in student_name or query in pern_no):
                exam_results.append({
                    'student_name': data.get('student_name'),
                    'pern_no': data.get('pern_no'),
                    'max_score': data.get('total_max_score'),
                    'score': data.get('total_score'),
                    'percentage': f"{data.get('percentage', 0)}%",
                    'timestamp': formatted_date,
                    'doc_id': doc.id
                })

                scores.append(float(data.get('percentage', 0)))
                if search_query: search_results_count += 1

            total_results_count += 1
            
            
                
        if exam_results:
            stats[selected_code] = {
                'total_tests': len(exam_results),
                'avg_score': sum(scores) / len(scores) if scores else 0,
                'max_score': max(scores) if scores else 0,
                'min_score': min(scores) if scores else 0,
                'results': exam_results
            }

    return render(request, 'admin_stats.html', {
        'codes': codes,
        'stats': stats,
        'search_query': search_query,
        'search_results': search_results_count,
        'total_results': total_results_count,
    })

def download_results(request, exam_code):
    # Reference the specific subcollection for this exam
    docs = db.collection('results').document('submissions').collection(exam_code).stream()
    
    data = []
    for doc in docs:
        data.append(doc.to_dict())
        
    if not data:
        return HttpResponse("No results found for this exam code.", status=404)

    # Create DataFrame
    df = pd.DataFrame(data)
    
    # Clean up column names for the Excel file
    column_mapping = {
        'pern_no': 'Perno',
        'name': 'Student Name',
        'score': 'Total Score',
        'timestamp': 'Submission Time'
    }
    df = df.rename(columns=column_mapping)

    # Use BytesIO to create the Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Results')
    
    response = HttpResponse(
        output.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    response['Content-Disposition'] = f'attachment; filename=Results_{exam_code}.xlsx'
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
        print("loading answers....")                                                                  # Debug Helper
        data = json.loads(request.body)
        answers = data.get('answers', {})
        student_name = request.session.get('student_name')
        exam_code = request.session.get('exam_code')
        pern_no = request.session.get('pern_no')
        
        print("Fetching questions config from DB")                                                     # Debug Helper
        # NEW: Get config + individual questions
        config_doc = db.collection('questions').document('config').get()
        questions = config_doc.to_dict()['questions'] if config_doc.exists else []
        
        if not questions:
            print("Empty questions....")                                                               # Debug Helper
            questions_docs = list(db.collection('questions').stream())
            questions = [q.to_dict() for q in questions_docs if q.id != 'config']
        
        score = 0
        result_details = []
        print("Calling Transformer grader model....")                                                   # Debug Helper
        grader = DescriptiveAnswerGrader()  # NEW Transformer grader
        print(f"Answers : {answers}")                                                                   # Debug Helper
        for q in questions:
            q_id = q['id']
            user_ans = answers.get(q_id, {})
            q_type = q['type']
            print(f"{q_id} Question score processing")                                                   # Debug Helper
            if q_type == 'mcq':
                selected = user_ans.get('selectedOption', '')
                teacher_answer = q['teacher_answer']
                is_correct = selected == teacher_answer
                q_score = q['max_score'] if is_correct else 0.0
                score += q_score
                details = {'type': 'MCQ', 'correct': is_correct, 'max_score': q['max_score']}
            
            else:  # descriptive
                student_ans = user_ans.get('answer', '')
                if not student_ans.strip():
                    q_score = 0.0
                    print(f"{q_id} was Unanswered...")                                                 # Debug Helper
                    details = {'type': 'Descriptive', 'score': 0.0, 'max_score': q['max_score']}
                else:
                    # NEW: Hybrid grading with concepts
                    concepts = [Concept(**c) for c in q.get('concepts', [])]
                    cfg = QuestionConfig(
                        question_id = q_id,
                        type =  q_type,
                        teacher_answer = q['teacher_answer'],
                        correct_answer = answers[q_id],
                        concepts = concepts,
                        max_score = float(q['max_score']),
                    )
                    print(f"Question config of {q_id} is : {cfg}")                                      # Debug Helper
                    result = grader.grade(cfg, student_ans)
                    print(f"Result score for it :: {result}")                                            # Debug Helper
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
        total_max = sum(q.get('max_score', 1.0) for q in questions)
        submission_data = {
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
    
        exam_results_ref = db.collection('results').document(exam_code).collection('submissions')
        exam_results_ref.document(str(pern_no)).set(submission_data)
        
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
