from django.urls import path
from . import views

urlpatterns = [
    path('', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    
    # Admin URLs
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/upload/', views.admin_upload, name='admin_upload'),
    path('admin/codes/', views.admin_codes, name='admin_codes'),
    path('admin/stats/', views.admin_stats, name='admin_stats'),
    path('admin/download/<str:exam_code>/', views.download_results, name='download_results'),
    path('admin/result/<str:exam_code>/<str:per_no>/', views.admin_result_view, name='admin_result_view'),
    path('admin/student-result-detail/<str:exam_code>/<str:doc_id>/', views.get_student_detail_json, name='get_student_detail_json'),
    # Student URLs
    path('student/enter-code/', views.enter_exam_code, name='enter_exam_code'),
    path('student/exam/', views.take_exam, name='take_exam'),
    path('student/results/', views.student_results, name='student_results'),  # ← ADD THIS LINE
    path('api/submit-exam/', views.submit_exam, name='submit_exam'),
]
