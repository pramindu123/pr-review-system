"""
Management command to sync pull requests from a GitHub repository.
"""

from django.core.management.base import BaseCommand, CommandError
from reviews.models import Repository
from reviews.github_client import GitHubClient, sync_pull_request, GitHubAPIError
from reviews.review_engine import ReviewEngine


class Command(BaseCommand):
    help = 'Sync pull requests from a GitHub repository'

    def add_arguments(self, parser):
        parser.add_argument('repository', type=str, help='Repository name (owner/repo)')
        parser.add_argument(
            '--state',
            type=str,
            default='open',
            choices=['open', 'closed', 'all'],
            help='PR state to sync (default: open)'
        )
        parser.add_argument(
            '--review',
            action='store_true',
            help='Generate reviews for synced PRs'
        )

    def handle(self, *args, **options):
        repo_name = options['repository']
        state = options['state']
        generate_reviews = options['review']

        # Find or create repository
        try:
            if '/' in repo_name:
                owner, name = repo_name.split('/')
                repository = Repository.objects.get(owner=owner, repo_name=name)
            else:
                repository = Repository.objects.get(name__icontains=repo_name)
        except Repository.DoesNotExist:
            raise CommandError(f'Repository "{repo_name}" not found. Add it first via the web interface.')
        except Repository.MultipleObjectsReturned:
            raise CommandError(f'Multiple repositories match "{repo_name}". Please be more specific.')

        self.stdout.write(f'Syncing PRs from {repository.name} (state: {state})...')

        client = GitHubClient()
        engine = ReviewEngine() if generate_reviews else None

        try:
            prs = client.get_pull_requests(repository.owner, repository.repo_name, state=state)
            self.stdout.write(f'Found {len(prs)} pull requests')

            synced = 0
            reviewed = 0

            for pr_data in prs:
                # Get detailed PR info
                pr_detail = client.get_pull_request(
                    repository.owner, repository.repo_name, pr_data['number']
                )
                pr, created = sync_pull_request(repository, pr_detail)
                synced += 1

                status = 'Created' if created else 'Updated'
                self.stdout.write(f'  {status}: #{pr.number} - {pr.title[:50]}')

                # Generate review if requested
                if generate_reviews and created:
                    try:
                        review = engine.review_pull_request(pr)
                        reviewed += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'    → Review generated (score: {review.score}%)')
                        )
                    except Exception as e:
                        self.stdout.write(
                            self.style.WARNING(f'    → Review failed: {e}')
                        )

            self.stdout.write(self.style.SUCCESS(
                f'\nSync complete: {synced} PRs synced, {reviewed} reviews generated'
            ))

        except GitHubAPIError as e:
            raise CommandError(f'GitHub API error: {e}')
