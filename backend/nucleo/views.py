from django.db import DatabaseError, connection
from django.http import JsonResponse
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .erros import MENSAGEM_ERRO_INTERNO, montar_corpo
from .excecoes import BancoIndisponivel, NaoEncontrado


def resposta_json(corpo, status):
    """JsonResponse sem escapar acentos, igual ao restante da API."""
    return JsonResponse(corpo, status=status, json_dumps_params={"ensure_ascii": False})


METODOS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def ola(request):
    return Response({"mensagem": "Olá, mundo! API do Portal de Solicitações no ar."})


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def saude(request):
    """Confirma que a API está no ar e conectada ao banco."""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except DatabaseError as erro:
        raise BancoIndisponivel() from erro
    return Response({"status": "ok", "banco": "conectado"})


@api_view(METODOS)
@authentication_classes([])
@permission_classes([AllowAny])
def rota_inexistente(request, *args, **kwargs):
    """Fim da lista de rotas de /api/: qualquer caminho desconhecido cai aqui."""
    raise NaoEncontrado("Rota não encontrada.")


def pagina_nao_encontrada(request, exception=None):
    """handler404 do Django, para caminhos fora de /api/ (usado com DEBUG desligado)."""
    return resposta_json(montar_corpo("NAO_ENCONTRADO", "Rota não encontrada."), 404)


def erro_interno(request):
    """handler500 do Django: resposta no formato padrão, sem detalhes técnicos."""
    return resposta_json(montar_corpo("ERRO_INTERNO", MENSAGEM_ERRO_INTERNO), 500)
