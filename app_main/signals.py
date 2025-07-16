from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .models import SiteSetup

@receiver(post_migrate)
def create_default_site_setup(sender, **kwargs):
    if not SiteSetup.objects.exists():
        SiteSetup.objects.create(name="Обменник")
