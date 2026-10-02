from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from solicitacoes import repositories, services
from solicitacoes.excecoes import TransicaoInvalida
from solicitacoes.models import Categoria, HistoricoStatus, Solicitacao, Status
from usuarios.models import Papel, Usuario

pytestmark = pytest.mark.django_db


def criar_usuario(login, papel=Papel.SOLICITANTE):
    return Usuario.objects.create_user(login, "Senha@123", nome=login.capitalize(), papel=papel)


def cliente_de(usuario):
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(usuario)}")
    return cliente


def alterar(cliente, solicitacao, corpo):
    return cliente.patch(f"/api/solicitacoes/{solicitacao.pk}/status/", corpo, format="json")


@pytest.fixture
def maria():
    return criar_usuario("maria")


@pytest.fixture
def joao():
    return criar_usuario("joao")


@pytest.fixture
def ana():
    return criar_usuario("ana", Papel.ATENDENTE)


@pytest.fixture
def ti():
    return Categoria.objects.create(nome="TI")


def abrir(solicitante, categoria, status=Status.ABERTO):
    solicitacao = Solicitacao.objects.create(
        titulo="Título da demanda",
        descricao="Descrição com mais de dez caracteres.",
        categoria=categoria,
        solicitante=solicitante,
        status=status,
    )
    HistoricoStatus.objects.create(
        solicitacao=solicitacao, status_novo=Status.ABERTO, alterado_por=solicitante
    )
    return solicitacao


def historico(solicitacao):
    return list(
        solicitacao.historico.order_by("alterado_em", "id").values_list(
            "status_anterior", "status_novo", "alterado_por__login"
        )
    )


class TestTransicoesValidas:
    def test_ciclo_completo_aberto_em_atendimento_concluido(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)
        atendente = cliente_de(ana)

        primeira = alterar(atendente, solicitacao, {"status": "EM_ATENDIMENTO"})
        segunda = alterar(atendente, solicitacao, {"status": "CONCLUIDO"})

        assert primeira.status_code == 200
        assert primeira.json()["status"] == "EM_ATENDIMENTO"
        assert segunda.status_code == 200
        assert segunda.json()["status"] == "CONCLUIDO"
        solicitacao.refresh_from_db()
        assert solicitacao.status == Status.CONCLUIDO

    def test_cada_mudanca_grava_uma_linha_no_historico(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)
        atendente = cliente_de(ana)

        alterar(atendente, solicitacao, {"status": "EM_ATENDIMENTO"})
        alterar(atendente, solicitacao, {"status": "CONCLUIDO"})

        assert historico(solicitacao) == [
            (None, "ABERTO", "maria"),
            ("ABERTO", "EM_ATENDIMENTO", "ana"),
            ("EM_ATENDIMENTO", "CONCLUIDO", "ana"),
        ]

    def test_resposta_traz_o_historico_atualizado(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)

        corpo = alterar(cliente_de(ana), solicitacao, {"status": "EM_ATENDIMENTO"}).json()

        ultimo = corpo["historico"][-1]
        assert ultimo["status_anterior"] == "ABERTO"
        assert ultimo["status_novo"] == "EM_ATENDIMENTO"
        assert ultimo["alterado_por"] == {"id": ana.pk, "nome": "Ana"}
        assert len(corpo["historico"]) == 2

    def test_atualiza_atualizado_em_e_preserva_a_data_de_criacao(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)
        criada_em, antes = solicitacao.criado_em, solicitacao.atualizado_em

        alterar(cliente_de(ana), solicitacao, {"status": "EM_ATENDIMENTO"})

        solicitacao.refresh_from_db()
        assert solicitacao.atualizado_em > antes
        assert solicitacao.criado_em == criada_em

    def test_atendente_altera_o_status_da_propria_solicitacao(self, ana, ti):
        solicitacao = abrir(ana, ti)

        resposta = alterar(cliente_de(ana), solicitacao, {"status": "EM_ATENDIMENTO"})

        assert resposta.status_code == 200
        assert historico(solicitacao)[-1] == ("ABERTO", "EM_ATENDIMENTO", "ana")

    def test_so_a_solicitacao_indicada_muda(self, maria, ana, ti):
        alvo, outra = abrir(maria, ti), abrir(maria, ti)

        alterar(cliente_de(ana), alvo, {"status": "EM_ATENDIMENTO"})

        outra.refresh_from_db()
        assert outra.status == Status.ABERTO
        assert outra.historico.count() == 1

    def test_campos_extras_no_corpo_sao_ignorados(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)

        alterar(
            cliente_de(ana),
            solicitacao,
            {"status": "EM_ATENDIMENTO", "titulo": "Hack", "solicitante": ana.pk},
        )

        solicitacao.refresh_from_db()
        assert solicitacao.titulo == "Título da demanda"
        assert solicitacao.solicitante == maria


