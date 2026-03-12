"""
Database Size Collector Package

Collects database sizes from multiple platforms and stores in Oracle.
"""

from .collectors import (
    SizeResult,
    OracleCollector,
    MySQLCollector,
    MongoCollector,
    PostgresCollector,
    CassandraCollector,
    MSSQLCollector
)
from .inventory_parser import InventoryParser, parse_inventory
from .storage import OracleStorage, create_storage

__version__ = '1.0.0'
__author__ = 'MTN DBA Team'

__all__ = [
    'SizeResult',
    'OracleCollector',
    'MySQLCollector',
    'MongoCollector',
    'PostgresCollector',
    'CassandraCollector',
    'MSSQLCollector',
    'InventoryParser',
    'parse_inventory',
    'OracleStorage',
    'create_storage'
]
