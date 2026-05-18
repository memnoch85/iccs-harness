from kokoro_onnx import Kokoro
import soundfile as sf
import os

print("Loading model...")

kokoro = Kokoro(
    "kokoro-v1.0.int8.onnx",
    "voices-v1.0.bin"
)

print("Generating speech...")

samples, sample_rate = kokoro.create(
    "Hello aunndesh. Nancee is online.",
    voice="af_heart",
    speed=1.0,
    lang="en-us"
)

sf.write("hello.wav", samples, sample_rate)

print("Playing audio...")

os.system("aplay hello.wav")
