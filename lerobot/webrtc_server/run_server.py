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
WebRTC Robot Server Launcher

This script starts the WebRTC server for remote robot control.
It provides examples of how to configure and start the server with
different robot setups.

Usage:
    python -m lerobot.webrtc_server.run_server --config CONFIG_FILE
    python -m lerobot.webrtc_server.run_server --example so101
    python -m lerobot.webrtc_server.run_server --help

Requirements:
    pip install -e ".[webrtc,feetech]"  # For SO101/SO100 robots
    pip install -e ".[webrtc,dynamixel]"  # For Koch robots
    
    For full WebRTC functionality (optional):
    pip install aiortc
"""

import asyncio
import argparse
import logging
import signal
import sys
from pathlib import Path

from .config.server_config import WebRTCServerConfig, RobotConnectionConfig, create_default_config

logger = logging.getLogger(__name__)


def setup_logging(debug: bool = False) -> None:
    """Setup logging configuration."""
    level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler('webrtc_server.log')
        ]
    )


def create_so101_example_config() -> WebRTCServerConfig:
    """Create example configuration for SO101 leader-follower setup."""
    config = WebRTCServerConfig(
        host="0.0.0.0",
        port=8080,
        debug=True,
        enable_safety_limits=True,
        emergency_stop_enabled=True
    )
    
    # Add SO101 leader
    config.add_robot("so101_leader", RobotConnectionConfig(
        robot_type="leader",
        robot_class="so101_leader",
        port="/dev/ttyUSB0",  # Adjust as needed
        id="webrtc_leader_arm"
    ))
    
    # Add SO101 follower - change id to match calibration
    config.add_robot("so101_follower", RobotConnectionConfig(
        robot_type="follower", 
        robot_class="so101_follower",
        port="/dev/tty.usbmodem58A60699991",
        id=None  # Change from "webrtc_follower_arm" to None
    ))
    
    return config


def create_so100_example_config() -> WebRTCServerConfig:
    """Create example configuration for SO100 leader-follower setup."""
    config = WebRTCServerConfig(
        host="0.0.0.0",
        port=8080,
        debug=True,
        enable_safety_limits=True,
        emergency_stop_enabled=True
    )
    
    # Add SO100 leader
    config.add_robot("so100_leader", RobotConnectionConfig(
        robot_type="leader",
        robot_class="so100_leader",
        port="/dev/ttyUSB0",
        id="webrtc_leader_arm"
    ))
    
    # Add SO100 follower
    config.add_robot("so100_follower", RobotConnectionConfig(
        robot_type="follower",
        robot_class="so100_follower", 
        port="/dev/ttyUSB1",
        id="webrtc_follower_arm"
    ))
    
    return config


def create_koch_example_config() -> WebRTCServerConfig:
    """Create example configuration for Koch leader-follower setup."""
    config = WebRTCServerConfig(
        host="0.0.0.0",
        port=8080,
        debug=True,
        enable_safety_limits=True,
        emergency_stop_enabled=True
    )
    
    # Add Koch leader
    config.add_robot("koch_leader", RobotConnectionConfig(
        robot_type="leader",
        robot_class="koch_leader",
        port="/dev/ttyUSB0",
        id="webrtc_leader_arm"
    ))
    
    # Add Koch follower
    config.add_robot("koch_follower", RobotConnectionConfig(
        robot_type="follower",
        robot_class="koch_follower",
        port="/dev/ttyUSB1", 
        id="webrtc_follower_arm"
    ))
    
    return config


def create_mixed_example_config() -> WebRTCServerConfig:
    """Create example configuration with multiple robot types."""
    config = WebRTCServerConfig(
        host="0.0.0.0",
        port=8080,
        debug=True,
        enable_safety_limits=True,
        emergency_stop_enabled=True
    )
    
    # Add multiple leaders
    config.add_robot("so101_leader", RobotConnectionConfig(
        robot_type="leader",
        robot_class="so101_leader",
        port="/dev/ttyUSB0",
        id="leader_1"
    ))
    
    config.add_robot("so100_leader", RobotConnectionConfig(
        robot_type="leader", 
        robot_class="so100_leader",
        port="/dev/ttyUSB1",
        id="leader_2"
    ))
    
    # Add multiple followers
    config.add_robot("so101_follower", RobotConnectionConfig(
        robot_type="follower",
        robot_class="so101_follower",
        port="/dev/ttyUSB2",
        id="follower_1"
    ))
    
    config.add_robot("koch_follower", RobotConnectionConfig(
        robot_type="follower",
        robot_class="koch_follower", 
        port="/dev/ttyUSB3",
        id="follower_2"
    ))
    
    return config


def create_so101_macos_config() -> WebRTCServerConfig:
    """Create SO101 configuration for macOS with specific USB port."""
    config = WebRTCServerConfig(
        host="0.0.0.0",
        port=8080,
        debug=True,
        enable_safety_limits=True,
        emergency_stop_enabled=True
    )
    
    # Add SO101 follower with your specific port
    config.add_robot("so101_follower", RobotConnectionConfig(
        robot_type="follower", 
        robot_class="so101_follower",
        port="/dev/tty.usbmodem58A60699991",  # Your specific port
        id="webrtc_follower_arm"
    ))
    
    return config


async def run_server(config: WebRTCServerConfig) -> None:
    """Run the WebRTC robot server."""
    try:
        # Import here to allow graceful failure if dependencies missing
        from .server.webrtc_robot_server import WebRTCRobotServer
        
        server = WebRTCRobotServer(config)
        
        # Setup signal handlers for graceful shutdown
        stop_event = asyncio.Event()
        
        def signal_handler():
            logger.info("Received shutdown signal")
            stop_event.set()
        
        # Register signal handlers
        if sys.platform != "win32":
            loop = asyncio.get_event_loop()
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, signal_handler)
        
        # Start server
        await server.start()
        
        logger.info("WebRTC Robot Server is running...")
        logger.info(f"Web interface: http://{config.host}:{config.port}")
        logger.info(f"API endpoint: http://{config.host}:{config.port}/api")
        logger.info(f"WebSocket endpoint: ws://{config.host}:{config.port}/ws")
        logger.info("Press Ctrl+C to stop the server")
        
        # Wait for shutdown signal
        try:
            await stop_event.wait()
        except KeyboardInterrupt:
            logger.info("Received keyboard interrupt")
        
        # Stop server
        await server.stop()
        
    except ImportError as e:
        logger.error(f"Missing dependencies: {e}")
        logger.error("Please install required packages:")
        logger.error('  For SO101/SO100: pip install -e ".[webrtc,feetech]"')
        logger.error('  For Koch robots: pip install -e ".[webrtc,dynamixel]"')
        logger.error('  For mixed setup: pip install -e ".[webrtc,feetech,dynamixel]"')
        logger.error("  Or install manually: pip install aiohttp aiohttp-cors websockets")
        logger.error("  pip install aiortc  # Optional, for full WebRTC support")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error running server: {e}")
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="WebRTC Robot Server for LeRobot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run with SO101 leader-follower setup
  python -m lerobot.webrtc_server.run_server --example so101
  
  # Run with SO100 leader-follower setup  
  python -m lerobot.webrtc_server.run_server --example so100
  
  # Run with Koch leader-follower setup
  python -m lerobot.webrtc_server.run_server --example koch
  
  # Run with mixed robot types
  python -m lerobot.webrtc_server.run_server --example mixed
  
  # Run with custom configuration
  python -m lerobot.webrtc_server.run_server --config my_config.json
  
  # Run with default configuration
  python -m lerobot.webrtc_server.run_server --default
        """
    )
    
    parser.add_argument(
        "--config", 
        type=str,
        help="Path to configuration file (JSON format)"
    )
    
    parser.add_argument(
        "--example",
        choices=["so101", "so100", "koch", "mixed", "so101_macos"],
        help="Use a predefined example configuration"
    )
    
    parser.add_argument(
        "--default",
        action="store_true",
        help="Use default configuration"
    )
    
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Server host address (default: 0.0.0.0)"
    )
    
    parser.add_argument(
        "--port",
        type=int, 
        default=8080,
        help="Server port (default: 8080)"
    )
    
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging"
    )
    
    parser.add_argument(
        "--no-safety",
        action="store_true",
        help="Disable safety limits (use with caution!)"
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(args.debug)
    
    # Create configuration
    config = None
    
    if args.config:
        # Load from file
        config_path = Path(args.config)
        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path}")
            sys.exit(1)
        
        import json
        try:
            with open(config_path) as f:
                config_data = json.load(f)
            # TODO: Implement proper config loading from JSON
            logger.warning("JSON config loading not fully implemented yet")
            config = create_default_config()
        except Exception as e:
            logger.error(f"Error loading configuration: {e}")
            sys.exit(1)
    
    elif args.example:
        # Use example configuration
        if args.example == "so101":
            config = create_so101_example_config()
        elif args.example == "so100":
            config = create_so100_example_config()
        elif args.example == "koch":
            config = create_koch_example_config()
        elif args.example == "mixed":
            config = create_mixed_example_config()
        elif args.example == "so101_macos":
            config = create_so101_macos_config()
    
    elif args.default:
        # Use default configuration
        config = create_default_config()
    
    else:
        logger.error("Must specify --config, --example, or --default")
        parser.print_help()
        sys.exit(1)
    
    # Override host/port if specified
    if args.host != "0.0.0.0":
        config.host = args.host
    if args.port != 8080:
        config.port = args.port
    if args.debug:
        config.debug = True
    if args.no_safety:
        config.enable_safety_limits = False
        logger.warning("Safety limits disabled! Use with extreme caution.")
    
    # Print configuration
    logger.info(f"Server configuration:")
    logger.info(f"  Host: {config.host}")
    logger.info(f"  Port: {config.port}")
    logger.info(f"  Debug: {config.debug}")
    logger.info(f"  Safety limits: {config.enable_safety_limits}")
    logger.info(f"  Emergency stop: {config.emergency_stop_enabled}")
    logger.info(f"  Robots: {list(config.robots.keys())}")
    
    # Start server
    try:
        asyncio.run(run_server(config))
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main() 