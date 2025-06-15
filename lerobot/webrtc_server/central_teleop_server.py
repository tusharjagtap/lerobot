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
    websocket: Any
    robot_type: str
    location: str
    last_ping: float

@dataclass
class RemoteLeader:
    name: str
    websocket: Any
    robot_type: str
    location: str
    last_ping: float
    last_action: Any = None

class CentralTeleoperationServer:
    """Central server that manages leader robot and communicates with remote followers."""
    
    def __init__(self, leader_port: str = None, websocket_port: int = 8081):
        self.leader_port = leader_port
        self.websocket_port = websocket_port
        self.remote_followers: Dict[str, RemoteFollower] = {}
        self.remote_leaders: Dict[str, RemoteLeader] = {}
        self.teleoperation_active = False
        
        # Create WebRTC server for leader
        self.server_config = WebRTCServerConfig(
            host="0.0.0.0",
            port=8080,
            debug=True,
            enable_safety_limits=True,
            emergency_stop_enabled=True
        )
        
        # Add leader robot only if local leader port is provided
        if leader_port:
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
        
        # Start WebSocket server for remote robots (leaders and followers)
        # Create a wrapper function to properly handle the method binding
        async def websocket_handler(websocket):
            await self.handle_remote_robot(websocket)
        
        self.websocket_server = await websockets.serve(
            websocket_handler,
            "0.0.0.0", 
            self.websocket_port
        )
        
        # Start teleoperation loop
        asyncio.create_task(self.teleoperation_loop())
        
        logger.info(f"✅ Central server running:")
        if self.leader_port:
            logger.info(f"   WebRTC (local leader): http://0.0.0.0:8080")
        else:
            logger.info(f"   WebRTC (status only): http://0.0.0.0:8080")
        logger.info(f"   WebSocket (remote robots): ws://0.0.0.0:{self.websocket_port}")
        
    async def handle_remote_robot(self, websocket):
        """Handle connections from remote robot agents (leaders and followers)."""
        try:
            logger.info(f"New remote robot connecting from {websocket.remote_address}")
            
            # Wait for registration message
            registration = await websocket.recv()
            data = json.loads(registration)
            
            if data.get("type") == "register":
                robot_name = data["name"]
                robot_type = data["robot_type"]
                location = data["location"]
                is_leader = data.get("is_leader", False)
                
                if is_leader:
                    # Register as leader
                    self.remote_leaders[robot_name] = RemoteLeader(
                        name=robot_name,
                        websocket=websocket,
                        robot_type=robot_type,
                        location=location,
                        last_ping=asyncio.get_event_loop().time()
                    )
                    
                    logger.info(f"✅ Registered remote leader: {robot_name} at {location}")
                    
                    # Send confirmation
                    await websocket.send(json.dumps({
                        "type": "registered",
                        "message": f"Leader {robot_name} registered successfully"
                    }))
                    
                    # Start action streaming automatically for leaders
                    await websocket.send(json.dumps({"type": "start_action_stream"}))
                    
                    # Handle leader communication
                    await self.handle_leader_communication(websocket, robot_name)
                    
                else:
                    # Register as follower
                    self.remote_followers[robot_name] = RemoteFollower(
                        name=robot_name,
                        websocket=websocket,
                        robot_type=robot_type,
                        location=location,
                        last_ping=asyncio.get_event_loop().time()
                    )
                    
                    logger.info(f"✅ Registered remote follower: {robot_name} at {location}")
                    
                    # Send confirmation
                    await websocket.send(json.dumps({
                        "type": "registered",
                        "message": f"Follower {robot_name} registered successfully"
                    }))
                    
                    # Handle follower communication
                    await self.handle_follower_communication(websocket, robot_name)
                        
        except websockets.exceptions.ConnectionClosed:
            # Remove follower on disconnect
            for name, follower in list(self.remote_followers.items()):
                if follower.websocket == websocket:
                    del self.remote_followers[name]
                    logger.info(f"❌ Remote follower {name} disconnected")
                    break
        except Exception as e:
            logger.error(f"Error handling remote robot: {e}")
            
    async def handle_leader_communication(self, websocket, leader_name):
        """Handle communication with a remote leader robot."""
        try:
            async for message in websocket:
                data = json.loads(message)
                
                if data.get("type") == "leader_action":
                    # Store the latest action from leader
                    if leader_name in self.remote_leaders:
                        self.remote_leaders[leader_name].last_action = data["action"]
                        logger.debug(f"Received action from leader {leader_name}: {data['action']}")
                        
                elif data.get("type") == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
                    self.remote_leaders[leader_name].last_ping = asyncio.get_event_loop().time()
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Leader {leader_name} disconnected")
            if leader_name in self.remote_leaders:
                del self.remote_leaders[leader_name]
        except Exception as e:
            logger.error(f"Error in leader communication for {leader_name}: {e}")
            
    async def handle_follower_communication(self, websocket, follower_name):
        """Handle communication with a remote follower robot."""
        try:
            async for message in websocket:
                data = json.loads(message)
                
                if data.get("type") == "ping":
                    await websocket.send(json.dumps({"type": "pong"}))
                    self.remote_followers[follower_name].last_ping = asyncio.get_event_loop().time()
                    
        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Follower {follower_name} disconnected")
            if follower_name in self.remote_followers:
                del self.remote_followers[follower_name]
        except Exception as e:
            logger.error(f"Error in follower communication for {follower_name}: {e}")
            
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
            leaders_count = len(self.remote_leaders) + (1 if "leader" in self.webrtc_server.robot_manager.robots and self.webrtc_server.robot_manager.robots["leader"].is_connected else 0)
            logger.info(f"🎮 Teleoperation started! Connected to {leaders_count} leader(s) and {len(self.remote_followers)} follower(s)")
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
                # Get action from leader (prioritize remote leaders over local)
                leader_action = None
                
                # First, try to get action from remote leaders
                if self.remote_leaders:
                    for leader_name, leader in self.remote_leaders.items():
                        if leader.last_action:
                            leader_action = leader.last_action
                            logger.debug(f"Using action from remote leader {leader_name}")
                            break
                
                # If no remote leader action, try local leader
                if not leader_action and "leader" in self.webrtc_server.robot_manager.robots:
                    try:
                        leader_robot = self.webrtc_server.robot_manager.robots["leader"]
                        if leader_robot.is_connected:
                            # Get action from local leader robot
                            leader_action = await self.webrtc_server.robot_manager.get_action("leader")
                            logger.debug("Using action from local leader")
                        else:
                            logger.debug("Local leader robot not connected, skipping action")
                    except Exception as e:
                        logger.debug(f"Error getting local leader action: {e}")
                
                # If we have an action from any leader, send it to followers
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
        local_leader_connected = False
        if "leader" in self.webrtc_server.robot_manager.robots:
            local_leader_connected = self.webrtc_server.robot_manager.robots.get("leader", {}).get("is_connected", False)
            
        return {
            "teleoperation_active": self.teleoperation_active,
            "local_leader_connected": local_leader_connected,
            "remote_leaders": {
                name: {
                    "location": leader.location,
                    "robot_type": leader.robot_type,
                    "last_ping": leader.last_ping,
                    "has_recent_action": leader.last_action is not None
                }
                for name, leader in self.remote_leaders.items()
            },
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
    
    # Configure your leader robot port (set to None for remote-only leaders)
    LEADER_PORT = None  # Set to "/dev/tty.usbmodem585A0078841" for local leader
    
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