"""
Management command to seed default branch rules.
"""

from django.core.management.base import BaseCommand
from reviews.models import BranchRule


class Command(BaseCommand):
    help = 'Seeds the database with default branch rules'

    def handle(self, *args, **options):
        default_rules = [
            {
                'name': 'Feature Branches',
                'branch_pattern': 'feature/*',
                'description': 'Review rules for new feature development',
                'severity': 'medium',
                'expectations': {
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
                }
            },
            {
                'name': 'Bug Fix Branches',
                'branch_pattern': 'bugfix/*',
                'description': 'Review rules for bug fixes',
                'severity': 'medium',
                'expectations': {
                    'checks': [
                        {'name': 'has_regression_test', 'description': 'Bug fixes should include regression tests', 'weight': 25},
                        {'name': 'focused_changes', 'description': 'Changes should be focused on the fix', 'weight': 20},
                        {'name': 'references_issue', 'description': 'Should reference an issue or bug ID', 'weight': 15},
                        {'name': 'reasonable_size', 'description': 'Bug fixes should be small and focused', 'weight': 15},
                        {'name': 'has_description', 'description': 'PR describes the bug and fix', 'weight': 25},
                    ],
                    'max_files': 10,
                    'max_lines': 200,
                }
            },
            {
                'name': 'Hotfix Branches',
                'branch_pattern': 'hotfix/*',
                'description': 'Review rules for critical hotfixes',
                'severity': 'critical',
                'expectations': {
                    'checks': [
                        {'name': 'minimal_changes', 'description': 'Hotfixes should be minimal', 'weight': 30},
                        {'name': 'critical_only', 'description': 'Only critical changes allowed', 'weight': 25},
                        {'name': 'has_description', 'description': 'Clear description of the critical issue', 'weight': 25},
                        {'name': 'no_new_features', 'description': 'No new features in hotfixes', 'weight': 20},
                    ],
                    'max_files': 5,
                    'max_lines': 100,
                }
            },
            {
                'name': 'Release Branches',
                'branch_pattern': 'release/*',
                'description': 'Review rules for release preparation',
                'severity': 'high',
                'expectations': {
                    'checks': [
                        {'name': 'version_bump', 'description': 'Version should be updated', 'weight': 25},
                        {'name': 'changelog_updated', 'description': 'Changelog should be updated', 'weight': 25},
                        {'name': 'no_new_features', 'description': 'No new features in release branches', 'weight': 25},
                        {'name': 'documentation_updated', 'description': 'Documentation should be current', 'weight': 25},
                    ],
                    'max_files': 15,
                    'max_lines': 300,
                }
            },
            {
                'name': 'Refactoring Branches',
                'branch_pattern': 'refactor/*',
                'description': 'Review rules for code refactoring',
                'severity': 'low',
                'expectations': {
                    'checks': [
                        {'name': 'has_tests', 'description': 'Refactoring should maintain or improve tests', 'weight': 25},
                        {'name': 'no_behavior_change', 'description': 'Should not change behavior', 'weight': 25},
                        {'name': 'improves_quality', 'description': 'Should improve code quality', 'weight': 25},
                        {'name': 'has_description', 'description': 'Clear description of refactoring goals', 'weight': 25},
                    ],
                    'max_files': 30,
                    'max_lines': 1000,
                }
            },
        ]

        created_count = 0
        for rule_data in default_rules:
            rule, created = BranchRule.objects.get_or_create(
                branch_pattern=rule_data['branch_pattern'],
                repository=None,  # Global rule
                defaults=rule_data
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f'Created rule: {rule.name}'))
            else:
                self.stdout.write(f'Rule already exists: {rule.name}')

        self.stdout.write(self.style.SUCCESS(f'\nCreated {created_count} new branch rules'))
