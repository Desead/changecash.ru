from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, re_path
from django.views.generic import TemplateView

from .views import (
    CustomLoginView,
    CustomLogoutView,
    ExchangeConfirmView,
    ExchangeFinalizeView,
    ExchangeHomeView,
    SignUpView,
    DynamicPageDispatchView,
    SiteDocumentDetailView,
    UserDashboardView,
    get_coins,
    get_limits_view,
    get_rate_view,
    popular_rates_view,
)

urlpatterns = [
    path('', ExchangeHomeView.as_view(), name='exchange_home'),
    path('confirm/', ExchangeConfirmView.as_view(), name='exchange_confirm'),
    path('finalize/', ExchangeFinalizeView.as_view(), name='exchange_finalize'),
    path('success/<int:pk>/', TemplateView.as_view(template_name='app_main/success.html'), name='exchange_success'),

    path('account/', UserDashboardView.as_view(), name='account_dashboard'),
    path('account/login/', CustomLoginView.as_view(), name='login'),
    path('account/register/', SignUpView.as_view(), name='signup'),
    path('account/logout/', CustomLogoutView.as_view(), name='logout'),

    path('api/get-rate/', get_rate_view, name='get_rate'),
    path('api/popular-rates/', popular_rates_view, name='popular_rates'),
    path('api/get-limits/', get_limits_view, name='get_limits'),
    path('api/coins/', get_coins, name='get_coins'),

    re_path(r'^(?P<page_path>.+)/$', DynamicPageDispatchView.as_view(), name='dynamic_page'),
    path('<slug:slug>/', SiteDocumentDetailView.as_view(), name='site_document'),
]
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
