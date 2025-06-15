# LeRobot WebRTC Server

A real-time web-based interface for controlling LeRobot leader and follower robots over the internet using WebRTC and WebSocket technologies.

## Features

- **Real-time Robot Control**: Send actions to both leader and follower robots with low latency
- **Web-based Interface**: Control robots from any web browser without installing additional software  
- **Multi-Robot Support**: Manage multiple robots simultaneously (SO101, SO100, Koch, etc.)
- **Safety Features**: Built-in action validation, safety limits, and emergency stop functionality
- **RESTful API**: Full HTTP API for integration with other systems
- **WebSocket Communication**: Real-time bidirectional communication for responsive control
- **Action Validation**: Comprehensive validation of robot actions before execution
- **Robot Status Monitoring**: Real-time status updates for all connected robots

## Architecture

The WebRTC server acts as a bridge between web clients and physical robots:

```
Web Browser ←→ WebRTC Server ←→ Robot Manager ←→ Leader/Follower Robots
     ↑              ↑                ↑                    ↑
   WebRTC/WS    HTTP API        Robot Classes      Physical Hardware
```

### Key Components

- **WebRTC Server**: Main server handling web connections and robot communication
- **Robot Manager**: Manages connections and routes actions to appropriate robots
- **Action Validator**: Validates and sanitizes robot actions for safety
- **Configuration System**: Flexible configuration for different robot setups

## Installation

### Prerequisites

```bash
# Install WebRTC dependencies for lerobot
pip install -e ".[webrtc]"

# Install robot-specific dependencies based on your hardware:
# For SO101/SO100 robots (uses Feetech servos)
pip install -e ".[webrtc,feetech]"

# For Koch robots (uses Dynamixel servos)  
pip install -e ".[webrtc,dynamixel]"

# Or install dependencies directly
pip install aiohttp>=3.8.0 aiohttp-cors>=0.7.0 websockets>=10.0
pip install feetech-servo-sdk>=1.0.0  # For SO101/SO100
pip install dynamixel-sdk>=3.7.31     # For Koch

# Optional for full WebRTC functionality (peer-to-peer connections)
pip install aiortc
```

### Basic Setup

1. Clone the lerobot repository and navigate to the webrtc_server directory
2. Install dependencies as shown above
3. Configure your robot connections (see Configuration section)
4. Start the server

## Quick Start

### 1. Install Dependencies & Run Example

```bash
# For SO101 robots - install WebRTC + Feetech dependencies
pip install -e ".[webrtc,feetech]"
python -m lerobot.webrtc_server.run_server --example so101

# For SO100 robots - install WebRTC + Feetech dependencies  
pip install -e ".[webrtc,feetech]"
python -m lerobot.webrtc_server.run_server --example so100

# For Koch robots - install WebRTC + Dynamixel dependencies
pip install -e ".[webrtc,dynamixel]"
python -m lerobot.webrtc_server.run_server --example koch

# For mixed robot types - install all dependencies
pip install -e ".[webrtc,feetech,dynamixel]"
python -m lerobot.webrtc_server.run_server --example mixed
```

### 2. Access Web Interface

Open your browser and navigate to:
- **Web Interface**: `http://localhost:8080`
- **API Documentation**: `http://localhost:8080/api/status`

### 3. Control Robots

- Connect to robots using the web interface
- Send actions via the built-in controls
- Monitor robot status in real-time
- Use emergency stop if needed

## Configuration

### Example Robot Configuration

```python
from lerobot.webrtc_server.config.server_config import WebRTCServerConfig, RobotConnectionConfig

config = WebRTCServerConfig(
    host="0.0.0.0",
    port=8080,
    enable_safety_limits=True,
    emergency_stop_enabled=True
)

# Add SO101 leader
config.add_robot("so101_leader", RobotConnectionConfig(
    robot_type="leader",
    robot_class="so101_leader",
    port="/dev/ttyUSB0",
    id="my_leader_arm"
))

# Add SO101 follower  
config.add_robot("so101_follower", RobotConnectionConfig(
    robot_type="follower",
    robot_class="so101_follower", 
    port="/dev/ttyUSB1",
    id="my_follower_arm"
))
```

### Supported Robot Types

#### Leaders (Teleoperation)
- `so101_leader` - SO-101 Leader Arm
- `so100_leader` - SO-100 Leader Arm  
- `koch_leader` - Koch Leader Arm

#### Followers (Action Execution)
- `so101_follower` - SO-101 Follower Arm
- `so100_follower` - SO-100 Follower Arm
- `koch_follower` - Koch Follower Arm

## API Reference

### REST API Endpoints

#### Robot Management
```http
GET    /api/robots                           # List all robots
GET    /api/robots/{name}/status             # Get robot status
POST   /api/robots/{name}/connect            # Connect to robot
POST   /api/robots/{name}/disconnect         # Disconnect from robot
```

#### Action Control  
```http
POST   /api/robots/{name}/action             # Send action to robot
GET    /api/robots/{name}/action             # Get action from leader robot
```

