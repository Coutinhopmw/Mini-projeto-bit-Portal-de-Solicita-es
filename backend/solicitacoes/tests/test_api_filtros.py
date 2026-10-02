from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from solicitacoes.models import Categoria, HistoricoStatus, Solicitacao, Status
from usuarios.models import Papel, Usuario

pytestmark = pytest.mark.django_db

URL = "/api/solicitacoes/"
SP = ZoneInfo("America/Sao_Paulo")


def criar_usuario(login, papel=Papel.SOLICITANTE):
    return Usuario.objects.create_user(login, "Senha@123", nome=login.capitalize(), papel=papel)


def cliente_de(usuario):
    cliente = APIClient()
    cliente.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(usuario)}")
    return cliente


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


@pytest.fixture
def rh():
    return Categoria.objects.create(nome="RH")


def abrir(solicitante, categoria, titulo="Título da demanda", status=Status.ABERTO, criado_em=None):
    solicitacao = Solicitacao.objects.create(
        titulo=titulo,
        descricao="Descrição com mais de dez caracteres.",
        categoria=categoria,
        solicitante=solicitante,
        status=status,
    )
    if criado_em is not None:
        Solicitacao.objects.filter(pk=solicitacao.pk).update(criado_em=criado_em)
    HistoricoStatus.objects.create(
        solicitacao=solicitacao, status_novo=Status.ABERTO, alterado_por=solicitante
    )
    return solicitacao


def listar(cliente, **parametros):
    return cliente.get(URL, parametros)


def titulos(resposta):
    return [item["titulo"] for item in resposta.json()["results"]]


class TestFiltroPorStatus:
    def test_devolve_so_o_status_pedido(self, maria, ti):
        abrir(maria, ti, "Aberta", Status.ABERTO)
        abrir(maria, ti, "Atendendo", Status.EM_ATENDIMENTO)
        abrir(maria, ti, "Feita", Status.CONCLUIDO)

        for status, esperado in [
            ("ABERTO", ["Aberta"]),
            ("EM_ATENDIMENTO", ["Atendendo"]),
            ("CONCLUIDO", ["Feita"]),
        ]:
            assert titulos(listar(cliente_de(maria), status=status)) == esperado

    @pytest.mark.parametrize("valor", ["FINALIZADO", "aberto", "1", "ABERTO "])
    def test_status_inexistente_devolve_400(self, maria, ti, valor):
        abrir(maria, ti)

        resposta = listar(cliente_de(maria), status=valor)

        assert resposta.status_code == 400
        assert resposta.json() == {
            "erro": "VALIDACAO",
            "mensagem": "Dados inválidos",
            "detalhes": {"status": "Status inválido."},
        }

    def test_status_vazio_e_ignorado(self, maria, ti):
        abrir(maria, ti, "Aberta")
        abrir(maria, ti, "Feita", Status.CONCLUIDO)

        assert len(titulos(listar(cliente_de(maria), status=""))) == 2


class TestFiltroPorCategoria:
    def test_devolve_so_a_categoria_pedida(self, maria, ti, rh):
        abrir(maria, ti, "De TI")
        abrir(maria, rh, "De RH")

        assert titulos(listar(cliente_de(maria), categoria=rh.pk)) == ["De RH"]

    @pytest.mark.parametrize("valor", ["abc", "99999", "-1", "1.5"])
    def test_categoria_invalida_devolve_400(self, maria, ti, valor):
        resposta = listar(cliente_de(maria), categoria=valor)

        assert resposta.status_code == 400
        assert resposta.json()["detalhes"] == {"categoria": "Categoria inválida."}

    def test_categoria_inativa_ainda_filtra_solicitacoes_antigas(self, maria, ti):
        abrir(maria, ti, "Antiga")
        ti.ativa = False
        ti.save()

        assert titulos(listar(cliente_de(maria), categoria=ti.pk)) == ["Antiga"]


