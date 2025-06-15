#!/usr/bin/env python
"""
Cloud Central Teleoperation Server

Standalone cloud-optimized version for Google Cloud Run.
"""

import asyncio
import logging
import json
import websockets
import os
from typing import Dict, Any
from dataclasses import dataclass

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

class CloudCentralTeleoperationServer:
    """Cloud Run optimized central teleoperation server."""
    
    def __init__(self):
        # Get configuration from environment variables
        self.websocket_port = int(os.environ.get('PORT', 8081))
        self.remote_followers: Dict[str, RemoteFollower] = {}
        self.remote_leaders: Dict[str, RemoteLeader] = {}
        self.teleoperation_active = False
        
    async def start(self):
        """Start the cloud-optimized central server."""
        logger.info("Starting cloud central teleoperation server...")
        
        # Start WebSocket server for remote robots (leaders and followers)
        async def websocket_handler(websocket):
            await self.handle_remote_robot(websocket)
        
        # Bind to all interfaces and use Cloud Run PORT
        self.websocket_server = await websockets.serve(
            websocket_handler,
            "0.0.0.0", 
            self.websocket_port
        )
        
        # Start teleoperation loop
        asyncio.create_task(self.teleoperation_loop())
        
        logger.info(f"✅ Cloud central server running on port {self.websocket_port}")
        logger.info(f"   WebSocket endpoint: ws://0.0.0.0:{self.websocket_port}")
        
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
            # Remove robot on disconnect
            for name, leader in list(self.remote_leaders.items()):
                if leader.websocket == websocket:
                    del self.remote_leaders[name]
                    logger.info(f"❌ Remote leader {name} disconnected")
                    break
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
        self.teleoperation_active = True
        leaders_count = len(self.remote_leaders)
        logger.info(f"🎮 Teleoperation started! Connected to {leaders_count} leader(s) and {len(self.remote_followers)} follower(s)")
        return True
        
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
                # Get action from remote leaders
                leader_action = None
                if self.remote_leaders:
                    for leader_name, leader in self.remote_leaders.items():
                        if leader.last_action:
                            leader_action = leader.last_action
                            logger.debug(f"Using action from remote leader {leader_name}")
                            break
                
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
        return {
            "teleoperation_active": self.teleoperation_active,
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
    """Run the cloud central teleoperation server."""
    # Configure logging for cloud environment
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    logger.info("🚀 Starting Cloud Run Central Teleoperation Server")
    logger.info(f"Environment: PORT={os.environ.get('PORT', 'not set')}")
    
    server = CloudCentralTeleoperationServer()
    
    try:
        await server.start()
        
        # Auto-start teleoperation after a delay
        await asyncio.sleep(5)
        await server.start_teleoperation()
        
        logger.info("✅ Cloud server ready - waiting for robot connections...")
        logger.info("Connect your remote leader and follower agents to this server")
        
        # Keep the server running
        await asyncio.Event().wait()
        
    except KeyboardInterrupt:
        logger.info("Shutting down cloud server...")
        await server.stop_teleoperation()
    except Exception as e:
        logger.error(f"Error in cloud server: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main()) 