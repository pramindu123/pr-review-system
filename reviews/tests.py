from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from unittest.mock import patch, MagicMock

from .models import Repository, BranchRule, PullRequest, Review
from .review_engine import ReviewEngine
from .github_client import GitHubClient


class RepositoryModelTests(TestCase):
    """Tests for Repository model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.repository = Repository.objects.create(
            name='owner/repo',
            owner='owner',
            repo_name='repo',
            github_url='https://github.com/owner/repo',
            created_by=self.user
        )

    def test_full_name_property(self):
        """Test full_name property returns correct format."""
        self.assertEqual(self.repository.full_name, 'owner/repo')

    def test_str_representation(self):
        """Test string representation."""
        self.assertEqual(str(self.repository), 'owner/repo')


class BranchRuleModelTests(TestCase):
    """Tests for BranchRule model."""

    def test_get_expectations_list(self):
        """Test expectations list extraction."""
        rule = BranchRule.objects.create(
            name='Test Rule',
            branch_pattern='feature/*',
            expectations={
                'checks': [
                    {'name': 'has_tests', 'description': 'Has tests', 'weight': 20}
                ]
            }
        )
        checks = rule.get_expectations_list()
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]['name'], 'has_tests')


class ReviewEngineTests(TestCase):
    """Tests for ReviewEngine."""

    def setUp(self):
        self.engine = ReviewEngine()

    def test_get_branch_type_feature(self):
        """Test branch type detection for feature branches."""
        self.assertEqual(self.engine.get_branch_type('feature/new-login'), 'feature')
        self.assertEqual(self.engine.get_branch_type('feat/new-login'), 'feature')

    def test_get_branch_type_bugfix(self):
        """Test branch type detection for bugfix branches."""
        self.assertEqual(self.engine.get_branch_type('bugfix/fix-login'), 'bugfix')
        self.assertEqual(self.engine.get_branch_type('fix/fix-login'), 'bugfix')

    def test_get_branch_type_hotfix(self):
        """Test branch type detection for hotfix branches."""
        self.assertEqual(self.engine.get_branch_type('hotfix/critical-fix'), 'hotfix')

    def test_get_branch_type_release(self):
        """Test branch type detection for release branches."""
        self.assertEqual(self.engine.get_branch_type('release/v1.0.0'), 'release')

    def test_get_branch_type_other(self):
        """Test branch type detection for unknown branches."""
        self.assertEqual(self.engine.get_branch_type('my-branch'), 'other')
        self.assertEqual(self.engine.get_branch_type('main'), 'other')

    def test_analyze_files(self):
        """Test file analysis."""
        files = [
            {'filename': 'src/main.py', 'additions': 100, 'deletions': 20},
            {'filename': 'tests/test_main.py', 'additions': 50, 'deletions': 10},
            {'filename': 'README.md', 'additions': 20, 'deletions': 5},
        ]
        analysis = self.engine.analyze_files(files)

        self.assertEqual(analysis['total_files'], 3)
        self.assertEqual(analysis['total_additions'], 170)
        self.assertEqual(analysis['total_deletions'], 35)
        self.assertTrue(analysis['has_tests'])
        self.assertTrue(analysis['has_documentation'])

    def test_analyze_diff_detects_debug_code(self):
        """Test diff analysis detects debug statements."""
        diff = """
