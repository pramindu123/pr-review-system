from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('repositories/', views.repository_list, name='repository_list'),
    path('repositories/add/', views.repository_add, name='repository_add'),
    path('repositories/<int:pk>/', views.repository_detail, name='repository_detail'),
    path('repositories/<int:pk>/sync/', views.repository_sync, name='repository_sync'),
    path('repositories/<int:pk>/delete/', views.repository_delete, name='repository_delete'),
    path('repositories/<int:pk>/toggle-webhook/', views.repository_toggle_webhook, name='repository_toggle_webhook'),
    path('pull-requests/', views.pull_request_list, name='pull_request_list'),
    path('pull-requests/<int:pk>/', views.pull_request_detail, name='pull_request_detail'),
    path('pull-requests/<int:pk>/review/', views.pull_request_review, name='pull_request_review'),
    path('reviews/', views.review_list, name='review_list'),
    path('reviews/<int:pk>/', views.review_detail, name='review_detail'),
    path('reviews/<int:pk>/approve/', views.review_approve, name='review_approve'),
    path('reviews/<int:pk>/reject/', views.review_reject, name='review_reject'),
    path('reviews/<int:pk>/post-to-github/', views.review_post_to_github, name='review_post_to_github'),
    path('pending/', views.pending_approvals, name='pending_approvals'),
    path('branch-rules/', views.branch_rule_list, name='branch_rule_list'),
    path('branch-rules/add/', views.branch_rule_add, name='branch_rule_add'),
    path('branch-rules/<int:pk>/delete/', views.branch_rule_delete, name='branch_rule_delete'),
]
