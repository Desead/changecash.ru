from decimal import Decimal, InvalidOperation
import logging

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.http import Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET
from xml.etree import ElementTree as ET
from django.views.generic import DetailView, FormView, TemplateView

from .choices import MerchantName, MoneyType, OrderStatus
from .decorators import ratelimit_ip
from .forms import ExchangeForm, SignUpForm
from .models import City, Money, Merchant, Order, PartnerAccrual, RateMoney, SiteDocument, SiteSetup, UserProfile
from .utils import OrderName
from lp.whitebit import WhiteBITAPIError, WhiteBITConfigurationError, get_whitebit_deposit_details


logger = logging.getLogger(__name__)


def _get_rate_record(left_symbol: str, right_symbol: str):
    qs = RateMoney.objects.filter(money_left=left_symbol, money_right=right_symbol).select_related('name')
    if not qs.exists():
        raise RateMoney.DoesNotExist

    default_rate = qs.filter(name__default_price=True).first()
    return default_rate or qs.order_by('id').first()


def _normalize_relative_path(value: str, default: str = 'xml_export/') -> str:
    normalized = (value or default).strip().strip('/')
    if not normalized:
        normalized = default.strip('/')
    return f'{normalized}/'


def _get_xml_export_relative_path() -> str:
    site_setup = SiteSetup.objects.first()
    return _normalize_relative_path(getattr(site_setup, 'xml_link', 'xml_export/'))


def _get_default_fee_merchant():
    return Merchant.objects.filter(default_price=True).first() or Merchant.objects.first()


def _decimal_to_xml(value: Decimal | int | float | str) -> str:
    decimal_value = Decimal(str(value or 0))
    normalized = format(decimal_value.normalize(), 'f')
    if '.' in normalized:
        normalized = normalized.rstrip('0').rstrip('.')
    return normalized or '0'


def _calculate_exchange_amounts(left_money_obj: Money, right_money_obj: Money, amount: Decimal) -> dict:
    fee_trade_multy = Decimal('1')
    left_symbol = (left_money_obj.name_short or '').strip().upper()
    right_symbol = (right_money_obj.name_short or '').strip().upper()

    left_rate = get_rate_to_usdt(left_symbol)
    right_rate = get_rate_to_usdt(right_symbol)

    if left_rate == 0 or right_rate == 0:
        raise ZeroDivisionError

    if left_symbol != 'USDT' and right_symbol != 'USDT':
        fee_trade_multy = Decimal('2')

    rate_value = left_rate / right_rate

    site_setup = SiteSetup.objects.first()
    fee_swap = Decimal(str(getattr(site_setup, 'fee', 0) or 0))

    fee_merchant = _get_default_fee_merchant()
    fee_trade = Decimal(str(getattr(fee_merchant, 'spot_taker_fee', 0) or 0))

    fee_deposit = Decimal(str(left_money_obj.fee_deposit_fix or 0))
    fee_withdraw = Decimal(str(right_money_obj.fee_withdraw_fix or 0))

    amount_in = Decimal(str(amount or 0))
    amount_net = amount_in - fee_deposit
    if amount_net < 0:
        amount_net = Decimal('0')

    amount_out_raw = amount_net * rate_value
    amount_out = amount_out_raw * (Decimal('100') - fee_trade * fee_trade_multy) / Decimal('100')
    amount_out = amount_out * (Decimal('100') - fee_swap) / Decimal('100')
    amount_out = amount_out - fee_withdraw

    if amount_out < 0:
        amount_out = Decimal('0')

    return {
        'rate_value': rate_value,
        'amount_in': amount_in,
        'amount_out': amount_out,
        'fee_deposit': fee_deposit,
        'fee_withdraw': fee_withdraw,
        'fee_trade': fee_trade,
        'fee_swap': fee_swap,
        'fee_trade_multiplier': fee_trade_multy,
    }


