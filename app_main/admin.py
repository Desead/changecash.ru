from django.contrib import admin
from app_main.models import City, Merchant, Money, SiteSetup, RateMoney, Order, PartnerAccrual, SiteDocument, UserProfile
from lp.getmoney import GetMoney

admin.site.site_title = 'Настройки'
admin.site.site_header = 'Панель управления обменником'


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    save_on_top = True
    actions_on_bottom = True
    actions = ['get_merchant_money', ]
    search_fields = ("name",)
    list_display = ("name", 'status', 'spot_taker_fee', 'spot_maker_fee')

    @admin.action(description='Загрузить все монеты')
    def get_merchant_money(self, request, queryset):
        total_created = 0
        total_updated = 0

        for obj in queryset:
            all_money = GetMoney(obj).get_money()

            if not isinstance(all_money, list):
                self.message_user(request, f"Ошибка загрузки монет для {obj}: {all_money}")
                continue

            for data in all_money:
                lookup = {
                    'merchant': data['merchant'],
                    'money_type': data['money_type'],
                    'name_short': data['name_short'],
                    'chain_long': data.get('chain_long'),
                }
                defaults = data.copy()
                defaults.pop('merchant', None)
                defaults.pop('money_type', None)
                defaults.pop('name_short', None)
                defaults.pop('chain_long', None)

                _, created = Money.objects.update_or_create(
                    **lookup,
                    defaults=defaults,
                )
                if created:
                    total_created += 1
                else:
                    total_updated += 1

        self.message_user(request, f"Загрузка монет завершена: создано {total_created}, обновлено {total_updated}")

    @admin.action(description='Быстрое удаление мерчантов')
    def delete_merchant(self, request, queryset):
        queryset.delete()
        self.message_user(request, f"Выбранные мерчанты удалены")


@admin.register(Money)
class Moneyadmin(admin.ModelAdmin):
    save_on_top = True
    actions_on_bottom = True
    search_fields = ('name_short', 'name_long', 'chain_short', 'chain_long',)
    list_filter = ('money_type', 'merchant', 'adeposit', 'awithdraw', 'deposit', 'withdraw')
    actions = ('delete_money', 'deposit_money_yes', 'deposit_money_no', 'withdraw_money_yes', 'withdraw_money_no', 'all_yes', 'all_no',)
    autocomplete_fields = ("merchant",)
    list_display = ('name_short', 'chain_long', 'money_type', 'merchant', 'adeposit', 'awithdraw', 'deposit', 'withdraw', 'min_withdraw',
                    'reserv')
    list_editable = ('deposit', 'withdraw', 'reserv',)

    @admin.action(description='Быстрое удаление монет')
    def delete_money(self, request, queryset):
        queryset.delete()
        self.message_user(request, f"Выбранные монеты удалены")

    @admin.action(description='Разрешить приём и отправку')
    def all_yes(self, request, queryset):
        queryset.update(deposit=True, withdraw=True)
        self.message_user(request, f"Выбранные монеты нельзя отправлять")

    @admin.action(description='Запретить приём и отправку')
    def all_no(self, request, queryset):
        queryset.update(withdraw=False, deposit=False)
        self.message_user(request, f"Выбранные монеты нельзя отправлять")

    readonly_fields = ('adeposit', 'awithdraw')
    fieldsets = (
        ("Основная информация", {
            'fields': (
                'merchant', 'money_type', ('name_short', 'name_long'),
                ('chain_short', 'chain_long'), 'api_format', 'nominal',
                'money_digits', 'reserv'
            )
        }),
        ("Иконки", {
            'classes': ('collapse',),
            'fields': ('icon_file', 'icon_url')
        }),
        ("Интеграция с BestChange", {
            'classes': ('collapse',),
            'fields': ('best_num', 'best_id')
        }),
        ("Доступность", {
            'classes': ('collapse',),
            'fields': (('deposit', 'withdraw'), ('adeposit', 'awithdraw'), ('stablecoin', 'memo'))
        }),
        ("Минимумы и лоты", {
            'classes': ('collapse',),
            'fields': (
                ('min_deposit', 'min_withdraw'),
                ('min_trade', 'max_trade', 'min_trade_usdt'),
            )
        }),
        ("Комиссии на ввод", {
            'classes': ('collapse',),
            'fields': (
                ('fee_deposit_fix', 'fee_deposit_per',),
                ('fee_deposit_min', 'fee_deposit_max',),
            )
        }),
        ("Комиссии на вывод", {
            'classes': ('collapse',),
            'fields': (
                ('fee_withdraw_fix', 'fee_withdraw_per',),
                ('fee_withdraw_min', 'fee_withdraw_max',),
            )
        }),
        ("Подтверждения сети", {
            'classes': ('collapse',),
            'fields': (('confirm_deposit', 'confirm_withdraw'),)
        }),
    )


