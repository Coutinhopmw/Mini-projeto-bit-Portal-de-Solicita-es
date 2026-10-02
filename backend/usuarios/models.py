from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models import Q, Value
from django.db.models.functions import Now


class Papel(models.TextChoices):
    SOLICITANTE = "SOLICITANTE", "Solicitante"
    ATENDENTE = "ATENDENTE", "Atendente"


class UsuarioManager(BaseUserManager):
    def create_user(self, login, password=None, **campos):
        if not login:
            raise ValueError("Informe o login.")
        usuario = self.model(login=login, **campos)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_superuser(self, login, password=None, **campos):
        campos["administrador"] = True
        return self.create_user(login, password, **campos)


class Usuario(AbstractBaseUser):
    """Usuário do portal. O Django Admin é liberado por `administrador` (D01)."""

    nome = models.CharField(max_length=150)
    login = models.CharField(max_length=50, unique=True)
    # O campo `password` do Django guarda o hash na coluna senha_hash.
    password = models.CharField(max_length=128, db_column="senha_hash")
    papel = models.CharField(
        max_length=20,
        choices=Papel,
        default=Papel.SOLICITANTE,
        db_default=Value(Papel.SOLICITANTE),
    )
    ativo = models.BooleanField(default=True, db_default=True)
    administrador = models.BooleanField(default=False, db_default=False)
    criado_em = models.DateTimeField(db_default=Now())
    last_login = models.DateTimeField(null=True, blank=True, db_column="ultimo_acesso")

    objects = UsuarioManager()

    USERNAME_FIELD = "login"
    REQUIRED_FIELDS = ["nome"]

    class Meta:
        db_table = "usuarios"
        constraints = [
            models.CheckConstraint(
                condition=Q(papel__in=Papel.values),
                name="usuarios_papel_valido",
            ),
        ]

    def __str__(self):
        return self.login

    # Atributos que o Django e o Admin esperam, ligados aos campos em português.
    @property
    def is_active(self):
        return self.ativo

    @property
    def is_staff(self):
        return self.administrador

    @property
    def is_superuser(self):
        return self.administrador

    def has_perm(self, perm, obj=None):
        return self.ativo and self.administrador

    def has_module_perms(self, app_label):
        return self.ativo and self.administrador
