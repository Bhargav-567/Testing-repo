from django.shortcuts import render, redirect
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib import messages
from django.contrib.auth.hashers import make_password, check_password


from .firebase_config import db
from .firebase_config import get_firestore_client

from .ai_service import evaluate_answer
import json
import pandas as pd
from datetime import datetime
from google.cloud.firestore_v1 import SERVER_TIMESTAMP

# Admin credentials
ADMIN_USER = 'Admin'
ADMIN_PASS = 'key123'
ADMIN_REGISTER_CODE = 'Boss@2025'
ADMIN_DOC_ID = "8BxExHElJPAbZmMr4oeF"  # Firestore document ID for admin credentials

# ==================== DATABASE HELPER ====================

def get_admin_doc():
    doc_ref = db.collection('admin_users').document(ADMIN_DOC_ID)
    doc = doc_ref.get()
    return doc_ref, doc

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
            
            # Hash the new password before storing
            password_hash = make_password(new_password)
            
            # Update Firestore admin doc with new password and optional contact info
            update_data = {
                'password_hash': password_hash,
                'email_or_mobile': contact_info,
                'updated_at': datetime.utcnow()
            }
            doc_ref.update(update_data)
            
            # Optionally add a success message here
            return redirect('login')  # Redirect after password reset
        
        # Login processing: check Firestore admin credentials
        login_type = request.POST.get('login_type')
        
        if login_type == 'admin':
            username = request.POST.get('username')
            password = request.POST.get('password')
            
            doc_ref, doc = get_admin_doc()
            if not doc.exists:
                error = "Admin credentials not set. Contact system administrator."
                return render(request, 'login.html', {'error': error})
            
            admin_data = doc.to_dict()
            stored_username = admin_data.get('username')
            stored_password_hash = admin_data.get('password_hash')
            
            # Check username and verify hashed password
            if (username == stored_username and 
                check_password(password, stored_password_hash)):
                request.session['admin_logged_in'] = True
                return redirect('admin_dashboard')
            else:
                error = 'Invalid credentials'
        
        elif login_type == 'student':
            name = request.POST.get('student_name')
            pern_no = request.POST.get('pern_no')  # NEW LINE
            if name and pern_no:
                request.session['student_name'] = name
                request.session['student_logged_in'] = True
                request.session['pern_no'] = pern_no  # NEW LINE
                return redirect('enter_exam_code')
            else:
                error = 'Enter your name and PERN no'
            # Your existing student login logic here
            pass

    return render(request, 'login.html', {'error': error})

def logout(request):
    request.session.flush()
    return redirect('login')

# ==================== ADMIN VIEWS ====================

def admin_dashboard(request):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    return render(request, 'admin_dashboard.html')

def admin_upload(request):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    if request.method == 'POST':
        if 'file' not in request.FILES:
            return render(request, 'admin_upload.html', {'error': 'No file selected'})
        
        file = request.FILES['file']
        duration = int(request.POST.get('duration', 60))
        
        try:
            # Read Excel/CSV file
            if file.name.endswith('.csv'):
                df = pd.read_csv(file)
            else:
                df = pd.read_excel(file)
            
            # Clear existing questions in Firestore
            questions_ref = db.collection('questions')
            for doc in questions_ref.stream():
                doc.reference.delete()
            
            # Add new questions
            for idx, row in df.iterrows():
                options = [str(row.get(f'option{i}', '')) for i in range(1, 5)]
                options = [opt for opt in options if opt and opt != 'nan']
                
                question_data = {
                    'id': str(row.get('id', f'q{idx+1}')),
                    'question': str(row['question']),
                    'type': str(row['type']).lower().strip(),
                    'options': options,
                    'correct_answer': str(row.get('correct answer', '')),
                    'correct_option': str(row.get('correct option', '')),
                    'created_at': SERVER_TIMESTAMP
                }
                
                db.collection('questions').document(question_data['id']).set(question_data)
            
            return render(request, 'admin_upload.html', {
                'success': f'Uploaded {len(df)} questions successfully!'
            })
        
        except Exception as e:
            return render(request, 'admin_upload.html', {'error': f'Error: {str(e)}'})
    
    return render(request, 'admin_upload.html')

