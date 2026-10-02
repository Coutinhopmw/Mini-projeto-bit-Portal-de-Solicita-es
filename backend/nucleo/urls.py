from django.urls import path

from . import views

urlpatterns = [
    path("ola/", views.ola, name="ola"),
    path("saude/", views.saude, name="saude"),
]
