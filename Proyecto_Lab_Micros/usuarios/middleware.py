from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from .horario import laboratorio_abierto


class BloqueoFueraHorarioMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if laboratorio_abierto():
            return self.get_response(request)

        ruta = request.path or ''
        rutas_permitidas = set()
        for nombre_url in ('login', 'logout', 'mi_cuenta'):
            try:
                rutas_permitidas.add(reverse(nombre_url))
            except NoReverseMatch:
                pass

        if (
            ruta.startswith('/admin/')
            or ruta.startswith('/static/')
            or ruta in rutas_permitidas
        ):
            return self.get_response(request)

        return render(
            request,
            'shared/fuera_de_horario.html',
            status=503,
        )

    