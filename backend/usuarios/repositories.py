"""Repositories: único ponto de acesso ao banco (consultas e gravações do ORM).

Não contém regra de negócio.
"""

from django.utils import timezone

from .models import Usuario


def buscar_por_id(usuario_id):
    return Usuario.objects.filter(pk=usuario_id).first()


def registrar_ultimo_acesso(usuario):
    usuario.last_login = timezone.now()
    usuario.save(update_fields=["last_login"])
