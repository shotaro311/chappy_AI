import sys
import os
import time
import numpy as np
import sounddevice as sd

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from src.config.loader import load_config
from src.audio.output_stream import AudioOutputStream

def main():
    print("=== Audio Output Test ===")
    
    # 1. List Devices
    print("\n[1] Available Devices:")
    print(sd.query_devices())
    
    # 2. Load Config
    print("\n[2] Loading Config (pc.dev)...")
    os.environ["APP_ENV"] = "pc.dev"
    config = load_config()
    print(f"Config loaded. Output Device: {config.audio.output_device}")
    
    # 3. Initialize Stream (24kHz for Realtime API simulation)
    SAMPLE_RATE = 24000
    print(f"\n[3] Initializing AudioOutputStream with {SAMPLE_RATE}Hz...")
    
    try:
        stream = AudioOutputStream(config, output_sample_rate=SAMPLE_RATE)
        stream.open()
        print("Stream opened successfully.")
        
        # 4. Generate Sine Wave (440Hz, 1 second)
        print("\n[4] Generating 440Hz Sine Wave (1 sec)...")
        duration = 1.0
        t = np.linspace(0, duration, int(SAMPLE_RATE * duration), False)
        # Generate float32 sine wave
        tone = np.sin(440 * 2 * np.pi * t)
        # Convert to int16 as expected by AudioOutputStream.play
        tone_int16 = (tone * 32767).astype(np.int16)
        
        # 5. Play
        print("Playing...")
        stream.play(tone_int16.tobytes())
        
        # Wait for playback to finish (play is non-blocking usually, but sounddevice.write blocks if buffer full? 
        # Actually AudioOutputStream.play calls stream.write. sd.OutputStream.write is blocking by default?
        # Let's wait a bit just in case.
        time.sleep(1.5)
        
        print("Playback finished.")
        
        stream.close()
        print("Stream closed.")
        
    except Exception as e:
        print(f"\n[ERROR] Failed to play audio: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
