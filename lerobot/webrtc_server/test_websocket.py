#!/usr/bin/env python
"""
Simple WebSocket connection test
"""

import asyncio
import websockets
import json

async def test_connection():
    try:
        print('Connecting to ws://127.0.0.1:8081...')
        websocket = await websockets.connect('ws://127.0.0.1:8081')
        print('✅ Connected successfully!')
        
        # Send registration message
        registration = {
            'type': 'register',
            'name': 'test_follower',
            'robot_type': 'so101_follower',
            'location': 'Test Location',
            'robot_id': 'test_robot'
        }
        
        await websocket.send(json.dumps(registration))
        print('📤 Sent registration message')
        
        # Wait for response
        response = await websocket.recv()
        print(f'📥 Received response: {response}')
        
        await websocket.close()
        print('Connection test completed')
        
    except Exception as e:
        print(f'❌ Connection failed: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_connection()) 