import json
from channels.generic.websocket import AsyncWebsocketConsumer

class ThreatConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        # ✅ MUST join the group
        self.group_name = "print_messages"
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        
        await self.accept()
        
        await self.send(text_data=json.dumps({
            'type': 'connection_established',
            'message': 'Connected to ThreatWatch WebSocket'
        }))
    
    async def disconnect(self, close_code):
        # ✅ MUST leave the group
        await self.channel_layer.group_discard(
            self.group_name,
            self.channel_name
        )
    
    async def receive(self, text_data):
        try:
            data = json.loads(text_data)
            message = data.get('message', '')
            
            await self.send(text_data=json.dumps({
                'type': 'message',
                'content': f'Received: {message}',
            }))
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid JSON received'
            }))
    
    # ✅ MUST have this method to receive from send_to_websocket()
    async def send_print(self, event):
        await self.send(text_data=json.dumps({
            'type': 'message',
            'content': event['text']
        }))