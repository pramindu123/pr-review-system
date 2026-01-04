from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator

from .models import Repository, BranchRule, PullRequest, Review
from .github_client import GitHubClient, GitHubAPIError, sync_pull_request
from .review_engine import ReviewEngine


@login_required
def dashboard(request):
    context = {
        'repositories': Repository.objects.filter(is_active=True)[:5],
        'pending_reviews': Review.objects.filter(status='pending').select_related('pull_request', 'pull_request__repository')[:10],
        'recent_prs': PullRequest.objects.filter(status='open').select_related('repository')[:10],
        'stats': {
            'repositories': Repository.objects.filter(is_active=True).count(),
            'open_prs': PullRequest.objects.filter(status='open').count(),
            'pending_reviews': Review.objects.filter(status='pending').count(),
            'approved_reviews': Review.objects.filter(status='approved').count(),
        }
    }
    return render(request, 'reviews/dashboard.html', context)


@login_required
def repository_list(request):
    repositories = Repository.objects.all().order_by('-created_at')
    paginator = Paginator(repositories, 20)
    page = request.GET.get('page')
    repositories = paginator.get_page(page)
    
    return render(request, 'reviews/repository_list.html', {
        'repositories': repositories
    })


@login_required
def repository_detail(request, pk):
    repository = get_object_or_404(Repository, pk=pk)
    pull_requests = repository.pull_requests.all().order_by('-created_at')
    
    open_prs_count = repository.pull_requests.filter(status='open').count()
    pending_reviews_count = Review.objects.filter(
        pull_request__repository=repository, 
        status='pending'
    ).count()
    
    status_filter = request.GET.get('status')
    if status_filter:
        pull_requests = pull_requests.filter(status=status_filter)
    
    paginator = Paginator(pull_requests, 20)
    page = request.GET.get('page')
    pull_requests = paginator.get_page(page)
    
    return render(request, 'reviews/repository_detail.html', {
        'repository': repository,
        'pull_requests': pull_requests,
        'branch_rules': repository.branch_rules.all(),
        'open_prs_count': open_prs_count,
        'pending_reviews_count': pending_reviews_count,
    })


@login_required
def repository_add(request):
    if request.method == 'POST':
        repo_name = request.POST.get('repo_name', '').strip()
        
        if '/' not in repo_name:
            messages.error(request, 'Please enter repository in format: owner/repo-name')
            return redirect('repository_add')
        
        parts = repo_name.split('/')
        owner = parts[0]
        name = parts[1]
        
        if Repository.objects.filter(owner=owner, repo_name=name).exists():
            messages.error(request, 'Repository already added')
            return redirect('repository_list')
        
        client = GitHubClient()
        success, error = client.verify_repository_access(owner, name)
        
        if not success:
            messages.error(request, f'Cannot access repository: {error}')
            return redirect('repository_add')
        
        repository = Repository.objects.create(
            name=repo_name,
            owner=owner,
            repo_name=name,
            github_url=f'https://github.com/{repo_name}',
            created_by=request.user
        )
        
        messages.success(request, f'Repository {repo_name} added successfully')
        return redirect('repository_detail', pk=repository.pk)
    
    return render(request, 'reviews/repository_add.html')


@login_required
@require_POST
def repository_sync(request, pk):
    repository = get_object_or_404(Repository, pk=pk)
    state = request.POST.get('state', 'open')
    
    try:
        client = GitHubClient()
        prs = client.get_pull_requests(repository.owner, repository.repo_name, state=state)
        
        synced = 0
        for pr_data in prs:
            pr_detail = client.get_pull_request(
                repository.owner, repository.repo_name, pr_data['number']
            )
            sync_pull_request(repository, pr_detail)
            synced += 1
        
        messages.success(request, f'Synced {synced} pull requests')
    except GitHubAPIError as e:
        messages.error(request, f'GitHub API error: {e}')
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.exception(f'Error syncing repository {repository.name}')
        messages.error(request, f'Error syncing: {str(e)}')
    
    return redirect('repository_detail', pk=pk)


