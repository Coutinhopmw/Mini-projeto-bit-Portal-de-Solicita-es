from django.core.management import call_command
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Prepara o banco com um comando: aplica as migrations e carrega o seed."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sem-seed",
            action="store_true",
            help="Aplica só as migrations, sem os dados de demonstração.",
        )

    def handle(self, *args, **opcoes):
        call_command("migrate", interactive=False, verbosity=opcoes["verbosity"])
        if not opcoes["sem_seed"]:
            call_command("carregar_seed", verbosity=opcoes["verbosity"])
        self.stdout.write(self.style.SUCCESS("Banco pronto."))
