import serial
import serial.tools.list_ports
import time
import pynmea2
import matplotlib.pyplot as plt
import math
from collections import deque

def list_serial_ports():
    """Lists available COM ports."""
    ports = serial.tools.list_ports.comports()
    return [port.device for port in ports]

def haversine_heading(lat1, lon1, lat2, lon2):
    """Calculates heading (bearing) between two latitude/longitude points."""
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    delta_lon = lon2 - lon1

    x = math.sin(delta_lon) * math.cos(lat2)
    y = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    heading = math.atan2(x, y)
    heading = math.degrees(heading)
    return (heading + 360) % 360  # Normalize to 0-360 degrees

def read_nmea_rmc(ser, test_duration):
    """Reads NMEA RMC messages, applies speed filtering, and calculates heading."""
    start_time = time.time()
    prev_lat, prev_lon = None, None
    last_valid_heading = None  # Store last valid heading
    last_speed = None  # Store last known speed
    speed_buffer = deque(maxlen=5)  # Store last 5 speeds for smoothing
    calculated_headings, reported_headings, timestamps = [], [], []
    previous_fixes = deque(maxlen=5)  # Stores last 5 fixes for smoothing
    first_heading_calculated = False  # Ensure at least one calculation is done

    print("Listening for NMEA RMC messages...")
    while (time.time() - start_time) < test_duration:
        line = ser.readline().decode(errors='ignore').strip()
        if line.startswith("$GNRMC") or line.startswith("$GPRMC"):  # Detect RMC message
            try:
                msg = pynmea2.parse(line)
                if msg.status != 'A':  # Ignore invalid fixes
                    continue

                lat = msg.latitude
                lon = msg.longitude
                reported_heading = float(msg.true_course) if msg.true_course else None
                speed_m_s = msg.spd_over_grnd * 0.514444  # Convert knots to m/s
                timestamp = time.time() - start_time

                # Add speed to rolling buffer
                speed_buffer.append(speed_m_s)
                avg_speed = sum(speed_buffer) / len(speed_buffer)  # Compute rolling average speed

                # Compute speed difference
                speed_diff = abs(speed_m_s - last_speed) if last_speed is not None else 0

                # Add the latest fix to history
                previous_fixes.append((lat, lon))

                if prev_lat is not None and prev_lon is not None:
                    if not first_heading_calculated:
                        # Compute the first heading regardless of speed
                        last_valid_heading = haversine_heading(prev_lat, prev_lon, lat, lon)
                        first_heading_calculated = True  # Ensure only one initial calculation

                    elif speed_diff > 0.2 or avg_speed > 0.2:
                        # Use smoothed location for heading calculation
                        avg_lat = sum(f[0] for f in previous_fixes) / len(previous_fixes)
                        avg_lon = sum(f[1] for f in previous_fixes) / len(previous_fixes)
                        last_valid_heading = haversine_heading(avg_lat, avg_lon, lat, lon)

                    elif last_valid_heading is not None:
                        print(f"Speed change too small (Δ={speed_diff:.3f} m/s) -> Keeping last heading: {last_valid_heading:.2f}°")

                    # Only store values when both are valid
                    if last_valid_heading is not None and reported_heading is not None:
                        calculated_headings.append(math.radians(last_valid_heading))
                        reported_headings.append(math.radians(reported_heading))
                        timestamps.append(timestamp)

                        print(f"Time: {timestamp:.1f}s | Speed: {speed_m_s:.2f} m/s | Δ Speed: {speed_diff:.3f} m/s | "
                              f"Avg Speed: {avg_speed:.2f} m/s | Calc Heading: {last_valid_heading:.2f}° | Reported Heading: {reported_heading:.2f}°")

                prev_lat, prev_lon = lat, lon  # Update last fix
                last_speed = speed_m_s  # Store last known speed

            except pynmea2.ParseError:
                continue  # Skip parsing errors

    return timestamps, calculated_headings, reported_headings

def plot_headings_polar(timestamps, calc_headings, reported_headings):
    """Plots calculated vs. reported heading using a polar plot."""
    plt.figure(figsize=(7, 7))
    ax = plt.subplot(111, polar=True)

    # Filter out None values before plotting
    calc_headings = [h for h in calc_headings if h is not None]
    reported_headings = [h for h in reported_headings if h is not None]

    # Plot calculated and reported headings
    ax.plot(calc_headings, timestamps, 'bo', label="Calculated Heading")  # Blue circles
    ax.plot(reported_headings, timestamps, 'ro', linestyle="dashed", label="Reported Heading")  # Red squares

    ax.set_theta_zero_location("N")  # 0° is North
    ax.set_theta_direction(-1)  # Clockwise direction

    plt.title("Calculated vs. Reported Heading (Polar Plot)")
    plt.legend()
    plt.show()

def main():
    # Step 1: Detect available COM ports
    ports = list_serial_ports()
    if not ports:
        print("No COM ports detected. Please connect a GNSS receiver.")
        return

    print("Available COM Ports:")
    for i, port in enumerate(ports):
        print(f"{i + 1}: {port}")

    # Step 2: Ask user to select a COM port
    port_index = int(input("Select COM port (number): ")) - 1
    selected_port = ports[port_index]

    # Step 3: Ask for baud rate and settings
    baud_rate = int(input("Enter baud rate (e.g., 9600, 115200): "))
    test_duration = int(input("Enter test duration in seconds: "))

    # Step 4: Open serial connection
    try:
        ser = serial.Serial(selected_port, baud_rate, timeout=1)
        print(f"Connected to {selected_port} at {baud_rate} baud.")
    except serial.SerialException as e:
        print(f"Error opening serial port: {e}")
        return

    # Step 5: Read NMEA RMC messages
    timestamps, calc_headings, reported_headings = read_nmea_rmc(ser, test_duration)

    # Step 6: Close the serial port
    ser.close()
    print("Test complete. Serial port closed.")

    # Step 7: Plot results using a polar plot
    if timestamps:
        plot_headings_polar(timestamps, calc_headings, reported_headings)
    else:
        print("No valid data received.")

if __name__ == "__main__":
    main()
