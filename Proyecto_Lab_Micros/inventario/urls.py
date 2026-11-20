from django.urls import path
from . import views

app_name = 'inventario'

urlpatterns = [
    path('', views.gestion_inventario, name='gestion'),
    path('nuevo/', views.nuevo_material, name='nuevo'),
    path('editar/<int:item_id>/', views.editar_material, name='editar'),
]