+++ b/src/main.py
@@ -1,5 +1,6 @@
+console.log('debug');
+print('test')
"""
        analysis = self.engine.analyze_diff(diff)
        self.assertTrue(analysis['has_debug_code'])
        self.assertEqual(len(analysis['debug_occurrences']), 2)

    def test_analyze_commits(self):
        """Test commit analysis."""
        commits = [
            {'sha': 'abc123', 'commit': {'message': 'Add new feature with tests'}},
            {'sha': 'def456', 'commit': {'message': 'fix'}},
            {'sha': 'ghi789', 'commit': {'message': 'Fixes #123: Login bug'}},
        ]
        analysis = self.engine.analyze_commits(commits)

        self.assertEqual(analysis['total_commits'], 3)
        self.assertEqual(analysis['descriptive_commits'], 2)
        self.assertEqual(analysis['short_commits'], 1)
        self.assertTrue(analysis['references_issues'])

    def test_calculate_rating(self):
        """Test rating calculation."""
        self.assertEqual(self.engine.calculate_rating(95, 100), 'excellent')
        self.assertEqual(self.engine.calculate_rating(75, 100), 'good')
        self.assertEqual(self.engine.calculate_rating(55, 100), 'needs_work')
        self.assertEqual(self.engine.calculate_rating(30, 100), 'poor')


class ReviewModelTests(TestCase):
    """Tests for Review model."""

    def setUp(self):
        self.user = User.objects.create_user(
            username='instructor',
            password='testpass123'
        )
        self.repository = Repository.objects.create(
            name='owner/repo',
            owner='owner',
            repo_name='repo',
            github_url='https://github.com/owner/repo'
        )
        self.pr = PullRequest.objects.create(
            repository=self.repository,
            github_id=1,
            number=1,
            title='Test PR',
            author='testuser',
            source_branch='feature/test',
            target_branch='main',
            github_url='https://github.com/owner/repo/pull/1',
            created_at='2024-01-01T00:00:00Z',
            updated_at='2024-01-01T00:00:00Z'
        )
        self.review = Review.objects.create(
            pull_request=self.pr,
            summary='Test summary',
            score=75
        )

    def test_approve_review(self):
        """Test approving a review."""
        self.review.approve(self.user, 'Looks good!')
        self.assertEqual(self.review.status, 'approved')
        self.assertEqual(self.review.reviewed_by, self.user)
        self.assertEqual(self.review.instructor_notes, 'Looks good!')
        self.assertIsNotNone(self.review.approved_at)

    def test_reject_review(self):
        """Test rejecting a review."""
        self.review.reject(self.user, 'Needs more work')
        self.assertEqual(self.review.status, 'rejected')
        self.assertEqual(self.review.reviewed_by, self.user)

    def test_mark_posted(self):
        """Test marking review as posted."""
        self.review.mark_posted(12345)
        self.assertEqual(self.review.status, 'posted')
        self.assertEqual(self.review.github_comment_id, 12345)
        self.assertIsNotNone(self.review.posted_at)


class ViewTests(TestCase):
    """Tests for views."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.repository = Repository.objects.create(
            name='owner/repo',
            owner='owner',
            repo_name='repo',
            github_url='https://github.com/owner/repo',
            created_by=self.user
        )

    def test_dashboard_requires_login(self):
        """Test dashboard requires authentication."""
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('login', response.url)

    def test_dashboard_accessible_when_logged_in(self):
        """Test dashboard is accessible when logged in."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('dashboard'))
        self.assertEqual(response.status_code, 200)

    def test_repository_list(self):
        """Test repository list view."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('repository_list'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'owner/repo')

    def test_repository_add(self):
        """Test adding a repository."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('repository_add'))
        self.assertEqual(response.status_code, 200)


class APITests(TestCase):
    """Tests for API endpoints."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
        self.repository = Repository.objects.create(
            name='owner/repo',
            owner='owner',
            repo_name='repo',
            github_url='https://github.com/owner/repo',
            created_by=self.user
        )

    def test_api_requires_auth(self):
        """Test API endpoints require authentication."""
        response = self.client.get('/api/repositories/')
        self.assertEqual(response.status_code, 403)

    def test_api_repositories_list(self):
        """Test repositories API endpoint."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/api/repositories/')
        self.assertEqual(response.status_code, 200)

    def test_api_dashboard_stats(self):
        """Test dashboard stats API endpoint."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get('/api/dashboard/stats/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('repositories', data)
        self.assertIn('pull_requests', data)
        self.assertIn('reviews', data)
