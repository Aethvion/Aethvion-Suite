"""
Aethvion Suite - Package Installer Worker
Background worker for async package installation
"""

import time
import threading
from typing import List, Dict, Any
from pathlib import Path
from core.utils import get_logger

logger = get_logger(__name__)


class PackageInstallerWorker:
    """
    Background worker for package installation.
    
    Runs in a separate thread, periodically checks for approved packages
    and installs them without blocking the main application.
    """
    
    def __init__(self, check_interval: int = 5):
        """
        Initialize package installer worker.
        
        Args:
            check_interval: Seconds between checks for approved packages
        """
        self.check_interval = check_interval
        self.thread = None
        self.running = False
        self.installed_packages: List[str] = []
        logger.info("Package Installer Worker initialized")
    
    def start(self):
        """Start the background worker thread."""
        if self.running:
            logger.warning("Worker already running")
            return
        
        self.running = True
        self.thread = threading.Thread(target=self._worker_loop, daemon=True)
        self.thread.start()
        logger.info("Package Installer Worker started")
    
    def stop(self):
        """Stop the background worker thread."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=10)
        logger.info("Package Installer Worker stopped")
    
    def _worker_loop(self):
        """Main worker loop - runs in background thread."""
        logger.info("Worker loop started")
        
        while self.running:
            try:
                # Check for approved packages
                installed = self._check_and_install()
                
                if installed:
                    self.installed_packages.extend(installed)
                    logger.info(f"Installed packages: {installed}")
                    
                    # Broadcast to WebSocket clients
                    self._broadcast_installation(installed)
                
            except Exception as e:
                logger.error(f"Error in worker loop: {e}")
            
            # Sleep before next check
            time.sleep(self.check_interval)
    
    def _check_and_install(self) -> List[str]:
        """
        Check for approved packages and install them.
        
        Returns:
            List of successfully installed package names
        """
        try:
            from core.workspace.package_manager import get_package_manager
            package_manager = get_package_manager()
            
            # Get approved packages (not yet installed)
            approved = package_manager.get_approved_packages()
            
            if not approved:
                return []
            
            logger.info(f"Found {len(approved)} approved packages to install")
            
            installed = []
            for package_name in approved:
                try:
                    # Install package
                    success = package_manager.install_package(package_name)
                    
                    if success:
                        installed.append(package_name)
                        logger.info(f"✓ Installed: {package_name}")
                    else:
                        logger.error(f"✗ Failed to install: {package_name}")
                        self._broadcast_event(package_name, "package_failed", error="Installation failed")
                        
                except Exception as e:
                    logger.error(f"Error installing {package_name}: {e}")
                    self._broadcast_event(package_name, "package_failed", error=str(e))
            
            return installed
            
        except Exception as e:
            logger.error(f"Error checking for approved packages: {e}")
            return []
    
    def _broadcast_event(self, package_name: str, event_type: str, error: str = None):
        """
        Broadcast package event to WebSocket clients.
        
        Args:
            package_name: Name of the package
            event_type: 'package_installed' or 'package_failed'
            error: Optional error message
        """
        try:
            # Import here to avoid circular dependency
            import asyncio
            from core.interfaces.dashboard.server import manager, main_event_loop
            
            if not main_event_loop:
                return

            message = {
                'type': event_type,
                'package': package_name,
                'timestamp': time.time()
            }
            if error:
                message['error'] = error

            # Broadcast to chat/main channel so app.js picks it up
            asyncio.run_coroutine_threadsafe(
                manager.broadcast(message, "chat"), 
                main_event_loop
            )
                
        except Exception as e:
            logger.warning(f"Could not broadcast event {event_type}: {e}")
    
    def is_alive(self) -> bool:
        """Check if worker thread is alive."""
        return self.thread is not None and self.thread.is_alive()
    
    def get_status(self) -> Dict[str, Any]:
        """Get worker status."""
        return {
            'running': self.running,
            'alive': self.is_alive(),
            'installed_count': len(self.installed_packages),
            'last_installed': self.installed_packages[-5:] if self.installed_packages else []
        }


# Singleton instance
_installer_worker = None

def get_installer_worker() -> PackageInstallerWorker:
    """Get the singleton PackageInstallerWorker instance."""
    global _installer_worker
    if _installer_worker is None:
        _installer_worker = PackageInstallerWorker()
    return _installer_worker
