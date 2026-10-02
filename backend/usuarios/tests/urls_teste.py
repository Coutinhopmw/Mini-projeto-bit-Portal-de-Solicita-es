"""Rotas só dos testes: exercitam as permissões antes de existirem as rotas reais."""

from django.urls import include, path
from rest_framework.response import Response
from rest_framework.views import APIView

from usuarios.permissions import EhAtendente


class SoParaAtendente(APIView):
    permission_classes = [EhAtendente]

    def get(self, request):
        return Response({"ok": True})


urlpatterns = [
    path("api/so-atendente/", SoParaAtendente.as_view()),
    path("", include("config.urls")),
]
