# IMPORTS
import os
import warnings
from statsmodels.tools.sm_exceptions import ConvergenceWarning
from sklearn.model_selection import train_test_split
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import LSTM, Dense
from datetime import datetime
from scipy.spatial import distance
from collections import Counter
import seaborn as sns
import itertools
import pickle
import pandas as pd
import numpy as np
from sklearn.preprocessing import MinMaxScaler
import matplotlib.pyplot as plt
from statsmodels.tsa.statespace.sarimax import SARIMAX
import matplotlib
matplotlib.use('Qt5Agg')
import matplotlib.pyplot as plt
pd.set_option('display.max_columns', None)
pd.set_option('display.max_rows', None)
pd.set_option('display.float_format', lambda x: '%.3f' % x)
pd.set_option('display.max_colwidth', None)
pd.set_option('display.width', 500)
warnings.simplefilter('ignore', category=ConvergenceWarning)

# FUNCTIONS
def station_coordinates(input):
    """
    Creates a dataset consisting of measurement station IDs and their corresponding X and Y coordinates.

    Args:
        input: Directory of the measurement station CSV file.

    Returns:
        df: A DataFrame containing columns "x", "y", and "hzbnr01".
    """
    df = pd.read_csv(os.path.join("Ehyd", "datasets_ehyd", input, "messstellen_alle.csv"), sep=";")
    output_df = df[["x", "y", "hzbnr01"]].copy()
    output_df['x'] = output_df['x'].astype(str).str.replace(',', '.').astype("float32")
    output_df['y'] = output_df['y'].astype(str).str.replace(',', '.').astype("float32")
    return output_df

def to_dataframe(folder_path, tip_coordinates):
    """
    Processes CSV files in the specified folder, skipping header information and creating DataFrames
    from the section marked by "Werte". Converts "L�cke" (Gap) values to NaN and skips rows with
    invalid data or specific keywords.

    For each CSV file, it extracts data starting after the "Werte:" line, processes date and value
    columns, and stores each DataFrame in a dictionary where the key is derived from the filename.
    Additionally, it matches IDs with tip coordinates and returns a DataFrame containing matched coordinates.

    Args:
        folder_path (str): The directory path where the CSV files are located.
        tip_coordinates (pd.DataFrame): A DataFrame containing coordinates to be matched with the IDs.

    Returns:
        dict: A dictionary where keys are IDs (extracted from filenames) and values are DataFrames.
        pd.DataFrame: A DataFrame with matched coordinates based on IDs.
    """
    dataframes_dict = {}
    coordinates = pd.DataFrame()

    for filename in os.listdir(folder_path):
        try:
            if filename.endswith(".csv"):
                filepath = os.path.join(folder_path, filename)

                with open(filepath, 'r', encoding='latin1') as file:
                    lines = file.readlines()

                    # Find the starting index of the data section
                    start_idx = next((i for i, line in enumerate(lines) if line.startswith("Werte:")), None)
                    if start_idx is None:
                        continue  # Skip files that do not contain 'Werte:'

                    start_idx += 1
                    header_line = lines[start_idx - 1].strip()

                    # Skip files with 'Invalid' in the header line
                    if "Invalid" in header_line:
                        continue

                    data_lines = lines[start_idx:]

                    data = []
                    for line in data_lines:
                        if line.strip():  # Skip empty lines
                            try:
                                date_str, value_str = line.split(';')[:2]

                                # Try multiple date formats
                                try:
                                    date = datetime.strptime(date_str.strip(), "%d.%m.%Y %H:%M:%S").date()
                                except ValueError:
                                    try:
                                        date = datetime.strptime(date_str.strip(), "%d.%m.%Y %H:%M").date()
                                    except ValueError:
                                        continue

                                value_str = value_str.strip().replace('L�cke', 'NaN')  # Convert 'L�cke' to NaN

                                # Skip rows with invalid data or specific keywords
                                if any(keyword in value_str for keyword in ["F", "K", "rekonstruiert aus Version 3->"]):
                                    continue

                                # Convert value to float
                                try:
                                    value = np.float32(value_str.replace(',', '.'))
                                except ValueError:
                                    continue

                                data.append([date, value])
                            except Exception:
                                break

                    if data:  # Create DataFrame only if data exists
                        df = pd.DataFrame(data, columns=['Date', 'Values'])
                        df.drop(df.index[-1], inplace=True)  # Dropping the last row (2022-01-01)
                        df_name = f"{filename[-10:-4]}"

                        dataframes_dict[df_name] = df

                        # Convert keys to integers
                        int_keys = [int(key) for key in dataframes_dict.keys() if key.isdigit()]
                        coordinates = tip_coordinates[tip_coordinates['hzbnr01'].isin(int_keys)]

        except Exception:
            continue

    return dataframes_dict, coordinates