def _collect_xml_money(*, for_deposit: bool = False, for_withdraw: bool = False) -> dict[str, Money]:
    qs = Money.objects.select_related('merchant').exclude(api_format__isnull=True).exclude(api_format='')
    if for_deposit:
        qs = qs.filter(deposit=True, adeposit=True)
    if for_withdraw:
        qs = qs.filter(withdraw=True, awithdraw=True)

    qs = qs.order_by('-merchant__default_price', 'merchant_id', 'id')

    result: dict[str, Money] = {}
    for money in qs:
        code = (money.api_format or '').strip()
        if not code:
            continue
        result.setdefault(code, money)
    return result




def _get_active_city_codes() -> list[str]:
    return list(
        City.objects.filter(is_active=True)
        .order_by('rank', 'name', 'code')
        .values_list('code', flat=True)
    )


def _build_xml_rate_pair(left_money_obj: Money, right_money_obj: Money) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    left_symbol = (left_money_obj.name_short or '').strip().upper()
    right_symbol = (right_money_obj.name_short or '').strip().upper()

    left_rate = get_rate_to_usdt(left_symbol)
    right_rate = get_rate_to_usdt(right_symbol)
    if left_rate <= 0 or right_rate <= 0:
        raise ZeroDivisionError

    return right_rate, left_rate, left_rate, right_rate


def _build_xml_min_amount(
    left_money_obj: Money,
    right_money_obj: Money,
    nominal_in: Decimal,
    amount_out: Decimal,
    left_rate_usdt: Decimal,
) -> Decimal:
    candidates: list[Decimal] = []

    for raw_value in (left_money_obj.min_deposit, left_money_obj.min_trade):
        value = Decimal(str(raw_value or 0))
        if value > 0:
            candidates.append(value)

    min_trade_usdt = Decimal(str(left_money_obj.min_trade_usdt or 0))
    if min_trade_usdt > 0 and left_rate_usdt > 0:
        candidates.append(min_trade_usdt / left_rate_usdt)

    right_min_withdraw = Decimal(str(right_money_obj.min_withdraw or 0))
    if right_min_withdraw > 0 and amount_out > 0:
        candidates.append(right_min_withdraw * nominal_in / amount_out)

    if not candidates:
        return nominal_in if nominal_in > 0 else Decimal('1')
    return max(candidates)


def build_xml_export_bytes() -> bytes:
    root = ET.Element('rates')

    site_setup = SiteSetup.objects.first()
    if site_setup and site_setup.pause:
        return ET.tostring(root, encoding='utf-8', xml_declaration=True)

    deposit_money = _collect_xml_money(for_deposit=True)
    withdraw_money = _collect_xml_money(for_withdraw=True)
    active_city_codes = _get_active_city_codes()

    for from_code, left_money_obj in deposit_money.items():
        for to_code, right_money_obj in withdraw_money.items():
            if from_code == to_code:
                continue

            left_is_cash = left_money_obj.money_type == MoneyType.CASH
            right_is_cash = right_money_obj.money_type == MoneyType.CASH
            needs_city = left_is_cash or right_is_cash
            if needs_city and not active_city_codes:
                continue

            try:
                nominal_in, amount_out, left_rate_usdt, _right_rate_usdt = _build_xml_rate_pair(left_money_obj, right_money_obj)
            except (RateMoney.DoesNotExist, ZeroDivisionError, InvalidOperation):
                continue

            if nominal_in <= 0 or amount_out <= 0:
                continue

            reserve = Decimal(str(right_money_obj.reserv or 0))
            min_amount = _build_xml_min_amount(
                left_money_obj=left_money_obj,
                right_money_obj=right_money_obj,
                nominal_in=nominal_in,
                amount_out=amount_out,
                left_rate_usdt=left_rate_usdt,
            )
            max_amount = Decimal(str(left_money_obj.max_trade or 0))

            if max_amount > 0 and min_amount > max_amount:
                continue

            item = ET.SubElement(root, 'item')
            ET.SubElement(item, 'from').text = from_code
            ET.SubElement(item, 'to').text = to_code
            ET.SubElement(item, 'in').text = _decimal_to_xml(nominal_in)
            ET.SubElement(item, 'out').text = _decimal_to_xml(amount_out)
            if reserve > 0:
                ET.SubElement(item, 'amount').text = _decimal_to_xml(reserve)
            ET.SubElement(item, 'minamount').text = _decimal_to_xml(min_amount)
            ET.SubElement(item, 'maxamount').text = _decimal_to_xml(max_amount)
            if needs_city:
                ET.SubElement(item, 'city').text = ','.join(active_city_codes)

    return ET.tostring(root, encoding='utf-8', xml_declaration=True)



