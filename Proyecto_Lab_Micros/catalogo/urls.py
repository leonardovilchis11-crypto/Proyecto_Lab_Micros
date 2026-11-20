from django.urls import path
from . import views

app_name = 'catalogo'

urlpatterns = [
    path('', views.vista_catalogo, name='lista'),
    path('detalle/<int:item_id>/', views.detalle_equipo, name='detalle'),
    path('agregar-carrito/<int:item_id>/', views.agregar_al_carrito, name='agregar_carrito'),
]