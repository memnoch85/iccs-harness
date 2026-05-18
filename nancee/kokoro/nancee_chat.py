import subprocess
from kokoro_onnx import Kokoro
import soundfile as sf
import os
import random
import time
import threading
import queue
import re
import onnxruntime as ort
import sounddevice as sd
import gc
import resource

# 8GB Performance optimizations
os.environ["OMP_NUM_THREADS"] = "4"
os.environ["OLLAMA_KV_CACHE_TYPE"] = "f16"  # Full precision - you have 8GB!
os.environ["OLLAMA_NUM_PARALLEL"] = "2"      # Can handle 2 requests

print("Loading Kokoro with optimized ONNX Runtime...")

# Create optimized ONNX Runtime session
sess_options = ort.SessionOptions()
sess_options.intra_op_num_threads = 4      # Match Pi 5 cores
sess_options.inter_op_num_threads = 1      # Sequential execution
sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
sess_options.enable_cpu_mem_arena = True   # Better memory management
sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

# Get available providers (CPU only for Pi)
providers = ['CPUExecutionProvider']

# Create session with optimizations
session = ort.InferenceSession(
    "kokoro-v1.0.int8.onnx",
    sess_options=sess_options,
    providers=providers
)

# Initialize Kokoro with optimized session
kokoro = Kokoro.from_session(session, "voices-v1.0.bin")

print("Pre-generating filler phrases...")
thinking_phrases = [
    "Hmm, let me think about that...",
    "Okay, just a second...",
    "Let me think...",
    "Interesting...",
    "Alright...",
    "Hold on a moment..."
]

# Response cache for repeated phrases
response_cache = {}
CACHE_MAX = 20

pregen_fillers = {}
for phrase in thinking_phrases:
    samples, sample_rate = kokoro.create(
        phrase,
        voice="af_heart",
        speed=0.9,
        lang="en-us"
    )
    pregen_fillers[phrase] = (samples, sample_rate)
    print(f"  ✓ Pre-generated: '{phrase[:20]}...'")

def speak_pregen(text, filename):
    print(f"\n[Filler: {text}]")
    samples, sample_rate = pregen_fillers[text]
    sf.write(filename, samples, sample_rate)
    os.system(f"aplay --buffer-size=2048 {filename} > /dev/null 2>&1")

def speak_final(text):
    text = text.strip().strip('"\'')
    if not text:
        text = "I'm not sure what to say about that."
    if not re.search(r'[.!?]$', text):
        text += '.'
    print(f"\nNancee: {text}")
    tts_start = time.time()
    samples, sample_rate = kokoro.create(
        #text[:120],
        ' '.join(text.split()[:16]),
        voice="af_heart",
        speed=1.2,
        lang="en-us"
    )
    tts_end = time.time()
    print(f"[TTS: {tts_end - tts_start:.2f}s]")
    playback_start = time.time()
    #sd.play(samples, sample_rate)
    #sd.wait()
    sd.stop()
    sd.play(samples, sample_rate)
    playback_end = time.time()
    print(f"[Playback: {playback_end - playback_start:.2f}s]")

def run_llm(prompt, result_queue):
    llm_start = time.time()
    print(f"[LLM start: {time.strftime('%H:%M:%S')}]")
    try:
        # Set memory limit to force cache clearing
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024 * 1024 * 1024, 4 * 1024 * 1024 * 1024))
        
        result = subprocess.run(
            ["ollama", "run", "qwen2.5:1.5b"],
            input=f"/set parameter num_predict 18\n{prompt}",
            capture_output=True,
            text=True,
            timeout=60,
            encoding='utf-8'
        )
        response = result.stdout.strip()

        # Clean up
        response = re.sub(r'^(User:|Nancee:)\s*', '', response, flags=re.IGNORECASE)
        response = response.split('\n')[0]

        if not response or len(response) < 2:
            response = "That's interesting!"

        print(f"[LLM done: {time.time() - llm_start:.2f}s]")
        result_queue.put(response)

    except subprocess.TimeoutExpired:
        print(f"[LLM timeout after 60s]")
        result_queue.put("I'm still thinking. Please ask again.")
    except Exception as e:
        print(f"[LLM error: {e}]")
        result_queue.put("I encountered an error. Please try again.")

print("\nLoading qwen2.5:1.5b (8GB optimized)...")
try:
    subprocess.run(
        ["ollama", "run", "qwen2.5:1.5b", "Warmup"],
        capture_output=True,
        timeout=60
    )
    print("✓ Model loaded with f16 precision")
except:
    print("⚠️ Warmup continuing...")

# Shorter boot wait since you have 8GB (60s was for 4GB)
print("Waiting 60 seconds for system to stabilize...")
for i in range(60, 0, -1):
    print(f"  {i}s", end='\r')
    time.sleep(1)
print("\n")

# Boot message
print("Preparing boot message...")
boot_samples, boot_rate = kokoro.create(
    "Nancee is online and ready to ride!",
    voice="af_heart",
    speed=0.9,
    lang="en-us"
)
sf.write("boot.wav", boot_samples, boot_rate)
os.system("aplay boot.wav > /dev/null 2>&1")

print("\n✅ Nancee ready! (8GB mode)\n")

# Track conversation turns for memory refresh
conversation_counter = 0
REFRESH_AFTER = 3  # Refresh model every 3 responses

while True:
    try:
        total_start = time.time()
        user_input = input("You: ")

        if user_input.lower() in ["quit", "exit", "bye"]:
            speak_final("It's been a wonderful journey. Until next time!")
            break

        if not user_input.strip():
            continue

        prompt = f"""Act as Nancee - witty, warm, sarcastic, emotionally connected road trip companion. One sentence only. Max 14 words.

        User: {user_input}
        Nancee:"""

        result_queue = queue.Queue()
        llm_thread = threading.Thread(target=run_llm, args=(prompt, result_queue))
        llm_thread.start()

        try:
            response = result_queue.get(timeout=8)
            print(f"\n[Fast response!]")
            speak_final(response)

        except queue.Empty:
            print(f"\n[Playing filler...]")
            filler = random.choice(thinking_phrases)
            filler_thread = threading.Thread(target=speak_pregen, args=(filler, "thinking.wav"))
            filler_thread.start()

            try:
                response = result_queue.get(timeout=52)
                filler_thread.join(timeout=1)
                print(f"\n[Response received]")
                speak_final(response)

            except queue.Empty:
                print(f"\n[Timeout after 60s]")
                filler_thread.join(timeout=1)
                speak_final("I'm having trouble thinking. Please ask again.")

        print(f"\n[Round trip: {time.time() - total_start:.1f}s]")
        print("-" * 40)
        
        # Increment conversation counter
        conversation_counter += 1
        
        # Refresh memory every REFRESH_AFTER responses to prevent slowdown
        if conversation_counter >= REFRESH_AFTER:
            print("\n[🔄 MEMORY REFRESH - Clearing cache to prevent slowdown]")
            # Force garbage collection
            gc.collect()
            # Clear response cache (optional - comment out if you want to keep cache)
            # response_cache.clear()
            print("[✓ Memory refresh complete]")
            conversation_counter = 0

    except KeyboardInterrupt:
        print("\n\nGoodbye!")
        break
