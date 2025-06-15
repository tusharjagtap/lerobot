#!/usr/bin/env python
"""
Simple Central Server for Testing

A minimal server to test remote follower connections without requiring a leader robot.
"""

import asyncio
import logging
import json
import websockets
import time
from typing import Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

@dataclass
class RemoteFollower:
    name: str
    websocket: any  # Changed from websockets.WebSocketServerProtocol (deprecated)
    robot_type: str
    location: str
    last_ping: float

class SimpleCentralServer:
    """Simple server for testing follower connections."""
    
    def __init__(self, websocket_port: int = 8081):
        self.websocket_port = websocket_port
        self.remote_followers: Dict[str, RemoteFollower] = {}
        self.test_mode = True
        
    async def start(self):
        """Start the simple server."""
        logger.info("Starting simple central server for testing...")
        
        # Create a direct handler function that captures self
        async def websocket_handler(websocket):
            logger.info(f"🔌 Handler called with websocket from {websocket.remote_address}")
            try:
                await self._handle_connection(websocket)
            except Exception as e:
                logger.error(f"Handler error: {e}")
                import traceback
                traceback.print_exc()
        
        # Start WebSocket server for remote followers
        self.websocket_server = await websockets.serve(
            websocket_handler,
            "0.0.0.0", 
            self.websocket_port
        )
        
        # Start test loop
        asyncio.create_task(self.test_loop())
        
        logger.info(f"✅ Simple server running on ws://0.0.0.0:{self.websocket_port}")
        logger.info("This server will accept follower connections and send test actions")
        
    async def _handle_connection(self, websocket):
        """Internal connection handler."""
        logger.info(f"🔌 New remote follower connecting from {websocket.remote_address}")
        
        try:
            logger.info("Waiting for registration message...")
            
            # Wait for registration message
            registration = await websocket.recv()
            logger.info(f"Received registration data: {registration}")
            
            data = json.loads(registration)
            logger.info(f"Parsed registration: {data}")
            
            if data.get("type") == "register":
                follower_name = data["name"]
                robot_type = data["robot_type"]
                location = data["location"]
                
                logger.info(f"Registering follower: {follower_name}")
                
                # Register the follower
                self.remote_followers[follower_name] = RemoteFollower(
                    name=follower_name,
                    websocket=websocket,
                    robot_type=robot_type,
                    location=location,
                    last_ping=time.time()
                )
                
                logger.info(f"✅ Registered remote follower: {follower_name} at {location}")
                
                # Send confirmation
                confirmation = json.dumps({
                    "type": "registered",
                    "message": f"Follower {follower_name} registered successfully"
                })
                
                logger.info(f"Sending confirmation: {confirmation}")
                await websocket.send(confirmation)
                
                # Keep connection alive and handle messages
                logger.info("Starting message loop...")
                async for message in websocket:
                    try:
                        data = json.loads(message)
                        if data.get("type") == "ping":
                            await websocket.send(json.dumps({"type": "pong"}))
                            self.remote_followers[follower_name].last_ping = time.time()
                            logger.debug(f"🏓 Ping from {follower_name}")
                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        
        except websockets.exceptions.ConnectionClosed:
            logger.info("Client disconnected during registration")
            # Remove follower on disconnect
            for name, follower in list(self.remote_followers.items()):
                if follower.websocket == websocket:
                    del self.remote_followers[name]
                    logger.info(f"❌ Remote follower {name} disconnected")
                    break
        except Exception as e:
            logger.error(f"Error handling remote follower: {e}")
            import traceback
            traceback.print_exc()
            
    async def test_loop(self):
        """Send test actions to connected followers."""
        await asyncio.sleep(5)  # Wait for connections
        
        test_actions = [
            {
                "shoulder_pan.pos": 0.0,
                "shoulder_lift.pos": 0.0,
                "elbow_flex.pos": 0.0,
                "wrist_flex.pos": 0.0,
                "wrist_roll.pos": 0.0,
                "gripper.pos": 50.0
            },
            {
                "shoulder_pan.pos": 10.0,
                "shoulder_lift.pos": -5.0,
                "elbow_flex.pos": 15.0,
                "wrist_flex.pos": -10.0,
                "wrist_roll.pos": 0.0,
                "gripper.pos": 60.0
            },
            {
                "shoulder_pan.pos": -10.0,
                "shoulder_lift.pos": 5.0,
                "elbow_flex.pos": -15.0,
                "wrist_flex.pos": 10.0,
                "wrist_roll.pos": 0.0,
                "gripper.pos": 40.0
            }
        ]
        
        action_index = 0
        
        while True:
            if not self.remote_followers:
                logger.info("⏳ Waiting for followers to connect...")
                await asyncio.sleep(2)
                continue
                
            try:
                # Send test action to all followers
                test_action = test_actions[action_index % len(test_actions)]
                action_index += 1
                
                logger.info(f"📤 Sending test action to {len(self.remote_followers)} followers: {test_action}")
                
                action_message = json.dumps({
                    "type": "action",
                    "action": test_action,
                    "timestamp": time.time()
                })
                
                # Send to all connected followers
                disconnected_followers = []
                for name, follower in self.remote_followers.items():
                    try:
                        await follower.websocket.send(action_message)
                        logger.debug(f"✅ Sent action to {name}")
                    except websockets.exceptions.ConnectionClosed:
                        disconnected_followers.append(name)
                    except Exception as e:
                        logger.error(f"❌ Error sending to {name}: {e}")
                
                # Clean up disconnected followers
                for name in disconnected_followers:
                    del self.remote_followers[name]
                    logger.warning(f"🗑️ Removed disconnected follower: {name}")
                
                # Send test actions every 5 seconds
                await asyncio.sleep(5)
                
            except Exception as e:
                logger.error(f"Error in test loop: {e}")
                await asyncio.sleep(1)

async def main():
    """Run the simple central server."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    server = SimpleCentralServer()
    
    try:
        await server.start()
        
        logger.info("✅ Simple server started successfully!")
        logger.info("Now run your remote follower agent to test the connection")
        logger.info("Press Ctrl+C to stop...")
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down simple server...")

if __name__ == "__main__":
    asyncio.run(main()) 