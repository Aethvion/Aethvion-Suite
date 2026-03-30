"""
Aethvion Suite - Package Management API Routes
FastAPI routes for package management operations
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
from core.utils import get_logger

logger = get_logger("web.package_routes")

# Create router
router = APIRouter(prefix="/api/packages", tags=["packages"])


@router.get("/all")
async def get_all_packages():
    """Get all packages (pending, approved, installed, denied)."""
    from core.workspace.package_manager import get_package_manager
    
    try:
        manager = get_package_manager()
        packages = manager.get_all_package_info()
        return {"packages": packages}
    except Exception as e:
        logger.error(f"Error fetching all packages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/pending")
async def get_pending_packages():
    """Get all pending package requests with metadata."""
    from core.workspace.package_manager import get_package_manager
    
    try:
        manager = get_package_manager()
        pending = manager.get_pending_requests()
        
        return {
            "pending": [
                {
                    "name": req.package_name,
                    "requested_by": req.requested_by,
                    "reason": req.reason,
                    "requested_at": req.requested_at,
                    "status": req.status,
                    "metadata": req.metadata
                }
                for req in pending
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching pending packages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/installed")
async def get_installed_packages():
    """Get all installed packages."""
    from core.workspace.package_manager import get_package_manager
    
    try:
        manager = get_package_manager()
        installed = manager.get_installed_packages()
        
        return {
            "installed": [
                {"name": name, "version": version}
                for name, version in installed.items()
            ]
        }
    except Exception as e:
        logger.error(f"Error fetching installed packages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/denied")
async def get_denied_packages():
    """Get all denied packages."""
    from core.workspace.package_manager import get_package_manager
    
    try:
        manager = get_package_manager()
        denied = manager.get_denied_packages()
        
        return {"denied": denied}
    except Exception as e:
        logger.error(f"Error fetching denied packages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/approve/{package_name}")
async def approve_package(package_name: str):
    """Approve and install a package."""
    from core.workspace.package_manager import get_package_manager
    
    try:
        manager = get_package_manager()
        success = manager.approve_package(package_name)
        
        if success:
            logger.info(f"Package {package_name} approved and installed")
            return {"success": True, "message": f"Package {package_name} installed successfully"}
        else:
            logger.warning(f"Failed to install package {package_name}")
            return {"success": False, "message": f"Failed to install {package_name}"}
            
    except Exception as e:
        logger.error(f"Error approving package {package_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/deny/{package_name}")
async def deny_package(package_name: str):
    """Deny a package request."""
    from core.workspace.package_manager import get_package_manager
    
    try:
        manager = get_package_manager()
        manager.deny_package(package_name)
        
        logger.info(f"Package {package_name} denied")
        return {"success": True, "message": f"Package {package_name} denied"}
        
    except Exception as e:
        logger.error(f"Error denying package {package_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/info/{package_name}")
async def get_package_info(package_name: str):
    """Get detailed information about a package from PyPI."""
    from core.workspace.package_intelligence import get_package_intelligence
    
    try:
        intelligence = get_package_intelligence()
        info = intelligence.get_package_info(package_name)
        
        if not info:
            raise HTTPException(status_code=404, detail=f"Package {package_name} not found on PyPI")
        
        return {
            "name": info.name,
            "version": info.version,
            "description": info.description,
            "author": info.author,
            "downloads_last_month": info.downloads_last_month,
            "github_stars": info.github_stars,
            "first_release": info.first_release_date.isoformat() if info.first_release_date else None,
            "last_release": info.last_release_date.isoformat() if info.last_release_date else None,
            "total_releases": info.total_releases,
            "is_actively_maintained": info.is_actively_maintained,
            "dependencies": info.dependencies,
            "dependency_count": info.dependency_count,
            "safety_score": info.safety_score,
            "safety_level": info.safety_level,
            "safety_reasons": info.safety_reasons
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching package info for {package_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/sync")
async def sync_packages():
    """Sync installed packages with package manager."""
    from core.workspace.package_manager import get_package_manager
    
    try:
        manager = get_package_manager()
        count = manager.sync_installed_packages()
        return {"success": True, "count": count, "message": f"Synced {count} new packages"}
    except Exception as e:
        logger.error(f"Error syncing packages: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/uninstall/{package_name}")
async def uninstall_package(package_name: str):
    """Uninstall a package."""
    from core.workspace.package_manager import get_package_manager
    
    try:
        manager = get_package_manager()
        success = manager.uninstall_package(package_name)
        
        if success:
            return {"success": True, "message": f"Package {package_name} uninstalled"}
        else:
            return {"success": False, "message": f"Failed to uninstall {package_name}"}
            
    except Exception as e:
        logger.error(f"Error uninstalling package {package_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/retry/{package_name}")
async def retry_package(package_name: str):
    """Retry a failed or uninstalled package."""
    from core.workspace.package_manager import get_package_manager
    
    try:
        manager = get_package_manager()
        success = manager.retry_package(package_name)
        
        if success:
            return {"success": True, "message": f"Package {package_name} queued for retry"}
        else:
            return {"success": False, "message": f"Failed to queue {package_name} for retry"}
            
    except Exception as e:
        logger.error(f"Error retrying package {package_name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