def to_global(dataframes_dict, prefix=''):
    """
    Adds DataFrames from a dictionary to the global namespace with optional prefix.

    Args:
        dataframes_dict (dict): A dictionary where keys are names (str) and values are DataFrames.
        prefix (str): An optional string to prefix to each DataFrame name in the global namespace.
    """
    for name, dataframe in dataframes_dict.items():
        globals()[f"{prefix}{name}"] = dataframe

def process_dataframes(df_dict):
    """
    Processes a dictionary of DataFrames by converting date columns, resampling daily data to monthly, and reindexing.

    Args:
        df_dict (dict): A dictionary where keys are DataFrame names and values are DataFrames.

    Returns:
        dict: The processed dictionary of DataFrames with date conversion, resampling, and reindexing applied.
    """
    for df_name, df_value in df_dict.items():
        df_value['Date'] = pd.to_datetime(df_value['Date'])

        if df_value['Date'].dt.to_period('D').nunique() > df_value['Date'].dt.to_period('M').nunique():
            df_value.set_index('Date', inplace=True)
            df_dict[df_name] = df_value.resample('MS').mean()

        else:
            df_value.set_index('Date', inplace=True)
            df_dict[df_name] = df_value

        all_dates = pd.date_range(start='1960-01-01', end='2021-12-01', freq='MS')
        new_df = pd.DataFrame(index=all_dates)
        df_dict[df_name] = new_df.join(df_dict[df_name], how='left').fillna("NaN")

    return df_dict

def process_and_store_data(folder, coordinates, prefix, points_list=None):
    data_dict, data_coordinates = to_dataframe(folder, coordinates)
    data_dict = process_dataframes(data_dict)

    for df_name, df in data_dict.items():
        df.astype('float32')

    to_global(data_dict, prefix=prefix)

    if points_list:
        data_dict = filter_dataframes_by_points(data_dict, points_list)
        data_coordinates = data_coordinates[data_coordinates['hzbnr01'].astype(str).isin(points_list)]

    return data_dict, data_coordinates

def filter_dataframes_by_points(dataframes_dict, points_list):
    """
    Filters a dictionary of DataFrames to include only those whose names are specified in a given CSV file.

    Args:
        dataframes_dict (dict): A dictionary where keys are names (str) and values are DataFrames.
        points_list (str): Path to a CSV file that contains the names (str) of the DataFrames to filter.

    Returns:
        dict: A filtered dictionary containing only the DataFrames whose names are listed in the CSV file.
    """
    filtered_dict = {name: df for name, df in dataframes_dict.items() if name in points_list}
    return filtered_dict

def save_to_pickle(item, filename):
    """
    Saves a dictionary to a pickle file.

    Args:
        data_dict (dict): The dictionary to save.
        filename (str): The path to the output pickle file.
    """
    with open(filename, 'wb') as f:
        pickle.dump(item, f)


########################################################################################################################
# Creating Dataframes from given CSVs
########################################################################################################################

# Define paths and coordinates
groundwater_all_coordinates = station_coordinates("Groundwater")
precipitation_coordinates = station_coordinates("Precipitation")
sources_coordinates = station_coordinates("Sources")
surface_water_coordinates = station_coordinates("Surface_Water")

# Precipitation: Rain and Snow
precipitation_folders = [
    ("Precipitation/N-Tagessummen", "rain_"),
    ("Precipitation/NS-Tagessummen", "snow_")]
for folder, prefix in precipitation_folders:
    dict_name, dict_coord = f"{prefix}_dict", f"{prefix}_coordinates"
    dict_name, dict_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", folder), precipitation_coordinates, prefix)

