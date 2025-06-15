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
WebRTC Server for LeRobot

This module provides WebRTC-based remote control capabilities for LeRobot systems,
allowing real-time action transmission to both leader and follower robots over the web.
"""

from .server.webrtc_robot_server import WebRTCRobotServer
from .config.server_config import WebRTCServerConfig
from .utils.robot_manager import RobotManager

__all__ = [
    "WebRTCRobotServer",
    "WebRTCServerConfig", 
    "RobotManager",
]

__version__ = "0.1.0" 