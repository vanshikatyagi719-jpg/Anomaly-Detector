import os
import pandas as pd
import numpy as np
from sklearn.ensemble import IsolationForest


class AnomalyDetector:
    def __init__(self):
        # Baseline statistical metrics (nominal benchmarks)
        self.baselines = {
            "temperature": {"mean": 60.0, "std": 2.6},
            "vibration": {"mean": 2.0, "std": 0.33},
            "pressure": {"mean": 40.0, "std": 1.25},
            "flowRate": {"mean": 120.0, "std": 4.1},
        }

        # Initialize ML model
        self.model = None
        self.trained = False

    def train(self, data_path):
        """
        Loads the historical dataset, calculates exact baseline statistics,
        and trains an unsupervised scikit-learn Isolation Forest model.
        """
        if not os.path.exists(data_path):
            print(
                f"[Engine] Training data not found at {data_path}. Running generator..."
            )
            # Import generator locally to avoid circular dependencies
            from datasets.generator import generate_historical_dataset

            generate_historical_dataset(data_path, row_count=1500)
        df = pd.read_csv(data_path)
        print(f"[Engine] Loaded {len(df)} records for training.")
        # 1. Isolate nominal baseline rows to teach the model "what normal is"
        normal_data = df[df["OperationalStatus"] == "NORMAL"]
        features = ["Temperature_C", "Vibration_mms", "Pressure_bar", "FlowRate_Lmin"]

        if len(normal_data) < 100:
            print("[Engine] Warning: Too few normal rows. Training on entire dataset.")
            normal_data = df

        X_train = normal_data[features].values
        # 2. Compute true statistical mean and standard deviation
        for i, key in enumerate(["temperature", "vibration", "pressure", "flowRate"]):
            col = features[i]
            mean_val = float(df[col].mean())
            std_val = float(df[col].std())
            self.baselines[key]["mean"] = mean_val
            # Avoid division by zero
            self.baselines[key]["std"] = std_val if std_val > 0 else 1.0
        # 3. Train the Isolation Forest
        # contamination represents expected ratio of anomalies (e.g. 5%)
        self.model = IsolationForest(
            n_estimators=100, contamination=0.10, random_state=42
        )
        self.model.fit(X_train)
        self.trained = True

        print("[Engine] ML Anomaly Detector trained successfully!")
        print(f"[Engine] Calculated Baselines: {self.baselines}")

    def score_telemetry(self, current_data):
        """
        Scores a live streaming telemetry reading.
        Returns calculated Z-Scores and the ML Isolation Forest anomaly flag.

        current_data format: {
            "temperature": 60.5,
            "vibration": 2.1,
            "pressure": 40.2,
            "flowRate": 120.4
        }
        """
        if not self.trained:
            # Fallback to defaults if not trained
            pass
        readings = current_data

        # 1. Compute individual Z-scores
        z_scores = {}
        alarms = {}

        for key in ["temperature", "vibration", "pressure", "flowRate"]:
            val = readings[key]
            mean = self.baselines[key]["mean"]
            std = self.baselines[key]["std"]

            z = (val - mean) / std
            z_scores[key] = round(z, 2)

            # Simple thresholding alarm: Z-Score > 3.0 or Z-Score < -3.0
            alarms[key] = abs(z) > 2.0
        # 2. Run multi-variable ML Isolation Forest prediction
        ml_anomaly = False
        if self.trained and self.model:
            # Feature array: [Temp, Vib, Pres, Flow]
            X_new = np.array(
                [
                    [
                        readings["temperature"],
                        readings["vibration"],
                        readings["pressure"],
                        readings["flowRate"],
                    ]
                ]
            )

            # predict returns 1 (normal) or -1 (anomaly)
            prediction = self.model.predict(X_new)[0]
            ml_anomaly = bool(prediction == -1)
        # 3. Compile structural analytics report
        # We trigger a global anomaly if ML flags it OR any Z-score is critical
        global_anomaly = ml_anomaly or any(alarms.values())
        return {
            "z_scores": z_scores,
            "alarms": alarms,
            "ml_anomaly": ml_anomaly,
            "global_anomaly": global_anomaly,
        }


# Singleton instance for simple module imports
detector = AnomalyDetector()
# Bootstrap auto-training when file is imported / executed directly
if __name__ == "__main__":
    detector.train(os.path.join("datasets", "sensor_data.csv"))
    test_normal = {
        "temperature": 61.2,
        "vibration": 1.95,
        "pressure": 39.8,
        "flowRate": 121.5,
    }
    test_failure = {
        "temperature": 94.0,
        "vibration": 2.1,
        "pressure": 24.0,
        "flowRate": 29.0,
    }
    print("Normal Test Result:", detector.score_telemetry(test_normal))
    print("Failure Test Result:", detector.score_telemetry(test_failure))
else:
    # Auto-initialize baseline model
    dataset_csv = os.path.join(os.path.dirname(__file__), "datasets", "sensor_data.csv")
    try:
        detector.train(dataset_csv)
    except Exception as e:
        print("[Engine] Auto-training deferred: ", e)
