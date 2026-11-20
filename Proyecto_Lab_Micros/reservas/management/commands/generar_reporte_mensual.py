import calendar
import os
from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from inventario.views import INVENTARIO_ITEMS
from reservas.models import Adeudo, SolicitudPrestamo
from reservas.services import sincronizar_adeudos


def es_ultimo_dia_habil_del_mes(fecha_actual):
    """Determina si fecha_actual es el último día hábil (Lunes-Viernes) del mes."""
    ultimo_num_dia = calendar.monthrange(fecha_actual.year, fecha_actual.month)[1]
    dia = date(fecha_actual.year, fecha_actual.month, ultimo_num_dia)
    while dia.weekday() >= 5:  # 5 = Sábado, 6 = Domingo
        dia -= timedelta(days=1)
    return fecha_actual == dia


class Command(BaseCommand):
    help = 'Genera el reporte mensual consolidado de inventario en PDF (Req. 7.0).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--forzar',
            action='store_true',
            help='Genera el PDF inmediatamente sin validar si hoy es el último día hábil del mes.',
        )

    def handle(self, *args, **options):
        ahora = timezone.localtime()
        hoy = ahora.date()

        if not options['forzar'] and not es_ultimo_dia_habil_del_mes(hoy):
            self.stdout.write(
                self.style.WARNING(
                    f'Hoy ({hoy.strftime("%d/%m/%Y")}) no es el último día hábil del mes. '
                    'Usa --forzar si deseas generar una prueba ahora.'
                )
            )
            return

        sincronizar_adeudos(ahora=ahora)

        # Carpeta de almacenamiento en media/reportes_mensuales/
        carpeta_destino = os.path.join(settings.BASE_DIR, 'media', 'reportes_mensuales')
        os.makedirs(carpeta_destino, exist_ok=True)

        periodo = hoy.strftime('%Y-%m')
        nombre_archivo = f'Reporte_Inventario_{periodo}.pdf'
        ruta_pdf = os.path.join(carpeta_destino, nombre_archivo)

        # Cálculos consolidados
        activos = [m for m in INVENTARIO_ITEMS if m.get('estatus') != 'BAJA_DEFINITIVA']
        disponibles = sum(1 for m in activos if m.get('estatus') == 'DISPONIBLE')
        prestados = sum(1 for m in activos if m.get('estatus') == 'PRESTADO')
        mantenimiento = sum(1 for m in activos if m.get('estatus') in ('MANTENIMIENTO', 'DANADO'))
        bajas = sum(1 for m in INVENTARIO_ITEMS if m.get('estatus') == 'BAJA_DEFINITIVA')

        prestamos_mes = SolicitudPrestamo.objects.filter(
            fecha__year=hoy.year,
            fecha__month=hoy.month,
            estatus=SolicitudPrestamo.Estatus.ATENDIDA,
        ).count()
        adeudos_activos = Adeudo.objects.filter(estatus=Adeudo.Estatus.ACTIVO).count()
        adeudos_liquidados = Adeudo.objects.filter(estatus=Adeudo.Estatus.LIQUIDADO).count()

        # Construcción del PDF con ReportLab
        doc = SimpleDocTemplate(ruta_pdf, pagesize=letter)
        estilos = getSampleStyleSheet()
        elementos = []

        elementos.append(Paragraph('<b>INSTITUTO POLITÉCNICO NACIONAL</b>', estilos['Title']))
        elementos.append(Paragraph('ESIME Culhuacán — Laboratorio de Microcontroladores', estilos['Heading2']))
        elementos.append(Paragraph(f'Reporte Mensual Consolidado de Inventario ({periodo})', estilos['Heading3']))
        elementos.append(Paragraph(f'Fecha y hora de corte: {ahora.strftime("%d/%m/%Y %H:%M")} hrs', estilos['Normal']))
        elementos.append(Spacer(1, 16))

        datos_resumen = [
            ['Indicador Operativo', 'Total'],
            ['Equipos activos en inventario', str(len(activos))],
            ['Unidades disponibles', str(disponibles)],
            ['Unidades en préstamo activo', str(prestados)],
            ['Unidades en mantenimiento / dañadas', str(mantenimiento)],
            ['Bajas definitivas históricas', str(bajas)],
            ['Préstamos atendidos en el mes', str(prestamos_mes)],
            ['Adeudos activos vigentes', str(adeudos_activos)],
            ['Adeudos liquidados', str(adeudos_liquidados)],
        ]

        tabla = Table(datos_resumen, colWidths=[340, 120])
        tabla.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6a1b29')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('ALIGN', (1, 1), (1, -1), 'CENTER'),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
            ('PADDING', (0, 0), (-1, -1), 8),
        ]))
        elementos.append(tabla)

        doc.build(elementos)
        self.stdout.write(self.style.SUCCESS(f'Reporte PDF generado exitosamente en: {ruta_pdf}'))
        