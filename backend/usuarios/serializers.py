from rest_framework import serializers

from .models import Usuario


class LoginSerializer(serializers.Serializer):
    login = serializers.CharField(
        error_messages={"required": "Informe o usuário.", "blank": "Informe o usuário."}
    )
    senha = serializers.CharField(
        trim_whitespace=False,
        error_messages={"required": "Informe a senha.", "blank": "Informe a senha."},
    )


class RenovacaoSerializer(serializers.Serializer):
    renovacao = serializers.CharField(
        error_messages={
            "required": "Informe o token de renovação.",
            "blank": "Informe o token de renovação.",
        }
    )


class UsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = Usuario
        fields = ["id", "nome", "login", "papel"]
        read_only_fields = fields
