from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class Repository(models.Model):
    name = models.CharField(max_length=255, help_text="Repository name (e.g., owner/repo)")
    owner = models.CharField(max_length=255, help_text="Repository owner/organization")
    repo_name = models.CharField(max_length=255, help_text="Repository name without owner")
    github_url = models.URLField(help_text="Full GitHub URL")
    webhook_enabled = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='repositories')

    class Meta:
        verbose_name_plural = "Repositories"
        unique_together = ['owner', 'repo_name']
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def full_name(self):
        return f"{self.owner}/{self.repo_name}"


class BranchRule(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('critical', 'Critical'),
    ]

    name = models.CharField(max_length=100, help_text="Rule name")
    branch_pattern = models.CharField(
        max_length=255, 
        help_text="Branch pattern (e.g., feature/*, bugfix/*)"
    )
    description = models.TextField(blank=True)
    expectations = models.JSONField(
        default=dict,
        help_text="JSON object with review expectations"
    )
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='medium')
    is_active = models.BooleanField(default=True)
    repository = models.ForeignKey(
        Repository, 
        on_delete=models.CASCADE, 
        null=True, 
        blank=True,
        related_name='branch_rules',
        help_text="Specific repository (leave blank for global rule)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['branch_pattern']

    def __str__(self):
        return f"{self.name} ({self.branch_pattern})"

    def get_expectations_list(self):
        return self.expectations.get('checks', [])


class PullRequest(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('closed', 'Closed'),
        ('merged', 'Merged'),
    ]

    repository = models.ForeignKey(Repository, on_delete=models.CASCADE, related_name='pull_requests')
    github_id = models.BigIntegerField(help_text="GitHub PR ID")
    number = models.IntegerField(help_text="PR number in repository")
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    author = models.CharField(max_length=255, help_text="GitHub username")
    author_avatar = models.URLField(blank=True)
    source_branch = models.CharField(max_length=255, help_text="Source/head branch")
    target_branch = models.CharField(max_length=255, help_text="Target/base branch")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    github_url = models.URLField()
    diff_url = models.URLField(blank=True)
    additions = models.IntegerField(default=0)
    deletions = models.IntegerField(default=0)
    changed_files = models.IntegerField(default=0)
    commits_count = models.IntegerField(default=0)
    created_at = models.DateTimeField()
    updated_at = models.DateTimeField()
    fetched_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['repository', 'number']
        ordering = ['-created_at']

    def __str__(self):
        return f"#{self.number} - {self.title}"

    @property
    def branch_type(self):
        if '/' in self.source_branch:
            return self.source_branch.split('/')[0]
        return 'other'


class Review(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending Approval'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('posted', 'Posted to GitHub'),
    ]

    RATING_CHOICES = [
        ('excellent', 'Excellent'),
        ('good', 'Good'),
        ('needs_work', 'Needs Work'),
        ('poor', 'Poor'),
    ]

    pull_request = models.ForeignKey(PullRequest, on_delete=models.CASCADE, related_name='reviews')
    branch_rule = models.ForeignKey(
        BranchRule, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reviews'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    overall_rating = models.CharField(max_length=20, choices=RATING_CHOICES, default='good')
    summary = models.TextField(help_text="Overall review summary")
    feedback_items = models.JSONField(
        default=list,
        help_text="List of structured feedback items"
    )
    expectations_met = models.JSONField(
        default=dict,
        help_text="Which expectations were met/not met"
    )
    score = models.IntegerField(default=0, help_text="Review score out of 100")
    reviewed_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='reviews_approved'
    )
    instructor_notes = models.TextField(blank=True, help_text="Notes from instructor")
    github_comment_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    posted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Review for {self.pull_request}"

    def approve(self, user, notes=''):
        self.status = 'approved'
        self.reviewed_by = user
        self.instructor_notes = notes
        self.approved_at = timezone.now()
        self.save()

    def reject(self, user, notes=''):
        self.status = 'rejected'
        self.reviewed_by = user
        self.instructor_notes = notes
        self.save()

    def mark_posted(self, comment_id):
        self.status = 'posted'
        self.github_comment_id = comment_id
        self.posted_at = timezone.now()
        self.save()

    def get_feedback_by_category(self):
        grouped = {}
        for item in self.feedback_items:
            category = item.get('category', 'general')
            if category not in grouped:
                grouped[category] = []
            grouped[category].append(item)
        return grouped


class ReviewComment(models.Model):
    SEVERITY_CHOICES = [
        ('info', 'Info'),
        ('suggestion', 'Suggestion'),
        ('warning', 'Warning'),
        ('error', 'Error'),
    ]

    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='comments')
    file_path = models.CharField(max_length=500)
    line_number = models.IntegerField(null=True, blank=True)
    content = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='info')
    category = models.CharField(max_length=100, default='general')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['file_path', 'line_number']

    def __str__(self):
        return f"{self.file_path}:{self.line_number} - {self.severity}"


class WebhookLog(models.Model):
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    repository = models.ForeignKey(
        Repository, 
        on_delete=models.CASCADE, 
        null=True, 
        related_name='webhook_logs'
    )
    processed = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-received_at']

    def __str__(self):
        return f"{self.event_type} at {self.received_at}"
