import requests
from django.conf import settings
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


class GitHubClient:
    BASE_URL = 'https://api.github.com'
    
    def __init__(self, token=None):
        self.token = token or settings.GITHUB_TOKEN
        self.headers = {
            'Authorization': f'token {self.token}',
            'Accept': 'application/vnd.github.v3+json',
            'X-GitHub-Api-Version': '2022-11-28'
        }
    
    def _make_request(self, method, endpoint, **kwargs):
        url = f"{self.BASE_URL}{endpoint}"
        response = requests.request(method, url, headers=self.headers, **kwargs)
        
        if response.status_code == 401:
            raise GitHubAuthError("Invalid GitHub token")
        elif response.status_code == 404:
            raise GitHubNotFoundError(f"Resource not found: {endpoint}")
        elif response.status_code == 403:
            raise GitHubRateLimitError("Rate limit exceeded or access denied")
        elif not response.ok:
            raise GitHubAPIError(f"GitHub API error: {response.status_code} - {response.text}")
        
        return response.json() if response.text else {}
    
    def get_repository(self, owner, repo):
        return self._make_request('GET', f'/repos/{owner}/{repo}')
    
    def get_pull_requests(self, owner, repo, state='open'):
        prs = []
        page = 1
        while True:
            result = self._make_request(
                'GET', 
                f'/repos/{owner}/{repo}/pulls',
                params={'state': state, 'per_page': 100, 'page': page}
            )
            if not result:
                break
            prs.extend(result)
            if len(result) < 100:
                break
            page += 1
        return prs
    
    def get_pull_request(self, owner, repo, pr_number):
        return self._make_request('GET', f'/repos/{owner}/{repo}/pulls/{pr_number}')
    
    def get_pull_request_files(self, owner, repo, pr_number):
        files = []
        page = 1
        while True:
            result = self._make_request(
                'GET',
                f'/repos/{owner}/{repo}/pulls/{pr_number}/files',
                params={'per_page': 100, 'page': page}
            )
            if not result:
                break
            files.extend(result)
            if len(result) < 100:
                break
            page += 1
        return files
    
    def get_pull_request_commits(self, owner, repo, pr_number):
        return self._make_request(
            'GET',
            f'/repos/{owner}/{repo}/pulls/{pr_number}/commits',
            params={'per_page': 100}
        )
    
    def get_pull_request_diff(self, owner, repo, pr_number):
        url = f"{self.BASE_URL}/repos/{owner}/{repo}/pulls/{pr_number}"
        headers = {**self.headers, 'Accept': 'application/vnd.github.v3.diff'}
        response = requests.get(url, headers=headers)
        return response.text
    
    def create_review_comment(self, owner, repo, pr_number, body, commit_id=None, path=None, line=None):
        data = {'body': body}
        if commit_id and path and line:
            data.update({
                'commit_id': commit_id,
                'path': path,
                'line': line
            })
        
        return self._make_request(
            'POST',
            f'/repos/{owner}/{repo}/pulls/{pr_number}/comments',
            json=data
        )
    
    def create_issue_comment(self, owner, repo, pr_number, body):
        return self._make_request(
            'POST',
            f'/repos/{owner}/{repo}/issues/{pr_number}/comments',
            json={'body': body}
        )
    
    def create_review(self, owner, repo, pr_number, body, event='COMMENT', comments=None):
        data = {
            'body': body,
            'event': event
        }
        if comments:
            data['comments'] = comments
        
        return self._make_request(
            'POST',
            f'/repos/{owner}/{repo}/pulls/{pr_number}/reviews',
            json=data
        )
    
    def get_file_content(self, owner, repo, path, ref=None):
        params = {}
        if ref:
            params['ref'] = ref
        
        result = self._make_request(
            'GET',
            f'/repos/{owner}/{repo}/contents/{path}',
            params=params
        )
        
        import base64
        if result.get('encoding') == 'base64':
            return base64.b64decode(result['content']).decode('utf-8')
        return result.get('content', '')
    
    def verify_repository_access(self, owner, repo):
        try:
            self.get_repository(owner, repo)
            return True, None
        except GitHubNotFoundError:
            return False, "Repository not found or not accessible"
        except GitHubAuthError:
            return False, "Invalid GitHub token"
        except Exception as e:
            return False, str(e)


class GitHubAPIError(Exception):
    pass


class GitHubAuthError(GitHubAPIError):
    pass


class GitHubNotFoundError(GitHubAPIError):
    pass


class GitHubRateLimitError(GitHubAPIError):
    pass


def parse_github_datetime(dt_string):
    if not dt_string:
        return None
    return datetime.fromisoformat(dt_string.replace('Z', '+00:00'))


def sync_pull_request(repository, pr_data):
    from .models import PullRequest
    
    pr, created = PullRequest.objects.update_or_create(
        repository=repository,
        number=pr_data['number'],
        defaults={
            'github_id': pr_data['id'],
            'title': pr_data['title'],
            'description': pr_data.get('body') or '',
            'author': pr_data['user']['login'],
            'author_avatar': pr_data['user'].get('avatar_url', ''),
            'source_branch': pr_data['head']['ref'],
            'target_branch': pr_data['base']['ref'],
            'status': 'merged' if pr_data.get('merged') else pr_data['state'],
            'github_url': pr_data['html_url'],
            'diff_url': pr_data.get('diff_url', ''),
            'additions': pr_data.get('additions', 0),
            'deletions': pr_data.get('deletions', 0),
            'changed_files': pr_data.get('changed_files', 0),
            'commits_count': pr_data.get('commits', 0),
            'created_at': parse_github_datetime(pr_data['created_at']),
            'updated_at': parse_github_datetime(pr_data['updated_at']),
        }
    )
    
    return pr, created