######### gizmo
for folder, prefix in precipitation_folders:
    dict_name, dict_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", folder), precipitation_coordinates, prefix)
    globals()[f"{prefix}_dict"] = dict_name
    globals()[f"{prefix}_coordinates"] = dict_coord
##########
def create_dict(main_folder, coordinates):
    for folder, prefix in main_folder:
        dict_name, dict_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", folder), coordinates, prefix)
        globals()[f"{prefix}_dict"] = dict_name
        globals()[f"{prefix}_coordinates"] = dict_coord

create_dict(precipitation_folders, precipitation_folders)
create_dict(source_folders, source_folders)
create_dict(source_folders, )


# Sources: Flow Rate, Conductivity, Temperature
source_folders = [
    ("Quellsch�ttung-Tagesmittel", "source_fr_"),
    ("Quellleitf�higkeit-Tagesmittel", "conductivity_"),
    ("Quellwassertemperatur-Tagesmittel", "source_temp_")]

surface_water_folders = [
    ("W-Tagesmittel", "surface_water_level_"),
    ("WT-Monatsmittel", "surface_water_temp_"),
    ("Schwebstoff-Tagesfracht", "sediment_"),
    ("Q-Tagesmittel", "surface_water_fr_")]

# Groundwater Dictionary (Filtered to requested 487 points)
points = pd.read_csv(os.path.join("Ehyd", "datasets_ehyd", "gw_test_empty.csv"))
points_list = [col for col in points.columns[1:]]
filtered_groundwater_dict, filtered_gw_coordinates = process_and_store_data(
    os.path.join("Ehyd", "datasets_ehyd", "Groundwater", "Grundwasserstand-Monatsmittel"),
    groundwater_all_coordinates, "gw_", points_list)

gw_temp_dict, gw_temp_coordinates = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Groundwater", "Grundwassertemperatur-Monatsmittel"), groundwater_all_coordinates, "gwt_")
rain_dict, rain_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Precipitation", precipitation_folders[0][0]), precipitation_coordinates, "rain_")
snow_dict, snow_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Precipitation", precipitation_folders[1][0]), precipitation_coordinates, "snow_")
source_fr_dict, source_fr_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Sources", source_folders[0][0]), sources_coordinates, "source_fr_")
conduct_dict, conduct_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Sources", source_folders[1][0]), sources_coordinates, "conduct_")
source_temp_dict, source_temp_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Sources", source_folders[2][0]), sources_coordinates, "source_temp_")
surface_water_lvl_dict, surface_water_lvl_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Surface_Water", surface_water_folders[0][0]), surface_water_coordinates, "surface_water_lvl_")
surface_water_temp_dict, surface_water_temp_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Surface_Water", surface_water_folders[1][0]), surface_water_coordinates, "surface_water_temp_")
sediment_dict, sediment_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Surface_Water", surface_water_folders[2][0]), surface_water_coordinates, "sediment_")
surface_water_fr_dict, surface_water_fr_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", "Surface_Water", surface_water_folders[3][0]), surface_water_coordinates, "surface_water_fr_")

# gizmo
for folder, prefix in surface_water_folders:
    dict_name, dict_coord = process_and_store_data(os.path.join("Ehyd", "datasets_ehyd", folder), surface_water_coordinates, prefix)
    globals()[f"{prefix}_dict"] = dict_name
    globals()[f"{prefix}_coordinates"] = dict_coord

# Save data to pickle files
dicts_list = [gw_temp_dict, filtered_groundwater_dict, snow_dict, rain_dict, conduct_dict, source_fr_dict,
              source_temp_dict, surface_water_lvl_dict, surface_water_fr_dict, surface_water_temp_dict, sediment_dict]

directory = 'Ehyd/pkl_files'

for dictionary in dicts_list:
    dict_name = [name for name in globals() if globals()[name] is dictionary][0]
    filename = os.path.join(directory, f'{dict_name}.pkl')
    save_to_pickle(dictionary, filename)

########################################################################################################################
# Gathering associated features for 487 stations
########################################################################################################################
def calculate_distance(coord1, coord2):
    return distance.euclidean(coord1, coord2)

