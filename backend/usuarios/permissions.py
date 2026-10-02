"""Autorização por perfil. A autenticação (quem é o usuário) é feita em autenticacao.py."""

from rest_framework.permissions import BasePermission

from .models import Papel


class EhAtendente(BasePermission):
    """Só o Atendente passa. Usada, por exemplo, na alteração de status (D02)."""

    def has_permission(self, request, view):
        usuario = request.user
        return bool(usuario and usuario.is_authenticated and usuario.papel == Papel.ATENDENTE)
