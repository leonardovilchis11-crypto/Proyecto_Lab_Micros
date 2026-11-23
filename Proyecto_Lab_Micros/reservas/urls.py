from django.urls import path
from . import views

app_name = 'reservas'

urlpatterns = [
    path('carrito/', views.vista_carrito, name='carrito'),
    path('mis-reservas/', views.vista_mis_reservas, name='mis_reservas'),
    path('cancelar/<str:folio>/', views.cancelar_reserva_alumno, name='cancelar_reserva'),
    path('fuera-horario/', views.vista_fuera_horario, name='fuera_horario'),
    path('bandeja/', views.vista_bandeja_solicitudes, name='bandeja_solicitudes'),
    path('ventanilla/prestamo/', views.vista_registrar_prestamo, name='registrar_prestamo'),
    path('prestamo-registrado/<str:folio>/', views.prestamo_registrado, name='prestamo_registrado'),
    path('comprobante/<str:folio>/', views.comprobante_prestamo, name='comprobante'),
    path('reportes/prestamos/', views.vista_reporte_prestamos, name='reporte_prestamos'),
    path('reportes/mensuales/', views.vista_reportes_mensuales, name='reportes_mensuales'),
    path(
        'reportes/mensuales/<str:nombre_archivo>/',
        views.vista_reporte_mensual_pdf,
        name='reporte_mensual_pdf',
    ),
    path('devoluciones/', views.vista_devoluciones, name='devoluciones'),
    path('adeudos/', views.vista_adeudos, name='adeudos'),
    path('historial/', views.vista_historial_prestamos, name='historial_prestamos'),
    path('notificaciones/admin/', views.notificaciones_administrador, name='notificaciones_admin'),
]

