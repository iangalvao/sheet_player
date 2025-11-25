import math
import simpleaudio as sa

SAMPLE_RATE = 44100

def beep():
    duration_s = 1.0
    freq = 440.0
    num_samples = int(SAMPLE_RATE * duration_s)
    amp = 8000

    buf = bytearray()
    for i in range(num_samples):
        t = i / SAMPLE_RATE
        sample = math.sin(2 * math.pi * freq * t)
        sample_int = int(amp * sample)
        buf.extend(sample_int.to_bytes(2, "little", signed=True))

    audio = bytes(buf)
    play_obj = sa.play_buffer(audio, 1, 2, SAMPLE_RATE)
    play_obj.wait_done()

if __name__ == "__main__":
    beep()
    print("finished beep()")