class TestFiltroPorTitulo:
    def test_busca_parcial(self, maria, ti):
        abrir(maria, ti, "Notebook não liga")
        abrir(maria, ti, "Acesso à VPN")

        assert titulos(listar(cliente_de(maria), q="book")) == ["Notebook não liga"]

    def test_nao_diferencia_maiusculas_de_minusculas(self, maria, ti):
        abrir(maria, ti, "Notebook não liga")

        for busca in ("NOTEBOOK", "notebook", "NoTeBoOk"):
            assert titulos(listar(cliente_de(maria), q=busca)) == ["Notebook não liga"]

    def test_nao_busca_na_descricao(self, maria, ti):
        abrir(maria, ti, "Outro assunto")

        assert titulos(listar(cliente_de(maria), q="Descrição")) == []

    def test_espacos_das_pontas_sao_ignorados(self, maria, ti):
        abrir(maria, ti, "Notebook não liga")

        assert titulos(listar(cliente_de(maria), q="   book   ")) == ["Notebook não liga"]

    def test_busca_vazia_ou_so_espacos_nao_filtra(self, maria, ti):
        abrir(maria, ti, "Primeiro chamado")
        abrir(maria, ti, "Segundo chamado")

        assert len(titulos(listar(cliente_de(maria), q=""))) == 2
        assert len(titulos(listar(cliente_de(maria), q="   "))) == 2

    def test_curingas_do_sql_sao_tratados_como_texto(self, maria, ti):
        abrir(maria, ti, "Desconto de 50% no plano")
        abrir(maria, ti, "Desconto de 5 no plano")
        abrir(maria, ti, "Chave_secreta")
        abrir(maria, ti, "ChaveXsecreta")

        assert titulos(listar(cliente_de(maria), q="50%")) == ["Desconto de 50% no plano"]
        assert titulos(listar(cliente_de(maria), q="e_s")) == ["Chave_secreta"]
        assert listar(cliente_de(maria), q="%").json()["count"] == 1

    def test_aspas_e_caracteres_de_injecao_nao_quebram_a_consulta(self, maria, ti):
        abrir(maria, ti, "Título comum")

        resposta = listar(cliente_de(maria), q="'; DROP TABLE solicitacoes; --")

        assert resposta.status_code == 200
        assert resposta.json()["count"] == 0
        assert Solicitacao.objects.count() == 1

    def test_limite_de_100_caracteres(self, maria, ti):
        assert listar(cliente_de(maria), q="a" * 100).status_code == 200

        resposta = listar(cliente_de(maria), q="a" * 101)

        assert resposta.status_code == 400
        assert resposta.json()["detalhes"] == {"q": "A busca deve ter no máximo 100 caracteres."}

    def test_acentos_contam_na_busca(self, maria, ti):
        """Hoje a busca diferencia acentos (melhoria futura: extensão unaccent)."""
        abrir(maria, ti, "Solicitação de acesso")

        assert titulos(listar(cliente_de(maria), q="solicitação")) == ["Solicitação de acesso"]
        assert titulos(listar(cliente_de(maria), q="solicitacao")) == []


