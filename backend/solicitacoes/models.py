from django.conf import settings
from django.db import models
from django.db.models import F, Q, Value
from django.db.models.functions import Length, Now, Trim
from django.db.models.lookups import GreaterThanOrEqual


class Status(models.TextChoices):
    ABERTO = "ABERTO", "Aberto"
    EM_ATENDIMENTO = "EM_ATENDIMENTO", "Em Atendimento"
    CONCLUIDO = "CONCLUIDO", "Concluído"


class Categoria(models.Model):
    nome = models.CharField(max_length=60, unique=True)
    ativa = models.BooleanField(default=True, db_default=True)

    class Meta:
        db_table = "categorias"

    def __str__(self):
        return self.nome


class Solicitacao(models.Model):
    titulo = models.CharField(max_length=150)
    descricao = models.CharField(max_length=2000)
    categoria = models.ForeignKey(Categoria, on_delete=models.PROTECT, related_name="solicitacoes")
    solicitante = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="solicitacoes"
    )
    status = models.CharField(
        max_length=20,
        choices=Status,
        default=Status.ABERTO,
        db_default=Value(Status.ABERTO),
    )
    criado_em = models.DateTimeField(db_default=Now())
    atualizado_em = models.DateTimeField(auto_now=True, db_default=Now())

    class Meta:
        db_table = "solicitacoes"
        constraints = [
            models.CheckConstraint(
                condition=Q(GreaterThanOrEqual(Length(Trim("titulo")), 3)),
                name="solicitacoes_titulo_minimo",
            ),
            models.CheckConstraint(
                condition=Q(GreaterThanOrEqual(Length(Trim("descricao")), 10)),
                name="solicitacoes_descricao_minima",
            ),
            models.CheckConstraint(
                condition=Q(status__in=Status.values),
                name="solicitacoes_status_valido",
            ),
        ]
        # Os índices de categoria_id e solicitante_id são criados pelo Django nas chaves
        # estrangeiras, então só os demais ficam declarados aqui.
        indexes = [
            models.Index(fields=["status"], name="solicitacoes_status_idx"),
            models.Index(fields=["criado_em"], name="solicitacoes_criado_em_idx"),
        ]

    def __str__(self):
        return f"{self.codigo} {self.titulo}"

    @property
    def codigo(self):
        """Código legível derivado do id, sem coluna (D06): SOL-00042."""
        return f"SOL-{self.pk:05d}"


class HistoricoStatus(models.Model):
    # Sem índice próprio: o índice composto abaixo já cobre a busca por solicitacao_id.
    solicitacao = models.ForeignKey(
        Solicitacao, on_delete=models.CASCADE, related_name="historico", db_index=False
    )
    # NULL significa "sem status anterior": é o registro gerado na criação (D11).
    status_anterior = models.CharField(  # noqa: DJ001
        max_length=20,
        choices=Status,
        null=True,
        blank=True,
    )
    status_novo = models.CharField(max_length=20, choices=Status)
    alterado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="alteracoes_status"
    )
    alterado_em = models.DateTimeField(db_default=Now())

    class Meta:
        db_table = "historico_status"
        constraints = [
            models.CheckConstraint(
                condition=Q(status_anterior__isnull=True) | Q(status_anterior__in=Status.values),
                name="historico_status_anterior_valido",
            ),
            models.CheckConstraint(
                condition=Q(status_novo__in=Status.values),
                name="historico_status_novo_valido",
            ),
            models.CheckConstraint(
                condition=Q(status_anterior__isnull=True) | ~Q(status_anterior=F("status_novo")),
                name="historico_status_muda",
            ),
        ]
        indexes = [
            models.Index(fields=["solicitacao", "alterado_em"], name="historico_solicitacao_idx"),
        ]

    def __str__(self):
        return f"{self.solicitacao_id}: {self.status_anterior} -> {self.status_novo}"
