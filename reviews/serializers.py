from rest_framework import serializers
from .models import Repository, BranchRule, PullRequest, Review, ReviewComment, WebhookLog


class RepositorySerializer(serializers.ModelSerializer):
    full_name = serializers.ReadOnlyField()
    pull_request_count = serializers.SerializerMethodField()
    
    class Meta:
        model = Repository
        fields = [
            'id', 'name', 'owner', 'repo_name', 'github_url', 
            'webhook_enabled', 'is_active', 'created_at', 'updated_at',
            'full_name', 'pull_request_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_pull_request_count(self, obj):
        return obj.pull_requests.count()
    
    def create(self, validated_data):
        if 'name' in validated_data and '/' in validated_data['name']:
            parts = validated_data['name'].split('/')
            if 'owner' not in validated_data:
                validated_data['owner'] = parts[0]
            if 'repo_name' not in validated_data:
                validated_data['repo_name'] = parts[1]
        
        validated_data['created_by'] = self.context['request'].user
        
        if 'github_url' not in validated_data:
            validated_data['github_url'] = f"https://github.com/{validated_data['owner']}/{validated_data['repo_name']}"
        
        return super().create(validated_data)


class BranchRuleSerializer(serializers.ModelSerializer):
    repository_name = serializers.SerializerMethodField()
    
    class Meta:
        model = BranchRule
        fields = [
            'id', 'name', 'branch_pattern', 'description', 
            'expectations', 'severity', 'is_active', 'repository',
            'repository_name', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
    
    def get_repository_name(self, obj):
        return obj.repository.name if obj.repository else 'Global'


class PullRequestListSerializer(serializers.ModelSerializer):
    repository_name = serializers.CharField(source='repository.name', read_only=True)
    latest_review_status = serializers.SerializerMethodField()
    latest_review_score = serializers.SerializerMethodField()
    
    class Meta:
        model = PullRequest
        fields = [
            'id', 'number', 'title', 'author', 'author_avatar',
            'source_branch', 'target_branch', 'status', 'github_url',
            'additions', 'deletions', 'changed_files', 'created_at',
            'repository_name', 'latest_review_status', 'latest_review_score'
        ]
    
    def get_latest_review_status(self, obj):
        latest = obj.reviews.first()
        return latest.status if latest else None
    
    def get_latest_review_score(self, obj):
        latest = obj.reviews.first()
        return latest.score if latest else None


class ReviewCommentSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewComment
        fields = [
            'id', 'file_path', 'line_number', 'content', 
            'severity', 'category', 'created_at'
        ]


class ReviewSerializer(serializers.ModelSerializer):
    comments = ReviewCommentSerializer(many=True, read_only=True)
    reviewed_by_name = serializers.SerializerMethodField()
    pull_request_title = serializers.CharField(source='pull_request.title', read_only=True)
    pull_request_number = serializers.IntegerField(source='pull_request.number', read_only=True)
    branch_rule_name = serializers.SerializerMethodField()
    
    class Meta:
        model = Review
        fields = [
            'id', 'pull_request', 'pull_request_title', 'pull_request_number',
            'branch_rule', 'branch_rule_name', 'status', 'overall_rating',
            'summary', 'feedback_items', 'expectations_met', 'score',
            'reviewed_by', 'reviewed_by_name', 'instructor_notes',
            'github_comment_id', 'created_at', 'updated_at', 
            'approved_at', 'posted_at', 'comments'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'approved_at', 'posted_at'
        ]
    
    def get_reviewed_by_name(self, obj):
        return obj.reviewed_by.username if obj.reviewed_by else None
    
    def get_branch_rule_name(self, obj):
        return obj.branch_rule.name if obj.branch_rule else None


class PullRequestDetailSerializer(serializers.ModelSerializer):
    repository_name = serializers.CharField(source='repository.name', read_only=True)
    reviews = ReviewSerializer(many=True, read_only=True)
    branch_type = serializers.ReadOnlyField()
    
    class Meta:
        model = PullRequest
        fields = [
            'id', 'repository', 'repository_name', 'github_id', 'number',
            'title', 'description', 'author', 'author_avatar',
            'source_branch', 'target_branch', 'branch_type', 'status',
            'github_url', 'diff_url', 'additions', 'deletions',
            'changed_files', 'commits_count', 'created_at', 'updated_at',
            'fetched_at', 'reviews'
        ]


class ReviewApprovalSerializer(serializers.Serializer):
    notes = serializers.CharField(required=False, allow_blank=True)
    post_to_github = serializers.BooleanField(default=False)


class WebhookLogSerializer(serializers.ModelSerializer):
    repository_name = serializers.SerializerMethodField()
    
    class Meta:
        model = WebhookLog
        fields = [
            'id', 'event_type', 'payload', 'repository', 
            'repository_name', 'processed', 'error_message',
            'received_at', 'processed_at'
        ]
    
    def get_repository_name(self, obj):
        return obj.repository.name if obj.repository else None


class SyncRepositorySerializer(serializers.Serializer):
    state = serializers.ChoiceField(
        choices=['open', 'closed', 'all'],
        default='open'
    )
