# context_processors.py

from .models import SiteSetup


def site_setup(request):
    obj = SiteSetup.objects.first()
    if not obj:
        obj = SiteSetup.objects.create(name="Обменник")
    return {"site_setup": obj}
