from copy import deepcopy
from datetime import date, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from inventario.views import INVENTARIO_ITEMS
from reservas.models import Adeudo, HistorialAdeudo, SolicitudPrestamo
from reservas.services import (
    ReservaService,
    obtener_alertas_prestamo,
    sincronizar_adeudos,
)
from usuarios.models import Usuario


class DevolucionesTests(TestCase):
    def setUp(self):
        self.unidad = next(item for item in INVENTARIO_ITEMS if item['id'] == 3)
        self.unidad_original = deepcopy(self.unidad)
        self.unidad['estatus'] = 'PRESTADO'
        self.unidad['observaciones'] = ''

        self.operador = Usuario.objects.create_user(
            username='lab-test',
            password='test-pass',
            boleta_credencial='LAB-0001',
            correo_institucional='lab-test@ipn.mx',
            rol=Usuario.Rol.LABORATORISTA,
        )
        self.client.force_login(self.operador)
        self._crear_prestamo_activo()

    def tearDown(self):
        self.unidad.clear()
        self.unidad.update(self.unidad_original)

    def _crear_prestamo_activo(self):
        session = self.client.session
        session['prestamos_activos_demo'] = [{
            'folio': 'PREST-501',
            'boleta': '2022640001',
            'estatus': 'ACTIVO',
            'articulos': [{
                'id': 3,
                'id_unico': 'MIC-ESP32-003',
                'nombre': 'Tarjeta de Desarrollo ESP32 NodeMCU',
            }],
        }]
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

    def test_scanning_item_code_finds_active_loan(self):
        response = self.client.post(reverse('reservas:devoluciones'), {
            'accion': 'buscar',
            'boleta': 'MIC-ESP32-003',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'PREST-501')
        self.assertContains(response, '2022640001')

    def test_damage_without_observations_does_not_process_return(self):
        response = self.client.post(reverse('reservas:devoluciones'), {
            'accion': 'registrar',
            'boleta': '2022640001',
            'estado_3': 'DANADO',
            'observaciones_3': '',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Las observaciones son obligatorias')
        self.assertEqual(self.unidad['estatus'], 'PRESTADO')
        self.assertEqual(self.client.session['prestamos_activos_demo'][0]['estatus'], 'ACTIVO')

    def test_damage_return_updates_inventory_and_history(self):
        response = self.client.post(reverse('reservas:devoluciones'), {
            'accion': 'registrar',
            'boleta': '2022640001',
            'estado_3': 'DANADO',
            'observaciones_3': 'Fusible quemado',
        })

        self.assertRedirects(
            response,
            f"{reverse('reservas:devoluciones')}?boleta=2022640001",
            fetch_redirect_response=False,
        )
        self.assertEqual(self.unidad['estatus'], 'DANADO')
        self.assertEqual(self.unidad['observaciones'], 'Fusible quemado')
        self.assertEqual(self.client.session['prestamos_activos_demo'][0]['estatus'], 'DEVUELTO')
        self.assertEqual(self.client.session['historial_devoluciones'][0]['id_unico'], 'MIC-ESP32-003')

    def test_good_return_makes_item_available_and_closes_loan(self):
        response = self.client.post(reverse('reservas:devoluciones'), {
            'accion': 'registrar',
            'boleta': '2022640001',
            'estado_3': 'DISPONIBLE',
            'observaciones_3': '',
        })

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.unidad['estatus'], 'DISPONIBLE')
        self.assertEqual(self.client.session['prestamos_activos_demo'][0]['estatus'], 'DEVUELTO')
        self.assertEqual(self.client.session['historial_devoluciones'][0]['estatus'], 'DISPONIBLE')

    def test_bandeja_filters_by_name_status_and_date(self):
        mariana = Usuario.objects.create_user(
            username='mariana',
            password='test-pass',
            first_name='Mariana',
            last_name='López Hernández',
            boleta_credencial='2022640001',
            correo_institucional='mariana@ipn.mx',
            rol=Usuario.Rol.ALUMNO,
        )
        carlos = Usuario.objects.create_user(
            username='carlos',
            password='test-pass',
            first_name='Carlos',
            last_name='Ruiz',
            boleta_credencial='2022640002',
            correo_institucional='carlos@ipn.mx',
            rol=Usuario.Rol.ALUMNO,
        )
        solicitud_mariana = SolicitudPrestamo.objects.create(
            alumno=mariana,
            equipos=[{'nombre': 'Osciloscopio', 'cantidad': 1}],
            fecha=date(2026, 11, 17),
            bloque='10:00 - 11:30',
        )
        cancelada = SolicitudPrestamo.objects.create(
            alumno=carlos,
            equipos=[{'nombre': 'Multímetro', 'cantidad': 1}],
            fecha=date(2026, 11, 18),
            bloque='11:30 - 13:00',
        )
        cancelada.estatus = SolicitudPrestamo.Estatus.CANCELADA
        cancelada.save(update_fields=['estatus'])

        response = self.client.get(reverse('reservas:bandeja_solicitudes'), {
            'q': 'Mariana',
            'estatus': 'CONFIRMADA',
            'fecha': '2026-11-17',
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, solicitud_mariana.folio)
        self.assertContains(response, '17/11/2026')
        self.assertNotContains(response, 'RES-2002')
        self.assertEqual(response.context['total_registros'], 1)

    def test_my_reservations_show_day_first_date(self):
        student = Usuario.objects.create_user(
            username='student-test',
            password='test-pass',
            boleta_credencial='2022640001',
            correo_institucional='student-test@ipn.mx',
            rol=Usuario.Rol.ALUMNO,
        )
        self.client.force_login(student)
        solicitud = SolicitudPrestamo.objects.create(
            alumno=student,
            equipos=[{'nombre': 'Osciloscopio', 'cantidad': 1}],
            fecha=date(2026, 11, 17),
            bloque='10:00 - 11:30',
        )

        response = self.client.get(reverse('reservas:mis_reservas'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '17/11/2026')
        self.assertContains(response, solicitud.folio)

    def test_my_active_loan_pdf_opens_in_new_tab(self):
        student = Usuario.objects.create_user(
            username='student-pdf-test',
            password='test-pass',
            boleta_credencial='2022640002',
            correo_institucional='student-pdf-test@ipn.mx',
            rol=Usuario.Rol.ALUMNO,
        )
        SolicitudPrestamo.objects.create(
            alumno=student,
            equipos=[{
                'nombre': 'Osciloscopio',
                'id_unico': 'OSC-TEST-001',
                'prestamo_activo': True,
                'devuelto': False,
                'fecha_limite': (timezone.localtime() + timedelta(hours=1)).isoformat(),
            }],
            fecha=timezone.localdate(),
            bloque='10:00 - 11:30',
            estatus=SolicitudPrestamo.Estatus.ATENDIDA,
        )
        self.client.force_login(student)

        response = self.client.get(reverse('reservas:mis_reservas'))

        self.assertContains(response, 'Ver PDF')
        self.assertContains(response, 'target="_blank" rel="noopener"')

    @patch('reservas.views.timezone.localdate', return_value=date(2026, 11, 16))
    @patch('reservas.views.timezone.localtime')
    def test_confirmed_request_is_saved_and_visible_to_operator(self, localtime, _localdate):
        localtime.return_value = timezone.make_aware(datetime(2026, 11, 16, 8, 0))
        student = Usuario.objects.create_user(
            username='requesting-student',
            password='test-pass',
            first_name='Roberto',
            last_name='García',
            boleta_credencial='2022640999',
            correo_institucional='roberto@ipn.mx',
            rol=Usuario.Rol.ALUMNO,
        )
        self.client.force_login(student)
        session = self.client.session
        session['carrito_solicitud'] = [{
            'id': 3,
            'id_unico': 'MIC-ESP32-003',
            'nombre': 'Tarjeta ESP32',
            'cantidad': 1,
        }]
        session.save()
        self.client.cookies[settings.SESSION_COOKIE_NAME] = session.session_key

        response = self.client.post(reverse('reservas:carrito'), {
            'accion': 'confirmar_solicitud',
            'fecha_reserva': '2026-11-16',
            'bloque_horario': '10:00 - 11:30',
            'acepto_reglamento': 'on',
        })

        self.assertRedirects(response, reverse('reservas:mis_reservas'), fetch_redirect_response=False)
        solicitud = SolicitudPrestamo.objects.get(alumno=student)
        self.assertEqual(solicitud.equipos[0]['id_unico'], 'MIC-ESP32-003')
        self.assertEqual(self.client.session['carrito_solicitud'], [])

        operator_client = Client()
        operator_client.force_login(self.operador)
        response = operator_client.get(reverse('reservas:bandeja_solicitudes'))
        self.assertContains(response, 'Roberto García')
        self.assertContains(response, '2022640999')
        self.assertContains(response, solicitud.folio)

    def test_same_day_booking_rejects_a_block_that_already_started(self):
        ahora = timezone.make_aware(datetime(2026, 11, 16, 10, 15))

        with self.assertRaisesMessage(ValueError, 'todavía no haya comenzado'):
            ReservaService.validar_fecha_y_bloque(
                date(2026, 11, 16),
                '10:00 - 11:30',
                ahora,
            )

        ReservaService.validar_fecha_y_bloque(
            date(2026, 11, 16),
            '11:30 - 13:00',
            ahora,
        )


class RegistroPrestamoTests(TestCase):
    def setUp(self):
        self.inventario_original = deepcopy(INVENTARIO_ITEMS)
        self.unidad = next(item for item in INVENTARIO_ITEMS if item['id'] == 1)
        self.alumno = Usuario.objects.create_user(
            username='alumno-prestamo',
            password='test-pass',
            first_name='Ana',
            last_name='Pérez',
            boleta_credencial='2022641234',
            correo_institucional='ana.perez@ipn.mx',
            rol=Usuario.Rol.ALUMNO,
        )
        self.operador = Usuario.objects.create_user(
            username='laboratorista-prestamo',
            password='test-pass',
            boleta_credencial='LAB-0002',
            correo_institucional='laboratorista2@ipn.mx',
            rol=Usuario.Rol.LABORATORISTA,
        )
        self.client.force_login(self.operador)

    def tearDown(self):
        INVENTARIO_ITEMS[:] = self.inventario_original

    def test_manual_loan_records_units_and_returns_pdf_receipt(self):
        response = self.client.post(reverse('reservas:registrar_prestamo'), {
            'accion': 'validar_alumno',
            'boleta': self.alumno.boleta_credencial,
        })
        self.assertRedirects(
            response,
            f"{reverse('reservas:registrar_prestamo')}?paso=2",
            fetch_redirect_response=False,
        )

        response = self.client.post(reverse('reservas:registrar_prestamo') + '?paso=2', {
            'accion': 'seleccionar_equipos',
            'equipo_ids': str(self.unidad['id']),
        })
        self.assertRedirects(
            response,
            f"{reverse('reservas:registrar_prestamo')}?paso=3",
            fetch_redirect_response=False,
        )

        response = self.client.post(reverse('reservas:registrar_prestamo') + '?paso=3', {
            'accion': 'confirmar_prestamo',
            'acepto_reglamento': 'on',
        })
        solicitud = SolicitudPrestamo.objects.get(alumno=self.alumno)
        self.assertRedirects(
            response,
            reverse('reservas:prestamo_registrado', args=[solicitud.folio]),
            fetch_redirect_response=False,
        )
        self.assertEqual(solicitud.estatus, SolicitudPrestamo.Estatus.ATENDIDA)
        self.assertEqual(solicitud.equipos[0]['id_unico'], self.unidad['id_unico'])
        fecha_prestamo = datetime.fromisoformat(solicitud.equipos[0]['fecha_prestamo'])
        fecha_limite = datetime.fromisoformat(solicitud.equipos[0]['fecha_limite'])
        self.assertEqual(fecha_limite - fecha_prestamo, timedelta(minutes=90))
        self.assertEqual(self.alumno.__class__.objects.get(pk=self.alumno.pk).estatus, Usuario.Estatus.CON_PRESTAMO)
        self.assertEqual(self.unidad['estatus'], 'PRESTADO')

        response = self.client.get(reverse('reservas:prestamo_registrado', args=[solicitud.folio]))
        self.assertContains(response, 'Ver comprobante PDF')
        self.assertContains(response, reverse('reservas:comprobante', args=[solicitud.folio]))
        self.assertContains(response, 'target="_blank" rel="noopener"')

        response = self.client.get(reverse('reservas:comprobante', args=[solicitud.folio]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertTrue(response.content.startswith(b'%PDF-1.4'))
        self.assertGreaterEqual(response.content.count(b'/Subtype /Image'), 2)

        self.client.force_login(self.alumno)
        response = self.client.get(reverse('reservas:prestamo_registrado', args=[solicitud.folio]))
        self.assertRedirects(
            response,
            reverse('reservas:mis_reservas'),
            fetch_redirect_response=False,
        )

    def test_sanctioned_student_cannot_continue_to_equipment_selection(self):
        self.alumno.estatus = Usuario.Estatus.SANCIONADO
        self.alumno.save(update_fields=['estatus'])

        response = self.client.post(reverse('reservas:registrar_prestamo'), {
            'accion': 'validar_alumno',
            'boleta': self.alumno.boleta_credencial,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'sanción activa')
        self.assertFalse(response.wsgi_request.session.get('prestamo_ventanilla', {}).get('alumno_id'))

    def test_existing_unreturned_loan_blocks_a_second_loan(self):
        SolicitudPrestamo.objects.create(
            alumno=self.alumno,
            equipos=[{
                'id': self.unidad['id'],
                'id_unico': self.unidad['id_unico'],
                'nombre': self.unidad['nombre'],
                'prestamo_activo': True,
                'devuelto': False,
            }],
            fecha=date.today(),
            bloque='Ventanilla',
            estatus=SolicitudPrestamo.Estatus.ATENDIDA,
        )
        self.alumno.estatus = Usuario.Estatus.CON_PRESTAMO
        self.alumno.save(update_fields=['estatus'])

        response = self.client.post(reverse('reservas:registrar_prestamo'), {
            'accion': 'validar_alumno',
            'boleta': self.alumno.boleta_credencial,
        })

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'préstamo activo pendiente de devolución')

    def test_registered_loan_can_be_returned_and_appears_in_report(self):
        self.unidad['estatus'] = 'PRESTADO'
        self.alumno.estatus = Usuario.Estatus.CON_PRESTAMO
        self.alumno.save(update_fields=['estatus'])
        solicitud = SolicitudPrestamo.objects.create(
            alumno=self.alumno,
            equipos=[{
                'id': self.unidad['id'],
                'id_unico': self.unidad['id_unico'],
                'nombre': self.unidad['nombre'],
                'prestamo_activo': True,
                'devuelto': False,
                'fecha_prestamo': timezone.localtime().isoformat(),
                'fecha_limite': timezone.localtime().isoformat(),
            }],
            fecha=date.today(),
            bloque='Ventanilla',
            estatus=SolicitudPrestamo.Estatus.ATENDIDA,
        )

        response = self.client.get(reverse('reservas:reporte_prestamos'))
        self.assertContains(response, solicitud.folio)
        self.assertContains(response, 'Activo')
        self.assertContains(response, 'target="_blank" rel="noopener"')

        response = self.client.post(reverse('reservas:devoluciones'), {
            'accion': 'registrar',
            'boleta': self.alumno.boleta_credencial,
            f"estado_{self.unidad['id']}": 'DISPONIBLE',
            f"observaciones_{self.unidad['id']}": '',
        })

        self.assertEqual(response.status_code, 302)
        solicitud.refresh_from_db()
        self.alumno.refresh_from_db()
        self.assertTrue(solicitud.equipos[0]['devuelto'])
        self.assertEqual(self.alumno.estatus, Usuario.Estatus.ACTIVO)
        self.assertEqual(self.unidad['estatus'], 'DISPONIBLE')

    def test_attending_request_opens_wizard_with_preloaded_student_and_unit(self):
        solicitud = SolicitudPrestamo.objects.create(
            alumno=self.alumno,
            equipos=[{
                'id': self.unidad['id'],
                'id_unico': self.unidad['id_unico'],
                'nombre': self.unidad['nombre'],
                'cantidad': 1,
            }],
            fecha=date(2026, 11, 17),
            bloque='10:00 - 11:30',
        )

        response = self.client.post(reverse('reservas:bandeja_solicitudes'), {
            'accion': 'atender',
            'folio': solicitud.folio,
        })

        self.assertRedirects(
            response,
            f"{reverse('reservas:registrar_prestamo')}?folio={solicitud.folio}",
            fetch_redirect_response=False,
        )
        response = self.client.get(response.url)
        self.assertContains(response, self.alumno.boleta_credencial)
        response = self.client.get(reverse('reservas:registrar_prestamo') + '?paso=2')
        self.assertContains(response, self.unidad['id_unico'])
        self.assertEqual(response.context['equipo_ids'], [str(self.unidad['id'])])


class RequisitosAdeudosYAlertasTests(TestCase):
    def setUp(self):
        self.alumno = Usuario.objects.create_user(
            username='alumno-adeudo',
            password='test-pass',
            first_name='Ana',
            last_name='Pérez',
            boleta_credencial='2022647001',
            correo_institucional='ana-adeudo@alumno.ipn.mx',
            rol=Usuario.Rol.ALUMNO,
        )
        self.admin = Usuario.objects.create_user(
            username='admin-adeudo',
            password='test-pass',
            boleta_credencial='ADM-7001',
            correo_institucional='admin-adeudo@ipn.mx',
            rol=Usuario.Rol.ADMINISTRADOR,
        )
        self.laboratorista = Usuario.objects.create_user(
            username='lab-adeudo',
            password='test-pass',
            boleta_credencial='LAB-7001',
            correo_institucional='lab-adeudo@ipn.mx',
            rol=Usuario.Rol.LABORATORISTA,
        )

    def _crear_prestamo(self, equipo, fecha_limite=None):
        ahora = timezone.localtime()
        if fecha_limite is None:
            fecha_limite = ahora + timedelta(minutes=90)
        return SolicitudPrestamo.objects.create(
            alumno=self.alumno,
            equipos=[{
                'id': 3,
                'id_unico': 'MIC-ESP32-003',
                'nombre': 'Tarjeta ESP32',
                'cantidad': 1,
                'prestamo_activo': True,
                'fecha_prestamo': ahora.isoformat(),
                'fecha_limite': fecha_limite.isoformat(),
                **equipo,
            }],
            fecha=ahora.date(),
            bloque='Ventanilla',
            estatus=SolicitudPrestamo.Estatus.ATENDIDA,
        )

    def test_student_warning_is_scheduled_fifteen_minutes_before_due(self):
        ahora = timezone.localtime()
        limite = ahora + timedelta(minutes=90)
        self._crear_prestamo({'devuelto': False}, limite)

        alerta = obtener_alertas_prestamo(self.alumno, ahora)[0]

        self.assertEqual(
            datetime.fromisoformat(alerta['fecha_aviso']),
            limite - timedelta(minutes=15),
        )

    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        DEFAULT_FROM_EMAIL='laboratorio@ipn.mx',
    )
    def test_expired_loan_sends_one_email_to_student(self):
        solicitud = self._crear_prestamo(
            {'devuelto': False},
            timezone.localtime() - timedelta(minutes=1),
        )

        self.assertEqual(sincronizar_adeudos(), 1)
        self.assertEqual(sincronizar_adeudos(), 0)

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, [self.alumno.correo_institucional])
        self.assertIn(solicitud.folio, mail.outbox[0].subject)
        self.assertIn('MIC-ESP32-003', mail.outbox[0].body)
        self.assertIsNotNone(
            Adeudo.objects.get(solicitud=solicitud).correo_vencimiento_enviado_en
        )

    def test_admin_notifications_are_live_data_and_not_available_to_other_roles(self):
        solicitud = SolicitudPrestamo.objects.create(
            alumno=self.alumno,
            equipos=[{'nombre': 'Tarjeta ESP32', 'cantidad': 1}],
            fecha=timezone.localdate(),
            bloque='10:00 - 11:30',
        )
        client = Client()
        client.force_login(self.admin)

        response = client.get(reverse('reservas:notificaciones_admin'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['eventos'][0]['id'], f'solicitud:{solicitud.pk}')

        client.force_login(self.laboratorista)
        response = client.get(reverse('reservas:notificaciones_admin'))
        self.assertEqual(response.status_code, 302)

    def test_adeudos_are_admin_only_created_from_damage_and_liquidated_with_history(self):
        solicitud = self._crear_prestamo({
            'devuelto': True,
            'estatus_devolucion': 'DANADO',
            'observaciones_devolucion': 'Conector roto',
        })
        client = Client()
        client.force_login(self.admin)

        response = client.get(reverse('reservas:adeudos'))

        self.assertEqual(response.status_code, 200)
        adeudo = Adeudo.objects.get(solicitud=solicitud)
        self.alumno.refresh_from_db()
        self.assertEqual(adeudo.tipo, Adeudo.Tipo.DANADO)
        self.assertEqual(self.alumno.estatus, Usuario.Estatus.SANCIONADO)
        self.assertEqual(adeudo.historial.count(), 1)

        respuesta_filtrada = client.get(reverse('reservas:adeudos'), {
            'q': self.alumno.boleta_credencial,
            'estatus': 'ACTIVO',
            'fecha': timezone.localtime(adeudo.creado_en).date().isoformat(),
        })
        self.assertEqual(respuesta_filtrada.context['total_registros'], 1)
        self.assertEqual(len(respuesta_filtrada.context['adeudos']), 1)

        client.force_login(self.laboratorista)
        self.assertEqual(client.get(reverse('reservas:adeudos')).status_code, 302)

        client.force_login(self.admin)
        response = client.post(reverse('reservas:adeudos'), {
            'accion': 'valorar',
            'adeudo_id': adeudo.pk,
            'monto': '125.50',
            'pieza_reposicion': '',
        })
        self.assertRedirects(response, reverse('reservas:adeudos'), fetch_redirect_response=False)
        adeudo.refresh_from_db()
        self.assertEqual(str(adeudo.monto), '125.50')

        response = client.post(reverse('reservas:adeudos'), {
            'accion': 'liquidar',
            'adeudo_id': adeudo.pk,
            'confirmar_liquidacion': 'on',
        })
        self.assertRedirects(response, reverse('reservas:adeudos'), fetch_redirect_response=False)
        adeudo.refresh_from_db()
        self.alumno.refresh_from_db()
        self.assertEqual(adeudo.estatus, Adeudo.Estatus.LIQUIDADO)
        self.assertEqual(self.alumno.estatus, Usuario.Estatus.ACTIVO)
        self.assertEqual(
            list(adeudo.historial.values_list('accion', flat=True)),
            [
                HistorialAdeudo.Accion.LIQUIDADO,
                HistorialAdeudo.Accion.ACTUALIZADO,
                HistorialAdeudo.Accion.REGISTRADO,
            ],
        )

    def test_overdue_unreturned_loan_creates_debt_and_sanctions_student(self):
        solicitud = self._crear_prestamo(
            {'devuelto': False},
            timezone.localtime() - timedelta(minutes=1),
        )
        client = Client()
        client.force_login(self.admin)

        response = client.get(reverse('reservas:adeudos'))

        self.assertEqual(response.status_code, 200)
        adeudo = Adeudo.objects.get(solicitud=solicitud)
        self.alumno.refresh_from_db()
        self.assertEqual(adeudo.tipo, Adeudo.Tipo.NO_DEVUELTO)
        self.assertEqual(self.alumno.estatus, Usuario.Estatus.SANCIONADO)

    def test_financial_export_is_admin_only(self):
        self._crear_prestamo({
            'devuelto': True,
            'estatus_devolucion': 'DANADO',
            'observaciones_devolucion': 'Pantalla rota',
        })
        client = Client()
        client.force_login(self.admin)

        response = client.get(reverse('reservas:adeudos'), {'exportar': 'csv'})

        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('Pantalla rota', response.content.decode('utf-8-sig'))

        client.force_login(self.alumno)
        self.assertEqual(
            client.get(reverse('reservas:adeudos'), {'exportar': 'csv'}).status_code,
            302,
        )

    def test_role_dashboards_show_only_their_required_alert_mechanisms(self):
        client = Client()
        client.force_login(self.alumno)
        respuesta_alumno = client.get(reverse('dashboard'))
        self.assertContains(respuesta_alumno, 'alertas-prestamo-data')
        self.assertContains(respuesta_alumno, 'Tu préstamo de')

        client.force_login(self.admin)
        respuesta_admin = client.get(reverse('dashboard'))
        self.assertContains(
            respuesta_admin,
            reverse('reservas:notificaciones_admin'),
        )
        self.assertContains(respuesta_admin, 'window.setInterval(consultar, 15000)')

        client.force_login(self.laboratorista)
        respuesta_laboratorista = client.get(reverse('dashboard'))
        self.assertContains(respuesta_laboratorista, 'Resumen del laboratorio')
        self.assertContains(respuesta_laboratorista, 'Préstamos activos')
        self.assertNotContains(respuesta_laboratorista, reverse('reservas:adeudos'))

    def test_loan_history_filters_by_student_and_shows_exact_delivery_and_return(self):
        ahora = timezone.localtime()
        entrega = ahora - timedelta(hours=2)
        devolucion = ahora - timedelta(hours=1)
        self._crear_prestamo({
            'devuelto': True,
            'estatus_devolucion': 'DISPONIBLE',
            'fecha_prestamo': entrega.isoformat(),
            'fecha_devolucion': devolucion.isoformat(),
        })
        client = Client()
        client.force_login(self.admin)

        response = client.get(reverse('reservas:reporte_prestamos'), {
            'q': self.alumno.boleta_credencial,
            'estatus': 'DEVUELTO',
            'fecha': devolucion.date().isoformat(),
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_registros'], 1)
        self.assertContains(response, self.alumno.boleta_credencial)
        self.assertContains(response, 'MIC-ESP32-003')
        self.assertContains(response, entrega.strftime('%d/%m/%Y %H:%M'))
        self.assertContains(response, devolucion.strftime('%d/%m/%Y %H:%M'))
        self.assertContains(response, 'Devuelto en buen estado')

    def test_loan_history_paginates_twenty_records(self):
        for indice in range(21):
            self._crear_prestamo({
                'devuelto': False,
                'id_unico': f'TEST-{indice:03d}',
            })
        client = Client()
        client.force_login(self.admin)

        response = client.get(reverse('reservas:reporte_prestamos'), {'page': '2'})

        self.assertEqual(response.context['total_registros'], 21)
        self.assertEqual(len(response.context['prestamos']), 1)
        self.assertEqual(response.context['page_obj'].number, 2)

    def test_admin_and_laboratorista_dashboard_summaries_count_live_operations(self):
        self._crear_prestamo({'devuelto': False})
        self._crear_prestamo(
            {'devuelto': False},
            timezone.localtime() - timedelta(minutes=1),
        )
        SolicitudPrestamo.objects.create(
            alumno=self.alumno,
            equipos=[{'nombre': 'ESP32', 'cantidad': 1}],
            fecha=timezone.localdate(),
            bloque='10:00 - 11:30',
            estatus=SolicitudPrestamo.Estatus.CONFIRMADA,
        )
        client = Client()

        for usuario in (self.admin, self.laboratorista):
            client.force_login(usuario)
            response = client.get(reverse('dashboard'))
            self.assertEqual(response.context['admin_summary']['prestamos_activos'], 2)
            self.assertEqual(response.context['admin_summary']['prestamos_vencidos'], 1)
            self.assertEqual(response.context['admin_summary']['solicitudes_pendientes'], 1)


class ReportesMensualesTests(TestCase):
    def setUp(self):
        self.operador = Usuario.objects.create_user(
            username='lab-reportes',
            password='test-pass',
            boleta_credencial='LAB-REPORTES',
            correo_institucional='lab-reportes@ipn.mx',
            rol=Usuario.Rol.LABORATORISTA,
        )
        self.alumno = Usuario.objects.create_user(
            username='alumno-reportes',
            password='test-pass',
            boleta_credencial='20260099',
            correo_institucional='alumno-reportes@ipn.mx',
            rol=Usuario.Rol.ALUMNO,
        )
        self.client.force_login(self.operador)

    def test_dashboard_links_to_monthly_reports_only_for_operators(self):
        response = self.client.get(reverse('dashboard'))

        self.assertContains(response, 'Reportes mensuales')
        self.assertContains(response, reverse('reservas:reportes_mensuales'))

        self.client.force_login(self.alumno)
        response = self.client.get(reverse('dashboard'))
        self.assertNotContains(response, reverse('reservas:reportes_mensuales'))

    def test_report_list_contains_matching_pdfs_newest_first(self):
        with TemporaryDirectory() as temp_dir:
            carpeta = Path(temp_dir) / 'media' / 'reportes_mensuales'
            carpeta.mkdir(parents=True)
            (carpeta / 'Reporte_Inventario_2026-10.pdf').write_bytes(b'%PDF older')
            (carpeta / 'Reporte_Inventario_2026-11.pdf').write_bytes(b'%PDF newer')
            (carpeta / 'not-a-monthly-report.pdf').write_bytes(b'%PDF ignored')

            with override_settings(BASE_DIR=temp_dir):
                response = self.client.get(reverse('reservas:reportes_mensuales'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [reporte['periodo'] for reporte in response.context['reportes']],
            ['2026-11', '2026-10'],
        )
        self.assertContains(response, 'Reporte_Inventario_2026-11.pdf')
        self.assertNotContains(response, 'not-a-monthly-report.pdf')
        self.assertContains(response, 'target="_blank" rel="noopener"')

    def test_pdf_opens_inline_and_is_restricted_to_operators(self):
        contenido_pdf = b'%PDF-1.4 test report'
        nombre = 'Reporte_Inventario_2026-11.pdf'
        with TemporaryDirectory() as temp_dir:
            carpeta = Path(temp_dir) / 'media' / 'reportes_mensuales'
            carpeta.mkdir(parents=True)
            (carpeta / nombre).write_bytes(contenido_pdf)

            with override_settings(BASE_DIR=temp_dir):
                response = self.client.get(
                    reverse('reservas:reporte_mensual_pdf', args=[nombre])
                )
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response['Content-Type'], 'application/pdf')
                self.assertTrue(response['Content-Disposition'].startswith('inline;'))
                self.assertEqual(b''.join(response.streaming_content), contenido_pdf)

                self.client.force_login(self.alumno)
                response = self.client.get(reverse('reservas:reportes_mensuales'))

        self.assertEqual(response.status_code, 302)
