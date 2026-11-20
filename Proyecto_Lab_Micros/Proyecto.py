import django
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404

# ==============================================================================
# 1. MODELO DE DATOS (Va en: usuarios/models.py)
# ==============================================================================

class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        ALUMNO = 'ALUMNO', 'Alumno'
        LABORATORISTA = 'LABORATORISTA', 'Laboratorista'
        ADMINISTRADOR = 'ADMINISTRADOR', 'Administrador'

    class Estatus(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        CON_PRESTAMO = 'CON_PRESTAMO', 'Con préstamo'
        SANCIONADO = 'SANCIONADO', 'Sancionado'

    # REQ-1.0 / 1.0.3: Boleta de 10 dígitos o número de credencial único
    boleta_credencial = models.CharField(
        max_length=20, 
        unique=True, 
        verbose_name="Boleta / Credencial"
    )
    correo_institucional = models.EmailField(
        unique=True, 
        verbose_name="Correo Institucional"
    )
    rol = models.CharField(
        max_length=15, 
        choices=Rol.choices, 
        default=Rol.ALUMNO
    )
    estatus = models.CharField(
        max_length=15, 
        choices=Estatus.choices, 
        default=Estatus.ACTIVO
    )

    # Identificador principal para el inicio de sesión
    USERNAME_FIELD = 'boleta_credencial'
    REQUIRED_FIELDS = ['username', 'correo_institucional', 'first_name', 'last_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.boleta_credencial})"


# ==============================================================================
# 2. FORMULARIOS Y VALIDACIONES (Va en: usuarios/forms.py)
# ==============================================================================

class RegistroAlumnoForm(django.forms.ModelForm):
    password = django.forms.CharField(
        widget=django.forms.PasswordInput, 
        min_length=8, 
        label="Clave de acceso"
    )
    confirmar_password = django.forms.CharField(
        widget=django.forms.PasswordInput, 
        label="Confirmar clave"
    )

    class Meta:
        model = Usuario
        fields = ['boleta_credencial', 'correo_institucional', 'password']

    def clean_boleta_credencial(self):
        boleta = self.cleaned_data.get('boleta_credencial')
        # REQ-1.0.1 / 1.0.2: Validar exactamente 10 dígitos numéricos
        if not boleta.isdigit() or len(boleta) != 10:
            raise ValidationError("El número de boleta debe contener exactamente 10 dígitos numéricos.")
        if Usuario.objects.filter(boleta_credencial=boleta).exists():
            raise ValidationError("Este número de boleta ya se encuentra registrado.")
        return boleta

    def clean_correo_institucional(self):
        correo = self.cleaned_data.get('correo_institucional')
        # REQ-1.0.2: Validar dominio @alumno.ipn.mx
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


# ==============================================================================
# 3. VISTAS Y CONTROLADORES (Va en: usuarios/views.py)
# ==============================================================================

def registrar_alumno(request):
    """REQ-1.0.2: Registro de nuevos alumnos con validaciones."""
    if request.method == 'POST':
        form = RegistroAlumnoForm(request.POST)
        if form.is_valid():
            alumno = form.save(commit=False)
            alumno.username = alumno.boleta_credencial
            alumno.set_password(form.cleaned_data['password'])
            alumno.rol = Usuario.Rol.ALUMNO
            alumno.save()
            return redirect('login')
    else:
        form = RegistroAlumnoForm()
    return render(request, 'usuarios/registro_alumno.html', {'form': form})


@login_required
def mi_cuenta(request):
    """REQ-1.0.5: Pantalla 'Mi cuenta' del usuario."""
    return render(request, 'usuarios/mi_cuenta.html', {'usuario': request.user})


@login_required
@user_passes_test(lambda u: u.rol == Usuario.Rol.ADMINISTRADOR)
def padron_usuarios(request):
    """REQ-1.0.4: Gestión y búsqueda en el padrón de usuarios (Solo Admin)."""
    query = request.GET.get('q', '')
    if query:
        usuarios = Usuario.objects.filter(
            Q(first_name__icontains=query) | 
            Q(last_name__icontains=query) | 
            Q(boleta_credencial__icontains=query)
        )
    else:
        usuarios = Usuario.objects.all()
    return render(request, 'usuarios/padron_usuarios.html', {'usuarios': usuarios, 'query': query})


@login_required
@user_passes_test(lambda u: u.rol == Usuario.Rol.ADMINISTRADOR)
def eliminar_usuario(request, user_id):
    """REQ-1.5: Restricción para eliminar perfiles con adeudos o préstamos activos."""
    usuario_a_eliminar = get_object_or_404(Usuario, id=user_id)
    
    # Verificar si tiene estatus sancionado o préstamos activos vinculados
    tiene_prestamos_activos = hasattr(usuario_a_eliminar, 'prestamos_recibidos') and usuario_a_eliminar.prestamos_recibidos.filter(estatus='ACTIVO').exists()
    
    if usuario_a_eliminar.estatus == Usuario.Estatus.SANCIONADO or tiene_prestamos_activos:
        return render(request, 'usuarios/error_eliminacion.html', {
            'error': 'No se puede eliminar: el alumno tiene préstamos activos o adeudos pendientes.'
        })
        
    usuario_a_eliminar.delete()
    return redirect('padron_usuarios')