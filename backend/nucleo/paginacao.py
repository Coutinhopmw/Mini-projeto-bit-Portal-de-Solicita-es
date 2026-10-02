from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.pagination import PageNumberPagination


class PaginacaoPadrao(PageNumberPagination):
    """10 itens por página, no formato {count, next, previous, results} (RN15).

    Parâmetros: `pagina` (a partir de 1) e `tamanho` (até 50). Página inválida ou fora do
    intervalo responde 400 com a mensagem do campo, como os demais parâmetros inválidos.
    """

    page_size = 10
    page_query_param = "pagina"
    page_size_query_param = "tamanho"
    max_page_size = 50

    def paginate_queryset(self, queryset, request, view=None):
        try:
            return super().paginate_queryset(queryset, request, view)
        except NotFound as erro:
            raise ValidationError({"pagina": "Página inválida."}) from erro
