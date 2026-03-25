from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import Money

User = get_user_model()


class ExchangeForm(forms.Form):
    left_money = forms.CharField()
    right_money = forms.CharField()
    left_amount = forms.DecimalField(min_value=0.00001, decimal_places=8, max_digits=20)
    right_amount = forms.DecimalField(required=False, decimal_places=8, max_digits=20)
    client_address = forms.CharField(max_length=255, required=True)
    client_memo = forms.CharField(max_length=255, required=False)
    agree = forms.BooleanField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.initial.get("left_money"):
            left_obj = Money.objects.filter(deposit=True, name_short="BTC", chain_long="Bitcoin").first()
            if left_obj:
                self.initial["left_money"] = f"{left_obj.name_short} {left_obj.chain_long}"

        if not self.initial.get("right_money"):
            right_obj = Money.objects.filter(withdraw=True, name_short="USDT", chain_long="TRC20").first()
            if right_obj:
                self.initial["right_money"] = f"{right_obj.name_short} {right_obj.chain_long}"

        if not self.initial.get("left_amount"):
            self.initial["left_amount"] = 1

    def clean_left_money(self):
        value = self.cleaned_data.get("left_money")
        return self._validate_money(value, deposit=True)

    def clean_right_money(self):
        value = self.cleaned_data.get("right_money")
        return self._validate_money(value, withdraw=True)

    def _validate_money(self, raw_value, deposit=False, withdraw=False):
        if not raw_value or " " not in raw_value:
            raise forms.ValidationError("Неверный формат монеты.")

        name_short, chain_long = raw_value.split(" ", 1)
        qs = Money.objects.filter(
            name_short__iexact=name_short.strip(),
            chain_long__iexact=chain_long.strip()
        )

        if deposit:
            qs = qs.filter(deposit=True, adeposit=True)
        if withdraw:
            qs = qs.filter(withdraw=True, awithdraw=True)

        money = qs.first()
        if not money:
            raise forms.ValidationError("Указанная монета недоступна для обмена.")

        return money

    def clean(self):
        cleaned_data = super().clean()
        return cleaned_data


class SignUpForm(UserCreationForm):
    email = forms.EmailField(required=True, label='Email')
    referral_code = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'email')

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Пользователь с таким email уже существует.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class ExchangeConfirmForm(forms.Form):
    from_money_id = forms.IntegerField(widget=forms.HiddenInput())
    to_money_id = forms.IntegerField(widget=forms.HiddenInput())
    amount = forms.DecimalField(decimal_places=8, min_value=Decimal("0.00001"))
