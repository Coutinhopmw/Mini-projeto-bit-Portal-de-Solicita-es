from datetime import timedelta

import pytest
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from solicitacoes import repositories, services
from solicitacoes.models import Categoria, HistoricoStatus, Solicitacao, Status
from usuarios.models import Papel, Usuario

pytestmark = pytest.mark.django_db

URL = "/api/solicitacoes/"
DADOS = {
    "titulo": "Notebook não liga",
    "descricao": "O notebook não liga depois da atualização de ontem.",
}


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


@pytest.fixture
def entrada(ti):
    return {**DADOS, "categoria": ti.pk}


def abrir(solicitante, categoria, status=Status.ABERTO, titulo="Título da demanda", **extra):
    solicitacao = Solicitacao.objects.create(
        titulo=titulo,
        descricao="Descrição com mais de dez caracteres.",
        categoria=categoria,
        solicitante=solicitante,
        status=status,
        **extra,
    )
    HistoricoStatus.objects.create(
        solicitacao=solicitacao, status_novo=Status.ABERTO, alterado_por=solicitante
    )
    return solicitacao


class TestCriar:
    def test_cria_com_os_campos_automaticos_definidos_no_servidor(self, maria, entrada, ti):
        resposta = cliente_de(maria).post(URL, entrada, format="json")

        assert resposta.status_code == 201
        corpo = resposta.json()
        assert corpo["status"] == "ABERTO"
        assert corpo["solicitante"] == {"id": maria.pk, "nome": "Maria"}
        assert corpo["categoria"] == {"id": ti.pk, "nome": "TI"}
        assert corpo["codigo"] == f"SOL-{corpo['id']:05d}"
        assert corpo["titulo"] == "Notebook não liga"
        assert abs(timezone.now() - Solicitacao.objects.get().criado_em) < timedelta(seconds=5)

    def test_valores_enviados_para_campos_automaticos_sao_ignorados(self, maria, joao, entrada):
        enviado = {
            **entrada,
            "id": 999,
            "codigo": "SOL-99999",
            "status": "CONCLUIDO",
            "solicitante": joao.pk,
            "criado_em": "2020-01-01T00:00:00Z",
            "atualizado_em": "2020-01-01T00:00:00Z",
        }

        resposta = cliente_de(maria).post(URL, enviado, format="json")

        assert resposta.status_code == 201
        solicitacao = Solicitacao.objects.get()
        assert solicitacao.pk != 999
        assert solicitacao.status == Status.ABERTO
        assert solicitacao.solicitante == maria
        assert solicitacao.criado_em.year == timezone.now().year

    def test_criacao_grava_o_primeiro_registro_do_historico(self, maria, entrada):
        resposta = cliente_de(maria).post(URL, entrada, format="json")

        historico = resposta.json()["historico"]
        assert len(historico) == 1
        assert historico[0]["status_anterior"] is None
        assert historico[0]["status_novo"] == "ABERTO"
        assert historico[0]["alterado_por"] == {"id": maria.pk, "nome": "Maria"}

    def test_atendente_tambem_abre_solicitacoes(self, ana, entrada):
        resposta = cliente_de(ana).post(URL, entrada, format="json")

        assert resposta.status_code == 201
        assert resposta.json()["solicitante"]["id"] == ana.pk

    def test_espacos_das_pontas_sao_removidos(self, maria, entrada):
        entrada["titulo"] = "   Notebook não liga   "

        cliente_de(maria).post(URL, entrada, format="json")

        assert Solicitacao.objects.get().titulo == "Notebook não liga"

    def test_campos_obrigatorios(self, maria):
        resposta = cliente_de(maria).post(URL, {}, format="json")

        assert resposta.status_code == 400
        assert resposta.json() == {
            "erro": "VALIDACAO",
            "mensagem": "Dados inválidos",
            "detalhes": {
                "titulo": "Informe o título.",
                "descricao": "Informe a descrição.",
                "categoria": "Selecione uma categoria.",
            },
        }
        assert Solicitacao.objects.count() == 0

    @pytest.mark.parametrize(
        ("campo", "valor", "mensagem"),
        [
            ("titulo", "ab", "O título deve ter entre 3 e 150 caracteres."),
            ("titulo", "   ab   ", "O título deve ter entre 3 e 150 caracteres."),
            ("titulo", "t" * 151, "O título deve ter entre 3 e 150 caracteres."),
            ("titulo", "   ", "Informe o título."),
            ("descricao", "curta", "A descrição deve ter entre 10 e 2000 caracteres."),
            ("descricao", "d" * 2001, "A descrição deve ter entre 10 e 2000 caracteres."),
            ("categoria", 99999, "Categoria inválida ou inativa."),
            ("categoria", "abc", "Categoria inválida ou inativa."),
            ("categoria", None, "Selecione uma categoria."),
        ],
    )
    def test_validacao_de_cada_campo(self, maria, entrada, campo, valor, mensagem):
        entrada[campo] = valor

        resposta = cliente_de(maria).post(URL, entrada, format="json")

        assert resposta.status_code == 400
        assert resposta.json()["detalhes"] == {campo: mensagem}
        assert Solicitacao.objects.count() == 0

    def test_limites_exatos_sao_aceitos(self, maria, entrada):
        entrada["titulo"] = "t" * 150
        entrada["descricao"] = "d" * 2000

        assert cliente_de(maria).post(URL, entrada, format="json").status_code == 201

    def test_categoria_inativa_e_recusada(self, maria, entrada, ti):
        ti.ativa = False
        ti.save()

        resposta = cliente_de(maria).post(URL, entrada, format="json")

        assert resposta.status_code == 400
        assert resposta.json()["detalhes"]["categoria"] == "Categoria inválida ou inativa."

    def test_sem_login_devolve_401(self, entrada):
        resposta = APIClient().post(URL, entrada, format="json")

        assert resposta.status_code == 401
        assert resposta.json()["erro"] == "NAO_AUTENTICADO"

    def test_historico_falho_desfaz_a_criacao(self, maria, ti, monkeypatch):
        def falhar(*args, **kwargs):
            raise RuntimeError("falha ao gravar o histórico")

        monkeypatch.setattr(repositories, "registrar_historico", falhar)

        with pytest.raises(RuntimeError):
            services.criar(maria, "Título válido", "Descrição válida de teste.", ti)

        assert Solicitacao.objects.count() == 0