@login_required
@require_POST
def repository_delete(request, pk):
    repository = get_object_or_404(Repository, pk=pk)
    repo_name = repository.name
    repository.delete()
    messages.success(request, f'Repository {repo_name} deleted')
    return redirect('repository_list')


@login_required
@require_POST
def repository_toggle_webhook(request, pk):
    repository = get_object_or_404(Repository, pk=pk)
    repository.webhook_enabled = not repository.webhook_enabled
    repository.save()
    status = 'enabled' if repository.webhook_enabled else 'disabled'
    messages.success(request, f'Webhook {status} for {repository.name}')
    return redirect('repository_detail', pk=pk)


@login_required
def pull_request_list(request):
    pull_requests = PullRequest.objects.all().select_related('repository').order_by('-created_at')
    status_filter = request.GET.get('status')
    if status_filter:
        pull_requests = pull_requests.filter(status=status_filter)
    
    repo_filter = request.GET.get('repository')
    if repo_filter:
        pull_requests = pull_requests.filter(repository_id=repo_filter)
    
    review_filter = request.GET.get('review_status')
    if review_filter:
        pull_requests = pull_requests.filter(reviews__status=review_filter).distinct()
    
    paginator = Paginator(pull_requests, 20)
    page = request.GET.get('page')
    pull_requests = paginator.get_page(page)
    
    return render(request, 'reviews/pull_request_list.html', {
        'pull_requests': pull_requests,
        'repositories': Repository.objects.filter(is_active=True),
    })


@login_required
def pull_request_detail(request, pk):
    pull_request = get_object_or_404(
        PullRequest.objects.select_related('repository'),
        pk=pk
    )
    reviews = pull_request.reviews.all().order_by('-created_at')
    
    return render(request, 'reviews/pull_request_detail.html', {
        'pull_request': pull_request,
        'reviews': reviews,
    })


@login_required
@require_POST
def pull_request_review(request, pk):
    pull_request = get_object_or_404(PullRequest, pk=pk)
    
    try:
        engine = ReviewEngine()
        review = engine.review_pull_request(pull_request)
        messages.success(request, 'Review generated successfully')
    except Exception as e:
        messages.error(request, f'Error generating review: {e}')
    
    return redirect('pull_request_detail', pk=pk)


@login_required
def review_list(request):
    reviews = Review.objects.all().select_related(
        'pull_request', 'pull_request__repository', 'reviewed_by'
    ).order_by('-created_at')
    
    status_filter = request.GET.get('status')
    if status_filter:
        reviews = reviews.filter(status=status_filter)
    
    repo_filter = request.GET.get('repository')
    if repo_filter:
        reviews = reviews.filter(pull_request__repository_id=repo_filter)
    
    paginator = Paginator(reviews, 20)
    page = request.GET.get('page')
    reviews = paginator.get_page(page)
    
    return render(request, 'reviews/review_list.html', {
        'reviews': reviews,
        'repositories': Repository.objects.filter(is_active=True),
    })


@login_required
def review_detail(request, pk):
    review = get_object_or_404(
        Review.objects.select_related('pull_request', 'pull_request__repository', 'branch_rule'),
        pk=pk
    )
    comments = review.comments.all()
    
    return render(request, 'reviews/review_detail.html', {
        'review': review,
        'comments': comments,
    })


@login_required
@require_POST
def review_approve(request, pk):
    review = get_object_or_404(Review, pk=pk)
    notes = request.POST.get('notes', '')
    post_to_github = request.POST.get('post_to_github') == 'on'
    
    review.approve(request.user, notes)
    messages.success(request, 'Review approved')
    
    if post_to_github:
        try:
            client = GitHubClient()
            pr = review.pull_request
            repo = pr.repository
            
            result = client.create_issue_comment(
                repo.owner, repo.repo_name, pr.number, review.summary
            )
            review.mark_posted(result.get('id'))
            messages.success(request, 'Review posted to GitHub')
        except GitHubAPIError as e:
            messages.error(request, f'Failed to post to GitHub: {e}')
    
    return redirect('review_detail', pk=pk)


