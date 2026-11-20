from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError


class ValorarAdeudoForm(forms.Form):
    monto = forms.DecimalField(
        required=False,
        min_value=Decimal('0.01'),
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'min': '0.01',
            'step': '0.01',
            'placeholder': '0.00',
        }),
    )
    pieza_reposicion = forms.CharField(
        required=False,
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Pieza que debe reponerse',
        }),
    )

    def clean(self):
        cleaned_data = super().clean()
        monto = cleaned_data.get('monto')
        pieza = cleaned_data.get('pieza_reposicion', '').strip()
        if bool(monto) == bool(pieza):
            raise ValidationError('Registra un monto o una pieza de reposición, pero no ambos.')
        cleaned_data['pieza_reposicion'] = pieza
        return cleaned_data
