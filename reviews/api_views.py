from rest_framework import viewsets, status, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Count, Q
import hashlib
import hmac
import json

from .models import Repository, BranchRule, PullRequest, Review, ReviewComment, WebhookLog
from .serializers import (
    RepositorySerializer, BranchRuleSerializer, 
    PullRequestListSerializer, PullRequestDetailSerializer,
    ReviewSerializer, ReviewApprovalSerializer, 
    WebhookLogSerializer, SyncRepositorySerializer
)
from .github_client import GitHubClient, sync_pull_request, GitHubAPIError
from .review_engine import ReviewEngine
from django.conf import settings


class RepositoryViewSet(viewsets.ModelViewSet):
    queryset = Repository.objects.all()
    serializer_class = RepositorySerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.query_params.get('active'):
            queryset = queryset.filter(is_active=True)
        return queryset
    
    @action(detail=True, methods=['post'])
    def sync(self, request, pk=None):
        repository = self.get_object()
        serializer = SyncRepositorySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        state = serializer.validated_data.get('state', 'open')
        
        try:
            client = GitHubClient()
            prs = client.get_pull_requests(repository.owner, repository.repo_name, state=state)
            
            synced = 0
            created = 0
            for pr_data in prs:
                pr_detail = client.get_pull_request(
                    repository.owner, repository.repo_name, pr_data['number']
                )
                pr, was_created = sync_pull_request(repository, pr_detail)
                synced += 1
                if was_created:
                    created += 1
            
            return Response({
                'status': 'success',
                'synced': synced,
                'created': created,
                'message': f'Synced {synced} pull requests ({created} new)'
            })
        except GitHubAPIError as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['get'])
    def verify(self, request, pk=None):
        repository = self.get_object()
        client = GitHubClient()
        
        success, error = client.verify_repository_access(
            repository.owner, repository.repo_name
        )
        
        if success:
            return Response({
                'status': 'success',
                'message': 'Repository access verified'
            })
        else:
            return Response({
                'status': 'error',
                'message': error
            }, status=status.HTTP_400_BAD_REQUEST)


class BranchRuleViewSet(viewsets.ModelViewSet):
    queryset = BranchRule.objects.all()
    serializer_class = BranchRuleSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset()
        repository = self.request.query_params.get('repository')
        if repository:
            queryset = queryset.filter(
                Q(repository_id=repository) | Q(repository__isnull=True)
            )
        return queryset


class PullRequestViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = PullRequest.objects.all()
    permission_classes = [permissions.IsAuthenticated]
    
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return PullRequestDetailSerializer
        return PullRequestListSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related('repository')
        

        repository = self.request.query_params.get('repository')
        if repository:
            queryset = queryset.filter(repository_id=repository)
        

        pr_status = self.request.query_params.get('status')
        if pr_status:
            queryset = queryset.filter(status=pr_status)
        

        review_status = self.request.query_params.get('review_status')
        if review_status:
            queryset = queryset.filter(reviews__status=review_status).distinct()
        

        pending = self.request.query_params.get('pending')
        if pending == 'true':
            queryset = queryset.filter(reviews__status='pending').distinct()
        
        return queryset.prefetch_related('reviews')
    
    @action(detail=True, methods=['post'])
    def review(self, request, pk=None):
        pull_request = self.get_object()
        
        try:
            engine = ReviewEngine()
            review = engine.review_pull_request(pull_request)
            
            serializer = ReviewSerializer(review)
            return Response({
                'status': 'success',
                'message': 'Review generated successfully',
                'review': serializer.data
            })
        except Exception as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def refresh(self, request, pk=None):
        """Refresh pull request data from GitHub."""
        pull_request = self.get_object()
        repo = pull_request.repository
        
        try:
            client = GitHubClient()
            pr_data = client.get_pull_request(
                repo.owner, repo.repo_name, pull_request.number
            )
            updated_pr, _ = sync_pull_request(repo, pr_data)
            
            serializer = PullRequestDetailSerializer(updated_pr)
            return Response({
                'status': 'success',
                'pull_request': serializer.data
            })
        except GitHubAPIError as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)


