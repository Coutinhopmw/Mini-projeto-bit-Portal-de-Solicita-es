import logging

import pytest
from django.core.management import call_command
from django.db import DatabaseError
from django.test import RequestFactory
from rest_framework.test import APIClient

from nucleo.views import erro_interno, pagina_nao_encontrada
from solicitacoes.models import Categoria, Solicitacao


@pytest.mark.django_db
def test_saude_confirma_a_conexao_com_o_banco():
    resposta = APIClient().get("/api/saude/")

    assert resposta.status_code == 200
    assert resposta.json() == {"status": "ok", "banco": "conectado"}


def test_saude_devolve_503_quando_o_banco_cai(monkeypatch):
    def falhar(*args, **kwargs):
        raise DatabaseError("conexão recusada em 10.0.0.5:5432")

    monkeypatch.setattr("nucleo.views.connection.cursor", falhar)

    resposta = APIClient().get("/api/saude/")

    assert resposta.status_code == 503
    assert resposta.json() == {
        "erro": "BANCO_INDISPONIVEL",
        "mensagem": "Não foi possível conectar ao banco de dados.",
    }
    assert "10.0.0.5" not in resposta.content.decode()


def test_middleware_registra_cada_requisicao(caplog):
    with caplog.at_level(logging.INFO, logger="portal.requisicoes"):
        APIClient().get("/api/ola/")

    assert any("GET /api/ola/ -> 200" in registro.getMessage() for registro in caplog.records)


@pytest.mark.django_db
def test_preparar_banco_aplica_migrations_e_seed():
    call_command("preparar_banco", verbosity=0)

    assert Categoria.objects.count() == 5
    assert Solicitacao.objects.count() == 12


@pytest.mark.django_db
def test_preparar_banco_sem_seed_nao_carrega_dados():
    call_command("preparar_banco", "--sem-seed", verbosity=0)

    assert Categoria.objects.count() == 0


def test_handlers_do_django_seguem_o_formato_padrao_sem_escapar_acentos():
    resposta_404 = pagina_nao_encontrada(RequestFactory().get("/qualquer"))
    resposta_500 = erro_interno(RequestFactory().get("/qualquer"))

    assert resposta_404.status_code == 404
    assert "Rota não encontrada." in resposta_404.content.decode()
    assert resposta_500.status_code == 500
    assert "Erro inesperado." in resposta_500.content.decode()
