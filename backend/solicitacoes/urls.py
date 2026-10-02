"""Rotas (routes): liga cada URL a uma view. Não contém lógica."""

from django.urls import path

from . import views

urlpatterns = [
    path("solicitacoes/", views.SolicitacoesView.as_view(), name="solicitacoes"),
    path("solicitacoes/<int:pk>/", views.SolicitacaoView.as_view(), name="solicitacao"),
    path("solicitacoes/<int:pk>/status/", views.StatusView.as_view(), name="status"),
    path("categorias/", views.CategoriasView.as_view(), name="categorias"),
]
