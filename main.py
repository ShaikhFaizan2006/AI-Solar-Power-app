# solar_predictor_app.py
import tkinter as tk
from tkinter import messagebox
import requests
from datetime import datetime
import joblib
import os
import pandas as pd

# === CONFIG ===
OPENWEATHER_API_KEY = '1a7c5b7bcfd8754576593c63d867768c'   # <<-- put your key here
MODEL_PATH = 'solar_irradiance_pipeline_local.pkl'  # Fixed: use local path
N_REF = 0.15      # reference efficiency (15%) - change if you want
BETA = 0.0045     # temperature coefficient (per °C) - change if you want

# Load trained pipeline
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Trained model not found at {MODEL_PATH}. Put it there or change MODEL_PATH.")

try:
    model_pipeline = joblib.load(MODEL_PATH)
except Exception as e:
    raise RuntimeError(f"Failed to load model: {e}")

# --- Helpers ---
def get_weather_openweather(city):
    """Return (temp_C, wind_m_s, lat, lon, sunrise_unix, sunset_unix)"""
    if OPENWEATHER_API_KEY == "YOUR_OPENWEATHER_API_KEY":
        raise ValueError("Please set your actual OpenWeather API key in OPENWEATHER_API_KEY")
    
    url = f"https://api.openweathermap.org/data/2.5/weather"
    params = {"q": city, "appid": OPENWEATHER_API_KEY, "units": "metric"}
    
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        js = r.json()
        
        # Check if API returned an error
        if js.get("cod") != 200:
            raise requests.HTTPError(f"API Error: {js.get('message', 'Unknown error')}")
        
        temp = js["main"]["temp"]
        wind = js["wind"].get("speed", 0.0)
        lat = js["coord"]["lat"]
        lon = js["coord"]["lon"]
        sunrise = js["sys"]["sunrise"]   # unix UTC
        sunset = js["sys"]["sunset"]     # unix UTC
        return temp, wind, lat, lon, sunrise, sunset
        
    except requests.exceptions.RequestException as e:
        raise requests.HTTPError(f"Weather API request failed: {e}")

def reverse_geocode_nominatim(lat, lon):
    """Return (state, district) from Nominatim reverse geocode (best-effort)"""
    url = "https://nominatim.openstreetmap.org/reverse"
    params = {"lat": lat, "lon": lon, "format": "json", "zoom": 10, "addressdetails": 1}
    headers = {"User-Agent": "MySolarApp/1.0 (your_email@example.com)"}
    
    try:
        r = requests.get(url, params=params, headers=headers, timeout=10)
        r.raise_for_status()
        js = r.json()
        
        if "error" in js:
            # Fallback for geocoding errors
            return "Unknown State", "Unknown District"
        
        addr = js.get("address", {})
        state = addr.get("state") or addr.get("region") or "Unknown State"
        # district/county mapping - try multiple keys:
        district = (addr.get("county") or addr.get("district") or 
                   addr.get("city_district") or addr.get("town") or 
                   addr.get("village") or addr.get("city") or "Unknown District")
        
        # Normalize strings (title case)
        return state.title(), district.title()
        
    except requests.exceptions.RequestException as e:
        # Fallback on network errors
        print(f"Geocoding failed: {e}")
        return "Unknown State", "Unknown District"

def predict_insolation_kwh(state, district, month_name):
    """Prepare single-row dataframe for model and predict kWh/m^2/day"""
    try:
        input_data = {"State": state, "District": district, "Month": month_name.capitalize()}
        print(f"Model input: {input_data}")
        
        row = pd.DataFrame([input_data])
        pred = model_pipeline.predict(row)[0]
        
        print(f"Model prediction: {pred:.3f} kWh/m²/day")
        
        return float(pred)
    except Exception as e:
        # If prediction fails, return a reasonable default
        print(f"Prediction failed: {e}")
        print(f"Using default insolation value of 4.5 kWh/m²/day")
        return 4.5  # Default reasonable insolation value for India

