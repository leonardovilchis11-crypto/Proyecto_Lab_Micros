from django.shortcuts import render, redirect
from inventario.views import INVENTARIO_ITEMS, CATEGORIAS_SISTEMA

# Pantalla 4: Catálogo de equipos con filtros en tiempo real y semáforo (Req. 2.0, 2.0.1, 2.3)
def vista_catalogo(request):
    query = request.GET.get('q', '').strip()
    categoria = request.GET.get('categoria', '').strip()
    disponibilidad = request.GET.get('disponibilidad', '').strip()

    # Retiramos permanentemente las bajas definitivas de la vista general (Req. 5.2)
    items_activos = [m for m in INVENTARIO_ITEMS if m['estatus'] != 'BAJA_DEFINITIVA']

    # Agrupamos por modelo para mostrar el conteo real de unidades y el estado individual
    grupos = {}
    for item in items_activos:
        clave = item['nombre']
        if clave not in grupos:
            grupos[clave] = {
                'id_representante': item['id'],
                'id_unico_ejemplo': item['id_unico'],
                'nombre': item['nombre'],
                'categoria': item['categoria'],
                'estante': item['estante'],
                'cajon': item['cajon'],
                'especificaciones': item['especificaciones'],
                'total_unidades': 0,
                'disponibles': 0,
                'prestados': 0,
                'mantenimiento': 0,
                'unidades': [],
            }
        grupos[clave]['total_unidades'] += 1
        grupos[clave]['unidades'].append(item)
        if item['estatus'] == 'DISPONIBLE':
            grupos[clave]['disponibles'] += 1
        elif item['estatus'] == 'PRESTADO':
            grupos[clave]['prestados'] += 1
        else:
            grupos[clave]['mantenimiento'] += 1

    equipos = list(grupos.values())

    # Aplicación estricta de los filtros (Req. 2.0.1)
    if query:
        q_low = query.lower()
        equipos = [
            e for e in equipos
            if q_low in e['nombre'].lower()
            or q_low in e['id_unico_ejemplo'].lower()
            or q_low in e['especificaciones'].lower()
            or any(q_low in u['id_unico'].lower() for u in e['unidades'])
        ]

    if categoria:
        equipos = [e for e in equipos if e['categoria'] == categoria]

    if disponibilidad == 'DISPONIBLE':
        equipos = [e for e in equipos if e['disponibles'] > 0]
    elif disponibilidad == 'PRESTADO':
        equipos = [e for e in equipos if e['disponibles'] == 0 and e['prestados'] > 0]
    elif disponibilidad == 'MANTENIMIENTO':
        equipos = [e for e in equipos if e['disponibles'] == 0 and e['mantenimiento'] > 0]

    carrito = request.session.get('carrito_solicitud', [])

    context = {
        'equipos': equipos,
        'categorias': CATEGORIAS_SISTEMA,
        'query': query,
        'categoria_sel': categoria,
        'disponibilidad_sel': disponibilidad,
        'carrito_count': len(carrito),
        'mensaje_catalogo': request.session.pop('mensaje_catalogo', None),
    }
    return render(request, 'catalogo/catalogo.html', context)


# Ficha de Detalle del Equipo (Req. 2.0.2)
def detalle_equipo(request, item_id):
    equipo_base = next((m for m in INVENTARIO_ITEMS if m['id'] == item_id and m['estatus'] != 'BAJA_DEFINITIVA'), None)
    if not equipo_base:
        return redirect('catalogo:lista')

    unidades_modelo = [
        m for m in INVENTARIO_ITEMS
        if m['nombre'] == equipo_base['nombre'] and m['estatus'] != 'BAJA_DEFINITIVA'
    ]
    disponibles = sum(1 for u in unidades_modelo if u['estatus'] == 'DISPONIBLE')
    primera_disponible = next((u for u in unidades_modelo if u['estatus'] == 'DISPONIBLE'), equipo_base)

    # Conservamos los filtros previos en el botón "Regresar al catálogo" (Req. 2.0.2)
    q = request.GET.get('q', '')
    categoria = request.GET.get('categoria', '')
    disponibilidad = request.GET.get('disponibilidad', '')

    carrito = request.session.get('carrito_solicitud', [])

    return render(request, 'catalogo/detalle_equipo.html', {
        'equipo': primera_disponible,
        'unidades': unidades_modelo,
        'disponibles': disponibles,
        'total_unidades': len(unidades_modelo),
        'q': q,
        'categoria': categoria,
        'disponibilidad': disponibilidad,
        'carrito_count': len(carrito),
    })


def agregar_al_carrito(request, item_id):
    equipo = next((m for m in INVENTARIO_ITEMS if m['id'] == item_id), None)
    if equipo and equipo['estatus'] == 'DISPONIBLE':
        carrito = request.session.get('carrito_solicitud', [])
        carrito.append({'id': equipo['id'], 'id_unico': equipo['id_unico'], 'nombre': equipo['nombre']})
        request.session['carrito_solicitud'] = carrito
        request.session['mensaje_catalogo'] = f"Se agregó '{equipo['nombre']} ({equipo['id_unico']})' a tu carrito de solicitud."
    return redirect('catalogo:lista')