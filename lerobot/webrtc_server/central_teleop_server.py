#!/usr/bin/env python
"""
Central Teleoperation Server

Runs the main WebRTC server with leader robot and manages remote followers.
"""

import asyncio
import logging
import json
import websockets
from typing import Dict, Set, Any
from dataclasses import dataclass

from lerobot.webrtc_server.config.server_config import WebRTCServerConfig, RobotConnectionConfig
from lerobot.webrtc_server.server.webrtc_robot_server import WebRTCRobotServer

logger = logging.getLogger(__name__)

@dataclass
class RemoteFollower:
    name: str
    websocket: websockets.WebSocketServerProtocol
    robot_type: str
    location: str
    last_ping: float

class CentralTeleoperationServer:
    """Central server that manages leader robot and communicates with remote followers."""
    
    def __init__(self, leader_port: str, websocket_port: int = 8081):
        self.leader_port = leader_port
        self.websocket_port = websocket_port
        self.remote_followers: Dict[str, RemoteFollower] = {}
        self.teleoperation_active = False
        
        # Create WebRTC server for leader
        self.server_config = WebRTCServerConfig(
            host="0.0.0.0",
            port=8080,
            debug=True,
            enable_safety_limits=True,
            emergency_stop_enabled=True
        )
        
        # Add leader robot
        self.server_config.add_robot("leader", RobotConnectionConfig(
            robot_type="leader",
            robot_class="so101_leader",
            port=leader_port,
            id="central_leader"
        ))
        
        self.webrtc_server = WebRTCRobotServer(self.server_config)
        
    async def start(self):
        """Start the central server."""
        logger.info("Starting central teleoperation server...")
        
        # Start WebRTC server for leader
        await self.webrtc_server.start()
        
        # Start WebSocket server for remote followers
        # Create a wrapper function to properly handle the method binding
        async def websocket_handler(websocket):
            await self.handle_remote_follower(websocket)
        
        self.websocket_server = await websockets.serve(
            websocket_handler,
            "0.0.0.0", 
            self.websocket_port
        )
        
        # Start teleoperation loop
        asyncio.create_task(self.teleoperation_loop())
        
        logger.info(f"✅ Central server running:")
        logger.info(f"   WebRTC (leader): http://0.0.0.0:8080")
        logger.info(f"   WebSocket (followers): ws://0.0.0.0:{self.websocket_port}")
        
    async def handle_remote_follower(self, websocket):
        """Handle connections from remote follower agents."""
        try:
            logger.info(f"New remote follower connecting from {websocket.remote_address}")
            
            # Wait for registration message
            registration = await websocket.recv()
            data = json.loads(registration)
            
            if data.get("type") == "register":
                follower_name = data["name"]
                robot_type = data["robot_type"]
                location = data["location"]
                
                # Register the follower
                self.remote_followers[follower_name] = RemoteFollower(
                    name=follower_name,
                    websocket=websocket,
                    robot_type=robot_type,
                    location=location,
                    last_ping=asyncio.get_event_loop().time()
                )
                
                logger.info(f"✅ Registered remote follower: {follower_name} at {location}")
                
                # Send confirmation
                await websocket.send(json.dumps({
                    "type": "registered",
                    "message": f"Follower {follower_name} registered successfully"
                }))
                
                # Keep connection alive
                async for message in websocket:
                    data = json.loads(message)
                    if data.get("type") == "ping":
                        await websocket.send(json.dumps({"type": "pong"}))
                        self.remote_followers[follower_name].last_ping = asyncio.get_event_loop().time()
                        
        except websockets.exceptions.ConnectionClosed:
            # Remove follower on disconnect
            for name, follower in list(self.remote_followers.items()):
                if follower.websocket == websocket:
                    del self.remote_followers[name]
                    logger.info(f"❌ Remote follower {name} disconnected")
                    break
        except Exception as e:
            logger.error(f"Error handling remote follower: {e}")
            
    async def start_teleoperation(self):
        """Start teleoperation from leader to all remote followers."""
        try:
            # Only try to connect leader if it exists
            if "leader" in self.webrtc_server.robot_manager.robots:
                success = await self.webrtc_server.robot_manager.connect_robot("leader")
                if not success:
                    logger.warning("Failed to connect leader robot! Teleoperation will run without leader.")
                    # Continue anyway - we can still communicate with followers
                    
            self.teleoperation_active = True
            logger.info(f"🎮 Teleoperation started! Connected to {len(self.remote_followers)} remote followers")
            return True
        except Exception as e:
            logger.error(f"Error starting teleoperation: {e}")
            return False
        
    async def stop_teleoperation(self):
        """Stop teleoperation."""
        self.teleoperation_active = False
        
        # Send stop command to all followers
        stop_message = json.dumps({"type": "stop_teleoperation"})
        for follower in self.remote_followers.values():
            try:
                await follower.websocket.send(stop_message)
            except:
                pass
                
        logger.info("⏹️ Teleoperation stopped")
        
    async def teleoperation_loop(self):
        """Main teleoperation loop."""
        await asyncio.sleep(3)  # Wait for server to start
        
        while True:
            if not self.teleoperation_active or not self.remote_followers:
                await asyncio.sleep(0.1)
                continue
                
            try:
                # Check if we have a leader robot and it's connected
                leader_action = None
                if "leader" in self.webrtc_server.robot_manager.robots:
                    try:
                        leader_robot = self.webrtc_server.robot_manager.robots["leader"]
                        if leader_robot.is_connected:
                            # Get action from leader robot
                            leader_action = await self.webrtc_server.robot_manager.get_action("leader")
                        else:
                            logger.debug("Leader robot not connected, skipping action")
                    except Exception as e:
                        logger.debug(f"Error getting leader action: {e}")
                
                # If we have an action from leader, send it to followers
                if leader_action:
                    logger.debug(f"📤 Sending action to {len(self.remote_followers)} followers: {leader_action}")
                    
                    action_message = json.dumps({
                        "type": "action",
                        "action": leader_action,
                        "timestamp": asyncio.get_event_loop().time()
                    })
                    
                    # Send to all connected followers
                    disconnected_followers = []
                    for name, follower in self.remote_followers.items():
                        try:
                            await follower.websocket.send(action_message)
                        except websockets.exceptions.ConnectionClosed:
                            disconnected_followers.append(name)
                        except Exception as e:
                            logger.error(f"Error sending to {name}: {e}")
                    
                    # Clean up disconnected followers
                    for name in disconnected_followers:
                        del self.remote_followers[name]
                        logger.warning(f"Removed disconnected follower: {name}")
                
                # Control frequency (30 Hz)
                await asyncio.sleep(1/30)
                
            except Exception as e:
                logger.error(f"Error in teleoperation loop: {e}")
                await asyncio.sleep(0.1)
                
    def get_status(self):
        """Get server status."""
        return {
            "teleoperation_active": self.teleoperation_active,
            "leader_connected": self.webrtc_server.robot_manager.robots.get("leader", {}).get("is_connected", False),
            "remote_followers": {
                name: {
                    "location": follower.location,
                    "robot_type": follower.robot_type,
                    "last_ping": follower.last_ping
                }
                for name, follower in self.remote_followers.items()
            }
        }

async def main():
    """Run the central teleoperation server."""
    logging.basicConfig(
        level=logging.DEBUG,  # Changed to DEBUG for better troubleshooting
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Configure your leader robot port
    LEADER_PORT = "/dev/tty.usbmodem585A0078841"  # Update this
    
    server = CentralTeleoperationServer(LEADER_PORT)
    
    try:
        await server.start()
        
        # Auto-start teleoperation after a delay
        await asyncio.sleep(5)
        await server.start_teleoperation()
        
        logger.info("Press Ctrl+C to stop...")
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        await server.stop_teleoperation()

if __name__ == "__main__":
    asyncio.run(main())