def get_rate_to_usdt(symbol: str) -> Decimal:
    symbol = (symbol or '').strip().upper()
    if not symbol:
        raise RateMoney.DoesNotExist

    if symbol == 'USDT':
        return Decimal('1')

    try:
        rate = _get_rate_record(symbol, 'USDT')
        return Decimal(str(rate.rate_bid or 0))
    except RateMoney.DoesNotExist:
        rate = _get_rate_record('USDT', symbol)
        if Decimal(str(rate.rate_bid or 0)) == 0:
            raise ZeroDivisionError
        return Decimal('1') / Decimal(str(rate.rate_bid))


class ExchangeHomeView(FormView):
    template_name = 'app_main/templates/app_main/home.html'
    form_class = ExchangeForm
    success_url = reverse_lazy('exchange_confirm')

    def form_valid(self, form):
        cleaned = form.cleaned_data

        left_symbol = str(cleaned['left_money'].name_short)
        right_symbol = str(cleaned['right_money'].name_short)
        left_rate = get_rate_to_usdt(left_symbol)
        right_rate = get_rate_to_usdt(right_symbol)

        order_kwargs = {
            'number': OrderName.create_order_name(),
            'user': self.request.user if self.request.user.is_authenticated else None,
            'left_money': left_symbol,
            'left_chain': str(cleaned['left_money'].chain_long),
            'left_lp': str(cleaned['left_money'].merchant.name),
            'right_money': right_symbol,
            'right_chain': str(cleaned['right_money'].chain_long),
            'right_lp': str(cleaned['right_money'].merchant.name),
            'left_rate': left_rate,
            'right_rate': right_rate,
            'left_count': cleaned['left_amount'],
            'right_count': cleaned.get('right_amount') or 0,
            'client_address': cleaned['client_address'],
            'client_memo': cleaned['client_memo'],
        }

        if cleaned['left_money'].money_type == MoneyType.CRYPTO:
            try:
                deposit_details = get_whitebit_deposit_details(cleaned['left_money'])
            except (WhiteBITConfigurationError, WhiteBITAPIError) as exc:
                logger.warning('WhiteBIT deposit address unavailable: %s', exc)
            except Exception:
                logger.exception('Unexpected WhiteBIT deposit address error')
            else:
                order_kwargs.update({
                    'left_lp': MerchantName.WHITEBIT,
                    'exchange_address': deposit_details.get('address', ''),
                    'exchange_memo': deposit_details.get('memo', ''),
                })

        order = Order.objects.create(**order_kwargs)

        self.request.session['order_id'] = order.id
        return redirect('exchange_confirm')

    def form_invalid(self, form):
        messages.error(self.request, 'Пожалуйста, исправьте ошибки в форме.')
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rates'] = RateMoney.objects.select_related('name').all()
        return context


class CustomLoginView(LoginView):
    template_name = 'account/login.html'
    redirect_authenticated_user = True

    def get_success_url(self):
        return self.get_redirect_url() or reverse_lazy('account_dashboard')


class CustomLogoutView(LogoutView):
    next_page = reverse_lazy('exchange_home')


class SignUpView(FormView):
    template_name = 'account/register.html'
    form_class = SignUpForm
    success_url = reverse_lazy('account_dashboard')

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect('account_dashboard')
        return super().dispatch(request, *args, **kwargs)

    def get_initial(self):
        initial = super().get_initial()
        ref_code = self.request.GET.get('ref', '').strip()
        if ref_code:
            initial['referral_code'] = ref_code
        return initial

    def form_valid(self, form):
        user = form.save()
        profile, _ = UserProfile.objects.get_or_create(user=user)

        ref_code = form.cleaned_data.get('referral_code', '').strip()
        if ref_code:
            referrer_profile = UserProfile.objects.select_related('user').filter(
                referral_code__iexact=ref_code
            ).first()
            if referrer_profile and referrer_profile.user_id != user.id:
                profile.referrer = referrer_profile.user
                profile.save(update_fields=['referrer'])

        login(self.request, user)
        return redirect(self.success_url)


