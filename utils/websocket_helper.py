# utils/websocket_helper.py
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync

def send_to_websocket(message):
    """Send message to all connected WebSocket clients"""
    channel_layer = get_channel_layer()
    async_to_sync(channel_layer.group_send)(
        "print_messages",
        {
            "type": "send_print",  # This calls send_print() method
            "text": message  # Changed from 'message' to 'text'
        }
    )