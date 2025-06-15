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
from typing import Dict, Any, List, Optional, Union
import numpy as np

logger = logging.getLogger(__name__)


class ActionValidator:
    """
    Validates robot actions for safety and correctness.
    
    Provides validation for different robot types and action formats,
    ensuring actions are safe before being sent to robots.
    """
    
    # Default safe ranges for different robot types
    ROBOT_LIMITS = {
        "so101_follower": {
            "joint_position_limits": (-180, 180),  # degrees
            "gripper_limits": (0, 100),  # percentage
            "max_delta": 10.0,  # maximum change per step
        },
        "so100_follower": {
            "joint_position_limits": (-180, 180),
            "gripper_limits": (0, 100),
            "max_delta": 10.0,
        },
        "koch_follower": {
            "joint_position_limits": (-180, 180),
            "gripper_limits": (0, 100),
            "max_delta": 10.0,
        },
        "so101_leader": {
            "joint_position_limits": (-180, 180),
            "gripper_limits": (0, 100),
            "max_delta": 10.0,
        },
        "so100_leader": {
            "joint_position_limits": (-180, 180),
            "gripper_limits": (0, 100),
            "max_delta": 10.0,
        },
        "koch_leader": {
            "joint_position_limits": (-180, 180),
            "gripper_limits": (0, 100),
            "max_delta": 10.0,
        },
    }
    
    def __init__(self, enable_safety_limits: bool = True):
        """Initialize the action validator."""
        self.enable_safety_limits = enable_safety_limits
        self.previous_actions: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"ActionValidator initialized (safety_limits={'enabled' if enable_safety_limits else 'disabled'})")
    
    def validate_action(self, 
                       robot_name: str, 
                       robot_class: str, 
                       action: Dict[str, Any],
                       robot_type: str = "follower") -> tuple[bool, Optional[str], Dict[str, Any]]:
        """
        Validate an action for a specific robot.
        
        Args:
            robot_name: Name of the robot
            robot_class: Class of the robot (e.g., "so101_follower")
            action: Action dictionary to validate
            robot_type: Type of robot ("leader" or "follower")
            
        Returns:
            Tuple of (is_valid, error_message, sanitized_action)
        """
        try:
            # Basic validation
            if not isinstance(action, dict):
                return False, "Action must be a dictionary", {}
            
            if not action:
                return False, "Action cannot be empty", {}
            
            # Get robot limits
            limits = self.ROBOT_LIMITS.get(robot_class, self.ROBOT_LIMITS["so101_follower"])
            
            # Copy action for sanitization
            sanitized_action = action.copy()
            
            # Validate based on robot type
            if robot_type == "follower":
                valid, error, sanitized_action = self._validate_follower_action(
                    robot_name, robot_class, sanitized_action, limits
                )
            elif robot_type == "leader":
                valid, error, sanitized_action = self._validate_leader_action(
                    robot_name, robot_class, sanitized_action, limits
                )
            else:
                return False, f"Unknown robot type: {robot_type}", {}
            
            if not valid:
                return False, error, {}
            
            # Store for delta validation
            self.previous_actions[robot_name] = sanitized_action.copy()
            
            return True, None, sanitized_action
            
        except Exception as e:
            logger.error(f"Error validating action for {robot_name}: {e}")
            return False, f"Validation error: {str(e)}", {}
    
    def _validate_follower_action(self, 
                                robot_name: str, 
                                robot_class: str,
                                action: Dict[str, Any], 
                                limits: Dict[str, Any]) -> tuple[bool, Optional[str], Dict[str, Any]]:
        """Validate action for follower robots."""
        
        # Check for required position keys
        position_keys = [key for key in action.keys() if key.endswith(".pos")]
        
        if not position_keys and not any(key in action for key in ["delta_x", "delta_y", "delta_z"]):
            return False, "Action must contain either joint positions (.pos) or end-effector deltas", action
        
        # Validate joint positions
        if position_keys:
            for key in position_keys:
                value = action[key]
                
                # Check type
                if not isinstance(value, (int, float)):
                    return False, f"Joint position {key} must be a number", action
                
                # Check limits if safety is enabled
                if self.enable_safety_limits:
                    min_val, max_val = limits["joint_position_limits"]
                    if value < min_val or value > max_val:
                        logger.warning(f"Clamping {key} from {value} to [{min_val}, {max_val}]")
                        action[key] = float(np.clip(value, min_val, max_val))
        
        # Validate end-effector commands
        ee_keys = ["delta_x", "delta_y", "delta_z"]
        for key in ee_keys:
            if key in action:
                value = action[key]
                
                # Check type
                if not isinstance(value, (int, float)):
                    return False, f"End-effector delta {key} must be a number", action
                
                # Check reasonable ranges for deltas (typically -1 to 1)
                if self.enable_safety_limits:
                    if abs(value) > 2.0:  # Allow some flexibility
                        logger.warning(f"Clamping {key} from {value} to [-2.0, 2.0]")
                        action[key] = float(np.clip(value, -2.0, 2.0))
        
        # Validate gripper
        if "gripper" in action:
            gripper_value = action["gripper"]
            
            if not isinstance(gripper_value, (int, float)):
                return False, "Gripper value must be a number", action
            
            if self.enable_safety_limits:
                min_val, max_val = limits["gripper_limits"]
                if gripper_value < min_val or gripper_value > max_val:
                    logger.warning(f"Clamping gripper from {gripper_value} to [{min_val}, {max_val}]")
                    action["gripper"] = float(np.clip(gripper_value, min_val, max_val))
        
        # Validate delta from previous action
        if self.enable_safety_limits and robot_name in self.previous_actions:
            valid, error = self._validate_action_delta(robot_name, action, limits)
            if not valid:
                return False, error, action
        
        return True, None, action
    
    def _validate_leader_action(self, 
                              robot_name: str, 
                              robot_class: str,
                              action: Dict[str, Any], 
                              limits: Dict[str, Any]) -> tuple[bool, Optional[str], Dict[str, Any]]:
        """Validate action for leader robots (typically used for feedback)."""
        
        # Leaders typically provide position feedback, validate similarly to followers
        # but with more permissive limits since they're human-controlled
        
        position_keys = [key for key in action.keys() if key.endswith(".pos")]
        
        for key in position_keys:
            value = action[key]
            
            if not isinstance(value, (int, float)):
                return False, f"Position {key} must be a number", action
            
            # More permissive limits for leaders
            if self.enable_safety_limits:
                min_val, max_val = limits["joint_position_limits"]
                # Extend limits by 20% for leaders
                extended_range = (max_val - min_val) * 0.2
                min_val -= extended_range
                max_val += extended_range
                
                if value < min_val or value > max_val:
                    logger.warning(f"Leader position {key} out of extended range: {value}")
                    # Don't clamp leader positions, just warn
        
        return True, None, action
    
    def _validate_action_delta(self, 
                             robot_name: str, 
                             current_action: Dict[str, Any], 
                             limits: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """Validate that the action delta from previous action is safe."""
        
        previous_action = self.previous_actions[robot_name]
        max_delta = limits["max_delta"]
        
        # Check deltas for joint positions
        for key in current_action:
            if key.endswith(".pos") and key in previous_action:
                current_val = current_action[key]
                previous_val = previous_action[key]
                delta = abs(current_val - previous_val)
                
                if delta > max_delta:
                    return False, f"Action delta too large for {key}: {delta} > {max_delta}"
        
        return True, None
    
    def set_robot_limits(self, robot_class: str, limits: Dict[str, Any]) -> None:
        """Set custom limits for a robot class."""
        self.ROBOT_LIMITS[robot_class] = limits
        logger.info(f"Updated limits for robot class {robot_class}")
    
    def get_robot_limits(self, robot_class: str) -> Dict[str, Any]:
        """Get current limits for a robot class."""
        return self.ROBOT_LIMITS.get(robot_class, self.ROBOT_LIMITS["so101_follower"])
    
    def reset_robot_history(self, robot_name: str) -> None:
        """Reset action history for a specific robot."""
        if robot_name in self.previous_actions:
            del self.previous_actions[robot_name]
            logger.info(f"Reset action history for robot {robot_name}")
    
    def reset_all_history(self) -> None:
        """Reset action history for all robots."""
        self.previous_actions.clear()
        logger.info("Reset action history for all robots")
    
    def validate_action_format(self, action: Dict[str, Any], expected_format: str) -> tuple[bool, Optional[str]]:
        """
        Validate that action matches expected format.
        
        Args:
            action: Action to validate
            expected_format: One of "joint_positions", "end_effector", "mixed"
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if expected_format == "joint_positions":
            position_keys = [key for key in action.keys() if key.endswith(".pos")]
            if not position_keys:
                return False, "Expected joint position actions (.pos keys)"
                
        elif expected_format == "end_effector":
            ee_keys = ["delta_x", "delta_y", "delta_z"]
            if not any(key in action for key in ee_keys):
                return False, "Expected end-effector delta actions (delta_x, delta_y, delta_z)"
                
        elif expected_format == "mixed":
            # Allow both formats
            position_keys = [key for key in action.keys() if key.endswith(".pos")]
            ee_keys = ["delta_x", "delta_y", "delta_z"]
            has_positions = bool(position_keys)
            has_ee = any(key in action for key in ee_keys)
            
            if not (has_positions or has_ee):
                return False, "Expected either joint positions or end-effector deltas"
        else:
            return False, f"Unknown action format: {expected_format}"
        
        return True, None 