from django.urls import path
from . import views

urlpatterns = [
    path('', views.login, name='login'),
    path('logout/', views.logout, name='logout'),
    
    # Admin URLs
    path('admin/dashboard/', views.admin_dashboard, name='admin_dashboard'),
    path('admin/upload/', views.admin_upload, name='admin_upload'),
    path('download/sample-excel/', views.download_sample_excel, name='download_sample_excel'),
    path('admin/codes/', views.admin_codes, name='admin_codes'),
    path('admin/stats/', views.admin_stats, name='admin_stats'),
    path('admin/download/<str:code>/', views.download_results, name='download_results'),
    
    # Student URLs
    path('student/enter-code/', views.enter_exam_code, name='enter_exam_code'),
    path('student/exam/', views.take_exam, name='take_exam'),
    path('student/results/', views.student_results, name='student_results'),  # ← ADD THIS LINE
    path('api/submit-exam/', views.submit_exam, name='submit_exam'),


    # Add these paths
    path('api/search-results/', views.student_result_detail, name='student_result_detail'),

]
