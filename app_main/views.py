from django.views.decorators.http import require_GET
from django.views.decorators.cache import cache_page
from django.shortcuts import render, get_object_or_404, redirect
from django.urls import reverse
from django.contrib import messages
from django.views import View
from django.http import HttpResponseRedirect, JsonResponse
from django.views.generic import FormView, DetailView, TemplateView
from django.urls import reverse_lazy

from .choices import OrderStatus
from .decorators import ratelimit_ip
from .models import Money, RateMoney, Order, SiteSetup, SiteDocument, Merchant
from .forms import ExchangeForm
from decimal import Decimal, InvalidOperation
from django.db.models import Q

from .utils import OrderName


class ExchangeHomeView(FormView):
    template_name = 'app_main/templates/app_main/home.html'
    form_class = ExchangeForm
    success_url = reverse_lazy('exchange_confirm')

    def form_valid(self, form):
        # Сохраняем данные в сессию
        cleaned = form.cleaned_data

        order = Order.objects.create(
            number=OrderName.create_order_name(),
            left_money=str(cleaned['left_money'].name_short),
            left_chain=str(cleaned['left_money'].chain_long),
            right_money=str(cleaned['right_money'].name_short),
            right_chain=str(cleaned['right_money'].chain_long),
            left_count=cleaned['left_amount'],
            right_count=cleaned.get('right_amount') or 0,
            client_address=cleaned['client_address'],
            client_memo=cleaned['client_memo'],
        )

        self.request.session['order_id'] = order.id
        return redirect('exchange_confirm')

    def form_invalid(self, form):
        messages.error(self.request, "Пожалуйста, исправьте ошибки в форме.")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['rates'] = RateMoney.objects.select_related('name').all()
        return context


class ExchangeConfirmView(View):
    def get(self, request):
        order_id = request.session.get("order_id")
        order = get_object_or_404(Order, id=order_id)
        return render(request, 'app_main/templates/app_main/confirm.html', {"order": order})

    def post(self, request):
        order_id = request.session.get("order_id")
        order = get_object_or_404(Order, id=order_id)
        action = request.POST.get("action")

        if action == "cancel":
            order.status = OrderStatus.CANCELLED
            order.save()
            return redirect("exchange_home")

        if action == "confirm":
            order.status = OrderStatus.IN_PROGRESS
            order.save()
            return render(request, 'app_main/templates/app_main/confirm.html', {
                "order": order,
                "confirmed": True,
            })


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

        # Пример: создать заявку
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


'''
пример запроса
http://127.0.0.1:8000/api/get-rate/?left=BTC%20Bitcoin&right=USDT%20TRC20&amount=0.005
'''


