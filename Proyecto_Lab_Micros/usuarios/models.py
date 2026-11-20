from django.contrib.auth.models import AbstractUser
from django.db import models

class Usuario(AbstractUser):
    class Rol(models.TextChoices):
        ALUMNO = 'ALUMNO', 'Alumno'
        LABORATORISTA = 'LABORATORISTA', 'Laboratorista'
        ADMINISTRADOR = 'ADMINISTRADOR', 'Administrador'

    class Estatus(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        CON_PRESTAMO = 'CON_PRESTAMO', 'Con préstamo'
        SANCIONADO = 'SANCIONADO', 'Sancionado'

    boleta_credencial = models.CharField(max_length=20, unique=True, verbose_name="Boleta / Credencial")
    correo_institucional = models.EmailField(unique=True, verbose_name="Correo Institucional")
    rol = models.CharField(max_length=15, choices=Rol.choices, default=Rol.ALUMNO)
    estatus = models.CharField(max_length=15, choices=Estatus.choices, default=Estatus.ACTIVO)

    USERNAME_FIELD = 'boleta_credencial'
    REQUIRED_FIELDS = ['username', 'correo_institucional', 'first_name', 'last_name']

    @property
    def nombre_completo(self):
        nombre = f"{self.first_name} {self.last_name}".strip()
        return nombre or self.username or self.boleta_credencial or "Usuario sin nombre"

    def __str__(self):
        return f"{self.nombre_completo} ({self.boleta_credencial})"
    