class TestFiltroPorPeriodo:
    def abrir_em(self, usuario, categoria, titulo, momento):
        return abrir(usuario, categoria, titulo, criado_em=momento)

    def test_extremos_inclusos_com_o_horario_de_brasilia(self, maria, ti):
        self.abrir_em(maria, ti, "Fim do dia 30", datetime(2026, 9, 30, 23, 59, 59, tzinfo=SP))
        self.abrir_em(maria, ti, "Inicio do dia 01", datetime(2026, 10, 1, 0, 0, 0, tzinfo=SP))
        self.abrir_em(maria, ti, "Fim do dia 01", datetime(2026, 10, 1, 23, 59, 59, tzinfo=SP))
        self.abrir_em(maria, ti, "Inicio do dia 02", datetime(2026, 10, 2, 0, 0, 0, tzinfo=SP))
        cliente = cliente_de(maria)

        assert sorted(titulos(listar(cliente, de="2026-10-01", ate="2026-10-01"))) == [
            "Fim do dia 01",
            "Inicio do dia 01",
        ]
        assert sorted(titulos(listar(cliente, ate="2026-09-30"))) == ["Fim do dia 30"]
        assert sorted(titulos(listar(cliente, de="2026-10-02"))) == ["Inicio do dia 02"]

    def test_data_final_inclui_o_proprio_dia_ate_o_ultimo_segundo(self, maria, ti):
        self.abrir_em(
            maria, ti, "Último instante", datetime(2026, 10, 1, 23, 59, 59, 999999, tzinfo=SP)
        )

        assert titulos(listar(cliente_de(maria), ate="2026-10-01")) == ["Último instante"]
        assert titulos(listar(cliente_de(maria), ate="2026-09-30")) == []

    def test_o_dia_e_contado_no_fuso_de_sao_paulo_e_nao_em_utc(self, maria, ti):
        # 02:30 UTC de 01/10 ainda é 23:30 de 30/09 em São Paulo.
        self.abrir_em(maria, ti, "Noite de Brasília", datetime(2026, 10, 1, 2, 30, tzinfo=UTC))
        # 03:00 UTC de 01/10 já é 00:00 de 01/10 em São Paulo.
        self.abrir_em(maria, ti, "Meia-noite", datetime(2026, 10, 1, 3, 0, tzinfo=UTC))
        cliente = cliente_de(maria)

        assert titulos(listar(cliente, de="2026-09-30", ate="2026-09-30")) == ["Noite de Brasília"]
        assert titulos(listar(cliente, de="2026-10-01", ate="2026-10-01")) == ["Meia-noite"]

    def test_so_data_inicial(self, maria, ti):
        self.abrir_em(maria, ti, "Antes", datetime(2026, 9, 1, 12, tzinfo=SP))
        self.abrir_em(maria, ti, "Depois", datetime(2026, 9, 20, 12, tzinfo=SP))

        assert titulos(listar(cliente_de(maria), de="2026-09-10")) == ["Depois"]

    def test_intervalo_sem_resultados(self, maria, ti):
        abrir(maria, ti)

        resposta = listar(cliente_de(maria), de="2001-01-01", ate="2001-01-31")

        assert resposta.status_code == 200
        assert resposta.json()["count"] == 0

    def test_mesmo_dia_nas_duas_pontas(self, maria, ti):
        self.abrir_em(maria, ti, "Meio-dia", datetime(2026, 10, 1, 12, tzinfo=SP))

        assert titulos(listar(cliente_de(maria), de="2026-10-01", ate="2026-10-01")) == ["Meio-dia"]

    def test_data_inicial_maior_que_a_final(self, maria):
        resposta = listar(cliente_de(maria), de="2026-10-02", ate="2026-10-01")

        assert resposta.status_code == 400
        assert resposta.json()["detalhes"] == {
            "de": "A data inicial não pode ser maior que a data final."
        }

    @pytest.mark.parametrize(
        "valor", ["01/10/2026", "2026-13-01", "2026-02-30", "abc", "2026-10", "20261001", "1"]
    )
    @pytest.mark.parametrize("campo", ["de", "ate"])
    def test_formato_de_data_invalido(self, maria, campo, valor):
        resposta = listar(cliente_de(maria), **{campo: valor})

        assert resposta.status_code == 400
        assert resposta.json()["detalhes"] == {campo: "Data inválida. Use o formato AAAA-MM-DD."}


class TestFiltrosCombinados:
    def test_todos_precisam_ser_atendidos(self, maria, ti, rh):
        momento = datetime(2026, 10, 1, 12, tzinfo=SP)
        abrir(maria, ti, "Notebook com defeito", Status.ABERTO, momento)
        abrir(maria, rh, "Notebook de RH", Status.ABERTO, momento)
        abrir(maria, ti, "Notebook atendido", Status.EM_ATENDIMENTO, momento)
        abrir(maria, ti, "Notebook antigo", Status.ABERTO, datetime(2026, 8, 1, tzinfo=SP))
        abrir(maria, ti, "Impressora", Status.ABERTO, momento)

        resposta = listar(
            cliente_de(maria),
            status="ABERTO",
            categoria=ti.pk,
            de="2026-09-01",
            ate="2026-10-31",
            q="note",
        )

        assert titulos(resposta) == ["Notebook com defeito"]

    def test_varios_erros_sao_devolvidos_juntos(self, maria):
        resposta = listar(cliente_de(maria), status="x", categoria="y", de="z", q="a" * 101)

        assert resposta.status_code == 400
        assert set(resposta.json()["detalhes"]) == {"status", "categoria", "de", "q"}

    def test_parametro_invalido_nao_vira_filtro_silencioso(self, maria, ti):
        abrir(maria, ti)

        assert listar(cliente_de(maria), status="INEXISTENTE").status_code == 400

    def test_parametros_desconhecidos_sao_ignorados(self, maria, ti):
        abrir(maria, ti, "Uma")

        resposta = listar(cliente_de(maria), banana="1", ordem="titulo")

        assert resposta.status_code == 200
        assert titulos(resposta) == ["Uma"]

    def test_filtros_mantem_a_ordem_da_mais_recente_para_a_mais_antiga(self, maria, ti):
        agora = datetime(2026, 10, 1, 12, tzinfo=SP)
        abrir(maria, ti, "Antiga", criado_em=agora - timedelta(days=2))
        abrir(maria, ti, "Recente", criado_em=agora)
        abrir(maria, ti, "Meio", criado_em=agora - timedelta(days=1))

        assert titulos(listar(cliente_de(maria), de="2026-01-01")) == ["Recente", "Meio", "Antiga"]

    def test_filtros_com_paginacao(self, maria, ti, rh):
        for numero in range(12):
            abrir(maria, ti, f"Demanda {numero:02d}")
        abrir(maria, rh, "Fora do filtro")
        cliente = cliente_de(maria)

        primeira = listar(cliente, categoria=ti.pk).json()
        segunda = listar(cliente, categoria=ti.pk, pagina=2).json()

        assert primeira["count"] == segunda["count"] == 12
        assert len(primeira["results"]) == 10
        assert len(segunda["results"]) == 2
        assert f"categoria={ti.pk}" in primeira["next"]
        assert "Fora do filtro" not in [
            i["titulo"] for i in primeira["results"] + segunda["results"]
        ]

    def test_listagem_filtrada_nao_faz_uma_consulta_por_item(
        self, maria, ti, django_assert_max_num_queries
    ):
        for numero in range(8):
            abrir(maria, ti, f"Demanda {numero}")

        with django_assert_max_num_queries(8):
            listar(
                cliente_de(maria), status="ABERTO", categoria=ti.pk, q="Demanda", de="2020-01-01"
            )


