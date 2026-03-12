# Synapse Module

Synapse is the dedicated face and body tracking module for the Misaka Cipher ecosystem. 
It streams real-time tracking parameters to other connected modules (like Specter) acting as a secure and fast bridge.

## Architecture

Synapse supports a pluggable tracker architecture. You can dynamically switch between different tracking backends (e.g., MediaPipe, OpenSeeFace, generic webcam trackers) depending on the desired performance and hardware capabilities.

### Components

- **`synapse_core.py`**: The main interface to manage, start, stop, and switch tracking backends.
- **`bridge.py`**: The integration layer that defines schemas and routing callbacks to distribute data (e.g., WebSocket streaming or direct Python callbacks).
- **`trackers/`**: The folder containing all the pluggable backends inheriting from `BaseTracker`.

## Connecting to Specter

Synapse mimics the generic VTube parameter model in its output, making it instantly compatible with Specter's VTuber engine overlay.
