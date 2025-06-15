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

import logging
import asyncio
from typing import Dict, Any, Optional, Union
from threading import Lock
import time

from lerobot.common.robots.robot import Robot
from lerobot.common.teleoperators.teleoperator import Teleoperator
from lerobot.common.errors import DeviceNotConnectedError, DeviceAlreadyConnectedError

# Import robot classes
from lerobot.common.robots.so101_follower import SO101Follower, SO101FollowerConfig
from lerobot.common.robots.so100_follower import SO100Follower, SO100FollowerConfig
from lerobot.common.robots.koch_follower import KochFollower, KochFollowerConfig

# Import teleoperator classes  
from lerobot.common.teleoperators.so101_leader import SO101Leader, SO101LeaderConfig
from lerobot.common.teleoperators.so100_leader import SO100Leader, SO100LeaderConfig
from lerobot.common.teleoperators.koch_leader import KochLeader, KochLeaderConfig

from ..config.server_config import RobotConnectionConfig, WebRTCServerConfig

logger = logging.getLogger(__name__)


class RobotManager:
    """
    Manages robot connections and action routing for WebRTC server.
    
    Handles both leader and follower robots, providing a unified interface
    for sending actions and managing connections.
    """
    
    # Mapping of robot class names to their respective classes and config classes
    ROBOT_REGISTRY = {
        "so101_follower": (SO101Follower, SO101FollowerConfig),
        "so100_follower": (SO100Follower, SO100FollowerConfig), 
        "koch_follower": (KochFollower, KochFollowerConfig),
        "so101_leader": (SO101Leader, SO101LeaderConfig),
        "so100_leader": (SO100Leader, SO100LeaderConfig),
        "koch_leader": (KochLeader, KochLeaderConfig),
    }
    
    def __init__(self, config: WebRTCServerConfig):
        """Initialize the robot manager with server configuration."""
        self.config = config
        self.robots: Dict[str, Union[Robot, Teleoperator]] = {}
        self.robot_configs: Dict[str, RobotConnectionConfig] = {}
        self.connection_lock = Lock()
        
        # Action queues for async processing
        self.action_queues: Dict[str, asyncio.Queue] = {}
        
        logger.info(f"RobotManager initialized with {len(config.robots)} robot configurations")
    
    async def initialize_robots(self) -> None:
        """Initialize all configured robots."""
        for name, robot_config in self.config.robots.items():
            try:
                await self.add_robot(name, robot_config)
                logger.info(f"Successfully initialized robot: {name}")
            except Exception as e:
                logger.error(f"Failed to initialize robot {name}: {e}")
    
    async def add_robot(self, name: str, robot_config: RobotConnectionConfig) -> None:
        """Add and initialize a robot connection."""
        if name in self.robots:
            raise ValueError(f"Robot {name} already exists")
        
        # Get robot class and config class
        if robot_config.robot_class not in self.ROBOT_REGISTRY:
            raise ValueError(f"Unknown robot class: {robot_config.robot_class}")
        
        robot_cls, config_cls = self.ROBOT_REGISTRY[robot_config.robot_class]
        
        # Create robot configuration
        config_dict = {
            "port": robot_config.port,
            "id": robot_config.id,
        }
        
        # Add optional parameters if specified
        if robot_config.calibration_dir:
            config_dict["calibration_dir"] = robot_config.calibration_dir
        if robot_config.max_relative_target:
            config_dict["max_relative_target"] = robot_config.max_relative_target
        if robot_config.use_degrees:
            config_dict["use_degrees"] = robot_config.use_degrees
        if hasattr(config_cls, "disable_torque_on_disconnect"):
            config_dict["disable_torque_on_disconnect"] = robot_config.disable_torque_on_disconnect
        
        # Create robot instance
        robot_instance_config = config_cls(**config_dict)
        robot_instance = robot_cls(robot_instance_config)
        
        # Store robot and configuration
        self.robots[name] = robot_instance
        self.robot_configs[name] = robot_config
        self.action_queues[name] = asyncio.Queue(maxsize=self.config.max_action_queue_size)
        
        logger.info(f"Added robot: {name} ({robot_config.robot_class})")
    
    async def connect_robot(self, name: str, calibrate: bool = True) -> bool:
        """Connect to a specific robot."""
        if name not in self.robots:
            raise ValueError(f"Robot {name} not found")
        
        robot = self.robots[name]
        
        try:
            with self.connection_lock:
                # Check if already connected
                if robot.is_connected:
                    logger.warning(f"Robot {name} is already connected")
                    return True
                
                logger.info(f"Attempting to connect to robot: {name}")
                
                # Connect to the robot
                robot.connect(calibrate=calibrate)
                
                # Verify connection was successful
                connection_verified = False
                for attempt in range(3):  # Try up to 3 times to verify
                    await asyncio.sleep(0.5)  # Give time for connection to establish
                    
                    if robot.is_connected:
                        connection_verified = True
                        break
                    elif hasattr(robot, 'bus') and hasattr(robot.bus, 'is_connected'):
                        if robot.bus.is_connected:
                            connection_verified = True
                            break
                    
                    logger.debug(f"Connection verification attempt {attempt + 1} for {name}: {robot.is_connected}")
                
                if connection_verified:
                    logger.info(f"✅ Successfully connected to robot: {name}")
                    return True
                else:
                    logger.error(f"❌ Connection to robot {name} not verified after connect() call")
                    return False
                
        except (DeviceNotConnectedError, DeviceAlreadyConnectedError) as e:
            logger.error(f"Failed to connect to robot {name}: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error connecting to robot {name}: {e}")
            return False
    
    async def disconnect_robot(self, name: str) -> bool:
        """Disconnect from a specific robot."""
        if name not in self.robots:
            raise ValueError(f"Robot {name} not found")
        
        robot = self.robots[name]
        
        try:
            with self.connection_lock:
                if not robot.is_connected:
                    logger.warning(f"Robot {name} is already disconnected")
                    return True
                
                robot.disconnect()
                logger.info(f"Successfully disconnected from robot: {name}")
                return True
                
        except Exception as e:
            logger.error(f"Error disconnecting from robot {name}: {e}")
            return False
    
    async def connect_all_robots(self, calibrate: bool = True) -> Dict[str, bool]:
        """Connect to all configured robots."""
        results = {}
        for name in self.robots:
            results[name] = await self.connect_robot(name, calibrate)
        return results
    
    async def disconnect_all_robots(self) -> Dict[str, bool]:
        """Disconnect from all robots."""
        results = {}
        for name in self.robots:
            results[name] = await self.disconnect_robot(name)
        return results
    
    async def send_action(self, robot_name: str, action: Dict[str, Any]) -> Dict[str, Any]:
        """Send an action to a specific robot."""
        if robot_name not in self.robots:
            raise ValueError(f"Robot {robot_name} not found")
        
        robot = self.robots[robot_name]
        robot_config = self.robot_configs[robot_name]
        
        if not robot.is_connected:
            raise DeviceNotConnectedError(f"Robot {robot_name} is not connected")
        
        try:
            # Log action if enabled
            if self.config.enable_action_logging:
                logger.debug(f"Sending action to {robot_name}: {action}")
            
            # Send action based on robot type
            if robot_config.robot_type == "follower":
                # For followers, use send_action method
                result = robot.send_action(action)
            elif robot_config.robot_type == "leader":
                # For leaders, this might be used for feedback (future feature)
                # For now, leaders typically only provide get_action, not send_action
                logger.warning(f"send_action called on leader robot {robot_name}. This may not be supported.")
                result = action  # Return the original action
            else:
                raise ValueError(f"Unknown robot type: {robot_config.robot_type}")
            
            return result
            
        except Exception as e:
            logger.error(f"Error sending action to robot {robot_name}: {e}")
            raise
    
    async def get_action(self, robot_name: str) -> Dict[str, Any]:
        """Get action from a leader robot (for teleoperation)."""
        if robot_name not in self.robots:
            raise ValueError(f"Robot {robot_name} not found")
        
        robot = self.robots[robot_name]
        robot_config = self.robot_configs[robot_name]
        
        if not robot.is_connected:
            raise DeviceNotConnectedError(f"Robot {robot_name} is not connected")
        
        if robot_config.robot_type != "leader":
            raise ValueError(f"get_action can only be called on leader robots, but {robot_name} is a {robot_config.robot_type}")
        
        try:
            # Get action from leader robot
            action = robot.get_action()
            
            if self.config.enable_action_logging:
                logger.debug(f"Got action from {robot_name}: {action}")
            
            return action
            
        except Exception as e:
            logger.error(f"Error getting action from robot {robot_name}: {e}")
            raise
    
    async def get_robot_status(self, robot_name: str) -> Dict[str, Any]:
        """Get status information for a specific robot."""
        if robot_name not in self.robots:
            raise ValueError(f"Robot {robot_name} not found")
        
        robot = self.robots[robot_name]
        robot_config = self.robot_configs[robot_name]
        
        # Get connection status with additional checks
        is_connected = False
        connection_details = "Unknown"
        
        try:
            # Primary check: robot's is_connected property
            is_connected = robot.is_connected
            
            # Additional verification for motor bus based robots
            if hasattr(robot, 'bus') and hasattr(robot.bus, 'is_connected'):
                bus_connected = robot.bus.is_connected
                connection_details = f"Robot: {is_connected}, Bus: {bus_connected}"
                
                # If there's a mismatch, prefer the bus status for accuracy
                if is_connected != bus_connected:
                    logger.warning(f"Connection status mismatch for {robot_name}: {connection_details}")
                    is_connected = bus_connected
            else:
                connection_details = f"Robot: {is_connected}"
                
            logger.debug(f"Status check for {robot_name}: {connection_details}")
                
        except Exception as e:
            logger.error(f"Error checking connection status for {robot_name}: {e}")
            is_connected = False
            connection_details = f"Error: {str(e)}"
        
        status = {
            "name": robot_name,
            "robot_type": robot_config.robot_type,
            "robot_class": robot_config.robot_class,
            "is_connected": is_connected,
            "port": robot_config.port,
            "id": robot_config.id,
            "connection_details": connection_details,  # Add debug info
        }
        
        # Add calibration status if available
        try:
            if hasattr(robot, "is_calibrated"):
                status["is_calibrated"] = robot.is_calibrated
        except Exception as e:
            logger.warning(f"Error checking calibration status for {robot_name}: {e}")
            status["is_calibrated"] = False
        
        return status
    
    async def get_all_robot_status(self) -> Dict[str, Dict[str, Any]]:
        """Get status for all robots."""
        status = {}
        for name in self.robots:
            status[name] = await self.get_robot_status(name)
        return status
    
    def list_robots(self) -> Dict[str, str]:
        """List all configured robots with their types."""
        return {
            name: self.robot_configs[name].robot_type 
            for name in self.robots
        }
    
    def get_leaders(self) -> Dict[str, str]:
        """Get all leader robots."""
        return {
            name: self.robot_configs[name].robot_class
            for name in self.robots
            if self.robot_configs[name].robot_type == "leader"
        }
    
    def get_followers(self) -> Dict[str, str]:
        """Get all follower robots."""
        return {
            name: self.robot_configs[name].robot_class
            for name in self.robots
            if self.robot_configs[name].robot_type == "follower"
        }
    
    async def emergency_stop_all(self) -> Dict[str, bool]:
        """Emergency stop for all connected robots."""
        logger.warning("Emergency stop activated for all robots!")
        results = {}
        
        for name in self.robots:
            try:
                robot = self.robots[name]
                if robot.is_connected:
                    # For followers, send zero action to stop movement
                    if self.robot_configs[name].robot_type == "follower":
                        zero_action = {f"{motor}.pos": 0.0 for motor in robot.bus.motors}
                        await self.send_action(name, zero_action)
                    
                    # Disconnect the robot
                    await self.disconnect_robot(name)
                    results[name] = True
                else:
                    results[name] = True  # Already disconnected
                    
            except Exception as e:
                logger.error(f"Error during emergency stop for robot {name}: {e}")
                results[name] = False
        
        return results
    
    async def cleanup(self) -> None:
        """Clean up all robot connections."""
        logger.info("Cleaning up robot manager...")
        await self.disconnect_all_robots()
        
        # Clear all data structures
        self.robots.clear()
        self.robot_configs.clear()
        self.action_queues.clear()
        
        logger.info("Robot manager cleanup completed")
    
    async def get_robot_position(self, robot_name: str) -> Dict[str, Any]:
        """Get current position/state of a specific robot."""
        if robot_name not in self.robots:
            raise ValueError(f"Robot {robot_name} not found")
        
        robot = self.robots[robot_name]
        robot_config = self.robot_configs[robot_name]
        
        if not robot.is_connected:
            raise DeviceNotConnectedError(f"Robot {robot_name} is not connected")
        
        try:
            # Get current positions based on robot type
            if robot_config.robot_type == "follower":
                # For followers, get current motor positions
                if hasattr(robot, 'bus') and hasattr(robot.bus, 'read_with_motor_ids'):
                    # Read current positions from all motors
                    positions = {}
                    for motor_name in robot.bus.motors:
                        try:
                            # Read current position for this motor
                            motor_positions = robot.bus.read_with_motor_ids([motor_name], "Present_Position")
                            if motor_positions and len(motor_positions) > 0:
                                positions[f"{motor_name}.pos"] = float(motor_positions[0])
                            else:
                                positions[f"{motor_name}.pos"] = 0.0
                        except Exception as e:
                            logger.warning(f"Error reading position for motor {motor_name}: {e}")
                            positions[f"{motor_name}.pos"] = 0.0
                    
                    return {
                        "robot": robot_name,
                        "positions": positions,
                        "timestamp": time.time()
                    }
                else:
                    # Fallback: try to get positions using robot's internal state
                    logger.warning(f"Could not access motor bus for {robot_name}, using fallback method")
                    return {
                        "robot": robot_name,
                        "positions": {},
                        "error": "Unable to read current positions",
                        "timestamp": time.time()
                    }
                    
            elif robot_config.robot_type == "leader":
                # For leaders, get the current action/position
                action = robot.get_action()
                return {
                    "robot": robot_name,
                    "positions": action,
                    "timestamp": time.time()
                }
            else:
                raise ValueError(f"Unknown robot type: {robot_config.robot_type}")
                
        except Exception as e:
            logger.error(f"Error getting position from robot {robot_name}: {e}")
            raise 