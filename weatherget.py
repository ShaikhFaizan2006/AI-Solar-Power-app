import tkinter as tk
from tkinter import messagebox
import requests
from datetime import datetime
import time

# OpenWeather API Key
API_KEY = '1a7c5b7bcfd8754576593c63d867768c'

# Solar panel constants
STC_IRRADIANCE = 1000  # Standard Test Conditions irradiance (W/m²)
STC_TEMP = 25  # Standard Test Conditions temperature (°C)
TEMP_COEFFICIENT = -0.004  # Typical temperature coefficient (%/°C)

def get_lat_lon(city_name):
    """
    Get latitude and longitude for a given city using OpenWeather Geocoding API
    (Alternative to Nominatim to avoid 403 errors)
    """
    url = f"http://api.openweathermap.org/geo/1.0/direct"
    params = {"q": city_name, "limit": 1, "appid": API_KEY}
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if not data:
            raise ValueError(f"City '{city_name}' not found.")
        
        return float(data[0]['lat']), float(data[0]['lon'])
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to get coordinates: {e}")

def get_lat_lon_nominatim(city_name):
    """
    Alternative method using Nominatim with better headers and error handling
    """
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": city_name, "format": "json", "limit": 1}
    headers = {
        "User-Agent": "WeatherSolarApp/1.0 (contact@example.com)",
        "Accept": "application/json"
    }
    
    try:
        # Add a small delay to respect rate limits
        time.sleep(1)
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if not data:
            raise ValueError(f"City '{city_name}' not found.")
        
        return float(data[0]['lat']), float(data[0]['lon'])
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to get coordinates from Nominatim: {e}")

def get_hourly_solar_irradiance(lat, lon, date_yyyymmdd):
    """
    Fetch hourly ALLSKY_SFC_SW_DWN (W/m²) from NASA POWER API
    """
    url = "https://power.larc.nasa.gov/api/temporal/hourly/point"
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN",
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": date_yyyymmdd,
        "end": date_yyyymmdd,
        "format": "JSON"
    }
    
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        irradiance_data = data.get("properties", {}).get("parameter", {}).get("ALLSKY_SFC_SW_DWN", {})
        return irradiance_data
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to get solar irradiance data: {e}")

