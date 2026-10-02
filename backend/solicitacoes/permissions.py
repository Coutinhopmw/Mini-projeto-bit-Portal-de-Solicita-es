"""Autorização por dono da solicitação."""

from rest_framework.permissions import BasePermission

from usuarios.models import Papel


class EhAutor(BasePermission):
    """Só o autor da solicitação passa. Vale para editar e excluir (D05).

    É uma permissão de objeto: a view deve chamar `self.check_object_permissions` depois
    de buscar a solicitação. Quem nem enxerga a solicitação (outro Solicitante) recebe 404
    antes de chegar aqui; quem a enxerga mas não é o autor (um Atendente) recebe 403.
    """

    def has_object_permission(self, request, view, obj):
        return obj.solicitante_id == request.user.pk


class EhAtendenteNoObjeto(BasePermission):
    """Só o Atendente altera o status, inclusive o das solicitações que ele mesmo abriu (D02).

    É checada por objeto, e não na entrada da view, para respeitar a ordem do PLN-01: quem
    nem enxerga a solicitação recebe 404 antes de descobrir que o perfil não basta (403).
    """

    def has_object_permission(self, request, view, obj):
        return request.user.papel == Papel.ATENDENTE