class TestFiltrosRespeitamAVisibilidade:
    def test_solicitante_nao_alcanca_solicitacoes_de_outra_pessoa(self, maria, joao, ti):
        abrir(maria, ti, "Da Maria")
        abrir(joao, ti, "Do João")

        resposta = listar(cliente_de(maria), q="João")

        assert titulos(resposta) == []

    @pytest.mark.parametrize(
        "filtro", [{"status": "ABERTO"}, {"q": "Do"}, {"de": "2020-01-01"}, {"ate": "2099-01-01"}]
    )
    def test_nenhum_filtro_amplia_o_que_o_solicitante_ve(self, maria, joao, ti, filtro):
        abrir(maria, ti, "Da Maria")
        abrir(joao, ti, "Do João")

        resposta = listar(cliente_de(maria), **filtro)

        assert all(i["solicitante"]["nome"] == "Maria" for i in resposta.json()["results"])

    def test_atendente_filtra_sobre_todas(self, maria, joao, ana, ti):
        abrir(maria, ti, "Notebook da Maria")
        abrir(joao, ti, "Notebook do João")
        abrir(joao, ti, "Impressora do João")

        assert sorted(titulos(listar(cliente_de(ana), q="notebook"))) == [
            "Notebook da Maria",
            "Notebook do João",
        ]

    def test_sem_login_devolve_401_antes_de_validar_os_filtros(self):
        resposta = APIClient().get(URL, {"status": "invalido"})

        assert resposta.status_code == 401


