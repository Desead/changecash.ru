import json
from decimal import Decimal
from pathlib import Path

import requests
from django.conf import settings
from django.core.cache import cache

from app_main.choices import MoneyType, MerchantName
from app_main.models import SiteSetup


def toDecimal(value):
    try:
        return Decimal(value)
    except Exception:
        return Decimal('0')


def toInt(value, default_value=0):
    try:
        return int(value)
    except Exception:
        return default_value


def get_stablecoins_set(site_setup):
    if not site_setup or not getattr(site_setup, 'stablecoin_list', ''):
        return set()
    return {item.strip().upper() for item in site_setup.stablecoin_list.split(',') if item.strip()}


class GetMoney:
    def __init__(self, exchange_data):
        self.exchange_data = exchange_data

    def get_money(self):
        site_setup_cache = cache.get('SiteSetup')
        if site_setup_cache is None:
            site_setup_cache = SiteSetup.load()

        all_money = self.__get_money_from_url()
        if not (isinstance(all_money, tuple) and all_money[0]):
            return all_money

        stablecoins = get_stablecoins_set(site_setup_cache)

        match self.exchange_data.name:
            case MerchantName.RAPIRA:
                return self._build_rapira_money(all_money[1], stablecoins)
            case MerchantName.WHITEBIT:
                return self._build_whitebit_money(all_money[1], stablecoins)
            case _:
                return False, f"Неизведанная биржа: {self.exchange_data}"

    def _build_rapira_money(self, payload, stablecoins):
        money_list = []
        for money in payload:
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
                'stablecoin': money['coinId'].upper() in stablecoins,
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

    def _build_whitebit_money(self, payload, stablecoins):
        money_list = []
        for ticker, currency in (payload or {}).items():
            if 'providers' in currency:
                # Для адресного мерчанта пока берём только крипту.
                continue

            name_long = currency.get('name') or ticker
            currency_precision = toInt(currency.get('currency_precision'), 8)
            can_deposit = bool(currency.get('can_deposit'))
            can_withdraw = bool(currency.get('can_withdraw'))
            raw_networks = currency.get('networks') or {}
            deposit_networks = raw_networks.get('deposits') or []
            withdraw_networks = raw_networks.get('withdraws') or []
            default_network = raw_networks.get('default')

            network_order = []
            for item in [*deposit_networks, *withdraw_networks, default_network, ticker]:
                if item and item not in network_order:
                    network_order.append(item)

            confirmations = currency.get('confirmations') or {}
            limits = currency.get('limits') or {}
            deposit_limits = limits.get('deposit') or {}
            withdraw_limits = limits.get('withdraw') or {}
            is_memo = bool(currency.get('is_memo'))

            for network in network_order:
                network_name = str(network).strip()
                network_deposit_limits = deposit_limits.get(network_name) or {}
                network_withdraw_limits = withdraw_limits.get(network_name) or {}

                money_list.append({
                    'merchant': self.exchange_data,
                    'money_type': MoneyType.CRYPTO,
                    'name_short': str(ticker).upper(),
                    'name_long': name_long,
                    'chain_short': network_name,
                    'chain_long': network_name,
                    'api_format': network_name,
                    'money_digits': currency_precision,
                    # На фронт такие монеты не показываем — они нужны только для подбора сети и адреса.
                    'deposit': False,
                    'withdraw': False,
                    'adeposit': can_deposit and network_name in deposit_networks,
                    'awithdraw': can_withdraw and network_name in withdraw_networks,
                    'stablecoin': str(ticker).upper() in stablecoins,
                    'memo': is_memo,
                    'min_deposit': toDecimal(network_deposit_limits.get('min', currency.get('min_deposit'))),
                    'min_withdraw': toDecimal(network_withdraw_limits.get('min', currency.get('min_withdraw'))),
                    'max_trade': toDecimal(network_withdraw_limits.get('max', currency.get('max_withdraw'))),
                    'confirm_deposit': toInt(confirmations.get(network_name), 1 if can_deposit else 0),
                    'confirm_withdraw': toInt(confirmations.get(network_name), 1 if can_withdraw else 0),
                })

        return money_list

    def __get_money_from_url(self):
        match self.exchange_data.name:
            case MerchantName.RAPIRA:
                try:
                    url = 'https://api.rapira.net/open/token'
                    headers = {'accept': 'application/json'}
                    response = requests.get(url, headers=headers, timeout=(5, 15))
                    response.raise_for_status()

                    if settings.DEBUG:
                        folder = Path('./files')
                        folder.mkdir(parents=True, exist_ok=True)
                        with open(folder / 'rapira token.json', 'w', encoding='utf-8') as f:
                            json.dump(response.json(), f, ensure_ascii=False, indent=4)

                    return True, response.json()
                except Exception:
                    return False, f"Ошибка при запросе к внешнему API для биржи: {self.exchange_data.name}"

            case MerchantName.WHITEBIT:
                try:
                    url = 'https://whitebit.com/api/v4/public/assets'
                    response = requests.get(url, timeout=(5, 20))
                    response.raise_for_status()

                    if settings.DEBUG:
                        folder = Path('./files')
                        folder.mkdir(parents=True, exist_ok=True)
                        with open(folder / 'whitebit assets.json', 'w', encoding='utf-8') as f:
                            json.dump(response.json(), f, ensure_ascii=False, indent=4)

                    return True, response.json()
                except Exception:
                    return False, f"Ошибка при запросе к внешнему API для биржи: {self.exchange_data.name}"

            case _:
                return False, f"Неизведанная биржа: {self.exchange_data}"