def admin_codes(request):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add':
            code = request.POST.get('code')
            test_name = request.POST.get('test_name', 'New Test')
            duration = int(request.POST.get('duration', 60))
            
            # Check if code exists
            if db.collection('exam_codes').document(code).get().exists:
                codes = list(db.collection('exam_codes').stream())
                return render(request, 'admin_codes.html', {
                    'error': 'Code already exists',
                    'codes': codes
                })
            
            # Add new code
            db.collection('exam_codes').document(code).set({
                'code': code,
                'test_name': test_name,
                'duration': duration,
                'active': False,
                'created_at': SERVER_TIMESTAMP
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

def admin_stats(request):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    codes = list(db.collection('exam_codes').stream())
    
    stats_data = {}
    for code_doc in codes:
        code = code_doc.id
        results = list(db.collection('results').where('exam_code', '==', code).stream())
        
        if results:
            scores = [r.to_dict()['score'] for r in results]
            total = results[0].to_dict()['total']
            stats_data[code] = {
                'test_name': code_doc.to_dict().get('test_name', 'Unnamed'),
                'total_tests': len(results),
                'avg_score': sum(scores) / len(scores),
                'max_score': max(scores),
                'min_score': min(scores),
                'total_questions': total,
                'results': [{
                    'student_name': r.to_dict()['student_name'],
                    'score': f"{r.to_dict()['score']}/{r.to_dict()['total']}",
                    'percentage': f"{(r.to_dict()['score'] / r.to_dict()['total']) * 100:.2f}%",
                    'timestamp': r.to_dict()['timestamp']
                } for r in results]
            }
    
    return render(request, 'admin_stats.html', {'codes': codes, 'stats': stats_data})

def download_results(request, code):
    if not request.session.get('admin_logged_in'):
        return redirect('login')
    
    results = list(db.collection('results').where('exam_code', '==', code).stream())
    
    data = [{
        'Student Name': r.to_dict()['student_name'],
        'Score': f"{r.to_dict()['score']}/{r.to_dict()['total']}",
        'Percentage': f"{(r.to_dict()['score'] / r.to_dict()['total']) * 100:.2f}%",
        'Timestamp': r.to_dict()['timestamp']
    } for r in results]
    
    df = pd.DataFrame(data)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="{code}_results.csv"'
    df.to_csv(path_or_buf=response, index=False)
    
    return response

# ==================== STUDENT VIEWS ====================

def enter_exam_code(request):
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
        
        # Check if questions exist
        questions = list(db.collection('questions').stream())
        if not questions:
            return render(request, 'enter_exam_code.html', {'error': 'No questions loaded'})
        
        request.session['exam_code'] = code
        request.session['exam_duration'] = code_data.get('duration', 60)
        request.session['exam_start_time'] = datetime.now().isoformat()
        return redirect('take_exam')
    
    return render(request, 'enter_exam_code.html')

def take_exam(request):
    if not request.session.get('student_logged_in') or 'exam_code' not in request.session:
        return redirect('enter_exam_code')
    
    questions = list(db.collection('questions').stream())
    questions_data = [{
        'id': q.id,
        'question': q.to_dict()['question'],
        'type': q.to_dict()['type'],
        'options': q.to_dict().get('options', [])
    } for q in questions]
    
    context = {
        'questions': json.dumps(questions_data),
        'duration': request.session.get('exam_duration', 60),
        'student_name': request.session.get('student_name'),
        'exam_code': request.session.get('exam_code')
    }
    
    return render(request, 'take_exam.html', context)

@csrf_exempt
def submit_exam(request):
    """Submit exam answers and evaluate"""
    print("\n" + "="*60)
    print("🔍 SUBMIT EXAM FUNCTION CALLED")
    print("="*60)
    
    if request.method != 'POST':
        print("❌ Invalid request method:", request.method)
        return JsonResponse({'error': 'Invalid request method'}, status=400)
    
    try:
        print("\n📝 Step 1: Parsing request body...")
        data = json.loads(request.body)
        answers = data.get('answers', {})
        print(f"✅ Parsed {len(answers)} answers from request")
        
        print("\n📝 Step 2: Getting session data...")
        student_name = request.session.get('student_name')
        exam_code = request.session.get('exam_code')
        print(f"✅ Student: {student_name}")
        print(f"✅ Exam Code: {exam_code}")
        
        if not student_name or not exam_code:
            print("❌ Missing session data!")
            return JsonResponse({'error': 'Session expired'}, status=400)
        
        print("\n📝 Step 3: Connecting to Firebase...")
        
        # db = get_db()
        print("✅ Firebase connected")
        
        print("\n📝 Step 4: Fetching questions from database...")
        questions_ref = db.collection('questions')
        questions_docs = list(questions_ref.stream())
        print(f"✅ Found {len(questions_docs)} questions in database")
        
        if not questions_docs:
            print("❌ No questions found in database!")
            return JsonResponse({'error': 'No questions found'}, status=400)
        
        print("\n📝 Step 5: Converting questions to list...")
        questions = []
        for q_doc in questions_docs:
            q_data = q_doc.to_dict()
            q_data['doc_id'] = q_doc.id
            questions.append(q_data)
            print(f"   - Q{q_doc.id}: {q_data.get('question', '')[:50]}...")
        
        print("\n📝 Step 6: Evaluating answers...")
        score = 0
        result_details = []
        
        for i, q in enumerate(questions):
            q_id = q.get('doc_id')
            user_ans = answers.get(q_id, {})
            q_type = q.get('type', 'unknown')
            
            print(f"\n   Question {i+1}/{len(questions)} ({q_type}):")
            print(f"   - ID: {q_id}")
            
            if q_type == 'mcq':
                selected = user_ans.get('selectedOption', '')
                correct_option = q.get('correct_option', '')
                is_correct = (selected == correct_option) if selected and correct_option else False
                
                if is_correct:
                    score += 1
                
                print(f"   - Your answer: {selected}")
                print(f"   - Correct answer: {correct_option}")
                print(f"   - Result: {'✅ Correct' if is_correct else '❌ Wrong'}")
                
                result_details.append({
                    'question': q.get('question', ''),
                    'type': 'MCQ',
                    'your_answer': selected,
                    'correct_answer': correct_option,
                    'correct': is_correct,
                    'score': 100 if is_correct else 0
                })
            
            else:  # descriptive
                student_answer = user_ans.get('answer', '')
                correct_answer = q.get('correct_answer', '')
                
                print(f"   - Your answer: {student_answer[:50]}...")
                print(f"   - Correct answer: {correct_answer[:50]}...")
                
                if student_answer and correct_answer:
                    similarity, ai_score, is_correct = evaluate_answer(student_answer, correct_answer)
                    print(f"   - Similarity: {similarity:.2f}")
                    print(f"   - AI Score: {ai_score:.2f}%")
                    print(f"   - Result: {'✅ Correct' if is_correct else '❌ Wrong'}")
                else:
                    similarity, ai_score, is_correct = 0.0, 0.0, False
                    print(f"   - Result: ❌ No answer provided")
                
                if is_correct:
                    score += 1
                
                result_details.append({
                    'question': q.get('question', ''),
                    'type': 'Descriptive',
                    'your_answer': student_answer,
                    'correct_answer': correct_answer,
                    'correct': is_correct,
                    'score': float(ai_score)
                })
        
        print(f"\n📊 Final Score: {score}/{len(questions)}")
        
        print("\n📝 Step 7: Saving to Firestore...")
        result_data = {
            'exam_code': exam_code,
            'student_name': student_name,
            'pern_no': request.session.get('pern_no'), 
            'score': int(score),
            'total': len(questions),
            'details': result_details,
            'timestamp': datetime.now().isoformat()
        }
        
        print(f"   - Exam Code: {exam_code}")
        print(f"   - Student: {student_name}")
        print(f"   - Score: {score}/{len(questions)}")
        
        # Save to database
        doc_ref = db.collection('results').add(result_data)
        print(f"✅ Result saved to Firestore! Doc ID: {doc_ref[1].id}")
        
        print("\n✅ SUCCESS: Exam submitted completely!")
        print("="*60 + "\n")
        
        # Return success response
        return JsonResponse({
            'success': True,
            'score': score,
            'total': len(questions),
            'details': result_details,
            'message': 'Exam submitted successfully'
        }, status=200)
    
    except json.JSONDecodeError as e:
        print(f"❌ JSON decode error: {e}")
        return JsonResponse({'error': 'Invalid JSON format'}, status=400)
    
    except Exception as e:
        error_msg = str(e)
        print(f"\n❌ ERROR: {error_msg}")
        import traceback
        traceback.print_exc()
        print("="*60 + "\n")
        return JsonResponse({'error': f'Server error: {error_msg}'}, status=500)


def student_results(request):
    """Display exam results page"""
    if not request.session.get('student_logged_in'):
        return redirect('login')
    
    return render(request, 'results.html')