def find_nearest_coordinates(gw_row, df, k=20):
    distances = df.apply(lambda row: calculate_distance(
        (gw_row['x'], gw_row['y']),
        (row['x'], row['y'])
    ), axis=1)
    nearest_indices = distances.nsmallest(k).index
    return df.loc[nearest_indices]

# Creating a dataframe that stores all the associated features of the 487 stations.
data = pd.DataFrame()
def add_nearest_coordinates_column(df_to_add, name, k, df_to_merge=None):
    if df_to_merge is None:
        df_to_merge = data  # Use the current value of 'data' as the default
    results = []

    # Find the nearest points according to the coordinates
    for _, gw_row in filtered_gw_coordinates.iterrows():
        nearest = find_nearest_coordinates(gw_row, df_to_add, k)
        nearest_list = nearest['hzbnr01'].tolist()
        results.append({
            'hzbnr01': gw_row['hzbnr01'],
            name: nearest_list
        })

    results_df = pd.DataFrame(results)

    # Debug: Check if 'hzbnr01' exists in both dataframes
    print("Columns in df_to_merge:", df_to_merge.columns)
    print("Columns in results_df:", results_df.columns)

    # Ensure that the column exists in both dataframes before merging
    if 'hzbnr01' in df_to_merge.columns and 'hzbnr01' in results_df.columns:
        # Merge operation
        df = df_to_merge.merge(results_df, on='hzbnr01', how='inner')

        # Debug: Birle?tirilmi? DataFrame'i yazd?rarak kontrol et
        print("Merged DataFrame:")
        print(df.head())
    else:
        raise KeyError("Column 'hzbnr01' does not exist in one of the dataframes.")

    return df

data = add_nearest_coordinates_column(gw_temp_coordinates, 'nearest_gw_temp', 1, df_to_merge=filtered_gw_coordinates)
data = add_nearest_coordinates_column(rain_coord, 'nearest_rain', 3, df_to_merge=data) # TODO burada data arguman? default oldugu icin silebiliriz.
data = add_nearest_coordinates_column(snow_coord, 'nearest_snow', 3, df_to_merge=data)
data = add_nearest_coordinates_column(source_fr_coord, 'nearest_source_fr', 1, df_to_merge=data)
data = add_nearest_coordinates_column(conduct_coord, 'nearest_conductivity', 1, df_to_merge=data)
data = add_nearest_coordinates_column(source_temp_coord, 'nearest_source_temp', 1, df_to_merge=data)
data = add_nearest_coordinates_column(surface_water_lvl_coord, 'nearest_owf_level', 3, df_to_merge=data)
data = add_nearest_coordinates_column(surface_water_temp_coord, 'nearest_owf_temp', 1, df_to_merge=data)
data = add_nearest_coordinates_column(sediment_coord, 'nearest_sediment', 1, df_to_merge=data)
data = add_nearest_coordinates_column(surface_water_fr_coord, 'nearest_owf_fr', 3, df_to_merge=data)
data.drop(["x", "y"], axis=1, inplace=True)

file_path = os.path.join(directory, 'data.pkl')
save_to_pickle(data, file_path)

########################################################################################################################
# Imputing NaN Values
########################################################################################################################
def nan_imputer(dict):
    new_dict = {}
    for df_name, df in dict.items():
        df_copy = df.copy(deep=True)  # Create a deep copy
        df_copy.replace('NaN', np.nan, inplace=True)
        first_valid_index = df_copy['Values'].first_valid_index()
        valid_values = df_copy.loc[first_valid_index:].copy()

        # Fill NaNs with the corresponding monthly means
        for month in range(1, 13):
            month_mean = valid_values[valid_values.index.month == month]['Values'].dropna().mean()
            valid_values.loc[valid_values.index.month == month, 'Values'] = valid_values.loc[
                valid_values.index.month == month, 'Values'].fillna(month_mean)

        # Update the copied DataFrame with filled values
        df_copy.update(valid_values)
        new_dict[df_name] = df_copy  # Store the modified copy

    return new_dict

