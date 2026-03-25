from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import SiteSetup, UserProfile

User = get_user_model()


@receiver(post_migrate)
def create_default_site_setup(sender, **kwargs):
    if not SiteSetup.objects.exists():
        SiteSetup.objects.create(name='Обменник')


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)
