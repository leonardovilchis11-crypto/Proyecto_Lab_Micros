from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # Pantalla 1: Inicio de sesión
    path('login/', views.login_view, name='login'),
    path('logout/', views.cerrar_sesion, name='logout'),
    path('sesion/continuar/', views.mantener_sesion, name='session_keepalive'),
    
    # Pantalla 2: Registro de alumnos
    path('registro/', views.registrar_alumno, name='registro_alumno'),
    path('seleccionar-registro/', views.seleccionar_tipo_registro, name='seleccionar_registro'),
    path('registro-laboratorista/', views.registrar_laboratorista_publico, name='registro_laboratorista'),
    
    # Pantalla 3: Alta de personal operativo
    path('alta-personal/', views.registrar_personal, name='registrar_personal'),

    # Pantalla 5: Recuperación y cambio de contraseña (REQ-1.2 / 1.4)
    path('recuperar-clave/', views.solicitar_recuperacion_clave, name='password_reset'),
    path('recuperar-clave/enviado/', auth_views.PasswordResetDoneView.as_view(template_name='usuarios/recuperar_clave_enviado.html'), name='password_reset_done'),
    path('reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='usuarios/recuperar_clave_confirmar.html'), name='password_reset_confirm'),
    path('reset/done/', auth_views.PasswordResetCompleteView.as_view(template_name='usuarios/recuperar_clave_completo.html'), name='password_reset_complete'),
    path('cambiar-clave/', auth_views.PasswordChangeView.as_view(template_name='usuarios/cambiar_clave.html', success_url='/usuarios/mi-cuenta/'), name='password_change'),

    # Pantalla 9: Panel de Inicio / Dashboard
    path('inicio/', views.dashboard, name='dashboard'),

    # Pantalla 12: Mi cuenta
    path('mi-cuenta/', views.mi_cuenta, name='mi_cuenta'),
    
    # Pantalla 7: Padrón de usuarios
    path('padron/', views.padron_usuarios, name='padron_usuarios'),
    path('eliminar/<int:user_id>/', views.eliminar_usuario, name='eliminar_usuario'),
]


