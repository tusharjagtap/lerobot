#!/usr/bin/env python
"""
Remote Follower Agent

Runs at remote locations with follower robots, connects to central server.
"""

import asyncio
import logging
import json
import websockets
from typing import Optional

from lerobot.common.robots.so101_follower import SO101Follower, SO101FollowerConfig

logger = logging.getLogger(__name__)

class RemoteFollowerAgent:
    """Agent that runs at remote location with follower robot."""
    
    def __init__(self, 
                 robot_port: str,
                 robot_id: str,
                 agent_name: str,
                 location: str,
                 central_server_host: str,
                 central_server_port: int = 8081):
        
        self.robot_port = robot_port
        self.robot_id = robot_id
        self.agent_name = agent_name
        self.location = location
        self.central_server_url = f"ws://{central_server_host}:{central_server_port}"
        
        # Create follower robot
        self.robot_config = SO101FollowerConfig(
            port=robot_port,
            id=robot_id
        )
        self.robot = SO101Follower(self.robot_config)
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        
    async def start(self):
        """Start the remote follower agent."""
        logger.info(f"Starting remote follower agent: {self.agent_name}")
        logger.info(f"Location: {self.location}")
        logger.info(f"Robot port: {self.robot_port}")
        
        # Connect to robot
        try:
            self.robot.connect()
            logger.info("✅ Robot connected successfully")
        except Exception as e:
            logger.error(f"❌ Failed to connect to robot: {e}")
            return
            
        # Connect to central server
        await self.connect_to_central_server()
        
    async def connect_to_central_server(self):
        """Connect to the central teleoperation server."""
        while True:
            try:
                logger.info(f"Connecting to central server: {self.central_server_url}")
                
                self.websocket = await websockets.connect(self.central_server_url)
                
                # Register with central server
                registration = {
                    "type": "register",
                    "name": self.agent_name,
                    "robot_type": "so101_follower", 
                    "location": self.location,
                    "robot_id": self.robot_id
                }
                
                await self.websocket.send(json.dumps(registration))
                
                # Wait for confirmation
                response = await self.websocket.recv()
                data = json.loads(response)
                
                if data.get("type") == "registered":
                    logger.info("✅ Successfully registered with central server")
                    
                    # Start message handling
                    await self.handle_messages()
                    
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection to central server lost, reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error connecting to central server: {e}")
                await asyncio.sleep(5)
                
    async def handle_messages(self):
        """Handle messages from central server."""
        ping_task = asyncio.create_task(self.ping_loop())
        
        try:
            async for message in self.websocket:
                data = json.loads(message)
                
                if data.get("type") == "action":
                    # Execute action on robot
                    action = data["action"]
                    try:
                        self.robot.send_action(action)
                        logger.debug(f"Executed action: {action}")
                    except Exception as e:
                        logger.error(f"Error executing action: {e}")
                        
                elif data.get("type") == "stop_teleoperation":
                    logger.info("Received stop teleoperation command")
                    
                elif data.get("type") == "pong":
                    logger.debug("Received pong from server")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Lost connection to central server")
        finally:
            ping_task.cancel()
            
    async def ping_loop(self):
        """Send periodic pings to central server."""
        while True:
            try:
                if self.websocket:
                    await self.websocket.send(json.dumps({"type": "ping"}))
                await asyncio.sleep(10)  # Ping every 10 seconds
            except:
                break
                
    async def stop(self):
        """Stop the agent."""
        if self.websocket:
            await self.websocket.close()
        if self.robot.is_connected:
            self.robot.disconnect()
        logger.info("Remote follower agent stopped")

async def main():
    """Run the remote follower agent."""
    logging.basicConfig(level=logging.INFO)
    
    # Configure your remote follower
    config = {
        "robot_port": "/dev/tty.usbmodem123456789",  # Update this
        "robot_id": "remote_follower_1",
        "agent_name": "warehouse_robot_1", 
        "location": "Warehouse Floor 2",
        "central_server_host": "192.168.1.100",  # Update with central server IP
    }
    
    agent = RemoteFollowerAgent(**config)
    
    try:
        await agent.start()
        logger.info("Press Ctrl+C to stop...")
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main())