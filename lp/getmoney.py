import requests
import json
from pathlib import Path
from django.conf import settings
from django.core.cache import cache
from app_main.choices import MoneyType, MerchantName
from app_main.models import SiteSetup
from decimal import Decimal


def toDecimal(value):
    try:
        return Decimal(value)
    except:
        return 0


def toInt(value, default_value=0):
    try:
        return int(value)
    except:
        return default_value


class GetMoney:
    def __init__(self, exchange_data):
        self.exchange_data = exchange_data

    def get_money(self):
        SiteSetup_cash = cache.get('SiteSetup')
        if SiteSetup_cash is None:
            SiteSetup_cash = SiteSetup.load()

        all_money = self.__get_money_from_url()
        if isinstance(all_money, tuple) and all_money[0]:
            money_list = []

            match self.exchange_data.name:
                case MerchantName.RAPIRA:
                    for money in all_money[1]:
                        money_list.append({
                            'merchant': self.exchange_data,
                            'money_type': MoneyType.CRYPTO,
                            'name_short': money['coinId'],
                            'name_long': money['coinId'],
                            'chain_short': money['chainId'],
                            'chain_long': money['displayName'],
                            'api_format': money['apiFormat'],
                            'money_digits': toInt(money['scale'], 8),
                            'deposit': True,
                            'withdraw': True,
                            'adeposit': money['rechargeable'],
                            'awithdraw': money['withdrawable'],
                            'min_deposit': toDecimal(money['minRecharge']),
                            'min_withdraw': toDecimal(money['minWithdraw']),
                            'fee_deposit_fix': toDecimal(money['rechargeFee']),
                            'fee_withdraw_fix': toDecimal(money['withdrawFee']),
                            'stablecoin': True if money['coinId'] in SiteSetup_cash.stablecoin_list else False,
                        })
                    money_list.append({
                        'merchant': self.exchange_data,
                        'money_type': MoneyType.CASH,
                        'name_short': 'RUB',
                        'name_long': 'RUB',
                        'money_digits': 2,
                        'deposit': True,
                        'withdraw': True,
                        'adeposit': True,
                        'awithdraw': True,
                        'min_deposit': 10_000,
                        'min_withdraw': 10_000,
                        'chain_short': MoneyType.CASH,
                        'chain_long': MoneyType.CASH,
                    })
                    return money_list

    def __get_money_from_url(self):

        match self.exchange_data.name:
            case MerchantName.RAPIRA:
                try:
                    url = 'https://api.rapira.net/open/token'
                    headers = {'accept': 'application/json'}
                    response = requests.get(url, headers=headers, timeout=(5, 15))

                    if settings.DEBUG:
                        folder = Path('./files')
                        folder.mkdir(parents=True, exist_ok=True)

                        with open(folder / 'rapira token.json', 'w', encoding='utf-8') as f:
                            json.dump(response.json(), f, ensure_ascii=False, indent=4)

                    return True, response.json()

                except Exception:
                    return False, f"Ошибка при запросе к внешнему API для биржи: {self.exchange_data.name}"

            case _:
                return False, f"Неизведанная биржа: {self.exchange_data}"
