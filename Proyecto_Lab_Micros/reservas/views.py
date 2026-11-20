import csv
import re
from datetime import datetime, time, timedelta
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q, Value
from django.db.models.functions import Concat
from django.core.paginator import Paginator
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from inventario.views import INVENTARIO_ITEMS
from usuarios.models import Usuario

from .forms import ValorarAdeudoForm
from .models import Adeudo, HistorialAdeudo, SolicitudPrestamo
from .services import (
    ReservaService,
    obtener_prestamos_vencidos,
    sincronizar_adeudos,
)


def _nombre_usuario(user):
    nombre = f"{user.first_name} {user.last_name}".strip()
    return nombre if nombre else user.boleta_credencial


def _valor_csv_seguro(valor):
    if isinstance(valor, str) and valor.startswith(('=', '+', '-', '@', '\t', '\r')):
        return f"'{valor}"
    return valor


def _fecha_formateada(fecha_texto):
    if hasattr(fecha_texto, 'strftime'):
        return fecha_texto.strftime('%d/%m/%Y')
    try:
        return datetime.strptime(fecha_texto, '%Y-%m-%d').strftime('%d/%m/%Y')
    except (TypeError, ValueError):
        return fecha_texto


def _fecha_hora_formateada(fecha_texto):
    if not fecha_texto:
        return ''
    try:
        return timezone.localtime(datetime.fromisoformat(fecha_texto)).strftime(
            '%d/%m/%Y %H:%M'
        )
    except (TypeError, ValueError):
        return fecha_texto


def _contexto_tabla(request, page_obj, campos_orden):
    query = request.GET.copy()
    query.pop('page', None)
    enlaces_orden = {}
    for campo in campos_orden:
        parametros = request.GET.copy()
        parametros['orden'] = campo
        parametros['direccion'] = (
            'desc'
            if request.GET.get('orden') == campo
            and request.GET.get('direccion') == 'asc'
            else 'asc'
        )
        parametros.pop('page', None)
        enlaces_orden[campo] = parametros.urlencode()
    return {
        'page_obj': page_obj,
        'query_params': query.urlencode(),
        'enlaces_orden': enlaces_orden,
    }


def _solicitud_a_fila(solicitud):
    return {
        'folio': solicitud.folio,
        'boleta': solicitud.alumno.boleta_credencial,
        'alumno': _nombre_usuario(solicitud.alumno),
        'equipos': ', '.join(
            f"{item['nombre']} (x{item['cantidad']})"
            for item in solicitud.equipos
        ),
        'fecha': solicitud.fecha.isoformat(),
        'fecha_formateada': _fecha_formateada(solicitud.fecha),
        'bloque': solicitud.bloque,
        'estatus': solicitud.estatus,
    }



def _obtener_carrito_normalizado(request):
    """
    Lee request.session['carrito_solicitud'] (alimentado desde catalogo/views.py)
    y consolida cantidades si el alumno agregó varias veces el mismo artículo.
    """
    raw_carrito = request.session.get('carrito_solicitud', [])
    consolidado = {}
    for item in raw_carrito:
        key = str(item.get('id'))
        if key not in consolidado:
            consolidado[key] = {
                'id': item.get('id'),
                'id_unico': item.get('id_unico', f"EQ-{item.get('id')}"),
                'nombre': item.get('nombre', 'Equipo de laboratorio'),
                'cantidad': int(item.get('cantidad', 1)),
            }
        else:
            # Si viene repetido sin campo 'cantidad' desde catálogo, sumamos 1
            if 'cantidad' not in item:
                consolidado[key]['cantidad'] += 1
    lista = list(consolidado.values())
    request.session['carrito_solicitud'] = lista
    return lista


def _inicializar_datos_demo(request):
    """Inicializa el préstamo de demostración en sesión si no existe."""
    if 'prestamos_activos_demo' not in request.session:
        request.session['prestamos_activos_demo'] = [
            {
                'folio': 'PREST-501',
                'boleta': getattr(request.user, 'boleta_credencial', '2022640001'),
                'equipos': 'Tarjeta de Desarrollo ESP32 NodeMCU (MIC-ESP32-003)',
                'articulos': [
                    {
                        'id': 3,
                        'id_unico': 'MIC-ESP32-003',
                        'nombre': 'Tarjeta de Desarrollo ESP32 NodeMCU',
                    },
                ],
                'hora_limite': 'Hoy, 14:30 hrs',
                'estatus': 'ACTIVO',
                'semaforo': 'amarillo',
            }
        ]


def _es_operador(user):
    return user.rol in ('LABORATORISTA', 'ADMINISTRADOR')


def _equipos_prestados(solicitud):
    return [
        equipo for equipo in solicitud.equipos
        if equipo.get('prestamo_activo') and not equipo.get('devuelto')
    ]


def _tiene_prestamos_activos(alumno):
    return any(
        _equipos_prestados(solicitud)
        for solicitud in SolicitudPrestamo.objects.filter(
            alumno=alumno,
            estatus=SolicitudPrestamo.Estatus.ATENDIDA,
        )
    )


def _actualizar_estatus_alumno(alumno):
    if Adeudo.objects.filter(alumno=alumno, estatus=Adeudo.Estatus.ACTIVO).exists():
        nuevo_estatus = Usuario.Estatus.SANCIONADO
    elif _tiene_prestamos_activos(alumno):
        nuevo_estatus = Usuario.Estatus.CON_PRESTAMO
    else:
        nuevo_estatus = Usuario.Estatus.ACTIVO

    if alumno.estatus != nuevo_estatus:
        alumno.estatus = nuevo_estatus
        alumno.save(update_fields=['estatus'])


def _sincronizar_inventario_prestamos():
    """Reconstituye el estado prestado del inventario desde los préstamos existentes."""
    solicitudes = SolicitudPrestamo.objects.filter(
        estatus=SolicitudPrestamo.Estatus.ATENDIDA,
    )
    estados = {}
    for solicitud in solicitudes:
        for equipo in solicitud.equipos:
            if equipo.get('prestamo_activo') and equipo.get('devuelto'):
                estados[equipo.get('id_unico')] = equipo.get(
                    'estatus_devolucion', 'DISPONIBLE'
                )
            elif equipo.get('prestamo_activo'):
                estados[equipo.get('id_unico')] = 'PRESTADO'

    for unidad in INVENTARIO_ITEMS:
        if unidad['id_unico'] in estados:
            unidad['estatus'] = estados[unidad['id_unico']]


