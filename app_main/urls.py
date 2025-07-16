from django.urls import path
from .views import ExchangeHomeView, ExchangeConfirmView, ExchangeFinalizeView, get_rate_view, get_limits_view, get_coins, popular_rates_view, \
    SiteDocumentDetailView
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    path('', ExchangeHomeView.as_view(), name='exchange_home'),
    path('confirm/', ExchangeConfirmView.as_view(), name='exchange_confirm'),
    path('finalize/', ExchangeFinalizeView.as_view(), name='exchange_finalize'),
    path('success/<int:pk>/', TemplateView.as_view(template_name='app_main/success.html'), name='exchange_success'),
    path('<slug:slug>/', SiteDocumentDetailView.as_view(), name='site_document'),
    path("api/get-rate/", get_rate_view, name="get_rate"),
    path('api/popular-rates/', popular_rates_view, name='popular_rates'),
    path("api/get-limits/", get_limits_view, name="get_limits"),
    path("api/coins/", get_coins, name="get_coins"),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
