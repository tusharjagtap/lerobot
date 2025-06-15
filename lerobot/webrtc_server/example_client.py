#!/usr/bin/env python

# Copyright 2025 The HuggingFace Inc. team. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Example WebRTC Server Client

This script demonstrates how to interact with the WebRTC Robot Server
using both HTTP API and WebSocket communication.

Usage:
    python example_client.py --server http://localhost:8080
    python example_client.py --robot so101_follower --demo circle
    python example_client.py --help
"""

import asyncio
import json
import time
import argparse
import logging
import math
from typing import Dict, Any, List

try:
    import aiohttp
    import websockets
    DEPS_AVAILABLE = True
except ImportError:
    DEPS_AVAILABLE = False

logger = logging.getLogger(__name__)


class WebRTCRobotClient:
    """Client for interacting with WebRTC Robot Server."""
    
    def __init__(self, server_url: str):
        """Initialize client with server URL."""
        self.server_url = server_url.rstrip('/')
        self.api_url = f"{self.server_url}/api"
        self.ws_url = self.server_url.replace('http', 'ws') + '/ws'
        self.session = None
        self.websocket = None
        
        logger.info(f"WebRTC Robot Client initialized for {server_url}")
    
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.websocket:
            await self.websocket.close()
        if self.session:
            await self.session.close()
    
    async def get_server_status(self) -> Dict[str, Any]:
        """Get server status information."""
        async with self.session.get(f"{self.api_url}/status") as response:
            return await response.json()
    
    async def list_robots(self) -> Dict[str, str]:
        """List all available robots."""
        async with self.session.get(f"{self.api_url}/robots") as response:
            return await response.json()
    
    async def get_robot_status(self, robot_name: str) -> Dict[str, Any]:
        """Get status of a specific robot."""
        async with self.session.get(f"{self.api_url}/robots/{robot_name}/status") as response:
            return await response.json()
    
    async def connect_robot(self, robot_name: str, calibrate: bool = True) -> bool:
        """Connect to a robot."""
        payload = {"calibrate": calibrate}
        async with self.session.post(f"{self.api_url}/robots/{robot_name}/connect", json=payload) as response:
            result = await response.json()
            return result.get("success", False)
    
    async def disconnect_robot(self, robot_name: str) -> bool:
        """Disconnect from a robot."""
        async with self.session.post(f"{self.api_url}/robots/{robot_name}/disconnect") as response:
            result = await response.json()
            return result.get("success", False)
    
    async def send_action(self, robot_name: str, action: Dict[str, Any]) -> Dict[str, Any]:
        """Send an action to a robot via HTTP API."""
        async with self.session.post(f"{self.api_url}/robots/{robot_name}/action", json=action) as response:
            return await response.json()
    
    async def get_action(self, robot_name: str) -> Dict[str, Any]:
        """Get action from a leader robot."""
        async with self.session.get(f"{self.api_url}/robots/{robot_name}/action") as response:
            return await response.json()
    
    async def emergency_stop(self) -> Dict[str, Any]:
        """Trigger emergency stop for all robots."""
        async with self.session.post(f"{self.api_url}/emergency_stop") as response:
            return await response.json()
    
    async def connect_websocket(self) -> None:
        """Connect to WebSocket for real-time communication."""
        self.websocket = await websockets.connect(self.ws_url)
        logger.info("WebSocket connected")
    
    async def send_websocket_action(self, robot_name: str, action: Dict[str, Any]) -> Dict[str, Any]:
        """Send action via WebSocket."""
        if not self.websocket:
            await self.connect_websocket()
        
        message = {
            "type": "robot_action",
            "robot": robot_name,
            "action": action
        }
        
        await self.websocket.send(json.dumps(message))
        
        # Wait for response
        response = await self.websocket.recv()
        return json.loads(response)
    
    async def ping_websocket(self) -> float:
        """Ping WebSocket to measure latency."""
        if not self.websocket:
            await self.connect_websocket()
        
        start_time = time.time()
        
        ping_message = {"type": "ping"}
        await self.websocket.send(json.dumps(ping_message))
        
        response = await self.websocket.recv()
        data = json.loads(response)
        
        if data.get("type") == "pong":
            return time.time() - start_time
        else:
            raise ValueError(f"Unexpected response: {data}")


async def demo_basic_api(client: WebRTCRobotClient, robot_name: str) -> None:
    """Demonstrate basic API usage."""
    logger.info("=== Basic API Demo ===")
    
    # Get server status
    status = await client.get_server_status()
    logger.info(f"Server status: {status['server']['running']}")
    
    # List robots
    robots = await client.list_robots()
    logger.info(f"Available robots: {list(robots.keys())}")
    
    if robot_name not in robots:
        logger.error(f"Robot {robot_name} not found in server configuration")
        return
    
    # Connect to robot
    logger.info(f"Connecting to {robot_name}...")
    success = await client.connect_robot(robot_name)
    if not success:
        logger.error(f"Failed to connect to {robot_name}")
        return
    
    logger.info(f"Successfully connected to {robot_name}")
    
    # Get robot status
    robot_status = await client.get_robot_status(robot_name)
    logger.info(f"Robot status: {robot_status}")
    
    # Send test action
    test_action = {"delta_x": 0.1, "delta_y": 0.0, "delta_z": 0.0}
    logger.info(f"Sending test action: {test_action}")
    
    result = await client.send_action(robot_name, test_action)
    if result.get("success"):
        logger.info("Action sent successfully")
    else:
        logger.error(f"Action failed: {result.get('error')}")
    
    # Disconnect
    await client.disconnect_robot(robot_name)
    logger.info(f"Disconnected from {robot_name}")


async def demo_websocket_communication(client: WebRTCRobotClient, robot_name: str) -> None:
    """Demonstrate WebSocket communication."""
    logger.info("=== WebSocket Demo ===")
    
    # Connect WebSocket
    await client.connect_websocket()
    
    # Test ping
    latency = await client.ping_websocket()
    logger.info(f"WebSocket latency: {latency*1000:.1f}ms")
    
    # Connect robot
    success = await client.connect_robot(robot_name)
    if not success:
        logger.error(f"Failed to connect to {robot_name}")
        return
    
    # Send actions via WebSocket
    actions = [
        {"delta_x": 0.1, "delta_y": 0.0, "delta_z": 0.0},
        {"delta_x": 0.0, "delta_y": 0.1, "delta_z": 0.0},
        {"delta_x": 0.0, "delta_y": 0.0, "delta_z": 0.1},
        {"delta_x": 0.0, "delta_y": 0.0, "delta_z": 0.0},
    ]
    
    for i, action in enumerate(actions):
        logger.info(f"Sending WebSocket action {i+1}: {action}")
        
        start_time = time.time()
        response = await client.send_websocket_action(robot_name, action)
        response_time = time.time() - start_time
        
        if response.get("success"):
            logger.info(f"Action completed in {response_time*1000:.1f}ms")
        else:
            logger.error(f"Action failed: {response.get('error')}")
        
        await asyncio.sleep(0.5)  # Small delay between actions
    
    # Disconnect
    await client.disconnect_robot(robot_name)


async def demo_circle_movement(client: WebRTCRobotClient, robot_name: str) -> None:
    """Demonstrate circular movement pattern."""
    logger.info("=== Circle Movement Demo ===")
    
    # Connect robot
    success = await client.connect_robot(robot_name)
    if not success:
        logger.error(f"Failed to connect to {robot_name}")
        return
    
    # Connect WebSocket for low latency
    await client.connect_websocket()
    
    # Generate circle movement
    radius = 0.05  # Small radius for safety
    steps = 20
    duration = 5.0  # 5 seconds for full circle
    
    logger.info(f"Executing circular movement (radius={radius}, {steps} steps)")
    
    for i in range(steps):
        angle = 2 * math.pi * i / steps
        
        action = {
            "delta_x": radius * math.cos(angle) / steps,
            "delta_y": radius * math.sin(angle) / steps,
            "delta_z": 0.0
        }
        
        try:
            response = await client.send_websocket_action(robot_name, action)
            if not response.get("success"):
                logger.error(f"Circle step {i} failed: {response.get('error')}")
                break
        except Exception as e:
            logger.error(f"Error in circle step {i}: {e}")
            break
        
        await asyncio.sleep(duration / steps)
    
    # Return to center
    center_action = {"delta_x": 0.0, "delta_y": 0.0, "delta_z": 0.0}
    await client.send_websocket_action(robot_name, center_action)
    
    logger.info("Circle movement completed")
    
    # Disconnect
    await client.disconnect_robot(robot_name)


async def demo_leader_follower(client: WebRTCRobotClient, leader_name: str, follower_name: str) -> None:
    """Demonstrate leader-follower control."""
    logger.info("=== Leader-Follower Demo ===")
    
    # Connect both robots
    leader_success = await client.connect_robot(leader_name)
    follower_success = await client.connect_robot(follower_name)
    
    if not (leader_success and follower_success):
        logger.error("Failed to connect to both robots")
        return
    
    logger.info("Both robots connected, starting leader-follower demo")
    
    # Read from leader and send to follower
    for i in range(10):
        try:
            # Get action from leader
            leader_response = await client.get_action(leader_name)
            leader_action = leader_response.get("action", {})
            
            if leader_action:
                # Convert leader position to follower action
                # This is a simplified conversion - real implementation would need
                # proper kinematics and calibration
                follower_action = {
                    "delta_x": 0.01,  # Small test movement
                    "delta_y": 0.0,
                    "delta_z": 0.0
                }
                
                # Send to follower
                follower_response = await client.send_action(follower_name, follower_action)
                
                logger.info(f"Step {i+1}: Leader action → Follower action")
                logger.debug(f"Leader: {leader_action}")
                logger.debug(f"Follower result: {follower_response.get('success')}")
            
            await asyncio.sleep(0.1)  # 10Hz control loop
            
        except Exception as e:
            logger.error(f"Error in leader-follower step {i}: {e}")
            break
    
    # Disconnect both robots
    await client.disconnect_robot(leader_name)
    await client.disconnect_robot(follower_name)
    
    logger.info("Leader-follower demo completed")


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="WebRTC Robot Server Example Client")
    
    parser.add_argument(
        "--server",
        default="http://localhost:8080",
        help="WebRTC server URL (default: http://localhost:8080)"
    )
    
    parser.add_argument(
        "--robot",
        default="so101_follower",
        help="Robot name to use for demos (default: so101_follower)"
    )
    
    parser.add_argument(
        "--demo",
        choices=["basic", "websocket", "circle", "leader_follower"],
        default="basic",
        help="Demo to run (default: basic)"
    )
    
    parser.add_argument(
        "--leader",
        help="Leader robot name (for leader_follower demo)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Check dependencies
    if not DEPS_AVAILABLE:
        logger.error("Missing dependencies. Please install:")
        logger.error('  pip install -e ".[webrtc]"')
        logger.error("  Or: pip install aiohttp websockets")
        return
    
    # Run demo
    async with WebRTCRobotClient(args.server) as client:
        try:
            if args.demo == "basic":
                await demo_basic_api(client, args.robot)
            elif args.demo == "websocket":
                await demo_websocket_communication(client, args.robot)
            elif args.demo == "circle":
                await demo_circle_movement(client, args.robot)
            elif args.demo == "leader_follower":
                if not args.leader:
                    logger.error("--leader required for leader_follower demo")
                    return
                await demo_leader_follower(client, args.leader, args.robot)
            
        except Exception as e:
            logger.error(f"Demo failed: {e}")
            
            # Try emergency stop in case of error
            try:
                await client.emergency_stop()
                logger.info("Emergency stop executed")
            except:
                pass


if __name__ == "__main__":
    asyncio.run(main()) 