def _generar_comprobante_pdf(solicitud, fecha_prestamo, fecha_limite, nombre):
    buffer = BytesIO()
    guinda = colors.HexColor('#6a1b29')
    gris_claro = colors.HexColor('#f2f3f5')
    estilos = getSampleStyleSheet()
    estilos.add(ParagraphStyle(
        name='NombreInstitucion',
        parent=estilos['Heading2'],
        alignment=TA_CENTER,
        textColor=guinda,
        fontSize=13,
        leading=16,
        spaceAfter=2,
    ))
    estilos.add(ParagraphStyle(
        name='SubtituloInstitucion',
        parent=estilos['Normal'],
        alignment=TA_CENTER,
        fontSize=9,
        leading=12,
    ))
    estilos.add(ParagraphStyle(
        name='TituloComprobante',
        parent=estilos['Heading1'],
        alignment=TA_CENTER,
        textColor=guinda,
        fontSize=16,
        leading=19,
        spaceAfter=4,
    ))
    estilos.add(ParagraphStyle(
        name='EtiquetaTabla',
        parent=estilos['BodyText'],
        fontName='Helvetica-Bold',
        fontSize=9,
        leading=12,
    ))
    estilos.add(ParagraphStyle(
        name='ValorTabla',
        parent=estilos['BodyText'],
        fontSize=9,
        leading=12,
    ))
    estilos.add(ParagraphStyle(
        name='EncabezadoTabla',
        parent=estilos['BodyText'],
        fontName='Helvetica-Bold',
        textColor=colors.white,
        fontSize=9,
        leading=12,
    ))
    estilos.add(ParagraphStyle(
        name='TituloSeccion',
        parent=estilos['BodyText'],
        fontName='Helvetica-Bold',
        textColor=guinda,
        fontSize=10,
        leading=13,
    ))
    estilos.add(ParagraphStyle(
        name='AvisoComprobante',
        parent=estilos['BodyText'],
        fontSize=9,
        leading=13,
    ))
    documento = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=42,
        leftMargin=42,
        topMargin=36,
        bottomMargin=42,
        title=f'Comprobante de préstamo {solicitud.folio}',
        author='Laboratorio de Microcontroladores ESIME',
    )
    carpeta_logos = (
        Path(settings.BASE_DIR)
        / 'usuarios'
        / 'static'
        / 'usuarios'
        / 'img'
    )
    logo_ipn = Image(
        str(carpeta_logos / 'logo-ipn.png'),
        width=48,
        height=56,
        kind='proportional',
    )
    logo_esime = Image(
        str(carpeta_logos / 'logo-esime.png'),
        width=56,
        height=56,
        kind='proportional',
    )

    def parrafo(texto, estilo='ValorTabla'):
        return Paragraph(escape(str(texto)), estilos[estilo])

    encabezado = Table(
        [[
            logo_ipn,
            [
                parrafo('INSTITUTO POLITÉCNICO NACIONAL', 'NombreInstitucion'),
                parrafo('ESIME Culhuacán - Laboratorio de Microcontroladores', 'SubtituloInstitucion'),
            ],
            logo_esime,
        ]],
        colWidths=[56, documento.width - 112, 56],
    )
    encabezado.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
        ('TOPPADDING', (0, 0), (-1, -1), 2),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
    ]))

    datos_prestamo = Table([
        [parrafo('Datos del préstamo', 'TituloSeccion'), ''],
        [parrafo('Folio', 'EtiquetaTabla'), parrafo(solicitud.folio)],
        [parrafo('Alumno', 'EtiquetaTabla'), parrafo(nombre)],
        [parrafo('Boleta', 'EtiquetaTabla'), parrafo(solicitud.alumno.boleta_credencial)],
        [parrafo('Fecha y hora de entrega', 'EtiquetaTabla'), parrafo(fecha_prestamo)],
        [parrafo('Límite de devolución', 'EtiquetaTabla'), parrafo(fecha_limite)],
    ], colWidths=[165, documento.width - 165])
    datos_prestamo.setStyle(TableStyle([
        ('SPAN', (0, 0), (-1, 0)),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#f8e9ec')),
        ('LINEBELOW', (0, 0), (-1, 0), 1, guinda),
        ('BACKGROUND', (0, 1), (0, -1), gris_claro),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#c8c8c8')),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))

    filas_equipos = [[
        parrafo('#', 'EncabezadoTabla'),
        parrafo('Equipo o material', 'EncabezadoTabla'),
        parrafo('Identificador único', 'EncabezadoTabla'),
    ]]
    for indice, equipo in enumerate(
        (equipo for equipo in solicitud.equipos if equipo.get('prestamo_activo')),
        start=1,
    ):
        filas_equipos.append([
            parrafo(indice),
            parrafo(equipo.get('nombre', 'Equipo')),
            parrafo(equipo.get('id_unico', '')),
        ])
    tabla_equipos = Table(
        filas_equipos,
        colWidths=[34, documento.width - 184, 150],
        repeatRows=1,
    )
    tabla_equipos.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), guinda),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#c8c8c8')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, gris_claro]),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 7),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    aviso = Table([[
        parrafo(
            'El alumno confirma la recepción del equipo y acepta devolverlo '
            'antes del límite indicado, conforme al reglamento del laboratorio.',
            'AvisoComprobante',
        ),
    ]], colWidths=[documento.width])
    aviso.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fff3cd')),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#e8cd80')),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))

    elementos = [
        encabezado,
        Spacer(1, 12),
        parrafo('COMPROBANTE DE PRÉSTAMO', 'TituloComprobante'),
        Spacer(1, 8),
        datos_prestamo,
        Spacer(1, 16),
        parrafo('Equipo(s) entregado(s)', 'TituloSeccion'),
        Spacer(1, 6),
        tabla_equipos,
        Spacer(1, 18),
        aviso,
    ]

    def pie_pagina(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(guinda)
        canvas.line(doc.leftMargin, 30, letter[0] - doc.rightMargin, 30)
        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(colors.HexColor('#555555'))
        canvas.drawString(doc.leftMargin, 18, 'ESIME Culhuacán - Laboratorio de Microcontroladores')
        canvas.drawRightString(letter[0] - doc.rightMargin, 18, f'Página {doc.page}')
        canvas.restoreState()

    documento.build(elementos, onFirstPage=pie_pagina, onLaterPages=pie_pagina)
    return buffer.getvalue()


# ==============================================================================
# VISTAS EXCLUSIVAS PARA EL PERFIL ALUMNO
# ==============================================================================

@login_required
@login_required
def vista_carrito(request):
    """Pantalla 14: Carrito de Solicitudes y Reserva (Req. 1.6, 3.1, 3.3.1, 3.4, 4.0)."""
    if request.user.rol != 'ALUMNO':
        return redirect('reservas:bandeja_solicitudes')

    # Regla Req. 3.4: Bloqueo automático sábado (5) y domingo (6)
    ahora = timezone.localtime()
    hoy = ahora.date()
    if not ReservaService.es_dia_habil(hoy):
        return redirect('reservas:fuera_horario')

    # Regla Req. 3.1 (REQ-10): Sincronizar préstamos vencidos y verificar adeudos activos
    sincronizar_adeudos(ahora=ahora, alumno=request.user)
    _actualizar_estatus_alumno(request.user)
    adeudos_activos = list(
        Adeudo.objects.filter(alumno=request.user, estatus=Adeudo.Estatus.ACTIVO)
    )
    bloqueado_por_adeudo = (
        request.user.estatus == Usuario.Estatus.SANCIONADO or len(adeudos_activos) > 0
    )

    carrito = _obtener_carrito_normalizado(request)
    bloques = ReservaService.BLOQUES_HORARIOS
    total_articulos = sum(item['cantidad'] for item in carrito)

    if request.method == 'POST':
        accion = request.POST.get('accion')

        if accion == 'actualizar_cantidad':
            item_id = str(request.POST.get('item_id'))
            nueva_cant = max(1, int(request.POST.get('cantidad', 1)))
            for item in carrito:
                if str(item['id']) == item_id:
                    item['cantidad'] = nueva_cant
                    break
            request.session['carrito_solicitud'] = carrito
            messages.success(request, 'Cantidad actualizada en tu carrito.')
            return redirect('reservas:carrito')

        elif accion == 'eliminar_item':
            item_id = str(request.POST.get('item_id'))
            carrito = [i for i in carrito if str(i['id']) != item_id]
            request.session['carrito_solicitud'] = carrito
            messages.info(request, 'Artículo eliminado del carrito.')
            return redirect('reservas:carrito')

        elif accion == 'confirmar_solicitud':
            if bloqueado_por_adeudo:
                messages.error(
                    request,
                    'Solicitud denegada (Req. 3.1): Tienes adeudos activos o préstamos vencidos. '
                    'Regulariza tu situación en el laboratorio antes de solicitar más material.'
                )
                return redirect('reservas:carrito')

            fecha_str = request.POST.get('fecha_reserva', '').strip()
            bloque = request.POST.get('bloque_horario', '').strip()
            acepto = request.POST.get('acepto_reglamento') == 'on'

            if not carrito:
                messages.error(request, 'Tu carrito está vacío. Agrega equipos desde el catálogo.')
                return redirect('reservas:carrito')

            if not acepto:
                messages.error(request, 'Debes aceptar el reglamento del laboratorio para continuar (Req. 1.6).')
                return redirect('reservas:carrito')

            try:
                fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
                ReservaService.validar_fecha_y_bloque(fecha_obj, bloque, ahora)
            except (TypeError, ValueError) as e:
                messages.error(request, str(e))
                return redirect('reservas:carrito')

            nueva_reserva = SolicitudPrestamo.objects.create(
                alumno=request.user,
                equipos=[
                    {
                        'id': item['id'],
                        'id_unico': item['id_unico'],
                        'nombre': item['nombre'],
                        'cantidad': item['cantidad'],
                    }
                    for item in carrito
                ],
                fecha=fecha_obj,
                bloque=bloque,
            )
            request.session['carrito_solicitud'] = []
            messages.success(
                request,
                f"Solicitud {nueva_reserva.folio} confirmada para el "
                f"{fecha_obj.strftime('%d/%m/%Y')} ({bloque})."
            )
            return redirect('reservas:mis_reservas')

    context = {
        'carrito': carrito,
        'total_articulos': total_articulos,
        'carrito_count': total_articulos,
        'bloques': bloques,
        'fecha_minima': hoy.strftime('%Y-%m-%d'),
        'hora_actual': ahora.strftime('%H:%M'),
        'estatus_alumno': request.user.estatus,
        'bloqueado_por_adeudo': bloqueado_por_adeudo,
        'adeudos_activos': adeudos_activos,
    }
    return render(request, 'reservas/carrito.html', context)

@login_required
def vista_mis_reservas(request):
    """Pantalla 15: Mis Reservas y Préstamos del Alumno (Req. 4.0.1, 4.1)."""
    if request.user.rol != 'ALUMNO':
        return redirect('reservas:bandeja_solicitudes')

    sincronizar_adeudos(alumno=request.user)
    ahora = timezone.localtime()
    solicitudes = SolicitudPrestamo.objects.filter(
        alumno=request.user,
        estatus__in=(SolicitudPrestamo.Estatus.CONFIRMADA, SolicitudPrestamo.Estatus.SIN_CONFIRMAR),
    )
    mis_reservas = []
    for solicitud in solicitudes:
        inicio_bloque = timezone.make_aware(datetime.combine(
            solicitud.fecha,
            time.fromisoformat(solicitud.bloque.split('-')[0].strip()),
        ))
        fila = _solicitud_a_fila(solicitud)
        fila['puede_cancelar'] = ahora < inicio_bloque
        mis_reservas.append(fila)

    prestamos_activos = []
    solicitudes_atendidas = SolicitudPrestamo.objects.filter(
        alumno=request.user,
        estatus=SolicitudPrestamo.Estatus.ATENDIDA,
    )
    for solicitud in solicitudes_atendidas:
        equipos_activos = _equipos_prestados(solicitud)
        if not equipos_activos:
            continue
        fecha_limite = next(
            (item.get('fecha_limite') for item in equipos_activos if item.get('fecha_limite')),
            '',
        )
        hora_limite = _fecha_hora_formateada(fecha_limite)
        if hora_limite:
            hora_limite = f'{hora_limite} hrs'
        prestamos_activos.append({
            'folio': solicitud.folio,
            'equipos': ', '.join(
                f"{item['nombre']} ({item['id_unico']})" for item in equipos_activos
            ),
            'hora_limite': hora_limite,
            'estatus': 'ACTIVO',
            'comprobante': True,
        })

    prestamos_activos.extend([
        p for p in request.session.get('prestamos_activos_demo', [])
        if p['boleta'] == request.user.boleta_credencial
    ])

    carrito = _obtener_carrito_normalizado(request)
    context = {
        'reservas_pendientes': mis_reservas,
        'prestamos_activos': prestamos_activos,
        'carrito_count': sum(i['cantidad'] for i in carrito),
        'historial_adeudos': Adeudo.objects.filter(
            alumno=request.user,
        ).prefetch_related('historial__actor'),
    }
    return render(request, 'reservas/mis_reservas.html', context)


@login_required
def cancelar_reserva_alumno(request, folio):
    """Acción Req. 4.1: Cancela la reserva del alumno si está antes del bloque horario."""
    if request.user.rol != 'ALUMNO':
        return redirect('reservas:bandeja_solicitudes')

    if request.method == 'POST':
        solicitud = SolicitudPrestamo.objects.filter(
            folio=folio,
            alumno=request.user,
            estatus__in=(SolicitudPrestamo.Estatus.CONFIRMADA, SolicitudPrestamo.Estatus.SIN_CONFIRMAR),
        ).first()
        if solicitud:
            inicio_bloque = timezone.make_aware(datetime.combine(
                solicitud.fecha,
                time.fromisoformat(solicitud.bloque.split('-')[0].strip()),
            ))
            if timezone.localtime() < inicio_bloque:
                solicitud.estatus = SolicitudPrestamo.Estatus.CANCELADA
                solicitud.save(update_fields=['estatus'])
                messages.success(request, f'La reserva {folio} fue cancelada.')
            else:
                messages.error(request, 'No puedes cancelar una reserva después del inicio del bloque.')
        else:
            messages.error(request, 'No se encontró una solicitud pendiente para cancelar.')
    return redirect('reservas:mis_reservas')


@login_required
def vista_fuera_horario(request):
    """Pantalla 19: Aviso de Servicio Fuera de Horario (Req. 3.4.1)."""
    if request.user.rol != 'ALUMNO':
        return redirect('reservas:bandeja_solicitudes')

    siguiente_habil = ReservaService.obtener_siguiente_dia_habil(timezone.localdate())
    carrito = _obtener_carrito_normalizado(request)
    context = {
        'siguiente_dia_habil': siguiente_habil,
        'siguiente_dia_texto': siguiente_habil.strftime('%d/%m/%Y'),
        'carrito_count': sum(i['cantidad'] for i in carrito),
    }
    return render(request, 'reservas/fuera_horario.html', context)


# ==============================================================================
# VISTA EXCLUSIVA PARA LABORATORISTA / ADMINISTRADOR (VENTANILLA)
# ==============================================================================

@login_required
def vista_registrar_prestamo(request):
    """Asistente de tres pasos para validar, seleccionar y entregar equipo."""
    if not _es_operador(request.user):
        return redirect('reservas:mis_reservas')

    _sincronizar_inventario_prestamos()
    session_key = 'prestamo_ventanilla'
    flujo = request.session.get(session_key, {})

    folio_inicial = request.GET.get('folio', '').strip()
    if folio_inicial:
        solicitud_inicial = SolicitudPrestamo.objects.filter(folio=folio_inicial).first()
        if (
            not solicitud_inicial
            or solicitud_inicial.estatus not in (
                SolicitudPrestamo.Estatus.CONFIRMADA,
                SolicitudPrestamo.Estatus.SIN_CONFIRMAR,
            )
        ):
            messages.error(request, 'La solicitud seleccionada ya no está pendiente de atención.')
            return redirect('reservas:bandeja_solicitudes')
        _sincronizar_inventario_prestamos()
        codigos_solicitados = {
            item.get('id_unico')
            for item in solicitud_inicial.equipos
            if item.get('id_unico')
        }
        ids_preseleccionados = [
            str(unidad['id'])
            for unidad in INVENTARIO_ITEMS
            if unidad['id_unico'] in codigos_solicitados
            and unidad['estatus'] == 'DISPONIBLE'
        ]
        flujo = {
            'alumno_id': solicitud_inicial.alumno_id,
            'boleta': solicitud_inicial.alumno.boleta_credencial,
            'folio': solicitud_inicial.folio,
            'equipo_ids': ids_preseleccionados,
        }
        request.session[session_key] = flujo

    try:
        paso = int(request.GET.get('paso', '1'))
    except ValueError:
        paso = 1
    if paso not in (1, 2, 3):
        paso = 1

    if request.method == 'POST':
        accion = request.POST.get('accion', '')
        if accion == 'cancelar':
            request.session.pop(session_key, None)
            messages.info(request, 'Se canceló el registro del préstamo.')
            return redirect('reservas:bandeja_solicitudes')

        if accion == 'validar_alumno':
            boleta = request.POST.get('boleta', '').strip()
            folio = request.POST.get('folio', '').strip()
            alumno = Usuario.objects.filter(
                boleta_credencial=boleta,
                rol=Usuario.Rol.ALUMNO,
            ).first()
            solicitud = SolicitudPrestamo.objects.filter(folio=folio).first() if folio else None
            if not alumno:
                messages.error(request, 'No se encontró un alumno con esa boleta.')
                flujo = {'boleta': boleta, 'folio': folio}
                request.session[session_key] = flujo
                paso = 1
            elif folio and (
                not solicitud
                or solicitud.alumno_id != alumno.id
                or solicitud.estatus not in (
                    SolicitudPrestamo.Estatus.CONFIRMADA,
                    SolicitudPrestamo.Estatus.SIN_CONFIRMAR,
                )
            ):
                messages.error(request, 'La solicitud no pertenece al alumno o ya no está pendiente.')
                flujo = {'boleta': boleta, 'folio': folio}
                request.session[session_key] = flujo
                paso = 1
            elif alumno.estatus == Usuario.Estatus.SANCIONADO:
                messages.error(request, 'El alumno tiene un adeudo o sanción activa y no puede recibir préstamos.')
                flujo = {'boleta': boleta, 'folio': folio}
                request.session[session_key] = flujo
                paso = 1
            elif (
                alumno.estatus == Usuario.Estatus.CON_PRESTAMO
                or _tiene_prestamos_activos(alumno)
            ):
                messages.error(request, 'El alumno ya cuenta con un préstamo activo pendiente de devolución.')
                flujo = {'boleta': boleta, 'folio': folio}
                request.session[session_key] = flujo
                paso = 1
            else:
                equipo_ids_previos = (
                    flujo.get('equipo_ids', [])
                    if flujo.get('folio') == folio and flujo.get('alumno_id') == alumno.id
                    else []
                )
                flujo = {
                    'alumno_id': alumno.id,
                    'boleta': alumno.boleta_credencial,
                    'folio': folio,
                    'equipo_ids': equipo_ids_previos,
                }
                request.session[session_key] = flujo
                return redirect(f"{request.path}?paso=2")

        elif accion == 'seleccionar_equipos':
            flujo = request.session.get(session_key, {})
            alumno = Usuario.objects.filter(id=flujo.get('alumno_id')).first()
            if not alumno:
                request.session.pop(session_key, None)
                messages.error(request, 'Vuelve a identificar al alumno para continuar.')
                return redirect(f"{request.path}?paso=1")

            seleccion = request.POST.getlist('equipo_ids')
            ids_unicos = set(seleccion)
            disponibles = {
                str(unidad['id']): unidad
                for unidad in INVENTARIO_ITEMS
                if unidad['estatus'] == 'DISPONIBLE'
            }
            unidades = [disponibles.get(item_id) for item_id in seleccion]
            if not seleccion or len(ids_unicos) != len(seleccion) or any(unidad is None for unidad in unidades):
                messages.error(request, 'Selecciona unidades disponibles y distintas para el préstamo.')
                paso = 2
            else:
                solicitud = SolicitudPrestamo.objects.filter(folio=flujo.get('folio')).first() if flujo.get('folio') else None
                if solicitud:
                    requeridos = {}
                    for item in solicitud.equipos:
                        nombre = item.get('nombre', '')
                        try:
                            cantidad = int(item.get('cantidad', 1))
                        except (TypeError, ValueError):
                            cantidad = 0
                        requeridos[nombre] = requeridos.get(nombre, 0) + cantidad
                    seleccionados = {}
                    for unidad in unidades:
                        seleccionados[unidad['nombre']] = seleccionados.get(unidad['nombre'], 0) + 1
                    if seleccionados != requeridos:
                        messages.error(
                            request,
                            'Selecciona exactamente las cantidades solicitadas para poder atender la reserva.',
                        )
                        paso = 2
                    else:
                        flujo['equipo_ids'] = [str(unidad['id']) for unidad in unidades]
                        request.session[session_key] = flujo
                        return redirect(f"{request.path}?paso=3")
                else:
                    flujo['equipo_ids'] = [str(unidad['id']) for unidad in unidades]
                    request.session[session_key] = flujo
                    return redirect(f"{request.path}?paso=3")

        elif accion == 'confirmar_prestamo':
            flujo = request.session.get(session_key, {})
            alumno = Usuario.objects.filter(id=flujo.get('alumno_id')).first()
            solicitud = SolicitudPrestamo.objects.filter(folio=flujo.get('folio')).first() if flujo.get('folio') else None
            ids = flujo.get('equipo_ids', [])
            unidades_por_id = {str(unidad['id']): unidad for unidad in INVENTARIO_ITEMS}
            unidades = [unidades_por_id.get(item_id) for item_id in ids]

            if request.POST.get('acepto_reglamento') != 'on':
                messages.error(request, 'Debes confirmar la aceptación del reglamento para registrar el préstamo.')
                paso = 3
            elif not alumno:
                request.session.pop(session_key, None)
                messages.error(request, 'No se encontró al alumno; inicia de nuevo el registro.')
                return redirect(f"{request.path}?paso=1")
            elif alumno.estatus == Usuario.Estatus.SANCIONADO:
                messages.error(request, 'El alumno tiene una sanción activa y no puede recibir préstamos.')
                paso = 3
            elif alumno.estatus == Usuario.Estatus.CON_PRESTAMO or _tiene_prestamos_activos(alumno):
                messages.error(request, 'El alumno ya cuenta con un préstamo activo pendiente de devolución.')
                paso = 3
            elif (
                not ids
                or len(unidades) != len(ids)
                or any(unidad is None or unidad['estatus'] != 'DISPONIBLE' for unidad in unidades)
            ):
                messages.error(request, 'Una o más unidades ya no están disponibles. Revisa la selección.')
                paso = 2
            elif solicitud and solicitud.estatus not in (
                SolicitudPrestamo.Estatus.CONFIRMADA,
                SolicitudPrestamo.Estatus.SIN_CONFIRMAR,
            ):
                messages.error(request, 'La reserva ya no está pendiente de atención.')
                paso = 1
            else:
                ahora = timezone.localtime()
                fecha_limite = (
                    timezone.make_aware(datetime.combine(
                        solicitud.fecha,
                        time.fromisoformat(solicitud.bloque.split('-')[1].strip()),
                    ))
                    if solicitud
                    else ahora + timedelta(minutes=90)
                )
                equipos_prestados = []
                for unidad in unidades:
                    equipos_prestados.append({
                        'id': unidad['id'],
                        'id_unico': unidad['id_unico'],
                        'nombre': unidad['nombre'],
                        'cantidad': 1,
                        'prestamo_activo': True,
                        'devuelto': False,
                        'fecha_prestamo': ahora.isoformat(),
                        'fecha_limite': fecha_limite.isoformat(),
                    })

                if solicitud is None:
                    solicitud = SolicitudPrestamo(
                        alumno=alumno,
                        fecha=ahora.date(),
                        bloque='Ventanilla',
                    )
                solicitud.equipos = equipos_prestados
                solicitud.estatus = SolicitudPrestamo.Estatus.ATENDIDA
                solicitud.save()
                alumno.estatus = Usuario.Estatus.CON_PRESTAMO
                alumno.save(update_fields=['estatus'])
                for unidad in unidades:
                    unidad['estatus'] = 'PRESTADO'
                    unidad['observaciones'] = f'Prestado en {solicitud.folio}'

                request.session.pop(session_key, None)
                messages.success(request, f'Préstamo {solicitud.folio} registrado correctamente.')
                return redirect('reservas:prestamo_registrado', folio=solicitud.folio)

    flujo = request.session.get(session_key, flujo)
    alumno = Usuario.objects.filter(id=flujo.get('alumno_id')).first()
    solicitud = SolicitudPrestamo.objects.filter(folio=flujo.get('folio')).first() if flujo.get('folio') else None
    if paso in (2, 3) and not alumno:
        return redirect(f"{request.path}?paso=1")

    if paso == 1:
        return render(request, 'reservas/registrar_prestamo.html', {
            'paso': 1,
            'boleta': flujo.get('boleta', ''),
            'folio': flujo.get('folio', ''),
        })

    if solicitud:
        requeridos = {}
        for item in solicitud.equipos:
            nombre = item.get('nombre', '')
            try:
                cantidad = int(item.get('cantidad', 1))
            except (TypeError, ValueError):
                cantidad = 0
            requeridos[nombre] = requeridos.get(nombre, 0) + cantidad
        unidades_disponibles = [
            unidad for unidad in INVENTARIO_ITEMS
            if unidad['estatus'] == 'DISPONIBLE' and unidad['nombre'] in requeridos
        ]
    else:
        requeridos = {}
        unidades_disponibles = [
            unidad for unidad in INVENTARIO_ITEMS if unidad['estatus'] == 'DISPONIBLE'
        ]

    seleccionadas = [
        unidades_por_id
        for item_id in flujo.get('equipo_ids', [])
        for unidades_por_id in INVENTARIO_ITEMS
        if str(unidades_por_id['id']) == str(item_id)
    ]
    return render(request, 'reservas/registrar_prestamo.html', {
        'paso': paso,
        'alumno': alumno,
        'solicitud': solicitud,
        'folio': flujo.get('folio', ''),
        'requeridos': requeridos,
        'unidades_disponibles': unidades_disponibles,
        'equipo_ids': flujo.get('equipo_ids', []),
        'seleccionadas': seleccionadas,
    })


@login_required
def comprobante_prestamo(request, folio):
    solicitud = SolicitudPrestamo.objects.filter(
        folio=folio,
        estatus=SolicitudPrestamo.Estatus.ATENDIDA,
    ).select_related('alumno').first()
    if not solicitud or not any(equipo.get('prestamo_activo') for equipo in solicitud.equipos):
        messages.error(request, 'No se encontró un comprobante de préstamo vigente para ese folio.')
        return redirect('reservas:bandeja_solicitudes' if _es_operador(request.user) else 'reservas:mis_reservas')
    if not _es_operador(request.user) and solicitud.alumno_id != request.user.id:
        return redirect('reservas:mis_reservas')

    fecha_prestamo = next(
        (equipo.get('fecha_prestamo') for equipo in solicitud.equipos if equipo.get('fecha_prestamo')),
        '',
    )
    fecha_limite = next(
        (equipo.get('fecha_limite') for equipo in solicitud.equipos if equipo.get('fecha_limite')),
        '',
    )
    fecha_prestamo = _fecha_hora_formateada(fecha_prestamo)
    fecha_limite = _fecha_hora_formateada(fecha_limite)
    nombre = _nombre_usuario(solicitud.alumno)
    pdf = _generar_comprobante_pdf(
        solicitud,
        fecha_prestamo,
        fecha_limite,
        nombre,
    )
    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'inline; filename="comprobante-{solicitud.folio}.pdf"'
    return response


@login_required
def prestamo_registrado(request, folio):
    if not _es_operador(request.user):
        return redirect('reservas:mis_reservas')

    solicitud = SolicitudPrestamo.objects.filter(
        folio=folio,
        estatus=SolicitudPrestamo.Estatus.ATENDIDA,
    ).select_related('alumno').first()
    if not solicitud or not any(equipo.get('prestamo_activo') for equipo in solicitud.equipos):
        messages.error(request, 'No se encontró el préstamo registrado.')
        return redirect('reservas:bandeja_solicitudes')

    return render(request, 'reservas/prestamo_registrado.html', {
        'solicitud': solicitud,
    })


@login_required
def vista_reporte_prestamos(request):
    """Reporte administrativo de las entregas y devoluciones registradas."""
    if not _es_operador(request.user):
        return redirect('reservas:mis_reservas')

    query = request.GET.get('q', '').strip().lower()
    fecha_filtro = request.GET.get('fecha', '').strip()
    estatus_filtro = request.GET.get('estatus', '').strip()
    fecha_obj = None
    fecha_invalida = False
    if fecha_filtro:
        try:
            fecha_obj = datetime.strptime(fecha_filtro, '%Y-%m-%d').date()
        except ValueError:
            fecha_invalida = True
            messages.error(request, 'El formato de fecha del filtro no es válido.')

    solicitudes = SolicitudPrestamo.objects.filter(
        estatus=SolicitudPrestamo.Estatus.ATENDIDA,
    ).select_related('alumno')
    adeudos_por_pieza = {
        (adeudo.solicitud_id, adeudo.id_material): adeudo.estatus
        for adeudo in Adeudo.objects.filter(
            solicitud__in=solicitudes,
        ).only('solicitud_id', 'id_material', 'estatus')
    }
    filas = []
    ahora = timezone.localtime()
    for solicitud in solicitudes:
        if fecha_invalida:
            continue
        alumno_texto = _nombre_usuario(solicitud.alumno)
        for equipo in solicitud.equipos:
            if not isinstance(equipo, dict) or not equipo.get('prestamo_activo'):
                continue
            try:
                entrega = datetime.fromisoformat(equipo.get('fecha_prestamo', ''))
                if timezone.is_naive(entrega):
                    entrega = timezone.make_aware(entrega)
                entrega = timezone.localtime(entrega)
            except (TypeError, ValueError):
                entrega = None
            try:
                devolucion = datetime.fromisoformat(equipo.get('fecha_devolucion', ''))
                if timezone.is_naive(devolucion):
                    devolucion = timezone.make_aware(devolucion)
                devolucion = timezone.localtime(devolucion)
            except (TypeError, ValueError):
                devolucion = None
            try:
                limite = datetime.fromisoformat(equipo.get('fecha_limite', ''))
                if timezone.is_naive(limite):
                    limite = timezone.make_aware(limite)
                limite = timezone.localtime(limite)
            except (TypeError, ValueError):
                limite = None

            id_material = str(equipo.get('id_unico', ''))
            estado_devolucion = equipo.get('estatus_devolucion', '')
            adeudo = adeudos_por_pieza.get((solicitud.pk, id_material))
            if not equipo.get('devuelto'):
                estado_filtro = 'VENCIDO' if limite and limite <= ahora else 'ACTIVO'
                estado = 'Vencido' if estado_filtro == 'VENCIDO' else 'Activo'
                if estado_filtro == 'VENCIDO' and adeudo == Adeudo.Estatus.ACTIVO:
                    estado = 'Vencido con adeudo'
            elif estado_devolucion == 'DANADO':
                estado_filtro = 'DANADO'
                estado = 'Dañado'
                if adeudo == Adeudo.Estatus.ACTIVO:
                    estado = 'Dañado con adeudo'
                elif adeudo == Adeudo.Estatus.LIQUIDADO:
                    estado = 'Dañado (adeudo liquidado)'
            elif estado_devolucion == 'MANTENIMIENTO':
                estado_filtro = 'DEVUELTO'
                estado = 'Devuelto a mantenimiento'
            else:
                estado_filtro = 'DEVUELTO'
                estado = 'Devuelto en buen estado'

            fechas_fila = [momento.date() for momento in (entrega, devolucion) if momento]
            if fecha_obj and fecha_obj not in fechas_fila:
                continue
            equipo_texto = f"{equipo.get('nombre', 'Equipo')} ({id_material})"
            if query and query not in ' '.join((
                solicitud.folio,
                alumno_texto,
                solicitud.alumno.boleta_credencial,
                equipo_texto,
            )).lower():
                continue
            if estatus_filtro and estado_filtro != estatus_filtro:
                continue
            fecha_limite = _fecha_hora_formateada(equipo.get('fecha_limite'))
            filas.append({
                'folio': solicitud.folio,
                'alumno': alumno_texto,
                'boleta': solicitud.alumno.boleta_credencial,
                'equipo': equipo_texto,
                'fecha': entrega.strftime('%d/%m/%Y %H:%M') if entrega else '—',
                'fecha_devolucion': (
                    devolucion.strftime('%d/%m/%Y %H:%M') if devolucion else '—'
                ),
                'fecha_limite': fecha_limite or '—',
                'estatus': estado,
                'estatus_filtro': estado_filtro,
                'entrega_orden': entrega.isoformat() if entrega else '',
                'devolucion_orden': devolucion.isoformat() if devolucion else '',
            })

    campos_orden = (
        'folio', 'alumno', 'equipo', 'fecha_entrega', 'fecha_devolucion', 'estatus'
    )
    orden = request.GET.get('orden', 'fecha_entrega')
    if orden not in campos_orden:
        orden = 'fecha_entrega'
    direccion = request.GET.get('direccion', 'desc')
    if direccion not in ('asc', 'desc'):
        direccion = 'desc'
    claves_orden = {
        'folio': 'folio',
        'alumno': 'alumno',
        'equipo': 'equipo',
        'fecha_entrega': 'entrega_orden',
        'fecha_devolucion': 'devolucion_orden',
        'estatus': 'estatus',
    }
    filas.sort(
        key=lambda fila: fila[claves_orden[orden]].lower(),
        reverse=direccion == 'desc',
    )
    page_obj = Paginator(filas, 20).get_page(request.GET.get('page'))

    return render(request, 'reservas/reporte_prestamos.html', {
        'prestamos': page_obj.object_list,
        'total_registros': len(filas),
        'query': request.GET.get('q', ''),
        'fecha_sel': fecha_filtro,
        'estatus_sel': estatus_filtro,
        'estatus_opciones': (
            ('ACTIVO', 'Activo'),
            ('VENCIDO', 'Vencido'),
            ('DEVUELTO', 'Devuelto'),
            ('DANADO', 'Dañado'),
        ),
        **_contexto_tabla(request, page_obj, campos_orden),
    })


_REPORTE_MENSUAL_PATTERN = re.compile(r'Reporte_Inventario_(\d{4}-\d{2})\.pdf')


@login_required
def vista_reportes_mensuales(request):
    if not _es_operador(request.user):
        return redirect('reservas:mis_reservas')

    carpeta = Path(settings.BASE_DIR) / 'media' / 'reportes_mensuales'
    reportes = []
    if carpeta.is_dir():
        for archivo in carpeta.iterdir():
            coincidencia = _REPORTE_MENSUAL_PATTERN.fullmatch(archivo.name)
            if coincidencia and archivo.is_file() and not archivo.is_symlink():
                reportes.append({
                    'nombre': archivo.name,
                    'periodo': coincidencia.group(1),
                })
    reportes.sort(key=lambda reporte: reporte['periodo'], reverse=True)

    return render(request, 'reservas/reportes_mensuales.html', {
        'reportes': reportes,
    })


@login_required
def vista_reporte_mensual_pdf(request, nombre_archivo):
    if not _es_operador(request.user):
        return redirect('reservas:mis_reservas')
    if not _REPORTE_MENSUAL_PATTERN.fullmatch(nombre_archivo):
        raise Http404

    carpeta = (Path(settings.BASE_DIR) / 'media' / 'reportes_mensuales').resolve()
    archivo = (carpeta / nombre_archivo).resolve()
    if archivo.parent != carpeta or not archivo.is_file() or archivo.is_symlink():
        raise Http404

    return FileResponse(
        archivo.open('rb'),
        content_type='application/pdf',
        as_attachment=False,
        filename=archivo.name,
    )


@login_required
def vista_bandeja_solicitudes(request):
    """Pantalla 6: Bandeja de Solicitudes y Reservas para Ventanilla (Req. 3.0.3)."""
    if request.user.rol not in ('LABORATORISTA', 'ADMINISTRADOR'):
        return redirect('reservas:mis_reservas')

    if request.method == 'POST':
        folio = request.POST.get('folio')
        accion = request.POST.get('accion')
        solicitud = SolicitudPrestamo.objects.filter(folio=folio).first()
        if solicitud and accion == 'atender':
            return redirect(f"{reverse('reservas:registrar_prestamo')}?folio={solicitud.folio}")
        elif solicitud and accion == 'cancelar':
            if solicitud.estatus in (
                SolicitudPrestamo.Estatus.CONFIRMADA,
                SolicitudPrestamo.Estatus.SIN_CONFIRMAR,
            ):
                solicitud.estatus = SolicitudPrestamo.Estatus.CANCELADA
                solicitud.save(update_fields=['estatus'])
                messages.warning(request, f"Reserva {folio} cancelada por ventanilla.")
            else:
                messages.error(request, 'Solo se pueden cancelar solicitudes que sigan pendientes.')
        elif not solicitud:
            messages.error(request, 'No se encontró la solicitud seleccionada.')
        return redirect('reservas:bandeja_solicitudes')

    # Filtros de búsqueda por boleta/nombre, estatus y fecha (Req. 3.0.3)
    q = request.GET.get('q', '').strip().lower()
    estatus_filtro = request.GET.get('estatus', '').strip()
    fecha_filtro = request.GET.get('fecha', '').strip()

    solicitudes = SolicitudPrestamo.objects.select_related('alumno').all()
    if q:
        solicitudes = solicitudes.annotate(
            alumno_nombre=Concat('alumno__first_name', Value(' '), 'alumno__last_name')
        ).filter(
            Q(alumno_nombre__icontains=q)
            | Q(alumno__first_name__icontains=q)
            | Q(alumno__last_name__icontains=q)
            | Q(alumno__boleta_credencial__icontains=q)
            | Q(folio__icontains=q)
        )
    if estatus_filtro:
        solicitudes = solicitudes.filter(estatus=estatus_filtro)
    if fecha_filtro:
        try:
            fecha_obj = datetime.strptime(fecha_filtro, '%Y-%m-%d').date()
            solicitudes = solicitudes.filter(fecha=fecha_obj)
        except ValueError:
            messages.error(request, 'El formato de fecha del filtro no es válido.')
            solicitudes = solicitudes.none()
    filtradas = [_solicitud_a_fila(solicitud) for solicitud in solicitudes]

    context = {
        'solicitudes': filtradas,
        'total_registros': len(filtradas),
        'query': request.GET.get('q', ''),
        'estatus_sel': estatus_filtro,
        'fecha_sel': fecha_filtro,
    }
    return render(request, 'reservas/bandeja_solicitudes.html', context)


@login_required
def vista_devoluciones(request):
    """Pantalla 17: recepción de equipos y registro de daños (Req. 5.0 a 5.1)."""
    if request.user.rol not in ('LABORATORISTA', 'ADMINISTRADOR'):
        return redirect('reservas:mis_reservas')

    accion = request.POST.get('accion', '') if request.method == 'POST' else ''
    entrada = (
        request.POST.get('boleta', '') if request.method == 'POST'
        else request.GET.get('boleta', '')
    ).strip()
    boleta = entrada
    _inicializar_datos_demo(request)
    prestamos = request.session.get('prestamos_activos_demo', [])
    _sincronizar_inventario_prestamos()
    unidad_escaneada = next(
        (item for item in INVENTARIO_ITEMS if item['id_unico'] == entrada),
        None,
    )
    prestamo_db = None
    if entrada:
        solicitudes_activas = SolicitudPrestamo.objects.filter(
            estatus=SolicitudPrestamo.Estatus.ATENDIDA,
        ).select_related('alumno')
        for solicitud in solicitudes_activas:
            equipos_activos = _equipos_prestados(solicitud)
            coincide_equipo = any(
                item.get('id_unico') == entrada for item in equipos_activos
            )
            coincide_boleta = solicitud.alumno.boleta_credencial == entrada
            if equipos_activos and (coincide_equipo or coincide_boleta):
                prestamo_db = {
                    'folio': solicitud.folio,
                    'boleta': solicitud.alumno.boleta_credencial,
                    'estatus': 'ACTIVO',
                    'articulos': [
                        {
                            'id': item['id'],
                            'id_unico': item['id_unico'],
                            'nombre': item['nombre'],
                        }
                        for item in equipos_activos
                    ],
                    'solicitud': solicitud,
                }
                boleta = solicitud.alumno.boleta_credencial
                break

    if prestamo_db:
        prestamo = prestamo_db
    elif unidad_escaneada:
        prestamo = next(
            (
                p for p in prestamos
                if p.get('estatus') == 'ACTIVO'
                and any(
                    articulo.get('id') == unidad_escaneada['id']
                    or articulo.get('id_unico') == entrada
                    for articulo in p.get('articulos', [])
                )
            ),
            None,
        )
        if prestamo:
            boleta = prestamo['boleta']
    else:
        prestamo = next(
            (
                p for p in prestamos
                if p.get('boleta') == boleta and p.get('estatus') == 'ACTIVO'
            ),
            None,
        )
    articulos = []
    if prestamo:
        articulos = [dict(item) for item in prestamo.get('articulos', [])]
        if not articulos:
            articulos = [
                dict(item) for item in INVENTARIO_ITEMS
                if f"({item['id_unico']})" in prestamo.get('equipos', '')
            ]
        for articulo in articulos:
            articulo['estado_seleccionado'] = request.POST.get(
                f"estado_{articulo['id']}", 'DISPONIBLE'
            ) if accion == 'registrar' else 'DISPONIBLE'
            articulo['observaciones_capturadas'] = request.POST.get(
                f"observaciones_{articulo['id']}", ''
            ) if accion == 'registrar' else ''

    if request.method == 'POST' and accion == 'buscar':
        if not boleta:
            messages.error(request, 'Escanea el código de barras o ingresa la boleta del alumno.')
        elif not prestamo:
            messages.warning(request, 'No se encontró un préstamo activo asociado al identificador escaneado.')

    if request.method == 'POST' and accion == 'registrar':
        if not prestamo or not articulos:
            messages.error(request, 'No hay un préstamo activo con artículos pendientes para devolver.')
        else:
            cambios = []
            error = None
            for articulo in articulos:
                estado = request.POST.get(f"estado_{articulo['id']}", '')
                observaciones = request.POST.get(f"observaciones_{articulo['id']}", '').strip()
                unidad = next(
                    (item for item in INVENTARIO_ITEMS if item['id'] == articulo['id']),
                    None,
                )

                if estado not in ('DISPONIBLE', 'MANTENIMIENTO', 'DANADO'):
                    error = f"Selecciona el estado de devolución de {articulo['id_unico']}."
                    break
                if not unidad or unidad['estatus'] != 'PRESTADO':
                    error = f"El equipo {articulo['id_unico']} no aparece actualmente como prestado en el inventario."
                    break
                if estado != 'DISPONIBLE' and not observaciones:
                    error = f"Las observaciones son obligatorias para reportar daños en {articulo['id_unico']}."
                    break

                cambios.append({
                    'articulo': articulo,
                    'unidad': unidad,
                    'estado': estado,
                    'observaciones': observaciones,
                })

            if error:
                messages.error(request, error)
            else:
                fecha_registro = timezone.localtime().strftime('%d/%m/%Y %H:%M')
                historial = request.session.get('historial_devoluciones', [])
                for cambio in cambios:
                    articulo = cambio['articulo']
                    unidad = cambio['unidad']
                    unidad['estatus'] = cambio['estado']
                    unidad['observaciones'] = cambio['observaciones']
                    historial.insert(0, {
                        'folio_prestamo': prestamo['folio'],
                        'boleta': boleta,
                        'id_unico': articulo['id_unico'],
                        'nombre': articulo['nombre'],
                        'estatus': cambio['estado'],
                        'observaciones': cambio['observaciones'],
                        'fecha': fecha_registro,
                    })

                if prestamo.get('solicitud'):
                    solicitud = prestamo['solicitud']
                    cambios_por_id = {
                        cambio['articulo']['id_unico']: cambio for cambio in cambios
                    }
                    for item in solicitud.equipos:
                        cambio = cambios_por_id.get(item.get('id_unico'))
                        if cambio:
                            item['devuelto'] = True
                            item['estatus_devolucion'] = cambio['estado']
                            item['observaciones_devolucion'] = cambio['observaciones']
                            item['fecha_devolucion'] = timezone.localtime().isoformat()
                    solicitud.equipos = solicitud.equipos
                    solicitud.save(update_fields=['equipos'])
                    sincronizar_adeudos(alumno=solicitud.alumno, actor=request.user)
                    _actualizar_estatus_alumno(solicitud.alumno)
                    _sincronizar_inventario_prestamos()
                else:
                    prestamo['articulos_devuelto'] = prestamo.get('articulos_devuelto', []) + [
                        cambio['articulo'] for cambio in cambios
                    ]
                    prestamo['articulos'] = []
                    prestamo['estatus'] = 'DEVUELTO'
                    request.session['prestamos_activos_demo'] = prestamos
                request.session['historial_devoluciones'] = historial
                messages.success(request, f"Se registró la devolución del préstamo {prestamo['folio']}.")
                return redirect(f"{request.path}?boleta={boleta}")

    return render(request, 'reservas/devoluciones.html', {
        'boleta': boleta,
        'entrada': entrada,
        'prestamo': prestamo,
        'articulos': articulos,
        'alumno': Usuario.objects.filter(boleta_credencial=boleta, rol='ALUMNO').first() if prestamo else None,
        'historial': request.session.get('historial_devoluciones', [])[:10],
    })


@login_required
@user_passes_test(lambda user: user.rol == Usuario.Rol.ADMINISTRADOR)
def vista_adeudos(request):
    """Administra y exporta adeudos activos y liquidados (Req. 6.2 y 6.2.1)."""
    sincronizar_adeudos()

    adeudos_qs = Adeudo.objects.select_related(
        'alumno',
        'solicitud',
        'creado_por',
        'liquidado_por',
    ).prefetch_related('historial__actor')
    query = request.GET.get('q', '').strip()
    estatus_filtro = request.GET.get('estatus', '').strip()
    fecha_filtro = request.GET.get('fecha', '').strip()
    if query:
        adeudos_qs = adeudos_qs.filter(
            Q(alumno__first_name__icontains=query)
            | Q(alumno__last_name__icontains=query)
            | Q(alumno__boleta_credencial__icontains=query)
            | Q(solicitud__folio__icontains=query)
            | Q(material__icontains=query)
            | Q(id_material__icontains=query)
            | Q(motivo__icontains=query)
        )
    if estatus_filtro:
        adeudos_qs = adeudos_qs.filter(estatus=estatus_filtro)
    if fecha_filtro:
        try:
            fecha_obj = datetime.strptime(fecha_filtro, '%Y-%m-%d').date()
            adeudos_qs = adeudos_qs.filter(creado_en__date=fecha_obj)
        except ValueError:
            adeudos_qs = adeudos_qs.none()
            messages.error(request, 'El formato de fecha del filtro no es válido.')

    if request.method == 'GET' and request.GET.get('exportar') == 'csv':
        response = HttpResponse(content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = 'attachment; filename="reporte-adeudos.csv"'
        response.write('\ufeff')
        escritor = csv.writer(response)
        escritor.writerow([
            'Folio',
            'Alumno',
            'Boleta',
            'Tipo',
            'Material',
            'Identificador',
            'Motivo',
            'Monto',
            'Pieza de reposición',
            'Estatus',
            'Fecha de registro',
            'Fecha de liquidación',
        ])
        for adeudo in adeudos_qs:
            escritor.writerow([_valor_csv_seguro(valor) for valor in [
                adeudo.solicitud.folio,
                _nombre_usuario(adeudo.alumno),
                adeudo.alumno.boleta_credencial,
                adeudo.get_tipo_display(),
                adeudo.material,
                adeudo.id_material,
                adeudo.motivo,
                adeudo.monto or '',
                adeudo.pieza_reposicion,
                adeudo.get_estatus_display(),
                timezone.localtime(adeudo.creado_en).strftime('%d/%m/%Y %H:%M'),
                timezone.localtime(adeudo.liquidado_en).strftime('%d/%m/%Y %H:%M')
                if adeudo.liquidado_en else '',
            ]])
        return response

    formularios_invalidos = {}
    if request.method == 'POST':
        accion = request.POST.get('accion')
        adeudo = get_object_or_404(
            Adeudo,
            pk=request.POST.get('adeudo_id'),
            estatus=Adeudo.Estatus.ACTIVO,
        )

        if accion == 'valorar':
            form = ValorarAdeudoForm(request.POST)
            if form.is_valid():
                adeudo.monto = form.cleaned_data['monto']
                adeudo.pieza_reposicion = form.cleaned_data['pieza_reposicion']
                adeudo.save(update_fields=['monto', 'pieza_reposicion'])
                detalle = (
                    f'Monto registrado: ${adeudo.monto:.2f}.'
                    if adeudo.monto is not None
                    else f'Pieza de reposición registrada: {adeudo.pieza_reposicion}.'
                )
                HistorialAdeudo.objects.create(
                    adeudo=adeudo,
                    actor=request.user,
                    accion=HistorialAdeudo.Accion.ACTUALIZADO,
                    detalle=detalle,
                )
                messages.success(request, f'Actualizaste el adeudo de {adeudo.alumno.boleta_credencial}.')
                return redirect('reservas:adeudos')
            formularios_invalidos[adeudo.pk] = form

        elif accion == 'liquidar':
            if request.POST.get('confirmar_liquidacion') != 'on':
                messages.error(request, 'Confirma la liquidación antes de levantar la sanción.')
            elif adeudo.monto is None and not adeudo.pieza_reposicion:
                messages.error(request, 'Primero registra el monto o la pieza que debe reponerse.')
            else:
                adeudo.estatus = Adeudo.Estatus.LIQUIDADO
                adeudo.liquidado_en = timezone.now()
                adeudo.liquidado_por = request.user
                adeudo.save(update_fields=['estatus', 'liquidado_en', 'liquidado_por'])
                HistorialAdeudo.objects.create(
                    adeudo=adeudo,
                    actor=request.user,
                    accion=HistorialAdeudo.Accion.LIQUIDADO,
                    detalle='El administrador confirmó el pago o la reposición y levantó el adeudo.',
                )
                _actualizar_estatus_alumno(adeudo.alumno)
                messages.success(
                    request,
                    f'El adeudo quedó liquidado. Se actualizó el estatus de {adeudo.alumno.boleta_credencial}.',
                )
                return redirect('reservas:adeudos')

    campos_orden = ('folio', 'alumno', 'material', 'estatus', 'fecha')
    orden = request.GET.get('orden', 'fecha')
    if orden not in campos_orden:
        orden = 'fecha'
    direccion = request.GET.get('direccion', 'desc')
    if direccion not in ('asc', 'desc'):
        direccion = 'desc'
    claves_orden = {
        'folio': 'solicitud__folio',
        'alumno': 'alumno__boleta_credencial',
        'material': 'material',
        'estatus': 'estatus',
        'fecha': 'creado_en',
    }
    adeudos_qs = adeudos_qs.order_by(
        ('-' if direccion == 'desc' else '') + claves_orden[orden]
    )
    total_registros = adeudos_qs.count()
    page_obj = Paginator(adeudos_qs, 20).get_page(request.GET.get('page'))
    adeudos = list(page_obj.object_list)
    for adeudo in adeudos:
        adeudo.form_valoracion = formularios_invalidos.get(adeudo.pk) or ValorarAdeudoForm(
            initial={
                'monto': adeudo.monto,
                'pieza_reposicion': adeudo.pieza_reposicion,
            }
        )

    activos = adeudos_qs.filter(estatus=Adeudo.Estatus.ACTIVO)
    contexto_tabla = _contexto_tabla(request, page_obj, campos_orden)
    return render(request, 'reservas/adeudos.html', {
        'adeudos': adeudos,
        'total_registros': total_registros,
        'total_activos': activos.count(),
        'total_monto': sum(
            monto for monto in adeudos_qs.values_list('monto', flat=True)
            if monto is not None
        ),
        'pendientes_valoracion': activos.filter(
            monto__isnull=True,
            pieza_reposicion='',
        ).count(),
        'query': query,
        'estatus_sel': estatus_filtro,
        'fecha_sel': fecha_filtro,
        **contexto_tabla,
    })


@login_required
@user_passes_test(lambda user: user.rol == Usuario.Rol.ADMINISTRADOR)
@require_GET
def notificaciones_administrador(_request):
    """Devuelve eventos de solicitudes nuevas y préstamos vencidos (Req. 6.1.1)."""
    ahora = timezone.localtime()
    sincronizar_adeudos(ahora=ahora)
    eventos = []

    pendientes = SolicitudPrestamo.objects.filter(
        estatus__in=(
            SolicitudPrestamo.Estatus.CONFIRMADA,
            SolicitudPrestamo.Estatus.SIN_CONFIRMAR,
        ),
    ).select_related('alumno')
    for solicitud in pendientes:
        eventos.append({
            'id': f'solicitud:{solicitud.pk}',
            'mensaje': (
                f'Nueva solicitud {solicitud.folio} de '
                f'{_nombre_usuario(solicitud.alumno)}.'
            ),
        })

    for vencido in obtener_prestamos_vencidos(ahora=ahora):
        solicitud = vencido['solicitud']
        equipo = vencido['equipo']
        eventos.append({
            'id': f"vencido:{solicitud.pk}:{equipo.get('id_unico', '')}",
            'mensaje': (
                f"Préstamo vencido: {equipo.get('nombre', 'Equipo')} "
                f"({solicitud.folio}), alumno {_nombre_usuario(solicitud.alumno)}."
            ),
        })

    return JsonResponse({'eventos': eventos})