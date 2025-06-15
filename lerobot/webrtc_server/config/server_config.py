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

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Union
from pathlib import Path


@dataclass
class RobotConnectionConfig:
    """Configuration for a single robot connection."""
    robot_type: str  # "leader" or "follower"
    robot_class: str  # e.g., "so101_leader", "so101_follower"
    port: str
    id: str
    calibration_dir: Optional[Path] = None
    max_relative_target: Optional[float] = None
    use_degrees: bool = False
    disable_torque_on_disconnect: bool = True


@dataclass
class WebRTCServerConfig:
    """Configuration for the WebRTC Robot Server."""
    
    # Server settings
    host: str = "0.0.0.0"
    port: int = 8080
    debug: bool = False
    
    # WebRTC settings
    ice_servers: List[Dict[str, Union[str, List[str]]]] = field(default_factory=lambda: [
        {"urls": ["stun:stun.l.google.com:19302"]},
        {"urls": ["stun:stun1.l.google.com:19302"]},
    ])
    
    # Security settings
    enable_cors: bool = True
    allowed_origins: List[str] = field(default_factory=lambda: ["*"])
    api_key: Optional[str] = None
    enable_authentication: bool = False
    
    # Robot configurations
    robots: Dict[str, RobotConnectionConfig] = field(default_factory=dict)
    
    # Action settings
    action_timeout_ms: int = 100  # Timeout for action commands
    max_action_queue_size: int = 10
    enable_action_logging: bool = True
    
    # Video streaming settings (for future expansion)
    enable_video_streaming: bool = False
    video_resolution: tuple = (640, 480)
    video_fps: int = 30
    
    # Safety settings
    enable_safety_limits: bool = True
    emergency_stop_enabled: bool = True
    max_connection_time_s: int = 3600  # 1 hour max session
    
    def add_robot(self, name: str, robot_config: RobotConnectionConfig) -> None:
        """Add a robot configuration to the server."""
        self.robots[name] = robot_config
    
    def get_robot_config(self, name: str) -> Optional[RobotConnectionConfig]:
        """Get robot configuration by name."""
        return self.robots.get(name)
    
    def list_robots(self) -> List[str]:
        """List all configured robot names."""
        return list(self.robots.keys())
    
    def get_leaders(self) -> Dict[str, RobotConnectionConfig]:
        """Get all leader robot configurations."""
        return {name: config for name, config in self.robots.items() 
                if config.robot_type == "leader"}
    
    def get_followers(self) -> Dict[str, RobotConnectionConfig]:
        """Get all follower robot configurations."""
        return {name: config for name, config in self.robots.items() 
                if config.robot_type == "follower"}


def create_default_config() -> WebRTCServerConfig:
    """Create a default WebRTC server configuration with common robot setups."""
    config = WebRTCServerConfig()
    
    # Add example SO101 leader configuration
    config.add_robot("so101_leader", RobotConnectionConfig(
        robot_type="leader",
        robot_class="so101_leader", 
        port="/dev/ttyUSB0",
        id="webrtc_leader_arm"
    ))
    
    # Add example SO101 follower configuration
    config.add_robot("so101_follower", RobotConnectionConfig(
        robot_type="follower",
        robot_class="so101_follower",
        port="/dev/ttyUSB1", 
        id="webrtc_follower_arm"
    ))
    
    return config 