filled_filtered_groundwater_dict = nan_imputer(filtered_groundwater_dict)
filled_gw_temp_dict = nan_imputer(gw_temp_dict)
filled_rain_dict = nan_imputer(rain_dict)
filled_snow_dict = nan_imputer(snow_dict)
filled_source_fr_dict = nan_imputer(source_fr_dict)
filled_source_temp_dict = nan_imputer(source_temp_dict)
filled_conduct_dict = nan_imputer(conduct_dict)
filled_surface_water_fr_dict = nan_imputer(surface_water_fr_dict)
filled_surface_water_lvl_dict = nan_imputer(surface_water_lvl_dict)
filled_surface_water_temp_dict = nan_imputer(surface_water_temp_dict)
filled_sediment_dict = nan_imputer(sediment_dict)

# S�zl�klerinizi i�eren liste ve isimlerini saklay?n
dicts_with_names = {
    'filled_gw_temp_dict': filled_gw_temp_dict,
    'filled_filtered_groundwater_dict': filled_filtered_groundwater_dict,
    'filled_snow_dict': filled_snow_dict,
    'filled_rain_dict': filled_rain_dict,
    'filled_conduct_dict': filled_conduct_dict,
    'filled_source_fr_dict': filled_source_fr_dict,
    'filled_source_temp_dict': filled_source_temp_dict,
    'filled_surface_water_lvl_dict': filled_surface_water_lvl_dict,
    'filled_surface_water_fr_dict': filled_surface_water_fr_dict,
    'filled_surface_water_temp_dict': filled_surface_water_temp_dict,
    'filled_sediment_dict': filled_sediment_dict
}

# Her bir s�zl�?� isimleriyle `.pkl` dosyas?na kaydetme
for dict_name, dictionary in dicts_with_names.items():
    filename = os.path.join(directory, f'{dict_name}.pkl')
    save_to_pickle(dictionary, filename)

# Calling pickle files back from the directory
pkl_files = [f for f in os.listdir(directory) if f.endswith('.pkl')]

for pkl_file in pkl_files:
    file_path = os.path.join(directory, pkl_file)
    with open(file_path, 'rb') as file:
        var_name = pkl_file[:-4]
        globals()[var_name] = pickle.load(file)

########################################################################################################################
# Adding lagged values and rolling means
########################################################################################################################
filled_dict_list = [filled_gw_temp_dict, filled_filtered_groundwater_dict, filled_snow_dict, filled_rain_dict,
                    filled_conduct_dict, filled_source_fr_dict, filled_source_temp_dict, filled_surface_water_lvl_dict,
                    filled_surface_water_fr_dict, filled_surface_water_temp_dict, filled_sediment_dict]

def add_lag_and_rolling_mean(df, window=6):
    """
    Adds lagged and rolling mean columns to a DataFrame.

    Args:
        df (pandas.DataFrame): The input DataFrame containing the data.
        window (int, optional): The window size for calculating the rolling mean. Default is 6.

    Returns:
        pandas.DataFrame: The DataFrame with additional columns for lagged values and rolling means.
    """
    column_name = df.columns[0]
    df[f'lag_1'] = df[column_name].shift(1)
    for i in range(1, 2):
        df[f'rolling_mean_{window}_lag_{i}'] = df[f'lag_1'].shift(i).rolling(window=window).mean()
    return df

for dictionary in filled_dict_list:
    for key, df in dictionary.items():
        dictionary[key] = add_lag_and_rolling_mean(df)

########################################################################################################################
# Zero Padding
########################################################################################################################
def zero_padding(df, start_date='1960-01-01'):
    """
    Fills missing months in a DataFrame with zero padding.

    This function ensures that the DataFrame has a continuous monthly index starting from the specified
    start date. Missing months are filled with zeroes.

    Args:
        df (pandas.DataFrame): The input DataFrame with a DateTime or PeriodIndex.
        start_date (str, optional): The start date for the time series, in 'YYYY-MM-DD' format.
                                    Default is '1960-01-01'.

    Returns:
        pandas.DataFrame: The DataFrame with a continuous monthly index, where missing months are filled with zeroes.
    """
    if not isinstance(df.index, pd.PeriodIndex):
        df.index = df.index.to_period('M')

    start_date = pd.to_datetime(start_date).to_period('M')
    all_dates = pd.period_range(start=start_date, end=df.index.max(), freq='M')
    new_df = pd.DataFrame(index=all_dates)
    new_df = new_df.join(df, how='left').fillna(0)
    new_df.index = new_df.index.to_timestamp()

    return new_df