def calculate_solar_power_output(irradiance, ambient_temp, noct, panel_area, stc_efficiency):
    """
    Calculate solar panel power output based on environmental conditions
    
    Args:
        irradiance: Solar irradiance (W/m²)
        ambient_temp: Ambient temperature (°C)
        noct: Nominal Operating Cell Temperature (°C)
        panel_area: Panel surface area (m²)
        stc_efficiency: Panel efficiency at STC (%)
    
    Returns:
        tuple: (cell_temperature, efficiency, power_output_kw)
    """
    # Handle negative or invalid irradiance values (NASA API sometimes returns -999 for no data)
    if irradiance is None or irradiance < 0:
        return ambient_temp, stc_efficiency, 0  # Return ambient temp and STC efficiency when no solar data
    
    if irradiance == 0:
        return ambient_temp, stc_efficiency, 0
    
    # 1. Calculate Cell Temperature (Tcell)
    # Tcell = Tambient + ((NOCT - 20) / 800) × Irradiance
    tcell = ambient_temp + ((noct - 20) / 800) * irradiance
    
    # 2. Calculate Efficiency (η)
    # η = ηSTC × (1 + β × (Tcell - 25))
    # where β is temperature coefficient (typically -0.004 or -0.4%/°C)
    efficiency = stc_efficiency * (1 + TEMP_COEFFICIENT * (tcell - STC_TEMP))
    
    # Ensure efficiency doesn't go negative
    efficiency = max(0, efficiency)
    
    # 3. Calculate Power Output
    # P = (Irradiance / 1000) × Area × (Efficiency / 100)
    power_output_kw = (irradiance / STC_IRRADIANCE) * panel_area * (efficiency / 100)
    
    return tcell, efficiency, power_output_kw
    """
    Fetch hourly ALLSKY_SFC_SW_DWN (W/m²) from NASA POWER API
    """
    url = "https://power.larc.nasa.gov/api/temporal/hourly/point"
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN",
        "community": "RE",
        "longitude": lon,
        "latitude": lat,
        "start": date_yyyymmdd,
        "end": date_yyyymmdd,
        "format": "JSON"
    }
    
    try:
        r = requests.get(url, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        irradiance_data = data.get("properties", {}).get("parameter", {}).get("ALLSKY_SFC_SW_DWN", {})
        return irradiance_data
    except requests.exceptions.RequestException as e:
        raise ValueError(f"Failed to get solar irradiance data: {e}")

def fetch_data():
    city = entry_city.get().strip()
    if not city:
        messagebox.showwarning("Warning", "Please enter a city name.")
        return

    # Get and validate solar panel parameters
    try:
        noct = float(entry_noct.get().strip()) if entry_noct.get().strip() else 45.0
        panel_area = float(entry_area.get().strip()) if entry_area.get().strip() else 2.0
        stc_efficiency = float(entry_efficiency.get().strip()) if entry_efficiency.get().strip() else 20.0
        
        if noct <= 0 or panel_area <= 0 or stc_efficiency <= 0:
            messagebox.showwarning("Warning", "Panel parameters must be positive values.")
            return
            
    except ValueError:
        messagebox.showerror("Error", "Please enter valid numeric values for panel parameters.")
        return

    try:
        # Get weather data from OpenWeather
        url_weather = f"https://api.openweathermap.org/data/2.5/weather?q={city}&units=metric&appid={API_KEY}"
        res = requests.get(url_weather, timeout=10)
        res.raise_for_status()
        data = res.json()
        
        temp = data['main']['temp']
        wind_speed = data['wind']['speed']
        
        # Display temp & wind speed
        text_temp.config(text=f"Temperature: {temp:.2f} °C")
        text_wind.config(text=f"Wind Speed: {wind_speed:.2f} m/s")
        
        # Get coordinates - try OpenWeather Geocoding first, fallback to Nominatim
        try:
            lat, lon = get_lat_lon(city)
        except:
            try:
                lat, lon = get_lat_lon_nominatim(city)
            except Exception as geo_error:
                text_irr.config(text=f"Solar Irradiance: Could not get coordinates - {geo_error}")
                text_tcell.config(text="Cell Temperature: N/A")
                text_efficiency.config(text="Efficiency: N/A")
                text_power.config(text="Power Output: N/A")
                return
        
        # Get solar irradiance from NASA POWER
        date_str = datetime.now().strftime("%Y%m%d")
        
        try:
            irr_data = get_hourly_solar_irradiance(lat, lon, date_str)
            
            # Find current hour key
            current_hour = datetime.now().strftime("%Y%m%d%H")
            current_irr = irr_data.get(current_hour, None)
            
            # Handle NASA API data issues (-999 indicates no data available)
            if current_irr is not None and current_irr != -999:
                text_irr.config(text=f"Solar Irradiance: {current_irr:.2f} W/m²")
                
                # Calculate solar panel performance
                tcell, efficiency, power_kw = calculate_solar_power_output(
                    current_irr, temp, noct, panel_area, stc_efficiency
                )
                
                text_tcell.config(text=f"Cell Temperature: {tcell:.2f} °C")
                text_efficiency.config(text=f"Efficiency: {efficiency:.2f} %")
                text_power.config(text=f"Power Output: {power_kw:.3f} kW")
                
            elif current_irr == -999:
                # NASA API returned -999 (no data), try to estimate based on time of day
                current_time = datetime.now()
                if 6 <= current_time.hour <= 18:  # Daytime hours
                    estimated_irr = 300  # Conservative estimate for daytime
                    text_irr.config(text=f"Solar Irradiance: ~{estimated_irr} W/m² (estimated)")
                    
                    tcell, efficiency, power_kw = calculate_solar_power_output(
                        estimated_irr, temp, noct, panel_area, stc_efficiency
                    )
                    
                    text_tcell.config(text=f"Cell Temperature: {tcell:.2f} °C (estimated)")
                    text_efficiency.config(text=f"Efficiency: {efficiency:.2f} % (estimated)")
                    text_power.config(text=f"Power Output: {power_kw:.3f} kW (estimated)")
                else:
                    # Nighttime
                    text_irr.config(text="Solar Irradiance: 0 W/m² (nighttime)")
                    text_tcell.config(text=f"Cell Temperature: {temp:.2f} °C")
                    text_efficiency.config(text=f"Efficiency: {stc_efficiency:.2f} %")
                    text_power.config(text="Power Output: 0.000 kW")
            else:
                text_irr.config(text="Solar Irradiance: Data not available for current hour.")
                text_tcell.config(text="Cell Temperature: N/A")
                text_efficiency.config(text="Efficiency: N/A")
                text_power.config(text="Power Output: N/A")
                
        except Exception as solar_error:
            text_irr.config(text=f"Solar Irradiance: {solar_error}")
            text_tcell.config(text="Cell Temperature: N/A")
            text_efficiency.config(text="Efficiency: N/A")
            text_power.config(text="Power Output: N/A")
            
    except requests.exceptions.RequestException as e:
        messagebox.showerror("Error", f"Network error: {e}")
    except KeyError as e:
        messagebox.showerror("Error", f"Unexpected response format: {e}")
    except Exception as e:
        messagebox.showerror("Error", f"Failed to fetch data: {e}")

# Tkinter UI
root = tk.Tk()
root.title("Weather & Solar Panel Power Calculator")
root.geometry("450x400")

# Input section
input_frame = tk.Frame(root)
input_frame.grid(row=0, column=0, columnspan=3, padx=10, pady=5)

# City input
tk.Label(input_frame, text="Enter city:").grid(row=0, column=0, padx=5, pady=2, sticky='w')
entry_city = tk.Entry(input_frame, width=15)
entry_city.grid(row=0, column=1, padx=5, pady=2)

btn_fetch = tk.Button(input_frame, text="Calculate", command=fetch_data, bg='lightblue')
btn_fetch.grid(row=0, column=2, padx=5, pady=2)

# Solar panel parameters section
panel_frame = tk.LabelFrame(root, text="Solar Panel Parameters", padx=10, pady=5)
panel_frame.grid(row=1, column=0, columnspan=3, padx=10, pady=5, sticky='ew')

tk.Label(panel_frame, text="NOCT (°C):").grid(row=0, column=0, padx=5, pady=2, sticky='w')
entry_noct = tk.Entry(panel_frame, width=10)
entry_noct.insert(0, "45.0")  # Default NOCT value
entry_noct.grid(row=0, column=1, padx=5, pady=2)

tk.Label(panel_frame, text="Panel Area (m²):").grid(row=0, column=2, padx=5, pady=2, sticky='w')
entry_area = tk.Entry(panel_frame, width=10)
entry_area.insert(0, "2.0")  # Default area value
entry_area.grid(row=0, column=3, padx=5, pady=2)

tk.Label(panel_frame, text="STC Efficiency (%):").grid(row=1, column=0, padx=5, pady=2, sticky='w')
entry_efficiency = tk.Entry(panel_frame, width=10)
entry_efficiency.insert(0, "20.0")  # Default efficiency value
entry_efficiency.grid(row=1, column=1, padx=5, pady=2)

# Results section
results_frame = tk.LabelFrame(root, text="Results", padx=10, pady=5)
results_frame.grid(row=2, column=0, columnspan=3, padx=10, pady=5, sticky='ew')

text_temp = tk.Label(results_frame, text="Temperature: N/A", anchor='w')
text_temp.grid(row=0, column=0, columnspan=3, padx=5, pady=2, sticky='w')

text_wind = tk.Label(results_frame, text="Wind Speed: N/A", anchor='w')
text_wind.grid(row=1, column=0, columnspan=3, padx=5, pady=2, sticky='w')

text_irr = tk.Label(results_frame, text="Solar Irradiance: N/A", anchor='w')
text_irr.grid(row=2, column=0, columnspan=3, padx=5, pady=2, sticky='w')

# Solar panel calculations section
calc_frame = tk.LabelFrame(root, text="Solar Panel Calculations", padx=10, pady=5)
calc_frame.grid(row=3, column=0, columnspan=3, padx=10, pady=5, sticky='ew')

text_tcell = tk.Label(calc_frame, text="Cell Temperature: N/A", anchor='w')
text_tcell.grid(row=0, column=0, columnspan=3, padx=5, pady=2, sticky='w')

text_efficiency = tk.Label(calc_frame, text="Efficiency: N/A", anchor='w')
text_efficiency.grid(row=1, column=0, columnspan=3, padx=5, pady=2, sticky='w')

text_power = tk.Label(calc_frame, text="Power Output: N/A", anchor='w', font=('Arial', 10, 'bold'))
text_power.grid(row=2, column=0, columnspan=3, padx=5, pady=2, sticky='w')

# Allow Enter key to trigger fetch
entry_city.bind('<Return>', lambda event: fetch_data())

root.mainloop()