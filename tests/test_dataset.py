import pandas as pd
import os
from app.analysis.data_analysis import analyze_dataset

def test_dataset_analysis(tmp_path):
    df = pd.DataFrame({
        'date': ['2023-01-01', '2023-01-02'],
        'revenue': [1000, 2000],
        'profit': [100, 250]
    })
    file_path = tmp_path / "test.csv"
    df.to_csv(file_path, index=False)
    
    result = analyze_dataset(str(file_path), "what is the revenue?")
    
    assert result["success"] == True
    assert "revenue" in result["columns"]
    assert "profit" in result["columns"]
    assert "Mean=1500.00" in result["analysis_text"]
    assert "Max=2000" in result["analysis_text"]
