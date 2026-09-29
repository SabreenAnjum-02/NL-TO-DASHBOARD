import os
import sys
import uuid
sys.path.append(os.path.join(os.getcwd(), "backend"))
from backend.main import DataService

def test_profiler():
    ds = DataService()
    
    dataset_id = str(uuid.uuid4())[:8]
    t1 = f"dataset_{dataset_id}_vendors"
    t2 = f"dataset_{dataset_id}_orders"
    t3 = f"dataset_{dataset_id}_summary"
    
    # Create test tables
    ds.db.execute(f"""
        CREATE TABLE "{t1}" (
            vendor_id VARCHAR,
            vendor_name VARCHAR,
            score INT
        )
    """)
    ds.db.execute(f'INSERT INTO "{t1}" VALUES (\'V1\', \'Alice\', 5), (\'V2\', \'Bob\', 4)')
    
    ds.db.execute(f"""
        CREATE TABLE "{t2}" (
            order_id INT,
            vendor_id VARCHAR,
            amount DOUBLE,
            order_date DATE
        )
    """)
    ds.db.execute(f'INSERT INTO "{t2}" VALUES (101, \'V1\', 150.5, \'2023-01-01\'), (102, \'V1\', 200.0, \'2023-01-02\'), (103, \'V2\', 50.0, \'2023-01-02\')')
    
    ds.db.execute(f"""
        CREATE TABLE "{t3}" (
            month VARCHAR,
            total_revenue DOUBLE
        )
    """)
    ds.db.execute(f'INSERT INTO "{t3}" VALUES (\'Jan 2023\', 400.5)')
    
    table_names = [t1, t2, t3]
    total_row_count = 2 + 3 + 1
    
    profile = {
        "row_count": total_row_count, 
        "column_count": 0,
        "columns": [],
        "tables": {},
        "relationships": []
    }
    
    all_columns = []
    col_map = []
    
    for t_name in table_names:
        table_info = {
            "purpose": "unknown",
            "grain": "unknown",
            "row_count": 0,
            "columns": [],
            "primary_key_candidates": []
        }
        
        t_count = ds.db.execute(f'SELECT COUNT(*) FROM "{t_name}"').fetchone()[0]
        table_info["row_count"] = t_count
        
        cols_raw = ds.db.execute(f'DESCRIBE "{t_name}"').fetchall()
        
        numeric_cols = 0
        date_cols = 0
        max_distinct = 0
        
        for col_name, col_type, *_ in cols_raw:
            if col_name == "Sheet_Name": continue
                
            col_info = {
                "name": col_name,
                "type": col_type,
                "null_count": 0,
                "samples": [],
            }
            
            try:
                null_count = ds.db.execute(f'SELECT COUNT(*) FROM "{t_name}" WHERE "{col_name}" IS NULL').fetchone()[0]
                col_info["null_count"] = null_count
                
                raw_samples = ds.db.execute(f'SELECT DISTINCT "{col_name}" FROM "{t_name}" WHERE "{col_name}" IS NOT NULL LIMIT 3').fetchall()
                col_info["samples"] = [str(r[0]) for r in raw_samples]
                
                type_up = col_type.upper()
                
                if any(t in type_up for t in ("INT", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC", "BIGINT", "HUGEINT", "REAL", "TINYINT", "SMALLINT")):
                    numeric_cols += 1
                    row = ds.db.execute(f'SELECT MIN("{col_name}"), MAX("{col_name}"), APPROX_COUNT_DISTINCT("{col_name}") FROM "{t_name}"').fetchone()
                    if row:
                        col_info["min"] = row[0]
                        col_info["max"] = row[1]
                        col_info["distinct_count"] = row[2]
                        max_distinct = max(max_distinct, row[2])
                elif any(t in type_up for t in ("DATE", "TIMESTAMP", "TIME")):
                    date_cols += 1
                    row = ds.db.execute(f'SELECT MIN("{col_name}"), MAX("{col_name}") FROM "{t_name}"').fetchone()
                    if row:
                        col_info["min_date"] = str(row[0])
                        col_info["max_date"] = str(row[1])
                        dist = ds.db.execute(f'SELECT APPROX_COUNT_DISTINCT("{col_name}") FROM "{t_name}"').fetchone()[0]
                        col_info["distinct_count"] = dist
                elif any(t in type_up for t in ("VARCHAR", "TEXT", "STRING", "CHAR")):
                    dist = ds.db.execute(f'SELECT APPROX_COUNT_DISTINCT("{col_name}") FROM "{t_name}"').fetchone()[0]
                    col_info["distinct_count"] = dist
                    max_distinct = max(max_distinct, dist)
                    if dist <= 10:
                        col_info["cardinality"] = "low"
                        raw_samples_ext = ds.db.execute(f'SELECT DISTINCT "{col_name}" FROM "{t_name}" WHERE "{col_name}" IS NOT NULL LIMIT 10').fetchall()
                        col_info["samples"] = [str(r[0]) for r in raw_samples_ext]
                    elif dist <= 50:
                        col_info["cardinality"] = "medium"
                    else:
                        col_info["cardinality"] = "high"
                        
                if "distinct_count" in col_info and col_info["distinct_count"] > 0:
                    if col_info["distinct_count"] == t_count and col_info["null_count"] == 0 and t_count > 1:
                        name_lower = col_name.lower()
                        if "id" in name_lower or "code" in name_lower or name_lower == "name" or name_lower == "vendor" or name_lower == "crew" or name_lower == "employee":
                            table_info["primary_key_candidates"].append(col_name)
                            
                col_map.append({
                    "table": t_name, 
                    "col": col_name, 
                    "type": type_up, 
                    "distinct": col_info.get("distinct_count", 0),
                    "nulls": null_count
                })
                        
            except Exception as e:
                print(e)
                pass
                
            table_info["columns"].append(col_info)
            all_columns.append({"table": t_name, **col_info})
            
        name_lower = t_name.lower()
        if t_count == 0:
            table_info["grain"] = "empty"
        elif t_count == 1:
            table_info["grain"] = "metadata/single record"
            table_info["purpose"] = "summary or configuration"
        else:
            is_summary = any(kw in name_lower for kw in ("summary", "total", "aggregate", "report", "monthly", "yearly"))
            if is_summary:
                table_info["grain"] = "aggregated/summary"
                table_info["purpose"] = "pre-calculated metrics"
            else:
                if len(table_info["primary_key_candidates"]) > 0:
                    table_info["grain"] = "entity-level (one row per entity)"
                elif max_distinct > 0 and max_distinct < (t_count * 0.2) and date_cols > 0:
                    table_info["grain"] = "time-series/event-level (transactional)"
                else:
                    table_info["grain"] = "detail-level/transactional (inferred)"
                    
        profile["tables"][t_name] = table_info
        
    for i in range(len(col_map)):
        for j in range(i+1, len(col_map)):
            c1, c2 = col_map[i], col_map[j]
            if c1["table"] == c2["table"]: continue
            
            n1, n2 = c1["col"].lower(), c2["col"].lower()
            
            if n1 == n2 or (n1 in n2 and "id" in n1) or (n2 in n1 and "id" in n2):
                if ("INT" in c1["type"] and "INT" in c2["type"]) or ("CHAR" in c1["type"] and "CHAR" in c2["type"]) or c1["type"] == c2["type"]:
                    if c1["distinct"] > 0 and c2["distinct"] > 0:
                        try:
                            overlap = ds.db.execute(f'SELECT COUNT(*) FROM (SELECT "{c1["col"]}" FROM "{c1["table"]}" WHERE "{c1["col"]}" IS NOT NULL INTERSECT SELECT "{c2["col"]}" FROM "{c2["table"]}" WHERE "{c2["col"]}" IS NOT NULL)').fetchone()[0]
                            if overlap > 0:
                                confidence = "likely" if overlap >= min(c1["distinct"], c2["distinct"]) * 0.5 else "possible"
                                profile["relationships"].append({
                                    "source_table": c1["table"],
                                    "source_column": c1["col"],
                                    "target_table": c2["table"],
                                    "target_column": c2["col"],
                                    "confidence": confidence,
                                    "overlap_count": overlap
                                })
                        except Exception as e:
                            print(e)
                            pass
                            
    import json
    print(json.dumps(profile, indent=2))

if __name__ == "__main__":
    test_profiler()
