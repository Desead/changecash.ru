import requests

def update_crypto_prices():
    from app_main.choices import MerchantName
    from app_main.models import RateMoney, Merchant

    print(f"Updating Rapira Prices")

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
            if stable_coin not in i['symbol']: continue

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
