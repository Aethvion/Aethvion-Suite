"""
Aethvion Suite - Package Intelligence System
Analyzes and maps system packages for integration
"""

import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any, Tuple
from core.utils import get_logger

logger = get_logger("workspace.package_intelligence")


@dataclass
class PackageInfo:
    """Comprehensive package metadata with safety rating."""
    
    name: str
    version: str
    description: str
    author: str
    
    # Popularity Metrics
    downloads_last_month: int = 0
    github_stars: int = 0
    
    # Age/Maturity
    first_release_date: Optional[datetime] = None
    last_release_date: Optional[datetime] = None
    total_releases: int = 0
    
    # Maintenance
    is_actively_maintained: bool = False
    
    # Dependencies
    dependencies: List[str] = field(default_factory=list)
    dependency_count: int = 0
    
    # Safety Rating (calculated)
    safety_score: float = 0.0
    safety_level: str = "UNKNOWN"
    safety_reasons: List[str] = field(default_factory=list)


class PackageIntelligence:
    """
    Fetches package metadata from PyPI and calculates safety ratings.
    
    Uses PyPI JSON API to gather comprehensive package information
    and applies a multi-factor algorithm to assess package safety.
    """
    
    PYPI_API_URL = "https://pypi.org/pypi/{package}/json"
    
    def __init__(self):
        """Initialize package intelligence system."""
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Misaka-Cipher-Package-Intelligence/1.0'
        })
        logger.info("Package Intelligence System initialized")
    
    def get_package_info(self, package_name: str) -> Optional[PackageInfo]:
        """
        Fetch comprehensive package information from PyPI.
        
        Args:
            package_name: Name of the package to analyze
            
        Returns:
            PackageInfo object with metadata and safety rating, or None if not found
        """
        try:
            logger.info(f"Fetching metadata for package: {package_name}")
            
            # Fetch from PyPI
            response = self.session.get(
                self.PYPI_API_URL.format(package=package_name),
                timeout=10
            )
            
            if response.status_code == 404:
                logger.warning(f"Package not found on PyPI: {package_name}")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            # Extract metadata
            info = self._parse_pypi_data(data, package_name)
            
            # Calculate safety rating
            info.safety_score, info.safety_level, info.safety_reasons = \
                self._calculate_safety_rating(info)
            
            logger.info(
                f"Package {package_name}: Safety={info.safety_level} "
                f"({info.safety_score:.0f}/100)"
            )
            
            return info
            
        except requests.RequestException as e:
            logger.error(f"Failed to fetch package info for {package_name}: {e}")
            return None
        except Exception as e:
            logger.error(f"Error processing package {package_name}: {e}")
            return None
    
    def _parse_pypi_data(self, data: Dict[str, Any], package_name: str) -> PackageInfo:
        """Parse PyPI JSON response into PackageInfo object."""
        
        info_section = data.get('info', {})
        releases = data.get('releases', {})
        
        # Basic info
        version = info_section.get('version', 'unknown')
        description = info_section.get('summary', 'No description available')
        author = info_section.get('author', 'Unknown')
        
        # Dependencies
        requires_dist = info_section.get('requires_dist', []) or []
        dependencies = [
            dep.split(';')[0].split('[')[0].strip()
            for dep in requires_dist
            if dep
        ]
        
        # Release dates
        release_dates = []
        for release_files in releases.values():
            if release_files:
                upload_time = release_files[0].get('upload_time_iso_8601')
                if upload_time:
                    try:
                        release_dates.append(
                            datetime.fromisoformat(upload_time.replace('Z', '+00:00'))
                        )
                    except ValueError:
                        continue
        
        release_dates.sort()
        first_release = release_dates[0] if release_dates else None
        last_release = release_dates[-1] if release_dates else None
        
        # Maintenance status
        is_maintained = False
        if last_release:
            days_since_update = (datetime.now(last_release.tzinfo) - last_release).days
            is_maintained = days_since_update <= 365
        
        # Note: PyPI doesn't provide download stats in JSON API
        # We'll use placeholder for now - can integrate with pypistats.org later
        downloads = 0
        
        return PackageInfo(
            name=package_name,
            version=version,
            description=description,
            author=author,
            downloads_last_month=downloads,
            github_stars=0,  # Would need to parse project_urls for GitHub link
            first_release_date=first_release,
            last_release_date=last_release,
            total_releases=len(releases),
            is_actively_maintained=is_maintained,
            dependencies=dependencies,
            dependency_count=len(dependencies)
        )
    
    def _calculate_safety_rating(
        self, 
        info: PackageInfo
    ) -> Tuple[float, str, List[str]]:
        """
        Calculate safety score based on multiple factors.
        
        Returns:
            Tuple of (score, level, reasons)
            - score: 0-100 (higher = safer)
            - level: "HIGH", "MEDIUM", "LOW", "UNKNOWN"
            - reasons: List of explanation strings
        """
        score = 0.0
        reasons = []
        
        # Age Factor (max 25 points)
        if info.first_release_date:
            age_years = (datetime.now(info.first_release_date.tzinfo) - info.first_release_date).days / 365
            if age_years >= 5:
                score += 25
                reasons.append("✓ Established package (5+ years)")
            elif age_years >= 2:
                score += 15
                reasons.append("⚠ Moderately mature (2-5 years)")
            else:
                score += 5
                reasons.append("⚠ New package (< 2 years)")
        else:
            reasons.append("⚠ Unknown age")
        
        # Popularity Factor (max 30 points)
        # Note: Currently placeholder - would need pypistats.org integration
        if info.downloads_last_month >= 1_000_000:
            score += 30
            reasons.append("✓ Very popular (1M+ downloads/month)")
        elif info.downloads_last_month >= 100_000:
            score += 20
            reasons.append("✓ Popular (100K+ downloads/month)")
        elif info.downloads_last_month >= 10_000:
            score += 10
            reasons.append("⚠ Moderate usage (10K+ downloads/month)")
        else:
            # Give some points for existence on PyPI
            score += 5
            reasons.append("ℹ Download stats unavailable")
        
        # Maintenance Factor (max 25 points)
        if info.last_release_date:
            days_since_update = (datetime.now(info.last_release_date.tzinfo) - info.last_release_date).days
            if days_since_update <= 180:  # 6 months
                score += 25
                reasons.append("✓ Recently updated (< 6 months)")
            elif days_since_update <= 365:
                score += 15
                reasons.append("⚠ Updated within year")
            else:
                score += 5
                reasons.append("⚠ Not recently updated (> 1 year)")
        else:
            reasons.append("⚠ Unknown update status")
        
        # Release Frequency (max 20 points)
        if info.total_releases >= 50:
            score += 20
            reasons.append("✓ Many releases (50+)")
        elif info.total_releases >= 20:
            score += 15
            reasons.append("✓ Regular releases (20+)")
        elif info.total_releases >= 5:
            score += 10
            reasons.append("⚠ Few releases (5-20)")
        else:
            score += 0
            reasons.append("⚠ Very few releases (< 5)")
        
        # Determine level
        if score >= 75:
            level = "HIGH"
        elif score >= 50:
            level = "MEDIUM"
        elif score >= 25:
            level = "LOW"
        else:
            level = "UNKNOWN"
        
        return score, level, reasons


# Singleton instance
_intelligence = None

def get_package_intelligence() -> PackageIntelligence:
    """Get the singleton PackageIntelligence instance."""
    global _intelligence
    if _intelligence is None:
        _intelligence = PackageIntelligence()
    return _intelligence
