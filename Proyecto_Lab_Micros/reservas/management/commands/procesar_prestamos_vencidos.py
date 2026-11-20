from django.core.management.base import BaseCommand

from reservas.services import sincronizar_adeudos


class Command(BaseCommand):
    help = 'Registra préstamos vencidos y envía el aviso por correo al alumno.'

    def handle(self, *args, **options):
        enviados = sincronizar_adeudos()
        self.stdout.write(
            self.style.SUCCESS(f'Avisos de vencimiento enviados: {enviados}')
        )