class TestListar:
    def test_colunas_da_listagem(self, maria, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(maria).get(URL)

        assert resposta.status_code == 200
        assert set(resposta.json()) == {"count", "next", "previous", "results"}
        item = resposta.json()["results"][0]
        assert set(item) == {
            "id",
            "codigo",
            "titulo",
            "categoria",
            "solicitante",
            "status",
            "criado_em",
        }
        assert item["codigo"] == f"SOL-{solicitacao.pk:05d}"
        assert item["categoria"] == {"id": ti.pk, "nome": "TI"}
        assert item["solicitante"] == {"id": maria.pk, "nome": "Maria"}

    def test_solicitante_ve_so_as_proprias(self, maria, joao, ti):
        abrir(maria, ti, titulo="Da Maria")
        abrir(joao, ti, titulo="Do João")

        resposta = cliente_de(maria).get(URL)

        assert [item["titulo"] for item in resposta.json()["results"]] == ["Da Maria"]
        assert resposta.json()["count"] == 1

    def test_atendente_ve_todas(self, maria, joao, ana, ti):
        abrir(maria, ti)
        abrir(joao, ti)

        assert cliente_de(ana).get(URL).json()["count"] == 2

    def test_ordenada_da_mais_recente_para_a_mais_antiga(self, maria, ti):
        agora = timezone.now()
        abrir(maria, ti, titulo="Antiga", criado_em=agora - timedelta(days=2))
        abrir(maria, ti, titulo="Recente", criado_em=agora)
        abrir(maria, ti, titulo="Meio", criado_em=agora - timedelta(days=1))

        titulos = [i["titulo"] for i in cliente_de(maria).get(URL).json()["results"]]

        assert titulos == ["Recente", "Meio", "Antiga"]

    def test_pagina_de_dez_itens(self, maria, ti):
        for numero in range(12):
            abrir(maria, ti, titulo=f"Demanda {numero:02d}")

        primeira = cliente_de(maria).get(URL).json()
        segunda = cliente_de(maria).get(URL, {"pagina": 2}).json()

        assert primeira["count"] == 12
        assert len(primeira["results"]) == 10
        assert primeira["previous"] is None
        assert "pagina=2" in primeira["next"]
        assert len(segunda["results"]) == 2
        assert segunda["next"] is None
        assert segunda["previous"] is not None

    def test_paginas_nao_repetem_itens(self, maria, ti):
        for numero in range(12):
            abrir(maria, ti, titulo=f"Demanda {numero:02d}")

        ids = []
        for pagina in (1, 2):
            ids += [
                i["id"] for i in cliente_de(maria).get(URL, {"pagina": pagina}).json()["results"]
            ]

        assert len(ids) == len(set(ids)) == 12

    def test_tamanho_da_pagina_e_limitado(self, maria, ti):
        for numero in range(3):
            abrir(maria, ti, titulo=f"Demanda {numero}")

        assert len(cliente_de(maria).get(URL, {"tamanho": 2}).json()["results"]) == 2
        assert cliente_de(maria).get(URL, {"tamanho": 9999}).status_code == 200

    @pytest.mark.parametrize("pagina", ["0", "-1", "abc", "99"])
    def test_pagina_invalida_devolve_400(self, maria, ti, pagina):
        abrir(maria, ti)

        resposta = cliente_de(maria).get(URL, {"pagina": pagina})

        assert resposta.status_code == 400
        assert resposta.json()["detalhes"] == {"pagina": "Página inválida."}

    def test_lista_vazia(self, maria):
        resposta = cliente_de(maria).get(URL)

        assert resposta.status_code == 200
        assert resposta.json() == {"count": 0, "next": None, "previous": None, "results": []}

    def test_sem_login_devolve_401(self):
        assert APIClient().get(URL).status_code == 401

    def test_listagem_nao_faz_uma_consulta_por_item(self, maria, ti, django_assert_max_num_queries):
        for numero in range(8):
            abrir(maria, ti, titulo=f"Demanda {numero}")

        with django_assert_max_num_queries(6):
            cliente_de(maria).get(URL)


class TestDetalhe:
    def test_devolve_descricao_e_historico(self, maria, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(maria).get(f"{URL}{solicitacao.pk}/")

        assert resposta.status_code == 200
        corpo = resposta.json()
        assert corpo["descricao"] == "Descrição com mais de dez caracteres."
        assert corpo["pode_editar"] is True
        assert corpo["pode_excluir"] is True
        assert [h["status_novo"] for h in corpo["historico"]] == ["ABERTO"]
        assert set(corpo) == {
            "id",
            "codigo",
            "titulo",
            "categoria",
            "solicitante",
            "status",
            "criado_em",
            "descricao",
            "atualizado_em",
            "pode_editar",
            "pode_excluir",
            "pode_alterar_status",
            "proximo_status",
            "historico",
        }

    def test_historico_em_ordem_cronologica(self, maria, ana, ti):
        solicitacao = abrir(maria, ti, status=Status.CONCLUIDO)
        agora = timezone.now()
        HistoricoStatus.objects.filter(solicitacao=solicitacao).update(
            alterado_em=agora - timedelta(hours=3)
        )
        HistoricoStatus.objects.create(
            solicitacao=solicitacao,
            status_anterior=Status.EM_ATENDIMENTO,
            status_novo=Status.CONCLUIDO,
            alterado_por=ana,
            alterado_em=agora,
        )
        HistoricoStatus.objects.create(
            solicitacao=solicitacao,
            status_anterior=Status.ABERTO,
            status_novo=Status.EM_ATENDIMENTO,
            alterado_por=ana,
            alterado_em=agora - timedelta(hours=1),
        )

        historico = cliente_de(maria).get(f"{URL}{solicitacao.pk}/").json()["historico"]

        assert [h["status_novo"] for h in historico] == ["ABERTO", "EM_ATENDIMENTO", "CONCLUIDO"]

    def test_atendente_ve_qualquer_solicitacao(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(ana).get(f"{URL}{solicitacao.pk}/")

        assert resposta.status_code == 200
        assert resposta.json()["pode_editar"] is False

    def test_solicitacao_de_outra_pessoa_devolve_404_e_nao_403(self, maria, joao, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(joao).get(f"{URL}{solicitacao.pk}/")

        assert resposta.status_code == 404
        assert resposta.json() == {
            "erro": "NAO_ENCONTRADO",
            "mensagem": "Solicitação não encontrada.",
        }

    def test_inexistente_devolve_o_mesmo_404(self, maria):
        resposta = cliente_de(maria).get(f"{URL}99999/")

        assert resposta.status_code == 404
        assert resposta.json() == {
            "erro": "NAO_ENCONTRADO",
            "mensagem": "Solicitação não encontrada.",
        }

    def test_pode_editar_e_falso_depois_de_aberta(self, maria, ti):
        solicitacao = abrir(maria, ti, status=Status.EM_ATENDIMENTO)

        corpo = cliente_de(maria).get(f"{URL}{solicitacao.pk}/").json()

        assert corpo["pode_editar"] is False
        assert corpo["pode_excluir"] is False

    def test_sem_login_devolve_401(self, maria, ti):
        solicitacao = abrir(maria, ti)

        assert APIClient().get(f"{URL}{solicitacao.pk}/").status_code == 401


class TestEditar:
    def test_autor_edita_enquanto_aberta(self, maria, rh, ti):
        solicitacao = abrir(maria, ti)
        antes = solicitacao.atualizado_em

        resposta = cliente_de(maria).put(
            f"{URL}{solicitacao.pk}/",
            {
                "titulo": "Novo título",
                "descricao": "Nova descrição bem detalhada.",
                "categoria": rh.pk,
            },
            format="json",
        )

        assert resposta.status_code == 200
        solicitacao.refresh_from_db()
        assert (solicitacao.titulo, solicitacao.categoria) == ("Novo título", rh)
        assert solicitacao.descricao == "Nova descrição bem detalhada."
        assert solicitacao.atualizado_em > antes
        assert resposta.json()["categoria"] == {"id": rh.pk, "nome": "RH"}

    def test_edicao_nao_altera_status_solicitante_nem_data_de_criacao(
        self, maria, joao, entrada, ti
    ):
        solicitacao = abrir(maria, ti)
        criada_em = solicitacao.criado_em

        cliente_de(maria).put(
            f"{URL}{solicitacao.pk}/",
            {
                **entrada,
                "status": "CONCLUIDO",
                "solicitante": joao.pk,
                "criado_em": "2020-01-01T00:00:00Z",
            },
            format="json",
        )

        solicitacao.refresh_from_db()
        assert solicitacao.status == Status.ABERTO
        assert solicitacao.solicitante == maria
        assert solicitacao.criado_em == criada_em

    def test_edicao_nao_mexe_no_historico(self, maria, entrada, ti):
        solicitacao = abrir(maria, ti)

        cliente_de(maria).put(f"{URL}{solicitacao.pk}/", entrada, format="json")

        assert solicitacao.historico.count() == 1

    @pytest.mark.parametrize("status", [Status.EM_ATENDIMENTO, Status.CONCLUIDO])
    def test_fora_do_status_aberto_devolve_409(self, maria, entrada, ti, status):
        solicitacao = abrir(maria, ti, status=status)

        resposta = cliente_de(maria).put(f"{URL}{solicitacao.pk}/", entrada, format="json")

        assert resposta.status_code == 409
        assert resposta.json() == {
            "erro": "SOLICITACAO_NAO_EDITAVEL",
            "mensagem": "Só é possível editar ou excluir solicitações com status Aberto.",
        }
        solicitacao.refresh_from_db()
        assert solicitacao.titulo == "Título da demanda"

    def test_atendente_que_nao_e_o_autor_recebe_403(self, maria, ana, entrada, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(ana).put(f"{URL}{solicitacao.pk}/", entrada, format="json")

        assert resposta.status_code == 403
        assert resposta.json()["erro"] == "SEM_PERMISSAO"
        solicitacao.refresh_from_db()
        assert solicitacao.titulo == "Título da demanda"

    def test_atendente_edita_a_propria_solicitacao(self, ana, entrada, ti):
        solicitacao = abrir(ana, ti)

        resposta = cliente_de(ana).put(f"{URL}{solicitacao.pk}/", entrada, format="json")

        assert resposta.status_code == 200

    def test_solicitante_de_outra_pessoa_recebe_404(self, maria, joao, entrada, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(joao).put(f"{URL}{solicitacao.pk}/", entrada, format="json")

        assert resposta.status_code == 404

    def test_dados_invalidos_devolvem_400_e_nao_alteram(self, maria, entrada, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(maria).put(
            f"{URL}{solicitacao.pk}/", {**entrada, "titulo": "ab"}, format="json"
        )

        assert resposta.status_code == 400
        solicitacao.refresh_from_db()
        assert solicitacao.titulo == "Título da demanda"

    def test_put_exige_todos_os_campos(self, maria, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(maria).put(
            f"{URL}{solicitacao.pk}/", {"titulo": "Só o título"}, format="json"
        )

        assert resposta.status_code == 400
        assert set(resposta.json()["detalhes"]) == {"descricao", "categoria"}

    def test_patch_nao_e_aceito(self, maria, entrada, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(maria).patch(f"{URL}{solicitacao.pk}/", entrada, format="json")

        assert resposta.status_code == 405

    def test_ordem_das_verificacoes_404_antes_de_403_antes_de_400_antes_de_409(
        self, maria, joao, ana, ti
    ):
        em_atendimento = abrir(maria, ti, status=Status.EM_ATENDIMENTO)
        invalido = {"titulo": "ab"}

        # Outro Solicitante nem enxerga a solicitação: 404, mesmo com dados inválidos.
        assert (
            cliente_de(joao).put(f"{URL}{em_atendimento.pk}/", invalido, format="json").status_code
            == 404
        )
        # O Atendente enxerga, mas não é o autor: 403, mesmo com dados inválidos e status errado.
        assert (
            cliente_de(ana).put(f"{URL}{em_atendimento.pk}/", invalido, format="json").status_code
            == 403
        )
        # O autor com dados inválidos recebe 400, antes do 409 do status.
        assert (
            cliente_de(maria).put(f"{URL}{em_atendimento.pk}/", invalido, format="json").status_code
            == 400
        )

    def test_sem_login_devolve_401(self, maria, entrada, ti):
        solicitacao = abrir(maria, ti)

        assert APIClient().put(f"{URL}{solicitacao.pk}/", entrada, format="json").status_code == 401

    def test_estado_e_relido_com_a_linha_travada(self, maria, ti):
        """Se o atendente muda o status entre a leitura e a gravação, a edição é barrada."""
        solicitacao = abrir(maria, ti)
        Solicitacao.objects.filter(pk=solicitacao.pk).update(status=Status.EM_ATENDIMENTO)

        from solicitacoes.excecoes import SolicitacaoNaoEditavel

        with pytest.raises(SolicitacaoNaoEditavel):
            services.editar(maria, solicitacao.pk, "Novo título", "Nova descrição longa.", ti)


class TestExcluir:
    def test_autor_exclui_enquanto_aberta(self, maria, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(maria).delete(f"{URL}{solicitacao.pk}/")

        assert resposta.status_code == 204
        assert resposta.content == b""
        assert not Solicitacao.objects.filter(pk=solicitacao.pk).exists()

    def test_exclusao_e_fisica_e_leva_o_historico(self, maria, ti):
        solicitacao = abrir(maria, ti)
        assert HistoricoStatus.objects.count() == 1

        cliente_de(maria).delete(f"{URL}{solicitacao.pk}/")

        assert HistoricoStatus.objects.count() == 0

    def test_depois_de_excluida_devolve_404(self, maria, ti):
        solicitacao = abrir(maria, ti)
        cliente = cliente_de(maria)
        cliente.delete(f"{URL}{solicitacao.pk}/")

        assert cliente.get(f"{URL}{solicitacao.pk}/").status_code == 404
        assert cliente.delete(f"{URL}{solicitacao.pk}/").status_code == 404

    @pytest.mark.parametrize("status", [Status.EM_ATENDIMENTO, Status.CONCLUIDO])
    def test_fora_do_status_aberto_devolve_409_e_mantem_a_solicitacao(self, maria, ti, status):
        solicitacao = abrir(maria, ti, status=status)

        resposta = cliente_de(maria).delete(f"{URL}{solicitacao.pk}/")

        assert resposta.status_code == 409
        assert resposta.json()["erro"] == "SOLICITACAO_NAO_EDITAVEL"
        assert Solicitacao.objects.filter(pk=solicitacao.pk).exists()
        assert HistoricoStatus.objects.filter(solicitacao=solicitacao).exists()

    def test_atendente_que_nao_e_o_autor_recebe_403(self, maria, ana, ti):
        solicitacao = abrir(maria, ti)

        resposta = cliente_de(ana).delete(f"{URL}{solicitacao.pk}/")

        assert resposta.status_code == 403
        assert Solicitacao.objects.filter(pk=solicitacao.pk).exists()

    def test_solicitante_de_outra_pessoa_recebe_404(self, maria, joao, ti):
        solicitacao = abrir(maria, ti)

        assert cliente_de(joao).delete(f"{URL}{solicitacao.pk}/").status_code == 404
        assert Solicitacao.objects.filter(pk=solicitacao.pk).exists()

    def test_sem_login_devolve_401(self, maria, ti):
        solicitacao = abrir(maria, ti)

        assert APIClient().delete(f"{URL}{solicitacao.pk}/").status_code == 401


class TestCategorias:
    def test_lista_so_as_ativas_em_ordem_alfabetica(self, maria, ti, rh):
        Categoria.objects.create(nome="Compras")
        Categoria.objects.create(nome="Antiga", ativa=False)

        resposta = cliente_de(maria).get("/api/categorias/")

        assert resposta.status_code == 200
        assert [c["nome"] for c in resposta.json()] == ["Compras", "RH", "TI"]
        assert set(resposta.json()[0]) == {"id", "nome"}

    def test_atendente_tambem_lista(self, ana, ti):
        assert cliente_de(ana).get("/api/categorias/").status_code == 200

    def test_sem_login_devolve_401(self):
        assert APIClient().get("/api/categorias/").status_code == 401

    def test_so_get_e_aceito(self, maria):
        assert (
            cliente_de(maria).post("/api/categorias/", {"nome": "Nova"}, format="json").status_code
            == 405
        )
