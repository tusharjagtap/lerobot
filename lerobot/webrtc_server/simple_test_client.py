#!/usr/bin/env python
"""
Simple WebSocket client for testing
"""

import asyncio
import websockets
import json

async def test_simple_connection():
    try:
        print('Connecting to ws://127.0.0.1:8081...')
        
        async with websockets.connect('ws://127.0.0.1:8081') as websocket:
            print('✅ Connected successfully!')
            
            # Send a simple message
            test_message = "Hello, server!"
            print(f'📤 Sending: {test_message}')
            await websocket.send(test_message)
            
            # Wait for response
            print('⏳ Waiting for response...')
            response = await websocket.recv()
            print(f'📥 Received: {response}')
            
            print('✅ Test completed successfully!')
            
    except Exception as e:
        print(f'❌ Test failed: {e}')
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_simple_connection()) 