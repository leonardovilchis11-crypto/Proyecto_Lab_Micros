from django.contrib import admin
from django.urls import path, include
from django.shortcuts import redirect

urlpatterns = [
    path('admin/', admin.site.urls),
    path('usuarios/', include('usuarios.urls')),
    path('inventario/', include('inventario.urls')), # <-- Ruta M2
    path('catalogo/', include('catalogo.urls')),
    # Al entrar a la página principal http://127.0.0.1:8000/ redirige al login
    path('', lambda request: redirect('login')),
    path('reservas/', include('reservas.urls')),
]
