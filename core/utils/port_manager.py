import os
import json
import socket
from pathlib import Path
from core.utils.paths import PORTS_JSON, PORTS_LOCK, SYSTEM

DATA_DIR = SYSTEM
REGISTRY_FILE = PORTS_JSON

class PortManager:
    @staticmethod
    def _ensure_registry_exists():
        if not DATA_DIR.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
        if not REGISTRY_FILE.exists():
            with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
                json.dump({}, f)

    @staticmethod
    def _is_port_in_use(port: int) -> bool:
        """Check if a port is physically bound by any application."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                # 0 means the port is available (connection refused)
                # If it successfully connects, the port is IN USE
                return s.connect_ex(('127.0.0.1', port)) == 0
            except Exception:
                return True

    @classmethod
    def get_registered_ports(cls, perform_cleanup: bool = True) -> dict:
        cls._ensure_registry_exists()
        registry = {}
        try:
            with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
                registry = json.load(f)
        except Exception:
            registry = {}

        if not perform_cleanup:
            return registry

        # Cleanup logic: remove ports that are no longer physically in use
        stale_found = False
        for port_str in list(registry.keys()):
            try:
                if not cls._is_port_in_use(int(port_str)):
                    del registry[port_str]
                    stale_found = True
            except (ValueError, TypeError):
                del registry[port_str]
                stale_found = True

        if stale_found:
            try:
                with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
                    json.dump(registry, f, indent=4)
            except Exception:
                pass

        return registry

    @classmethod
    def get_port_from_env(cls, env_var: str, default: int) -> int:
        """Helper to get a port specified in environment variables."""
        return int(os.environ.get(env_var, default))

    @classmethod
    def bind_port(cls, module_name: str, preferred_port: int, port_range: tuple = (8080, 8100)) -> int:
        """
        Attempt to register the preferred_port. If it's physically in use or
        registered by someone else, scan upwards within port_range until an open port is found.
        Registers the allocated port in ports.json and returns it.
        """
        cls._ensure_registry_exists()
        
        lock_file = PORTS_LOCK
        import time as pytime
        
        # Simple retry-based file locking
        locked = False
        for _ in range(50): # Try for 5 seconds
            try:
                if not lock_file.exists():
                    lock_file.write_text(str(os.getpid()))
                    locked = True
                    break
            except:
                pass
            pytime.sleep(0.1)
            
        try:
            registry = cls.get_registered_ports()
            
            # We need to scrub the registry for stale instances of this module
            stale_ports = [p for p, m in registry.items() if m == module_name]
            for sp in stale_ports:
                del registry[sp]

            target_port = preferred_port
            min_port, max_port = port_range

            while target_port <= max_port:
                if not cls._is_port_in_use(target_port):
                    # Bind it in registry
                    registry[str(target_port)] = module_name
                    try:
                        with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
                            json.dump(registry, f, indent=4)
                        print(f"[{module_name}] Assigned dynamic port: {target_port}")
                        return target_port
                    except Exception as e:
                        print(f"ERROR writing to port registry: {e}")
                        return target_port
                
                target_port += 1
                
            return preferred_port
        finally:
            if locked and lock_file.exists():
                try:
                    lock_file.unlink()
                except:
                    pass

    @classmethod
    def release_port(cls, port: int):
        """Release a port from the registry on shutdown."""
        cls._ensure_registry_exists()
        registry = cls.get_registered_ports()
        str_port = str(port)
        if str_port in registry:
            del registry[str_port]
            try:
                with open(REGISTRY_FILE, "w", encoding="utf-8") as f:
                    json.dump(registry, f, indent=4)
            except Exception:
                pass