# --- Tkinter UI action ---
def on_predict():
    city = entry_city.get().strip()
    if not city:
        messagebox.showwarning("Input required", "Please enter a city name.")
        return

    try:
        noct = float(entry_noct.get())
        if noct <= 0:
            raise ValueError("NOCT must be positive")
    except ValueError:
        messagebox.showwarning("Invalid Input", "Enter a valid NOCT (°C) number (must be positive).")
        return

    try:
        panel_area = float(entry_area.get())
        if panel_area <= 0:
            raise ValueError("Panel area must be positive")
    except ValueError:
        messagebox.showwarning("Invalid Input", "Enter a valid panel area in m² (must be positive).")
        return

    try:
        # Clear previous results
        for label in [text_temp, text_wind, text_loc, text_insol, text_irr, text_tcell, text_eff, text_power]:
            label.config(text=label.cget("text").split(":")[0] + ": Loading...")
        root.update()

        # 1) Live weather
        temp, wind_speed, lat, lon, sunrise_unix, sunset_unix = get_weather_openweather(city)

        # 2) Reverse geocode to state/district (for model features)
        state, district = reverse_geocode_nominatim(lat, lon)

        # 3) Current month name for model
        month_name = datetime.utcnow().strftime("%B")  # e.g., "August"

        # 4) Predict daily insolation (kWh/m^2/day) using trained model
        predicted_kwh = predict_insolation_kwh(state, district, month_name)
        
        # Validate and clamp insolation to realistic values (2-7 kWh/m²/day for India)
        if predicted_kwh <= 0 or predicted_kwh > 10:
            print(f"Warning: Model predicted unrealistic insolation: {predicted_kwh:.2f}")
            predicted_kwh = max(min(predicted_kwh, 7.0), 3.0)  # Clamp to reasonable range
            print(f"Clamped to: {predicted_kwh:.2f} kWh/m²/day")

        # 5) Convert daily kWh/m^2 to average W/m^2 during daylight hours
        daylight_hours = max((sunset_unix - sunrise_unix) / 3600.0, 1.0)  # avoid div0
        irradiance_wm2 = (predicted_kwh * 1000.0) / daylight_hours  # W/m^2 average over daylight

        # 6) Calculate Tcell, efficiency n, and power P (Watts)
        # More realistic cell temperature calculation
        Tcell = temp + ((noct - 20.0) / 800.0) * irradiance_wm2
        
        # Calculate efficiency with temperature derating
        # BETA is typically 0.004-0.005 per °C for silicon panels
        temp_loss_factor = 1 - BETA * (Tcell - 25.0)
        efficiency = N_REF * temp_loss_factor
        
        # Clamp efficiency to realistic bounds (5% to 25% for solar panels)
        efficiency = max(min(efficiency, 0.25), 0.05)
        
        P_watt = efficiency * irradiance_wm2 * panel_area
        
        # Debug output to help diagnose issues
        print(f"Debug info:")
        print(f"  Cell temp: {Tcell:.2f}°C")
        print(f"  Temp loss factor: {temp_loss_factor:.4f}")
        print(f"  Raw efficiency: {N_REF * temp_loss_factor:.4f}")
        print(f"  Clamped efficiency: {efficiency:.4f}")
        print(f"  Irradiance: {irradiance_wm2:.2f} W/m²")
        print(f"  Panel area: {panel_area} m²")

        # Display results
        text_temp.config(text=f"Temp: {temp:.2f} °C")
        text_wind.config(text=f"Wind: {wind_speed:.2f} m/s")
        text_loc.config(text=f"Location: {state} / {district} (lat={lat:.3f}, lon={lon:.3f})")
        text_insol.config(text=f"Predicted daily insolation: {predicted_kwh:.2f} kWh/m²/day")
        text_irr.config(text=f"Estimated irradiance (avg daylight): {irradiance_wm2:.2f} W/m²")
        text_tcell.config(text=f"Tcell: {Tcell:.2f} °C")
        text_eff.config(text=f"Efficiency: {efficiency*100:.2f} %")
        text_power.config(text=f"Predicted Power: {P_watt:.2f} W (for area {panel_area} m²)")

    except ValueError as ve:
        messagebox.showerror("Configuration Error", str(ve))
        # Reset loading messages
        for label in [text_temp, text_wind, text_loc, text_insol, text_irr, text_tcell, text_eff, text_power]:
            label.config(text=label.cget("text").split(":")[0] + ": N/A")
    except requests.HTTPError as he:
        messagebox.showerror("API Error", f"API request failed: {he}")
        # Reset loading messages
        for label in [text_temp, text_wind, text_loc, text_insol, text_irr, text_tcell, text_eff, text_power]:
            label.config(text=label.cget("text").split(":")[0] + ": N/A")
    except Exception as e:
        messagebox.showerror("Error", f"An unexpected error occurred: {e}")
        # Reset loading messages
        for label in [text_temp, text_wind, text_loc, text_insol, text_irr, text_tcell, text_eff, text_power]:
            label.config(text=label.cget("text").split(":")[0] + ": N/A")

