#!/usr/bin/env python
"""
Minimal WebSocket server for testing basic connectivity
"""

import asyncio
import websockets
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def echo_handler(websocket, path):
    logger.info(f"Client connected from {websocket.remote_address}")
    try:
        async for message in websocket:
            logger.info(f"Received: {message}")
            
            # Echo the message back
            response = {
                "echo": message,
                "status": "received"
            }
            
            await websocket.send(json.dumps(response))
            logger.info(f"Sent response: {response}")
            
    except websockets.exceptions.ConnectionClosed:
        logger.info("Client disconnected")
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()

async def main():
    logger.info("Starting minimal WebSocket server on port 8081...")
    
    server = await websockets.serve(echo_handler, "localhost", 8081)
    logger.info("✅ Server started on ws://localhost:8081")
    
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main()) 