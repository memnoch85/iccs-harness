# Nancee Sherpa/Kokoro Runtime

Local Nancee runtime using:

* Sherpa ONNX + Kokoro for TTS
* Ollama for the LLM
* `system-prompt.txt` for the shared personality prompt
* systemd warmup to preload the selected Ollama model at boot

## Files

```text
config.py
nancee_chat.py
ollama_runtime.py
nancee-ollama-warmup
nancee-llm-warmup@.service
system-prompt.txt
kokoro-multi-lang-v1_0/
venv/
```

Do not commit:

```text
venv/
__pycache__/
kokoro-multi-lang-v1_0/
```

## Kokoro assets

Extract the Kokoro model into:

```text
sherpa/kokoro-multi-lang-v1_0/
```

It should contain files such as:

```text
model.onnx
voices.bin
tokens.txt
espeak-ng-data/
lexicon-us-en.txt
lexicon-zh.txt
```

## Python environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install numpy sounddevice sherpa-onnx
```

## Run Nancee

```bash
source venv/bin/activate
python3 nancee_chat.py
```

Exit with:

```text
q
quit
exit
```

## Configuration

Runtime settings are stored in:

```text
config.py
```

Common environment overrides:

```bash
export LLM_MODEL=llama3.2:3b
export VOICE_ID=3
export SPEED=1.2
export SHERPA_THREADS=4
```

The shared prompt is stored in:

```text
system-prompt.txt
```

Both the chat runtime and warmup script must use the same prompt.

## Install the warmup command

```bash
sudo cp nancee-ollama-warmup \
  /usr/local/bin/nancee-ollama-warmup

sudo chmod 755 \
  /usr/local/bin/nancee-ollama-warmup
```

Manual warmup:

```bash
/usr/local/bin/nancee-ollama-warmup llama3.2:3b
```

## Install the systemd service

```bash
sudo cp nancee-llm-warmup@.service \
  /etc/systemd/system/nancee-llm-warmup@.service

sudo systemctl daemon-reload
```

Enable the selected model at boot:

```bash
sudo systemctl enable --now \
  nancee-llm-warmup@llama3.2:3b.service
```

Check status:

```bash
systemctl status \
  nancee-llm-warmup@llama3.2:3b.service \
  --no-pager -l
```

View logs:

```bash
journalctl \
  -u nancee-llm-warmup@llama3.2:3b.service \
  -n 100 \
  --no-pager
```

For this oneshot service, the following is normal:

```text
Active: active (exited)
```

Confirm the model is loaded:

```bash
ollama ps
```

## Change models

Pull the new model:

```bash
ollama pull NEW_MODEL
```

Disable the old service:

```bash
sudo systemctl disable --now \
  nancee-llm-warmup@OLD_MODEL.service

ollama stop OLD_MODEL
```

Enable the new service:

```bash
sudo systemctl enable --now \
  nancee-llm-warmup@NEW_MODEL.service
```

Set the same model in `config.py` or with:

```bash
export LLM_MODEL=NEW_MODEL
```

The Python model and systemd model must match.

## Cold-start test

```bash
ollama stop llama3.2:3b

sudo systemctl restart \
  nancee-llm-warmup@llama3.2:3b.service

ollama ps

python3 nancee_chat.py
```

## Timeouts

Current recommended timeout order:

```text
Warmup helper:   120 seconds
Python caller:   125 seconds
systemd service: 115 seconds
Normal response: 120 seconds
```

After changing the service file:

```bash
sudo cp nancee-llm-warmup@.service \
  /etc/systemd/system/nancee-llm-warmup@.service

sudo systemctl daemon-reload
```
