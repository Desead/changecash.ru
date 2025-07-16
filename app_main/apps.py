from django.apps import AppConfig
from app_main.jobs.sheduler import start_scheduler_with_lock


class AppMainConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'app_main'
    verbose_name = 'Все настройки'

    def ready(self):
        start_scheduler_with_lock()

        import app_main.signals