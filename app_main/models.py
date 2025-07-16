from django.db import models
from django.core.cache import cache
from app_main.choices import MoneyType, MerchantName, OrderStatus, DocumentType
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.conf import settings
from pathlib import Path
from app_main.utils import OrderName
from django.templatetags.static import static
from django_ckeditor_5.fields import CKEditor5Field

MAX_DIGITS = 30  # общее количество цифр
DECIMAL_PLACES = 10  # количество цифр после запятой


def validate_image_size(image):
    max_size = 300 * 1024  # 300 KB
    if image.size > max_size:
        raise ValidationError("Иконка слишком большая (максимум 300KB)")


class Order(models.Model):
    number = models.CharField('Номер заявки', max_length=100, editable=False, unique=True)
    status = models.CharField('Статус заявки', max_length=100, choices=OrderStatus.choices, default=OrderStatus.NEW)

    time_created = models.DateTimeField('Заявка создана', auto_now_add=True)
    time_final = models.DateTimeField('Закрыли заявку', default=timezone.now, editable=False)

    left_money = models.CharField('Монета слева', max_length=100)
    left_chain = models.CharField('Сеть слева', max_length=100)
    left_lp = models.CharField('Мерчант слева', max_length=100, default=MerchantName.RAPIRA)
    left_rate = models.DecimalField('Курс слева к USDT', default=1, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')
    left_count = models.DecimalField('Планируем получить', max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0, )

    right_money = models.CharField('Монета справа', max_length=100)
    right_chain = models.CharField('Сеть справа', max_length=100)
    right_lp = models.CharField('Мерчант справа', max_length=100, default=MerchantName.RAPIRA)
    right_rate = models.DecimalField('Курс справа к USDT', default=1, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')
    right_count = models.DecimalField('Планируем отправить', max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0, )

    client_address = models.CharField('Адрес клиента', max_length=255, default='', help_text='')
    client_memo = models.CharField('Memo клиента', max_length=255, default='', blank=True, help_text='')
    exchange_address = models.CharField('Адрес обменника', max_length=255, default='', help_text='')
    exchange_memo = models.CharField('Memo обменника', max_length=255, default='', blank=True, help_text='')

    hash_left = models.CharField('Хеш входящей транзакции', max_length=128, default='', blank=True, help_text='')
    hash_right = models.CharField('Хеш исходящей транзакции', max_length=128, default='', blank=True, help_text='')
    link_left = models.URLField('Ссылка на входящую транзакции', default='', blank=True, help_text='')
    link_right = models.URLField('Ссылка на исходящую транзакции', default='', blank=True, help_text='')

    pl = models.DecimalField('Доход по заявке', max_digits=MAX_DIGITS, decimal_places=DECIMAL_PLACES, default=0, )

    descriptions = models.TextField('Комментарий к заявке', blank=True, null=True, help_text='Просто любой комментарий который захотели добавить к заявке')

    class Meta:
        verbose_name = 'Заявка на обмен'
        verbose_name_plural = '1 Заявки на обмен'

    def __str__(self):
        return self.number

    def save(self, *args, **kwargs):
        if not self.number:  # создаём уникальный номер заявки
            while True:
                # todo возможно ли здесь потенциально вечный цикл ?
                number = OrderName.create_order_name()
                if not Order.objects.filter(number=number).exists():
                    self.number = number
                    break
        super().save(*args, **kwargs)


class RateMoney(models.Model):
    name = models.ForeignKey('Merchant', on_delete=models.CASCADE)
    money_left = models.CharField('Монета слева', max_length=30, help_text='')
    money_right = models.CharField('Монета справа', max_length=30, default='USDT', help_text='')

    rate_nominal = models.DecimalField('Номинал', default=1, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='Номинал монеты слева')
    rate_ask = models.DecimalField('Ask', default=1, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')
    rate_bid = models.DecimalField('Bid', default=1, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')
    updated_rate = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Курс монеты'
        verbose_name_plural = '2 Курсы монеты'

    def __str__(self):
        return f"{self.name} : {self.money_left}: {self.money_right}: {self.rate_bid}"


class Money(models.Model):
    merchant = models.ForeignKey('Merchant', on_delete=models.CASCADE, verbose_name='Провайдер')
    money_type = models.CharField('Тип монеты', max_length=20, choices=MoneyType.choices, default=MoneyType.CRYPTO)
    name_short = models.CharField('Короткое название', max_length=100, help_text='Короткое название монеты: BTC')
    name_long = models.CharField('Длинное название', max_length=100, default='', help_text='Длинное название монеты: Bitcoin')
    chain_short = models.CharField('Блокчейн', max_length=100, blank=True, null=True, help_text='Короткое название сети: ETH')
    chain_long = models.CharField('Блокчейн', max_length=100, blank=True, null=True, help_text='Длинное название сети: ERC20')
    api_format = models.CharField('Название для API', max_length=100, blank=True, null=True, help_text='Как монета будет отображаться в api')
    nominal = models.PositiveIntegerField('Номинал', default=1, help_text='')
    reserv = models.DecimalField('Текущие резервы', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')
    money_digits = models.PositiveIntegerField('Точность монеты', default=8, help_text='')
    icon_file = models.ImageField(upload_to='money_icons/', blank=True, null=True, validators=[validate_image_size], )
    icon_url = models.URLField("URL иконки", blank=True, null=True)

    best_num = models.PositiveIntegerField('Номер на бесте', default=0, blank=True, help_text='')
    best_id = models.CharField('Название на бесте', max_length=10, default='', blank=True, help_text='')

    deposit = models.BooleanField(verbose_name='D', default=False, help_text='Монету можно получить')
    withdraw = models.BooleanField(verbose_name='W', default=False, help_text='Монету можно отдать')
    adeposit = models.BooleanField(verbose_name='DA', default=True, editable=False, help_text='Монету можно получить (авто)')
    awithdraw = models.BooleanField(verbose_name='WA', default=True, editable=False, help_text='Монету можно отдать (авто)')
    stablecoin = models.BooleanField('Стейблкоин', default=False, help_text='')
    memo = models.BooleanField('Memo/Tag/Destantion', default=False, help_text='')

    min_deposit = models.DecimalField('Мин ввод', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')
    min_withdraw = models.DecimalField('Мин вывод', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')
    max_trade = models.DecimalField('Макс лот', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')
    min_trade = models.DecimalField('Мин лот', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')
    min_trade_usdt = models.DecimalField('Мин лот в usdt', default=5, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, help_text='')

    fee_deposit_fix = models.DecimalField('Комиссия на ввод фикс', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS)
    fee_deposit_per = models.DecimalField('Комиссия на ввод в %', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS)
    fee_deposit_min = models.DecimalField('Мин комиссия на ввод', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS)
    fee_deposit_max = models.DecimalField('Макс комиссия на ввод', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS)
    fee_withdraw_fix = models.DecimalField('Комиссия на вывод фикс', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS, )
    fee_withdraw_per = models.DecimalField('Комиссия на вывод в %', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS)
    fee_withdraw_min = models.DecimalField('Мин комиссия на вывод', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS)
    fee_withdraw_max = models.DecimalField('Макс комиссия на вывод', default=0, decimal_places=DECIMAL_PLACES, max_digits=MAX_DIGITS)

    confirm_deposit = models.PositiveIntegerField('Потдверждений для ввода', default=0, help_text='')
    confirm_withdraw = models.PositiveIntegerField('Потдверждений для вывода', default=0, help_text='')

    class Meta:
        verbose_name = 'Все монеты, валюты'
        verbose_name_plural = '3 Все монеты, валюты'

    def __str__(self):
        return f"{self.name_short}/{self.name_long} - {self.chain_short}/{self.chain_long} : {self.merchant.name}"

    def save(self, *args, **kwargs):
        # Для крипты всегда нужно хотя бы 1 подтверждение
        if self.money_type == MoneyType.CRYPTO:
            if self.confirm_deposit == 0:
                self.confirm_deposit = 1
            if self.confirm_withdraw == 0:
                self.confirm_withdraw = 1
            if self.confirm_withdraw < self.confirm_deposit:
                self.confirm_withdraw = self.confirm_deposit

        if self.chain_long is None and self.chain_short is None:
            self.chain_long = self.money_type
            self.chain_short = self.money_type
        super().save(*args, **kwargs)

    @property
    def icon_src(self):
        if self.icon_file:
            return self.icon_file.url
        elif self.icon_url:
            return self.icon_url
        else:
            filename = f"{self.name_short.upper()}.png"
            static_path = Path(settings.BASE_DIR) / 'static' / 'logo_money' / filename
            if static_path.exists():
                return static(f'logo_money/{filename}')
            return static('logo_money/default.png')


class Merchant(models.Model):
    status = models.BooleanField('Статус', default=True, help_text='')
    astatus = models.BooleanField('Статус (авто)', editable=False, default=True, help_text='')

    name = models.CharField('Название', max_length=100, choices=MerchantName.choices, unique=True, blank=False, default=MerchantName.RAPIRA)
    default_price = models.BooleanField('Цены на главную', default=False, blank=False, help_text='Цены этого провайдера будут показываться на главной')
    api_public_view = models.CharField('Public key', max_length=3000, blank=True, help_text='')
    api_secret_view = models.CharField('Privat key', max_length=3000, blank=True, help_text='')
    api_phass_view = models.CharField('Secret/UID', max_length=3000, blank=True, help_text='Иногда на биржах используется 3 ключа')
    api_public = models.CharField(max_length=3000, blank=True, editable=False)
    api_secret = models.CharField(max_length=3000, blank=True, editable=False)
    api_phass = models.CharField(max_length=3000, blank=True, editable=False)

    stablecoin = models.CharField('Стейблкоин', max_length=100, default='USDT',
                                  help_text='Расчётный стейблкоин. В основном USDT, но, к примеру, у MEXC всё считается через USDC')
    no_used_money = models.CharField('Не используемые монеты', max_length=100, default='LUNA;USDTX;TERRA',
                                     help_text='Эти монеты у данного поставщика не использовать')
    spot_taker_fee = models.FloatField('Комиссия тейкера на споте в %', default='0.1')
    spot_maker_fee = models.FloatField('Комиссия мейкера на споте в %', default='0.1')
    future_taker_fee = models.FloatField('Комиссия тейкера на фьючерсах в %', default='0.1')
    future_maker_fee = models.FloatField('Комиссия мейкера на фьючерсах в %', default='0.1')

    class Meta:
        verbose_name = 'Биржа, Мерчант'
        verbose_name_plural = '4 Биржы, Мерчанты'

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        # Сохраним ключики в скрытых полях, а в админке покажем звёздочки
        if '*' not in self.api_public_view:
            self.api_public = self.api_public_view
            if self.api_public_view != '':
                self.api_public_view = self.api_public_view[:3] + 10 * '*' + self.api_public_view[-3:]
        if '*' not in self.api_secret_view:
            self.api_secret = self.api_secret_view
            if self.api_public_view != '':
                self.api_secret_view = self.api_secret_view[:3] + 10 * '*' + self.api_secret_view[-3:]
        if '*' not in self.api_phass_view:
            self.api_phass = self.api_phass_view
            if self.api_phass_view != '':
                self.api_phass_view = self.api_phass_view[:3] + 10 * '*' + self.api_phass_view[-3:]

        super().save(*args, **kwargs)


class SiteSetup(models.Model):
    name = models.CharField('Название обменника', default='Swap Name', blank=True, max_length=50, help_text='Это название отображается на главной')
    pause = models.BooleanField('Обмен приостановлен', default=False)
    logo = models.ImageField("Логотип", upload_to="logos/", blank=True, null=True)
    code_to_head = models.TextField('Код в HEAD', default='', blank=True, help_text='Код в тег /head. Сюда нужно вставлять различные метрики и т.д.')
    seo_title = models.CharField('Title', max_length=255, blank=True, default='Надёжный обменник', help_text='Title для главной. ~ 45 символов')
    seo_description = models.CharField('Description', max_length=255, blank=True, default='Безопасный обмен', help_text='Descriptions для главной')
    seo_keywords = models.CharField('Keywords', max_length=255, blank=True, default='bitcoin,swap,change,crypto', help_text='Keywords для главной')
    contact_email = models.EmailField("Email для связи", blank=True, null=True)
    contact_telegram = models.URLField("Ссылка на Telegram (поддержка)", blank=True, null=True)
    news_telegram = models.URLField("Ссылка на Telegram-канал (новости)", blank=True, null=True)
    news_vk = models.URLField("Ссылка на VK-группу (новости)", blank=True, null=True)
    main_title = models.CharField('Заголовок на главной', max_length=200, default="Добро пожаловать в Обменник!")
    main_subtitle = models.CharField('Подзаголовок на главной', max_length=300, default="Обменивайте криптовалюту быстро, безопасно и удобно.")
    popular_rates = models.ManyToManyField('RateMoney', blank=True, related_name='popular_rates', verbose_name='Популярные монеты')
    stablecoin_list = models.TextField('Список стейблкоинов', default='USDT, USDC, DAI,BUSD,USDP,TUSD,USDD,GUSD,FDUSD,PYUSD, USDE, FRAX, USDY, USD Yield')

    xml_link = models.CharField('XML', max_length=100, default='xml_export/', help_text='Адрес для файла экспорта курсов в xml')
    fee = models.FloatField('Комиссия обменника, в %', default='1.00')
    content = CKEditor5Field('Текст', config_name="default",
                             default='Благодарим за выбор нашего сервиса! Для завершения обмена просьба написать оператору и договориться на время посещения офиса')

    class Meta:
        verbose_name = 'Настройки обменника'
        verbose_name_plural = '5 Настройки обменника'

    def __str__(self):
        if self.name == '': return 'Обменник без имени'
        return self.name

    def clean(self):
        if SiteSetup.objects.exclude(id=self.id).exists():
            raise ValidationError("Можно создать только один комплект настроек сайта.")

    def save(self, *args, **kwargs):
        self.full_clean()
        self.stablecoin_list = ','.join(
            sorted(list(set(xxx.strip().upper() for xxx in self.stablecoin_list.split(',') if xxx.strip() != ''))))
        super().save(*args, **kwargs)

        cache.set('SiteSetup', self)

    @classmethod
    def load(cls):
        config = cls.objects.first()
        cache.set('SiteSetup', config)
        return config


class SiteDocument(models.Model):
    doc_type = models.CharField("Тип документа", choices=DocumentType.choices, max_length=50, unique=True, default=DocumentType.RULES)
    slug = models.SlugField(max_length=64, unique=True, editable=False)
    content = CKEditor5Field(config_name="default")

    def save(self, *args, **kwargs):
        self.slug = self.doc_type  # автоматически копирует значение doc_type
        super().save(*args, **kwargs)

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "6 Документы"

    def __str__(self):
        return self.doc_type
