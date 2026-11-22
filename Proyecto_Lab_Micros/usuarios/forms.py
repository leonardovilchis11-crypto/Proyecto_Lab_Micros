from django import forms
from django.contrib.auth import authenticate
from django.core.exceptions import ValidationError
from .models import Usuario


def _generar_username_nombre_completo(usuario_obj, first_name, last_name):
    """Genera un username basado en el nombre completo, evitando duplicados."""
    nombre_completo = " ".join(
        parte.strip()
        for parte in [first_name or "", last_name or ""]
        if parte and parte.strip()
    )
    if not nombre_completo:
        return getattr(usuario_obj, "username", "") or ""

    base = nombre_completo
    candidato = base
    contador = 2
    while Usuario.objects.filter(username=candidato).exclude(pk=usuario_obj.pk).exists():
        candidato = f"{base} ({contador})"
        contador += 1
    return candidato


class LoginForm(forms.Form):
    nombre_usuario = forms.CharField(
        label="Nombre de usuario o nombre",
        max_length=150,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'id_nombre_usuario',
            'placeholder': 'Ej. Pablo_V o Pablo Vilchis',
            'autocomplete': 'off',
        }),
    )
    boleta_credencial = forms.CharField(
        label="Número de Boleta / Credencial",
        max_length=50,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'id': 'id_boleta_credencial',
            'placeholder': 'Ej. 2023350942',
            'autocomplete': 'off',
        }),
    )
    password = forms.CharField(
        label="Clave de acceso",
        strip=False,
        widget=forms.PasswordInput(
            render_value=True,
            attrs={
                'class': 'form-control',
                'id': 'id_password',
                'autocomplete': 'off',
            },
        ),
    )

    def __init__(self, request=None, *args, **kwargs):
        self.request = request
        self.user_cache = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        nombre_ingresado = " ".join((cleaned_data.get("nombre_usuario") or "").split())
        boleta_ingresada = (cleaned_data.get("boleta_credencial") or "").strip()
        password = cleaned_data.get("password")

        if nombre_ingresado and boleta_ingresada and password:
            usuario_obj = Usuario.objects.filter(
                boleta_credencial__iexact=boleta_ingresada
            ).first()

            nombre_valido = False
            if usuario_obj is not None:
                nombre_completo = " ".join(
                    f"{usuario_obj.first_name} {usuario_obj.last_name}".split()
                ).lower()
                nombre_ingresado_low = nombre_ingresado.lower()

                if (
                    (getattr(usuario_obj, "username", "") or "").lower() == nombre_ingresado_low
                    or (usuario_obj.first_name or "").strip().lower() == nombre_ingresado_low
                    or (nombre_completo and nombre_completo == nombre_ingresado_low)
                ):
                    nombre_valido = True

            if usuario_obj is not None and nombre_valido:
                valor_login = getattr(usuario_obj, Usuario.USERNAME_FIELD)
                self.user_cache = authenticate(
                    self.request,
                    username=valor_login,
                    password=password,
                )

            if self.user_cache is None:
                raise ValidationError(
                    "El nombre de usuario/nombre, la boleta o la clave de acceso son incorrectos."
                )
            if not self.user_cache.is_active:
                raise ValidationError("Esta cuenta se encuentra inactiva.")

        return cleaned_data

    def get_user(self):
        return self.user_cache


class RegistroAlumnoForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150,
        label="Nombre(s)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Pablo'})
    )
    last_name = forms.CharField(
        max_length=150,
        label="Apellidos",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Vilchis Martínez'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'class': 'form-control'}),
        min_length=8,
        label="Clave de acceso"
    )
    confirmar_password = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'class': 'form-control'}),
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

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.username = _generar_username_nombre_completo(
            usuario,
            self.cleaned_data.get("first_name"),
            self.cleaned_data.get("last_name"),
        )
        if commit:
            usuario.save()
        return usuario


class RegistroPersonalForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150,
        label="Nombre(s)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Pablo'})
    )
    last_name = forms.CharField(
        max_length=150,
        label="Apellidos",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Hernández López'})
    )
    password = forms.CharField(widget=forms.PasswordInput(render_value=True, attrs={'class': 'form-control'}), min_length=8, label="Clave de acceso")
    confirmar_password = forms.CharField(widget=forms.PasswordInput(render_value=True, attrs={'class': 'form-control'}), label="Confirmar clave")

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
        self.fields['rol'].choices = [
            (Usuario.Rol.LABORATORISTA, 'Laboratorista'),
            (Usuario.Rol.ADMINISTRADOR, 'Administrador'),
        ]

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("password") != cleaned_data.get("confirmar_password"):
            raise ValidationError("Las claves de acceso no coinciden.")
        return cleaned_data

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.username = _generar_username_nombre_completo(
            usuario,
            self.cleaned_data.get("first_name"),
            self.cleaned_data.get("last_name"),
        )
        if commit:
            usuario.save()
        return usuario


class RegistroLaboratoristaPublicoForm(forms.ModelForm):
    first_name = forms.CharField(
        max_length=150,
        label="Nombre(s)",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Pablo'})
    )
    last_name = forms.CharField(
        max_length=150,
        label="Apellidos",
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ej. Hernández López'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'class': 'form-control'}),
        min_length=8,
        label="Clave de acceso"
    )
    confirmar_password = forms.CharField(
        widget=forms.PasswordInput(render_value=True, attrs={'class': 'form-control'}),
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

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.username = _generar_username_nombre_completo(
            usuario,
            self.cleaned_data.get("first_name"),
            self.cleaned_data.get("last_name"),
        )
        if commit:
            usuario.save()
        return usuario


class EditarUsuarioForm(forms.ModelForm):
    class Meta:
        model = Usuario
        fields = [
            'first_name',
            'last_name',
            'boleta_credencial',
            'correo_institucional',
            'rol',
            'estatus',
            'is_active',
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'boleta_credencial': forms.TextInput(attrs={'class': 'form-control'}),
            'correo_institucional': forms.EmailInput(attrs={'class': 'form-control'}),
            'rol': forms.Select(attrs={'class': 'form-select'}),
            'estatus': forms.Select(attrs={'class': 'form-select'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        labels = {
            'first_name': 'Nombre(s)',
            'last_name': 'Apellidos',
            'is_active': 'Cuenta activa',
        }

    def clean_boleta_credencial(self):
        boleta = (self.cleaned_data.get('boleta_credencial') or '').strip()
        if not boleta:
            raise ValidationError("La boleta o credencial es obligatoria.")
        qs = Usuario.objects.filter(boleta_credencial__iexact=boleta)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Este número de boleta o credencial ya está registrado en otro usuario.")
        return boleta

    def clean_correo_institucional(self):
        correo = (self.cleaned_data.get('correo_institucional') or '').strip()
        if not correo:
            raise ValidationError("El correo institucional es obligatorio.")
        qs = Usuario.objects.filter(correo_institucional__iexact=correo)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("Este correo institucional ya está registrado en otro usuario.")
        return correo

    def save(self, commit=True):
        usuario = super().save(commit=False)
        usuario.username = _generar_username_nombre_completo(
            usuario,
            self.cleaned_data.get('first_name'),
            self.cleaned_data.get('last_name'),
        )
        if commit:
            usuario.save()
        return usuario

    