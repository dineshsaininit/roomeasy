import serial
import time
import pandas as pd
from datetime import datetime

SERIAL_PORT = 'COM5' 
BAUD_RATE = 9600
READ_COMMAND = b'\xFF\x01\x86\x00\x00\x00\x00\x00\x79'

# List to store our data rows
net_value = []

def decode_packet(packet):
    """Parses the hex packet into actual physical sensor metrics."""
    if len(packet) >= 26 and packet[0] == 0xFF and packet[1] == 0x86:
        
        current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        # 1. Particulate Matter & CO2 
        pm1_0 = (packet[2] << 8) | packet[3]
        pm2_5 = (packet[4] << 8) | packet[5]
        pm10  = (packet[6] << 8) | packet[7]
        co2   = (packet[8] << 8) | packet[9]
        
        # 2. Volatile Gases 
        tvoc = (packet[10] << 8) | packet[11]
        ch2o = (packet[12] << 8) | packet[13]
        
        # Append to our dataset 
        net_value.append({
            'Timestamp': current_time,
            'PM_1.0': pm1_0,
            'PM_2.5': pm2_5,
            'PM_10': pm10,
            'CO2': co2,
            'TVOC': tvoc,
            'CH2O': ch2o
        })
        
        # Print a clean dashboard to the terminal
        print("\n" + "="*35)
        print("LIVE AQI DATA COLLECTION")
        print("="*35)
        print(f"Time   : {current_time}")
        print("-" * 35)
        print(f"PM 1.0 : {pm1_0} µg/m³")
        print(f"PM 2.5 : {pm2_5} µg/m³")
        print(f"PM 10  : {pm10} µg/m³")
        print(f"CO2    : {co2} ppm")
        print(f"TVOC   : {tvoc} (Raw)")
        print(f"CH2O   : {ch2o} (Raw)")
        print("="*35)
    else:
        print("Received incomplete packet. Waiting...")

def run_aqi_monitor():
    print(f"Opening {SERIAL_PORT} at {BAUD_RATE} baud...")
    
    try:
        ser = serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2)
        print("Connected! Starting data collection (Press Ctrl+C to stop)...")
        ser.reset_input_buffer()
        
        while True:
            # Ping the sensor
            ser.write(READ_COMMAND)
            time.sleep(0.5)
            
            # Read and decode the reply
            if ser.in_waiting >= 26:
                raw_bytes = ser.read(26)
                decode_packet(raw_bytes)
                ser.reset_input_buffer()
                
            time.sleep(2) 

    except serial.SerialException as e:
        print(f"\n[!] Connection Error: {e}")
    except KeyboardInterrupt:
        print("\n[!] Data collection stopped by user.")
    finally:
        if 'ser' in locals() and ser.is_open:
            ser.close()
            print("Serial port closed.")
            
        if net_value:
            print(f"Saving {len(net_value)} rows of data...")
            df = pd.DataFrame(net_value)
            df.to_csv("pollutant_new_iot.csv", index=False)
            print("Data successfully saved to pollutant_new_iot.csv")

if __name__ == '__main__':
    run_aqi_monitor()