#### System Control
```http
GET    /api/status                           # Get server status
POST   /api/emergency_stop                   # Emergency stop all robots
```

### WebSocket Communication

Connect to `ws://localhost:8080/ws` for real-time communication.

#### Message Format
```json
{
  "type": "robot_action",
  "robot": "robot_name", 
  "action": {
    "delta_x": 0.1,
    "delta_y": 0.0,
    "delta_z": 0.0,
    "gripper": 1.0
  }
}
```

## Action Formats

### End-Effector Actions (Most Common)
```json
{
  "delta_x": 0.1,    # X-axis movement (-1.0 to 1.0)
  "delta_y": 0.0,    # Y-axis movement (-1.0 to 1.0) 
  "delta_z": 0.0,    # Z-axis movement (-1.0 to 1.0)
  "gripper": 1.0     # Gripper: 0=close, 1=stay, 2=open
}
```

### Joint Position Actions
```json
{
  "shoulder_pan.pos": 45.0,
  "shoulder_lift.pos": -30.0,
  "elbow_flex.pos": 90.0,
  "wrist_flex.pos": 0.0,
  "wrist_roll.pos": 0.0,
  "gripper.pos": 50.0
}
```

## Safety Features

### Action Validation
- **Range Checking**: Ensures actions are within safe robot limits
- **Delta Validation**: Prevents sudden large movements that could damage robots
- **Type Validation**: Verifies action format and data types
- **Robot-Specific Limits**: Different safety limits for different robot types

### Emergency Controls
- **Emergency Stop**: Immediately stops and disconnects all robots
- **Connection Timeouts**: Automatically disconnects inactive connections
- **Safety Limits**: Configurable limits that can be enabled/disabled

### Usage Guidelines
- Always test with safety limits enabled first
- Use emergency stop if robots behave unexpectedly
- Start with small action values and increase gradually
- Monitor robot status continuously during operation

## Troubleshooting

### Common Issues

#### Connection Problems
```bash
# Check USB ports
ls /dev/ttyUSB* /dev/ttyACM*

# Check permissions
sudo chmod 666 /dev/ttyUSB0

# Test robot connection
python -m lerobot.calibrate --robot.port=/dev/ttyUSB0
```

#### Server Issues
```bash
# Check if port is in use
netstat -tulpn | grep :8080

# Run with debug logging
python -m lerobot.webrtc_server.run_server --example so101 --debug

# Check server logs
tail -f webrtc_server.log
```

#### Robot Issues
- **Missing scservo_sdk**: Install Feetech dependencies with `pip install -e ".[feetech]"`
- **Missing dynamixel_sdk**: Install Dynamixel dependencies with `pip install -e ".[dynamixel]"`
- Ensure robots are calibrated before use
- Check that robot IDs match configuration
- Verify robot firmware is compatible
- Test robots with standard lerobot tools first

### Error Messages

| Error | Solution |
|-------|----------|
| `No module named 'scservo_sdk'` | Install Feetech dependencies: `pip install -e ".[feetech]"` |
| `No module named 'dynamixel_sdk'` | Install Dynamixel dependencies: `pip install -e ".[dynamixel]"` |
| `Robot not found` | Check robot name in configuration |
| `Device not connected` | Call connect API first |
| `Invalid action` | Check action format and values |
| `Port not found` | Verify USB connection and port path |
| `Permission denied` | Run `sudo chmod 666 /dev/ttyUSB*` |

## Development

### Adding New Robot Types

1. Create robot class inheriting from `Robot` or `Teleoperator`
2. Add to `ROBOT_REGISTRY` in `robot_manager.py`
3. Update action validator with robot-specific limits
4. Test with example configuration

### Custom Clients

Use the WebSocket API to create custom clients:

```javascript
const ws = new WebSocket('ws://localhost:8080/ws');

ws.onopen = function() {
    // Send robot action
    ws.send(JSON.stringify({
        type: 'robot_action',
        robot: 'so101_follower',
        action: {
            delta_x: 0.1,
            delta_y: 0.0, 
            delta_z: 0.0
        }
    }));
};
```

## Examples

### Basic Usage
```bash
# Start server with SO101 setup
python -m lerobot.webrtc_server.run_server --example so101

# In another terminal, test API
curl http://localhost:8080/api/robots

# Connect to follower
curl -X POST http://localhost:8080/api/robots/so101_follower/connect

# Send action
curl -X POST http://localhost:8080/api/robots/so101_follower/action \
  -H "Content-Type: application/json" \
  -d '{"delta_x": 0.1, "delta_y": 0.0, "delta_z": 0.0}'
```

### Leader-Follower Teleoperation
```bash
# Start server
python -m lerobot.webrtc_server.run_server --example so101

# Connect both robots via web interface
# Move leader manually to control follower
# Or get leader actions programmatically:
curl http://localhost:8080/api/robots/so101_leader/action
```

## Contributing

1. Follow existing code patterns and documentation style
2. Add tests for new functionality  
3. Update README with new features
4. Ensure safety features are maintained
5. Test with actual robot hardware when possible

## License

Licensed under the Apache License, Version 2.0. See LICENSE file for details. 