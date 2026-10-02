import pytest
from django.http import Http404
from rest_framework import exceptions, serializers
from rest_framework.test import APIClient

from nucleo.erros import MENSAGEM_ERRO_INTERNO, tratar_excecao
from nucleo.excecoes import ErroDeNegocio
from nucleo.validacao import CampoTexto


class SolicitacaoDeTeste(serializers.Serializer):
    titulo = CampoTexto(rotulo="título", minimo=3, maximo=150)
    descricao = CampoTexto(rotulo="descrição", minimo=10, maximo=2000, artigo="a")


def corpo_do_erro(excecao):
    return tratar_excecao(excecao, {}).data


@pytest.mark.parametrize("metodo", ["get", "post", "put", "patch", "delete"])
def test_rota_inexistente_devolve_404_no_formato_padrao(metodo):
    resposta = getattr(APIClient(), metodo)("/api/nao-existe/")

    assert resposta.status_code == 404
    assert resposta.json() == {"erro": "NAO_ENCONTRADO", "mensagem": "Rota não encontrada."}


def test_rota_inexistente_aninhada_tambem_devolve_404():
    resposta = APIClient().get("/api/solicitacoes/999/algo/")

    assert resposta.status_code == 404
    assert resposta.json()["erro"] == "NAO_ENCONTRADO"


def test_metodo_nao_permitido_segue_o_formato_padrao():
    resposta = APIClient().post("/api/ola/")

    assert resposta.status_code == 405
    assert resposta.json()["erro"] == "METODO_NAO_PERMITIDO"


def test_validacao_devolve_detalhes_por_campo():
    serializer = SolicitacaoDeTeste(data={"titulo": "ab", "descricao": ""})
    with pytest.raises(exceptions.ValidationError) as excecao:
        serializer.is_valid(raise_exception=True)

    resposta = tratar_excecao(excecao.value, {})

    assert resposta.status_code == 400
    assert resposta.data == {
        "erro": "VALIDACAO",
        "mensagem": "Dados inválidos",
        "detalhes": {
            "titulo": "O título deve ter entre 3 e 150 caracteres.",
            "descricao": "Informe a descrição.",
        },
    }


def test_erro_geral_de_validacao_vira_campo_geral():
    corpo = corpo_do_erro(exceptions.ValidationError("Algo não bate."))

    assert corpo["detalhes"] == {"geral": "Algo não bate."}


def test_erro_de_negocio_usa_codigo_e_status_proprios():
    class TransicaoInvalida(ErroDeNegocio):
        status_code = 409
        erro = "TRANSICAO_INVALIDA"

    resposta = tratar_excecao(
        TransicaoInvalida("Não é possível alterar o status de ABERTO para CONCLUIDO."), {}
    )

    assert resposta.status_code == 409
    assert resposta.data == {
        "erro": "TRANSICAO_INVALIDA",
        "mensagem": "Não é possível alterar o status de ABERTO para CONCLUIDO.",
    }


@pytest.mark.parametrize(
    ("excecao", "status", "codigo"),
    [
        (exceptions.ParseError(), 400, "REQUISICAO_INVALIDA"),
        (exceptions.NotAuthenticated(), 401, "NAO_AUTENTICADO"),
        (exceptions.AuthenticationFailed(), 401, "NAO_AUTENTICADO"),
        (exceptions.PermissionDenied(), 403, "SEM_PERMISSAO"),
        (exceptions.NotFound(), 404, "NAO_ENCONTRADO"),
        (exceptions.MethodNotAllowed("PUT"), 405, "METODO_NAO_PERMITIDO"),
        (Http404(), 404, "NAO_ENCONTRADO"),
        (exceptions.Throttled(), 429, "MUITAS_TENTATIVAS"),
        (exceptions.UnsupportedMediaType("text/xml"), 415, "FORMATO_NAO_SUPORTADO"),
    ],
)
def test_excecoes_do_drf_viram_o_formato_padrao(excecao, status, codigo):
    resposta = tratar_excecao(excecao, {})

    assert resposta.status_code == status
    assert resposta.data["erro"] == codigo
    assert set(resposta.data) == {"erro", "mensagem"}


def test_excecao_inesperada_nao_vaza_detalhes(caplog):
    with caplog.at_level("ERROR", logger="portal.erros"):
        resposta = tratar_excecao(RuntimeError("senha=segredo123 em /etc/arquivo"), {})

    assert resposta.status_code == 500
    assert resposta.data == {"erro": "ERRO_INTERNO", "mensagem": MENSAGEM_ERRO_INTERNO}
    assert "segredo123" not in str(resposta.data)
    # O detalhe técnico fica só no log, com a exceção original anexada.
    registros = [registro for registro in caplog.records if registro.exc_info]
    assert len(registros) == 1
    assert registros[0].exc_info[0] is RuntimeError


def test_campo_texto_remove_espacos_das_pontas():
    serializer = SolicitacaoDeTeste(
        data={"titulo": "  Notebook  ", "descricao": "  Não liga depois da atualização.  "}
    )

    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["titulo"] == "Notebook"
    assert serializer.validated_data["descricao"] == "Não liga depois da atualização."


def test_campo_texto_rejeita_somente_espacos():
    serializer = SolicitacaoDeTeste(data={"titulo": "     ", "descricao": "x" * 20})

    assert not serializer.is_valid()
    assert str(serializer.errors["titulo"][0]) == "Informe o título."


def test_campo_texto_rejeita_texto_acima_do_limite():
    serializer = SolicitacaoDeTeste(data={"titulo": "t" * 151, "descricao": "d" * 20})

    assert not serializer.is_valid()
    assert str(serializer.errors["titulo"][0]) == "O título deve ter entre 3 e 150 caracteres."
