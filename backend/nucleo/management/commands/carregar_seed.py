from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

CAMINHO_SEED = settings.BASE_DIR.parent / "database" / "seed.sql"


class Command(BaseCommand):
    help = "Carrega os dados de demonstração de database/seed.sql. Pode rodar mais de uma vez."

    def handle(self, *args, **opcoes):
        if not CAMINHO_SEED.exists():
            raise CommandError(f"Arquivo não encontrado: {CAMINHO_SEED}")
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(CAMINHO_SEED.read_text(encoding="utf-8"))
        self.stdout.write(self.style.SUCCESS("Dados de demonstração carregados."))
