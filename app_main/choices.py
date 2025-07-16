from django.db import models


class MoneyType(models.TextChoices):
    CRYPTO = 'crypto', 'Криптовалюта'
    FIAT = 'fiat', 'Банковские карты'
    PAYMENT = 'payment', 'Платёжные системы'
    CASH = 'cash', 'Наличные'


class MerchantName(models.TextChoices):
    RAPIRA = 'rapira', 'rapira.net'
    # HAND = 'list_address', 'Собственные монеты'  # Собственный список адресов
    # GECKO = 'coingecko', 'coingecko.com'
    # CMK = 'coinmarketcap', 'coinmarketcap.com'
    # BYBIT = 'bybit', 'bybit.com'
    # WHITEBIT = 'whitebit', 'whitebit.com'


class OrderType(models.TextChoices):
    AUTO = 'auto', 'авто обмен'
    HAND = 'hand', 'ручной обмен'


class SwapType(models.TextChoices):
    FLOATING = 'floating', 'Плавающий курс'
    FIXED = 'fixed', 'Фиксированный курс'


class OrderStatus(models.TextChoices):
    NEW = 'new', 'Новая'
    IN_PROGRESS = 'in_progress', 'В работе'
    CLOSED = 'closed', 'Закрыта'
    CANCELLED = 'cancelled', 'Отменена'


class CreateType(models.TextChoices):
    REAL = 'real', 'Реальная заявка'
    TEST = 'test', 'Тестовая заявка'


class DocumentType(models.TextChoices):
    RULES = "exchange_rules", "Правила обмена"
    PRIVACY = "privacy_policy", "Политика конфиденциальности"
    TERMS = "terms_of_service", "Пользовательское соглашение"
    RISK = "disclaimer", "Риски / Отказ от ответственности"
    REQUESTS = "authorities_requests", "Руководство по запросам от компетентных органов"
    AML = "aml_kyc_policy", "Политика AML / KYC"
    FAQ = "faq", "Вопросы и ответы (FAQ)"
    ABOUT = "about", "О компании"
    SUPPORT = "support", "Поддержка"
