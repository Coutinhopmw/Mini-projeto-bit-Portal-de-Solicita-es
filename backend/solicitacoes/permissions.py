"""Autorização por dono da solicitação."""

from rest_framework.permissions import BasePermission


class EhAutor(BasePermission):
    """Só o autor da solicitação passa. Vale para editar e excluir (D05).

    É uma permissão de objeto: a view deve chamar `self.check_object_permissions` depois
    de buscar a solicitação. Quem nem enxerga a solicitação (outro Solicitante) recebe 404
    antes de chegar aqui; quem a enxerga mas não é o autor (um Atendente) recebe 403.
    """

    def has_object_permission(self, request, view, obj):
        return obj.solicitante_id == request.user.pk
