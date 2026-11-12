# Writes three 12-second mono WAV tones (22.05 kHz, 16-bit) used by phase0.test.js.
# Usage: python3 -I make-fixtures.py <output-dir>
import sys, wave, struct, math, os
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
for name, f in [('Artist A - Song One.wav', 220), ('Artist B - Song Two.wav', 330), ('Artist C - Song Three.wav', 440)]:
    w = wave.open(os.path.join(out, name), 'wb'); w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
    w.writeframes(b''.join(struct.pack('<h', int(9000 * math.sin(2 * math.pi * f * i / 22050))) for i in range(22050 * 12)))
    w.close()