for dictionary in filled_dict_list:
    for key in dictionary:
        dictionary[key] = zero_padding(dictionary[key])

########################################################################################################################
# Changing the data type to float32
########################################################################################################################
def convert_to_float32(df):
    """
    Converts all columns in a DataFrame to the float32 data type.

    Args:
        df (pandas.DataFrame): The input DataFrame with columns to be converted.

    Returns:
        pandas.DataFrame: The DataFrame with all columns converted to float32.
    """
    return df.astype('float32')

for dictionary in filled_dict_list:
    for key in dictionary:
        dictionary[key] = convert_to_float32(dictionary[key])

########################################################################################################################
# LSTM-formatted dataframes and the .pkl file
########################################################################################################################
# 732 dataframe
new_df = pd.DataFrame(index=data['hzbnr01'])

new_df['ground_water_lvl'] = None
new_df['ground_water_lvl_lag_1'] = None
new_df['ground_water_lvl_rolling_mean_6_lag_1'] = None

rows_to_add = []

for index in new_df.index:
    key = str(index)  # Anahtar?n string oldu?una dikkat ediyoruz

    if key in filled_filtered_groundwater_dict:
        df = filled_filtered_groundwater_dict[key]

        if not df.empty:
            # Her bir sat?r? new_df'ye ekliyoruz
            for _, row in df.iterrows():
                rows_to_add.append([index, row['Values'], row['lag_1'], row['rolling_mean_6_lag_1']])
        else:
            print(f"DataFrame for key {key} is empty.")
    else:
        print(f"Key {key} not found in the dictionary.")

# Yeni bir DataFrame olu?turuyoruz ve eski new_df ile birle?tiriyoruz
new_df_expanded = pd.DataFrame(rows_to_add, columns=['index', 'ground_water_lvl', 'ground_water_lvl_lag_1',
                                                     'ground_water_lvl_rolling_mean_6_lag_1'])
new_df_expanded = new_df_expanded.set_index('index')

# ?ndeks ve de?erleri kontrol ediyoruz
print(new_df_expanded)

########################################################################################################################
# Normalization
########################################################################################################################
scaler = MinMaxScaler(feature_range=(0, 1))
normalized_dfs = [pd.DataFrame(scaler.fit_transform(df), columns=df.columns) for df in list_of_dfs]

# todo son bir datatype'? kontrol edelim
########################################################################################################################
# LSTM Model
########################################################################################################################
# 1. Veri Haz?rl???

# DataFrame'leri numpy array'lerine d�n�?t�r�p birle?tirin
data = np.array([df.values for df in list_of_dfs])  # (720, 487, 57)

# 2. Pencereleme
def create_windows(data, window_size, forecast_horizon):
    X, y = [], []
    num_time_steps = data.shape[0]

    for start in range(num_time_steps - window_size - forecast_horizon + 1):
        end = start + window_size
        X.append(data[start:end, :, :])
        y.append(data[end:end + forecast_horizon, :, :])

    X = np.array(X)
    y = np.array(y)

    # X'in boyutlar?n? (batch_size, time_steps, features) haline getir
    X = X.reshape(X.shape[0], X.shape[1], -1)
    y = y.reshape(y.shape[0], y.shape[1], -1)

    return X, y


window_size = 12 # window size'? hala tam olarak anlayamad?m
forecast_horizon = 26 # �n�m�zdeli 26 ay? tahmin edece?iz
X, y = create_windows(data, window_size, forecast_horizon)  # X: (672, 12, 487, 5), y: (672, 26, 487, 5)

# 3. E?itim ve Test Setlerine B�lme
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, shuffle=False)

# 4. LSTM Modelini Olu?turma ve E?itim
model = Sequential()
model.add(LSTM(units=57, return_sequences=True, input_shape=(window_size, data.shape[1] * data.shape[2])))
model.add(LSTM(units=57, return_sequences=True))
model.add(Dense(data.shape[2]))  # �?k?? katman?, tahmin edilmesi gereken s�tun say?s?na g�re ayarlanmal?
model.compile(optimizer='adam', loss='mse')

# Modeli e?itme
history = model.fit(X_train, y_train, epochs=50, batch_size=32, validation_data=(X_test, y_test))


