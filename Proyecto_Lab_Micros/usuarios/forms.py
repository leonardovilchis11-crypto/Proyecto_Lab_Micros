from django import forms
from django.core.exceptions import ValidationError
from .models import Usuario

class RegistroAlumnoForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150, 
        label="Nombre(s)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Leonardo'})
    )
    last_name = forms.CharField(
        max_length=150, 
        label="Apellidos",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Vilchis Martínez'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}), 
        min_length=8, 
        label="Clave de acceso"
    )
    confirmar_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}), 
        label="Confirmar clave"
    )

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'boleta_credencial', 'correo_institucional', 'password']
        widgets = {
            'boleta_credencial': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '10 dígitos numéricos'}),
            'correo_institucional': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'usuario@alumno.ipn.mx'}),
        }

    def clean_boleta_credencial(self):
        boleta = self.cleaned_data.get('boleta_credencial')
        if not boleta.isdigit() or len(boleta) != 10:
            raise ValidationError("El número de boleta debe contener exactamente 10 dígitos numéricos.")
        if Usuario.objects.filter(boleta_credencial=boleta).exists():
            raise ValidationError("Este número de boleta ya se encuentra registrado.")
        return boleta

    def clean_correo_institucional(self):
        correo = self.cleaned_data.get('correo_institucional')
        if not correo.endswith('@alumno.ipn.mx'):
            raise ValidationError("El correo electrónico debe pertenecer al dominio institucional @alumno.ipn.mx.")
        return correo

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirmar = cleaned_data.get("confirmar_password")
        if password and confirmar and password != confirmar:
            raise ValidationError("Las claves de acceso no coinciden.")
        return cleaned_data

class RegistroPersonalForm(forms.ModelForm):
    first_name = forms.CharField(max_length=150, label="Nombre(s)", widget=forms.TextInput(attrs={'class': 'form-control'}))
    last_name = forms.CharField(max_length=150, label="Apellidos", widget=forms.TextInput(attrs={'class': 'form-control'}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), min_length=8, label="Clave de acceso")
    confirmar_password = forms.CharField(widget=forms.PasswordInput(attrs={'class': 'form-control'}), label="Confirmar clave")

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'boleta_credencial', 'correo_institucional', 'rol', 'password']
        widgets = {
            'boleta_credencial': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de empleado / credencial'}),
            'correo_institucional': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'correo@ipn.mx'}),
            'rol': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo permitir elegir roles operativos (Laboratorista o Administrador)
        self.fields['rol'].choices = [
            (Usuario.Rol.LABORATORISTA, 'Laboratorista'),
            (Usuario.Rol.ADMINISTRADOR, 'Administrador'),
        ]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("confirmar_password"):
            raise ValidationError("Las claves de acceso no coinciden.")
        return cleaned_data

class RegistroLaboratoristaPublicoForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150,
        label="Nombre(s)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Roberto'})
    )
    last_name = forms.CharField(
        max_length=150,
        label="Apellidos",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Hernández López'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        min_length=8,
        label="Clave de acceso"
    )
    confirmar_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control'}),
        label="Confirmar clave"
    )

    class Meta:
        model = Usuario
        fields = ['first_name', 'last_name', 'boleta_credencial', 'correo_institucional', 'password']
        widgets = {
            'boleta_credencial': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Número de empleado / credencial'}),
            'correo_institucional': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'usuario@ipn.mx'}),
        }

    def clean_boleta_credencial(self):
        credencial = self.cleaned_data.get('boleta_credencial', '').strip()
        if Usuario.objects.filter(boleta_credencial=credencial).exists():
            raise ValidationError("Este número de credencial ya se encuentra registrado.")
        return credencial

    def clean_correo_institucional(self):
        correo = self.cleaned_data.get('correo_institucional', '').strip()
        if not correo.endswith('@ipn.mx'):
            raise ValidationError("El correo del laboratorista debe pertenecer al dominio institucional @ipn.mx.")
        return correo

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("confirmar_password"):
            raise ValidationError("Las claves de acceso no coinciden.")
        return cleaned_data
    