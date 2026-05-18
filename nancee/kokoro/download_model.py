from huggingface_hub import hf_hub_download
import os

# Create directory
os.makedirs("./phi3-model", exist_ok=True)

# Download Q4_K_M version
model_path = hf_hub_download(
    repo_id="tensorblock/Phi-3-mini-4k-instruct-GGUF",
    filename="Phi-3-mini-4k-instruct-Q4_K_M.gguf",
    local_dir="./phi3-model",
    local_dir_use_symlinks=False
)

print(f"Downloaded to: {model_path}")
