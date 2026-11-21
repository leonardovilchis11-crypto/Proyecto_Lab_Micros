from reservas.models import Adeudo, SolicitudPrestamo
from reservas.services import obtener_alertas_prestamo, obtener_prestamos_vencidos


def notificaciones_interfaz(request):
    if not getattr(request, 'user', None) or not request.user.is_authenticated:
        return {'notificaciones': [], 'notificaciones_no_leidas': 0}

    notifs = []
    usuario = request.user

    if getattr(usuario, 'rol', None) == 'ALUMNO':
        for alerta in obtener_alertas_prestamo(usuario):
            notifs.append({
                'titulo': 'Aviso de préstamo',
                'mensaje': alerta,
                'tipo': 'warning',
            })

        adeudos_activos = Adeudo.objects.filter(alumno=usuario, estatus='ACTIVO').count()
        if adeudos_activos:
            notifs.append({
                'titulo': 'Adeudo pendiente',
                'mensaje': f'Tienes {adeudos_activos} adeudo(s) activo(s) pendiente(s) de liquidar.',
                'tipo': 'danger',
            })

        solicitudes_listas = SolicitudPrestamo.objects.filter(
            alumno=usuario,
            estatus=SolicitudPrestamo.Estatus.CONFIRMADA,
        ).count()
        if solicitudes_listas:
            notifs.append({
                'titulo': 'Solicitud confirmada',
                'mensaje': f'Tienes {solicitudes_listas} solicitud(es) confirmada(s) lista(s) para pasar al laboratorio.',
                'tipo': 'info',
            })
    else:
        vencidos = len(obtener_prestamos_vencidos())
        if vencidos:
            notifs.append({
                'titulo': 'Préstamos vencidos',
                'mensaje': f'Hay {vencidos} préstamo(s) vencido(s) por revisar.',
                'tipo': 'danger',
            })

        pendientes = SolicitudPrestamo.objects.filter(
            estatus__in=(
                SolicitudPrestamo.Estatus.CONFIRMADA,
                SolicitudPrestamo.Estatus.SIN_CONFIRMAR,
            )
        ).count()
        if pendientes:
            notifs.append({
                'titulo': 'Solicitudes pendientes',
                'mensaje': f'Hay {pendientes} solicitud(es) de material pendiente(s) de atender.',
                'tipo': 'warning',
            })

    return {
        'notificaciones': notifs,
        'notificaciones_no_leidas': len(notifs),
    }

