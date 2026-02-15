from django.urls import path
from . import consumers

websocket_urlpatterns = [
    path('ws/threats/', consumers.ThreatConsumer.as_asgi()),
]