class TestTransicoesInvalidas:
    @pytest.mark.parametrize(
        ("atual", "novo"),
        [
            (Status.ABERTO, "CONCLUIDO"),
            (Status.ABERTO, "ABERTO"),
            (Status.EM_ATENDIMENTO, "ABERTO"),
            (Status.EM_ATENDIMENTO, "EM_ATENDIMENTO"),
            (Status.CONCLUIDO, "ABERTO"),
            (Status.CONCLUIDO, "EM_ATENDIMENTO"),
            (Status.CONCLUIDO, "CONCLUIDO"),
        ],
    )
    def test_fora_do_ciclo_devolve_409_sem_alterar_nada(self, maria, ana, ti, atual, novo):
        solicitacao = abrir(maria, ti, status=atual)
        linhas_antes = solicitacao.historico.count()
        atualizado_antes = Solicitacao.objects.get(pk=solicitacao.pk).atualizado_em

        resposta = alterar(cliente_de(ana), solicitacao, {"status": novo})

        assert resposta.status_code == 409
        assert resposta.json()["erro"] == "TRANSICAO_INVALIDA"
        solicitacao.refresh_from_db()
        assert solicitacao.status == atual
        assert solicitacao.historico.count() == linhas_antes
        assert solicitacao.atualizado_em == atualizado_antes

    def test_mensagem_cita_os_dois_status(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)

        resposta = alterar(cliente_de(ana), solicitacao, {"status": "CONCLUIDO"})

        assert resposta.json() == {
            "erro": "TRANSICAO_INVALIDA",
            "mensagem": "Não é possível alterar o status de Aberto para Concluído.",
        }

    def test_concluido_e_estado_final(self, maria, ana, ti):
        solicitacao = abrir(maria, ti, status=Status.CONCLUIDO)
        atendente = cliente_de(ana)

        for novo in ("ABERTO", "EM_ATENDIMENTO", "CONCLUIDO"):
            assert alterar(atendente, solicitacao, {"status": novo}).status_code == 409

    def test_clique_duplo_nao_gera_duas_transicoes(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)
        atendente = cliente_de(ana)

        primeira = alterar(atendente, solicitacao, {"status": "EM_ATENDIMENTO"})
        segunda = alterar(atendente, solicitacao, {"status": "EM_ATENDIMENTO"})

        assert (primeira.status_code, segunda.status_code) == (200, 409)
        assert solicitacao.historico.count() == 2


