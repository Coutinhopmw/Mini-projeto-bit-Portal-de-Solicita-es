from django.contrib import admin
from django.urls import include, path, re_path

from nucleo import views as nucleo_views

handler404 = "nucleo.views.pagina_nao_encontrada"
handler500 = "nucleo.views.erro_interno"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("nucleo.urls")),
    path("api/", include("usuarios.urls")),
    path("api/", include("solicitacoes.urls")),
    # Sempre por último: qualquer outro caminho em /api/ devolve o 404 no formato padrão.
    re_path(r"^api/", nucleo_views.rota_inexistente),
]
