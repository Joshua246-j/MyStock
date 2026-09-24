import pandas as pd
import os

def analyze_dataset(file_path: str, query: str):
    """Basic analysis of a CSV or Excel dataset."""
    try:
        _, ext = os.path.splitext(file_path)
        
        if ext.lower() == '.csv':
            df = pd.read_csv(file_path)
        elif ext.lower() in ['.xlsx', '.xls']:
            df = pd.read_excel(file_path)
        else:
            return {"success": False, "error": f"Unsupported file type: {ext}"}
            
        if df.empty:
             return {"success": False, "error": "Dataset is empty"}
             
        # Basic numerical analysis (Version 1 simple info)
        numeric_cols = df.select_dtypes(include=['number']).columns.tolist()
        
        summary = []
        summary.append(f"Dataset has {len(df)} rows and {len(df.columns)} columns.")
        summary.append(f"Columns: {', '.join(df.columns)}")
        
        if numeric_cols:
            summary.append("\nNumerical Summary:")
            for col in numeric_cols:
                col_min = df[col].min()
                col_max = df[col].max()
                col_mean = df[col].mean()
                summary.append(f"- {col}: Min={col_min}, Max={col_max}, Mean={col_mean:.2f}")
                
        return {
            "success": True, 
            "analysis_text": "\n".join(summary),
            "columns": list(df.columns)
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