class UserDashboardView(LoginRequiredMixin, TemplateView):
    template_name = 'account/dashboard.html'
    login_url = reverse_lazy('login')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        profile, _ = UserProfile.objects.get_or_create(user=self.request.user)
        orders_qs = self.request.user.orders.order_by('-time_created')

        partner_accruals_qs = PartnerAccrual.objects.filter(
            partner_user=self.request.user
        ).select_related('referred_user', 'order')

        context.update({
            'profile': profile,
            'orders': orders_qs[:50],
            'orders_total': orders_qs.count(),
            'orders_in_progress': orders_qs.filter(status=OrderStatus.IN_PROGRESS).count(),
            'orders_closed': orders_qs.filter(status=OrderStatus.CLOSED).count(),
            'orders_cancelled': orders_qs.filter(status=OrderStatus.CANCELLED).count(),
            'referral_url': self.request.build_absolute_uri(
                f"{reverse('signup')}?ref={profile.referral_code}"
            ),
            'partner_accruals': partner_accruals_qs[:50],
            'partner_referrals_count': UserProfile.objects.filter(referrer=self.request.user).count(),
            'partner_accruals_total': partner_accruals_qs.count(),
        })
        return context


class ExchangeConfirmView(View):
    def get(self, request):
        order_id = request.session.get('order_id')
        order = get_object_or_404(Order, id=order_id)
        return render(request, 'app_main/templates/app_main/confirm.html', {'order': order})

    def post(self, request):
        order_id = request.session.get('order_id')
        order = get_object_or_404(Order, id=order_id)
        action = request.POST.get('action')

        if action == 'cancel':
            order.status = OrderStatus.CANCELLED
            order.save()
            return redirect('exchange_home')

        if action == 'confirm':
            order.status = OrderStatus.IN_PROGRESS
            order.save()
            return render(request, 'app_main/templates/app_main/confirm.html', {
                'order': order,
                'confirmed': True,
            })

        return redirect('exchange_confirm')


class ExchangeFinalizeView(View):
    def post(self, request):
        messages.warning(request, 'Маршрут finalize устарел. Используйте стандартную форму обмена на главной странице.')
        return redirect('exchange_home')


class SiteDocumentDetailView(DetailView):
    model = SiteDocument
    template_name = 'app_main/templates/app_main/document_detail.html'
    context_object_name = 'document'

    def get_object(self):
        return get_object_or_404(SiteDocument, slug=self.kwargs['slug'])


class DynamicPageDispatchView(View):
    def get(self, request, page_path: str):
        normalized_page_path = _normalize_relative_path(page_path)
        if normalized_page_path == _get_xml_export_relative_path():
            return xml_export_view(request)

        page_slug = page_path.strip('/')
        if '/' in page_slug:
            raise Http404('Страница не найдена')

        document = get_object_or_404(SiteDocument, slug=page_slug)
        return render(request, 'app_main/templates/app_main/document_detail.html', {'document': document})


@require_GET
@cache_page(60)
def xml_export_view(request):
    return HttpResponse(build_xml_export_bytes(), content_type='application/xml; charset=utf-8')


def resolve_exchange_money(symbol: str, chain_long: str, *, deposit=False, withdraw=False):
    qs = Money.objects.filter(
        name_short__iexact=(symbol or "").strip(),
        chain_long__iexact=(chain_long or "").strip(),
    )
    if deposit:
        qs = qs.filter(deposit=True, adeposit=True)
    if withdraw:
        qs = qs.filter(withdraw=True, awithdraw=True)
    return qs.first()


