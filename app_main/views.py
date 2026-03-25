from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.http import HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.decorators.cache import cache_page
from django.views.decorators.http import require_GET
from django.views.generic import DetailView, FormView, TemplateView

from .choices import OrderStatus
from .decorators import ratelimit_ip
from .forms import ExchangeForm, SignUpForm
from .models import Money, Merchant, Order, PartnerAccrual, RateMoney, SiteDocument, SiteSetup, UserProfile
from .utils import OrderName


def get_rate_to_usdt(symbol: str) -> Decimal:
    symbol = (symbol or '').strip().upper()
    if not symbol:
        raise RateMoney.DoesNotExist

    if symbol == 'USDT':
        return Decimal('1')

    try:
        rate = RateMoney.objects.get(money_left=symbol, money_right='USDT')
        return Decimal(str(rate.rate_bid or 0))
    except RateMoney.DoesNotExist:
        rate = RateMoney.objects.get(money_left='USDT', money_right=symbol)
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

        order = Order.objects.create(
            number=OrderName.create_order_name(),
            user=self.request.user if self.request.user.is_authenticated else None,
            left_money=left_symbol,
            left_chain=str(cleaned['left_money'].chain_long),
            right_money=right_symbol,
            right_chain=str(cleaned['right_money'].chain_long),
            left_rate=left_rate,
            right_rate=right_rate,
            left_count=cleaned['left_amount'],
            right_count=cleaned.get('right_amount') or 0,
            client_address=cleaned['client_address'],
            client_memo=cleaned['client_memo'],
        )

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
        from_id = request.POST.get('from_money_id')
        to_id = request.POST.get('to_money_id')
        amount = request.POST.get('amount')

        try:
            amount = Decimal(amount)
            from_money = Money.objects.get(id=from_id)
            to_money = Money.objects.get(id=to_id)
        except Exception:
            return render(request, 'errors/error.html', {'message': 'Ошибка оформления заявки'})

        order = Order.objects.create(
            from_money=from_money,
            to_money=to_money,
            amount_from=amount,
            status='new'
        )

        return HttpResponseRedirect(reverse('exchange_success', args=[order.id]))


class SiteDocumentDetailView(DetailView):
    model = SiteDocument
    template_name = 'app_main/templates/app_main/document_detail.html'
    context_object_name = 'document'

    def get_object(self):
        try:
            return SiteDocument.objects.get(slug=self.kwargs['slug'])
        except SiteDocument.DoesNotExist:
            return HttpResponseRedirect(reverse('exchange_home'))


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

    left_parts = left_raw.split()
    right_parts = right_raw.split()

    if len(left_parts) != 2 or len(right_parts) != 2:
        return JsonResponse({'error': 'Некорректный формат монеты'}, status=400)

    left_symbol = left_parts[0]
    right_symbol = right_parts[0]

    try:
        amount = Decimal(amount_raw)
    except (InvalidOperation, ValueError):
        amount = None

    fee_trade_multy = Decimal('1')
    try:
        left_rate = get_rate_to_usdt(left_symbol)
        right_rate = get_rate_to_usdt(right_symbol)

        if left_rate == 0 or right_rate == 0:
            return JsonResponse({'error': 'Ошибка кросс-курса (0)'}, status=400)

        if left_symbol != 'USDT' and right_symbol != 'USDT':
            fee_trade_multy = Decimal('2')

        rate_value = left_rate / right_rate

    except RateMoney.DoesNotExist:
        return JsonResponse({'error': 'Одна из монет не имеет курса к USDT'}, status=404)
    except ZeroDivisionError:
        return JsonResponse({'error': 'Ошибка деления на 0'}, status=400)

    response_data = {
        'rate': f'{rate_value:.8f}',
        'cached': False
    }

    if amount:
        try:
            left_money_obj = Money.objects.get(name_short=left_parts[0], chain_long=left_parts[1])
            right_money_obj = Money.objects.get(name_short=right_parts[0], chain_long=right_parts[1])
            fee_swap = Decimal(SiteSetup.objects.first().fee)
            fee_trade = Decimal(Merchant.objects.first().spot_taker_fee)
        except Money.DoesNotExist:
            return JsonResponse({'error': 'Монета не найдена в базе'}, status=404)
        except SiteSetup.DoesNotExist:
            fee_swap = 0
        except Merchant.DoesNotExist:
            fee_trade = 0

        fee_deposit = Decimal(left_money_obj.fee_deposit_fix) or Decimal('0')
        fee_withdraw = Decimal(right_money_obj.fee_withdraw_fix) or Decimal('0')

        try:
            fee_swap = Decimal(fee_swap)
        except (InvalidOperation, ValueError):
            fee_swap = 0
        try:
            fee_trade = Decimal(fee_trade)
        except (InvalidOperation, ValueError):
            fee_trade = 0

        amount_in = amount.quantize(Decimal('1.00000000'))
        amount_net = amount - fee_deposit

        if amount_net < 0:
            amount_net = Decimal('0')

        amount_out_raw = amount_net * rate_value
        amount_out = amount_out_raw * (100 - fee_trade * fee_trade_multy) / 100
        amount_out = amount_out * (100 - fee_swap) / 100
        amount_out = amount_out - fee_withdraw

        if amount_out < 0:
            amount_out = Decimal('0')

        response_data.update({
            'amount_in': str(amount_in),
            'amount_out': str(amount_out.quantize(Decimal('1.00000000'))),
            'fee_deposit': str(fee_deposit),
            'fee_withdraw': str(fee_withdraw),
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
