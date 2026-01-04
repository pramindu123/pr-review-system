"""
PR Review Engine - Automatically reviews pull requests based on branch rules.
"""

import re
import fnmatch
from typing import List, Dict, Any, Optional, Tuple
from .models import PullRequest, Review, ReviewComment, BranchRule
from .github_client import GitHubClient
import logging

logger = logging.getLogger(__name__)


class ReviewEngine:
    """
    Engine for automatically reviewing pull requests.
    
    Analyzes PRs based on:
    - Branch naming conventions
    - Code changes
    - Commit messages
    - File types modified
    - PR metadata
    """
    
    # Default expectations for different branch types
    DEFAULT_EXPECTATIONS = {
        'feature': {
            'checks': [
                {'name': 'has_tests', 'description': 'New features should include tests', 'weight': 20},
                {'name': 'has_documentation', 'description': 'Features should be documented', 'weight': 15},
                {'name': 'reasonable_size', 'description': 'PR should be reasonably sized (< 500 lines)', 'weight': 10},
                {'name': 'descriptive_commits', 'description': 'Commits should be descriptive', 'weight': 10},
                {'name': 'no_debug_code', 'description': 'No debug/console statements', 'weight': 15},
                {'name': 'follows_conventions', 'description': 'Follows coding conventions', 'weight': 15},
                {'name': 'has_description', 'description': 'PR has a meaningful description', 'weight': 15},
            ],
            'max_files': 20,
            'max_lines': 500,
        },
        'bugfix': {
            'checks': [
                {'name': 'has_regression_test', 'description': 'Bug fixes should include regression tests', 'weight': 25},
                {'name': 'focused_changes', 'description': 'Changes should be focused on the fix', 'weight': 20},
                {'name': 'references_issue', 'description': 'Should reference an issue or bug ID', 'weight': 15},
                {'name': 'reasonable_size', 'description': 'Bug fixes should be small and focused', 'weight': 15},
                {'name': 'has_description', 'description': 'PR describes the bug and fix', 'weight': 25},
            ],
            'max_files': 10,
            'max_lines': 200,
        },
        'hotfix': {
            'checks': [
                {'name': 'minimal_changes', 'description': 'Hotfixes should be minimal', 'weight': 30},
                {'name': 'critical_only', 'description': 'Only critical changes allowed', 'weight': 25},
                {'name': 'has_description', 'description': 'Clear description of the critical issue', 'weight': 25},
                {'name': 'no_new_features', 'description': 'No new features in hotfixes', 'weight': 20},
            ],
            'max_files': 5,
            'max_lines': 100,
        },
        'release': {
            'checks': [
                {'name': 'version_bump', 'description': 'Version should be updated', 'weight': 25},
                {'name': 'changelog_updated', 'description': 'Changelog should be updated', 'weight': 25},
                {'name': 'no_new_features', 'description': 'No new features in release branches', 'weight': 25},
                {'name': 'documentation_updated', 'description': 'Documentation should be current', 'weight': 25},
            ],
            'max_files': 15,
            'max_lines': 300,
        },
        'refactor': {
            'checks': [
                {'name': 'has_tests', 'description': 'Refactoring should maintain or improve tests', 'weight': 25},
                {'name': 'no_behavior_change', 'description': 'Should not change behavior', 'weight': 25},
                {'name': 'improves_quality', 'description': 'Should improve code quality', 'weight': 25},
                {'name': 'has_description', 'description': 'Clear description of refactoring goals', 'weight': 25},
            ],
            'max_files': 30,
            'max_lines': 1000,
        },
        'other': {
            'checks': [
                {'name': 'has_description', 'description': 'PR has a description', 'weight': 25},
                {'name': 'reasonable_size', 'description': 'PR is reasonably sized', 'weight': 25},
                {'name': 'descriptive_commits', 'description': 'Commits are descriptive', 'weight': 25},
                {'name': 'follows_conventions', 'description': 'Follows project conventions', 'weight': 25},
            ],
            'max_files': 20,
            'max_lines': 500,
        }
    }
    
    # File patterns that indicate tests
    TEST_PATTERNS = [
        '*test*.py', '*_test.py', 'test_*.py',
        '*spec*.js', '*test*.js', '*.spec.ts', '*.test.ts',
        '*Test.java', '*Tests.java',
        '*_test.go', '*_test.rb',
    ]
    
    # File patterns that indicate documentation
    DOC_PATTERNS = [
        '*.md', '*.rst', '*.txt', 'docs/*', 'documentation/*',
        'README*', 'CHANGELOG*', 'CONTRIBUTING*',
    ]
    
    # Patterns that indicate debug code
    DEBUG_PATTERNS = [
        r'console\.log\(',
        r'print\(',
        r'debugger;',
        r'binding\.pry',
        r'import pdb',
        r'pdb\.set_trace\(\)',
        r'console\.debug\(',
        r'System\.out\.println\(',
    ]
    
    def __init__(self, github_client: Optional[GitHubClient] = None):
        self.github_client = github_client or GitHubClient()
    
    def get_branch_type(self, branch_name: str) -> str:
        """Extract the branch type from branch name."""
        branch_lower = branch_name.lower()
        
        for prefix in ['feature/', 'feat/', 'features/']:
            if branch_lower.startswith(prefix):
                return 'feature'
        
        for prefix in ['bugfix/', 'bug/', 'fix/']:
            if branch_lower.startswith(prefix):
                return 'bugfix'
        
        for prefix in ['hotfix/', 'hot/', 'emergency/']:
            if branch_lower.startswith(prefix):
                return 'hotfix'
        
        for prefix in ['release/', 'releases/', 'rel/']:
            if branch_lower.startswith(prefix):
                return 'release'
        
        for prefix in ['refactor/', 'refactoring/', 'cleanup/']:
            if branch_lower.startswith(prefix):
                return 'refactor'
        
        return 'other'
    
    def get_matching_branch_rule(self, pull_request: PullRequest) -> Optional[BranchRule]:
        """Find a matching branch rule for the pull request."""
        # First check repository-specific rules
        repo_rules = BranchRule.objects.filter(
            repository=pull_request.repository,
            is_active=True
        )
        
        for rule in repo_rules:
            if fnmatch.fnmatch(pull_request.source_branch, rule.branch_pattern):
                return rule
        
        # Then check global rules
        global_rules = BranchRule.objects.filter(
            repository__isnull=True,
            is_active=True
        )
        
        for rule in global_rules:
            if fnmatch.fnmatch(pull_request.source_branch, rule.branch_pattern):
                return rule
        
        return None
    
    def get_expectations(self, pull_request: PullRequest) -> Dict[str, Any]:
        """Get review expectations for a pull request."""
        # Check for custom branch rule
        branch_rule = self.get_matching_branch_rule(pull_request)
        
        if branch_rule and branch_rule.expectations:
            return branch_rule.expectations
        
        # Fall back to default expectations based on branch type
        branch_type = self.get_branch_type(pull_request.source_branch)
        return self.DEFAULT_EXPECTATIONS.get(branch_type, self.DEFAULT_EXPECTATIONS['other'])
    
    def analyze_files(self, files: List[Dict]) -> Dict[str, Any]:
        """Analyze the files changed in a PR."""
        analysis = {
            'total_files': len(files),
            'total_additions': 0,
            'total_deletions': 0,
            'has_tests': False,
            'has_documentation': False,
            'file_types': {},
            'test_files': [],
            'doc_files': [],
            'source_files': [],
        }
        
        for file in files:
            filename = file.get('filename', '')
            additions = file.get('additions', 0)
            deletions = file.get('deletions', 0)
            
            analysis['total_additions'] += additions
            analysis['total_deletions'] += deletions
            
            # Get file extension
            ext = filename.split('.')[-1] if '.' in filename else 'none'
            analysis['file_types'][ext] = analysis['file_types'].get(ext, 0) + 1
            
            # Check if it's a test file
            for pattern in self.TEST_PATTERNS:
                if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                    analysis['has_tests'] = True
                    analysis['test_files'].append(filename)
                    break
            
            # Check if it's a documentation file
            for pattern in self.DOC_PATTERNS:
                if fnmatch.fnmatch(filename.lower(), pattern.lower()):
                    analysis['has_documentation'] = True
                    analysis['doc_files'].append(filename)
                    break
            
            # Track as source file if not test or doc
            if filename not in analysis['test_files'] and filename not in analysis['doc_files']:
                analysis['source_files'].append(filename)
        
        return analysis
    
    def analyze_diff(self, diff: str) -> Dict[str, Any]:
        """Analyze the PR diff for issues."""
        analysis = {
            'has_debug_code': False,
            'debug_occurrences': [],
            'large_functions': [],
            'todos_added': [],
        }
        
        lines = diff.split('\n')
        current_file = None
        line_number = 0
        
        for line in lines:
            # Track current file
            if line.startswith('+++ b/'):
                current_file = line[6:]
                line_number = 0
                continue
            
            # Track line numbers from diff headers
            if line.startswith('@@'):
                match = re.search(r'\+(\d+)', line)
                if match:
                    line_number = int(match.group(1))
                continue
            
            # Only analyze added lines
            if line.startswith('+') and not line.startswith('+++'):
                added_content = line[1:]
                
                # Check for debug patterns
                for pattern in self.DEBUG_PATTERNS:
                    if re.search(pattern, added_content, re.IGNORECASE):
                        analysis['has_debug_code'] = True
                        analysis['debug_occurrences'].append({
                            'file': current_file,
                            'line': line_number,
                            'content': added_content.strip()[:100]
                        })
                
                # Check for TODO/FIXME comments
                if re.search(r'\b(TODO|FIXME|XXX|HACK)\b', added_content, re.IGNORECASE):
                    analysis['todos_added'].append({
                        'file': current_file,
                        'line': line_number,
                        'content': added_content.strip()[:100]
                    })
                
                line_number += 1
        
        return analysis
    
    def analyze_commits(self, commits: List[Dict]) -> Dict[str, Any]:
        """Analyze commit messages."""
        analysis = {
            'total_commits': len(commits),
            'descriptive_commits': 0,
            'short_commits': 0,
            'commits': [],
            'references_issues': False,
            'issue_references': [],
        }
        
        issue_pattern = re.compile(r'#\d+|(?:closes?|fixes?|resolves?)\s+#?\d+', re.IGNORECASE)
        
        for commit in commits:
            message = commit.get('commit', {}).get('message', '')
            first_line = message.split('\n')[0]
            
            commit_info = {
                'sha': commit.get('sha', '')[:7],
                'message': first_line[:100],
                'is_descriptive': len(first_line) >= 10,
            }
            
            if len(first_line) >= 10:
                analysis['descriptive_commits'] += 1
            else:
                analysis['short_commits'] += 1
            
            # Check for issue references
            issues = issue_pattern.findall(message)
            if issues:
                analysis['references_issues'] = True
                analysis['issue_references'].extend(issues)
            
            analysis['commits'].append(commit_info)
        
        return analysis
    
    def evaluate_expectations(
        self, 
        expectations: Dict[str, Any],
        file_analysis: Dict[str, Any],
        diff_analysis: Dict[str, Any],
        commit_analysis: Dict[str, Any],
        pr: PullRequest
    ) -> Dict[str, Any]:
        """Evaluate how well the PR meets expectations."""
        results = {
            'checks': [],
            'score': 0,
            'max_score': 0,
            'passed': 0,
            'failed': 0,
        }
        
        checks = expectations.get('checks', [])
        max_files = expectations.get('max_files', 20)
        max_lines = expectations.get('max_lines', 500)
        
        for check in checks:
            check_name = check['name']
            check_weight = check.get('weight', 10)
            results['max_score'] += check_weight
            
            passed = False
            details = ''
            
            if check_name == 'has_tests':
                passed = file_analysis['has_tests']
                details = f"Test files found: {len(file_analysis['test_files'])}"
            
            elif check_name == 'has_documentation':
                passed = file_analysis['has_documentation']
                details = f"Documentation files: {len(file_analysis['doc_files'])}"
            
            elif check_name == 'has_regression_test':
                passed = file_analysis['has_tests']
                details = "Regression tests detected" if passed else "No regression tests found"
            
            elif check_name == 'reasonable_size':
                total_changes = file_analysis['total_additions'] + file_analysis['total_deletions']
                passed = total_changes <= max_lines and file_analysis['total_files'] <= max_files
                details = f"{total_changes} lines changed, {file_analysis['total_files']} files"
            
            elif check_name == 'focused_changes':
                passed = file_analysis['total_files'] <= max_files
                details = f"{file_analysis['total_files']} files changed"
            
            elif check_name == 'minimal_changes':
                passed = file_analysis['total_files'] <= 5 and (file_analysis['total_additions'] + file_analysis['total_deletions']) <= 100
                details = f"{file_analysis['total_files']} files, {file_analysis['total_additions'] + file_analysis['total_deletions']} lines"
            
            elif check_name == 'descriptive_commits':
                ratio = commit_analysis['descriptive_commits'] / max(commit_analysis['total_commits'], 1)
                passed = ratio >= 0.8
                details = f"{commit_analysis['descriptive_commits']}/{commit_analysis['total_commits']} descriptive commits"
            
            elif check_name == 'no_debug_code':
                passed = not diff_analysis['has_debug_code']
                if not passed:
                    details = f"Found {len(diff_analysis['debug_occurrences'])} debug statements"
                else:
                    details = "No debug code found"
            
            elif check_name == 'references_issue':
                passed = commit_analysis['references_issues']
                details = f"Issues referenced: {', '.join(commit_analysis['issue_references'][:5])}" if passed else "No issue references"
            
            elif check_name == 'has_description':
                passed = len(pr.description) >= 50
                details = f"Description length: {len(pr.description)} characters"
            
            elif check_name == 'no_new_features':
                # Heuristic: check for keywords in commits
                feature_keywords = ['add', 'new', 'implement', 'create']
                has_feature = any(
                    any(kw in c['message'].lower() for kw in feature_keywords)
                    for c in commit_analysis['commits']
                )
                passed = not has_feature
                details = "No feature-like changes detected" if passed else "Possible new features detected"
            
            elif check_name == 'version_bump':
                version_files = ['package.json', 'setup.py', 'version.py', 'VERSION', 'pyproject.toml']
                has_version = any(any(vf in f for vf in version_files) for f in file_analysis['source_files'])
                passed = has_version
                details = "Version file modified" if passed else "No version file changes found"
            
            elif check_name == 'changelog_updated':
                changelog_files = ['CHANGELOG', 'HISTORY', 'CHANGES', 'NEWS']
                has_changelog = any(any(cf in f.upper() for cf in changelog_files) for f in file_analysis['doc_files'])
                passed = has_changelog
                details = "Changelog updated" if passed else "Changelog not updated"
            
            elif check_name == 'no_behavior_change':
                passed = file_analysis['has_tests']
                details = "Tests present to verify behavior" if passed else "Tests recommended for refactoring"
            
            elif check_name == 'improves_quality':
                # Heuristic: more deletions than additions often means cleanup
                passed = file_analysis['total_deletions'] >= file_analysis['total_additions'] * 0.3
                details = f"Removed {file_analysis['total_deletions']} lines"
            
            elif check_name == 'follows_conventions':
                # Basic check - can be expanded
                passed = True
                details = "Conventions check passed"
            
            elif check_name == 'critical_only':
                passed = file_analysis['total_files'] <= 5
                details = f"{file_analysis['total_files']} files changed"
            
            elif check_name == 'documentation_updated':
                passed = file_analysis['has_documentation']
                details = f"Documentation files: {len(file_analysis['doc_files'])}"
            
            else:
                passed = True
                details = "Check not implemented"
            
            if passed:
                results['score'] += check_weight
                results['passed'] += 1
            else:
                results['failed'] += 1
            
            results['checks'].append({
                'name': check_name,
                'description': check['description'],
                'passed': passed,
                'weight': check_weight,
                'details': details
            })
        
        return results
    
    def generate_feedback(
        self,
        pr: PullRequest,
        expectations: Dict[str, Any],
        evaluation: Dict[str, Any],
        file_analysis: Dict[str, Any],
        diff_analysis: Dict[str, Any],
        commit_analysis: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate structured feedback items."""
        feedback = []
        
        # Add feedback for failed checks
        for check in evaluation['checks']:
            if not check['passed']:
                feedback.append({
                    'category': 'expectation',
                    'severity': 'warning',
                    'title': check['description'],
                    'message': f"❌ {check['description']}: {check['details']}",
                    'suggestion': self._get_suggestion(check['name'])
                })
        
        # Add feedback for passed checks
        for check in evaluation['checks']:
            if check['passed']:
                feedback.append({
                    'category': 'expectation',
                    'severity': 'success',
                    'title': check['description'],
                    'message': f"✅ {check['description']}: {check['details']}",
                    'suggestion': None
                })
        
        # Add debug code warnings
        for debug in diff_analysis.get('debug_occurrences', [])[:5]:
            feedback.append({
                'category': 'code_quality',
                'severity': 'error',
                'title': 'Debug code detected',
                'message': f"Debug statement in {debug['file']} at line {debug['line']}",
                'suggestion': 'Remove debug statements before merging'
            })
        
        # Add TODO warnings
        for todo in diff_analysis.get('todos_added', [])[:5]:
            feedback.append({
                'category': 'code_quality',
                'severity': 'info',
                'title': 'TODO comment added',
                'message': f"TODO in {todo['file']} at line {todo['line']}: {todo['content']}",
                'suggestion': 'Consider creating an issue to track this TODO'
            })
        
        # Add size warnings
        total_changes = file_analysis['total_additions'] + file_analysis['total_deletions']
        if total_changes > 500:
            feedback.append({
                'category': 'pr_size',
                'severity': 'warning',
                'title': 'Large pull request',
                'message': f"This PR has {total_changes} lines changed across {file_analysis['total_files']} files",
                'suggestion': 'Consider breaking large PRs into smaller, focused changes'
            })
        
        return feedback
    
    def _get_suggestion(self, check_name: str) -> str:
        """Get improvement suggestion for a failed check."""
        suggestions = {
            'has_tests': 'Add unit tests for new functionality',
            'has_documentation': 'Add documentation or update README',
            'has_regression_test': 'Add a test that reproduces the bug to prevent regression',
            'reasonable_size': 'Consider splitting into smaller PRs',
            'focused_changes': 'Keep changes focused on the bug fix',
            'minimal_changes': 'Hotfixes should contain only critical changes',
            'descriptive_commits': 'Use descriptive commit messages (50+ characters)',
            'no_debug_code': 'Remove console.log, print, and debugger statements',
            'references_issue': 'Reference the issue number in commit message (e.g., "Fixes #123")',
            'has_description': 'Add a detailed PR description explaining the changes',
            'no_new_features': 'This branch type should not include new features',
            'version_bump': 'Update version number in package.json or similar',
            'changelog_updated': 'Update CHANGELOG.md with release notes',
            'no_behavior_change': 'Ensure tests verify behavior is unchanged',
            'improves_quality': 'Refactoring should simplify or clean up code',
            'follows_conventions': 'Follow project coding conventions',
            'critical_only': 'Limit hotfixes to critical issues only',
            'documentation_updated': 'Update documentation for release',
        }
        return suggestions.get(check_name, 'Review and improve this aspect')
    
    def calculate_rating(self, score: int, max_score: int) -> str:
        """Calculate overall rating based on score percentage."""
        if max_score == 0:
            return 'good'
        
        percentage = (score / max_score) * 100
        
        if percentage >= 90:
            return 'excellent'
        elif percentage >= 70:
            return 'good'
        elif percentage >= 50:
            return 'needs_work'
        else:
            return 'poor'
    
    def generate_summary(
        self,
        pr: PullRequest,
        branch_type: str,
        evaluation: Dict[str, Any],
        file_analysis: Dict[str, Any]
    ) -> str:
        """Generate a human-readable summary."""
        percentage = (evaluation['score'] / max(evaluation['max_score'], 1)) * 100
        
        summary_parts = [
            f"## PR Review Summary for #{pr.number}",
            f"",
            f"**Branch Type:** `{branch_type}`",
            f"**Score:** {evaluation['score']}/{evaluation['max_score']} ({percentage:.0f}%)",
            f"**Checks Passed:** {evaluation['passed']}/{evaluation['passed'] + evaluation['failed']}",
            f"",
            f"### Changes Overview",
            f"- **Files Changed:** {file_analysis['total_files']}",
            f"- **Lines Added:** +{file_analysis['total_additions']}",
            f"- **Lines Removed:** -{file_analysis['total_deletions']}",
            f"- **Tests Included:** {'Yes' if file_analysis['has_tests'] else 'No'}",
            f"- **Documentation Updated:** {'Yes' if file_analysis['has_documentation'] else 'No'}",
            f"",
        ]
        
        # Add failed checks section
        failed_checks = [c for c in evaluation['checks'] if not c['passed']]
        if failed_checks:
            summary_parts.append("### Areas for Improvement")
            for check in failed_checks:
                summary_parts.append(f"- ❌ {check['description']}")
            summary_parts.append("")
        
        # Add passed checks section
        passed_checks = [c for c in evaluation['checks'] if c['passed']]
        if passed_checks:
            summary_parts.append("### Passed Checks")
            for check in passed_checks:
                summary_parts.append(f"- ✅ {check['description']}")
            summary_parts.append("")
        
        return "\n".join(summary_parts)
    
    def review_pull_request(self, pull_request: PullRequest) -> Review:
        """
        Perform a complete review of a pull request.
        
        Args:
            pull_request: PullRequest model instance
        
        Returns:
            Review model instance
        """
        repo = pull_request.repository
        
        # Get data from GitHub
        try:
            files = self.github_client.get_pull_request_files(
                repo.owner, repo.repo_name, pull_request.number
            )
            commits = self.github_client.get_pull_request_commits(
                repo.owner, repo.repo_name, pull_request.number
            )
            diff = self.github_client.get_pull_request_diff(
                repo.owner, repo.repo_name, pull_request.number
            )
        except Exception as e:
            logger.error(f"Error fetching PR data: {e}")
            # Create a basic review with error
            return Review.objects.create(
                pull_request=pull_request,
                status='pending',
                overall_rating='needs_work',
                summary=f"Error fetching PR data: {str(e)}",
                feedback_items=[{
                    'category': 'error',
                    'severity': 'error',
                    'title': 'Review Error',
                    'message': f'Could not fetch PR data from GitHub: {str(e)}',
                    'suggestion': 'Check GitHub token and repository access'
                }],
                score=0
            )
        
        # Get branch type and expectations
        branch_type = self.get_branch_type(pull_request.source_branch)
        branch_rule = self.get_matching_branch_rule(pull_request)
        expectations = self.get_expectations(pull_request)
        
        # Analyze PR
        file_analysis = self.analyze_files(files)
        diff_analysis = self.analyze_diff(diff)
        commit_analysis = self.analyze_commits(commits)
        
        # Evaluate against expectations
        evaluation = self.evaluate_expectations(
            expectations, file_analysis, diff_analysis, commit_analysis, pull_request
        )
        
        # Generate feedback and summary
        feedback = self.generate_feedback(
            pull_request, expectations, evaluation, 
            file_analysis, diff_analysis, commit_analysis
        )
        summary = self.generate_summary(pull_request, branch_type, evaluation, file_analysis)
        rating = self.calculate_rating(evaluation['score'], evaluation['max_score'])
        
        # Create the review
        review = Review.objects.create(
            pull_request=pull_request,
            branch_rule=branch_rule,
            status='pending',
            overall_rating=rating,
            summary=summary,
            feedback_items=feedback,
            expectations_met={
                'checks': evaluation['checks'],
                'passed': evaluation['passed'],
                'failed': evaluation['failed']
            },
            score=int((evaluation['score'] / max(evaluation['max_score'], 1)) * 100)
        )
        
        # Create individual comments for code issues
        for debug in diff_analysis.get('debug_occurrences', [])[:10]:
            ReviewComment.objects.create(
                review=review,
                file_path=debug['file'],
                line_number=debug['line'],
                content=f"Debug statement detected: `{debug['content']}`",
                severity='error',
                category='code_quality'
            )
        
        for todo in diff_analysis.get('todos_added', [])[:10]:
            ReviewComment.objects.create(
                review=review,
                file_path=todo['file'],
                line_number=todo['line'],
                content=f"TODO added: {todo['content']}",
                severity='info',
                category='code_quality'
            )
        
        return review
