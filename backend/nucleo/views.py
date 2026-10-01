from rest_framework.decorators import api_view
from rest_framework.response import Response


@api_view(["GET"])
def ola(request):
    return Response({"mensagem": "Olá, mundo! API do Portal de Solicitações no ar."})
