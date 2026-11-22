import logging
import smtplib
from datetime import datetime, time, timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import Adeudo, HistorialAdeudo, SolicitudPrestamo
from usuarios.models import Usuario


logger = logging.getLogger(__name__)
_SMTP_CONFIGURATION_WARNING_EMITTED = False


class ReservaService:
    """Reglas de negocio de disponibilidad operativa y reservas (Req. 3.4 y 4.0)."""

    # Bandera temporal para pruebas: permite reservar en fines de semana y cualquier bloque horario
    MODO_PRUEBAS_SIN_RESTRICCION_HORARIA = True

    BLOQUES_HORARIOS = [
        '07:00 - 08:30',
        '08:30 - 10:00',
        '10:00 - 11:30',
        '11:30 - 13:00',
        '13:00 - 14:30',
        '14:30 - 16:00',
        '16:00 - 17:30',
        '17:30 - 19:00',
        '19:00 - 20:30',
        '20:30 - 22:00',
    ]

    @classmethod
    def es_dia_habil(cls, fecha_obj):
        """Retorna True si es lunes (0) a viernes (4); en modo pruebas siempre True."""
        if cls.MODO_PRUEBAS_SIN_RESTRICCION_HORARIA:
            return True
        return fecha_obj.weekday() < 5

    @classmethod
    def obtener_siguiente_dia_habil(cls, fecha_referencia):
        """Calcula el próximo día hábil a partir de la fecha dada."""
        siguiente = fecha_referencia + timedelta(days=1)
        while not cls.es_dia_habil(siguiente):
            siguiente += timedelta(days=1)
        return siguiente

    @classmethod
    def validar_fecha_y_bloque(cls, fecha_obj, bloque, ahora=None):
        """Valida bloque oficial; en modo pruebas omite restricciones de día/hora."""
        if bloque not in cls.BLOQUES_HORARIOS:
            raise ValueError('Selecciona un bloque horario válido dentro del horario operativo.')

        if cls.MODO_PRUEBAS_SIN_RESTRICCION_HORARIA:
            return

        if not cls.es_dia_habil(fecha_obj):
            raise ValueError(
                'El servicio de reservas y préstamos está disponible únicamente de lunes a viernes (Req. 3.4).'
            )

        momento_actual = timezone.localtime(ahora) if ahora else timezone.localtime()
        if fecha_obj < momento_actual.date():
            raise ValueError('No puedes reservar una fecha que ya pasó.')

        if fecha_obj == momento_actual.date():
            hora_inicio = time.fromisoformat(bloque.split('-')[0].strip())
            if hora_inicio <= momento_actual.time().replace(tzinfo=None):
                raise ValueError(
                    'Para hoy, elige un bloque que todavía no haya comenzado.'
                )


def _fecha_limite_datetime(valor):
    if not valor:
        return None
    try:
        fecha = datetime.fromisoformat(valor)
    except (TypeError, ValueError):
        return None
    if timezone.is_naive(fecha):
        fecha = timezone.make_aware(fecha)
    return timezone.localtime(fecha)


def obtener_alertas_prestamo(alumno, ahora=None):
    ahora = timezone.localtime(ahora or timezone.now())
    alertas = []
    solicitudes = SolicitudPrestamo.objects.filter(
        alumno=alumno,
        estatus=SolicitudPrestamo.Estatus.ATENDIDA,
    )
    for solicitud in solicitudes:
        for equipo in solicitud.equipos:
            if not isinstance(equipo, dict) or not equipo.get('prestamo_activo') or equipo.get('devuelto'):
                continue
            limite = _fecha_limite_datetime(equipo.get('fecha_limite'))
            if not limite:
                continue
            alertas.append({
                'id': f"{solicitud.folio}:{equipo.get('id_unico', '')}",
                'folio': solicitud.folio,
                'material': equipo.get('nombre', 'Equipo de laboratorio'),
                'id_material': equipo.get('id_unico', ''),
                'fecha_limite': limite.isoformat(),
                'fecha_aviso': (limite - timedelta(minutes=15)).isoformat(),
            })
    return alertas


def obtener_prestamos_vencidos(ahora=None, alumno=None):
    ahora = timezone.localtime(ahora or timezone.now())
    solicitudes = SolicitudPrestamo.objects.filter(
        estatus=SolicitudPrestamo.Estatus.ATENDIDA,
    ).select_related('alumno')
    if alumno is not None:
        solicitudes = solicitudes.filter(alumno=alumno)

    vencidos = []
    for solicitud in solicitudes:
        for equipo in solicitud.equipos:
            if not isinstance(equipo, dict) or not equipo.get('prestamo_activo') or equipo.get('devuelto'):
                continue
            limite = _fecha_limite_datetime(equipo.get('fecha_limite'))
            if limite and limite <= ahora:
                vencidos.append({
                    'solicitud': solicitud,
                    'equipo': equipo,
                    'fecha_limite': limite,
                })
    return vencidos


