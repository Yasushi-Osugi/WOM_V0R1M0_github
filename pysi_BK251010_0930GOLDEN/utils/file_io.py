#utils_file_io250114.py
#以下に、`utils/file_io.py` のコードを生成します。このモジュールは、ファイルの入#出力に関するユーティリティを提供します。
#
#```python
# utils/file_io.py
import pandas as pd
import os
import csv
def read_csv_as_dictlist(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row for row in reader]
def read_csv(filepath):
    with open(filepath, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        #@STOP
        #next(reader)  # 最初の1行（ヘッダー）をスキップ
        data = [row for row in reader]
    return data
## 使用例
#csv_data = read_csv('example.csv')
#for row in csv_data:
#    print(row)
def load_monthly_demand(file_name: str) -> pd.DataFrame:
    """
    Load monthly demand data from a CSV file.
    Parameters:
        file_name (str): Path to the CSV file.
    Returns:
        pd.DataFrame: Monthly demand data as a DataFrame.
    """
    try:
        return pd.read_csv(file_name)
    except Exception as e:
        print(f"Error reading file {file_name}: {e}")
        return pd.DataFrame()  # Return an empty DataFrame on error
def load_cost_table(file_path):
    """
    Load a cost table from a CSV file and return it as a DataFrame.
    Parameters:
        file_path (str): Path to the CSV file.
    Returns:
        pd.DataFrame: Loaded cost table.
    """
    try:
        return pd.read_csv(file_path)
    except Exception as e:
        print(f"Error loading cost table: {e}")
        return None
def read_tree_file(file_name):
    """
    Read and parse the tree file.
    Parameters:
        file_name (str): The path to the tree file.
    Returns:
        list[dict]: List of rows as dictionaries.
    """
    with open(file_name, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)
def load_csv(file_path: str) -> pd.DataFrame:
    """
    Load a CSV file into a pandas DataFrame.
    Parameters:
        file_path (str): Path to the CSV file.
    Returns:
        pd.DataFrame: Loaded data as a DataFrame.
    Raises:
        FileNotFoundError: If the file does not exist.
        IOError: If there is an error reading the file.
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    try:
        df = pd.read_csv(file_path)
        print(f"Loaded data from {file_path}, shape: {df.shape}")
        return df
    except Exception as e:
        raise IOError(f"Error reading CSV file {file_path}: {e}")
def save_csv(data: pd.DataFrame, file_path: str, index: bool = False):
    """
    Save a pandas DataFrame to a CSV file.
    Parameters:
        data (pd.DataFrame): DataFrame to save.
        file_path (str): Path to save the CSV file.
        index (bool): Whether to include the index in the output file.
    Raises:
        IOError: If there is an error writing the file.
    """
    try:
        data.to_csv(file_path, index=index)
        print(f"Data saved to {file_path}, shape: {data.shape}")
    except Exception as e:
        raise IOError(f"Error writing CSV file {file_path}: {e}")
def create_directory(directory_path: str):
    """
    Create a directory if it does not exist.
    Parameters:
        directory_path (str): Path to the directory to create.
    """
    try:
        os.makedirs(directory_path, exist_ok=True)
        print(f"Directory created or already exists: {directory_path}")
    except Exception as e:
        raise IOError(f"Failed to create directory {directory_path}: {e}")
#```
#
#---
#
#### 主な機能
#
#1. **CSVファイルの読み込み**
#   - `load_csv` メソッドで CSV を `pandas.DataFrame` として読み込み。
#   - ファイルが存在しない場合やエラーが発生した場合に例外を発生。
#
#2. **CSVファイルの保存**
#   - `save_csv` メソッドで `pandas.DataFrame` を CSV ファイルとして保存。
#   - 保存先が正しくない場合やエラーが発生した場合に例外を発生。
#
#3. **ディレクトリ作成**
#   - `create_directory` メソッドでディレクトリを作成（存在しない場合のみ）。
#
#---
#
#### 次のステップ
#
#1. このコードを `utils/file_io.py` として保存。
#2. 他のモジュール（例えば `network/tree.py` や `utils/demand_processing.py`）か#ら `load_csv` や `save_csv` を使用してファイル操作を統一。
#3. 必要であれば、JSONやExcelファイルの入出力関数を追加。
#
#引き続き、次のモジュールの作成もお任せください！
#
#
#
