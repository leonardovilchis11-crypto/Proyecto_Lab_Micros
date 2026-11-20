from django.db import models
from django.utils import timezone

from usuarios.models import Usuario


class SolicitudPrestamo(models.Model):
    class Estatus(models.TextChoices):
        CONFIRMADA = 'CONFIRMADA', 'Confirmada'
        SIN_CONFIRMAR = 'SIN_CONFIRMAR', 'Sin confirmar'
        ATENDIDA = 'ATENDIDA', 'Atendida'
        CANCELADA = 'CANCELADA', 'Cancelada'

    folio = models.CharField(max_length=20, unique=True, blank=True)
    alumno = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='solicitudes_prestamo',
    )
    equipos = models.JSONField(default=list)
    fecha = models.DateField()
    bloque = models.CharField(max_length=20)
    estatus = models.CharField(
        max_length=15,
        choices=Estatus.choices,
        default=Estatus.CONFIRMADA,
    )
    creada = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('-creada',)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if not self.folio:
            self.folio = f'RES-{self.pk + 1000}'
            super().save(update_fields=['folio'])

    def __str__(self):
        return f'{self.folio} - {self.alumno}'


class Adeudo(models.Model):
    class Tipo(models.TextChoices):
        DANADO = 'DANADO', 'Material dañado'
        NO_DEVUELTO = 'NO_DEVUELTO', 'Material no devuelto'

    class Estatus(models.TextChoices):
        ACTIVO = 'ACTIVO', 'Activo'
        LIQUIDADO = 'LIQUIDADO', 'Liquidado'

    alumno = models.ForeignKey(
        Usuario,
        on_delete=models.PROTECT,
        related_name='adeudos',
    )
    solicitud = models.ForeignKey(
        SolicitudPrestamo,
        on_delete=models.PROTECT,
        related_name='adeudos',
    )
    id_material = models.CharField(max_length=80)
    material = models.CharField(max_length=200)
    tipo = models.CharField(max_length=15, choices=Tipo.choices)
    motivo = models.TextField()
    monto = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    pieza_reposicion = models.CharField(max_length=150, blank=True)
    estatus = models.CharField(
        max_length=12,
        choices=Estatus.choices,
        default=Estatus.ACTIVO,
    )
    creado_en = models.DateTimeField(default=timezone.now)
    creado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adeudos_registrados',
    )
    liquidado_en = models.DateTimeField(null=True, blank=True)
    correo_vencimiento_enviado_en = models.DateTimeField(null=True, blank=True)
    liquidado_por = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='adeudos_liquidados',
    )

    class Meta:
        ordering = ('-creado_en',)
        constraints = [
            models.UniqueConstraint(
                fields=('solicitud', 'id_material'),
                name='unique_adeudo_por_pieza_prestada',
            ),
        ]

    def __str__(self):
        return f'{self.solicitud.folio} - {self.id_material} ({self.get_estatus_display()})'


class HistorialAdeudo(models.Model):
    class Accion(models.TextChoices):
        REGISTRADO = 'REGISTRADO', 'Adeudo registrado'
        ACTUALIZADO = 'ACTUALIZADO', 'Adeudo actualizado'
        LIQUIDADO = 'LIQUIDADO', 'Adeudo liquidado'

    adeudo = models.ForeignKey(
        Adeudo,
        on_delete=models.CASCADE,
        related_name='historial',
    )
    actor = models.ForeignKey(
        Usuario,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='movimientos_adeudos',
    )
    accion = models.CharField(max_length=12, choices=Accion.choices)
    detalle = models.TextField()
    creado_en = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ('-creado_en',)