@admin.register(City)
class CityAdmin(admin.ModelAdmin):
    save_on_top = True
    search_fields = ('name', 'code')
    list_display = ('name', 'code', 'is_active')
    list_filter = ('is_active',)
    list_editable = ('is_active',)
    ordering = ('-is_active', 'name',)


@admin.register(SiteSetup)
class SiteSetupAdmin(admin.ModelAdmin):
    save_on_top = True
    filter_horizontal = ['popular_rates']
    fieldsets = (
        ("Общие настройки", {
            'fields': ('name', 'pause', 'logo', 'fee', 'partner_percent', 'stablecoin_list', 'xml_link',)
        }),
        ("SEO", {
            'classes': ('collapse',),
            'fields': ('seo_title', 'seo_description', 'seo_keywords', 'code_to_head')
        }),
        ("Контакты", {
            'classes': ('collapse',),
            'fields': ('contact_email', 'contact_telegram', 'news_telegram', 'news_vk')
        }),
        ("Контент на главной", {
            'classes': ('collapse',),
            'fields': ('main_title', 'main_subtitle', 'popular_rates',)
        }),
        ("Текст для подтверждения заявки", {
            'classes': ('collapse',),
            'fields': ('content',)
        }),
    )


@admin.register(RateMoney)
class RateMoneyAdmin(admin.ModelAdmin):
    save_on_top = True
    actions_on_bottom = True
    list_display = ('money_left', 'money_right', 'rate_ask', 'rate_bid', 'updated_rate',)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    save_on_top = True
    search_fields = ('user__username', 'user__email', 'referral_code')
    list_display = ('user', 'referral_code', 'referrer', 'partner_balance', 'partner_total_earned', 'created_at')
    readonly_fields = ('created_at',)
    autocomplete_fields = ('user', 'referrer')


@admin.register(PartnerAccrual)
class PartnerAccrualAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ('created_at', 'partner_user', 'referred_user', 'order', 'source_amount', 'source_currency', 'source_amount_usdt', 'percent',
                    'reward_amount')
    search_fields = ('partner_user__username', 'referred_user__username', 'order__number')
    autocomplete_fields = ('partner_user', 'referred_user', 'order')
    readonly_fields = ('created_at',)


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ('number', 'user', 'status', 'time_created', 'formatted_left_count', 'left_money', 'left_chain', 'formatted_right_count', 'right_money',
                    'right_chain',)
    list_filter = ('status', 'user')
    search_fields = ('number', 'user__username', 'client_address', 'exchange_address')
    autocomplete_fields = ('user',)
    readonly_fields = ('number', 'time_created', 'time_final')
    fieldsets = (
        ("Основная информация", {
            'fields': ('number', 'user', 'status', ('time_created', 'time_final'),),
            'classes': ('wide',),
        }),
        ("Монета слева", {
            'fields': ('left_money', 'left_chain', 'left_lp', 'left_count'),
            'classes': ('collapse',),
        }),
        ("Монета справа", {
            'fields': ('right_money', 'right_chain', 'right_lp', 'right_count'),
            'classes': ('collapse',),
        }),
        ("Данные клиента", {
            'fields': ('client_address', 'client_memo'),
            'classes': ('collapse',),
        }),
        ("Данные обменника", {
            'fields': ('exchange_address', 'exchange_memo'),
            'classes': ('collapse',),
        }),
        ("Транзакции", {
            'fields': ('hash_left', 'hash_right', 'link_left', 'link_right'),
            'classes': ('collapse',),
        }),
        ("Финансы", {
            'fields': ('pl',),
            'classes': ('collapse',),
        }),
        ("Комментарий", {
            'fields': ('descriptions',),
            'classes': ('collapse',),
        }),
    )

    def formatted_left_count(self, obj):
        return self._format_decimal(obj.left_count)

    formatted_left_count.short_description = 'Получаем'

    def formatted_right_count(self, obj):
        return self._format_decimal(obj.right_count)

    formatted_right_count.short_description = 'Отдаём'

    def _format_decimal(self, value):
        if value is None:
            return "0.00"
        s = f"{value:.8f}".rstrip('0').rstrip('.')
        if '.' not in s:
            s += '.00'
        elif len(s.split('.')[-1]) == 1:
            s += '0'
        return s


@admin.register(SiteDocument)
class SiteDocumentAdmin(admin.ModelAdmin):
    save_on_top = True
    list_display = ('doc_type',)
