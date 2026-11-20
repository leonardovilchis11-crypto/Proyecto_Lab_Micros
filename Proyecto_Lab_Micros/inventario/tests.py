from collections import Counter
from copy import deepcopy

from django.test import TestCase
from django.urls import reverse

from .views import INVENTARIO_ITEMS


class GestionInventarioTests(TestCase):
    def setUp(self):
        self.original_items = deepcopy(INVENTARIO_ITEMS)
        INVENTARIO_ITEMS[:] = [
            {
                'id': index,
                'id_unico': f'TEST-{index:03d}',
                'nombre': f'Equipo {index:03d}',
                'categoria': 'Microcontroladores',
                'estante': 'Estante A',
                'cajon': f'Cajón {index}',
                'estatus': 'MANTENIMIENTO' if index == 21 else 'DISPONIBLE',
                'especificaciones': '',
                'observaciones': '',
                'motivo_baja': '',
            }
            for index in range(1, 22)
        ]

    def tearDown(self):
        INVENTARIO_ITEMS[:] = self.original_items

    def test_inventory_filters_sorts_and_paginates_twenty_records(self):
        primera_pagina = self.client.get(reverse('inventario:gestion'))

        self.assertEqual(primera_pagina.context['total_registros'], 21)
        self.assertEqual(len(primera_pagina.context['materiales']), 20)
        self.assertEqual(primera_pagina.context['page_obj'].number, 1)
        self.assertContains(primera_pagina, 'Mostrando 1–20 de 21 unidades.')

        segunda_pagina = self.client.get(reverse('inventario:gestion'), {'page': '2'})

        self.assertEqual(segunda_pagina.context['total_registros'], 21)
        self.assertEqual(len(segunda_pagina.context['materiales']), 1)
        self.assertEqual(segunda_pagina.context['page_obj'].number, 2)
        self.assertEqual(
            segunda_pagina.context['materiales'][0]['id_unico'],
            'TEST-021',
        )

        filtrada = self.client.get(reverse('inventario:gestion'), {
            'estatus': 'MANTENIMIENTO',
            'orden': 'id_unico',
            'direccion': 'desc',
        })
        self.assertEqual(filtrada.context['total_registros'], 1)
        self.assertEqual(filtrada.context['materiales'][0]['id_unico'], 'TEST-021')


class CantidadPorModeloTests(TestCase):
    def test_inventory_has_five_individual_units_per_model(self):
        cantidades = Counter(item['nombre'] for item in INVENTARIO_ITEMS)
        identificadores = [item['id_unico'] for item in INVENTARIO_ITEMS]

        self.assertEqual(len(cantidades), 14)
        self.assertEqual(set(cantidades.values()), {5})
        self.assertEqual(len(identificadores), len(set(identificadores)))
        self.assertEqual(len(INVENTARIO_ITEMS), 70)

        catalogo = self.client.get(reverse('catalogo:lista'))
        self.assertEqual(catalogo.status_code, 200)
        self.assertEqual(
            {equipo['total_unidades'] for equipo in catalogo.context['equipos']},
            {5},
        )
