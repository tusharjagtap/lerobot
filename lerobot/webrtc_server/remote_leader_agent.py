#!/usr/bin/env python
"""
Remote Leader Agent

Runs at remote locations with leader robots, connects to central teleop server remotely via WebSocket
"""

import asyncio
import logging
import json
import websockets
from typing import Optional, Any

from lerobot.common.teleoperators.so101_leader import SO101Leader, SO101LeaderConfig

logger = logging.getLogger(__name__)

class RemoteLeaderAgent:
    """Agent that runs at remote location with leader robot."""
    
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
        # Use secure WebSocket (wss://) for Cloud Run HTTPS endpoints
        if central_server_port == 443:
            self.central_server_url = f"wss://{central_server_host}"
        else:
            self.central_server_url = f"ws://{central_server_host}:{central_server_port}"
        
        # Create leader robot
        self.robot_config = SO101LeaderConfig(
            port=robot_port,
            id=robot_id
        )
        self.robot = SO101Leader(self.robot_config)
        self.websocket: Optional[Any] = None
        self.action_sending_active = False
        
    async def start(self):
        """Start the remote leader agent."""
        logger.info(f"Starting remote leader agent: {self.agent_name}")
        logger.info(f"Location: {self.location}")
        logger.info(f"Robot port: {self.robot_port}")
        
        # Connect to robot
        try:
            self.robot.connect()
            logger.info("✅ Leader robot connected successfully")
        except Exception as e:
            logger.error(f"❌ Failed to connect to leader robot: {e}")
            return
            
        # Connect to central server
        await self.connect_to_central_server()
        
    async def connect_to_central_server(self):
        """Connect to the central teleoperation server."""
        while True:
            try:
                logger.info(f"Connecting to central server: {self.central_server_url}")
                
                self.websocket = await websockets.connect(self.central_server_url)
                
                # Register with central server as leader
                registration = {
                    "type": "register",
                    "name": self.agent_name,
                    "robot_type": "so101_leader", 
                    "location": self.location,
                    "robot_id": self.robot_id,
                    "is_leader": True  # Flag to identify as leader
                }
                
                await self.websocket.send(json.dumps(registration))
                
                # Wait for confirmation
                response = await self.websocket.recv()
                data = json.loads(response)
                
                if data.get("type") == "registered":
                    logger.info("✅ Successfully registered with central server as leader")
                    
                    # Start action sending and message handling
                    await self.handle_communication()
                    
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Connection to central server lost, reconnecting...")
                await asyncio.sleep(5)
            except Exception as e:
                logger.error(f"Error connecting to central server: {e}")
                await asyncio.sleep(5)
                
    async def handle_communication(self):
        """Handle communication with central server."""
        # Start ping loop
        ping_task = asyncio.create_task(self.ping_loop())
        
        # Start action sending loop
        action_task = asyncio.create_task(self.action_sending_loop())
        
        try:
            # Handle incoming messages
            async for message in self.websocket:
                data = json.loads(message)
                
                if data.get("type") == "start_action_stream":
                    logger.info("Received command to start sending actions")
                    self.action_sending_active = True
                    
                elif data.get("type") == "stop_action_stream":
                    logger.info("Received command to stop sending actions")
                    self.action_sending_active = False
                    
                elif data.get("type") == "pong":
                    logger.debug("Received pong from server")
                    
        except websockets.exceptions.ConnectionClosed:
            logger.warning("Lost connection to central server")
        finally:
            ping_task.cancel()
            action_task.cancel()
            
    async def action_sending_loop(self):
        """Send leader robot actions to central server."""
        while True:
            try:
                if self.action_sending_active and self.websocket:
                    # Get action from leader robot
                    try:
                        action = self.robot.get_action()
                        if action:
                            # Send action to central server
                            action_message = json.dumps({
                                "type": "leader_action",
                                "action": action,
                                "timestamp": asyncio.get_event_loop().time(),
                                "source": self.agent_name
                            })
                            
                            await self.websocket.send(action_message)
                            logger.debug(f"Sent leader action: {action}")
                    except Exception as e:
                        logger.error(f"Error getting/sending leader action: {e}")
                
                # Send at 30 Hz
                await asyncio.sleep(1/30)
                
            except Exception as e:
                logger.error(f"Error in action sending loop: {e}")
                await asyncio.sleep(0.1)
                
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
        self.action_sending_active = False
        if self.websocket:
            await self.websocket.close()
        if self.robot.is_connected:
            self.robot.disconnect()
        logger.info("Remote leader agent stopped")

async def main():
    """Run the remote leader agent."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Configure your remote leader
    config = {
        "robot_port": "/dev/tty.usbmodem585A0078841",  # Update this to match your leader robot
        "robot_id": "remote_leader_1",
        "agent_name": "control_station_leader", 
        "location": "Control Station Room A",
        "central_server_host": "lerobot-central-teleop-671396067800.us-central1.run.app",  # Cloud Run service URL
        "central_server_port": 443  # HTTPS port for Cloud Run
    }
    
    agent = RemoteLeaderAgent(**config)
    
    try:
        await agent.start()
        logger.info("Press Ctrl+C to stop...")
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await agent.stop()

if __name__ == "__main__":
    asyncio.run(main()) 