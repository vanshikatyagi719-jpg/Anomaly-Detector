import asyncio
import json
import math
import random
import sys
import websockets
class TelemetryProducer:
    def __init__(self, backend_url="ws://localhost:8000/ws/stream"):
        self.backend_url = backend_url
        self.time_index = 0
        
        # Nominal metrics & variation limits
        self.base_temp, self.temp_var, self.temp_noise = 60.0, 2.5, 0.8
        self.base_vib, self.vib_var, self.vib_noise = 2.0, 0.3, 0.15
        self.base_pres, self.pres_var, self.pres_noise = 40.0, 1.2, 0.4
        self.base_flow, self.flow_var, self.flow_noise = 120.0, 4.0, 1.5
        
        # Local failure state trackers (updated when receiving replies or default to NORMAL)
        self.active_fault = "NORMAL"
        self.failure_progress = 0.0
    def generate_packet(self):
        """
        Calculates physical sensor oscillations and noise.
        """
        self.time_index += 1
        
        # Natural mechanical hum (sine wave cycle)
        wave = math.sin(self.time_index / 20.0)
        # Baseline physical jitter noise
        t_jitter = (random.random() - 0.5) * self.temp_noise
        v_jitter = (random.random() - 0.5) * self.vib_noise
        p_jitter = (random.random() - 0.5) * self.pres_noise
        f_jitter = (random.random() - 0.5) * self.flow_noise
        # nominal scaling factors
        temp_factor = 1.0
        vib_factor = 1.0
        pres_factor = 1.0
        flow_factor = 1.0
        # Mathematical failure profiles (activated depending on active server configuration)
        if self.active_fault == "BEARING_WEAR":
            self.failure_progress = min(1.0, self.failure_progress + 0.05)
            vib_factor = 1.0 + (1.95 * self.failure_progress)
            temp_factor = 1.0 + (0.35 * self.failure_progress)
        elif self.active_fault == "COOLANT_LEAK":
            self.failure_progress = min(1.0, self.failure_progress + 0.05)
            flow_factor = 1.0 - (0.75 * self.failure_progress)
            temp_factor = 1.0 + (0.58 * self.failure_progress)
            pres_factor = 1.0 - (0.42 * self.failure_progress)
        elif self.active_fault == "PIPE_BLOCKAGE":
            self.failure_progress = min(1.0, self.failure_progress + 0.05)
            pres_factor = 1.0 + (0.48 * self.failure_progress)
            flow_factor = 1.0 - (0.85 * self.failure_progress)
            vib_factor = 1.0 + (0.28 * self.failure_progress)
        else:
            self.failure_progress = 0.0
        # Generate metrics
        temperature = (self.base_temp + wave * self.temp_var) * temp_factor + t_jitter
        vibration = (self.base_vib + wave * self.vib_var) * vib_factor + v_jitter
        pressure = (self.base_pres + wave * self.pres_var) * pres_factor + p_jitter
        flow_rate = (self.base_flow + wave * self.flow_var) * flow_factor + f_jitter

    
        # Random anomaly injection (8% probability)
        anomaly_type = None
        if random.random() < 0.08:
            anomaly_type = random.choice([
                "TEMP_SPIKE",
                "VIBRATION_SPIKE",
                "PRESSURE_DROP",
            ])

            if anomaly_type == "TEMP_SPIKE":
                temperature += random.uniform(20, 35)
            elif anomaly_type == "VIBRATION_SPIKE":
                vibration += random.uniform(2, 4)
            elif anomaly_type == "PRESSURE_DROP":
                pressure -= random.uniform(10, 18)

            print(f"⚠ Synthetic anomaly generated: {anomaly_type}")
        # Clamp positive
        temperature = max(0.0, round(temperature, 2))
        vibration = max(0.0, round(vibration, 3))
        pressure = max(0.0, round(pressure, 2))
        flow_rate = max(0.0, round(flow_rate, 2))
        return {
            "type": "telemetry",
            "payload": {
                "readings": {
                    "temperature": temperature,
                    "vibration": vibration,
                    "pressure": pressure,
                    "flowRate": flow_rate
                }
            }
        }
    async def run(self):
        """
        Main execution loop. Retries connection indefinitely and streams telemetry.
        """
        print(f"[Streaming] Initializing Telemetry Producer, connecting to {self.backend_url}")
        
        while True:
            try:
                async with websockets.connect(self.backend_url) as ws:
                    print("[Streaming] Connected successfully to API WebSocket Gateway!")
                    
                    while True:
                        # 1. Generate new real-time physical packet
                        packet = self.generate_packet()
                        
                        # 2. Push packet to API server
                        await ws.send(json.dumps(packet))
                        
                        # 3. Read reply from server (useful to check active server side fault mode updates)
                        try:
                            # Wait for standard reply buffer
                            reply_str = await asyncio.wait_for(ws.recv(), timeout=0.01)
                            reply = json.loads(reply_str)
                            if "payload" in reply and "status" in reply["payload"]:
                                # Sync server side fault state back to local simulator
                                if self.active_fault != reply["payload"]["status"]:
                                    self.active_fault = reply["payload"]["status"]
                                    self.failure_progress = 0.0
                                    print(f"[Streaming] Synced Failure Mode from server: {self.active_fault}")
                        except asyncio.TimeoutError:
                            # It is normal to timeout if server did not send packet back yet
                            pass
                            
                        # Stream ticking at 300ms intervals
                        await asyncio.sleep(0.3)
                        
            except (websockets.exceptions.ConnectionClosed, ConnectionRefusedError, OSError) as e:
                print(f"[Streaming] Connection failed/lost. Retrying in 2 seconds... (Error: {e})")
                await asyncio.sleep(2.0)
            except Exception as e:
                print(f"[Streaming] Unexpected error: {e}. Exiting.")
                break
if __name__ == "__main__":
    producer = TelemetryProducer()
    try:
        asyncio.run(producer.run())
    except KeyboardInterrupt:
        print("[Streaming] Shutting down producer.")