# --- Build UI ---
root = tk.Tk()
root.title("ML-based Solar Power Predictor")
root.geometry("500x350")  # Set a reasonable window size

# Configure grid weights for better layout
root.columnconfigure(1, weight=1)

tk.Label(root, text="City:").grid(row=0, column=0, sticky="e", padx=6, pady=6)
entry_city = tk.Entry(root, width=30)
entry_city.grid(row=0, column=1, padx=6, pady=6, sticky="ew")

tk.Label(root, text="NOCT (°C):").grid(row=1, column=0, sticky="e", padx=6, pady=6)
entry_noct = tk.Entry(root, width=10)
entry_noct.grid(row=1, column=1, sticky="w", padx=6, pady=6)
entry_noct.insert(0, "45")  # sensible default

tk.Label(root, text="Panel area (m²):").grid(row=2, column=0, sticky="e", padx=6, pady=6)
entry_area = tk.Entry(root, width=10)
entry_area.grid(row=2, column=1, sticky="w", padx=6, pady=6)
entry_area.insert(0, "1.6")

btn = tk.Button(root, text="Predict Solar Power", command=on_predict, bg="#4CAF50", fg="white", font=("Arial", 10, "bold"))
btn.grid(row=3, column=0, columnspan=2, pady=12)

# Output labels with better formatting
output_font = ("Arial", 9)

text_temp = tk.Label(root, text="Temp: N/A", font=output_font)
text_temp.grid(row=4, column=0, columnspan=2, sticky="w", padx=6, pady=2)

text_wind = tk.Label(root, text="Wind: N/A", font=output_font)
text_wind.grid(row=5, column=0, columnspan=2, sticky="w", padx=6, pady=2)

text_loc = tk.Label(root, text="Location: N/A", font=output_font)
text_loc.grid(row=6, column=0, columnspan=2, sticky="w", padx=6, pady=2)

text_insol = tk.Label(root, text="Predicted daily insolation: N/A", font=output_font)
text_insol.grid(row=7, column=0, columnspan=2, sticky="w", padx=6, pady=2)

text_irr = tk.Label(root, text="Estimated irradiance (avg daylight): N/A", font=output_font)
text_irr.grid(row=8, column=0, columnspan=2, sticky="w", padx=6, pady=2)

text_tcell = tk.Label(root, text="Tcell: N/A", font=output_font)
text_tcell.grid(row=9, column=0, columnspan=2, sticky="w", padx=6, pady=2)

text_eff = tk.Label(root, text="Efficiency: N/A", font=output_font)
text_eff.grid(row=10, column=0, columnspan=2, sticky="w", padx=6, pady=2)

text_power = tk.Label(root, text="Predicted Power: N/A", fg="#2E7D32", font=("Arial", 9, "bold"))
text_power.grid(row=11, column=0, columnspan=2, sticky="w", padx=6, pady=2)

if __name__ == "__main__":
    root.mainloop()