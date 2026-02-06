from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse, FileResponse
from django.conf import settings
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.contrib.auth.hashers import make_password, check_password
from django.contrib import messages
import os 
import json
import pandas as pd
import uuid
from datetime import datetime
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from firebase_admin import firestore
SERVER_TIMESTAMP = firestore.SERVER_TIMESTAMP
# NEW IMPORTS for Hybrid Grader
# from .ai_service import evaluate_answer  # Updated to hybrid
from .ai_service import evaluate_answer, DescriptiveAnswerGrader, Concept, QuestionConfig  # NEW

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
            name = request.POST.get('student_name').strip().upper()
            pern_no = request.POST.get('pern_no').strip().upper()
            if name and pern_no:
                request.session['student_name'] = name
                request.session['student_logged_in'] = True
                request.session['pern_no'] = pern_no
                print(f"Student login: {name} | PERN: {pern_no}")
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
    return render(request, 'admin/admin_dashboard.html')


@csrf_exempt
def admin_upload(request):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    # ✅ GET REQUEST - Always show form first
    if request.method == 'GET':
        return render(request, 'admin/admin_upload.html', {
            'success': None,
            'error': None
        })
    
    # ✅ POST REQUEST HANDLING
    if 'file' not in request.FILES:
        return JsonResponse({'error': 'No file selected'}, status=400)
    
    file = request.FILES['file']
    exam_code = request.POST.get('exam_code').upper()
    print(f"Uploading exam for code: {exam_code} from file: {file.name}")
    
    try:
        df = pd.read_excel(file) if file.name.endswith(('.xlsx', '.xls')) else pd.read_csv(file)
        # db.collection('exams').document(exam_code).delete()
        
        db.collection('exams').document(exam_code).set({
            'exam_code': exam_code,
            'status': 'uploading'  # Temporary
        })

        questions_data = []
        for idx, row in df.iterrows():
            q_id = str(row.get('Q_ID', f'Q{idx+1}'))
            q_type = str(row.get('Type', row.get('type', 'mcq'))).lower().strip()
            
            def safe_str(value):
                if pd.isna(value) or value is None:
                    return ''
                if isinstance(value, (list, dict)):
                    return str(value[0] if value else '')
                return str(value).strip()
            
            question = safe_str(row.get('Question'))
            teacher_answer = safe_str(row.get('Teacher_Answer'))
            
            # Concepts parsing (your existing code)
            concepts = []
            concept_names_raw = safe_str(row.get('Concept_Names', ''))
            concept_keywords_raw = safe_str(row.get('Concept_Keywords', ''))
            
            if concept_names_raw and concept_keywords_raw:
                names = [n.strip() for n in concept_names_raw.split(',') if n.strip()]
                kw_groups = [kw.strip() for kw in concept_keywords_raw.split(';') if kw.strip()]
                
                for name, kw_group in zip(names, kw_groups):
                    if name:
                        keywords = [kw.strip() for kw in safe_str(kw_group).split(',') if kw.strip()]
                        concepts.append({'name': name, 'keywords': keywords})
            
            options = []
            if q_type == 'mcq':
                for i in range(1, 5):
                    opt = safe_str(row.get(f'option{i}'))
                    if opt:
                        options.append(opt)
            
            q_data = {
                'id': q_id,
                'question': question,
                'type': q_type,
                'max_score': float(row.get('Max_Score', 10.0 if q_type == 'descriptive' else 1.0)),
                'teacher_answer': teacher_answer,
                'concepts': concepts,
                'options': options,
                'correct_option': safe_str(row.get('Teacher_Answer', '')).upper()
            }
            
            db.collection('exams').document(exam_code).collection('questions').document(q_id).set(q_data)
            questions_data.append(q_data)
        
        db.collection('exams').document(exam_code).set({
            'exam_code': exam_code,
            'questions': questions_data,
            'duration': int(request.POST.get('duration', 60)),
            'total_questions': len(questions_data),
            'max_score': sum(q['max_score'] for q in questions_data),
            'status': 'active'  # Final status
        }, merge=True)

                # db.collection('exams').document(exam_code).set(exam_summary)
        
        success_msg = f'✅ {len(questions_data)} questions uploaded for {exam_code}!'
        
        # AJAX vs Regular form
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'success': True, 'message': success_msg})
        else:
            return render(request, 'admin/admin_upload.html', {
                'success': success_msg
            })
            
    except Exception as e:
        return JsonResponse({'error': f'Upload failed: {str(e)}'}, status=400)