@require_GET
@cache_page(3)  # кэш
@ratelimit_ip(rate='10/s', block=True)
def get_rate_view(request):
    if getattr(request, 'limited', False):
        return JsonResponse({
            "error": "Слишком много запросов. Пожалуйста, подождите.",
            "code": 429
        }, status=429)

    # Далее — логика получения курсов
    left_raw = request.GET.get("left", "").strip()
    right_raw = request.GET.get("right", "").strip()
    amount_raw = request.GET.get("amount", "").strip()

    if not left_raw or not right_raw:
        return JsonResponse({"error": "Параметры монет не заданы"}, status=400)

    left_parts = left_raw.split()
    right_parts = right_raw.split()

    if len(left_parts) != 2 or len(right_parts) != 2:
        return JsonResponse({"error": "Некорректный формат монеты"}, status=400)

    left_symbol = left_parts[0]
    right_symbol = right_parts[0]

    try:
        amount = Decimal(amount_raw)
    except (InvalidOperation, ValueError):
        amount = None

    # Основной блок получения курса
    fee_trade_multy = Decimal("1")
    try:
        if left_symbol == "USDT":
            try:
                rate = RateMoney.objects.get(money_left="USDT", money_right=right_symbol)
                rate_value = rate.rate_bid
            except RateMoney.DoesNotExist:
                rate = RateMoney.objects.get(money_left=right_symbol, money_right="USDT")
                if rate.rate_bid == 0:
                    raise ZeroDivisionError
                rate_value = Decimal("1") / rate.rate_bid

        elif right_symbol == "USDT":
            try:
                rate = RateMoney.objects.get(money_left=left_symbol, money_right="USDT")
                rate_value = rate.rate_bid
            except RateMoney.DoesNotExist:
                rate = RateMoney.objects.get(money_left="USDT", money_right=left_symbol)
                if rate.rate_bid == 0:
                    raise ZeroDivisionError
                rate_value = Decimal("1") / rate.rate_bid

        else:
            # Кросс-курс через USDT
            fee_trade_multy = Decimal("2")
            try:
                rate_left = RateMoney.objects.get(money_left=left_symbol, money_right="USDT")
                left_rate = rate_left.rate_bid
            except RateMoney.DoesNotExist:
                rate_left = RateMoney.objects.get(money_left="USDT", money_right=left_symbol)
                if rate_left.rate_bid == 0:
                    raise ZeroDivisionError
                left_rate = Decimal("1") / rate_left.rate_bid

            try:
                rate_right = RateMoney.objects.get(money_left=right_symbol, money_right="USDT")
                right_rate = rate_right.rate_bid
            except RateMoney.DoesNotExist:
                rate_right = RateMoney.objects.get(money_left="USDT", money_right=right_symbol)
                if rate_right.rate_bid == 0:
                    raise ZeroDivisionError
                right_rate = Decimal("1") / rate_right.rate_bid

            if left_rate == 0 or right_rate == 0:
                return JsonResponse({"error": "Ошибка кросс-курса (0)"}, status=400)

            rate_value = left_rate / right_rate

    except RateMoney.DoesNotExist:
        return JsonResponse({"error": "Одна из монет не имеет курса к USDT"}, status=404)
    except ZeroDivisionError:
        return JsonResponse({"error": "Ошибка деления на 0"}, status=400)

    # Финальный ответ
    response_data = {
        "rate": f"{rate_value:.8f}",
        "cached": False
    }

    if amount:
        # 1. Получаем комиссии
        try:
            left_money_obj = Money.objects.get(name_short=left_parts[0], chain_long=left_parts[1])
            right_money_obj = Money.objects.get(name_short=right_parts[0], chain_long=right_parts[1])
            fee_swap = Decimal(SiteSetup.objects.first().fee)
            fee_trade = Decimal(Merchant.objects.first().spot_taker_fee)
        except Money.DoesNotExist:
            return JsonResponse({"error": "Монета не найдена в базе"}, status=404)
        except SiteSetup.DoesNotExist:
            fee_swap = 0
        except Merchant.DoesNotExist:
            fee_trade = 0

        fee_deposit = Decimal(left_money_obj.fee_deposit_fix) or Decimal("0")
        fee_withdraw = Decimal(right_money_obj.fee_withdraw_fix) or Decimal("0")

        try:
            fee_swap = Decimal(fee_swap)
        except (InvalidOperation, ValueError):
            fee_swap = 0
        try:
            fee_trade = Decimal(fee_trade)
        except (InvalidOperation, ValueError):
            fee_trade = 0

        # 2. Рассчитываем итоговые значения
        amount_in = amount.quantize(Decimal('1.00000000'))
        amount_net = amount - fee_deposit

        if amount_net < 0:
            amount_net = Decimal("0")

        amount_out_raw = amount_net * rate_value
        amount_out = amount_out_raw * (100 - fee_trade * fee_trade_multy) / 100
        amount_out = amount_out * (100 - fee_swap) / 100
        amount_out = amount_out - fee_withdraw

        if amount_out < 0:
            amount_out = Decimal("0")

        response_data.update({
            "amount_in": str(amount_in),
            "amount_out": str(amount_out.quantize(Decimal('1.00000000'))),
            "fee_deposit": str(fee_deposit),
            "fee_withdraw": str(fee_withdraw),

            "min_deposit": str(left_money_obj.min_deposit),
            "min_withdraw": str(right_money_obj.min_withdraw),
            "fee_deposit_per": str(left_money_obj.fee_deposit_per or 0),
            "fee_withdraw_per": str(right_money_obj.fee_withdraw_per or 0),
            "confirm_deposit": left_money_obj.confirm_deposit,
            "confirm_withdraw": right_money_obj.confirm_withdraw,
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
    left_id = request.GET.get("left_id")
    right_id = request.GET.get("right_id")

    if not left_id or not right_id:
        return JsonResponse({"error": "Не переданы ID монет"}, status=400)

    try:
        left_money = Money.objects.get(id=left_id)
        right_money = Money.objects.get(id=right_id)
    except Money.DoesNotExist:
        return JsonResponse({"error": "Монета не найдена"}, status=404)

    min_left = left_money.min_deposit + left_money.fee_deposit_fix
    min_right = right_money.min_withdraw + right_money.fee_withdraw_fix

    return JsonResponse({
        "min_left": str(min_left),
        "left_code": f"{left_money.name_short} {left_money.chain_short}",
        "min_right": str(min_right),
        "right_code": f"{right_money.name_short} {right_money.chain_short}",
    })
