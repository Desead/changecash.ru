import requests
from django.db.models import Q


def sync_auto_trade_flags_by_rates():
    from app_main.choices import MerchantName, MoneyType
    from app_main.models import Money, RateMoney

    tradable_symbols = {"USDT"}

    pairs = RateMoney.objects.filter(
        Q(money_left="USDT") | Q(money_right="USDT")
    ).values_list("money_left", "money_right")

    for left_symbol, right_symbol in pairs:
        left_symbol = (left_symbol or "").upper()
        right_symbol = (right_symbol or "").upper()

        if left_symbol == "USDT" and right_symbol:
            tradable_symbols.add(right_symbol)
        if right_symbol == "USDT" and left_symbol:
            tradable_symbols.add(left_symbol)

    crypto_qs = Money.objects.filter(money_type=MoneyType.CRYPTO)

    # WhiteBIT монеты — внутренние, всегда скрыты с фронта.
    crypto_qs.filter(merchant__name=MerchantName.WHITEBIT).update(
        adeposit=False,
        awithdraw=False,
    )

    non_whitebit_qs = crypto_qs.exclude(merchant__name=MerchantName.WHITEBIT)

    non_whitebit_qs.filter(name_short__in=tradable_symbols).update(
        adeposit=True,
        awithdraw=True,
    )
    non_whitebit_qs.exclude(name_short__in=tradable_symbols).update(
        adeposit=False,
        awithdraw=False,
    )



def update_crypto_prices():
    from app_main.choices import MerchantName
    from app_main.models import RateMoney, Merchant

    print("Updating Rapira Prices")

    try:
        url = "https://api.rapira.net/open/market/rates"
        response = requests.get(url, timeout=(5, 10))
        response.raise_for_status()
        data = response.json()

    except Exception as e:
        print(f"[ERROR] Failed to fetch prices: {e}")
        return

    if data['code'] == 0 and 'data' in data:
        merchant = Merchant.objects.filter(name=MerchantName.RAPIRA)[0]
        stable_coin = 'USDT'

        for i in data['data']:
            if stable_coin not in i['symbol']:
                continue

            RateMoney.objects.update_or_create(
                name=merchant,
                money_left=i['quoteCurrency'],
                money_right=i['baseCurrency'],
                rate_nominal=1,
                defaults={
                    'rate_ask': i['askPrice'],
                    'rate_bid': i['bidPrice'],
                }
            )

        sync_auto_trade_flags_by_rates()