class TestPerfilEVisibilidade:
    def test_solicitante_recebe_403_mesmo_na_propria_solicitacao(self, maria, ti):
        solicitacao = abrir(maria, ti)

        resposta = alterar(cliente_de(maria), solicitacao, {"status": "EM_ATENDIMENTO"})

        assert resposta.status_code == 403
        assert resposta.json() == {
            "erro": "SEM_PERMISSAO",
            "mensagem": "Você não tem permissão para realizar esta ação.",
        }
        solicitacao.refresh_from_db()
        assert solicitacao.status == Status.ABERTO
        assert solicitacao.historico.count() == 1

    def test_solicitante_nao_conclui_a_propria_demanda(self, maria, ti):
        solicitacao = abrir(maria, ti, status=Status.EM_ATENDIMENTO)

        resposta = alterar(cliente_de(maria), solicitacao, {"status": "CONCLUIDO"})

        assert resposta.status_code == 403
        solicitacao.refresh_from_db()
        assert solicitacao.status == Status.EM_ATENDIMENTO

    def test_solicitacao_de_outra_pessoa_devolve_404_e_nao_403(self, maria, joao, ti):
        solicitacao = abrir(maria, ti)

        resposta = alterar(cliente_de(joao), solicitacao, {"status": "EM_ATENDIMENTO"})

        assert resposta.status_code == 404
        assert resposta.json()["mensagem"] == "Solicitação não encontrada."

    def test_inexistente_devolve_404(self, ana):
        resposta = cliente_de(ana).patch(
            "/api/solicitacoes/99999/status/", {"status": "EM_ATENDIMENTO"}, format="json"
        )

        assert resposta.status_code == 404

    def test_sem_login_devolve_401(self, maria, ti):
        solicitacao = abrir(maria, ti)

        resposta = alterar(APIClient(), solicitacao, {"status": "EM_ATENDIMENTO"})

        assert resposta.status_code == 401
        assert resposta.json()["erro"] == "NAO_AUTENTICADO"


