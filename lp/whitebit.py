import base64
import hashlib
import hmac
import json
import time
from typing import Iterable

import requests

from app_main.choices import MerchantName, MoneyType
from app_main.models import Merchant, Money


class WhiteBITError(Exception):
    pass


class WhiteBITConfigurationError(WhiteBITError):
    pass


class WhiteBITAPIError(WhiteBITError):
    def __init__(self, message, status_code=None, payload=None):
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


def normalize_network_name(value):
    value = (value or '').strip().upper()
    if not value:
        return ''

    aliases = {
        'ERC-20': 'ERC20',
        'TRC-20': 'TRC20',
        'BEP-20': 'BEP20',
        'BEP 20': 'BEP20',
        'BSC': 'BEP20',
        'BSC (BEP20)': 'BEP20',
        'POLYGON POS': 'POLYGON',
        'ARBITRUM ONE': 'ARBITRUM',
        'OPTIMISM MAINNET': 'OPTIMISM',
        'AVALANCHE C-CHAIN': 'AVAXC',
    }
    return aliases.get(value, value.replace(' ', ''))


def unique_keep_order(values: Iterable):
    seen = set()
    result = []
    for value in values:
        marker = value if value is not None else '__NONE__'
        if marker in seen:
            continue
        seen.add(marker)
        result.append(value)
    return result


def extract_error_message(payload, fallback='Ошибка WhiteBIT API'):
    if isinstance(payload, dict):
        for key in ('message', 'msg', 'error', 'errors', 'description'):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
            if isinstance(value, list) and value:
                first = value[0]
                if isinstance(first, str) and first.strip():
                    return first.strip()
        return json.dumps(payload, ensure_ascii=False)[:300]
    if isinstance(payload, str) and payload.strip():
        return payload.strip()
    return fallback


class WhiteBITClient:
    base_url = 'https://whitebit.com'

    def __init__(self, merchant):
        self.merchant = merchant
        self.api_key = (merchant.api_public or '').strip()
        self.api_secret = (merchant.api_secret or '').strip()

        if not self.api_key or not self.api_secret:
            raise WhiteBITConfigurationError('У мерчанта WhiteBIT не заполнены API key / API secret.')

    def _nonce(self):
        return int(time.time() * 1000)

    def _post(self, path, payload):
        body = {
            'request': path,
            'nonce': self._nonce(),
            'nonceWindow': True,
            **payload,
        }
        body_raw = json.dumps(body, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
        encoded_payload = base64.b64encode(body_raw)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            encoded_payload,
            hashlib.sha512,
        ).hexdigest()

        response = requests.post(
            f'{self.base_url}{path}',
            data=body_raw,
            headers={
                'Content-type': 'application/json',
                'X-TXC-APIKEY': self.api_key,
                'X-TXC-PAYLOAD': encoded_payload.decode('utf-8'),
                'X-TXC-SIGNATURE': signature,
            },
            timeout=(10, 20),
        )

        try:
            payload = response.json()
        except ValueError:
            raise WhiteBITAPIError(
                f'WhiteBIT вернул не-JSON ответ (HTTP {response.status_code}).',
                status_code=response.status_code,
            )

        if response.status_code >= 400:
            raise WhiteBITAPIError(
                extract_error_message(payload, fallback=f'HTTP {response.status_code}'),
                status_code=response.status_code,
                payload=payload,
            )

        return payload

    def get_deposit_address(self, ticker, network=None):
        request_payload = {
            'ticker': str(ticker).upper(),
        }
        if network:
            request_payload['network'] = network

        data = self._post('/api/v4/main-account/address', request_payload)
        account = data.get('account') or {}
        address = (account.get('address') or '').strip()
        memo = (account.get('memo') or '').strip()

        if not address:
            raise WhiteBITAPIError('WhiteBIT не вернул адрес депозита.', payload=data)

        return {
            'address': address,
            'memo': memo,
            'raw': data,
        }


def build_network_candidates(selected_money, whitebit_merchant):
    selected_symbol = str(selected_money.name_short).upper()
    target_networks = {
        normalize_network_name(selected_money.api_format),
        normalize_network_name(selected_money.chain_short),
        normalize_network_name(selected_money.chain_long),
    }
    target_networks.discard('')

    candidates = []
    whitebit_rows = list(
        Money.objects.filter(
            merchant=whitebit_merchant,
            money_type=MoneyType.CRYPTO,
            name_short__iexact=selected_symbol,
        )
    )

    exact_matches = []
    fallback_matches = []
    for row in whitebit_rows:
        row_candidates = [row.api_format, row.chain_short, row.chain_long]
        row_candidates = [item for item in row_candidates if item]
        if not row_candidates:
            continue

        preferred_network = row_candidates[0]
        row_normalized = {normalize_network_name(item) for item in row_candidates if item}
        if target_networks & row_normalized:
            exact_matches.append(preferred_network)
        else:
            fallback_matches.append(preferred_network)

    candidates.extend(exact_matches)
    candidates.extend(fallback_matches)
    candidates.extend([selected_money.api_format, selected_money.chain_short, selected_money.chain_long])

    normalized_symbol = normalize_network_name(selected_symbol)
    normalized_candidates = []
    for item in candidates:
        normalized = normalize_network_name(item)
        if not normalized:
            continue
        if normalized == normalized_symbol:
            continue
        normalized_candidates.append(normalized)

    normalized_candidates = unique_keep_order(normalized_candidates)
    normalized_candidates.append(None)
    return normalized_candidates


def get_whitebit_deposit_details(selected_money):
    whitebit_merchant = Merchant.objects.filter(name=MerchantName.WHITEBIT, status=True).first()
    if not whitebit_merchant:
        raise WhiteBITConfigurationError('Не найден активный мерчант WhiteBIT. Создайте его в админке и включите статус.')

    client = WhiteBITClient(whitebit_merchant)
    ticker = str(selected_money.name_short).upper()
    last_error = None

    for network in build_network_candidates(selected_money, whitebit_merchant):
        try:
            result = client.get_deposit_address(ticker=ticker, network=network)
            result['merchant_name'] = whitebit_merchant.name
            result['network'] = network or ''
            return result
        except WhiteBITAPIError as exc:
            last_error = exc
            # Ошибки авторизации/доступа сразу отдаём наружу, дальше перебирать сети бессмысленно.
            if exc.status_code in (401, 403):
                raise
            continue

    if last_error:
        raise WhiteBITAPIError(f'Не удалось получить адрес депозита WhiteBIT для {ticker}: {last_error}')

    raise WhiteBITAPIError(f'Не удалось получить адрес депозита WhiteBIT для {ticker}.')
