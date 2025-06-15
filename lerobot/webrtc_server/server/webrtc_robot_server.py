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

import asyncio
import json
import logging
import time
from typing import Dict, Any, Optional
from datetime import datetime

# Web server imports
from aiohttp import web, WSMsgType
from aiohttp_cors import setup as cors_setup, ResourceOptions

from ..config.server_config import WebRTCServerConfig
from ..utils.robot_manager import RobotManager
from ..utils.action_validator import ActionValidator

logger = logging.getLogger(__name__)


class WebRTCRobotServer:
    """
    WebRTC server for remote robot control.
    
    Provides real-time communication for sending actions
    to both leader and follower robots over the web.
    """
    
    def __init__(self, config: WebRTCServerConfig):
        """Initialize the WebRTC robot server."""
        self.config = config
        self.app = web.Application()
        self.robot_manager = RobotManager(config)
        self.action_validator = ActionValidator(config.enable_safety_limits)
        
        # Statistics
        self.stats = {
            "total_connections": 0,
            "actions_sent": 0,
            "errors": 0,
            "start_time": datetime.now(),
        }
        
        logger.info("WebRTC Robot Server initialized")
        self._setup_routes()
        self._setup_cors()
    
    def _setup_routes(self) -> None:
        """Setup HTTP routes."""
        
        # Main interface
        self.app.router.add_get("/", self._handle_index)
        
        # API routes
        self.app.router.add_get("/api/robots", self._handle_list_robots)
        self.app.router.add_get("/api/robots/{robot_name}/status", self._handle_robot_status)
        self.app.router.add_post("/api/robots/{robot_name}/connect", self._handle_connect_robot)
        self.app.router.add_post("/api/robots/{robot_name}/disconnect", self._handle_disconnect_robot)
        self.app.router.add_post("/api/robots/{robot_name}/action", self._handle_send_action)
        self.app.router.add_get("/api/robots/{robot_name}/action", self._handle_get_action)
        self.app.router.add_post("/api/emergency_stop", self._handle_emergency_stop)
        self.app.router.add_get("/api/status", self._handle_server_status)
        
        # WebSocket for real-time communication
        self.app.router.add_get("/ws", self._handle_websocket)
        
        logger.info("Routes configured")
    
    def _setup_cors(self) -> None:
        """Setup CORS for the web application."""
        if self.config.enable_cors:
            cors = cors_setup(self.app, defaults={
                "*": ResourceOptions(
                    allow_credentials=True,
                    expose_headers="*",
                    allow_headers="*",
                    allow_methods="*"
                )
            })
            
            for route in list(self.app.router.routes()):
                cors.add(route)
            
            logger.info("CORS configured")
    
    async def _handle_index(self, request: web.Request) -> web.Response:
        """Serve the main web interface."""
        html_content = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>LeRobot WebRTC Controller</title>
            <style>
                body { font-family: Arial, sans-serif; margin: 20px; }
                .robot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 20px; }
                .robot-card { border: 1px solid #ccc; padding: 20px; border-radius: 8px; }
                .status-connected { color: green; }
                .status-disconnected { color: red; }
                button { margin: 5px; padding: 10px; }
                .action-controls { margin-top: 15px; }
                input[type="number"] { width: 80px; margin: 2px; }
            </style>
        </head>
        <body>
            <h1>LeRobot WebRTC Controller</h1>
            <div id="status"></div>
            <div id="robots" class="robot-grid"></div>
            
            <script>
                async function loadRobots() {
                    try {
                        const response = await fetch('/api/robots');
                        const robots = await response.json();
                        displayRobots(robots);
                    } catch (error) {
                        console.error('Error loading robots:', error);
                    }
                }
                
                function displayRobots(robots) {
                    const container = document.getElementById('robots');
                    container.innerHTML = '';
                    
                    for (const [name, type] of Object.entries(robots)) {
                        const card = document.createElement('div');
                        card.className = 'robot-card';
                        card.innerHTML = `
                            <h3>${name}</h3>
                            <p>Type: ${type}</p>
                            <div id="status-${name}" class="status-disconnected">Disconnected</div>
                            <button onclick="connectRobot('${name}')">Connect</button>
                            <button onclick="disconnectRobot('${name}')">Disconnect</button>
                            <div class="action-controls">
                                <h4>Send Action:</h4>
                                <input type="number" id="dx-${name}" placeholder="delta_x" step="0.1" value="0.1">
                                <input type="number" id="dy-${name}" placeholder="delta_y" step="0.1" value="0.0">
                                <input type="number" id="dz-${name}" placeholder="delta_z" step="0.1" value="0.0">
                                <button onclick="sendAction('${name}')">Send</button>
                            </div>
                        `;
                        container.appendChild(card);
                    }
                }
                
                async function connectRobot(name) {
                    try {
                        const response = await fetch(`/api/robots/${name}/connect`, { method: 'POST' });
                        const result = await response.json();
                        if (result.success) {
                            document.getElementById(`status-${name}`).textContent = 'Connected';
                            document.getElementById(`status-${name}`).className = 'status-connected';
                        }
                    } catch (error) {
                        console.error('Error connecting robot:', error);
                    }
                }
                
                async function disconnectRobot(name) {
                    try {
                        const response = await fetch(`/api/robots/${name}/disconnect`, { method: 'POST' });
                        const result = await response.json();
                        if (result.success) {
                            document.getElementById(`status-${name}`).textContent = 'Disconnected';
                            document.getElementById(`status-${name}`).className = 'status-disconnected';
                        }
                    } catch (error) {
                        console.error('Error disconnecting robot:', error);
                    }
                }
                
                async function sendAction(name) {
                    try {
                        const dx = parseFloat(document.getElementById(`dx-${name}`).value) || 0.0;
                        const dy = parseFloat(document.getElementById(`dy-${name}`).value) || 0.0;
                        const dz = parseFloat(document.getElementById(`dz-${name}`).value) || 0.0;
                        
                        const action = { "delta_x": dx, "delta_y": dy, "delta_z": dz };
                        const response = await fetch(`/api/robots/${name}/action`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(action)
                        });
                        const result = await response.json();
                        console.log('Action result:', result);
                    } catch (error) {
                        console.error('Error sending action:', error);
                    }
                }
                
                // Load robots on page load
                loadRobots();
                
                // Refresh status every 2 seconds
                setInterval(loadRobots, 2000);
            </script>
        </body>
        </html>
        """
        return web.Response(text=html_content, content_type="text/html")
    
    async def _handle_list_robots(self, request: web.Request) -> web.Response:
        """List all configured robots."""
        try:
            robots = self.robot_manager.list_robots()
            return web.json_response(robots)
        except Exception as e:
            logger.error(f"Error listing robots: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def _handle_robot_status(self, request: web.Request) -> web.Response:
        """Get status of a specific robot."""
        robot_name = request.match_info["robot_name"]
        
        try:
            status = await self.robot_manager.get_robot_status(robot_name)
            return web.json_response(status)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=404)
        except Exception as e:
            logger.error(f"Error getting robot status: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def _handle_connect_robot(self, request: web.Request) -> web.Response:
        """Connect to a specific robot."""
        robot_name = request.match_info["robot_name"]
        
        try:
            data = await request.json() if request.content_type == "application/json" else {}
            calibrate = data.get("calibrate", True)
            
            success = await self.robot_manager.connect_robot(robot_name, calibrate)
            return web.json_response({"success": success, "robot": robot_name})
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=404)
        except Exception as e:
            logger.error(f"Error connecting robot: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def _handle_disconnect_robot(self, request: web.Request) -> web.Response:
        """Disconnect from a specific robot."""
        robot_name = request.match_info["robot_name"]
        
        try:
            success = await self.robot_manager.disconnect_robot(robot_name)
            return web.json_response({"success": success, "robot": robot_name})
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=404)
        except Exception as e:
            logger.error(f"Error disconnecting robot: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def _handle_send_action(self, request: web.Request) -> web.Response:
        """Send an action to a specific robot."""
        robot_name = request.match_info["robot_name"]
        
        try:
            action = await request.json()
            
            # Get robot configuration for validation
            robot_config = self.config.get_robot_config(robot_name)
            if not robot_config:
                return web.json_response({"error": f"Robot {robot_name} not configured"}, status=404)
            
            # Validate action
            is_valid, error_msg, sanitized_action = self.action_validator.validate_action(
                robot_name, robot_config.robot_class, action, robot_config.robot_type
            )
            
            if not is_valid:
                return web.json_response({"error": f"Invalid action: {error_msg}"}, status=400)
            
            # Send action to robot
            result = await self.robot_manager.send_action(robot_name, sanitized_action)
            
            # Update statistics
            self.stats["actions_sent"] += 1
            
            return web.json_response({
                "success": True, 
                "robot": robot_name, 
                "action_sent": result,
                "original_action": action
            })
            
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=404)
        except Exception as e:
            logger.error(f"Error sending action: {e}")
            self.stats["errors"] += 1
            return web.json_response({"error": str(e)}, status=500)
    
    async def _handle_get_action(self, request: web.Request) -> web.Response:
        """Get action from a leader robot."""
        robot_name = request.match_info["robot_name"]
        
        try:
            action = await self.robot_manager.get_action(robot_name)
            return web.json_response({"robot": robot_name, "action": action})
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=404)
        except Exception as e:
            logger.error(f"Error getting action: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def _handle_emergency_stop(self, request: web.Request) -> web.Response:
        """Emergency stop all robots."""
        try:
            results = await self.robot_manager.emergency_stop_all()
            return web.json_response({"success": True, "results": results})
        except Exception as e:
            logger.error(f"Error during emergency stop: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def _handle_server_status(self, request: web.Request) -> web.Response:
        """Get server status information."""
        try:
            robot_status = await self.robot_manager.get_all_robot_status()
            
            status = {
                "server": {
                    "running": True,
                    "stats": self.stats.copy(),
                    "config": {
                        "host": self.config.host,
                        "port": self.config.port,
                        "safety_limits": self.config.enable_safety_limits,
                        "emergency_stop": self.config.emergency_stop_enabled,
                    }
                },
                "robots": robot_status
            }
            
            return web.json_response(status)
        except Exception as e:
            logger.error(f"Error getting server status: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    async def _handle_websocket(self, request: web.Request) -> web.WebSocketResponse:
        """Handle WebSocket connections for real-time communication."""
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        logger.info("WebSocket connection established")
        
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                try:
                    data = json.loads(msg.data)
                    response = await self._handle_ws_message(data)
                    if response:
                        await ws.send_str(json.dumps(response))
                except Exception as e:
                    logger.error(f"Error handling WebSocket message: {e}")
                    await ws.send_str(json.dumps({"error": str(e)}))
            elif msg.type == WSMsgType.ERROR:
                logger.error(f"WebSocket error: {ws.exception()}")
                break
        
        logger.info("WebSocket connection closed")
        return ws
    
    async def _handle_ws_message(self, data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Handle WebSocket messages."""
        message_type = data.get("type")
        
        if message_type == "ping":
            return {"type": "pong", "timestamp": time.time()}
        elif message_type == "robot_action":
            robot_name = data.get("robot")
            action = data.get("action")
            
            if not robot_name or not action:
                return {"type": "error", "message": "Missing robot name or action"}
            
            try:
                result = await self._process_robot_action(robot_name, action)
                return {
                    "type": "action_result",
                    "robot": robot_name,
                    "success": True,
                    "result": result
                }
            except Exception as e:
                return {
                    "type": "action_result", 
                    "robot": robot_name,
                    "success": False,
                    "error": str(e)
                }
        else:
            return {"type": "error", "message": f"Unknown message type: {message_type}"}
    
    async def _process_robot_action(self, robot_name: str, action: Dict[str, Any]) -> Dict[str, Any]:
        """Process robot action from WebSocket."""
        
        # Get robot configuration
        robot_config = self.config.get_robot_config(robot_name)
        if not robot_config:
            raise ValueError(f"Robot {robot_name} not configured")
        
        # Validate action
        is_valid, error_msg, sanitized_action = self.action_validator.validate_action(
            robot_name, robot_config.robot_class, action, robot_config.robot_type
        )
        
        if not is_valid:
            raise ValueError(f"Invalid action: {error_msg}")
        
        # Send action to robot
        result = await self.robot_manager.send_action(robot_name, sanitized_action)
        
        # Update statistics
        self.stats["actions_sent"] += 1
        
        return result
    
    async def start(self) -> None:
        """Start the WebRTC robot server."""
        logger.info(f"Starting WebRTC Robot Server on {self.config.host}:{self.config.port}")
        
        # Initialize robots
        await self.robot_manager.initialize_robots()
        
        # Start web server
        runner = web.AppRunner(self.app, access_log=logger)
        await runner.setup()
        
        site = web.TCPSite(runner, self.config.host, self.config.port)
        await site.start()
        
        logger.info(f"WebRTC Robot Server started at http://{self.config.host}:{self.config.port}")
        logger.info(f"Configured robots: {list(self.config.robots.keys())}")
    
    async def stop(self) -> None:
        """Stop the WebRTC robot server."""
        logger.info("Stopping WebRTC Robot Server...")
        await self.robot_manager.cleanup()
        logger.info("WebRTC Robot Server stopped") 