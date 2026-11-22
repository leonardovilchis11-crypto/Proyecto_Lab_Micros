from django.contrib.auth import login as auth_login, logout as auth_logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.views.decorators.http import require_POST
from .models import Usuario
from .forms import (
    LoginForm,
    RegistroAlumnoForm,
    RegistroPersonalForm,
    RegistroLaboratoristaPublicoForm,
    EditarUsuarioForm,
)
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode
from django.utils.encoding import force_bytes
from django.core.mail import send_mail
from django.conf import settings
from django.contrib import messages
from reservas.models import Adeudo, SolicitudPrestamo
from reservas.services import sincronizar_adeudos


def login_view(request):
    """Inicio de sesión con nombre/usuario, boleta/credencial y clave, conservando datos al fallar."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = LoginForm(request, data=request.POST)
        if form.is_valid():
            auth_login(request, form.get_user())
            siguiente = request.GET.get('next') or request.POST.get('next')
            if siguiente and siguiente.startswith('/'):
                return redirect(siguiente)
            return redirect('dashboard')
    else:
        form = LoginForm(request)

    return render(request, 'usuarios/login.html', {'form': form})


def registrar_alumno(request):
    if request.method == 'POST':
        form = RegistroAlumnoForm(request.POST)
        if form.is_valid():
            alumno = form.save(commit=False)
            alumno.set_password(form.cleaned_data['password'])
            alumno.rol = Usuario.Rol.ALUMNO
            alumno.save()
            messages.success(request, 'Registro de alumno completado. Ya puedes iniciar sesión.')
            return redirect('login')
    else:
        form = RegistroAlumnoForm()
    return render(request, 'usuarios/registro_alumno.html', {'form': form})


@login_required
def mi_cuenta(request):
    usuario = Usuario.objects.get(pk=request.user.pk)

    if usuario.rol == Usuario.Rol.ALUMNO:
        sincronizar_adeudos(alumno=usuario)
        usuario.refresh_from_db(fields=['estatus'])

    return render(request, 'usuarios/mi_cuenta.html', {'usuario': usuario})


def _motivos_bloqueo_eliminacion(usuario_objetivo):
    """Verifica préstamos activos y adeudos registrados (Req. 1.5 y 1.5.1)."""
    if getattr(usuario_objetivo, 'rol', None) != Usuario.Rol.ALUMNO:
        return []

    sincronizar_adeudos(alumno=usuario_objetivo)
    motivos = []

    adeudos_activos = Adeudo.objects.filter(
        alumno=usuario_objetivo,
        estatus=Adeudo.Estatus.ACTIVO,
    ).count()
    if adeudos_activos:
        motivos.append(f"tiene {adeudos_activos} adeudo(s) activo(s) pendiente(s) de liquidar")

    adeudos_historicos = Adeudo.objects.filter(alumno=usuario_objetivo).count()
    if adeudos_historicos and not adeudos_activos:
        motivos.append(f"cuenta con {adeudos_historicos} adeudo(s) registrado(s) en su historial de auditoría")

    prestamos_activos = sum(
        1
        for solicitud in SolicitudPrestamo.objects.filter(
            alumno=usuario_objetivo,
            estatus=SolicitudPrestamo.Estatus.ATENDIDA,
        )
        for equipo in solicitud.equipos
        if isinstance(equipo, dict) and equipo.get('prestamo_activo') and not equipo.get('devuelto')
    )
    if prestamos_activos:
        motivos.append(f"tiene {prestamos_activos} equipo(s) en préstamo activo sin devolver")

    if usuario_objetivo.estatus == Usuario.Estatus.SANCIONADO and not motivos:
        motivos.append("su cuenta presenta estatus Sancionado")

    return motivos


@login_required
@user_passes_test(lambda u: u.rol == Usuario.Rol.ADMINISTRADOR)
def padron_usuarios(request):
    query = request.GET.get('q', '').strip()
    if query:
        usuarios_qs = Usuario.objects.filter(
            Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(boleta_credencial__icontains=query)
        )
    else:
        usuarios_qs = Usuario.objects.all()

    usuarios = list(usuarios_qs)
    for u in usuarios:
        if u.pk == request.user.pk:
            u.puede_eliminarse = False
            u.motivo_bloqueo = "No puedes eliminar tu propia cuenta de Administrador activa."
        else:
            motivos = _motivos_bloqueo_eliminacion(u)
            u.puede_eliminarse = len(motivos) == 0
            u.motivo_bloqueo = (
                "No se puede eliminar ya que cuenta con adeudos (" + " y ".join(motivos) + ")."
                if motivos
                else ""
            )

    return render(request, 'usuarios/padron_usuarios.html', {'usuarios': usuarios, 'query': query})


@login_required
@user_passes_test(lambda u: u.rol == Usuario.Rol.ADMINISTRADOR)
def editar_usuario(request, user_id):
    """Permite al Administrador editar los datos, rol o estatus de un usuario."""
    usuario_objetivo = get_object_or_404(Usuario, id=user_id)

    if request.method == 'POST':
        form = EditarUsuarioForm(request.POST, instance=usuario_objetivo)
        if form.is_valid():
            usuario_editado = form.save()
            messages.success(
                request,
                f"Los datos de {usuario_editado.nombre_completo} ({usuario_editado.boleta_credencial}) fueron actualizados.",
            )
            return redirect('padron_usuarios')
    else:
        form = EditarUsuarioForm(instance=usuario_objetivo)

    return render(request, 'usuarios/editar_usuario.html', {
        'form': form,
        'usuario_objetivo': usuario_objetivo,
    })


@login_required
@user_passes_test(lambda u: u.rol == Usuario.Rol.ADMINISTRADOR)
def eliminar_usuario(request, user_id):
    """Pantalla 7 / REQ-1.5 y 1.5.1: Eliminar usuario con validación de adeudos y préstamos."""
    usuario_a_eliminar = get_object_or_404(Usuario, id=user_id)

    if usuario_a_eliminar == request.user:
        return render(request, 'usuarios/error_eliminacion.html', {
            'mensaje': 'No puedes eliminar tu propia cuenta de Administrador activa.'
        })

    motivos = _motivos_bloqueo_eliminacion(usuario_a_eliminar)
    if motivos:
        return render(request, 'usuarios/error_eliminacion.html', {
            'mensaje': (
                f'No es posible eliminar al usuario {usuario_a_eliminar.boleta_credencial} '
                f'porque {" y ".join(motivos)}. Regulariza su situación antes de darlo de baja.'
            )
        })

    if request.method == 'POST':
        boleta = usuario_a_eliminar.boleta_credencial
        usuario_a_eliminar.delete()
        messages.success(request, f'El usuario {boleta} fue eliminado correctamente del padrón.')
        return redirect('padron_usuarios')

    return render(request, 'usuarios/eliminar_usuario.html', {'usuario_objetivo': usuario_a_eliminar})


@login_required
def dashboard(request):
    """Pantalla 9: Panel de Inicio Operativo según el rol del usuario."""
    loan_alerts = []
    admin_summary = None
    if request.user.rol == Usuario.Rol.ALUMNO:
        from reservas.services import obtener_alertas_prestamo, sincronizar_adeudos

        sincronizar_adeudos(alumno=request.user)
        loan_alerts = obtener_alertas_prestamo(request.user)
    elif request.user.rol in (
        Usuario.Rol.ADMINISTRADOR,
        Usuario.Rol.LABORATORISTA,
    ):
        from reservas.models import SolicitudPrestamo
        from reservas.services import obtener_prestamos_vencidos
        from inventario.views import INVENTARIO_ITEMS

        if request.user.rol == Usuario.Rol.ADMINISTRADOR:
            from reservas.services import sincronizar_adeudos

            sincronizar_adeudos()
        prestamos_activos = 0
        solicitudes_activas = SolicitudPrestamo.objects.filter(
            estatus=SolicitudPrestamo.Estatus.ATENDIDA,
        )
        for solicitud in solicitudes_activas:
            prestamos_activos += sum(
                1 for equipo in solicitud.equipos
                if isinstance(equipo, dict)
                and equipo.get('prestamo_activo')
                and not equipo.get('devuelto')
            )
        admin_summary = {
            'prestamos_activos': prestamos_activos,
            'prestamos_vencidos': len(obtener_prestamos_vencidos()),
            'solicitudes_pendientes': SolicitudPrestamo.objects.filter(
                estatus__in=(
                    SolicitudPrestamo.Estatus.CONFIRMADA,
                    SolicitudPrestamo.Estatus.SIN_CONFIRMAR,
                )
            ).count(),
            'equipos_mantenimiento': sum(
                1 for equipo in INVENTARIO_ITEMS
                if equipo.get('estatus') == 'MANTENIMIENTO'
            ),
        }

    return render(request, 'usuarios/dashboard.html', {
        'usuario': request.user,
        'loan_alerts': loan_alerts,
        'admin_summary': admin_summary,
    })


@require_POST
def mantener_sesion(request):
    if not request.user.is_authenticated:
        return JsonResponse({'ok': False}, status=401)
    return JsonResponse({'ok': True})


@require_POST
def cerrar_sesion(request):
    por_inactividad = request.POST.get('inactividad') == '1'
    auth_logout(request)
    destino = reverse('login')
    if por_inactividad:
        destino = f'{destino}?inactividad=1'
    return redirect(destino)


@login_required
@user_passes_test(lambda u: u.rol == Usuario.Rol.ADMINISTRADOR)
def registrar_personal(request):
    """Pantalla 3 / REQ-1.0.3: Alta de personal operativo (Solo Admin)."""
    if request.method == 'POST':
        form = RegistroPersonalForm(request.POST)
        if form.is_valid():
            personal = form.save(commit=False)
            personal.set_password(form.cleaned_data['password'])
            personal.save()
            return redirect('padron_usuarios')
    else:
        form = RegistroPersonalForm()
    return render(request, 'usuarios/registro_personal.html', {'form': form})


def solicitar_recuperacion_clave(request):
    """Paso 1 (Req. 1.1.3): Envía enlace real vía Gmail SMTP buscando en correo_institucional."""
    if request.method == 'POST':
        correo = request.POST.get('email', '').strip()
        boleta = request.POST.get('boleta_credencial', '').strip()

        filtro = Q(correo_institucional__iexact=correo) | Q(email__iexact=correo)
        usuario = Usuario.objects.filter(filtro).first()
        if boleta and usuario and usuario.boleta_credencial != boleta:
            usuario = None

        if usuario:
            destino = usuario.correo_institucional or usuario.email
            uid = urlsafe_base64_encode(force_bytes(usuario.pk))
            token = default_token_generator.make_token(usuario)
            ruta = reverse('password_reset_confirm', kwargs={'uidb64': uid, 'token': token})
            enlace = request.build_absolute_uri(ruta)

            send_mail(
                subject='[ESIME Culhuacán] Restablecimiento de contraseña',
                message=(
                    f'Hola {usuario.first_name or usuario.boleta_credencial},\n\n'
                    f'Para crear una nueva contraseña en el Sistema del Laboratorio de Microprocesadores, '
                    f'entra al siguiente enlace:\n\n{enlace}\n\n'
                    f'Si no solicitaste este cambio, ignora este mensaje.\n\n'
                    f'Atentamente,\nLaboratorio de Microprocesadores — ESIME Culhuacán'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[destino],
                fail_silently=False,
            )

        return redirect('password_reset_done')

    return render(request, 'usuarios/recuperar_clave.html')


def seleccionar_tipo_registro(request):
    """Pantalla intermedia desde el login para elegir perfil Alumno o Laboratorista."""
    return render(request, 'usuarios/seleccionar_registro.html')


def registrar_laboratorista_publico(request):
    """Formulario de registro abierto para personal Laboratorista."""
    if request.method == 'POST':
        form = RegistroLaboratoristaPublicoForm(request.POST)
        if form.is_valid():
            lab = form.save(commit=False)
            lab.set_password(form.cleaned_data['password'])
            lab.rol = Usuario.Rol.LABORATORISTA
            lab.save()
            return redirect('login')
    else:
        form = RegistroLaboratoristaPublicoForm()
    return render(request, 'usuarios/registro_laboratorista.html', {'form': form})


