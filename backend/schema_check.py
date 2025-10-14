#!/usr/bin/env python3

import sqlite3
import json
from datetime import datetime

def get_database_schema():
    print("=== DATABASE SCHEMA INSPECTION ===")
    
    conn = sqlite3.connect("email_verifier.db")
    cursor = conn.cursor()
    
    try:
        # Get all tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = cursor.fetchall()
        
        print("📋 TABLES FOUND:")
        for table_name in tables:
            table = table_name[0]
            print(f"\n🔍 {table}:")
            
            # Get detailed column info
            cursor.execute(f"PRAGMA table_info({table})")
            columns = cursor.fetchall()
            
            for col in columns:
                col_id, col_name, col_type, not_null, default_val, primary_key = col
                indicators = []
                if primary_key:
                    indicators.append("PK")
                if not_null:
                    indicators.append("NOT NULL")
                
                indicator_str = f" ({', '.join(indicators)})" if indicators else ""
                print(f"  {col_name}: {col_type}{indicator_str}")
                
            # Show sample data
            try:
                cursor.execute(f"SELECT COUNT(*) FROM {table}")
                count = cursor.fetchone()[0]
                print(f"  Records: {count}")
                
                if count > 0:
                    cursor.execute(f"SELECT * FROM {table} LIMIT 1")
                    sample = cursor.fetchone()
                    column_names = [desc[0] for desc in cursor.description]
                    
                    print(f"  Sample record:")
                    for i, (col_name, value) in enumerate(zip(column_names, sample)):
                        if isinstance(value, str) and len(value) > 100:
                            value = value[:100] + "..."
                        print(f"    {col_name}: {value}")
                        
            except Exception as e:
                print(f"  Error getting sample: {e}")
    
    finally:
        conn.close()

if __name__ == "__main__":
    get_database_schema()