class ReviewViewSet(viewsets.ModelViewSet):
    queryset = Review.objects.all()
    serializer_class = ReviewSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    def get_queryset(self):
        queryset = super().get_queryset().select_related(
            'pull_request', 'pull_request__repository', 'branch_rule', 'reviewed_by'
        )
        
        review_status = self.request.query_params.get('status')
        if review_status:
            queryset = queryset.filter(status=review_status)
        
        repository = self.request.query_params.get('repository')
        if repository:
            queryset = queryset.filter(pull_request__repository_id=repository)
        
        return queryset.prefetch_related('comments')
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        review = self.get_object()
        serializer = ReviewApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        notes = serializer.validated_data.get('notes', '')
        post_to_github = serializer.validated_data.get('post_to_github', False)
        
        review.approve(request.user, notes)
        
        if post_to_github:
            try:
                self._post_review_to_github(review)
            except GitHubAPIError as e:
                return Response({
                    'status': 'partial',
                    'message': f'Review approved but failed to post to GitHub: {e}'
                })
        
        return Response({
            'status': 'success',
            'message': 'Review approved' + (' and posted to GitHub' if post_to_github else '')
        })
    
    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        review = self.get_object()
        serializer = ReviewApprovalSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        notes = serializer.validated_data.get('notes', '')
        review.reject(request.user, notes)
        
        return Response({
            'status': 'success',
            'message': 'Review rejected'
        })
    
    @action(detail=True, methods=['post'])
    def post_to_github(self, request, pk=None):
        review = self.get_object()
        
        if review.status != 'approved':
            return Response({
                'status': 'error',
                'message': 'Review must be approved before posting to GitHub'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            self._post_review_to_github(review)
            return Response({
                'status': 'success',
                'message': 'Review posted to GitHub'
            })
        except GitHubAPIError as e:
            return Response({
                'status': 'error',
                'message': str(e)
            }, status=status.HTTP_400_BAD_REQUEST)
    
    def _post_review_to_github(self, review):
        pr = review.pull_request
        repo = pr.repository
        
        client = GitHubClient()
        
        result = client.create_issue_comment(
            repo.owner, repo.repo_name, pr.number, review.summary
        )
        
        review.mark_posted(result.get('id'))


class GitHubWebhookView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def post(self, request):
        if settings.GITHUB_WEBHOOK_SECRET:
            signature = request.headers.get('X-Hub-Signature-256')
            if not self._verify_signature(request.body, signature):
                return Response({'error': 'Invalid signature'}, status=status.HTTP_403_FORBIDDEN)
        
        event_type = request.headers.get('X-GitHub-Event', 'unknown')
        payload = request.data
        

        webhook_log = WebhookLog.objects.create(
            event_type=event_type,
            payload=payload
        )
        
        try:
            if event_type == 'pull_request':
                self._handle_pull_request_event(payload, webhook_log)
            elif event_type == 'ping':
                webhook_log.processed = True
                webhook_log.processed_at = timezone.now()
                webhook_log.save()
            
            return Response({'status': 'ok'})
        except Exception as e:
            webhook_log.error_message = str(e)
            webhook_log.save()
            return Response({'error': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _verify_signature(self, payload, signature):

        if not signature:
            return False
        
        expected = 'sha256=' + hmac.new(
            settings.GITHUB_WEBHOOK_SECRET.encode(),
            payload,
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)
    
    def _handle_pull_request_event(self, payload, webhook_log):

        action = payload.get('action')
        pr_data = payload.get('pull_request', {})
        repo_data = payload.get('repository', {})
        

        repo_full_name = repo_data.get('full_name', '').split('/')
        if len(repo_full_name) != 2:
            raise ValueError("Invalid repository name")
        
        try:
            repository = Repository.objects.get(
                owner=repo_full_name[0],
                repo_name=repo_full_name[1]
            )
        except Repository.DoesNotExist:
            raise ValueError(f"Repository not found: {repo_data.get('full_name')}")
        
        webhook_log.repository = repository
        webhook_log.save()
        

        client = GitHubClient()
        pr_detail = client.get_pull_request(
            repository.owner, repository.repo_name, pr_data['number']
        )
        pr, created = sync_pull_request(repository, pr_detail)
        

        if action in ['opened', 'synchronize', 'reopened']:
            engine = ReviewEngine()
            engine.review_pull_request(pr)
        
        webhook_log.processed = True
        webhook_log.processed_at = timezone.now()
        webhook_log.save()


class DashboardStatsView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    
    def get(self, request):
        stats = {
            'repositories': Repository.objects.filter(is_active=True).count(),
            'pull_requests': {
                'total': PullRequest.objects.count(),
                'open': PullRequest.objects.filter(status='open').count(),
                'closed': PullRequest.objects.filter(status='closed').count(),
                'merged': PullRequest.objects.filter(status='merged').count(),
            },
            'reviews': {
                'total': Review.objects.count(),
                'pending': Review.objects.filter(status='pending').count(),
                'approved': Review.objects.filter(status='approved').count(),
                'rejected': Review.objects.filter(status='rejected').count(),
                'posted': Review.objects.filter(status='posted').count(),
            },
            'recent_reviews': ReviewSerializer(
                Review.objects.select_related('pull_request')[:5],
                many=True
            ).data
        }
        
        return Response(stats)