class TestValidacao:
    @pytest.mark.parametrize(
        "corpo",
        [{}, {"status": ""}, {"status": None}, {"status": "FINALIZADO"}, {"status": "aberto"}]
        + [{"status": 1}, {"status": ["CONCLUIDO"]}],
        ids=["ausente", "vazio", "nulo", "inexistente", "minusculas", "numero", "lista"],
    )
    def test_status_invalido_devolve_400(self, maria, ana, ti, corpo):
        solicitacao = abrir(maria, ti)

        resposta = alterar(cliente_de(ana), solicitacao, corpo)

        assert resposta.status_code == 400
        assert resposta.json() == {
            "erro": "VALIDACAO",
            "mensagem": "Dados inválidos",
            "detalhes": {"status": "Status inválido."},
        }

    def test_corpo_que_nao_e_json(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(ana).generic(
            "PATCH",
            f"/api/solicitacoes/{solicitacao.pk}/status/",
            data="{quebrado",
            content_type="application/json",
        )

        assert resposta.status_code == 400
        assert resposta.json()["erro"] == "REQUISICAO_INVALIDA"

    def test_ordem_404_403_400_409(self, maria, joao, ana, ti):
        concluida = abrir(maria, ti, status=Status.CONCLUIDO)
        invalido = {"status": "FINALIZADO"}

        # 404: outro Solicitante nem enxerga a solicitação.
        assert alterar(cliente_de(joao), concluida, invalido).status_code == 404
        # 403: o autor enxerga, mas não é Atendente, mesmo com corpo inválido.
        assert alterar(cliente_de(maria), concluida, invalido).status_code == 403
        # 400: o Atendente com status inexistente, antes do 409 da transição.
        assert alterar(cliente_de(ana), concluida, invalido).status_code == 400
        # 409: status existente, mas fora do ciclo.
        assert alterar(cliente_de(ana), concluida, {"status": "ABERTO"}).status_code == 409

    @pytest.mark.parametrize("metodo", ["get", "put", "post", "delete"])
    def test_so_patch_e_aceito(self, maria, ana, ti, metodo):
        solicitacao = abrir(maria, ti)

        resposta = getattr(cliente_de(ana), metodo)(f"/api/solicitacoes/{solicitacao.pk}/status/")

        assert resposta.status_code == 405


class TestAtomicidade:
    def test_falha_no_historico_desfaz_a_mudanca_de_status(self, maria, ana, ti, monkeypatch):
        solicitacao = abrir(maria, ti)

        def falhar(*args, **kwargs):
            raise RuntimeError("falha ao gravar o histórico")

        monkeypatch.setattr(repositories, "registrar_historico", falhar)

        with pytest.raises(RuntimeError):
            services.alterar_status(ana, solicitacao.pk, Status.EM_ATENDIMENTO)

        solicitacao.refresh_from_db()
        assert solicitacao.status == Status.ABERTO
        assert solicitacao.historico.count() == 1

    def test_status_alterado_por_fora_e_relido_com_a_linha_travada(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)
        # Outro atendente já concluiu a demanda depois da leitura inicial da view.
        Solicitacao.objects.filter(pk=solicitacao.pk).update(status=Status.CONCLUIDO)

        with pytest.raises(TransicaoInvalida):
            services.alterar_status(ana, solicitacao.pk, Status.EM_ATENDIMENTO)

    def test_erro_de_transicao_nao_deixa_historico_pela_metade(self, maria, ana, ti):
        solicitacao = abrir(maria, ti, status=Status.EM_ATENDIMENTO)

        with pytest.raises(TransicaoInvalida):
            services.alterar_status(ana, solicitacao.pk, Status.ABERTO)

        assert solicitacao.historico.count() == 1


class TestIndicadoresNoDetalhe:
    def get(self, usuario, solicitacao):
        return cliente_de(usuario).get(f"/api/solicitacoes/{solicitacao.pk}/").json()

    def test_atendente_recebe_a_proxima_transicao(self, maria, ana, ti):
        aberta = abrir(maria, ti)
        em_atendimento = abrir(maria, ti, status=Status.EM_ATENDIMENTO)

        a, b = self.get(ana, aberta), self.get(ana, em_atendimento)

        assert (a["pode_alterar_status"], a["proximo_status"]) == (True, "EM_ATENDIMENTO")
        assert (b["pode_alterar_status"], b["proximo_status"]) == (True, "CONCLUIDO")

    def test_concluida_nao_tem_proxima_transicao(self, maria, ana, ti):
        concluida = abrir(maria, ti, status=Status.CONCLUIDO)

        corpo = self.get(ana, concluida)

        assert (corpo["pode_alterar_status"], corpo["proximo_status"]) == (False, None)

    def test_solicitante_nao_recebe_acao_de_status(self, maria, ti):
        solicitacao = abrir(maria, ti)

        corpo = self.get(maria, solicitacao)

        assert (corpo["pode_alterar_status"], corpo["proximo_status"]) == (False, None)

    def test_depois_de_alterar_o_detalhe_reflete_o_novo_estado(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)
        alterar(cliente_de(ana), solicitacao, {"status": "EM_ATENDIMENTO"})

        # A autora não pode mais editar nem excluir: a solicitação saiu do status Aberto.
        corpo = self.get(maria, solicitacao)

        assert corpo["status"] == "EM_ATENDIMENTO"
        assert (corpo["pode_editar"], corpo["pode_excluir"]) == (False, False)

    def test_status_alterado_bloqueia_a_edicao_e_a_exclusao_pela_api(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)
        alterar(cliente_de(ana), solicitacao, {"status": "EM_ATENDIMENTO"})
        autora = cliente_de(maria)
        corpo = {
            "titulo": "Novo título",
            "descricao": "Nova descrição bem detalhada.",
            "categoria": ti.pk,
        }

        edicao = autora.put(f"/api/solicitacoes/{solicitacao.pk}/", corpo, format="json")
        exclusao = autora.delete(f"/api/solicitacoes/{solicitacao.pk}/")

        assert (edicao.status_code, exclusao.status_code) == (409, 409)

    def test_data_de_alteracao_fica_na_ordem_cronologica(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)
        atendente = cliente_de(ana)
        alterar(atendente, solicitacao, {"status": "EM_ATENDIMENTO"})
        alterar(atendente, solicitacao, {"status": "CONCLUIDO"})

        datas = [h["alterado_em"] for h in self.get(ana, solicitacao)["historico"]]

        assert datas == sorted(datas)
        assert abs(timezone.now() - solicitacao.historico.latest("alterado_em").alterado_em) < (
            timedelta(seconds=5)
        )
