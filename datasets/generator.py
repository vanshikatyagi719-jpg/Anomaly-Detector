import os
import math
import random
import pandas as pd
from datetime import datetime, timedelta


def generate_historical_dataset(file_path, row_count=1500):
    """
    Generates a structured historical time-series sensor stream.
    Incorporates operational noise, cyclical variations (sine waves),
    and introduces distinct multi-sensor failure events.
    """
    print("Generating synthetic sensor logs...")

    # Nominals and variations
    base_temp, temp_var, temp_noise = 60.0, 2.5, 0.8
    base_vib, vib_var, vib_noise = 2.0, 0.3, 0.15
    base_pres, pres_var, pres_noise = 40.0, 1.2, 0.4
    base_flow, flow_var, flow_noise = 120.0, 4.0, 1.5
    data_rows = []
    start_time = datetime.now() - timedelta(seconds=row_count * 5)

    active_fault = "NORMAL"
    fault_progress = 0.0
    for i in range(row_count):
        timestamp = (start_time + timedelta(seconds=i * 5)).isoformat()

        # Inject systematic failures at distinct blocks
        if 300 <= i < 420:
            active_fault = "BEARING_WEAR"
        elif 700 <= i < 820:
            active_fault = "COOLANT_LEAK"
        elif 1100 <= i < 1220:
            active_fault = "PIPE_BLOCKAGE"
        else:
            active_fault = "NORMAL"
        # Manage failure progress (0.0 to 1.0)
        if active_fault != "NORMAL":
            fault_progress = min(1.0, fault_progress + 0.04)
        else:
            fault_progress = 0.0
        # Math models (sine wave cycle)
        wave = math.sin(i / 20.0)
        # Baseline noise
        t_jitter = (random.random() - 0.5) * temp_noise
        v_jitter = (random.random() - 0.5) * vib_noise
        p_jitter = (random.random() - 0.5) * pres_noise
        f_jitter = (random.random() - 0.5) * flow_noise
        # nominal scaling factors
        temp_factor = 1.0
        vib_factor = 1.0
        pres_factor = 1.0
        flow_factor = 1.0
        if active_fault == "BEARING_WEAR":
            # Vibration spikes, Temp rises moderately
            vib_factor = 1.0 + (1.9 * fault_progress)
            temp_factor = 1.0 + (0.35 * fault_progress)
        elif active_fault == "COOLANT_LEAK":
            # Flow falls, Temp spikes, Pressure drops
            flow_factor = 1.0 - (0.75 * fault_progress)
            temp_factor = 1.0 + (0.58 * fault_progress)
            pres_factor = 1.0 - (0.42 * fault_progress)
        elif active_fault == "PIPE_BLOCKAGE":
            # Pressure spikes, Flow falls, slight Vibration rise
            pres_factor = 1.0 + (0.48 * fault_progress)
            flow_factor = 1.0 - (0.85 * fault_progress)
            vib_factor = 1.0 + (0.28 * fault_progress)
        # Calculate final metrics
        temperature = (base_temp + wave * temp_var) * temp_factor + t_jitter
        vibration = (base_vib + wave * vib_var) * vib_factor + v_jitter
        pressure = (base_pres + wave * pres_var) * pres_factor + p_jitter
        flow_rate = (base_flow + wave * flow_var) * flow_factor + f_jitter
        # Force positive metrics
        temperature = max(0.0, round(temperature, 2))
        vibration = max(0.0, round(vibration, 3))
        pressure = max(0.0, round(pressure, 2))
        flow_rate = max(0.0, round(flow_rate, 2))
        data_rows.append(
            {
                "Timestamp": timestamp,
                "OperationalStatus": active_fault,
                "Temperature_C": temperature,
                "Vibration_mms": vibration,
                "Pressure_bar": pressure,
                "FlowRate_Lmin": flow_rate,
            }
        )
    # Save to CSV
    df = pd.DataFrame(data_rows)
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    df.to_csv(file_path, index=False)
    print(f"Dataset generated successfully at {file_path}")


if __name__ == "__main__":
    generate_historical_dataset("sensor_data.csv")
