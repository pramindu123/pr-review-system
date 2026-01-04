from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .api_views import (
    RepositoryViewSet, BranchRuleViewSet, PullRequestViewSet,
    ReviewViewSet, GitHubWebhookView, DashboardStatsView
)

router = DefaultRouter()
router.register(r'repositories', RepositoryViewSet)
router.register(r'branch-rules', BranchRuleViewSet)
router.register(r'pull-requests', PullRequestViewSet)
router.register(r'reviews', ReviewViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('webhooks/github/', GitHubWebhookView.as_view(), name='github-webhook'),
    path('dashboard/stats/', DashboardStatsView.as_view(), name='dashboard-stats'),
]
