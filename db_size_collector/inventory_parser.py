#!/usr/bin/env python3
"""
Database Size Collector - Inventory Parser
Parses Ansible inventory YAML files to extract host information.
"""

import os
import yaml
import logging
from typing import Dict, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class InventoryParser:
    """Parse Ansible inventory files for database hosts."""
    
    PLATFORM_FILES = {
        'oracle': 'oracle_hosts.yml',
        'mysql': 'mysql_hosts.yml',
        'mongo': 'mongo_hosts.yml',
        'postgres': 'postgres_hosts.yml',
        'cassandra': 'cassandra_hosts.yml',
        'mssql': 'mssql_hosts.yml'
    }
    
    def __init__(self, inventory_path: str):
        """
        Initialize with path to inventory directory.
        
        Args:
            inventory_path: Path to the directory containing host files
        """
        self.inventory_path = Path(inventory_path)
        if not self.inventory_path.exists():
            raise FileNotFoundError(f"Inventory path not found: {inventory_path}")
    
    def _load_yaml(self, filepath: Path) -> Optional[Dict]:
        """Load and parse a YAML file."""
        try:
            with open(filepath, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}")
            return None
    
    def _extract_hosts(self, data: Dict, platform: str) -> List[Dict]:
        """Extract host information from inventory structure."""
        hosts = []
        
        if not data or 'all' not in data:
            return hosts
        
        def process_group(group_data: Dict, environment: str = 'PROD'):
            """Recursively process host groups."""
            if not group_data:
                return
            
            # Process hosts in this group
            if 'hosts' in group_data and group_data['hosts']:
                for hostname, host_vars in group_data['hosts'].items():
                    if host_vars is None:
                        host_vars = {}
                    
                    host_info = {
                        'hostname': hostname,
                        'environment': environment,
                        **host_vars
                    }
                    hosts.append(host_info)
            
            # Process child groups
            if 'children' in group_data and group_data['children']:
                for child_name, child_data in group_data['children'].items():
                    # Determine environment from group name
                    child_env = environment
                    child_lower = child_name.lower()
                    if 'prod' in child_lower or 'prd' in child_lower:
                        child_env = 'PROD'
                    elif 'uat' in child_lower or 'test' in child_lower or 'dev' in child_lower:
                        child_env = 'UAT'
                    
                    process_group(child_data, child_env)
        
        # Start processing from 'all' group
        process_group(data.get('all', {}))
        
        return hosts
    
    def get_hosts(self, platform: str) -> List[Dict]:
        """
        Get all hosts for a specific platform.
        
        Args:
            platform: One of: oracle, mysql, mongo, postgres, cassandra, mssql
        
        Returns:
            List of host dictionaries with all their variables
        """
        if platform not in self.PLATFORM_FILES:
            raise ValueError(f"Unknown platform: {platform}. Valid: {list(self.PLATFORM_FILES.keys())}")
        
        filename = self.PLATFORM_FILES[platform]
        filepath = self.inventory_path / filename
        
        if not filepath.exists():
            logger.warning(f"Inventory file not found: {filepath}")
            return []
        
        data = self._load_yaml(filepath)
        if not data:
            return []
        
        hosts = self._extract_hosts(data, platform)
        logger.info(f"Loaded {len(hosts)} hosts for {platform}")
        
        return hosts
    
    def get_all_hosts(self) -> Dict[str, List[Dict]]:
        """
        Get hosts for all platforms.
        
        Returns:
            Dictionary with platform names as keys and host lists as values
        """
        all_hosts = {}
        
        for platform in self.PLATFORM_FILES.keys():
            hosts = self.get_hosts(platform)
            if hosts:
                all_hosts[platform] = hosts
        
        return all_hosts
    
    def get_host_count(self) -> Dict[str, int]:
        """Get count of hosts per platform."""
        counts = {}
        for platform in self.PLATFORM_FILES.keys():
            hosts = self.get_hosts(platform)
            counts[platform] = len(hosts)
        return counts


def parse_inventory(inventory_path: str) -> Dict[str, List[Dict]]:
    """
    Convenience function to parse inventory.
    
    Args:
        inventory_path: Path to inventory directory
    
    Returns:
        Dictionary of platform -> hosts list
    """
    parser = InventoryParser(inventory_path)
    return parser.get_all_hosts()


if __name__ == '__main__':
    # Test the parser
    import sys
    
    if len(sys.argv) > 1:
        inv_path = sys.argv[1]
    else:
        # Default to MTN inventory
        inv_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'ansible/inventory/mtn_databases'
        )
    
    print(f"Parsing inventory from: {inv_path}")
    
    parser = InventoryParser(inv_path)
    
    print("\nHost counts:")
    for platform, count in parser.get_host_count().items():
        print(f"  {platform}: {count}")
    
    print("\nSample hosts:")
    all_hosts = parser.get_all_hosts()
    for platform, hosts in all_hosts.items():
        if hosts:
            print(f"\n{platform.upper()}:")
            for host in hosts[:3]:  # Show first 3
                print(f"  - {host.get('hostname', 'unknown')}: {host.get('ansible_host', 'N/A')}")
