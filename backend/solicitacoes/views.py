"""Controllers (HTTP): lê a requisição, chama o service e devolve a resposta.

Não contém regra de negócio nem acesso direto ao banco.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from nucleo.paginacao import PaginacaoPadrao

from . import services
from .permissions import EhAutor
from .serializers import (
    CategoriaSerializer,
    SolicitacaoDetalheSerializer,
    SolicitacaoEntradaSerializer,
    SolicitacaoListaSerializer,
)


def _detalhe(solicitacao, request):
    return SolicitacaoDetalheSerializer(solicitacao, context={"request": request}).data


class SolicitacoesView(APIView):
    """GET /api/solicitacoes/ (paginada) e POST /api/solicitacoes/ (cria)."""

    def get(self, request):
        paginador = PaginacaoPadrao()
        pagina = paginador.paginate_queryset(services.listar(request.user), request, view=self)
        return paginador.get_paginated_response(SolicitacaoListaSerializer(pagina, many=True).data)

    def post(self, request):
        entrada = SolicitacaoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        solicitacao = services.criar(request.user, **entrada.validated_data)
        return Response(_detalhe(solicitacao, request), status=status.HTTP_201_CREATED)


class SolicitacaoView(APIView):
    """GET, PUT e DELETE em /api/solicitacoes/{id}/.

    A ordem das verificações segue o PLN-01: 401 sem login, 404 se o usuário não enxerga a
    solicitação, 403 se não é o autor, 400 se os dados são inválidos e 409 se o estado proíbe.
    """

    def get_permissions(self):
        permissoes = [IsAuthenticated()]
        if self.request.method in ("PUT", "DELETE"):
            permissoes.append(EhAutor())
        return permissoes

    def get(self, request, pk):
        return Response(_detalhe(services.obter(request.user, pk), request))

    def put(self, request, pk):
        solicitacao = services.obter(request.user, pk)
        self.check_object_permissions(request, solicitacao)
        entrada = SolicitacaoEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)
        atualizada = services.editar(request.user, pk, **entrada.validated_data)
        return Response(_detalhe(atualizada, request))

    def delete(self, request, pk):
        solicitacao = services.obter(request.user, pk)
        self.check_object_permissions(request, solicitacao)
        services.excluir(request.user, pk)
        return Response(status=status.HTTP_204_NO_CONTENT)


class CategoriasView(APIView):
    """GET /api/categorias/: categorias ativas, para o formulário e os filtros (RN16)."""

    def get(self, request):
        return Response(CategoriaSerializer(services.listar_categorias(), many=True).data)