class TestDashboard:
    def resumo(self, usuario):
        resposta = cliente_de(usuario).get("/api/dashboard/")
        assert resposta.status_code == 200
        return resposta.json()

    def test_zerado_quando_nao_ha_solicitacoes(self, maria):
        assert self.resumo(maria) == {
            "total": 0,
            "abertas": 0,
            "em_atendimento": 0,
            "concluidas": 0,
        }

    def test_conta_cada_status(self, maria, ti):
        abrir(maria, ti, status=Status.ABERTO)
        abrir(maria, ti, status=Status.ABERTO)
        abrir(maria, ti, status=Status.EM_ATENDIMENTO)
        for _ in range(3):
            abrir(maria, ti, status=Status.CONCLUIDO)

        assert self.resumo(maria) == {
            "total": 6,
            "abertas": 2,
            "em_atendimento": 1,
            "concluidas": 3,
        }

    def test_solicitante_ve_so_os_proprios_numeros(self, maria, joao, ti):
        abrir(maria, ti, status=Status.ABERTO)
        abrir(joao, ti, status=Status.ABERTO)
        abrir(joao, ti, status=Status.CONCLUIDO)

        assert self.resumo(maria)["total"] == 1
        assert self.resumo(joao)["total"] == 2

    def test_atendente_ve_o_total_geral(self, maria, joao, ana, ti):
        abrir(maria, ti, status=Status.ABERTO)
        abrir(joao, ti, status=Status.EM_ATENDIMENTO)
        abrir(ana, ti, status=Status.CONCLUIDO)

        assert self.resumo(ana) == {
            "total": 3,
            "abertas": 1,
            "em_atendimento": 1,
            "concluidas": 1,
        }

    def test_a_soma_dos_status_bate_com_o_total(self, maria, ti):
        for status in (Status.ABERTO, Status.EM_ATENDIMENTO, Status.CONCLUIDO, Status.ABERTO):
            abrir(maria, ti, status=status)

        r = self.resumo(maria)

        assert r["abertas"] + r["em_atendimento"] + r["concluidas"] == r["total"]

    @pytest.mark.parametrize("papel", [Papel.SOLICITANTE, Papel.ATENDENTE])
    def test_numeros_batem_com_a_listagem_do_proprio_usuario(self, maria, joao, ana, ti, rh, papel):
        for dono, status in [
            (maria, Status.ABERTO),
            (maria, Status.EM_ATENDIMENTO),
            (joao, Status.CONCLUIDO),
            (joao, Status.ABERTO),
            (ana, Status.CONCLUIDO),
        ]:
            abrir(dono, ti, status=status)
        usuario = maria if papel == Papel.SOLICITANTE else ana
        cliente = cliente_de(usuario)

        resumo = self.resumo(usuario)

        assert resumo["total"] == listar(cliente).json()["count"]
        assert resumo["abertas"] == listar(cliente, status="ABERTO").json()["count"]
        assert resumo["em_atendimento"] == listar(cliente, status="EM_ATENDIMENTO").json()["count"]
        assert resumo["concluidas"] == listar(cliente, status="CONCLUIDO").json()["count"]

    def test_bate_com_uma_contagem_manual_no_banco(self, maria, joao, ti):
        for status in [Status.ABERTO] * 3 + [Status.EM_ATENDIMENTO] * 2 + [Status.CONCLUIDO]:
            abrir(maria, ti, status=status)
        abrir(joao, ti, status=Status.ABERTO)

        resumo = self.resumo(maria)

        assert (
            resumo["abertas"]
            == Solicitacao.objects.filter(solicitante=maria, status=Status.ABERTO).count()
        )
        assert resumo["total"] == Solicitacao.objects.filter(solicitante=maria).count() == 6

    def test_acompanha_as_mudancas_de_status_e_a_exclusao(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)
        assert self.resumo(maria)["abertas"] == 1

        cliente_de(ana).patch(
            f"{URL}{solicitacao.pk}/status/", {"status": "EM_ATENDIMENTO"}, format="json"
        )
        assert self.resumo(maria) == {
            "total": 1,
            "abertas": 0,
            "em_atendimento": 1,
            "concluidas": 0,
        }

        outra = abrir(maria, ti)
        cliente_de(maria).delete(f"{URL}{outra.pk}/")
        assert self.resumo(maria)["total"] == 1

    def test_uma_unica_consulta_de_agregacao(self, maria, ti, django_assert_max_num_queries):
        for status in (Status.ABERTO, Status.EM_ATENDIMENTO, Status.CONCLUIDO):
            abrir(maria, ti, status=status)

        from solicitacoes import repositories

        with django_assert_max_num_queries(1):
            repositories.contar_por_status()

    def test_sem_login_devolve_401(self):
        assert APIClient().get("/api/dashboard/").status_code == 401

    @pytest.mark.parametrize("metodo", ["post", "put", "patch", "delete"])
    def test_so_get_e_aceito(self, maria, metodo):
        assert getattr(cliente_de(maria), metodo)("/api/dashboard/").status_code == 405


class TestComOsDadosDoSeed:
    def test_numeros_dos_usuarios_de_demonstracao(self):
        call_command("carregar_seed", verbosity=0)
        maria = Usuario.objects.get(login="maria.solicitante")
        ana = Usuario.objects.get(login="ana.atendente")

        assert cliente_de(maria).get("/api/dashboard/").json() == {
            "total": 6,
            "abertas": 2,
            "em_atendimento": 2,
            "concluidas": 2,
        }
        assert cliente_de(ana).get("/api/dashboard/").json() == {
            "total": 12,
            "abertas": 4,
            "em_atendimento": 4,
            "concluidas": 4,
        }

    def test_filtros_sobre_o_seed(self):
        call_command("carregar_seed", verbosity=0)
        ana = cliente_de(Usuario.objects.get(login="ana.atendente"))

        assert listar(ana, status="CONCLUIDO").json()["count"] == 4
        assert listar(ana, categoria=Categoria.objects.get(nome="TI").pk).json()["count"] == 3
        assert listar(ana, q="vpn").json()["count"] == 1
        assert listar(ana, de="2026-09-29", ate="2026-09-29").json()["count"] == 2