@require_GET
@cache_page(3)
@ratelimit_ip(rate='10/s', block=True)
def get_rate_view(request):
    if getattr(request, 'limited', False):
        return JsonResponse({
            'error': 'Слишком много запросов. Пожалуйста, подождите.',
            'code': 429
        }, status=429)

    left_raw = request.GET.get('left', '').strip()
    right_raw = request.GET.get('right', '').strip()
    amount_raw = request.GET.get('amount', '').strip()

    if not left_raw or not right_raw:
        return JsonResponse({'error': 'Параметры монет не заданы'}, status=400)

    left_parts = left_raw.split(' ', 1)
    right_parts = right_raw.split(' ', 1)

    if len(left_parts) != 2 or len(right_parts) != 2:
        return JsonResponse({'error': 'Некорректный формат монеты'}, status=400)

    left_symbol = left_parts[0]
    right_symbol = right_parts[0]

    try:
        amount = Decimal(amount_raw)
    except (InvalidOperation, ValueError):
        amount = None

    try:
        left_money_obj = resolve_exchange_money(left_parts[0], left_parts[1], deposit=True)
        right_money_obj = resolve_exchange_money(right_parts[0], right_parts[1], withdraw=True)

        if not left_money_obj or not right_money_obj:
            return JsonResponse({'error': 'Монета недоступна для обмена'}, status=404)

        calc = _calculate_exchange_amounts(left_money_obj, right_money_obj, amount or Decimal('1'))
    except RateMoney.DoesNotExist:
        return JsonResponse({'error': 'Одна из монет не имеет курса к USDT'}, status=404)
    except ZeroDivisionError:
        return JsonResponse({'error': 'Ошибка деления на 0'}, status=400)

    response_data = {
        'rate': f"{calc['rate_value']:.8f}",
        'cached': False
    }

    if amount is not None:
        response_data.update({
            'amount_in': str(calc['amount_in'].quantize(Decimal('1.00000000'))),
            'amount_out': str(calc['amount_out'].quantize(Decimal('1.00000000'))),
            'fee_deposit': str(calc['fee_deposit']),
            'fee_withdraw': str(calc['fee_withdraw']),
            'min_deposit': str(left_money_obj.min_deposit),
            'min_withdraw': str(right_money_obj.min_withdraw),
            'fee_deposit_per': str(left_money_obj.fee_deposit_per or 0),
            'fee_withdraw_per': str(right_money_obj.fee_withdraw_per or 0),
            'confirm_deposit': left_money_obj.confirm_deposit,
            'confirm_withdraw': right_money_obj.confirm_withdraw,
        })

    return JsonResponse(response_data)


def get_coins(request):
    coins = Money.objects.filter((Q(deposit=True) | Q(withdraw=True)) & (Q(adeposit=True) | Q(awithdraw=True)))
    data = []
    for coin in coins:
        data.append({
            'name_short': coin.name_short,
            'chain_long': coin.chain_long,
            'deposit': coin.deposit,
            'adeposit': coin.adeposit,
            'withdraw': coin.withdraw,
            'awithdraw': coin.awithdraw,
            'icon_src': coin.icon_src,
        })
    return JsonResponse({'coins': data})


def popular_rates_view(request):
    site_setup = SiteSetup.objects.first()
    if not site_setup:
        return JsonResponse({'rates': []})

    rates = site_setup.popular_rates.all()

    result = [
        {
            'left': rate.money_left,
            'right': rate.money_right,
            'rate': str(rate.rate_bid),
        }
        for rate in rates
    ]

    return JsonResponse({'rates': result})


@require_GET
def get_limits_view(request):
    left_id = request.GET.get('left_id')
    right_id = request.GET.get('right_id')

    if not left_id or not right_id:
        return JsonResponse({'error': 'Не переданы ID монет'}, status=400)

    try:
        left_money = Money.objects.get(id=left_id)
        right_money = Money.objects.get(id=right_id)
    except Money.DoesNotExist:
        return JsonResponse({'error': 'Монета не найдена'}, status=404)

    min_left = left_money.min_deposit + left_money.fee_deposit_fix
    min_right = right_money.min_withdraw + right_money.fee_withdraw_fix

    return JsonResponse({
        'min_left': str(min_left),
        'left_code': f'{left_money.name_short} {left_money.chain_short}',
        'min_right': str(min_right),
        'right_code': f'{right_money.name_short} {right_money.chain_short}',
    })
