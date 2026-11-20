from django.test import TestCase
from django.urls import reverse

from .models import Usuario


class MiCuentaTests(TestCase):
    def setUp(self):
        self.usuario = Usuario.objects.create_user(
            username='20260001',
            boleta_credencial='20260001',
            correo_institucional='alumno01@alumno.ipn.mx',
            first_name='Alumno',
            last_name='Prueba',
            rol=Usuario.Rol.ALUMNO,
            estatus=Usuario.Estatus.ACTIVO,
            password='Clave-segura-123',
        )

    def test_mi_cuenta_muestra_datos_del_usuario(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse('mi_cuenta'))

        self.assertEqual(respuesta.status_code, 200)
        self.assertContains(respuesta, 'Alumno Prueba')
        self.assertContains(respuesta, '20260001')
        self.assertContains(respuesta, 'alumno01@alumno.ipn.mx')
        self.assertContains(respuesta, 'Alumno')
        self.assertContains(respuesta, 'Activo')


class CierreSesionInactividadTests(TestCase):
    def setUp(self):
        self.usuario = Usuario(
            username='alumno01',
            boleta_credencial='20260001',
            correo_institucional='alumno01@example.com',
            first_name='Alumno',
            last_name='Prueba',
        )
        self.usuario.set_password('Clave-segura-123')
        self.usuario.save()

    def test_keepalive_requires_authenticated_post(self):
        url = reverse('session_keepalive')

        respuesta_anonima = self.client.post(url)
        self.assertEqual(respuesta_anonima.status_code, 401)

        self.client.force_login(self.usuario)
        respuesta_autenticada = self.client.post(url)
        self.assertEqual(respuesta_autenticada.status_code, 200)
        self.assertJSONEqual(respuesta_autenticada.content, {'ok': True})
        self.assertEqual(self.client.get(url).status_code, 405)

    def test_logout_marks_session_as_inactive_only_when_requested(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.post(reverse('logout'))
        self.assertRedirects(respuesta, reverse('login'))

        self.client.force_login(self.usuario)
        respuesta = self.client.post(reverse('logout'), {'inactividad': '1'})
        self.assertRedirects(respuesta, f"{reverse('login')}?inactividad=1")

    def test_login_displays_inactivity_message(self):
        respuesta = self.client.get(reverse('login'), {'inactividad': '1'})

        self.assertContains(respuesta, 'Tu sesión se cerró automáticamente por inactividad.')

    def test_authenticated_page_includes_session_timeout_prompt(self):
        self.client.force_login(self.usuario)

        respuesta = self.client.get(reverse('dashboard'))

        self.assertContains(respuesta, 'aviso-inactividad')
        self.assertContains(respuesta, reverse('session_keepalive'))
