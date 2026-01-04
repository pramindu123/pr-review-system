from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import PullRequest, Review


@receiver(post_save, sender=PullRequest)
def auto_review_new_pr(sender, instance, created, **kwargs):
    if created and instance.status == 'open':
        from .review_engine import ReviewEngine
        engine = ReviewEngine()
        engine.review_pull_request(instance)
