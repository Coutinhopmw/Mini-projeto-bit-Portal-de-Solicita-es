"""Controllers (HTTP): lê a requisição, chama o service e devolve a resposta.

Não contém regra de negócio nem acesso direto ao banco.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import LoginSerializer, RenovacaoSerializer, UsuarioSerializer
from .throttles import LimiteDeLogin


class LoginView(APIView):
    """POST /api/auth/login/: usuário e senha -> token de acesso, de renovação e o usuário."""

    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [LimiteDeLogin]
    mensagem_limite = "Muitas tentativas de login. Aguarde 1 minuto e tente novamente."

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        usuario, tokens = services.autenticar(**serializer.validated_data)
        return Response({**tokens, "usuario": UsuarioSerializer(usuario).data})


class RenovacaoView(APIView):
    """POST /api/auth/refresh/: token de renovação -> novo token de acesso."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get_authenticate_header(self, request):
        # Sem classes de autenticação o DRF trocaria o 401 por 403; o cabeçalho mantém o 401.
        return 'Bearer realm="api"'

    def post(self, request):
        serializer = RenovacaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        acesso = services.renovar_acesso(serializer.validated_data["renovacao"])
        return Response({"acesso": acesso})


class LogoutView(APIView):
    """POST /api/auth/logout/: bloqueia o token de renovação do usuário logado."""

    def post(self, request):
        serializer = RenovacaoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.encerrar_sessao(request.user, serializer.validated_data["renovacao"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """GET /api/auth/me/: dados do usuário logado."""

    def get(self, request):
        return Response(UsuarioSerializer(request.user).data)