def _enviar_notificacion_vencimiento(adeudo, equipo):
    global _SMTP_CONFIGURATION_WARNING_EMITTED
    if settings.EMAIL_BACKEND.endswith('console.EmailBackend'):
        if not _SMTP_CONFIGURATION_WARNING_EMITTED:
            logger.warning(
                'Los avisos de vencimiento no se envían: configura el servidor SMTP '
                'mediante variables de entorno.',
            )
            _SMTP_CONFIGURATION_WARNING_EMITTED = True
        return False
    destinatario = adeudo.alumno.correo_institucional
    if not destinatario:
        logger.error(
            'No se envió el aviso de vencimiento de %s: el alumno no tiene correo registrado.',
            adeudo.solicitud.folio,
        )
        return False

    limite = _fecha_limite_datetime(equipo.get('fecha_limite'))
    limite_texto = (
        limite.strftime('%d/%m/%Y %H:%M') if limite else 'no disponible'
    )
    asunto = f'Préstamo vencido: {adeudo.solicitud.folio}'
    mensaje = (
        f'Hola {_nombre_para_correo(adeudo.alumno)},\n\n'
        f'El préstamo {adeudo.solicitud.folio} venció y aún no se registra la '
        f'devolución del equipo {adeudo.material} ({adeudo.id_material}).\n'
        f'Fecha límite: {limite_texto}.\n\n'
        'Comunícate con el laboratorio para regularizar la devolución.'
    )
    try:
        enviados = send_mail(
            asunto,
            mensaje,
            settings.DEFAULT_FROM_EMAIL,
            [destinatario],
            fail_silently=False,
        )
    except (smtplib.SMTPException, OSError):
        logger.exception(
            'Falló el envío del aviso de vencimiento para %s.',
            adeudo.solicitud.folio,
        )
        return False
    if enviados != 1:
        logger.error(
            'El aviso de vencimiento para %s no fue aceptado por el backend de correo.',
            adeudo.solicitud.folio,
        )
        return False

    adeudo.correo_vencimiento_enviado_en = timezone.now()
    adeudo.save(update_fields=['correo_vencimiento_enviado_en'])
    return True


def _nombre_para_correo(alumno):
    nombre = f'{alumno.first_name} {alumno.last_name}'.strip()
    return nombre or alumno.boleta_credencial


def sincronizar_adeudos(ahora=None, alumno=None, actor=None):
    ahora = timezone.localtime(ahora or timezone.now())
    notificaciones_enviadas = 0
    solicitudes = SolicitudPrestamo.objects.filter(
        estatus=SolicitudPrestamo.Estatus.ATENDIDA,
    ).select_related('alumno')
    if alumno is not None:
        solicitudes = solicitudes.filter(alumno=alumno)

    for solicitud in solicitudes:
        for equipo in solicitud.equipos:
            if not isinstance(equipo, dict) or not equipo.get('prestamo_activo'):
                continue

            tipo = None
            motivo = ''
            if equipo.get('devuelto') and equipo.get('estatus_devolucion') == 'DANADO':
                tipo = Adeudo.Tipo.DANADO
                motivo = equipo.get('observaciones_devolucion') or 'Material recibido dañado.'
            elif not equipo.get('devuelto'):
                limite = _fecha_limite_datetime(equipo.get('fecha_limite'))
                if limite and limite <= ahora:
                    tipo = Adeudo.Tipo.NO_DEVUELTO
                    motivo = 'El material no se devolvió antes de la fecha límite.'

            id_material = str(equipo.get('id_unico', '')).strip()
            if not tipo or not id_material:
                continue

            adeudo, creado = Adeudo.objects.get_or_create(
                solicitud=solicitud,
                id_material=id_material,
                defaults={
                    'alumno': solicitud.alumno,
                    'material': equipo.get('nombre', 'Equipo de laboratorio'),
                    'tipo': tipo,
                    'motivo': motivo,
                    'creado_por': actor,
                },
            )
            if creado:
                HistorialAdeudo.objects.create(
                    adeudo=adeudo,
                    actor=actor,
                    accion=HistorialAdeudo.Accion.REGISTRADO,
                    detalle=f'{adeudo.get_tipo_display()}: {motivo}',
                )
            elif adeudo.estatus == Adeudo.Estatus.ACTIVO and adeudo.tipo != tipo:
                adeudo.tipo = tipo
                adeudo.motivo = motivo
                adeudo.save(update_fields=['tipo', 'motivo'])
                HistorialAdeudo.objects.create(
                    adeudo=adeudo,
                    actor=actor,
                    accion=HistorialAdeudo.Accion.ACTUALIZADO,
                    detalle=f'El tipo de adeudo se actualizó a {adeudo.get_tipo_display()}: {motivo}',
                )

            if (
                adeudo.estatus == Adeudo.Estatus.ACTIVO
                and solicitud.alumno.estatus != Usuario.Estatus.SANCIONADO
            ):
                solicitud.alumno.estatus = Usuario.Estatus.SANCIONADO
                solicitud.alumno.save(update_fields=['estatus'])

            if (
                tipo == Adeudo.Tipo.NO_DEVUELTO
                and adeudo.estatus == Adeudo.Estatus.ACTIVO
                and adeudo.correo_vencimiento_enviado_en is None
                and _enviar_notificacion_vencimiento(adeudo, equipo)
            ):
                notificaciones_enviadas += 1

    return notificaciones_enviadas