@login_required
@require_POST
def review_reject(request, pk):
    review = get_object_or_404(Review, pk=pk)
    notes = request.POST.get('notes', '')
    
    review.reject(request.user, notes)
    messages.success(request, 'Review rejected')
    
    return redirect('review_detail', pk=pk)


@login_required
@require_POST
def review_post_to_github(request, pk):
    review = get_object_or_404(Review, pk=pk)
    
    if review.status != 'approved':
        messages.error(request, 'Review must be approved first')
        return redirect('review_detail', pk=pk)
    
    try:
        client = GitHubClient()
        pr = review.pull_request
        repo = pr.repository
        
        result = client.create_issue_comment(
            repo.owner, repo.repo_name, pr.number, review.summary
        )
        review.mark_posted(result.get('id'))
        messages.success(request, 'Review posted to GitHub')
    except GitHubAPIError as e:
        messages.error(request, f'Failed to post: {e}')
    
    return redirect('review_detail', pk=pk)


@login_required
def branch_rule_list(request):
    rules = BranchRule.objects.all().select_related('repository').order_by('branch_pattern')
    
    return render(request, 'reviews/branch_rule_list.html', {
        'rules': rules,
    })


@login_required
def branch_rule_add(request):
    if request.method == 'POST':
        name = request.POST.get('name')
        branch_pattern = request.POST.get('branch_pattern')
        description = request.POST.get('description', '')
        severity = request.POST.get('severity', 'medium')
        repository_id = request.POST.get('repository')
        
        checks = []
        check_names = request.POST.getlist('check_name[]')
        check_descriptions = request.POST.getlist('check_description[]')
        check_weights = request.POST.getlist('check_weight[]')
        
        for i, check_name in enumerate(check_names):
            if check_name:
                checks.append({
                    'name': check_name,
                    'description': check_descriptions[i] if i < len(check_descriptions) else '',
                    'weight': int(check_weights[i]) if i < len(check_weights) else 10
                })
        
        expectations = {'checks': checks}
        
        repository = None
        if repository_id:
            repository = get_object_or_404(Repository, pk=repository_id)
        
        BranchRule.objects.create(
            name=name,
            branch_pattern=branch_pattern,
            description=description,
            expectations=expectations,
            severity=severity,
            repository=repository
        )
        
        messages.success(request, 'Branch rule created')
        return redirect('branch_rule_list')
    
    return render(request, 'reviews/branch_rule_add.html', {
        'repositories': Repository.objects.filter(is_active=True),
        'default_checks': [
            {'name': 'has_tests', 'description': 'Includes test files'},
            {'name': 'has_documentation', 'description': 'Includes documentation updates'},
            {'name': 'reasonable_size', 'description': 'PR is reasonably sized'},
            {'name': 'descriptive_commits', 'description': 'Commit messages are descriptive'},
            {'name': 'no_debug_code', 'description': 'No debug code'},
            {'name': 'has_description', 'description': 'PR has a description'},
            {'name': 'references_issue', 'description': 'References an issue'},
        ]
    })


@login_required
@require_POST
def branch_rule_delete(request, pk):
    rule = get_object_or_404(BranchRule, pk=pk)
    rule.delete()
    messages.success(request, 'Branch rule deleted')
    return redirect('branch_rule_list')


@login_required
def pending_approvals(request):
    reviews = Review.objects.filter(status='pending').select_related(
        'pull_request', 'pull_request__repository'
    ).order_by('-created_at')
    
    paginator = Paginator(reviews, 20)
    page = request.GET.get('page')
    reviews = paginator.get_page(page)
    
    return render(request, 'reviews/pending_approvals.html', {
        'reviews': reviews,
    })
