from datetime import time
from django.utils import timezone

HORA_APERTURA = time(7, 0)
HORA_CIERRE = time(22, 0)


def laboratorio_abierto(ahora=None):
    """Retorna True solo de Lunes a Viernes entre 07:00 y 22:00 hrs (hora local)."""
    dt = timezone.localtime(ahora or timezone.now())
    es_dia_habil = dt.weekday() < 5  # 0=Lunes ... 4=Viernes, 5=Sábado, 6=Domingo
    hora_actual = dt.time()
    en_hora = HORA_APERTURA <= hora_actual < HORA_CIERRE
    return es_dia_habil and en_hora


def horario_laboral_contexto(request):
    abierto = laboratorio_abierto()
    return {
        'laboratorio_abierto': abierto,
        'mensaje_fuera_horario': (
            'El servicio del laboratorio se encuentra cerrado por horario laboral. '
            'Atención de Lunes a Viernes de 07:00 a 22:00 hrs (sábados y domingos cerrado).'
        ),
    }

