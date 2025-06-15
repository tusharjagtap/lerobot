#!/usr/bin/env python
"""
Test script to diagnose robot connection issues.

This script helps verify if the robot connection is stable and identifies
where the connection status issue might be occurring.
"""

import asyncio
import logging
import time
from lerobot.common.teleoperators.so101_leader import SO101Leader, SO101LeaderConfig

# Set up logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_robot_connection():
    """Test robot connection and monitor its status."""
    
    # Configure your robot port
    ROBOT_PORT = "/dev/tty.usbmodem585A0078841"  # Update this to match your actual port
    
    logger.info("🔧 Starting robot connection test...")
    
    # Create robot configuration
    config = SO101LeaderConfig(
        port=ROBOT_PORT,
        id="test_leader"
    )
    
    # Create robot instance
    robot = SO101Leader(config)
    
    logger.info(f"📱 Created robot with port: {ROBOT_PORT}")
    logger.info(f"🔍 Initial connection state: {robot.is_connected}")
    
    try:
        # Test connection
        logger.info("🔌 Attempting to connect to robot...")
        robot.connect(calibrate=False)  # Skip calibration for faster testing
        
        logger.info(f"✅ Connect() completed. Connection state: {robot.is_connected}")
        
        if hasattr(robot, 'bus'):
            logger.info(f"🚌 Bus connection state: {robot.bus.is_connected}")
        
        # Monitor connection for 30 seconds
        logger.info("👀 Monitoring connection status for 30 seconds...")
        
        for i in range(30):
            robot_connected = robot.is_connected
            bus_connected = robot.bus.is_connected if hasattr(robot, 'bus') else "N/A"
            
            status_msg = f"[{i+1:2d}/30] Robot: {robot_connected}, Bus: {bus_connected}"
            
            if robot_connected:
                logger.info(f"✅ {status_msg}")
                
                # Try to read an action to verify connection is working
                try:
                    action = robot.get_action()
                    logger.debug(f"📖 Read action: {action}")
                except Exception as e:
                    logger.warning(f"⚠️  Failed to read action: {e}")
                    
            else:
                logger.error(f"❌ {status_msg}")
            
            await asyncio.sleep(1)
        
        logger.info("✅ Connection monitoring completed")
        
    except Exception as e:
        logger.error(f"❌ Error during connection test: {e}")
        
    finally:
        # Cleanup
        try:
            if robot.is_connected:
                logger.info("🔌 Disconnecting robot...")
                robot.disconnect()
                logger.info(f"🔍 Final connection state: {robot.is_connected}")
        except Exception as e:
            logger.error(f"❌ Error during disconnect: {e}")

async def test_webrtc_integration():
    """Test robot connection through WebRTC server components."""
    from lerobot.webrtc_server.utils.robot_manager import RobotManager
    from lerobot.webrtc_server.config.server_config import WebRTCServerConfig, RobotConnectionConfig
    
    logger.info("🌐 Testing WebRTC integration...")
    
    # Create server config
    config = WebRTCServerConfig()
    config.add_robot("leader", RobotConnectionConfig(
        robot_type="leader",
        robot_class="so101_leader",
        port="/dev/tty.usbmodem585A0078841",  # Update this
        id="test_leader"
    ))
    
    # Create robot manager
    manager = RobotManager(config)
    
    try:
        # Initialize robots
        await manager.initialize_robots()
        logger.info("✅ Robot manager initialized")
        
        # Test connection
        logger.info("🔌 Connecting through robot manager...")
        success = await manager.connect_robot("leader", calibrate=False)
        logger.info(f"🔍 Connection result: {success}")
        
        # Check status multiple times
        for i in range(10):
            status = await manager.get_robot_status("leader")
            logger.info(f"[{i+1:2d}/10] Status: {status}")
            await asyncio.sleep(2)
            
    except Exception as e:
        logger.error(f"❌ WebRTC integration test failed: {e}")
    
    finally:
        await manager.cleanup()

if __name__ == "__main__":
    print("🤖 Robot Connection Diagnostic Tool")
    print("=" * 50)
    
    # Test 1: Direct robot connection
    print("\n1️⃣ Testing direct robot connection...")
    asyncio.run(test_robot_connection())
    
    # Test 2: WebRTC integration
    print("\n2️⃣ Testing WebRTC integration...")
    asyncio.run(test_webrtc_integration())
    
    print("\n✅ All tests completed!")
    print("\nIf you see connection drops or errors, please share the output for further diagnosis.") 