from django.urls import path
from . import views

urlpatterns = [
    path('', views.event_list, name='event_list'),
    path('<int:year>/', views.index, name='index'),
    path('<int:year>/vote/', views.vote_next, name='vote_next'),
    path('<int:year>/compare/', views.compare, name='compare'),
]
