from django.urls import path
from . import views

urlpatterns = [
    path('', views.county_select, name='county_select'),
    path('hub/', views.hub_view, name='hub'),
    path('chat/', views.chat_view, name='chat'),
    path('search/', views.search_view, name='search'),
    path('hardiness/', views.hardiness_view, name='hardiness'),
    path('api/chat', views.chat_api, name='chat_api'),
    path('api/search', views.search_api, name='search_api'),
    path('api/hardiness', views.hardiness_api, name='hardiness_api'),
    path('api/feedback', views.feedback_api, name='feedback_api'),
    path('api/escalate', views.escalation_api, name='escalate'),
]
