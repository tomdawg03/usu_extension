from django.urls import path
from . import views

urlpatterns = [
    path('', views.county_select, name='county_select'),
    path('chat/', views.chat_view, name='chat'),
    path('api/chat', views.chat_api, name='chat_api'),
    path('api/feedback', views.feedback_api, name='feedback_api'),
]
