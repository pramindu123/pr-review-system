from django.contrib import admin
from .models import Repository, BranchRule, PullRequest, Review, ReviewComment, WebhookLog


@admin.register(Repository)
class RepositoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'owner', 'repo_name', 'is_active', 'webhook_enabled', 'created_at']
    list_filter = ['is_active', 'webhook_enabled']
    search_fields = ['name', 'owner', 'repo_name']
    readonly_fields = ['created_at', 'updated_at']


@admin.register(BranchRule)
class BranchRuleAdmin(admin.ModelAdmin):
    list_display = ['name', 'branch_pattern', 'severity', 'repository', 'is_active']
    list_filter = ['severity', 'is_active', 'repository']
    search_fields = ['name', 'branch_pattern']


@admin.register(PullRequest)
class PullRequestAdmin(admin.ModelAdmin):
    list_display = ['number', 'title', 'repository', 'author', 'status', 'source_branch', 'created_at']
    list_filter = ['status', 'repository']
    search_fields = ['title', 'author', 'source_branch']
    readonly_fields = ['fetched_at']


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['id', 'pull_request', 'status', 'overall_rating', 'score', 'reviewed_by', 'created_at']
    list_filter = ['status', 'overall_rating']
    search_fields = ['pull_request__title', 'summary']
    readonly_fields = ['created_at', 'updated_at', 'approved_at', 'posted_at']


@admin.register(ReviewComment)
class ReviewCommentAdmin(admin.ModelAdmin):
    list_display = ['review', 'file_path', 'line_number', 'severity', 'category']
    list_filter = ['severity', 'category']
    search_fields = ['file_path', 'content']


@admin.register(WebhookLog)
class WebhookLogAdmin(admin.ModelAdmin):
    list_display = ['event_type', 'repository', 'processed', 'received_at', 'processed_at']
    list_filter = ['event_type', 'processed']
    readonly_fields = ['received_at', 'processed_at']