@require_http_methods(["GET"])
def download_sample_excel(request):
    file_path = os.path.join(
        settings.BASE_DIR,
        'exam/static/samples/Exam_Questions_Complete_Sample.xlsx'
    )

    return FileResponse(
        open(file_path, 'rb'),
        as_attachment=True,
        filename='Exam_Questions_Complete_Sample.xlsx'
    )

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
                return render(request, 'admin/admin_codes.html', {
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
    return render(request, 'admin/admin_codes.html', {'codes': codes})

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

import json
from google.cloud import firestore  # Ensure this import

import uuid
from firebase_admin import firestore
import json
from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

def admin_stats(request):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    stats_data = {}
    
    try:
        codes = list(db.collection('exam_codes').limit(50).stream())
        
        for code_doc in codes:
            code_id = code_doc.id
            print(f"🔍 Processing stats for code: {code_id}")
            
            # ✅ UNIVERSAL SCAN: Match ANY doc containing exam code
            all_results_docs = list(db.collection('results').limit(100).stream())
            matching_docs = []
            
            for doc in all_results_docs:
                doc_id = doc.id
                # ✅ MATCH: Exam001_*, even with None pern_no
                if doc_id.startswith(code_id + '_'):
                    matching_docs.append(doc)
                    print(f"  ✅ FOUND: {doc_id}")
            
            print(f"✅ {len(matching_docs)} results for {code_id}")
            
            all_results = []
            scores, totals = [], []
            
            for doc in matching_docs:
                doc_data = doc.to_dict()
                
                score = float(doc_data.get('total_score', 0) or 0)
                total = float(doc_data.get('max_possible', 1) or 1)
                percentage = (score / total * 100) if total > 0 else 0
                
                # ✅ Extract pern_no from doc_id or fallback
                doc_id_parts = doc.id.split('_')
                pern_no = doc_data.get('pern_no') or doc_id_parts[1] if len(doc_id_parts) > 1 else 'Unknown'
                
                all_results.append({
                    'doc_id': doc.id,
                    'pern_no': pern_no,
                    'doc_path': doc.reference.path,
                    'student_name': doc_data.get('student_name', 'Unknown'),
                    'score': f"{score}/{total}",
                    'percentage': f"{percentage:.1f}%",
                    'submitted_at': doc_data.get('submitted_at'),
                    'percentage_num': percentage
                })
                
                scores.append(score)
                totals.append(total)
            
            stats_data[code_id] = {
                'test_name': code_doc.to_dict().get('test_name', 'Unnamed'),
                'exam_code_display': code_id.upper(),
                'pern_docs_found': len(matching_docs),
                'total_tests': len(all_results),
                'avg_score': round(sum(scores) / len(scores), 1) if scores else 0,
                'max_score': max(scores) if scores else 0,
                'min_score': min(scores) if scores else 0,
                'total_questions': totals[0] if totals else 0,
                'results': all_results
            }
    
    except Exception as e:
        print(f"❌ Admin stats error: {e}")
        stats_data = {'error': str(e)}
    
    context = {
        'codes': codes,
        'stats': stats_data,
        'stats_json': json.dumps(stats_data, default=str, indent=2)
    }
    return render(request, 'admin/admin_stats.html', context)


@csrf_exempt
def student_result_detail(request):
    doc_path = request.GET.get('doc_path')
    if not doc_path:
        return JsonResponse({'error': 'No document path'}, status=400)
    
    try:
        doc_ref = db.collection('results').document(doc_path.split('/')[-1])
        doc = doc_ref.get()
        
        if not doc.exists:
            return JsonResponse({'error': 'Document not found'}, status=404)
        
        data = doc.to_dict()
        return JsonResponse({
            'doc_id': doc.id,
            'student_name': data.get('student_name'),
            'pern_no': data.get('pern_no'),
            'exam_code': data.get('exam_code'),
            'percentage': data.get('percentage'),
            'total_score': data.get('total_score'),
            'max_possible': data.get('max_possible'),
            'evaluation': data.get('q_results', [])
        })
    
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


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
    
    if not request.session.get('student_logged_in'):
        return redirect('login')
    
    if request.method == 'POST':
        code = request.POST.get('exam_code')
        code = code.upper().strip()

        # ✅ Check exam code exists FIRST
        exam_doc = db.collection('exams').document(code).get()
        print("Checking exam code:", code)
        print("Exam document exists:", exam_doc.exists)

        if not exam_doc.exists:
            return render(request, 'student/enter_exam_code.html', {'error': 'Invalid exam code'})
        
        # ✅ Get questions from subcollection
        questions = list(db.collection('exams').document(code).collection('questions').stream())
        if not questions:
            return render(request, 'student/enter_exam_code.html', {'error': 'No questions loaded for this exam'})
        
        code_data = exam_doc.to_dict()

        if not code_data.get('status', False):
            return render(request, 'student/enter_exam_code.html', {'error': 'Exam not active'})
        
        request.session['exam_code'] = code
        request.session['exam_duration'] = code_data.get('duration', 60)
        request.session['exam_start_time'] = datetime.now().isoformat()
        return redirect('take_exam')
    
    return render(request, 'student/enter_exam_code.html')


def take_exam(request):
    # UNCHANGED
    if not request.session.get('student_logged_in') or 'exam_code' not in request.session:
        return redirect('enter_exam_code')
    try:
        exam_code = request.session['exam_code']
        questions = list(db.collection('exams').document(exam_code).collection('questions').stream())
        
        print(f"🔍 Loaded {len(questions)} questions for {exam_code}")
        
        if not questions:
            print(f"❌ No questions found for {exam_code}")
            return render(request, 'student/enter_exam_code.html', {
                'error': f'No questions found for exam "{exam_code}". Contact admin.'
            })
        
        questions_data = [{
            'id': q.id,
            'question': q.to_dict()['question'],
            'type': q.to_dict()['type'],
            'options': q.to_dict().get('options', []),
            'max_score': q.to_dict().get('max_score', 1.0),
            'teacher_answer': q.to_dict().get('teacher_answer', '')
        } for q in questions]
        
        print(f"✅ Sending {len(questions_data)} questions to template")
        
        return render(request, 'student/take_exam.html', {
            'questions': json.dumps(questions_data),
            'duration': request.session.get('exam_duration', 60),
            'student_name': request.session.get('student_name'),
            'exam_code': exam_code
        })
    except Exception as e:
        print(f"❌ ERROR loading exam: {str(e)}")
        return render(request, 'student/enter_exam_code.html', {
            'error': f'Error loading exam: {str(e)}'
        })

def evaluate_exam(answers, exam_code, pern_no=None, student_name=None):
    print(f"🔍 Evaluating {exam_code}: {len(answers)} answers")
    
    try:
        questions = list(db.collection('exams').document(exam_code).collection('questions').stream())
        if not questions:
            return {'error': f'No questions found for exam {exam_code}'}
        
        total_score = 0.0
        max_possible = 0.0
        details = []
        
        for q in questions:
            q_data = q.to_dict()
            q_id = q.id
            
            max_score = q_data.get('max_score', 1.0)
            q_type = q_data.get('type', 'mcq')
            teacher_answer = q_data.get('teacher_answer', q_data.get('correct_option', ''))
            
            concepts_data = q_data.get('concepts', [])
            concepts = [Concept(c.get('name', ''), c.get('keywords', []), c.get('weight', 1.0)) 
                       for c in concepts_data]
            
            student_answer = (answers.get(q_id, {})
                            .get('selectedOption') or 
                            answers.get(q_id, {}).get('answer', '')).strip()
            
            result = evaluate_answer(
                student_answer=student_answer,
                correct_answer=teacher_answer,
                concepts=concepts,
                max_score=max_score,
                q_type=q_type
            )
            
            total_score += result['final_score']
            max_possible += max_score
            
            # ✅ CONDITIONAL BREAKDOWN
            detail_data = {
                'question_id': q_id,
                'question': q_data.get('question', 'Unknown')[:60] + '...',
                'type': q_type,
                'max_score': max_score,
                'final_score': result['final_score'],
                'normalized': result.get('normalized', 0.0),
                'student_answer': student_answer[:120] + '...' if len(student_answer) > 120 else student_answer,
                'teacher_answer': teacher_answer[:120] + '...',
                'is_correct': result.get('is_correct', result.get('normalized', 0) > 0.5),
                'concepts': [c.name for c in concepts]
            }
            
            # 🔥 DESCRIPTIVE ONLY: Detailed AI scores
            if q_type == 'descriptive':
                detail_data.update({
                    'concept_score': result.get('concept_score', 0.0),
                    'relation_score': result.get('relation_score', 0.0),
                    'semantic_similarity': result.get('semantic_similarity', 0.0),
                    'penalty': result.get('penalty', 0.0),
                    'show_breakdown': True
                })
            else:  # MCQ
                detail_data.update({
                    'show_breakdown': False,
                    'options': q_data.get('options', []),
                    'selected_option': student_answer,
                    'correct_option': teacher_answer,
                    'message': result.get('message', 'Evaluated')
                })
            
            details.append(detail_data)
        
        percentage = (total_score / max_possible * 100) if max_possible > 0 else 0
        
        return {
            'total_score': total_score,
            'percentage': percentage,
            'max_possible': max_possible,
            'details': details,
            'student_name': student_name,
            'exam_code': exam_code
        }
        
    except Exception as e:
        print(f"❌ EVALUATION ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'error': f'Evaluation failed: {str(e)}'}


@csrf_exempt
def submit_exam(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        exam_code = data.get('exam_code')
        pern_no = data.get('pern_no')
        student_name = data.get('student_name', 'Unknown')
        questions = data.get('questions', [])

        if not exam_code or not pern_no:
            print("❌ Missing exam_code or pern_no in submission")
        
        # ✅ NEW PRODUCTION DOC ID: exam_code_pern_uuid
        doc_id = f"{exam_code}_{pern_no}_{str(uuid.uuid4())}"
        result_ref = db.collection('results').document(doc_id)
        
        # ✅ FLAT STRUCTURE - All data in ONE document
        result_data = {
            'exam_code': exam_code,
            'pern_no': pern_no,
            'student_name': student_name,
            'submitted_at': firestore.SERVER_TIMESTAMP,
            'total_score': 0.0,
            'max_possible': 0.0,
            'percentage': 0.0,
            'q_results': [],  # Array of question details
            'timestamp': firestore.SERVER_TIMESTAMP
        }
        
        # Process each question
        total_score = 0.0
        max_possible = 0.0
        q_results = []
        
        for q_data in questions:
            q_id = q_data.get('question_id')
            q_type = q_data.get('type', 'MCQ')
            max_score = float(q_data.get('max_score', 0))
            student_answer = q_data.get('student_answer', '')
            teacher_answer = q_data.get('teacher_answer', '')
            
            # Your existing AI evaluation logic here
            if q_type.upper() == 'DESCRIPTIVE':
                result = evaluate_descriptive_answer(student_answer, teacher_answer, max_score)
            else:
                result = evaluate_mcq_answer(student_answer, teacher_answer, max_score)
            
            q_result = {
                'question_id': q_id,
                'type': q_type,
                'max_score': max_score,
                'final_score': result.get('final_score', 0.0),
                'normalized': result.get('normalized', 0.0),
                'percentage': result.get('percentage', 0.0),
                'student_answer': student_answer[:200],  # Truncate for storage
                'teacher_answer': teacher_answer[:200],
                'concept_score': result.get('concept_score', 0.0),
                'relation_score': result.get('relation_score', 0.0),
                'semantic_similarity': result.get('semantic_similarity', 0.0),
                'penalty': result.get('penalty', 0.0)
            }
            
            q_results.append(q_result)
            total_score += result.get('final_score', 0.0)
            max_possible += max_score
        
        # Final calculations
        percentage = (total_score / max_possible * 100) if max_possible > 0 else 0
        
        result_data.update({
            'total_score': round(total_score, 2),
            'max_possible': round(max_possible, 2),
            'percentage': round(percentage, 1),
            'q_results': q_results
        })
        
        # ✅ SAVE TO FIRESTORE (Production structure)
        result_ref.set(result_data)
        
        print(f"✅ SAVED: {doc_id} | {student_name} | {percentage:.1f}%")
        
        return JsonResponse({
            'success': True,
            'doc_id': doc_id,
            'percentage': percentage,
            'total_score': total_score,
            'message': 'Exam submitted successfully!'
        })
        
    except Exception as e:
        print(f"❌ submit_exam error: {e}")
        return JsonResponse({'error': str(e)}, status=500)


def student_results(request):
    if not request.session.get('student_logged_in'):
        return redirect('login')
    
    # Get from session or query param
    doc_path = request.session.get('last_result_id') or request.GET.get('doc_path')
    
    if not doc_path:
        return render(request, 'student/results.html', {
            'error': 'No results found. Please take an exam first.',
            'student_name': request.session.get('student_name', 'Student')
        })
    
    try:
        result_doc = db.document(doc_path).get()
        if not result_doc.exists:
            return render(request, 'student/results.html', {
                'error': 'Result not found.',
                'student_name': request.session.get('student_name', 'Student')
            })
        
        results = result_doc.to_dict()
        student_name = request.session.get('student_name', results.get('student_name', 'Student'))
        
        # Clear session after viewing
        if request.session.get('last_result_id') == doc_path:
            request.session.pop('last_result_id', None)
            request.session.modified = True
        
        return render(request, 'student/results.html', {
            'results': results,
            'student_name': student_name,
            'exam_code': results.get('exam_code'),
            'submitted_at': results.get('submitted_at'),
            'doc_path': doc_path
        })
        
    except Exception as e:
        return render(request, 'student/results.html', {
            'error': f'Error loading results: {str(e)}',
            'student_name': request.session.get('student_name', 'Student')
        })

