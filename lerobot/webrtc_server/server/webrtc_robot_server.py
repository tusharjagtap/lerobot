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
        self.app.router.add_get("/api/robots/{robot_name}/position", self._handle_get_position)
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
                body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
                .robot-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(350px, 1fr)); gap: 20px; }
                .robot-card { 
                    border: 1px solid #ccc; 
                    padding: 20px; 
                    border-radius: 8px; 
                    background: white;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }
                .robot-card h3 { margin-top: 0; color: #333; }
                .status-connected { 
                    color: #28a745; 
                    font-weight: bold; 
                    font-size: 1.1em;
                    padding: 5px 10px;
                    background: #d4edda;
                    border-radius: 4px;
                    display: inline-block;
                }
                .status-disconnected { 
                    color: #dc3545; 
                    font-weight: bold; 
                    font-size: 1.1em;
                    padding: 5px 10px;
                    background: #f8d7da;
                    border-radius: 4px;
                    display: inline-block;
                }
                button { 
                    margin: 5px; 
                    padding: 10px 15px; 
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                    background: #007bff;
                    color: white;
                }
                button:hover { background: #0056b3; }
                .action-controls { 
                    margin-top: 15px; 
                    padding-top: 15px;
                    border-top: 1px solid #eee;
                }
                .action-controls h4 {
                    margin: 0 0 10px 0;
                    color: #333;
                    font-size: 14px;
                }
                .action-controls label {
                    font-size: 12px;
                    font-weight: bold;
                    color: #555;
                    align-self: center;
                }
                input[type="number"] { 
                    width: 80px; 
                    margin: 2px; 
                    padding: 5px;
                    border: 1px solid #ddd;
                    border-radius: 3px;
                    font-size: 12px;
                }
                .action-controls button {
                    margin: 5px 2px;
                    padding: 8px 12px;
                    font-size: 12px;
                }
                .current-position {
                    margin-top: 15px;
                    padding-top: 15px;
                    border-top: 1px solid #eee;
                }
                .current-position h4 {
                    margin: 0 0 10px 0;
                    color: #333;
                    font-size: 14px;
                }
                .header { text-align: center; margin-bottom: 30px; }
                .header h1 { color: #333; margin-bottom: 10px; }
                .header p { color: #666; margin: 0; }
            </style>
        </head>
                 <body>
            <div class="header">
                <h1>🤖 LeRobot WebRTC Controller</h1>
                <p>Real-time robot connection status and control interface</p>
                <p><small>Status updates every 2 seconds automatically</small></p>
            </div>
            <div id="robots" class="robot-grid"></div>
            
            <script>
                async function loadRobots() {
                    try {
                        const response = await fetch('/api/robots');
                        const robots = await response.json();
                        await displayRobots(robots);
                    } catch (error) {
                        console.error('Error loading robots:', error);
                    }
                }
                
                async function displayRobots(robots) {
                    const container = document.getElementById('robots');
                    container.innerHTML = '';
                    
                    for (const [name, type] of Object.entries(robots)) {
                        const card = document.createElement('div');
                        card.className = 'robot-card';
                        card.innerHTML = `
                            <h3>${name}</h3>
                            <p>Type: ${type}</p>
                            <div id="status-${name}" class="status-disconnected">Checking...</div>
                            <div id="details-${name}" style="font-size: 12px; color: #666; margin: 5px 0;"></div>
                            <button onclick="connectRobot('${name}')">Connect</button>
                            <button onclick="disconnectRobot('${name}')">Disconnect</button>
                            
                            <div class="current-position">
                                <h4>📍 Current Position:</h4>
                                <div id="current-position-${name}" style="font-size: 11px; background: #f8f9fa; padding: 8px; border-radius: 4px; margin: 5px 0;">
                                    <div style="color: #666;">Position data will appear when connected...</div>
                                </div>
                                <button onclick="updateCurrentPosition('${name}')" style="font-size: 11px; padding: 4px 8px;">🔄 Refresh Position</button>
                            </div>
                            
                            <div class="action-controls">
                                <h4>Send Joint Position Action:</h4>
                                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 5px; margin: 10px 0;">
                                    <label>Shoulder Pan:</label>
                                    <input type="number" id="shoulder_pan-${name}" step="0.1" value="0.0" min="-180" max="180">
                                    <label>Shoulder Lift:</label>
                                    <input type="number" id="shoulder_lift-${name}" step="0.1" value="0.0" min="-180" max="180">
                                    <label>Elbow Flex:</label>
                                    <input type="number" id="elbow_flex-${name}" step="0.1" value="0.0" min="-180" max="180">
                                    <label>Wrist Flex:</label>
                                    <input type="number" id="wrist_flex-${name}" step="0.1" value="0.0" min="-180" max="180">
                                    <label>Wrist Roll:</label>
                                    <input type="number" id="wrist_roll-${name}" step="0.1" value="0.0" min="-180" max="180">
                                    <label>Gripper:</label>
                                    <input type="number" id="gripper-${name}" step="1" value="50" min="0" max="100">
                                </div>
                                <button onclick="sendAction('${name}')">Send Joint Action</button>
                                <button onclick="presetAction('${name}', 'home')" style="background: #28a745;">Home Position</button>
                                <button onclick="presetAction('${name}', 'safe')" style="background: #ffc107; color: #000;">Safe Position</button>
                                <button onclick="copyCurrentToInputs('${name}')" style="background: #17a2b8;">📋 Copy Current → Inputs</button>
                            </div>
                        `;
                        container.appendChild(card);
                        
                        // Check individual robot status
                        updateRobotStatus(name);
                        
                        // Update current position if connected
                        updateCurrentPosition(name);
                    }
                }
                
                async function updateRobotStatus(robotName) {
                    try {
                        const response = await fetch(`/api/robots/${robotName}/status`);
                        const status = await response.json();
                        
                        const statusElement = document.getElementById(`status-${robotName}`);
                        const detailsElement = document.getElementById(`details-${robotName}`);
                        
                        console.log(`Status update for ${robotName}:`, status); // Debug log
                        
                        if (status.is_connected) {
                            statusElement.textContent = 'Connected';
                            statusElement.className = 'status-connected';
                            
                            let details = `Port: ${status.port}`;
                            if (status.is_calibrated !== undefined) {
                                details += `, Calibrated: ${status.is_calibrated ? 'Yes' : 'No'}`;
                            }
                            if (status.connection_details) {
                                details += ` (${status.connection_details})`;
                            }
                            detailsElement.textContent = details;
                        } else {
                            statusElement.textContent = 'Disconnected';
                            statusElement.className = 'status-disconnected';
                            let details = `Port: ${status.port}`;
                            if (status.connection_details) {
                                details += ` (${status.connection_details})`;
                            }
                            detailsElement.textContent = details;
                        }
                    } catch (error) {
                        console.error(`Error getting status for ${robotName}:`, error);
                        const statusElement = document.getElementById(`status-${robotName}`);
                        const detailsElement = document.getElementById(`details-${robotName}`);
                        statusElement.textContent = 'Error';
                        statusElement.className = 'status-disconnected';
                        detailsElement.textContent = `Error: ${error.message}`;
                    }
                }
                
                async function connectRobot(name) {
                    try {
                        // Update UI to show connecting
                        document.getElementById(`status-${name}`).textContent = 'Connecting...';
                        document.getElementById(`status-${name}`).className = 'status-disconnected';
                        
                        const response = await fetch(`/api/robots/${name}/connect`, { method: 'POST' });
                        const result = await response.json();
                        
                        if (result.success) {
                            // Update status after successful connection
                            await updateRobotStatus(name);
                        } else {
                            document.getElementById(`status-${name}`).textContent = 'Connection Failed';
                            document.getElementById(`status-${name}`).className = 'status-disconnected';
                        }
                    } catch (error) {
                        console.error('Error connecting robot:', error);
                        document.getElementById(`status-${name}`).textContent = 'Connection Error';
                        document.getElementById(`status-${name}`).className = 'status-disconnected';
                    }
                }
                
                async function disconnectRobot(name) {
                    try {
                        // Update UI to show disconnecting
                        document.getElementById(`status-${name}`).textContent = 'Disconnecting...';
                        
                        const response = await fetch(`/api/robots/${name}/disconnect`, { method: 'POST' });
                        const result = await response.json();
                        
                        if (result.success) {
                            // Update status after successful disconnection
                            await updateRobotStatus(name);
                        } else {
                            document.getElementById(`status-${name}`).textContent = 'Disconnect Failed';
                            document.getElementById(`status-${name}`).className = 'status-disconnected';
                        }
                    } catch (error) {
                        console.error('Error disconnecting robot:', error);
                        document.getElementById(`status-${name}`).textContent = 'Disconnect Error';
                        document.getElementById(`status-${name}`).className = 'status-disconnected';
                    }
                }
                
                async function sendAction(name) {
                    try {
                        // Get joint position values
                        const shoulderPan = parseFloat(document.getElementById(`shoulder_pan-${name}`).value) || 0.0;
                        const shoulderLift = parseFloat(document.getElementById(`shoulder_lift-${name}`).value) || 0.0;
                        const elbowFlex = parseFloat(document.getElementById(`elbow_flex-${name}`).value) || 0.0;
                        const wristFlex = parseFloat(document.getElementById(`wrist_flex-${name}`).value) || 0.0;
                        const wristRoll = parseFloat(document.getElementById(`wrist_roll-${name}`).value) || 0.0;
                        const gripper = parseFloat(document.getElementById(`gripper-${name}`).value) || 50.0;
                        
                        // Create joint position action (same format as your curl command)
                        const action = {
                            "shoulder_pan.pos": shoulderPan,
                            "shoulder_lift.pos": shoulderLift,
                            "elbow_flex.pos": elbowFlex,
                            "wrist_flex.pos": wristFlex,
                            "wrist_roll.pos": wristRoll,
                            "gripper.pos": gripper
                        };
                        
                        console.log(`Sending action to ${name}:`, action);
                        
                        const response = await fetch(`/api/robots/${name}/action`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(action)
                        });
                        
                        const result = await response.json();
                        
                        if (result.success) {
                            console.log('✅ Action sent successfully:', result);
                            // Show success feedback
                            showActionFeedback(name, 'success', 'Action sent successfully!');
                        } else {
                            console.error('❌ Action failed:', result);
                            showActionFeedback(name, 'error', `Action failed: ${result.error || 'Unknown error'}`);
                        }
                    } catch (error) {
                        console.error('Error sending action:', error);
                        showActionFeedback(name, 'error', `Network error: ${error.message}`);
                    }
                }
                
                async function presetAction(name, preset) {
                    try {
                        let action;
                        
                        // Define preset positions
                        switch(preset) {
                            case 'home':
                                action = {
                                    "shoulder_pan.pos": 0.0,
                                    "shoulder_lift.pos": 0.0,
                                    "elbow_flex.pos": 0.0,
                                    "wrist_flex.pos": 0.0,
                                    "wrist_roll.pos": 0.0,
                                    "gripper.pos": 50.0
                                };
                                break;
                            case 'safe':
                                action = {
                                    "shoulder_pan.pos": 0.0,
                                    "shoulder_lift.pos": -30.0,
                                    "elbow_flex.pos": 60.0,
                                    "wrist_flex.pos": -30.0,
                                    "wrist_roll.pos": 0.0,
                                    "gripper.pos": 0.0
                                };
                                break;
                            default:
                                throw new Error(`Unknown preset: ${preset}`);
                        }
                        
                        console.log(`Sending ${preset} preset to ${name}:`, action);
                        
                        const response = await fetch(`/api/robots/${name}/action`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify(action)
                        });
                        
                        const result = await response.json();
                        
                        if (result.success) {
                            console.log(`✅ ${preset} preset sent successfully:`, result);
                            showActionFeedback(name, 'success', `${preset.charAt(0).toUpperCase() + preset.slice(1)} position sent!`);
                            
                            // Update the input fields to show the preset values
                            document.getElementById(`shoulder_pan-${name}`).value = action["shoulder_pan.pos"];
                            document.getElementById(`shoulder_lift-${name}`).value = action["shoulder_lift.pos"];
                            document.getElementById(`elbow_flex-${name}`).value = action["elbow_flex.pos"];
                            document.getElementById(`wrist_flex-${name}`).value = action["wrist_flex.pos"];
                            document.getElementById(`wrist_roll-${name}`).value = action["wrist_roll.pos"];
                            document.getElementById(`gripper-${name}`).value = action["gripper.pos"];
                        } else {
                            console.error(`❌ ${preset} preset failed:`, result);
                            showActionFeedback(name, 'error', `${preset} preset failed: ${result.error || 'Unknown error'}`);
                        }
                    } catch (error) {
                        console.error(`Error sending ${preset} preset:`, error);
                        showActionFeedback(name, 'error', `Error: ${error.message}`);
                    }
                }
                
                function showActionFeedback(robotName, type, message) {
                    // Create or update feedback element
                    let feedbackElement = document.getElementById(`feedback-${robotName}`);
                    if (!feedbackElement) {
                        feedbackElement = document.createElement('div');
                        feedbackElement.id = `feedback-${robotName}`;
                        feedbackElement.style.cssText = `
                            margin: 10px 0;
                            padding: 8px;
                            border-radius: 4px;
                            font-size: 12px;
                            font-weight: bold;
                        `;
                        
                        // Insert after the robot card header
                        const robotCard = document.getElementById(`details-${robotName}`).parentElement;
                        robotCard.insertBefore(feedbackElement, robotCard.children[2]); // After status and details
                    }
                    
                    // Set styling based on type
                    if (type === 'success') {
                        feedbackElement.style.backgroundColor = '#d4edda';
                        feedbackElement.style.color = '#155724';
                        feedbackElement.style.border = '1px solid #c3e6cb';
                    } else {
                        feedbackElement.style.backgroundColor = '#f8d7da';
                        feedbackElement.style.color = '#721c24';
                        feedbackElement.style.border = '1px solid #f5c6cb';
                    }
                    
                    feedbackElement.textContent = message;
                    
                    // Clear feedback after 3 seconds
                    setTimeout(() => {
                        if (feedbackElement.parentNode) {
                            feedbackElement.parentNode.removeChild(feedbackElement);
                        }
                    }, 3000);
                }
                
                async function updateCurrentPosition(robotName) {
                    try {
                        const response = await fetch(`/api/robots/${robotName}/position`);
                        
                        if (response.ok) {
                            const positionData = await response.json();
                            displayCurrentPosition(robotName, positionData);
                        } else {
                            // Robot might not be connected or doesn't support position reading
                            const positionElement = document.getElementById(`current-position-${robotName}`);
                            if (positionElement) {
                                positionElement.innerHTML = '<div style="color: #dc3545;">⚠️ Unable to read position (robot may be disconnected)</div>';
                            }
                        }
                    } catch (error) {
                        console.log(`Position update failed for ${robotName}:`, error.message);
                        const positionElement = document.getElementById(`current-position-${robotName}`);
                        if (positionElement) {
                            positionElement.innerHTML = '<div style="color: #666;">Position unavailable</div>';
                        }
                    }
                }
                
                function displayCurrentPosition(robotName, positionData) {
                    const positionElement = document.getElementById(`current-position-${robotName}`);
                    if (!positionElement) return;
                    
                    if (positionData.error) {
                        positionElement.innerHTML = `<div style="color: #dc3545;">❌ ${positionData.error}</div>`;
                        return;
                    }
                    
                    const positions = positionData.positions || {};
                    const timestamp = new Date(positionData.timestamp * 1000).toLocaleTimeString();
                    
                    let html = `<div style="color: #28a745; font-weight: bold; margin-bottom: 5px;">✅ Live Position Data</div>`;
                    html += `<div style="font-size: 10px; color: #666; margin-bottom: 8px;">Updated: ${timestamp}</div>`;
                    
                    if (Object.keys(positions).length === 0) {
                        html += '<div style="color: #ffc107;">⚠️ No position data available</div>';
                    } else {
                        html += '<div style="display: grid; grid-template-columns: 1fr 1fr; gap: 3px; font-family: monospace;">';
                        
                        // Display positions in a nice format
                        for (const [joint, value] of Object.entries(positions)) {
                            const jointName = joint.replace('.pos', '').replace('_', ' ');
                            const formattedValue = typeof value === 'number' ? value.toFixed(1) : value;
                            html += `
                                <div style="font-weight: bold; color: #495057;">${jointName}:</div>
                                <div style="color: #007bff;">${formattedValue}°</div>
                            `;
                        }
                        html += '</div>';
                    }
                    
                    positionElement.innerHTML = html;
                }
                
                function copyCurrentToInputs(robotName) {
                    try {
                        // Get the current position display element
                        const positionElement = document.getElementById(`current-position-${robotName}`);
                        if (!positionElement) {
                            showActionFeedback(robotName, 'error', 'Position data not available');
                            return;
                        }
                        
                        // We need to fetch the current position data fresh
                        fetch(`/api/robots/${robotName}/position`)
                            .then(response => response.json())
                            .then(positionData => {
                                if (positionData.error) {
                                    showActionFeedback(robotName, 'error', `Cannot copy position: ${positionData.error}`);
                                    return;
                                }
                                
                                const positions = positionData.positions || {};
                                let copiedCount = 0;
                                
                                // Map positions to input fields
                                const jointMapping = {
                                    'shoulder_pan.pos': 'shoulder_pan',
                                    'shoulder_lift.pos': 'shoulder_lift',
                                    'elbow_flex.pos': 'elbow_flex',
                                    'wrist_flex.pos': 'wrist_flex',
                                    'wrist_roll.pos': 'wrist_roll',
                                    'gripper.pos': 'gripper'
                                };
                                
                                for (const [posKey, inputKey] of Object.entries(jointMapping)) {
                                    if (positions[posKey] !== undefined) {
                                        const inputElement = document.getElementById(`${inputKey}-${robotName}`);
                                        if (inputElement) {
                                            inputElement.value = positions[posKey].toFixed(1);
                                            copiedCount++;
                                        }
                                    }
                                }
                                
                                if (copiedCount > 0) {
                                    showActionFeedback(robotName, 'success', `✅ Copied ${copiedCount} joint positions to inputs`);
                                } else {
                                    showActionFeedback(robotName, 'error', 'No position data available to copy');
                                }
                            })
                            .catch(error => {
                                console.error('Error copying positions:', error);
                                showActionFeedback(robotName, 'error', 'Failed to copy positions');
                            });
                    } catch (error) {
                        console.error('Error in copyCurrentToInputs:', error);
                        showActionFeedback(robotName, 'error', 'Error copying positions');
                    }
                }
                
                // Load robots on page load
                loadRobots();
                
                // Refresh status and positions every 2 seconds
                setInterval(async () => {
                    // Get current robot list and update their status and positions
                    try {
                        const response = await fetch('/api/robots');
                        const robots = await response.json();
                        for (const robotName of Object.keys(robots)) {
                            await updateRobotStatus(robotName);
                            // Only update positions for connected robots to avoid spam
                            const statusElement = document.getElementById(`status-${robotName}`);
                            if (statusElement && statusElement.textContent === 'Connected') {
                                updateCurrentPosition(robotName);
                            }
                        }
                    } catch (error) {
                        console.error('Error refreshing robot data:', error);
                    }
                }, 2000);
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

    async def _handle_get_position(self, request: web.Request) -> web.Response:
        """Get current position from a robot."""
        robot_name = request.match_info["robot_name"]
        
        try:
            position = await self.robot_manager.get_robot_position(robot_name)
            return web.json_response(position)
        except ValueError as e:
            return web.json_response({"error": str(e)}, status=404)
        except Exception as e:
            logger.error(f"Error getting position: {e}")
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